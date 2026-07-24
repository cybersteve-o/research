"""Synthese-Ableitungen — explizite Korrelationsregeln (spec §2.5).

The genuinely valuable insights arise from *combinations* of signals. These are
implemented as explicit, inspectable rules — not an opaque model. Each fired rule
returns the backing signal ids so the conclusion stays traceable, and its
confidence is aggregated deterministically from those signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .competitor import signal_mentions
from .db import Store
from .decisions import aggregate_confidence
from .models import Competitor, Signal, SignalType


@dataclass
class CorrelationInsight:
    rule_id: str
    label: str
    entity: str
    signal_ids: list[str]
    conclusion: str
    decision_link: list[str]
    confidence: float
    contributing_types: list[str] = field(default_factory=list)


def _by_type(signals: list[Signal], stype: SignalType) -> list[Signal]:
    return [s for s in signals if s.type == stype]


def _has(text_signals: list[Signal], *keywords: str) -> list[Signal]:
    out = []
    for s in text_signals:
        hay = f"{s.headline} {s.fact}".lower()
        if any(k in hay for k in keywords):
            out.append(s)
    return out


def _insight(rule_id, label, entity, signals, conclusion, links) -> CorrelationInsight:
    return CorrelationInsight(
        rule_id=rule_id,
        label=label,
        entity=entity,
        signal_ids=[s.id for s in signals],
        conclusion=conclusion,
        decision_link=links,
        confidence=aggregate_confidence(signals),
        contributing_types=sorted({s.type.value for s in signals}),
    )


def evaluate(store: Store) -> list[CorrelationInsight]:
    """Run all correlation rules over the current signal base."""
    signals = store.list_signals()
    insights: list[CorrelationInsight] = []
    for competitor in store.list_competitors():
        cs = [s for s in signals if signal_mentions(s, competitor)]
        if not cs:
            continue
        insights.extend(_rules_for_competitor(store, competitor, cs))
    return insights


def _rules_for_competitor(
    store: Store, competitor: Competitor, cs: list[Signal]
) -> list[CorrelationInsight]:
    out: list[CorrelationInsight] = []
    name = competitor.name

    regulatory = _by_type(cs, SignalType.regulatory)
    hiring = _by_type(cs, SignalType.hiring)
    financial = _by_type(cs, SignalType.financial)
    marketing = _by_type(cs, SignalType.marketing)
    channel = _by_type(cs, SignalType.channel)

    capex = _has(financial, "capex", "werk", "standort", "kapazit", "plant")
    margin_down = _has(financial, "marge", "margin")

    # R1: Zulassung + Stellenanzeige + Capex -> Launch-Wahrscheinlichkeit hoch
    if regulatory and hiring and capex:
        out.append(_insight(
            "R1", "Zulassung + Hiring + Capex", name,
            regulatory + hiring + capex,
            "Launch-Wahrscheinlichkeit hoch, Zeitfenster schätzbar.",
            ["E2", "E6"]))

    # R2: Margenverfall + Kapazitätsaufbau -> Preisoffensive wahrscheinlich
    if margin_down and (capex or hiring):
        out.append(_insight(
            "R2", "Margenverfall + Kapazitätsaufbau", name,
            margin_down + capex + hiring,
            "Preisoffensive wahrscheinlich, nicht Premiumstrategie.",
            ["E3"]))

    # R3: Content-Verschiebung Richtung Planer + Anstieg Spec-Share
    planer_content = _has(marketing, "planer", "architekt", "spezifik", "bim")
    spec = _has(channel, "ausschreibung", "spec", "vorgeschrieben", "tender")
    if planer_content and spec:
        out.append(_insight(
            "R3", "Planer-Content + Spec-Share", name,
            planer_content + spec,
            "Angriff auf die Ausschreibungsebene, nicht auf den Handel.",
            ["E3", "E4"]))

    # R4: Produkte still aus Katalog + kein Nachfolger -> Rückzug aus Segment
    discontinued = [
        p for p in store.list_products()
        if p.competitor_id == competitor.id and p.status == "discontinued"
    ]
    for p in discontinued:
        successor = any(
            q.competitor_id == competitor.id and q.application == p.application
            and q.status == "active"
            for q in store.list_products()
        )
        if not successor:
            out.append(CorrelationInsight(
                "R4", "Katalog-Streichung ohne Nachfolger", name, [],
                f"Rückzug aus Segment '{p.application}' — Chance für eigenen Ausbau.",
                ["E1"], confidence=0.5, contributing_types=["catalog"]))

    return out
