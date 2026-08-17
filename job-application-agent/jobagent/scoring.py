"""Scores normalized jobs against a candidate profile.

A job's searchable text (title + description + tags) is matched against:
  - each target category's keywords -> category match + category score
  - general AI-signal keywords -> ai_score
  - exclusion keywords (non-introvert-friendly / customer-facing roles)
    -> exclusion_hits; jobs at/above exclusion_threshold are marked
       'excluded' rather than ranked.

fit_score combines the best category score (scaled by that category's
weight) with the AI signal score, then applies an exclusion penalty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoreResult:
    category: str | None
    category_score: float
    ai_score: float
    fit_score: float
    exclusion_hits: list[str]
    excluded: bool


def _count_hits(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if p.lower() in text]


def score_job(job_text_title: str, job_text_description: str, job_tags: str, profile: dict[str, Any]) -> ScoreResult:
    haystack = " ".join(
        [job_text_title or "", job_text_description or "", job_tags or ""]
    ).lower()

    exclusion_keywords = profile.get("exclusion_keywords", [])
    exclusion_hits = _count_hits(haystack, exclusion_keywords)
    exclusion_threshold = profile.get("exclusion_threshold", 1)
    excluded = len(exclusion_hits) >= exclusion_threshold

    ai_keywords = profile.get("ai_signal_keywords", [])
    ai_hits = _count_hits(haystack, ai_keywords)
    ai_score = float(len(ai_hits))

    best_category = None
    best_category_score = 0.0
    for cat in profile.get("target_categories", []):
        hits = _count_hits(haystack, cat.get("keywords", []))
        weight = float(cat.get("weight", 1.0))
        raw_score = len(hits) * weight
        if raw_score > best_category_score:
            best_category_score = raw_score
            best_category = cat.get("name")

    fit_score = best_category_score * 2 + ai_score
    if excluded:
        fit_score -= 100  # sink excluded jobs to the bottom instead of hiding them

    return ScoreResult(
        category=best_category,
        category_score=best_category_score,
        ai_score=ai_score,
        fit_score=fit_score,
        exclusion_hits=exclusion_hits,
        excluded=excluded,
    )
