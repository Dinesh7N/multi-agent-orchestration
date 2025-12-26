"""
Basic Task Example

Demonstrates how to programmatically create and execute a simple debate task.

Usage:
    python examples/basic_task.py
"""

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from debate.db import get_async_session
from debate.models import Task
from debate.orchestrate import generate_slug

console = Console()


async def create_task(request: str) -> Task:
    """Create a new debate task."""
    console.print("\n[bold blue]Creating new task...[/bold blue]")

    title = request[:100]
    slug = generate_slug(title)

    task = Task(
        slug=slug,
        title=title,
        request=request,
        status="created",
        complexity="standard",
    )

    async with get_async_session() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)

    console.print(f"[green]✓ Created task: {task.slug}[/green]")
    return task


async def get_task_status(task_slug: str) -> Task | None:
    """Retrieve task status from database."""
    async with get_async_session() as session:
        result = await session.execute(
            "SELECT * FROM tasks WHERE slug = :slug", {"slug": task_slug}
        )
        row = result.fetchone()

        if not row:
            return None

        # Convert row to Task object (simplified)
        return row


async def display_task_info(task: Task) -> None:
    """Display task information in a formatted table."""
    table = Table(title="Task Information")

    table.add_column("Property", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Slug", task.slug)
    table.add_row("Title", task.title)
    table.add_row("Status", task.status)
    table.add_row("Complexity", task.complexity or "N/A")
    table.add_row("Created", str(task.created_at))

    console.print("\n")
    console.print(table)


async def main():
    """Main execution function."""
    console.print(
        Panel.fit(
            "[bold]Basic Task Example[/bold]\nDemonstrates creating and managing debate tasks",
            border_style="blue",
        )
    )

    # Example 1: Create a new task
    request = "Add user authentication with JWT tokens to the API"

    try:
        task = await create_task(request)
        await display_task_info(task)

        console.print("\n[bold green]Task created successfully![/bold green]")
        console.print("\nNext steps:")
        console.print("1. Start workers: [cyan]uv run claude-worker[/cyan]")
        console.print(f"2. View status: [cyan]uv run debate status {task.slug}[/cyan]")
        console.print("3. Monitor progress in the database")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("\nMake sure:")
        console.print("• Database is running (docker ps)")
        console.print("• Migrations are applied (alembic upgrade head)")
        console.print("• Configuration is correct (.env file)")


if __name__ == "__main__":
    asyncio.run(main())
