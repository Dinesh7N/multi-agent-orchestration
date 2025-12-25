"""
Consensus Analysis Example

Demonstrates how to analyze consensus between agents and interpret agreement levels.

Usage:
    python examples/consensus_analysis.py
"""

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from debate.consensus import ConsensusCalculator
from debate.models import Finding

console = Console()


def create_finding(
    agent: str,
    category: str | None = None,
    file_path: str | None = None,
    severity: str | None = None,
    finding: str = "Sample finding",
) -> Finding:
    """Helper to create a Finding object."""
    return Finding(
        task_id="example-task",
        round_id="round-1",
        analysis_id=f"analysis-{agent}",
        agent=agent,
        category=category,
        finding=finding,
        file_path=file_path,
        severity=severity,
    )


async def example_high_consensus():
    """Example: High consensus between agents."""
    console.print("\n[bold]Example 1: High Consensus[/bold]")

    # Both agents agree on most aspects
    gemini_findings = [
        create_finding(
            "gemini",
            category="security",
            file_path="src/auth.py",
            severity="high",
            finding="SQL injection vulnerability in login function",
        ),
        create_finding(
            "gemini",
            category="security",
            file_path="src/api.py",
            severity="medium",
            finding="Missing input validation",
        ),
    ]

    claude_findings = [
        create_finding(
            "claude",
            category="security",
            file_path="src/auth.py",
            severity="high",
            finding="Potential SQL injection in authentication",
        ),
        create_finding(
            "claude",
            category="security",
            file_path="src/api.py",
            severity="medium",
            finding="Input validation needed",
        ),
    ]

    recommendations_gemini = [
        "Use parameterized queries",
        "Add input validation middleware",
    ]

    recommendations_claude = [
        "Implement parameterized queries",
        "Add request validation",
    ]

    calc = ConsensusCalculator()
    breakdown = await calc.calculate(
        gemini_findings=gemini_findings,
        claude_findings=claude_findings,
        gemini_recommendations=recommendations_gemini,
        claude_recommendations=recommendations_claude,
        round_number=1,
    )

    display_consensus_results(breakdown)


async def example_low_consensus():
    """Example: Low consensus - agents disagree."""
    console.print("\n[bold]Example 2: Low Consensus[/bold]")

    # Agents find different issues
    gemini_findings = [
        create_finding(
            "gemini",
            category="security",
            file_path="src/auth.py",
            severity="high",
            finding="Authentication bypass vulnerability",
        ),
    ]

    claude_findings = [
        create_finding(
            "claude",
            category="performance",
            file_path="src/database.py",
            severity="low",
            finding="Inefficient query in user lookup",
        ),
    ]

    recommendations_gemini = ["Fix authentication logic", "Add session validation"]

    recommendations_claude = ["Optimize database queries", "Add query caching"]

    calc = ConsensusCalculator()
    breakdown = await calc.calculate(
        gemini_findings=gemini_findings,
        claude_findings=claude_findings,
        gemini_recommendations=recommendations_gemini,
        claude_recommendations=recommendations_claude,
        round_number=1,
    )

    display_consensus_results(breakdown)


async def example_partial_consensus():
    """Example: Partial consensus - mixed agreement."""
    console.print("\n[bold]Example 3: Partial Consensus[/bold]")

    # Agents agree on category but differ on severity
    gemini_findings = [
        create_finding(
            "gemini",
            category="security",
            file_path="src/auth.py",
            severity="critical",
            finding="Password stored in plain text",
        ),
        create_finding(
            "gemini",
            category="code-quality",
            file_path="src/utils.py",
            severity="low",
            finding="Unused imports",
        ),
    ]

    claude_findings = [
        create_finding(
            "claude",
            category="security",
            file_path="src/auth.py",
            severity="high",  # Different severity
            finding="Passwords not properly hashed",
        ),
    ]

    recommendations_gemini = [
        "Implement bcrypt password hashing",
        "Clean up unused code",
    ]

    recommendations_claude = ["Use bcrypt for password storage"]

    calc = ConsensusCalculator()
    breakdown = await calc.calculate(
        gemini_findings=gemini_findings,
        claude_findings=claude_findings,
        gemini_recommendations=recommendations_gemini,
        claude_recommendations=recommendations_claude,
        round_number=1,
    )

    display_consensus_results(breakdown)


def display_consensus_results(breakdown):
    """Display consensus calculation results."""
    table = Table(title="Consensus Breakdown")

    table.add_column("Metric", style="cyan")
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Weight", style="blue", justify="right")

    table.add_row("Category Agreement", f"{breakdown.category_score:.1f}%", "40%")
    table.add_row("File Path Agreement", f"{breakdown.file_path_score:.1f}%", "30%")
    table.add_row("Severity Agreement", f"{breakdown.severity_score:.1f}%", "10%")
    table.add_row(
        "Recommendation Similarity", f"{breakdown.recommendation_score:.1f}%", "20%"
    )
    table.add_row("", "", "", style="dim")
    table.add_row(
        "[bold]Overall Consensus[/bold]",
        f"[bold]{breakdown.overall_score:.1f}%[/bold]",
        "",
    )

    console.print(table)

    # Interpretation
    if breakdown.overall_score >= 80:
        console.print("\n[bold green]✓ Strong consensus reached[/bold green]")
        console.print("Agents are in substantial agreement. Proceed with implementation.")
    elif breakdown.overall_score >= 60:
        console.print("\n[bold yellow]⚠ Moderate consensus[/bold yellow]")
        console.print(
            "Some agreement, but consider another debate round to refine approach."
        )
    else:
        console.print("\n[bold red]✗ Low consensus[/bold red]")
        console.print(
            "Significant disagreement. Additional rounds needed or human intervention."
        )


async def main():
    """Run all consensus examples."""
    console.print(
        Panel.fit(
            "[bold]Consensus Analysis Examples[/bold]\n"
            "Demonstrates how agents reach consensus through structured debate",
            border_style="blue",
        )
    )

    try:
        await example_high_consensus()
        await example_low_consensus()
        await example_partial_consensus()

        console.print(
            "\n[bold green]Examples completed![/bold green]\n"
            "\nKey Takeaways:"
            "\n• Category and file path agreement are most heavily weighted"
            "\n• Consensus ≥ 80% indicates strong agreement"
            "\n• Low consensus triggers additional debate rounds"
            "\n• System adapts based on agent agreement patterns"
        )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


if __name__ == "__main__":
    asyncio.run(main())
