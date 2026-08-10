"""Quellen-Reliabilität — welchen Quellen ist zu trauen (spec §3.4, §5.6).

The source class (A amtlich … D Gerücht) is the prior. This module adds the
*earned* part: how a publisher has actually performed in this store — how often
its signals got independently confirmed, and how often they were refuted.

That matters for a tool built on Evidenzzwang: a class-B trade journal that has
been confirmed nine times out of ten deserves more weight than an untested one,
and a source whose claims keep getting refuted should be visible as such.

Deterministic and explainable — a ratio over stored outcomes, never a model
opinion. Publishers with too little history are reported as "unbewertet" instead
of being given a flattering default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mci.db import Store
from mci.models import SignalStatus

MIN_HISTORY = 3  # below this, a publisher stays explicitly unrated


@dataclass
class SourceScore:
    publisher: str
    source_class: str = ""
    n_signals: int = 0
    confirmed: int = 0
    refuted: int = 0
    score: float | None = None   # 0..1, None while unrated
    signal_ids: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score is None:
            return "unbewertet"
        if self.score >= 0.7:
            return "verlässlich"
        if self.score >= 0.4:
            return "gemischt"
        return "fragwürdig"

    @property
    def icon(self) -> str:
        return {"verlässlich": "🟢", "gemischt": "🟡",
                "fragwürdig": "🔴", "unbewertet": "⚪"}[self.label]


# Class prior — what we assume before a publisher has a track record.
_CLASS_PRIOR = {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.25}


def score_sources(store: Store) -> list[SourceScore]:
    """Rate every publisher by its confirmation / refutation record."""
    scores: dict[str, SourceScore] = {}
    for s in store.list_signals():
        for eid in s.evidence_ids:
            ev = store.get_evidence(eid)
            if not ev:
                continue
            src = store.get_source(ev.source_id)
            if not src:
                continue
            key = src.publisher or src.url
            entry = scores.setdefault(
                key, SourceScore(publisher=key, source_class=src.source_class.value))
            entry.n_signals += 1
            entry.signal_ids.append(s.id)
            if s.status == SignalStatus.confirmed:
                entry.confirmed += 1
            elif s.status == SignalStatus.refuted:
                entry.refuted += 1

    for entry in scores.values():
        if entry.n_signals < MIN_HISTORY:
            entry.score = None  # honest: not enough history to judge
            continue
        prior = _CLASS_PRIOR.get(entry.source_class, 0.5)
        # Confirmations pull up, refutations pull down; the class prior anchors
        # a publisher whose signals are mostly still unconfirmed.
        earned = (entry.confirmed - entry.refuted) / entry.n_signals
        entry.score = round(max(0.0, min(1.0, 0.5 * prior + 0.5 * (0.5 + earned / 2))), 3)

    return sorted(scores.values(),
                  key=lambda e: (e.score if e.score is not None else -1,
                                 e.n_signals), reverse=True)
