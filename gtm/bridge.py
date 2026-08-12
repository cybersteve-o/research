"""Revenue Bridge — die Lücke zwischen Plan und Forecast, in Ursachen zerlegt.

Der erste Bildschirm des Cockpits und die Naht zu den beiden anderen Säulen: der
Forecast liefert die Zahlen, das MCI-Tool liefert die Belege für die Zuordnung.

Drei Dinge macht dieses Modul bewusst unbequem:

**Der unerklärte Rest bleibt stehen.** Was die Zuordnung nicht erklärt, wird als
eigene Stufe ausgewiesen, nicht auf die anderen verteilt. Eine Brücke, bei der
70 % der Lücke unerklärt sind, ist ein ehrliches Ergebnis — und ein Auftrag an
die Recherche, kein Grund, die Zahlen zu glätten.

**Exogene Ursachen werden markiert.** Ein schrumpfender Markt ist keine
Maßnahme wert. Wer trotzdem Budget dagegen wirft, verbrennt es.

**Überattribution wird gemeldet.** Wenn die zugeordneten Ursachen zusammen mehr
ergeben als die Lücke, stimmt die Zerlegung nicht — dann sagt die Brücke das,
statt still zu skalieren.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fmt import eur as _eur
from .models import (
    CAUSE_LABELS,
    BridgeStep,
    CauseCode,
    PlanFigure,
)

# Ab diesem Anteil unerklärter Lücke ist die Brücke keine Entscheidungsgrundlage
# mehr, sondern eine Rechercheaufgabe.
UNEXPLAINED_WARN_SHARE = 0.35


@dataclass
class Bridge:
    """Plan ▸ Ursachen ▸ Forecast für eine Periode, optional je Markt gefiltert."""

    period: str = "FY2026"
    figures: list[PlanFigure] = field(default_factory=list)
    steps: list[BridgeStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def plan_eur(self) -> float:
        return sum(f.plan_eur for f in self.figures)

    @property
    def forecast_eur(self) -> float:
        return sum(f.forecast_eur for f in self.figures)

    @property
    def gap_eur(self) -> float:
        """Positiv = Unterdeckung gegen Plan."""
        return self.plan_eur - self.forecast_eur

    @property
    def explained_eur(self) -> float:
        return sum(s.amount_eur for s in self.steps if not s.is_unexplained)

    @property
    def unexplained_eur(self) -> float:
        return sum(s.amount_eur for s in self.steps if s.is_unexplained)

    @property
    def explained_share(self) -> float:
        return (self.explained_eur / self.gap_eur) if self.gap_eur > 0 else 0.0

    @property
    def addressable_eur(self) -> float:
        """Der Teil der Lücke, gegen den sich überhaupt etwas ausrichten lässt.

        Ohne exogene Ursachen, ohne unerklärten Rest. Das ist die Zahl, an der
        das Maßnahmenportfolio später gemessen wird — nicht die Gesamtlücke.
        """
        return sum(
            s.amount_eur
            for s in self.steps
            if not s.is_unexplained and not s.is_exogenous and s.amount_eur > 0
        )

    @property
    def markets(self) -> list[str]:
        return sorted({f.market for f in self.figures})

    def by_cause(self) -> list[tuple[CauseCode | None, float]]:
        """Ursachen, absteigend nach Betrag. Der unerklärte Rest steht am Ende."""
        agg: dict[CauseCode | None, float] = {}
        for s in self.steps:
            agg[s.cause] = agg.get(s.cause, 0.0) + s.amount_eur
        known = [(c, v) for c, v in agg.items() if c is not None]
        known.sort(key=lambda t: t[1], reverse=True)
        rest = [(c, v) for c, v in agg.items() if c is None]
        return known + rest

    def by_market(self) -> list[tuple[str, float]]:
        agg: dict[str, float] = {}
        for f in self.figures:
            agg[f.market] = agg.get(f.market, 0.0) + f.gap_eur
        return sorted(agg.items(), key=lambda t: t[1], reverse=True)

    def steps_for_market(self, market: str) -> list[BridgeStep]:
        return [s for s in self.steps if s.market == market]


def build(
    figures: list[PlanFigure],
    attributions: list[BridgeStep],
    *,
    period: str = "FY2026",
    markets: list[str] | None = None,
) -> Bridge:
    """Baut die Brücke und schließt sie mit dem unerklärten Rest.

    `attributions` sind die zugeordneten Ursachenanteile — aus dem Forecast-
    System, aus der Analyse oder von Hand. Pro Markt wird geprüft, ob sie die
    Lücke über- oder unterdecken; die Differenz wird als eigene Stufe ergänzt.
    """
    figs = [f for f in figures if f.period == period]
    if markets:
        keep = set(markets)
        figs = [f for f in figs if f.market in keep]
    attrs = [a for a in attributions if a.period == period]
    if markets:
        keep = set(markets)
        attrs = [a for a in attrs if a.market in keep]

    steps: list[BridgeStep] = list(attrs)
    warnings: list[str] = []

    # Je Markt den Rest bilden, damit die Brücke marktweise aufgeht.
    gap_by_market: dict[str, float] = {}
    for f in figs:
        gap_by_market[f.market] = gap_by_market.get(f.market, 0.0) + f.gap_eur
    attr_by_market: dict[str, float] = {}
    for a in attrs:
        attr_by_market[a.market] = attr_by_market.get(a.market, 0.0) + a.amount_eur

    for market, gap in sorted(gap_by_market.items()):
        attributed = attr_by_market.get(market, 0.0)
        residual = gap - attributed
        if abs(residual) < 1.0:
            continue
        if residual < 0:
            warnings.append(
                f"{market}: die zugeordneten Ursachen erklären "
                f"{_eur(abs(residual))} mehr als die Lücke — die Zerlegung ist "
                f"überattribuiert und muss korrigiert werden."
            )
        steps.append(BridgeStep(
            market=market, period=period, cause=None, amount_eur=residual,
            confidence=0.0,
            note="Nicht zugeordneter Rest — Auftrag an die Recherche.",
        ))

    bridge = Bridge(period=period, figures=figs, steps=steps, warnings=warnings)

    if bridge.gap_eur > 0 and bridge.unexplained_eur > 0:
        share = bridge.unexplained_eur / bridge.gap_eur
        if share >= UNEXPLAINED_WARN_SHARE:
            bridge.warnings.append(
                f"{share:.0%} der Lücke sind keiner Ursache zugeordnet. Ein "
                f"Maßnahmenpaket auf dieser Grundlage adressiert bestenfalls "
                f"{1 - share:.0%} des Problems."
            )
    exogenous = sum(s.amount_eur for s in bridge.steps if s.is_exogenous)
    if bridge.gap_eur > 0 and exogenous / bridge.gap_eur >= 0.25:
        bridge.warnings.append(
            f"{exogenous / bridge.gap_eur:.0%} der Lücke sind exogen "
            f"(Marktvolumen). Dagegen hilft kein Budget — dieser Teil gehört in "
            f"die Planrevision, nicht ins Maßnahmenportfolio."
        )
    return bridge
