"""Kern des Wirkungscockpits: Rechenkette, Brücke, Allokation.

Geprüft werden die Zusagen, die das Werkzeug nach außen macht — nicht die
Implementierung. Wenn eine dieser Prüfungen fällt, ist eine Aussage falsch, die
in einer Sitzung getroffen würde.
"""

import pytest

from gtm import demo_data
from gtm.allocate import allocate, frontier
from gtm.bridge import build as build_bridge
from gtm.catalog import MEASURE_CATALOG
from gtm.effects import (
    MIN_DOSE,
    SECONDARY_CAUSE_WEIGHT,
    addressed_gap,
    breakdown,
    realization_fraction,
    saturation,
)
from gtm.models import Band, BridgeStep, CauseCode, EvidenceClass, Measure, PlanFigure


# --------------------------------------------------------------------------
# Sättigung und Realisierung
# --------------------------------------------------------------------------
def test_saturation_is_normalised_and_concave():
    assert saturation(0.0) == 0.0
    assert saturation(1.0) == 1.0
    # Konkav: jede weitere Scheibe bringt weniger als die vorige.
    steps = [saturation(i / 10) for i in range(11)]
    gains = [b - a for a, b in zip(steps, steps[1:])]
    assert all(later <= earlier + 1e-12 for earlier, later in zip(gains, gains[1:]))


def test_measure_slower_than_horizon_yields_nothing():
    """Eine Maßnahme mit 27 Monaten Wirkzeit trägt zur Jahreslücke nichts bei."""
    assert realization_fraction(27, 12, 12) == 0.0
    assert realization_fraction(12, 6, 12) == 0.0


def test_realization_grows_with_horizon_and_never_exceeds_one():
    values = [realization_fraction(3, 4, h) for h in range(4, 60, 4)]
    assert all(b >= a for a, b in zip(values, values[1:]))
    assert all(0.0 <= v <= 1.0 for v in values)


def test_secondary_causes_count_only_half():
    """Eine Maßnahme, die zwei Ursachen streift, darf nicht beide voll für sich
    reklamieren — sonst sähen breite Maßnahmen besser aus als gezielte."""
    measure = Measure(
        name="Test", addresses=[CauseCode.distribution, CauseCode.competitive_loss],
        effect_grade=Band(low=0.1, mode=0.2, high=0.3),
    )
    steps = [
        BridgeStep(market="DE", cause=CauseCode.distribution, amount_eur=1_000_000),
        BridgeStep(market="DE", cause=CauseCode.competitive_loss, amount_eur=1_000_000),
    ]
    total, shares = addressed_gap(measure, steps)
    assert total == pytest.approx(1_000_000 + SECONDARY_CAUSE_WEIGHT * 1_000_000)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_unexplained_residual_is_never_addressable():
    measure = Measure(name="Test", addresses=[CauseCode.distribution],
                      effect_grade=Band(low=0.1, mode=0.2, high=0.3))
    steps = [
        BridgeStep(market="DE", cause=None, amount_eur=500_000),
        BridgeStep(market="DE", cause=CauseCode.distribution, amount_eur=200_000),
    ]
    total, _ = addressed_gap(measure, steps)
    assert total == 200_000


def test_breakdown_chain_reproduces_its_own_result():
    """Die ausgewiesene Kette muss das ausgewiesene Ergebnis ergeben — sonst ist
    die Herleitung Dekoration."""
    measure = next(m for m in MEASURE_CATALOG
                   if m.name == "Konditionensystem nachschärfen")
    steps = [BridgeStep(market="DE", cause=CauseCode.price, amount_eur=2_000_000)]
    detail = breakdown(measure, steps, 1.0, 12, market="DE")
    expected_run_rate = (
        detail.addressed_gap_eur
        * detail.effect_grade.mode
        * detail.saturation
        * detail.evidence_discount
    )
    assert detail.effect_run_rate.mode == pytest.approx(expected_run_rate)
    assert detail.effect_horizon.mode == pytest.approx(
        expected_run_rate * detail.realization
    )


# --------------------------------------------------------------------------
# Brücke
# --------------------------------------------------------------------------
def _demo_bridge(period="FY2026"):
    return build_bridge(demo_data.plan_figures(period),
                        demo_data.attributions(period), period=period)


def test_bridge_closes_exactly():
    """Plan minus alle Stufen muss den Forecast ergeben — sonst lügt der Wasserfall."""
    bridge = _demo_bridge()
    total_steps = sum(s.amount_eur for s in bridge.steps)
    assert total_steps == pytest.approx(bridge.gap_eur)


def test_unexplained_residual_is_kept_not_distributed():
    bridge = _demo_bridge()
    assert bridge.unexplained_eur > 0
    assert bridge.explained_share < 1.0
    assert any(s.is_unexplained for s in bridge.steps)


def test_addressable_excludes_exogenous_and_unexplained():
    bridge = _demo_bridge()
    exogenous = sum(s.amount_eur for s in bridge.steps if s.is_exogenous)
    assert bridge.addressable_eur == pytest.approx(
        bridge.gap_eur - bridge.unexplained_eur - exogenous
    )
    assert bridge.addressable_eur < bridge.gap_eur


def test_over_attribution_is_reported():
    figures = [PlanFigure(market="DE", period="FY2026",
                          plan_eur=1_000_000, forecast_eur=900_000)]
    attributions = [
        BridgeStep(market="DE", period="FY2026",
                   cause=CauseCode.price, amount_eur=250_000),
    ]
    bridge = build_bridge(figures, attributions, period="FY2026")
    assert any("überattribuiert" in w for w in bridge.warnings)


def test_plan_minus_all_causes_equals_forecast():
    """Die Abstimmprobe der Brücke — sie muss auf den Cent aufgehen."""
    bridge = _demo_bridge()
    assert bridge.plan_eur - sum(s.amount_eur for s in bridge.steps) == pytest.approx(
        bridge.forecast_eur
    )


# --------------------------------------------------------------------------
# Allokation
# --------------------------------------------------------------------------
def _demo_portfolio(**kwargs):
    bridge = _demo_bridge()
    params = dict(
        budget_eur=2_500_000, capacity_fte_months=200, horizon_months=12,
        market_factors=demo_data.MARKET_COST_FACTORS, max_measures=12,
    )
    params.update(kwargs)
    return bridge, allocate(bridge, MEASURE_CATALOG, **params)


def test_allocation_respects_budget_and_capacity():
    _, pf = _demo_portfolio(budget_eur=800_000, capacity_fte_months=40)
    assert pf.cost_used_eur <= 800_000 + 1e-6
    assert pf.capacity_used <= 40 + 1e-6


def test_allocation_respects_the_attention_limit():
    _, pf = _demo_portfolio(max_measures=5)
    assert len(pf.allocations) <= 5


def test_no_measure_runs_below_the_minimum_dose():
    """Alibi-Maßnahmen mit 5 % Einsatz existieren nur im Plan, nicht in der Welt."""
    _, pf = _demo_portfolio()
    assert all(a.dose >= MIN_DOSE - 1e-9 for a in pf.allocations)


def test_every_funded_measure_pays_for_itself():
    """Keine Maßnahme im Paket darf weniger zurückholen, als sie kostet."""
    _, pf = _demo_portfolio()
    for a in pf.allocations:
        assert a.effect_run_rate.mode >= a.cost_eur - 1e-6, a.measure_name


def test_effect_never_exceeds_the_addressable_gap():
    """Der Ursachendeckel: Maßnahmen können nicht mehr zurückholen, als die
    Ursachen an Lücke hergeben."""
    bridge, pf = _demo_portfolio(budget_eur=20_000_000, capacity_fte_months=10_000,
                                 max_measures=60)
    assert pf.effect_run_rate.mode <= bridge.addressable_eur + 1.0


def test_slow_measures_are_excluded_and_named():
    _, pf = _demo_portfolio(horizon_months=12)
    assert "Spezifikationsarbeit bei Planern" in pf.too_slow
    assert all(a.measure_name not in pf.too_slow for a in pf.allocations)


def test_longer_horizon_admits_the_slow_measures():
    _, short = _demo_portfolio(horizon_months=12)
    _, long = _demo_portfolio(horizon_months=36)
    assert len(long.too_slow) < len(short.too_slow)


def test_bands_are_ordered_and_never_points():
    _, pf = _demo_portfolio()
    assert pf.effect_horizon.low <= pf.effect_horizon.mode <= pf.effect_horizon.high
    assert not pf.effect_horizon.is_point
    for a in pf.allocations:
        assert a.effect_horizon.low <= a.effect_horizon.mode <= a.effect_horizon.high


def test_residual_gap_is_never_negative():
    _, pf = _demo_portfolio(budget_eur=50_000_000, max_measures=60)
    assert pf.residual_gap_eur >= 0.0


def test_more_budget_never_reduces_effect():
    bridge = _demo_bridge()
    points = frontier(
        bridge, MEASURE_CATALOG,
        budgets=[250_000, 500_000, 1_000_000, 2_000_000, 4_000_000],
        capacity_fte_months=200, horizon_months=12,
        market_factors=demo_data.MARKET_COST_FACTORS, max_measures=12,
    )
    effects = [p.effect_horizon_eur for p in points]
    assert all(b >= a - 1e-6 for a, b in zip(effects, effects[1:]))


def test_marginal_return_declines():
    bridge = _demo_bridge()
    points = frontier(
        bridge, MEASURE_CATALOG,
        budgets=[250_000, 500_000, 750_000, 1_000_000, 1_500_000, 2_500_000],
        capacity_fte_months=200, horizon_months=12,
        market_factors=demo_data.MARKET_COST_FACTORS, max_measures=12,
    )
    marginals = [p.marginal_return for p in points if p.marginal_return]
    assert all(b <= a + 1e-9 for a, b in zip(marginals, marginals[1:]))


def test_capacity_binding_is_reported_as_such():
    """Bei Kapazitätsbindung hilft mehr Geld nicht — das muss dastehen."""
    _, pf = _demo_portfolio(budget_eur=5_000_000, capacity_fte_months=20)
    assert any("Kapazität" in w for w in pf.warnings)


def test_zero_budget_yields_an_empty_but_valid_portfolio():
    _, pf = _demo_portfolio(budget_eur=0)
    assert pf.allocations == []
    assert pf.effect_horizon.mode == 0.0
    assert pf.residual_gap_eur == pytest.approx(pf.gap_eur)


def test_assumed_evidence_is_discounted():
    """Zwei identische Maßnahmen, nur die Evidenzklasse unterscheidet sie."""
    steps = [BridgeStep(market="DE", cause=CauseCode.price, amount_eur=1_000_000)]
    grade = Band(low=0.1, mode=0.2, high=0.3)
    measured = Measure(name="A", addresses=[CauseCode.price], effect_grade=grade,
                       evidence_class=EvidenceClass.measured,
                       time_to_effect_months=1, ramp_months=1)
    assumed = Measure(name="B", addresses=[CauseCode.price], effect_grade=grade,
                      evidence_class=EvidenceClass.assumed,
                      time_to_effect_months=1, ramp_months=1)
    a = breakdown(measured, steps, 1.0, 12)
    b = breakdown(assumed, steps, 1.0, 12)
    assert b.effect_run_rate.mode < a.effect_run_rate.mode
