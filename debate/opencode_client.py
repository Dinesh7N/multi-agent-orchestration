from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _require_httpx() -> Any:
    try:
        return importlib.import_module("httpx")
    except ModuleNotFoundError as e:
        raise OpencodeAPIError(
            "Missing dependency 'httpx'. Install it in this project's environment (see pyproject.toml)."
        ) from e


def _require_httpx_sse() -> Any:
    try:
        return importlib.import_module("httpx_sse")
    except ModuleNotFoundError as e:
        raise OpencodeAPIError(
            "Missing dependency 'httpx-sse'. Install it in this project's environment (see pyproject.toml)."
        ) from e


class OpencodeAPIError(RuntimeError):
    """Raised when the OpenCode server returns an error."""


@dataclass(frozen=True)
class OpencodePromptResult:
    session_id: str
    message_id: str
    raw_output: str
    response_json: dict[str, Any]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _extract_text(parts: list[dict[str, Any]]) -> str:
    # Most useful text lives in parts with type == "text".
    texts: list[str] = []
    for part in parts:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
    return "".join(texts).strip()


class OpencodeClient:
    """Async client for the OpenCode local server."""

    def __init__(
        self,
        *,
        base_url: str,
        directory: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._directory = directory

        self._httpx = _require_httpx()
        self._timeout = self._httpx.Timeout(timeout_seconds)
        self._client = self._httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    def set_directory(self, directory: str | None) -> None:
        self._directory = directory

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: Any | None = None,
    ) -> Any:
        try:
            resp = await self._client.request(method, path, params=params, json=body)
            resp.raise_for_status()
            return resp
        except self._httpx.RequestError as e:
            raise OpencodeAPIError(f"OpenCode request failed ({method} {path}): {e}") from e
        except self._httpx.HTTPStatusError as e:
            status = e.response.status_code
            text = e.response.text
            raise OpencodeAPIError(f"OpenCode API error {status} ({method} {path}): {text}") from e

    async def health_check(self) -> None:
        await self._request("GET", "/session")

    async def list_sessions(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/session")
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []

    async def guess_active_directory(self) -> str | None:
        """Heuristic: pick the most recently updated session directory."""
        sessions = await self.list_sessions()
        best: tuple[float, str] | None = None
        for s in sessions:
            directory = s.get("directory")
            time_obj = s.get("time")
            updated = None
            if isinstance(time_obj, dict):
                updated = time_obj.get("updated")
            if not isinstance(directory, str) or not isinstance(updated, (int, float)):
                continue
            if best is None or float(updated) > best[0]:
                best = (float(updated), directory)
        return best[1] if best else None

    async def create_session(self, *, title: str, parent_id: str | None = None) -> str:
        """Create a new session and return session_id."""
        params: dict[str, str] = {}
        if self._directory:
            params["directory"] = self._directory

        body: dict[str, Any] = {"title": title}
        if parent_id:
            body["parentID"] = parent_id

        resp = await self._request("POST", "/session", params=params, body=body)
        payload = resp.json()
        session_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(session_id, str) or not session_id:
            raise OpencodeAPIError(f"Unexpected create_session response: {payload}")
        return session_id

    async def prompt(
        self,
        *,
        session_id: str,
        agent: str,
        text: str,
        message_id: str | None = None,
        model: dict[str, str] | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        no_reply: bool = False,
    ) -> OpencodePromptResult:
        """Send a prompt to a session, returning assistant output."""
        params: dict[str, str] = {}
        if self._directory:
            params["directory"] = self._directory

        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
            "agent": agent,
            "noReply": no_reply,
        }
        if message_id:
            body["messageID"] = message_id
        if model:
            body["model"] = model
        if tools:
            body["tools"] = tools
        if system:
            body["system"] = system

        resp = await self._request(
            "POST", f"/session/{session_id}/message", params=params, body=body
        )
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise OpencodeAPIError(
                f"Invalid JSON response from OpenCode: {resp.text[:200]}"
            ) from exc

        info = payload.get("info") if isinstance(payload, dict) else None
        parts = payload.get("parts") if isinstance(payload, dict) else None

        if not isinstance(info, dict) or not isinstance(parts, list):
            raise OpencodeAPIError(f"Unexpected prompt response: {payload}")

        msg_id = info.get("id")
        if not isinstance(msg_id, str) or not msg_id:
            raise OpencodeAPIError(f"Missing message id in response: {payload}")

        raw_output = _extract_text([p for p in parts if isinstance(p, dict)])

        if not raw_output or raw_output.strip() == "":
            import logging

            logging.warning(
                f"OpenCode returned empty output. Session: {session_id}, "
                f"Parts count: {len(parts)}, Response: {json.dumps(payload)[:500]}"
            )

        return OpencodePromptResult(
            session_id=session_id,
            message_id=msg_id,
            raw_output=raw_output,
            response_json=payload,
        )

        return OpencodePromptResult(
            session_id=session_id,
            message_id=msg_id,
            raw_output=raw_output,
            response_json=payload,
        )

    async def wait_for_idle(self, *, session_id: str, timeout_seconds: float = 300.0) -> None:
        """Wait for a session to become idle via SSE.

        This is optional because POST /session/{id}/message is typically synchronous.
        """
        deadline = _now_utc().timestamp() + timeout_seconds

        try:
            httpx_sse = _require_httpx_sse()
            async with httpx_sse.aconnect_sse(self._client, "GET", "/event") as event_source:
                async for sse in event_source.aiter_sse():
                    if _now_utc().timestamp() > deadline:
                        raise OpencodeAPIError(f"Timed out waiting for session idle: {session_id}")

                    if not sse.data:
                        continue
                    try:
                        evt = json.loads(sse.data)
                    except json.JSONDecodeError:
                        continue

                    evt_type = evt.get("type")
                    props = evt.get("properties") if isinstance(evt.get("properties"), dict) else {}

                    if evt_type == "session.idle" and props.get("sessionID") == session_id:
                        return
                    if evt_type == "session.error" and props.get("sessionID") == session_id:
                        raise OpencodeAPIError(f"Session error: {evt}")
        except self._httpx.RequestError as e:
            raise OpencodeAPIError(f"Error streaming events from OpenCode: {e}") from e

    async def get_messages(self, *, session_id: str) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if self._directory:
            params["directory"] = self._directory

        resp = await self._request("GET", f"/session/{session_id}/message", params=params)
        payload = resp.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]
        return []

    async def get_latest_assistant_text(self, *, session_id: str) -> str:
        """Fetch all messages and return latest assistant text."""
        messages = await self.get_messages(session_id=session_id)
        # Each item is expected to look like {info: {...}, parts: [...]}
        for item in reversed(messages):
            if not isinstance(item, dict):
                continue
            info = item.get("info")
            parts = item.get("parts")
            if not isinstance(info, dict) or not isinstance(parts, list):
                continue
            if info.get("role") != "assistant":
                continue
            return _extract_text([p for p in parts if isinstance(p, dict)])
        return ""
