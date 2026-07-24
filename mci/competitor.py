"""Wettbewerberakte — lebendes Dokument (spec §4).

Assembles a living competitor file from stored data: Stammdaten, financial &
launch timelines, portfolio map, strategy hypotheses (with confidence), and open
questions (aggregated known_unknowns). It is *derived*, never hand-maintained,
so it stays current as signals arrive.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .db import Store
from .models import Competitor, Hypothesis, Product, Signal, SignalType


def signal_mentions(signal: Signal, competitor: Competitor) -> bool:
    """Match a signal to a competitor by explicit entity link or name/alias."""
    if competitor.id in signal.entities.competitors or competitor.name in signal.entities.competitors:
        return True
    names = [competitor.name, *competitor.aliases]
    hay = f"{signal.headline} {signal.fact}".lower()
    for n in names:
        n = n.strip()
        if n and re.search(rf"\b{re.escape(n.lower())}\b", hay):
            return True
    return False


class CompetitorDossier(BaseModel):
    competitor: Competitor
    portfolio: list[Product] = Field(default_factory=list)
    financial_timeline: list[Signal] = Field(default_factory=list)
    launch_timeline: list[Signal] = Field(default_factory=list)
    other_signals: list[Signal] = Field(default_factory=list)
    strategy_hypotheses: list[Hypothesis] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


def build(store: Store, competitor_id: str) -> CompetitorDossier | None:
    competitor = next(
        (c for c in store.list_competitors() if c.id == competitor_id), None
    )
    if competitor is None:
        return None

    signals = [s for s in store.list_signals() if signal_mentions(s, competitor)]
    signals.sort(key=lambda s: s.first_seen)

    financial = [s for s in signals if s.type == SignalType.financial]
    launches = [s for s in signals if s.type == SignalType.launch]
    others = [s for s in signals if s.type not in {SignalType.financial, SignalType.launch}]

    portfolio = [
        p for p in store.list_products() if p.competitor_id == competitor_id
    ]
    hyps = [
        h for h in store.list_hypotheses() if h.competitor_id == competitor_id
    ]

    open_q: list[str] = []
    for s in signals:
        open_q.extend(s.known_unknowns)
    seen: set[str] = set()
    open_q = [q for q in open_q if not (q in seen or seen.add(q))]

    return CompetitorDossier(
        competitor=competitor,
        portfolio=portfolio,
        financial_timeline=financial,
        launch_timeline=launches,
        other_signals=others,
        strategy_hypotheses=hyps,
        open_questions=open_q,
    )
