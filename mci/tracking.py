"""Entscheidungs-Nachhalten: Empfehlung → Beschluss → Ergebnis (spec §5.5, §6.6.8).

The differentiating loop most competitive-intelligence tools skip: writing down
what was recommended, what was actually decided, and — later — what happened.
That turns the tool from an opinion generator into something with a track record:

* **Trefferquote** — how often the recommendation matched the outcome.
* **Optimismus-Bias** — the tool's systematic lean. A positive value means
  outcomes came in *worse* than expected, i.e. the analysis was too optimistic.

Nothing here is inferred by an LLM. A human records the decision and the outcome;
the module only aggregates. An unresolved decision is never counted as a hit —
open cases stay open, which is what keeps the hit rate honest.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from mci.db import Store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return f"dec_{uuid.uuid4().hex[:12]}"


# How a decision resolved. "offen" until someone records the outcome.
STATUSES = ("offen", "eingetreten", "teilweise", "nicht eingetreten", "verworfen")

# Outcome -> score used for the hit rate and the bias measure.
_SCORE = {"eingetreten": 1.0, "teilweise": 0.5, "nicht eingetreten": 0.0}


class DecisionRecord(BaseModel):
    """One recorded decision and, once known, its outcome."""

    id: str = Field(default_factory=_id)
    field_id: str = ""                 # the ActionField it came from
    decision_category: str = ""        # E1..E7
    recommendation: str = ""           # what the tool recommended
    decision: str = ""                 # what the humans actually decided
    owner: str = ""                    # who owns it
    confidence_at_decision: float = 0.0
    decided_at: datetime = Field(default_factory=_now)
    review_date: str = ""

    status: str = "offen"
    outcome_note: str = ""
    resolved_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.status in _SCORE

    @property
    def score(self) -> float | None:
        return _SCORE.get(self.status)


class TrackRecord(BaseModel):
    """Aggregate view over all recorded decisions."""

    total: int = 0
    resolved: int = 0
    open: int = 0
    hit_rate: float | None = None      # 0..1 over resolved decisions
    optimism_bias: float | None = None  # >0 => tool was too optimistic
    by_category: dict[str, int] = Field(default_factory=dict)

    @property
    def verdict(self) -> str:
        if self.optimism_bias is None:
            return "noch keine Datenbasis"
        if self.optimism_bias > 0.15:
            return "zu optimistisch — Konfidenzen nach unten korrigieren"
        if self.optimism_bias < -0.15:
            return "zu vorsichtig — Chancen werden unterschätzt"
        return "gut kalibriert"


def record_decision(
    store: Store,
    *,
    field_id: str = "",
    decision_category: str = "",
    recommendation: str = "",
    decision: str = "",
    owner: str = "",
    confidence: float = 0.0,
    review_date: str = "",
) -> DecisionRecord:
    """Write down what was decided, while the reasoning is still fresh."""
    rec = DecisionRecord(
        field_id=field_id, decision_category=decision_category,
        recommendation=recommendation, decision=decision, owner=owner,
        confidence_at_decision=confidence, review_date=review_date,
    )
    store.upsert_decision(rec)
    return rec


def resolve(store: Store, decision_id: str, *, status: str,
            note: str = "") -> DecisionRecord | None:
    """Record how a decision actually turned out."""
    if status not in STATUSES:
        raise ValueError(f"unbekannter Status '{status}'; erlaubt: {STATUSES}")
    rec = store.get_decision(decision_id)
    if rec is None:
        return None
    rec.status = status
    rec.outcome_note = note
    rec.resolved_at = _now()
    store.upsert_decision(rec)
    return rec


def add_note(store: Store, decision_id: str, note: str) -> DecisionRecord | None:
    """Append a dated comment — the running commentary on a decision."""
    rec = store.get_decision(decision_id)
    if rec is None or not note.strip():
        return rec
    rec.notes.append(f"[{_now():%Y-%m-%d}] {note.strip()}")
    store.upsert_decision(rec)
    return rec


def track_record(store: Store) -> TrackRecord:
    """Aggregate hit rate and optimism bias over all recorded decisions."""
    records = store.list_decisions()
    tr = TrackRecord(total=len(records))
    resolved = [r for r in records if r.is_resolved]
    tr.resolved = len(resolved)
    tr.open = sum(1 for r in records if r.status == "offen")
    for r in records:
        if r.decision_category:
            tr.by_category[r.decision_category] = (
                tr.by_category.get(r.decision_category, 0) + 1)
    if not resolved:
        return tr

    scores = [r.score or 0.0 for r in resolved]
    tr.hit_rate = round(sum(scores) / len(scores), 3)
    # Bias = how far stated confidence ran ahead of the realised outcome.
    # Positive => predicted more confidently than reality delivered.
    gaps = [r.confidence_at_decision - (r.score or 0.0) for r in resolved]
    tr.optimism_bias = round(sum(gaps) / len(gaps), 3)
    return tr
