"""Wirkungsrechnung — der deterministische Kern des Cockpits.

Jede Zahl, die eine Maßnahme trägt, entsteht hier, und zwar aus einer Kette, die
sich vollständig aufschreiben lässt:

    adressierte Lücke  ×  Wirkungsgrad  ×  Sättigung(Dosis)
                       ×  Evidenzabschlag  ×  Realisierungsanteil(Horizont)

`breakdown()` gibt genau diese Kette zurück, Glied für Glied. Wenn in der Demo
jemand fragt „woher kommt die Zahl?“, ist das die Antwort — nicht eine Prosa-
Begründung, sondern die Rechnung selbst.

Zwei Modellentscheidungen, die man kennen muss:

**Sättigung.** Der doppelte Einsatz bringt nicht die doppelte Wirkung. Die
Wirkung folgt einer konkaven Kurve über der Dosis, normiert auf s(0)=0 und
s(1)=1. Ohne diese Krümmung würde der Allokator sein gesamtes Budget in die eine
effizienteste Maßnahme kippen — ein Ergebnis, das jeder Praktiker sofort als
falsch erkennt.

**Realisierungsanteil.** Eine Maßnahme mit 27 Monaten Wirkzeit schließt die
Lücke des laufenden Geschäftsjahres nicht. Nicht ein bisschen — gar nicht. Der
Realisierungsanteil rechnet das aus, statt es der Diskussion zu überlassen, und
er ist der Grund, warum das Cockpit Wirkung *im Horizont* und Wirkung *voll
eingeschwungen* immer getrennt ausweist.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .fmt import eur as _eur
from .models import (
    EVIDENCE_DISCOUNT,
    Band,
    BridgeStep,
    CauseCode,
    Measure,
)

# Krümmung der Sättigungskurve. 2.5 bedeutet: die erste Hälfte des Einsatzes
# holt rund 71 % der Wirkung. Bewusst konservativ — wer den Wert ändert, ändert
# die Aussage des Portfolios und sollte das begründen können.
SATURATION_K = 2.5

# Schrittweite der Dosis in der Allokation. Kleiner = feiner, aber langsamer.
DOSE_STEP = 0.05

# Mindestdosis: unterhalb davon wird eine Maßnahme gar nicht gefahren. Programme
# haben Rüstkosten und binden Aufmerksamkeit; eine Maßnahme mit 5 % Einsatz
# existiert in der Praxis nicht, sie steht nur im Plan. Ohne diese Schwelle
# streut der Allokator das Budget in Dutzende Alibi-Maßnahmen, weil die
# Sättigungskurve kleine Dosen rechnerisch am effizientesten aussehen lässt.
MIN_DOSE = 0.25

# Eine Maßnahme muss sich mindestens selbst tragen: ihre eingeschwungene
# Jahreswirkung darf die Kosten nicht unterschreiten. Geprüft wird gegen die
# Run-Rate und nicht gegen die Wirkung im Horizont — sonst fiele jede
# Aufbaumaßnahme durch, deren Ertrag erst im Folgejahr anfällt. Ohne diese
# Grenze finanziert ein reiner Maximierer auch Maßnahmen, die 27.000 € kosten
# und 2.300 € zurückholen: rechnerisch ein Zugewinn, betriebswirtschaftlich Unfug.
MIN_PAYBACK_RATIO = 1.0

# Gewicht einer Neben-Ursache. Eine Maßnahme greift ihre Hauptursache voll an,
# die weiteren nur zur Hälfte — siehe `addressed_gap`.
SECONDARY_CAUSE_WEIGHT = 0.5


def saturation(dose: float) -> float:
    """Konkave Sättigung über der Dosis, normiert auf s(0)=0, s(1)=1."""
    if dose <= 0.0:
        return 0.0
    if dose >= 1.0:
        return 1.0
    return (1.0 - math.exp(-SATURATION_K * dose)) / (1.0 - math.exp(-SATURATION_K))


def realization_fraction(
    time_to_effect_months: int, ramp_months: int, horizon_months: int
) -> float:
    """Anteil der Jahreswirkung, der innerhalb des Horizonts tatsächlich anfällt.

    Die Wirkung setzt nach `time_to_effect_months` ein und steigt über
    `ramp_months` linear auf ihr volles Niveau. Zurückgegeben wird das über den
    Horizont gemittelte Wirkungsniveau — also der Anteil der eingeschwungenen
    Jahreswirkung, der in der Periode wirklich verdient wird.
    """
    horizon = float(horizon_months)
    start = float(time_to_effect_months)
    ramp = float(max(ramp_months, 0))
    if horizon <= 0:
        return 0.0
    if horizon <= start:
        return 0.0
    if ramp <= 0:
        return (horizon - start) / horizon
    if horizon <= start + ramp:
        return ((horizon - start) ** 2 / (2.0 * ramp)) / horizon
    return (ramp / 2.0 + (horizon - start - ramp)) / horizon


def addressed_gap(measure: Measure, steps: list[BridgeStep]) -> tuple[float, dict[CauseCode, float]]:
    """Was eine Maßnahme angreifen kann — Summe und Aufteilung auf die Ursachen.

    Die erste Ursache in `addresses` gilt als Hauptursache und zählt voll; jede
    weitere zählt nur mit `SECONDARY_CAUSE_WEIGHT`. Ohne diese Regel würde eine
    Maßnahme, die zwei Ursachen streift, die Summe beider für sich reklamieren —
    und breit angelegte Maßnahmen sähen systematisch besser aus als gezielte,
    was das Gegenteil der Wahrheit ist.

    Nur positive Beträge zählen: eine Ursache, die den Plan *stützt*, ist kein
    Angriffspunkt. Unerklärte Reste zählen nie mit — auf etwas, das niemand
    erklären kann, lässt sich keine Maßnahme richten.
    """
    weights = {
        cause: (1.0 if i == 0 else SECONDARY_CAUSE_WEIGHT)
        for i, cause in enumerate(measure.addresses)
    }
    per_cause: dict[CauseCode, float] = {}
    for s in steps:
        if s.cause in weights and s.amount_eur > 0 and not s.is_unexplained:
            per_cause[s.cause] = per_cause.get(s.cause, 0.0) + s.amount_eur * weights[s.cause]
    total = sum(per_cause.values())
    shares = {c: v / total for c, v in per_cause.items()} if total > 0 else {}
    return total, shares


def addressed_gap_eur(measure: Measure, steps: list[BridgeStep]) -> float:
    """Nur die Summe — für Aufrufer, die die Aufteilung nicht brauchen."""
    return addressed_gap(measure, steps)[0]


@dataclass
class EffectBreakdown:
    """Die Rechenkette einer einzelnen Maßnahme, Glied für Glied."""

    measure_name: str = ""
    market: str = ""
    addressed_gap_eur: float = 0.0
    effect_grade: Band = field(default_factory=Band)
    dose: float = 0.0
    saturation: float = 0.0
    evidence_discount: float = 1.0
    realization: float = 0.0
    horizon_months: int = 12
    effect_horizon: Band = field(default_factory=Band)
    effect_run_rate: Band = field(default_factory=Band)
    cost_eur: float = 0.0

    def as_rows(self) -> list[tuple[str, str]]:
        """Für die Oberfläche: die Kette als lesbare Zeilen."""
        return [
            ("Adressierte Lücke", f"{_eur(self.addressed_gap_eur)}"),
            ("× Wirkungsgrad (Band)",
             f"{self.effect_grade.low:.0%} / {self.effect_grade.mode:.0%} / "
             f"{self.effect_grade.high:.0%}"),
            (f"× Sättigung bei Dosis {self.dose:.0%}", f"{self.saturation:.2f}"),
            ("× Evidenzabschlag", f"{self.evidence_discount:.2f}"),
            ("= Wirkung eingeschwungen p. a.", f"{_eur(self.effect_run_rate.mode)}"),
            (f"× Realisierung in {self.horizon_months} Monaten", f"{self.realization:.2f}"),
            ("= Wirkung im Horizont", f"{_eur(self.effect_horizon.mode)}"),
        ]


def cost_for(measure: Measure, dose: float, market_factor: float = 1.0) -> float:
    """Kosten sind linear in der Dosis — nur die Wirkung sättigt, nicht der Preis."""
    return measure.cost_full_eur * market_factor * max(0.0, min(1.0, dose))


def capacity_for(measure: Measure, dose: float, market_factor: float = 1.0) -> float:
    return measure.capacity_fte_months * market_factor * max(0.0, min(1.0, dose))


def effect_for(
    measure: Measure,
    addressed_gap: float,
    dose: float,
    horizon_months: int,
) -> tuple[Band, Band]:
    """(Wirkung im Horizont, Wirkung voll eingeschwungen) als Bänder."""
    if addressed_gap <= 0 or dose <= 0:
        return Band(), Band()
    discount = EVIDENCE_DISCOUNT[measure.evidence_class]
    run_rate = measure.effect_grade.scaled(addressed_gap * saturation(dose) * discount)
    realization = realization_fraction(
        measure.time_to_effect_months, measure.ramp_months, horizon_months
    )
    return run_rate.scaled(realization), run_rate


def breakdown(
    measure: Measure,
    steps: list[BridgeStep],
    dose: float,
    horizon_months: int,
    *,
    market: str = "",
    market_factor: float = 1.0,
) -> EffectBreakdown:
    """Die vollständige, nachrechenbare Herleitung einer Maßnahmenwirkung."""
    gap = addressed_gap_eur(measure, steps)
    horizon, run_rate = effect_for(measure, gap, dose, horizon_months)
    return EffectBreakdown(
        measure_name=measure.name,
        market=market,
        addressed_gap_eur=gap,
        effect_grade=measure.effect_grade,
        dose=dose,
        saturation=saturation(dose),
        evidence_discount=EVIDENCE_DISCOUNT[measure.evidence_class],
        realization=realization_fraction(
            measure.time_to_effect_months, measure.ramp_months, horizon_months
        ),
        horizon_months=horizon_months,
        effect_horizon=horizon,
        effect_run_rate=run_rate,
        cost_eur=cost_for(measure, dose, market_factor),
    )


def acts_within(measure: Measure, horizon_months: int) -> bool:
    """Wirkt die Maßnahme im Betrachtungszeitraum überhaupt noch?"""
    return realization_fraction(
        measure.time_to_effect_months, measure.ramp_months, horizon_months
    ) > 0.0


def cause_headroom(steps: list[BridgeStep]) -> dict[CauseCode, float]:
    """Wie viel Lücke je Ursache maximal zurückzuholen ist.

    Die Obergrenze, gegen die der Allokator prüft. Ohne sie summieren sich
    Maßnahmen fröhlich auf 300 % der Lücke — der klassische Planungsunfug, den
    dieses Cockpit gerade verhindern soll.
    """
    out: dict[CauseCode, float] = {}
    for s in steps:
        if s.cause is None or s.amount_eur <= 0:
            continue
        out[s.cause] = out.get(s.cause, 0.0) + s.amount_eur
    return out
