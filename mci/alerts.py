"""Frühwarnsystem (requirement: „meldet sofort, wenn ein Konkurrent die Preise
ändert oder ein neues Produkt ankündigt").

Rule-based alerts over the signal store. Deliberately explicit and traceable:
each alert names the rule that fired and carries the underlying signal, so a
warning is never an opaque model opinion. Recency-weighted — an alert about a
two-day-old launch outranks a three-week-old one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mci.db import Store
from mci.models import Signal, SignalType

# Keyword triggers for a price move (headline/fact), DE + EN.
_PRICE_RE = re.compile(
    r"\b(preis|preise|rabatt|discount|price|pricing|tarif|senk\w*|erhöh\w*|"
    r"reduz\w*|cut|increase|teurer|günstiger|angebot)\b", re.IGNORECASE)


@dataclass
class Alert:
    level: str          # hoch | mittel | niedrig
    kind: str           # Preisänderung | Neues Produkt | Zulassung/Patent
    entity: str
    headline: str
    signal_id: str
    at: datetime
    decision_link: list[str] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return {"hoch": "🔴", "mittel": "🟠", "niedrig": "🟡"}.get(self.level, "•")


_LEVEL_ORDER = {"hoch": 0, "mittel": 1, "niedrig": 2}


def _who(s: Signal) -> str:
    return ", ".join(s.entities.competitors or s.entities.markets) or "—"


def _classify(s: Signal) -> tuple[str, str] | None:
    """Return (kind, level) if the signal warrants an early warning, else None."""
    text = f"{s.headline} {s.fact}"
    if _PRICE_RE.search(text):
        return ("Preisänderung", "hoch")
    if s.type == SignalType.launch:
        return ("Neues Produkt", "hoch")
    if s.type in (SignalType.regulatory, SignalType.patent):
        return ("Zulassung/Patent", "mittel")
    return None


def detect(store: Store, *, now: datetime | None = None, window_days: int = 21) -> list[Alert]:
    """Scan recent, non-refuted signals and raise early-warning alerts."""
    now = now or datetime.now(timezone.utc)
    alerts: list[Alert] = []
    for s in store.list_signals():
        if s.status.value == "refuted":
            continue
        seen = s.last_seen or s.first_seen
        if seen and (now - seen).days > window_days:
            continue
        hit = _classify(s)
        if not hit:
            continue
        kind, level = hit
        alerts.append(Alert(
            level=level, kind=kind, entity=_who(s), headline=s.headline,
            signal_id=s.id, at=seen or now, decision_link=s.decision_link,
        ))
    alerts.sort(key=lambda a: (_LEVEL_ORDER.get(a.level, 9), -a.at.timestamp()))
    return alerts
