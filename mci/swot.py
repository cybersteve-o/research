"""Wettbewerbs-Matrix & SWOT (requirement: „automatischer Vergleich von Preisen,
Funktionen und Stärken (SWOT-Analyse)").

Built only from stored, source-linked signals — the matrix counts observed
activity per competitor, and the SWOT buckets are rule-derived and labelled as
interpretation (never fact). Where the evidence is thin, the cell says so instead
of inventing a comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mci.db import Store
from mci.models import SignalType
from mci.sentiment import competitor_sentiment

# Activity buckets shown as matrix columns.
_COLUMNS = {
    "Launches": {SignalType.launch},
    "Zulassungen/Patente": {SignalType.regulatory, SignalType.patent},
    "Kapazität/Personal": {SignalType.hiring, SignalType.channel},
    "Finanzen": {SignalType.financial},
    "Feedback": {SignalType.customer_feedback},
}


def matrix(store: Store) -> list[dict]:
    """One row per competitor: observed activity counts + segments + sentiment."""
    sent = {b.competitor: b for b in competitor_sentiment(store)}
    rows: list[dict] = []
    for c in store.list_competitors():
        sigs = [s for s in store.list_signals() if c.name in s.entities.competitors]
        row: dict = {"Wettbewerber": c.name, "Land": c.country,
                     "Segmente": ", ".join(c.segments) or "—"}
        for col, types in _COLUMNS.items():
            row[col] = sum(1 for s in sigs if s.type in types)
        bs = sent.get(c.name)
        row["Sentiment"] = bs.label if bs else "—"
        rows.append(row)
    return rows


@dataclass
class SWOT:
    competitor: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.strengths or self.weaknesses
                    or self.opportunities or self.threats)


def swot(store: Store, competitor_id: str) -> SWOT | None:
    """Rule-derived SWOT for one competitor from its signals (interpretation)."""
    comp = next((c for c in store.list_competitors() if c.id == competitor_id), None)
    if comp is None:
        return None
    sigs = [s for s in store.list_signals() if comp.name in s.entities.competitors]
    res = SWOT(competitor=comp.name)
    for s in sigs:
        # Strengths: their strong offensive moves.
        if s.type in (SignalType.regulatory, SignalType.patent, SignalType.launch):
            res.strengths.append(s.headline)
        # Weaknesses: negative voice-of-market about them.
        if s.type == SignalType.customer_feedback:
            from mci.sentiment import score_text
            if score_text(f"{s.headline} {s.fact}") < -0.15:
                res.weaknesses.append(s.headline)
        # Threats: expansion / hiring in a market (pressure on us).
        if s.type in (SignalType.hiring, SignalType.channel):
            res.threats.append(s.headline)
        # Opportunities: their open questions / our known gaps around them.
        res.opportunities.extend(s.known_unknowns)
    # dedupe, keep order, cap
    for name in ("strengths", "weaknesses", "opportunities", "threats"):
        seen: set[str] = set()
        vals = [x for x in getattr(res, name) if not (x in seen or seen.add(x))]
        setattr(res, name, vals[:6])
    return res
