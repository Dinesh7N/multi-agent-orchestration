"""Error types and helpers for the debate workflow."""

from __future__ import annotations

import re
from typing import Any

import click


class SchemaNotInitializedError(click.ClickException):
    """Raised when the database schema/migrations have not been applied."""


_PG_MISSING_RELATION_RE = re.compile(r'relation "(?P<table>[^"]+)" does not exist', re.IGNORECASE)
_SQLITE_MISSING_TABLE_RE = re.compile(r"no such table:\s*(?P<table>[A-Za-z0-9_]+)", re.IGNORECASE)


def _unwrap_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def missing_table_name(exc: BaseException) -> str | None:
    """Best-effort extraction of the missing table name from a DB exception."""
    for e in _unwrap_exception_chain(exc):
        message = str(e)
        match = _PG_MISSING_RELATION_RE.search(message) or _SQLITE_MISSING_TABLE_RE.search(message)
        if match:
            return match.group("table")
    return None


def is_schema_missing_error(exc: BaseException) -> bool:
    """Return True if the exception looks like a missing-table / missing-schema error."""
    name = missing_table_name(exc)
    if name:
        return True

    # Fallback for drivers that don't format errors consistently.
    for e in _unwrap_exception_chain(exc):
        message = str(e).lower()
        if "undefinedtableerror" in message:
            return True
        if "does not exist" in message and "relation" in message:
            return True
    return False


def schema_not_initialized_message(exc: BaseException) -> str:
    table = missing_table_name(exc)
    table_hint = f" (missing table `{table}`)" if table else ""

    lines: list[str] = [
        f"Database schema is not initialized{table_hint}.",
        "Run: `uv run alembic upgrade head`",
        "Or validate with: `uv run debate schema-check`",
    ]
    return "\n".join(lines)
