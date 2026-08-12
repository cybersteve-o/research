"""Playbook-Transfer — was in einem Markt gewirkt hat, anderswo anwenden.

Das Skalenversprechen einer global aufgestellten Einheit steht und fällt damit,
ob eine Erfahrung aus einem Land in einem anderen etwas wert ist. Meistens ist
sie das teilweise, und genau dieses „teilweise“ ist die interessante Zahl.

Der Übertragbarkeitswert setzt sich aus zwei Faktoren zusammen:

* **Marktähnlichkeit** — gewichteter Abstand über Kanalstruktur, Regulierung,
  Wettbewerbsdichte, Reife und Preisniveau. Die Gewichte stehen unten und sind
  diskutierbar; sie sind eine Setzung, keine Messung, und das Modul sagt das.
* **Belegstärke des Ursprungsfalls** — eine Maßnahme, deren Wirkung im
  Ursprungsmarkt sauber gemessen wurde, überträgt sich belastbarer als eine, bei
  der schon dort nur geschätzt wurde.

Was das Modul bewusst *nicht* tut: eine Wirkung im Zielmarkt versprechen. Es
liefert eine erwartete Bandbreite, den Übertragbarkeitswert und die konkreten
Strukturunterschiede, die dagegensprechen. Die Entscheidung bleibt beim Menschen,
und die Gegenargumente stehen gleich mit auf dem Zettel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Band, MarketProfile, MeasureOutcome

# Gewichte der Ähnlichkeitsdimensionen. Kanalstruktur wiegt am schwersten: eine
# Maßnahme, die über den Fachhandel läuft, scheitert in einem Markt mit anderer
# Kanalstruktur unabhängig von allem anderen.
DIMENSION_WEIGHTS: dict[str, float] = {
    "channel_concentration": 0.30,
    "competitive_density": 0.22,
    "maturity": 0.20,
    "regulation_intensity": 0.16,
    "price_level": 0.12,
}

DIMENSION_LABELS: dict[str, str] = {
    "channel_concentration": "Kanalstruktur",
    "competitive_density": "Wettbewerbsdichte",
    "maturity": "Marktreife",
    "regulation_intensity": "Regulierungsdichte",
    "price_level": "Preisniveau",
}

# Ab diesem Abstand in einer Dimension wird der Unterschied als Einwand genannt.
CAVEAT_THRESHOLD = 0.25

# Unter diesem Übertragbarkeitswert ist ein Transfer nicht zu empfehlen.
TRANSFER_FLOOR = 0.45


def similarity(a: MarketProfile, b: MarketProfile) -> float:
    """Gewichtete Ähnlichkeit zweier Märkte, 0..1."""
    distance = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        distance += weight * abs(getattr(a, dim) - getattr(b, dim))
    return round(max(0.0, 1.0 - distance), 3)


def differences(a: MarketProfile, b: MarketProfile) -> list[tuple[str, float]]:
    """Dimensionen mit relevantem Abstand, absteigend."""
    diffs = [
        (dim, round(abs(getattr(a, dim) - getattr(b, dim)), 3))
        for dim in DIMENSION_WEIGHTS
    ]
    diffs = [d for d in diffs if d[1] >= CAVEAT_THRESHOLD]
    diffs.sort(key=lambda t: t[1], reverse=True)
    return diffs


@dataclass
class TransferCandidate:
    """Ein Vorschlag, eine gemessene Maßnahme in einen anderen Markt zu tragen."""

    measure_name: str = ""
    source_market: str = ""
    target_market: str = ""
    similarity: float = 0.0
    evidence_strength: float = 0.0
    transferability: float = 0.0
    source_effect_eur: float = 0.0
    expected_effect: Band = field(default_factory=Band)
    caveats: list[str] = field(default_factory=list)

    @property
    def recommended(self) -> bool:
        return self.transferability >= TRANSFER_FLOOR

    @property
    def verdict(self) -> str:
        if self.transferability >= 0.75:
            return "übertragbar"
        if self.transferability >= TRANSFER_FLOOR:
            return "mit Anpassung übertragbar"
        return "nicht übertragen"


def _evidence_strength(outcome: MeasureOutcome) -> float:
    """Wie belastbar der Ursprungsfall ist.

    Gemessen und innerhalb des erwarteten Bandes ist der Idealfall. Gemessen und
    außerhalb ist immer noch besser als gar nicht gemessen — dann wissen wir
    wenigstens, dass unser Modell dort danebenlag.
    """
    if outcome.status != "gemessen" or outcome.actual_eur is None:
        return 0.35
    return 0.95 if outcome.within_band else 0.7


def transfer_candidates(
    outcomes: list[MeasureOutcome],
    profiles: dict[str, MarketProfile],
    *,
    targets: list[str] | None = None,
    min_effect_eur: float = 50_000,
) -> list[TransferCandidate]:
    """Alle sinnvollen Transfers aus gemessenen Ergebnissen in andere Märkte."""
    candidates: list[TransferCandidate] = []
    target_markets = targets or list(profiles)

    for outcome in outcomes:
        if outcome.actual_eur is None or outcome.actual_eur < min_effect_eur:
            continue
        source = profiles.get(outcome.market)
        if source is None:
            continue
        strength = _evidence_strength(outcome)

        for target in target_markets:
            if target == outcome.market:
                continue
            profile = profiles.get(target)
            if profile is None:
                continue
            sim = similarity(source, profile)
            transferability = round(sim * strength, 3)

            # Erwartete Wirkung: der gemessene Effekt, gedämpft mit der
            # Übertragbarkeit. Das Band öffnet sich, je unähnlicher die Märkte
            # sind — Unsicherheit wächst mit der Distanz, nicht mit der Zeit.
            spread = 0.25 + (1.0 - sim)
            centre = outcome.actual_eur * transferability
            expected = Band(
                low=round(centre * max(0.0, 1.0 - spread), 2),
                mode=round(centre, 2),
                high=round(centre * (1.0 + spread), 2),
            )

            caveats = [
                f"{DIMENSION_LABELS[dim]} weicht deutlich ab (Abstand {delta:.2f})"
                for dim, delta in differences(source, profile)
            ]
            if strength < 0.5:
                caveats.append(
                    "Der Ursprungsfall wurde nie nachgemessen — der Transfer "
                    "stützt sich auf eine Erwartung, nicht auf ein Ergebnis."
                )

            candidates.append(TransferCandidate(
                measure_name=outcome.measure_name,
                source_market=outcome.market,
                target_market=target,
                similarity=sim,
                evidence_strength=strength,
                transferability=transferability,
                source_effect_eur=outcome.actual_eur,
                expected_effect=expected,
                caveats=caveats,
            ))

    candidates.sort(key=lambda c: c.transferability, reverse=True)
    return candidates


def similarity_matrix(profiles: dict[str, MarketProfile]) -> list[dict]:
    """Alle Marktpaare mit ihrer Ähnlichkeit — für die Heatmap."""
    markets = sorted(profiles)
    return [
        {"source": a, "target": b, "similarity": similarity(profiles[a], profiles[b])}
        for a in markets
        for b in markets
    ]
