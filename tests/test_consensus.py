import pytest

from debate.consensus import ConsensusCalculator
from debate.models import Finding


def _finding(
    *,
    agent: str,
    category: str | None = None,
    file_path: str | None = None,
    severity: str | None = None,
    agreed_by: list[str] | None = None,
    disputed_by: list[str] | None = None,
) -> Finding:
    return Finding(
        task_id="task",
        round_id="round",
        analysis_id="analysis",
        agent=agent,
        category=category,
        finding="test",
        file_path=file_path,
        severity=severity,
        agreed_by=agreed_by,
        disputed_by=disputed_by,
    )


@pytest.mark.asyncio
async def test_consensus_breakdown_basic_overlap() -> None:
    calc = ConsensusCalculator()
    gemini_findings = [
        _finding(agent="gemini", category="security", file_path="src/auth.py", severity="high")
    ]
    claude_findings = [
        _finding(agent="claude", category="security", file_path="src/auth.py", severity="medium")
    ]

    breakdown = await calc.calculate(
        gemini_findings=gemini_findings,
        claude_findings=claude_findings,
        gemini_recommendations=["Use parameterized queries"],
        claude_recommendations=["Use parameterized queries"],
        round_number=1,
    )

    assert breakdown.category_score == 100.0
    assert breakdown.file_path_score == 100.0
    assert breakdown.severity_score >= 0.0


def test_explicit_agreement_round_two() -> None:
    calc = ConsensusCalculator()
    gemini_findings = [
        _finding(agent="gemini", agreed_by=["claude"]),
    ]
    claude_findings = [
        _finding(agent="claude", disputed_by=["gemini"]),
    ]

    score = calc._calculate_explicit_agreements(gemini_findings, claude_findings, 2)
    assert score == 50.0
