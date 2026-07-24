"""Battlecard je Produktlinie — direkt vertriebsnutzbar (spec §4).

Wir vs. Top-3 competitors: strengths, weaknesses, price level, objection
handling. Weaknesses are pulled from customer_feedback signals (real recurring
issues), not invented. Every claim keeps its backing signal id so the card is
traceable.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .competitor import signal_mentions
from .db import Store
from .models import Competitor, SignalType


class CompetitorEntry(BaseModel):
    name: str
    known_weaknesses: list[str] = Field(default_factory=list)  # from feedback signals
    signal_ids: list[str] = Field(default_factory=list)


class Battlecard(BaseModel):
    line: str
    own_strengths: list[str] = Field(default_factory=list)
    own_weaknesses: list[str] = Field(default_factory=list)  # from own feedback
    competitors: list[CompetitorEntry] = Field(default_factory=list)
    price_note: str = ""
    objection_handling: list[str] = Field(default_factory=list)


def build(
    store: Store,
    line: str,
    *,
    segment: str = "",
    own_strengths: list[str] | None = None,
) -> Battlecard:
    signals = store.list_signals()
    feedback = [s for s in signals if s.type == SignalType.customer_feedback]

    own_weak = [
        s.fact for s in feedback
        if line.lower() in f"{s.headline} {s.fact}".lower()
    ]

    competitors = store.list_competitors()
    if segment:
        competitors = [c for c in competitors if segment in c.segments] or competitors
    top3 = competitors[:3]

    entries: list[CompetitorEntry] = []
    for c in top3:
        weak = [s for s in feedback if signal_mentions(s, c)]
        entries.append(
            CompetitorEntry(
                name=c.name,
                known_weaknesses=[s.fact for s in weak],
                signal_ids=[s.id for s in weak],
            )
        )

    price_signals = [
        s for s in signals if s.type == SignalType.financial and "marge" in s.fact.lower()
    ]
    price_note = (
        "Margentrend-Signale vorhanden — Preisdruck beobachten"
        if price_signals
        else "Keine Margensignale; Preiskorridor stabil annehmbar"
    )

    return Battlecard(
        line=line,
        own_strengths=own_strengths or [],
        own_weaknesses=own_weak,
        competitors=entries,
        price_note=price_note,
        objection_handling=[
            "Einwand Preis → Systemhaftung und Durchsetzungsquote betonen",
            "Einwand Verfügbarkeit → Listungstiefe/Distribution belegen",
        ],
    )
