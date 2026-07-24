"""E8 scenario module tests (spec §6)."""

import pytest

from mci.db import Store
from mci.scenario import (
    Assumption,
    ReferenceCase,
    Scenario,
    run_simulation,
    verdict_for,
)
from mci.scenario.engine import build_packages
from mci.scenario.models import AssumptionClass, CompetitorResponse, Distribution
from mci.scenario.store import ScenarioStore


def _assumption(driver, baseline, low, mode, high, klass=AssumptionClass.analog):
    return Assumption(
        driver_node=driver, baseline=baseline, value=mode,
        distribution=Distribution(type="triangular", low=low, mode=mode, high=high),
        klasse=klass,
    )


def _scenario(target=2.0):
    return Scenario(target_metric="market_share_pp", target_value=target,
                    market="DE", horizon_months=24, mode="inverse")


def test_simulation_produces_band_not_point():
    scn = _scenario()
    asmp = [
        _assumption("distributionsgrad", 0.60, 0.60, 0.65, 0.70),
        _assumption("listungstiefe", 0.34, 0.34, 0.40, 0.46),
        _assumption("abverkaufsrate", 0.50, 0.48, 0.50, 0.52),
        _assumption("preisniveau", 0.90, 0.88, 0.90, 0.92),
    ]
    sim = run_simulation(scn, asmp, seed=1,
                         competitor_response=CompetitorResponse(modeled=True,
                                                                net_effect_adjustment=-0.3))
    lo, hi = sim.outcome_band_80
    assert lo <= sim.outcome_median <= hi
    assert 0.0 <= sim.p_target_hit <= 1.0
    assert sim.sensitivity  # tornado present
    assert len(sim.critical_assumptions) <= 3


def test_unmodeled_competitor_response_flags_incomplete():
    scn = _scenario()
    asmp = [_assumption("listungstiefe", 0.34, 0.34, 0.40, 0.46)]
    sim = run_simulation(scn, asmp, seed=1)  # no competitor response
    assert sim.incomplete is True


def test_verdict_rules_reference_class():
    # required movement far above best observed -> unplausibel
    assert verdict_for(2.0, 0.5) == "unplausibel ohne Strukturbruch"
    assert verdict_for(1.2, 0.5) == "ambitioniert"
    assert verdict_for(0.5, 0.8) == "plausibel"


def test_reference_class_extrapolation_warning():
    scn = _scenario()
    # requires listungstiefe +18pp; best observed 6pp -> factor 3 -> unplausibel
    asmp = [_assumption("listungstiefe", 0.34, 0.34, 0.52, 0.52)]
    refs = [ReferenceCase(driver="listungstiefe", observed_delta=0.06,
                          description="beste je beobachtete Jahresbewegung")]
    sim = run_simulation(scn, asmp, seed=1, reference_cases=refs,
                         competitor_response=CompetitorResponse(modeled=True))
    assert sim.extrapolation_warnings
    assert sim.verdict == "unplausibel ohne Strukturbruch"


def test_denominator_warning_for_assumed_volume():
    scn = _scenario()
    asmp = [
        _assumption("marktvolumen", 0.5, 0.4, 0.5, 0.6, klass=AssumptionClass.assumed),
        _assumption("listungstiefe", 0.34, 0.34, 0.40, 0.46),
    ]
    sim = run_simulation(scn, asmp, seed=1,
                         competitor_response=CompetitorResponse(modeled=True))
    assert "Nennerwarnung" in sim.denominator_warning


def test_build_packages_and_persist(tmp_path):
    store = Store(tmp_path / "t.db")
    ss = ScenarioStore(store)
    scn = ss.save_scenario(_scenario())
    pkgs = [
        {"label": "Kanaloffensive", "lever_set": ["listungstiefe"],
         "competitor_response": CompetitorResponse(modeled=True, net_effect_adjustment=-0.2),
         "assumptions": [_assumption("listungstiefe", 0.34, 0.34, 0.40, 0.46),
                         _assumption("distributionsgrad", 0.6, 0.6, 0.66, 0.7)]},
    ]
    sims = build_packages(scn, pkgs, seed=7)
    assert len(sims) == 1
    ss.save_simulation(sims[0])
    assert ss.list_simulations(scn.id)


def test_nachhaltemodus_optimism_bias(tmp_path):
    store = Store(tmp_path / "t.db")
    ss = ScenarioStore(store)
    scn = ss.save_scenario(_scenario())
    asmp = [_assumption("listungstiefe", 0.34, 0.34, 0.40, 0.46)]
    sim = run_simulation(scn, asmp, seed=1,
                         competitor_response=CompetitorResponse(modeled=True))
    ss.save_simulation(sim)
    # actual came in below the predicted median -> negative deviation (optimism)
    ss.record_outcome(scn.id, actual_value=sim.outcome_median - 0.5)
    bias = ss.optimism_bias()
    assert bias is not None and bias < 0
