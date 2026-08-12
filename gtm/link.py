"""Kopplung an die zweite Säule: MCI-Signale als Beleg für die Ursachenzuordnung.

Das ist die Naht, die den Dreiklang sichtbar macht. Eine Brückenstufe behauptet
„1,1 Mio € gehen an den Wettbewerb verloren“. Ohne Beleg ist das eine Meinung.
Dieses Modul holt die Signale, die genau diese Aussage stützen, hängt sie an die
Stufe und leitet daraus deren Konfidenz ab — deterministisch, aus Quellenklasse,
Status und Alter der Signale, wie sie das MCI-Tool bereits berechnet hat.

Die Zuordnung Signal ▸ Ursache läuft zweistufig: erst über den Signaltyp, dann
über Stichwörter im Faktentext. Beides ist bewusst grob und liefert Kandidaten,
keine Wahrheit — deshalb bleibt die Stufe ohne Signale nicht etwa unbelegt
stehen, sondern bekommt Konfidenz 0 und taucht in der Lückenliste auf.

Fehlt das MCI-Tool oder seine Datenbank, funktioniert das Cockpit unverändert
weiter; die Stufen sind dann eben unbelegt. Keine harte Abhängigkeit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bridge import Bridge
from .fmt import eur as _eur
from .models import CAUSE_LABELS, BridgeStep, CauseCode

try:  # Das MCI-Paket liegt im selben Repo, muss aber nicht installiert sein.
    from mci.db import Store
    from mci.models import Signal, SignalStatus, SignalType
    _MCI_AVAILABLE = True
except Exception:  # noqa: BLE001  # pragma: no cover - nur ohne mci-Paket
    Store = object  # type: ignore[assignment,misc]
    Signal = object  # type: ignore[assignment,misc]
    SignalStatus = None  # type: ignore[assignment]
    SignalType = None  # type: ignore[assignment]
    _MCI_AVAILABLE = False


# Grobzuordnung über den Signaltyp.
_TYPE_TO_CAUSE: dict[str, list[CauseCode]] = {
    "channel": [CauseCode.distribution],
    "launch": [CauseCode.competitive_loss, CauseCode.mix],
    "regulatory": [CauseCode.specification],
    "patent": [CauseCode.mix],
    "marketing": [CauseCode.competitive_loss],
    "market_data": [CauseCode.market_volume],
    "financial": [CauseCode.price],
    "customer_feedback": [CauseCode.execution],
    "hiring": [CauseCode.competitive_loss],
}

# Feinzuordnung über Stichwörter im Fakt. Deutsch und englisch, weil die
# Ingestion beides einsammelt.
_KEYWORDS: list[tuple[tuple[str, ...], CauseCode]] = [
    (("listung", "sortiment", "regal", "händler", "distribution", "verfügbar",
      "listing", "shelf", "distributor"), CauseCode.distribution),
    (("preis", "rabatt", "kondition", "discount", "price", "pricing"),
     CauseCode.price),
    (("ausschreibung", "planer", "spezifikation", "norm", "zulassung", "eta-",
      "tender", "specification", "architect"), CauseCode.specification),
    (("marktvolumen", "nachfrage", "baugenehmigung", "konjunktur", "market volume",
      "demand", "permits"), CauseCode.market_volume),
    (("lieferzeit", "verfügbarkeit", "servicegrad", "lieferfähig", "lead time",
      "availability", "supply"), CauseCode.execution),
    (("marktanteil", "verdräng", "gewonnen", "verloren", "share", "switch"),
     CauseCode.competitive_loss),
    (("sortimentslücke", "produktlücke", "portfolio gap", "range gap"),
     CauseCode.mix),
]


def causes_for_signal(signal) -> list[CauseCode]:
    """Welche Ursachen dieses Signal stützen könnte. Kandidaten, keine Wahrheit."""
    out: list[CauseCode] = []
    stype = getattr(signal, "type", None)
    key = getattr(stype, "value", stype)
    if key in _TYPE_TO_CAUSE:
        out.extend(_TYPE_TO_CAUSE[key])

    text = " ".join(filter(None, [
        getattr(signal, "headline", ""),
        getattr(signal, "fact", ""),
        getattr(signal, "derivation", ""),
    ])).lower()
    for words, cause in _KEYWORDS:
        if any(w in text for w in words) and cause not in out:
            out.append(cause)
    return out


def _mentions_market(signal, market: str) -> bool:
    entities = getattr(signal, "entities", None)
    markets = list(getattr(entities, "markets", []) or []) if entities else []
    if market in markets:
        return True
    text = " ".join(filter(None, [
        getattr(signal, "headline", ""), getattr(signal, "fact", "")
    ]))
    return f" {market}" in f" {text}" or f"({market})" in text


def evidence_for(
    store, market: str, cause: CauseCode, *, limit: int = 5
) -> list:
    """Die stärksten Signale, die eine Ursache in einem Markt stützen."""
    if not _MCI_AVAILABLE or store is None:
        return []
    hits = []
    for sig in store.list_signals():
        if cause not in causes_for_signal(sig):
            continue
        if not _mentions_market(sig, market):
            continue
        hits.append(sig)
    hits.sort(key=lambda s: getattr(s, "priority", 0.0), reverse=True)
    return hits[:limit]


def _confidence_from(signals: list) -> float:
    """Konfidenz einer Zuordnung aus den stützenden Signalen.

    Kein eigenes Modell: das MCI-Tool hat die Signalkonfidenz bereits aus
    Quellenklasse, Triangulation und Alter berechnet. Hier wird nur aggregiert —
    Mittel der drei stärksten, mit Zuschlag, wenn mindestens eines bestätigt ist.
    """
    if not signals:
        return 0.0
    top = sorted((getattr(s, "confidence", 0.0) for s in signals), reverse=True)[:3]
    base = sum(top) / len(top)
    confirmed = any(
        getattr(getattr(s, "status", None), "value", None) == "confirmed"
        for s in signals
    )
    return round(min(1.0, base * (1.15 if confirmed else 0.9)), 3)


def attach_evidence(bridge: Bridge, store) -> Bridge:
    """Hängt Signale an jede Brückenstufe und setzt deren Konfidenz.

    Verändert die Beträge nicht — nur ihre Belastbarkeit. Eine Stufe ohne Signal
    behält ihren Euro-Betrag und bekommt Konfidenz 0; sie ist damit nicht falsch,
    aber unbelegt, und die Oberfläche zeigt das.
    """
    for step in bridge.steps:
        if step.cause is None:
            continue
        signals = evidence_for(store, step.market, step.cause)
        step.evidence_signal_ids = [getattr(s, "id", "") for s in signals]
        step.confidence = _confidence_from(signals)
    return bridge


@dataclass
class GapItem:
    """Eine Ursache ohne belastbaren Beleg — Auftrag an die Recherche."""

    market: str
    cause: CauseCode
    amount_eur: float
    confidence: float

    @property
    def label(self) -> str:
        return CAUSE_LABELS[self.cause]

    def research_question(self) -> str:
        return (
            f"{self.market}: Womit lässt sich belegen, dass "
            f"{_eur(self.amount_eur)} der Planlücke auf "
            f"„{self.label}“ zurückgehen?"
        )


def open_gaps(bridge: Bridge, *, min_amount_eur: float = 100_000,
              max_confidence: float = 0.4) -> list[GapItem]:
    """Große Brückenstufen mit schwachem Beleg, absteigend nach Betrag.

    Das ist die Rückkopplung in die zweite Säule: Diese Liste gehört als
    Rechercheauftrag ins MCI-Tool. Der Kreis schließt sich genau hier.
    """
    items = [
        GapItem(market=s.market, cause=s.cause, amount_eur=s.amount_eur,
                confidence=s.confidence)
        for s in bridge.steps
        if s.cause is not None
        and s.amount_eur >= min_amount_eur
        and s.confidence <= max_confidence
    ]
    items.sort(key=lambda i: i.amount_eur, reverse=True)
    return items


def evidence_summary(bridge: Bridge) -> dict[str, float]:
    """Wie viel Euro Lücke belegt, schwach belegt und unbelegt sind."""
    strong = weak = none = 0.0
    for s in bridge.steps:
        if s.cause is None:
            continue
        if s.confidence >= 0.6:
            strong += s.amount_eur
        elif s.confidence > 0.0:
            weak += s.amount_eur
        else:
            none += s.amount_eur
    return {"belegt": strong, "schwach belegt": weak, "unbelegt": none}
