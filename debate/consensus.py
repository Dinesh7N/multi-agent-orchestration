"""
Multi-factor consensus calculation for debate rounds.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Finding, Round


@dataclass
class ConsensusBreakdown:
    """Detailed breakdown of agreement scores."""

    category_score: float
    file_path_score: float
    severity_score: float
    semantic_score: float
    explicit_score: float

    @property
    def weighted_total(self) -> float:
        return (
            0.15 * self.category_score
            + 0.25 * self.file_path_score
            + 0.15 * self.severity_score
            + 0.25 * self.semantic_score
            + 0.20 * self.explicit_score
        )

    def to_dict(self) -> dict:
        return {
            "category": round(self.category_score, 2),
            "file_path": round(self.file_path_score, 2),
            "severity": round(self.severity_score, 2),
            "semantic": round(self.semantic_score, 2),
            "explicit": round(self.explicit_score, 2),
            "weighted_total": round(self.weighted_total, 2),
        }


class ConsensusCalculator:
    """Calculates multi-factor consensus between agents."""

    def __init__(self, embedding_client: object | None = None) -> None:
        self._embedding_client = embedding_client

    async def calculate(
        self,
        gemini_findings: Sequence[Finding],
        claude_findings: Sequence[Finding],
        gemini_recommendations: list[str],
        claude_recommendations: list[str],
        round_number: int,
    ) -> ConsensusBreakdown:
        category_score = self._calculate_category_overlap(gemini_findings, claude_findings)
        file_path_score = self._calculate_file_overlap(gemini_findings, claude_findings)
        severity_score = self._calculate_severity_agreement(gemini_findings, claude_findings)
        semantic_score = await self._calculate_semantic_similarity(
            gemini_recommendations, claude_recommendations
        )
        explicit_score = self._calculate_explicit_agreements(
            gemini_findings, claude_findings, round_number
        )

        return ConsensusBreakdown(
            category_score=category_score,
            file_path_score=file_path_score,
            severity_score=severity_score,
            semantic_score=semantic_score,
            explicit_score=explicit_score,
        )

    def _calculate_category_overlap(
        self, gemini: Sequence[Finding], claude: Sequence[Finding]
    ) -> float:
        gemini_cats = {f.category for f in gemini if f.category}
        claude_cats = {f.category for f in claude if f.category}

        if not gemini_cats and not claude_cats:
            return 100.0

        intersection = gemini_cats & claude_cats
        union = gemini_cats | claude_cats
        return (len(intersection) / len(union)) * 100 if union else 100.0

    def _calculate_file_overlap(
        self, gemini: Sequence[Finding], claude: Sequence[Finding]
    ) -> float:
        gemini_files = {f.file_path for f in gemini if f.file_path}
        claude_files = {f.file_path for f in claude if f.file_path}

        if not gemini_files and not claude_files:
            return 100.0
        if not gemini_files or not claude_files:
            return 0.0

        exact_matches = gemini_files & claude_files
        total_unique = len(gemini_files | claude_files)
        exact_score = len(exact_matches) / total_unique if total_unique else 0.0

        remaining_gemini = gemini_files - exact_matches
        remaining_claude = claude_files - exact_matches
        remaining_dirs_g = {self._get_directory(f) for f in remaining_gemini}
        remaining_dirs_c = {self._get_directory(f) for f in remaining_claude}
        dir_overlap = len(remaining_dirs_g & remaining_dirs_c)
        dir_score = (dir_overlap / total_unique) * 0.5 if total_unique else 0.0

        return (exact_score + dir_score) * 100

    def _get_directory(self, file_path: str) -> str:
        parts = file_path.rsplit("/", 1)
        return parts[0] if len(parts) > 1 else ""

    def _calculate_severity_agreement(
        self, gemini: Sequence[Finding], claude: Sequence[Finding]
    ) -> float:
        severity_weights = {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1,
            "info": 0,
        }

        def get_severity_distribution(findings: Sequence[Finding]) -> dict[str, int]:
            dist = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
            for f in findings:
                if f.severity and f.severity in dist:
                    dist[f.severity] += 1
            return dist

        gemini_dist = get_severity_distribution(gemini)
        claude_dist = get_severity_distribution(claude)

        total_weighted_diff = 0
        total_weighted_sum = 0

        for severity, weight in severity_weights.items():
            g_count = gemini_dist[severity]
            c_count = claude_dist[severity]
            weighted_diff = abs(g_count - c_count) * (weight + 1)
            weighted_sum = (g_count + c_count) * (weight + 1)
            total_weighted_diff += weighted_diff
            total_weighted_sum += weighted_sum

        if total_weighted_sum == 0:
            return 100.0

        similarity = 1 - (total_weighted_diff / total_weighted_sum)
        return similarity * 100

    async def _calculate_semantic_similarity(
        self, gemini_recs: list[str], claude_recs: list[str]
    ) -> float:
        if not gemini_recs and not claude_recs:
            return 100.0
        if not gemini_recs or not claude_recs:
            return 0.0

        if self._embedding_client:
            embeddings = await self._get_embeddings(
                self._embedding_client, gemini_recs, claude_recs
            )
            if embeddings:
                return embeddings

        local_similarity = self._local_semantic_similarity(gemini_recs, claude_recs)
        if local_similarity is not None:
            return local_similarity

        return self._fallback_text_similarity(gemini_recs, claude_recs)

    async def _get_embeddings(
        self, embedding_client: object, gemini_recs: list[str], claude_recs: list[str]
    ) -> float | None:
        try:
            gemini_embeddings = await embedding_client.create_embeddings(gemini_recs)
            claude_embeddings = await embedding_client.create_embeddings(claude_recs)
            gemini_avg = _mean_vector(gemini_embeddings)
            claude_avg = _mean_vector(claude_embeddings)
            return _cosine_similarity(gemini_avg, claude_avg) * 100
        except Exception:
            return None

    def _local_semantic_similarity(
        self, gemini_recs: list[str], claude_recs: list[str]
    ) -> float | None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return None

        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            gemini_vecs = model.encode(gemini_recs)
            claude_vecs = model.encode(claude_recs)
            gemini_avg = _mean_vector(gemini_vecs)
            claude_avg = _mean_vector(claude_vecs)
            return _cosine_similarity(gemini_avg, claude_avg) * 100
        except Exception:
            return None

    def _fallback_text_similarity(self, gemini_recs: list[str], claude_recs: list[str]) -> float:
        def tokenize(texts: list[str]) -> set[str]:
            words: set[str] = set()
            for text in texts:
                words.update(text.lower().split())
            return words

        gemini_words = tokenize(gemini_recs)
        claude_words = tokenize(claude_recs)
        if not gemini_words and not claude_words:
            return 100.0
        intersection = gemini_words & claude_words
        union = gemini_words | claude_words
        return (len(intersection) / len(union)) * 100 if union else 0.0

    def _calculate_explicit_agreements(
        self, gemini: Sequence[Finding], claude: Sequence[Finding], round_number: int
    ) -> float:
        if round_number < 2:
            return 50.0

        total_cross_refs = 0
        agreements = 0

        for finding in gemini:
            if finding.agreed_by and "claude" in finding.agreed_by:
                agreements += 1
                total_cross_refs += 1
            if finding.disputed_by and "claude" in finding.disputed_by:
                total_cross_refs += 1

        for finding in claude:
            if finding.agreed_by and "gemini" in finding.agreed_by:
                agreements += 1
                total_cross_refs += 1
            if finding.disputed_by and "gemini" in finding.disputed_by:
                total_cross_refs += 1

        if total_cross_refs == 0:
            return 50.0

        return (agreements / total_cross_refs) * 100


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        return []
    length = len(vectors[0])
    totals = [0.0] * length
    count = 0
    for vec in vectors:
        if len(vec) != length:
            continue
        for idx, val in enumerate(vec):
            totals[idx] += float(val)
        count += 1
    if count == 0:
        return []
    return [val / count for val in totals]


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = sqrt(sum(a * a for a in vec_a))
    norm_b = sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def calculate_round_consensus(
    session: AsyncSession,
    round_obj: Round,
    embedding_client: object | None = None,
) -> tuple[float, ConsensusBreakdown]:
    from .db import get_analyses_for_round, get_findings_for_round

    findings = await get_findings_for_round(session, round_obj.id)
    analyses = await get_analyses_for_round(session, round_obj.id)

    gemini_findings = [f for f in findings if f.agent == "gemini"]
    claude_findings = [f for f in findings if f.agent == "claude"]

    gemini_analysis = next((a for a in analyses if a.agent == "gemini"), None)
    claude_analysis = next((a for a in analyses if a.agent == "claude"), None)

    gemini_recs = gemini_analysis.recommendations if gemini_analysis else []
    claude_recs = claude_analysis.recommendations if claude_analysis else []

    calculator = ConsensusCalculator(embedding_client=embedding_client)
    breakdown = await calculator.calculate(
        gemini_findings=gemini_findings,
        claude_findings=claude_findings,
        gemini_recommendations=gemini_recs or [],
        claude_recommendations=claude_recs or [],
        round_number=round_obj.round_number,
    )

    round_obj.consensus_breakdown = breakdown.to_dict()
    round_obj.agreement_rate = breakdown.weighted_total

    return breakdown.weighted_total, breakdown
