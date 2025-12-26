"""
Automated task complexity classification and fast-track routing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Conversation, Task


class Complexity(str, Enum):
    TRIVIAL = "trivial"
    STANDARD = "standard"
    COMPLEX = "complex"


@dataclass
class TriageResult:
    """Result of automated triage classification."""

    complexity: Complexity
    confidence: float
    reasons: list[str]
    recommended_action: str
    requires_confirmation: bool


class TaskTriager:
    """Classifies task complexity based on heuristics."""

    TRIVIAL_KEYWORDS = {
        "typo",
        "typos",
        "spelling",
        "rename",
        "comment",
        "documentation",
        "readme",
        "docs",
        "todo",
        "remove unused",
        "delete unused",
        "cleanup",
        "update version",
        "bump version",
    }

    COMPLEX_KEYWORDS = {
        "architecture",
        "refactor",
        "security",
        "authentication",
        "authorization",
        "database schema",
        "migration",
        "performance",
        "scalability",
        "api redesign",
        "breaking change",
        "major version",
    }

    SINGLE_FILE_PATTERNS = [
        r"in (\w+\.\w+)",
        r"file (\w+\.\w+)",
        r"^fix (\w+)",
    ]

    MULTI_FILE_PATTERNS = [
        r"across (?:all|the|multiple)",
        r"throughout",
        r"everywhere",
        r"all (\w+) files",
    ]

    def __init__(self, history_weight: float = 0.3) -> None:
        self._history_weight = history_weight

    async def classify(
        self,
        session: AsyncSession,
        task: Task,
        conversations: list[Conversation],
    ) -> TriageResult:
        full_text = self._extract_full_text(task, conversations)

        keyword_score = self._keyword_analysis(full_text)
        scope_score = self._scope_analysis(full_text)
        history_score = await self._historical_analysis(session, full_text)

        final_score = (
            0.4 * keyword_score
            + 0.3 * scope_score
            + self._history_weight * history_score
            + (0.3 - self._history_weight) * 0.5
        )

        complexity, reasons = self._score_to_complexity(final_score, keyword_score, scope_score)

        confidence = self._calculate_confidence(keyword_score, scope_score, history_score)

        recommended_action = self._get_recommended_action(complexity)
        requires_confirmation = confidence < 0.7 or (
            complexity == Complexity.TRIVIAL and "security" in full_text.lower()
        )

        return TriageResult(
            complexity=complexity,
            confidence=confidence,
            reasons=reasons,
            recommended_action=recommended_action,
            requires_confirmation=requires_confirmation,
        )

    def _extract_full_text(self, task: Task, conversations: list[Conversation]) -> str:
        parts = [task.title]
        for conv in conversations:
            if conv.role == "human":
                parts.append(conv.content)
        return " ".join(parts).lower()

    def _keyword_analysis(self, text: str) -> float:
        trivial_count = sum(1 for kw in self.TRIVIAL_KEYWORDS if kw in text)
        complex_count = sum(1 for kw in self.COMPLEX_KEYWORDS if kw in text)

        if trivial_count > 0 and complex_count == 0:
            return 0.1
        if complex_count > 0 and trivial_count == 0:
            return 0.9
        if complex_count > trivial_count:
            return 0.7
        if trivial_count > complex_count:
            return 0.3
        return 0.5

    def _scope_analysis(self, text: str) -> float:
        single_matches = sum(1 for pattern in self.SINGLE_FILE_PATTERNS if re.search(pattern, text))
        multi_matches = sum(1 for pattern in self.MULTI_FILE_PATTERNS if re.search(pattern, text))

        if multi_matches > 0:
            return 0.9
        if single_matches > 0:
            return 0.2
        return 0.5

    async def _historical_analysis(self, session: AsyncSession, text: str) -> float:
        del session
        del text
        return 0.5

    def _score_to_complexity(
        self, final_score: float, keyword_score: float, scope_score: float
    ) -> tuple[Complexity, list[str]]:
        reasons: list[str] = []
        if keyword_score < 0.3:
            reasons.append("trivial_keywords")
        if keyword_score > 0.7:
            reasons.append("complex_keywords")
        if scope_score < 0.3:
            reasons.append("single_file_scope")
        if scope_score > 0.7:
            reasons.append("multi_file_scope")

        if final_score <= 0.3:
            return Complexity.TRIVIAL, reasons
        if final_score >= 0.7:
            return Complexity.COMPLEX, reasons
        return Complexity.STANDARD, reasons

    def _calculate_confidence(
        self, keyword_score: float, scope_score: float, history_score: float
    ) -> float:
        variance = max(keyword_score, scope_score, history_score) - min(
            keyword_score, scope_score, history_score
        )
        return max(0.0, min(1.0, 1 - variance))

    def _get_recommended_action(self, complexity: Complexity) -> str:
        if complexity == Complexity.TRIVIAL:
            return "fast_track"
        if complexity == Complexity.COMPLEX:
            return "extended_debate"
        return "debate"
