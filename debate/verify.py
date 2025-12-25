"""Verification script - validates implementation against the plan."""

import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import db
from .models import Verification

console = Console()


@dataclass
class VerificationResult:
    """Result from verification checks."""

    tests_ran: bool = False
    tests_passed: bool | None = None
    tests_total: int = 0
    tests_failed: int = 0
    tests_output: str = ""

    lint_ran: bool = False
    lint_passed: bool | None = None
    lint_warnings: int = 0
    lint_errors: int = 0
    lint_output: str = ""

    build_ran: bool = False
    build_passed: bool | None = None
    build_output: str = ""

    files_changed: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0

    overall_status: str = "pending"


def run_command(
    cmd: list[str], cwd: Path | None = None, timeout: int = 120
) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def detect_test_command(cwd: Path) -> list[str] | None:
    """Detect the appropriate test command for the project."""
    if (cwd / "package.json").exists():
        return ["npm", "test"]
    if (cwd / "pytest.ini").exists() or (cwd / "pyproject.toml").exists():
        return ["pytest", "-v"]
    if (cwd / "go.mod").exists():
        return ["go", "test", "./..."]
    if (cwd / "Cargo.toml").exists():
        return ["cargo", "test"]
    return None


def detect_lint_command(cwd: Path) -> list[str] | None:
    """Detect the appropriate lint command for the project."""
    if (cwd / "package.json").exists():
        return ["npm", "run", "lint"]
    if (cwd / "pyproject.toml").exists():
        return ["ruff", "check", "."]
    if (cwd / "go.mod").exists():
        return ["golangci-lint", "run"]
    return None


def detect_build_command(cwd: Path) -> list[str] | None:
    """Detect the appropriate build command for the project."""
    if (cwd / "package.json").exists():
        return ["npm", "run", "build"]
    if (cwd / "go.mod").exists():
        return ["go", "build", "./..."]
    if (cwd / "Cargo.toml").exists():
        return ["cargo", "build"]
    return None


def get_git_changes(cwd: Path) -> tuple[list[str], int, int]:
    """Get git diff statistics."""
    # Get changed files
    code, stdout, _ = run_command(["git", "diff", "--name-only", "HEAD~1"], cwd)
    files = stdout.strip().split("\n") if code == 0 and stdout.strip() else []

    # Get line counts
    code, stdout, _ = run_command(["git", "diff", "--shortstat", "HEAD~1"], cwd)
    lines_added = 0
    lines_removed = 0
    if code == 0 and stdout:
        import re

        add_match = re.search(r"(\d+) insertion", stdout)
        del_match = re.search(r"(\d+) deletion", stdout)
        if add_match:
            lines_added = int(add_match.group(1))
        if del_match:
            lines_removed = int(del_match.group(1))

    return files, lines_added, lines_removed


def run_tests(cwd: Path) -> tuple[bool, int, int, str]:
    """Run tests and return (passed, total, failed, output)."""
    cmd = detect_test_command(cwd)
    if not cmd:
        return False, 0, 0, "No test command detected"

    console.print(f"[blue]Running: {' '.join(cmd)}[/blue]")
    code, stdout, stderr = run_command(cmd, cwd)

    output = stdout + stderr
    passed = code == 0

    # Try to parse test counts (varies by framework)
    total = 0
    failed = 0
    import re

    # pytest style
    match = re.search(r"(\d+) passed", output)
    if match:
        total += int(match.group(1))
    match = re.search(r"(\d+) failed", output)
    if match:
        failed = int(match.group(1))
        total += failed

    # jest/mocha style
    match = re.search(r"Tests:\s+(\d+) passed", output)
    if match:
        total += int(match.group(1))
    match = re.search(r"(\d+) failed", output)
    if match:
        failed = int(match.group(1))

    return passed, total, failed, output


def run_lint(cwd: Path) -> tuple[bool, int, int, str]:
    """Run linter and return (passed, warnings, errors, output)."""
    cmd = detect_lint_command(cwd)
    if not cmd:
        return False, 0, 0, "No lint command detected"

    console.print(f"[blue]Running: {' '.join(cmd)}[/blue]")
    code, stdout, stderr = run_command(cmd, cwd)

    output = stdout + stderr
    passed = code == 0

    # Count warnings/errors (rough estimate)
    warnings = output.lower().count("warning")
    errors = output.lower().count("error")

    return passed, warnings, errors, output


def run_build(cwd: Path) -> tuple[bool, str]:
    """Run build and return (passed, output)."""
    cmd = detect_build_command(cwd)
    if not cmd:
        return False, "No build command detected"

    console.print(f"[blue]Running: {' '.join(cmd)}[/blue]")
    code, stdout, stderr = run_command(cmd, cwd, timeout=300)

    output = stdout + stderr
    passed = code == 0

    return passed, output


async def verify_task(task_slug: str, cwd: Path | None = None) -> VerificationResult:
    """Run verification checks for a task."""
    console.print(f"[bold]Verifying task: {task_slug}[/bold]")

    if cwd is None:
        cwd = Path.cwd()

    result = VerificationResult()

    # Get git changes
    console.print("\n[bold]Checking git changes...[/bold]")
    result.files_changed, result.lines_added, result.lines_removed = get_git_changes(cwd)
    console.print(f"  Files changed: {len(result.files_changed)}")
    console.print(f"  Lines: +{result.lines_added} / -{result.lines_removed}")

    # Run tests
    console.print("\n[bold]Running tests...[/bold]")
    result.tests_ran = True
    result.tests_passed, result.tests_total, result.tests_failed, result.tests_output = run_tests(
        cwd
    )
    if result.tests_passed:
        console.print(f"[green]Tests passed: {result.tests_total} total[/green]")
    else:
        console.print(f"[red]Tests failed: {result.tests_failed}/{result.tests_total}[/red]")

    # Run lint
    console.print("\n[bold]Running linter...[/bold]")
    result.lint_ran = True
    result.lint_passed, result.lint_warnings, result.lint_errors, result.lint_output = run_lint(cwd)
    if result.lint_passed:
        console.print(f"[green]Lint passed (warnings: {result.lint_warnings})[/green]")
    else:
        console.print(f"[red]Lint failed: {result.lint_errors} errors[/red]")

    # Run build
    console.print("\n[bold]Running build...[/bold]")
    result.build_ran = True
    result.build_passed, result.build_output = run_build(cwd)
    if result.build_passed:
        console.print("[green]Build passed[/green]")
    else:
        console.print("[red]Build failed[/red]")

    # Determine overall status
    if result.tests_passed and result.lint_passed and result.build_passed:
        result.overall_status = "passed"
    elif result.tests_passed is False or result.build_passed is False:
        result.overall_status = "failed"
    else:
        result.overall_status = "partial"

    # Store in database
    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if task:
            verification = Verification(
                task_id=task.id,
                tests_ran=result.tests_ran,
                tests_passed=result.tests_passed,
                tests_total=result.tests_total,
                tests_failed=result.tests_failed,
                tests_output=result.tests_output[:10000],  # Limit output size
                lint_ran=result.lint_ran,
                lint_passed=result.lint_passed,
                lint_warnings=result.lint_warnings,
                lint_errors=result.lint_errors,
                lint_output=result.lint_output[:10000],
                build_ran=result.build_ran,
                build_passed=result.build_passed,
                build_output=result.build_output[:10000],
                files_changed=result.files_changed,
                lines_added=result.lines_added,
                lines_removed=result.lines_removed,
                overall_status=result.overall_status,
            )
            session.add(verification)
            console.print("\n[green]Verification stored in database[/green]")

    # Print summary
    console.print("\n")
    table = Table(title="Verification Summary")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    table.add_row(
        "Tests",
        "[green]PASS[/green]" if result.tests_passed else "[red]FAIL[/red]",
        f"{result.tests_total} total, {result.tests_failed} failed",
    )
    table.add_row(
        "Lint",
        "[green]PASS[/green]" if result.lint_passed else "[red]FAIL[/red]",
        f"{result.lint_warnings} warnings, {result.lint_errors} errors",
    )
    table.add_row(
        "Build",
        "[green]PASS[/green]" if result.build_passed else "[red]FAIL[/red]",
        "",
    )
    table.add_row(
        "Overall",
        "[green]PASS[/green]" if result.overall_status == "passed" else "[red]FAIL[/red]",
        result.overall_status,
    )

    console.print(table)

    return result


@click.command()
@click.argument("task_slug")
@click.option("--cwd", "-C", type=click.Path(exists=True, path_type=Path), help="Working directory")
def main(task_slug: str, cwd: Path | None) -> None:
    """Verify implementation for a task.

    TASK_SLUG: The task slug (e.g., auth-refactor)
    """
    result = asyncio.run(verify_task(task_slug, cwd))
    sys.exit(0 if result.overall_status == "passed" else 1)


if __name__ == "__main__":
    main()
