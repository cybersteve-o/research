"""Nachhalten — erwartete gegen eingetretene Wirkung.

Der Teil, den fast jedes Planungswerkzeug wegläßt, und der einzige, der aus
Meinung mit der Zeit Wissen macht. Ohne ihn ist das Cockpit ein hübscher
Vorschlagsgenerator; mit ihm bekommt es eine Bilanz.

Drei Kennzahlen, alle bewusst unbestechlich:

* **Trefferquote** — Anteil der gemessenen Maßnahmen, deren Ergebnis im
  vorhergesagten Band lag. Offene Maßnahmen zählen nie als Treffer.
* **Optimismus-Bias** — die systematische Schlagseite. Positiv heißt: die
  Ergebnisse fielen schlechter aus als erwartet, wir waren zu optimistisch.
  Aufgeschlüsselt nach Träger, was in einer zusammengeführten Einheit die
  vielleicht heikelste und nützlichste Zahl im ganzen Werkzeug ist.
* **Kalibrierung** — ob die Evidenzabschläge aus `models.py` stimmen. Wenn
  Maßnahmen der Klasse „angenommen“ im Schnitt 45 % unter Erwartung liefern, war
  ein Abschlag von 60 % zu milde. Das Modul rechnet das aus und *schlägt vor*;
  ändern muss ein Mensch.

Nichts hier wird von einer KI gefüllt. Ein Mensch trägt das Ergebnis ein, das
Modul aggregiert nur — genau wie `mci.tracking`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .fmt import eur as _eur
from .models import (
    EVIDENCE_DISCOUNT,
    EVIDENCE_LABELS,
    INSTRUMENT_LABELS,
    EvidenceClass,
    Instrument,
    MeasureOutcome,
    Portfolio,
)

# Unter dieser Fallzahl ist jede Aussage über Bias oder Kalibrierung Rauschen.
MIN_CASES = 3


def expectations_from(portfolio: Portfolio, *, owner: str = "") -> list[MeasureOutcome]:
    """Friert die Erwartung eines beschlossenen Portfolios ein.

    Der entscheidende Schritt: die Erwartung wird *vor* dem Ergebnis
    festgeschrieben. Wer erst hinterher notiert, was er erwartet hatte, misst
    seine Erinnerung, nicht seine Prognose.
    """
    return [
        MeasureOutcome(
            measure_id=a.measure_id,
            measure_name=a.measure_name,
            market=a.market,
            period=a.period,
            expected=a.effect_horizon,
            owner=owner,
            status="offen",
        )
        for a in portfolio.allocations
    ]


def record_actual(
    outcome: MeasureOutcome, actual_eur: float, *, note: str = ""
) -> MeasureOutcome:
    """Trägt das gemessene Ergebnis ein."""
    outcome.actual_eur = actual_eur
    outcome.status = "gemessen"
    outcome.measured_at = datetime.now(timezone.utc)
    if note:
        outcome.note = note
    return outcome


def _measured(outcomes: list[MeasureOutcome]) -> list[MeasureOutcome]:
    return [o for o in outcomes if o.status == "gemessen" and o.actual_eur is not None]


def hit_rate(outcomes: list[MeasureOutcome]) -> float | None:
    """Anteil der gemessenen Maßnahmen, die im vorhergesagten Band lagen."""
    measured = _measured(outcomes)
    if not measured:
        return None
    return round(sum(1 for o in measured if o.within_band) / len(measured), 3)


def optimism_bias(outcomes: list[MeasureOutcome]) -> float | None:
    """Mittlere relative Abweichung. Positiv = wir waren zu optimistisch."""
    measured = [o for o in _measured(outcomes) if o.expected.mode > 0]
    if not measured:
        return None
    deltas = [
        (o.expected.mode - float(o.actual_eur)) / o.expected.mode for o in measured
    ]
    return round(sum(deltas) / len(deltas), 3)


@dataclass
class BiasRow:
    label: str
    n: int
    bias: float | None
    hit_rate: float | None


def bias_by_instrument(outcomes: list[MeasureOutcome],
                       instrument_of: dict[str, Instrument]) -> list[BiasRow]:
    """Schlagseite je Träger — Vertrieb, Marketing, gemeinsam.

    `instrument_of` bildet Maßnahmen-ID auf Träger ab; die Zuordnung kommt aus
    dem Katalog, nicht aus dem Ergebnis, damit sie nicht nachträglich passend
    gemacht werden kann.
    """
    buckets: dict[Instrument, list[MeasureOutcome]] = {}
    for o in outcomes:
        inst = instrument_of.get(o.measure_id)
        if inst is None:
            continue
        buckets.setdefault(inst, []).append(o)

    rows = [
        BiasRow(
            label=INSTRUMENT_LABELS[inst],
            n=len(_measured(items)),
            bias=optimism_bias(items),
            hit_rate=hit_rate(items),
        )
        for inst, items in buckets.items()
    ]
    rows.sort(key=lambda r: r.n, reverse=True)
    return rows


@dataclass
class CalibrationRow:
    evidence_class: EvidenceClass
    label: str
    n: int
    mean_ratio: float | None       # Ist / Erwartung
    current_discount: float = 1.0
    suggested_discount: float | None = None
    note: str = ""


def calibration(
    outcomes: list[MeasureOutcome], evidence_of: dict[str, EvidenceClass]
) -> list[CalibrationRow]:
    """Prüft die Evidenzabschläge gegen die Wirklichkeit.

    Das ist die Selbstkorrektur des Werkzeugs. Der Vorschlag wird berechnet, aber
    nie automatisch übernommen — ein Modell, das seine eigenen Parameter still
    nachzieht, ist nicht mehr prüfbar.
    """
    buckets: dict[EvidenceClass, list[MeasureOutcome]] = {}
    for o in outcomes:
        klass = evidence_of.get(o.measure_id)
        if klass is None:
            continue
        buckets.setdefault(klass, []).append(o)

    rows: list[CalibrationRow] = []
    for klass in EvidenceClass:
        items = _measured(buckets.get(klass, []))
        current = EVIDENCE_DISCOUNT[klass]
        if len(items) < MIN_CASES:
            rows.append(CalibrationRow(
                evidence_class=klass, label=EVIDENCE_LABELS[klass],
                n=len(items), mean_ratio=None, current_discount=current,
                note=f"Zu wenige Fälle ({len(items)} von {MIN_CASES}) — "
                     f"keine Aussage.",
            ))
            continue
        ratios = [
            float(o.actual_eur) / o.expected.mode
            for o in items if o.expected.mode > 0
        ]
        mean_ratio = sum(ratios) / len(ratios) if ratios else None
        suggested = None
        note = ""
        if mean_ratio is not None:
            suggested = round(max(0.2, min(1.0, current * mean_ratio)), 2)
            if abs(suggested - current) < 0.05:
                note = "Abschlag passt."
            elif suggested < current:
                note = (f"Abschlag zu milde — Vorschlag {suggested:.2f} "
                        f"statt {current:.2f}.")
            else:
                note = (f"Abschlag zu streng — Vorschlag {suggested:.2f} "
                        f"statt {current:.2f}.")
        rows.append(CalibrationRow(
            evidence_class=klass, label=EVIDENCE_LABELS[klass], n=len(items),
            mean_ratio=round(mean_ratio, 3) if mean_ratio is not None else None,
            current_discount=current, suggested_discount=suggested, note=note,
        ))
    return rows


@dataclass
class TrackReport:
    n_total: int = 0
    n_measured: int = 0
    n_open: int = 0
    expected_eur: float = 0.0
    actual_eur: float = 0.0
    hit_rate: float | None = None
    optimism_bias: float | None = None
    by_instrument: list[BiasRow] = field(default_factory=list)
    calibration: list[CalibrationRow] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def report(
    outcomes: list[MeasureOutcome],
    *,
    instrument_of: dict[str, Instrument] | None = None,
    evidence_of: dict[str, EvidenceClass] | None = None,
) -> TrackReport:
    """Die Bilanz des Werkzeugs in einem Objekt."""
    measured = _measured(outcomes)
    rep = TrackReport(
        n_total=len(outcomes),
        n_measured=len(measured),
        n_open=sum(1 for o in outcomes if o.status == "offen"),
        expected_eur=round(sum(o.expected.mode for o in measured), 2),
        actual_eur=round(sum(float(o.actual_eur) for o in measured), 2),
        hit_rate=hit_rate(outcomes),
        optimism_bias=optimism_bias(outcomes),
    )
    if instrument_of:
        rep.by_instrument = bias_by_instrument(outcomes, instrument_of)
    if evidence_of:
        rep.calibration = calibration(outcomes, evidence_of)

    if rep.n_measured == 0:
        rep.lines.append(
            "Noch kein Ergebnis gemessen — das Werkzeug hat bislang keine Bilanz. "
            "Bis dahin sind alle Wirkungsangaben Erwartungen, nichts weiter."
        )
        return rep

    rep.lines.append(
        f"{rep.n_measured} von {rep.n_total} Maßnahmen gemessen; erwartet "
        f"{_eur(rep.expected_eur)}, eingetreten {_eur(rep.actual_eur)}."
    )
    if rep.hit_rate is not None:
        rep.lines.append(
            f"Trefferquote {rep.hit_rate:.0%} — so oft lag das Ergebnis im "
            f"vorhergesagten Band."
        )
    if rep.optimism_bias is not None:
        if rep.optimism_bias > 0.1:
            rep.lines.append(
                f"Optimismus-Bias +{rep.optimism_bias:.0%}: die Wirkungen fielen "
                f"systematisch schwächer aus als erwartet. Künftige Portfolios "
                f"sollten entsprechend gelesen werden."
            )
        elif rep.optimism_bias < -0.1:
            rep.lines.append(
                f"Bias {rep.optimism_bias:.0%}: die Wirkungen fielen stärker aus "
                f"als erwartet — die Schätzungen sind zu vorsichtig."
            )
        else:
            rep.lines.append(
                f"Bias {rep.optimism_bias:+.0%}: die Schätzungen sind im Mittel "
                f"unverzerrt."
            )
    for row in rep.by_instrument:
        if row.bias is not None and abs(row.bias) > 0.15 and row.n >= MIN_CASES:
            direction = "zu optimistisch" if row.bias > 0 else "zu vorsichtig"
            rep.lines.append(
                f"{row.label} schätzt systematisch {direction} "
                f"({row.bias:+.0%} über {row.n} Fälle)."
            )
    return rep
