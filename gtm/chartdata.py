"""Datenaufbereitung für die Diagramme — bewusst getrennt von `charts.py`.

Dieselbe Trennung wie im MCI-Paket: hier entstehen die Zeilen, dort werden sie
gezeichnet. Der Vorteil ist Testbarkeit — die Formen lassen sich prüfen, ohne
Altair zu installieren oder ein Diagramm zu rendern.

Alle Funktionen geben Listen einfacher Dictionaries zurück und niemals None;
eine leere Liste ist das Signal „nichts zu zeichnen“.
"""

from __future__ import annotations

from .allocate import FrontierPoint
from .bridge import Bridge
from .effects import realization_fraction
from .models import (
    CAUSE_LABELS,
    EVIDENCE_LABELS,
    INSTRUMENT_LABELS,
    CauseCode,
    Instrument,
    MarketProfile,
    Measure,
    MeasureOutcome,
    Portfolio,
)


def waterfall_rows(bridge: Bridge) -> list[dict]:
    """Die **Lücke**, Ursache für Ursache aufgebaut — nicht Plan ▸ Forecast.

    Der Unterschied ist keine Kosmetik. Ein Wasserfall von 680 Mio auf 638 Mio
    zeichnet die Ursachen als Millimeterstreifen an den oberen Rand: rechnerisch
    korrekt, praktisch unlesbar. Hier beginnt die Achse bei null und endet bei
    der Lücke, sodass jede Ursache die Höhe bekommt, die ihrer Bedeutung für die
    Entscheidung entspricht. Plan und Forecast stehen als Kennzahlen darüber.

    Jede Stufe trägt `start` und `end` für den Bereichsbalken sowie eine Rolle,
    über die die Farbe zugewiesen wird — Ursache, exogen, unerklärt oder Summe.
    """
    rows: list[dict] = []
    running = 0.0
    for i, (cause, amount) in enumerate(bridge.by_cause()):
        if cause is None:
            label, role = "Unerklärt", "Unerklärt"
        else:
            label = CAUSE_LABELS[cause]
            role = "Exogen" if cause is CauseCode.market_volume else "Ursache"
        start = running
        running += amount
        rows.append({
            "label": label, "role": role, "amount": amount,
            "start": start, "end": running, "order": i,
        })
    rows.append({
        "label": "Lücke gesamt", "role": "Summe", "amount": bridge.gap_eur,
        "start": 0.0, "end": bridge.gap_eur, "order": len(rows),
    })
    return rows


def evidence_rows(bridge: Bridge) -> list[dict]:
    """Belegte, schwach belegte und unbelegte Lücke je Markt."""
    agg: dict[tuple[str, str], float] = {}
    for step in bridge.steps:
        if step.cause is None:
            continue
        if step.confidence >= 0.6:
            band = "belegt"
        elif step.confidence > 0.0:
            band = "schwach belegt"
        else:
            band = "unbelegt"
        agg[(step.market, band)] = agg.get((step.market, band), 0.0) + step.amount_eur
    return [
        {"market": market, "band": band, "amount": amount}
        for (market, band), amount in sorted(agg.items())
    ]


def measure_rows(portfolio: Portfolio) -> list[dict]:
    """Maßnahmen mit Wirkungsband — für den Balken mit Fehlerbalken."""
    return [
        {
            "measure": a.measure_name,
            "label": f"{a.market} · {a.measure_name}",
            "market": a.market,
            "instrument": INSTRUMENT_LABELS[a.instrument],
            "evidence": EVIDENCE_LABELS[a.evidence_class],
            "dose": a.dose,
            "cost": a.cost_eur,
            "effect": a.effect_horizon.mode,
            "effect_low": a.effect_horizon.low,
            "effect_high": a.effect_horizon.high,
            "run_rate": a.effect_run_rate.mode,
            "efficiency": a.efficiency,
        }
        for a in portfolio.allocations
    ]


def instrument_rows(portfolio: Portfolio) -> list[dict]:
    """Wirkung je Träger — die Integrationskennzahl als Diagramm."""
    agg: dict[Instrument, float] = {}
    cost: dict[Instrument, float] = {}
    for a in portfolio.allocations:
        agg[a.instrument] = agg.get(a.instrument, 0.0) + a.effect_horizon.mode
        cost[a.instrument] = cost.get(a.instrument, 0.0) + a.cost_eur
    total = sum(agg.values()) or 1.0
    return [
        {
            "instrument": INSTRUMENT_LABELS[inst],
            "effect": value,
            "cost": cost.get(inst, 0.0),
            "share": value / total,
        }
        for inst, value in sorted(agg.items(), key=lambda t: t[1], reverse=True)
    ]


def market_rows(portfolio: Portfolio, bridge: Bridge) -> list[dict]:
    """Lücke gegen Wirkung je Markt — wo das Paket trägt und wo nicht."""
    gap = dict(bridge.by_market())
    effect: dict[str, float] = {}
    cost: dict[str, float] = {}
    for a in portfolio.allocations:
        effect[a.market] = effect.get(a.market, 0.0) + a.effect_horizon.mode
        cost[a.market] = cost.get(a.market, 0.0) + a.cost_eur
    return [
        {
            "market": market,
            "gap": amount,
            "effect": effect.get(market, 0.0),
            "cost": cost.get(market, 0.0),
            "coverage": (effect.get(market, 0.0) / amount) if amount > 0 else 0.0,
        }
        for market, amount in sorted(gap.items(), key=lambda t: t[1], reverse=True)
    ]


def frontier_rows(points: list[FrontierPoint]) -> list[dict]:
    """Effizienzgrenze im Langformat — beide Wirkungsreihen teilen eine Achse.

    Beide Reihen sind Euro, deshalb dürfen sie in ein Diagramm; der Grenzertrag
    hat eine andere Einheit und bekommt sein eigenes (siehe `marginal_rows`).
    """
    rows: list[dict] = []
    for p in points:
        rows.append({"budget": p.budget_eur, "series": "Im Horizont",
                     "effect": p.effect_horizon_eur, "n": p.n_measures})
        rows.append({"budget": p.budget_eur, "series": "Eingeschwungen p. a.",
                     "effect": p.effect_run_rate_eur, "n": p.n_measures})
    return rows


def marginal_rows(points: list[FrontierPoint]) -> list[dict]:
    """Grenzertrag je zusätzlichem Euro. Eigene Einheit, eigenes Diagramm."""
    rows: list[dict] = []
    for p in points:
        if not p.marginal_return and not p.marginal_return_run_rate:
            continue
        rows.append({"budget": p.budget_eur, "series": "Im Horizont",
                     "marginal": p.marginal_return})
        rows.append({"budget": p.budget_eur, "series": "Eingeschwungen p. a.",
                     "marginal": p.marginal_return_run_rate})
    return rows


def timeline_rows(
    portfolio: Portfolio,
    measures: dict[str, Measure],
    *,
    months: int = 36,
) -> list[dict]:
    """Monatliches Wirkungsniveau des Portfolios, annualisiert.

    Zeigt, was der Horizont abschneidet: die Kurve steigt weit über das hinaus,
    was im Betrachtungszeitraum verdient wird. Genau diese Fläche jenseits der
    Horizontlinie ist das Argument gegen reine Jahresoptimierung.
    """
    rows: list[dict] = []
    for month in range(0, months + 1):
        level = 0.0
        for a in portfolio.allocations:
            measure = measures.get(a.measure_id)
            if measure is None:
                continue
            start = measure.time_to_effect_months
            ramp = max(measure.ramp_months, 0)
            if month <= start:
                factor = 0.0
            elif ramp <= 0 or month >= start + ramp:
                factor = 1.0
            else:
                factor = (month - start) / ramp
            level += a.effect_run_rate.mode * factor
        rows.append({"month": month, "level": level})
    return rows


def outcome_rows(outcomes: list[MeasureOutcome]) -> list[dict]:
    """Erwartungsband gegen eingetretenes Ergebnis."""
    rows: list[dict] = []
    for o in outcomes:
        rows.append({
            "label": f"{o.market} · {o.measure_name}",
            "measure": o.measure_name,
            "market": o.market,
            "expected": o.expected.mode,
            "expected_low": o.expected.low,
            "expected_high": o.expected.high,
            "actual": o.actual_eur,
            "status": o.status,
            "treffer": ("im Band" if o.within_band else "daneben")
                       if o.actual_eur is not None else "offen",
        })
    rows.sort(key=lambda r: r["expected"], reverse=True)
    return rows


def similarity_rows(
    profiles: dict[str, MarketProfile], similarity_fn
) -> list[dict]:
    """Marktähnlichkeit als Matrix — Magnitude, also ein Farbton hell→dunkel."""
    markets = sorted(profiles)
    return [
        {"source": a, "target": b,
         "similarity": similarity_fn(profiles[a], profiles[b])}
        for a in markets
        for b in markets
    ]


def transfer_rows(candidates) -> list[dict]:
    """Transferkandidaten als Punkte über Ähnlichkeit und erwarteter Wirkung."""
    return [
        {
            "label": f"{c.source_market} → {c.target_market}",
            "measure": c.measure_name,
            "source": c.source_market,
            "target": c.target_market,
            "similarity": c.similarity,
            "transferability": c.transferability,
            "expected": c.expected_effect.mode,
            "verdict": c.verdict,
        }
        for c in candidates
    ]


def realization_curve(measures: list[Measure], horizon_months: int) -> list[dict]:
    """Realisierungsanteil je Maßnahme im Horizont — was wann ankommt."""
    return [
        {
            "measure": m.name,
            "instrument": INSTRUMENT_LABELS[m.instrument],
            "time_to_effect": m.time_to_effect_months,
            "realization": realization_fraction(
                m.time_to_effect_months, m.ramp_months, horizon_months
            ),
        }
        for m in sorted(measures, key=lambda m: m.time_to_effect_months)
    ]
