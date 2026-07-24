"""Hybrides Scoring (spec §4, §5.3) — der wichtigste Konstruktionspunkt.

The LLM sets *no* numbers. It supplies qualitative inputs (source class,
impact category, reaction window in months); this module computes confidence
and priority deterministically so they are reproducible and explainable
(spec §5.3, Anti-Requirement §9 "keine frei vom LLM gesetzten Scores").

    priority = impact × confidence × urgency × proximity          (spec §4)
    confidence = source_class × triangulation × recency            (spec §5.3)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import SourceClass

# Gewicht je Quellenklasse (spec §3.4).
SOURCE_CLASS_WEIGHT: dict[SourceClass, float] = {
    SourceClass.A: 1.00,
    SourceClass.B: 0.75,
    SourceClass.C: 0.50,
    SourceClass.D: 0.25,
}

# Triangulation (spec §3.5): a signal counts as "confirmed" only from two
# independent sources. The factor rewards corroboration.
CONFIRMED_MIN_SOURCES = 2

# Proximity for a signal that does not touch any focus market/line. Non-zero so
# off-focus early-warning signals still rank (low) instead of scoring priority 0.
PROXIMITY_FLOOR = 0.2


def triangulation_factor(independent_sources: int) -> float:
    if independent_sources <= 0:
        return 0.0
    if independent_sources == 1:
        return 0.60
    if independent_sources == 2:
        return 0.85
    return 1.00


def recency_factor(age_days: float, half_life_days: float) -> float:
    """Exponential decay against the signal's Halbwertszeit (spec §3.6).

    Fresh -> ~1.0; at one half-life -> 0.5; long past -> approaches 0.
    """
    if half_life_days <= 0:
        return 0.0
    age_days = max(0.0, age_days)
    return 0.5 ** (age_days / half_life_days)


def compute_confidence(
    source_class: SourceClass,
    independent_sources: int,
    age_days: float,
    half_life_days: float,
) -> float:
    conf = (
        SOURCE_CLASS_WEIGHT[source_class]
        * triangulation_factor(independent_sources)
        * recency_factor(age_days, half_life_days)
    )
    return round(_clamp(conf, 0.0, 1.0), 4)


def urgency_from_window(reaction_window_months: float | None) -> int:
    """Map a reaction window (months) to an urgency step 1..5 (spec §5.3).

    Shorter window -> more urgent. The LLM estimates the window; the mapping is
    fixed here so the step is not an LLM opinion.
    """
    if reaction_window_months is None:
        return 1
    m = reaction_window_months
    if m <= 1:
        return 5
    if m <= 3:
        return 4
    if m <= 6:
        return 3
    if m <= 12:
        return 2
    return 1


def compute_proximity(
    signal_markets: list[str],
    signal_products: list[str],
    focus_markets: list[str],
    focus_lines: list[str],
) -> float:
    """Relevance to the user's focus lines/markets (spec §4, deterministic).

    Transparent overlap score. No focus set -> neutral 0.5 so a fresh install
    still surfaces signals. A focus match -> 1.0; no match -> PROXIMITY_FLOOR
    (not 0.0) so off-focus early-warning signals from adjacent markets still
    rank low rather than vanishing entirely from the cockpit.
    """
    if not focus_markets and not focus_lines:
        return 0.5

    def _overlap(items: list[str], focus: list[str]) -> float | None:
        if not focus:
            return None
        f = {x.strip().lower() for x in focus if x.strip()}
        hit = any(i.strip().lower() in f for i in items)
        return 1.0 if hit else PROXIMITY_FLOOR

    market_score = _overlap(signal_markets, focus_markets)
    line_score = _overlap(signal_products, focus_lines)
    parts = [s for s in (market_score, line_score) if s is not None]
    if not parts:
        return 0.5
    # Either axis matching is meaningful; take the max so a strong market match
    # isn't diluted by an unrelated product axis.
    return round(max(parts), 4)


@dataclass(frozen=True)
class ScoreBreakdown:
    """All four factors are individually visible (spec §4, no Blackbox)."""

    impact: int
    confidence: float
    urgency: int
    proximity: float
    priority: float

    # Sub-components of confidence, kept for the evidence drill-down.
    source_class_weight: float
    triangulation: float
    recency: float
    independent_sources: int

    def as_dict(self) -> dict:
        return {
            "impact": self.impact,
            "confidence": self.confidence,
            "urgency": self.urgency,
            "proximity": self.proximity,
            "priority": self.priority,
            "confidence_components": {
                "source_class_weight": self.source_class_weight,
                "triangulation": self.triangulation,
                "recency": self.recency,
                "independent_sources": self.independent_sources,
            },
        }


def score(
    *,
    impact: int,
    source_class: SourceClass,
    independent_sources: int,
    age_days: float,
    half_life_days: float,
    reaction_window_months: float | None,
    signal_markets: list[str],
    signal_products: list[str],
    focus_markets: list[str],
    focus_lines: list[str],
) -> ScoreBreakdown:
    impact = int(_clamp(impact, 1, 5))
    conf = compute_confidence(source_class, independent_sources, age_days, half_life_days)
    urg = urgency_from_window(reaction_window_months)
    prox = compute_proximity(signal_markets, signal_products, focus_markets, focus_lines)

    priority = impact * conf * urg * prox
    return ScoreBreakdown(
        impact=impact,
        confidence=conf,
        urgency=urg,
        proximity=prox,
        priority=round(priority, 4),
        source_class_weight=SOURCE_CLASS_WEIGHT[source_class],
        triangulation=triangulation_factor(independent_sources),
        recency=round(recency_factor(age_days, half_life_days), 4),
        independent_sources=independent_sources,
    )


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# Priority is impact(1..5) × conf(0..1) × urgency(1..5) × proximity(0..1),
# so its theoretical max is 25. Expose a 0..100 normalization for the UI.
PRIORITY_MAX = 25.0


def priority_pct(priority: float) -> int:
    if not math.isfinite(priority):
        return 0
    return int(round(_clamp(priority / PRIORITY_MAX, 0.0, 1.0) * 100))
