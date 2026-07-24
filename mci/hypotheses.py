"""Hypotheses with falsification triggers + automatic check (spec §3.8, §5.5).

Each hypothesis carries a `falsification_trigger`: "how would I know it's wrong?"
`auto_check` scans the signal base for a signal that satisfies that trigger and,
if found, marks the hypothesis **refuted** — attaching the contradicting signal.

The KI may refute (a factual check) but may NEVER set a hypothesis to
`confirmed` (spec §5.5) — that stays a human action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import Store
from .models import Hypothesis, Signal

_STOP = {
    "wenn", "dass", "eine", "einer", "einen", "wird", "werden", "nicht", "kein",
    "keine", "oder", "und", "der", "die", "das", "den", "dem", "mit", "für",
    "auf", "sich", "innerhalb", "über", "unter", "erkennen", "woran",
}


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[a-zäöüß]{5,}", text.lower())
    return {w for w in words if w not in _STOP}


def create(
    store: Store,
    *,
    statement: str,
    falsification_trigger: str,
    competitor_id: str | None = None,
    supporting_signal_ids: list[str] | None = None,
    review_horizon_days: int = 90,
) -> Hypothesis:
    h = Hypothesis(
        competitor_id=competitor_id,
        statement=statement,
        supporting_signal_ids=supporting_signal_ids or [],
        falsification_trigger=falsification_trigger,
        review_date=datetime.now(timezone.utc) + timedelta(days=review_horizon_days),
        status="open",
    )
    store.upsert_hypothesis(h)
    return h


def _signal_triggers(signal: Signal, trigger_words: set[str]) -> bool:
    if not trigger_words:
        return False
    hay = _content_words(f"{signal.headline} {signal.fact}")
    overlap = trigger_words & hay
    # Conservative: require a strong majority of trigger content words present.
    return len(overlap) >= max(2, int(round(0.6 * len(trigger_words))))


@dataclass
class HypothesisCheck:
    hypothesis_id: str
    refuted: bool
    by_signal_id: str | None
    review_overdue: bool


def auto_check(store: Store) -> list[HypothesisCheck]:
    """Scan open hypotheses against the signal base. Refute on trigger match."""
    now = datetime.now(timezone.utc)
    signals = store.list_signals()
    results: list[HypothesisCheck] = []

    for h in store.list_hypotheses(status="open"):
        trigger_words = _content_words(h.falsification_trigger)
        refuting = next((s for s in signals if _signal_triggers(s, trigger_words)), None)
        overdue = bool(h.review_date and h.review_date < now)

        if refuting is not None:
            h.status = "refuted"
            if refuting.id not in h.contradicting_signal_ids:
                h.contradicting_signal_ids.append(refuting.id)
            store.upsert_hypothesis(h)

        results.append(
            HypothesisCheck(
                hypothesis_id=h.id,
                refuted=refuting is not None,
                by_signal_id=refuting.id if refuting else None,
                review_overdue=overdue,
            )
        )
    return results
