"""Der Weg durch das Cockpit: Forecast einlesen, koppeln, nachhalten, exportieren."""

from types import SimpleNamespace

import pytest

from gtm import chartdata, demo_data
from gtm.allocate import allocate
from gtm.bridge import build as build_bridge
from gtm.catalog import MEASURE_CATALOG
from gtm.export import allocations_csv, bridge_csv, decision_one_pager
from gtm.forecast import (
    ForecastFormatError,
    attributions_from_rows,
    from_csv,
    from_rows,
    validate,
)
from gtm.link import causes_for_signal, evidence_summary, open_gaps
from gtm.llm.roles import GtmRoles
from gtm.models import Band, BridgeStep, CauseCode, MeasureOutcome, PlanFigure
from gtm.playbook import similarity, transfer_candidates
from gtm.store import Store
from gtm.tracking import calibration, expectations_from, hit_rate, optimism_bias
from gtm.tracking import report as track_report


def _bridge():
    return build_bridge(demo_data.plan_figures(), demo_data.attributions(),
                        period="FY2026")


def _portfolio(bridge=None):
    bridge = bridge or _bridge()
    return allocate(
        bridge, MEASURE_CATALOG, budget_eur=2_500_000,
        capacity_fte_months=200, horizon_months=12,
        market_factors=demo_data.MARKET_COST_FACTORS, max_measures=12,
    )


# --------------------------------------------------------------------------
# Forecast-Schnittstelle
# --------------------------------------------------------------------------
def test_german_number_format_is_understood():
    result = from_rows([{
        "market": "DE", "line": "Abdichtung", "period": "FY2026",
        "plan_eur": "14.000.000,50", "forecast_eur": "13.200.000",
    }])
    assert result.figures[0].plan_eur == pytest.approx(14_000_000.50)
    assert result.figures[0].gap_eur == pytest.approx(800_000.50)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1.000.000", 1_000_000.0),      # deutscher Tausenderpunkt, mehrfach
        ("1.000", 1_000.0),              # einmal, drei Ziffern -> Tausender
        ("1,50", 1.5),                   # deutsches Dezimalkomma
        ("1,234,567.89", 1_234_567.89),  # englische Schreibweise
        ("1.234.567,89", 1_234_567.89),  # deutsche Schreibweise
        ("14 000 000 €", 14_000_000.0),  # Leerzeichen und Währungszeichen
        ("-250.000", -250_000.0),        # negativ
        (1_500_000, 1_500_000.0),        # schon numerisch
    ],
)
def test_number_formats(raw, expected):
    result = from_rows([{"market": "DE", "period": "FY2026",
                         "plan_eur": raw, "forecast_eur": "0"}])
    assert result.figures[0].plan_eur == pytest.approx(expected)


def test_missing_mandatory_column_fails_loudly():
    with pytest.raises(ForecastFormatError) as exc:
        from_rows([{"market": "DE", "plan_eur": 1, "forecast_eur": 1}])
    assert "period" in str(exc.value)


def test_non_numeric_value_names_the_row_and_column():
    with pytest.raises(ForecastFormatError) as exc:
        from_rows([{"market": "DE", "period": "FY2026",
                    "plan_eur": "keine Zahl", "forecast_eur": "1"}])
    assert "plan_eur" in str(exc.value)


def test_duplicate_rows_are_flagged_because_they_double_the_gap():
    row = {"market": "DE", "line": "Abdichtung", "period": "FY2026",
           "plan_eur": "1000", "forecast_eur": "900"}
    result = from_rows([dict(row), dict(row)])
    assert any("Doppelte Zeile" in w for w in result.warnings)


def test_huge_gap_is_called_a_plan_revision():
    warnings = validate([PlanFigure(market="DE", period="FY2026",
                                    plan_eur=1_000_000, forecast_eur=200_000)])
    assert any("Planrevision" in w for w in warnings)


def test_csv_is_read_with_either_delimiter(tmp_path):
    path = tmp_path / "forecast.csv"
    path.write_text(
        "market;line;period;plan_eur;forecast_eur\n"
        "DE;Abdichtung;FY2026;1.000.000;900.000\n",
        encoding="utf-8",
    )
    result = from_csv(path)
    assert len(result.figures) == 1
    assert result.figures[0].source == "csv"


def test_unknown_cause_code_is_rejected():
    with pytest.raises(ForecastFormatError) as exc:
        attributions_from_rows([{"market": "DE", "cause": "erfunden",
                                 "amount_eur": "1000"}])
    assert "unbekannte Ursache" in str(exc.value)


# --------------------------------------------------------------------------
# Kopplung an die Recherche
# --------------------------------------------------------------------------
def _signal(headline="", fact="", stype="other", confidence=0.5, status="confirmed"):
    return SimpleNamespace(
        id="sig_1", headline=headline, fact=fact, derivation="",
        type=SimpleNamespace(value=stype), confidence=confidence,
        status=SimpleNamespace(value=status), priority=0.5,
        entities=SimpleNamespace(markets=["DE"]),
    )


def test_signal_type_and_keywords_both_map_to_causes():
    by_type = causes_for_signal(_signal(stype="channel"))
    assert CauseCode.distribution in by_type

    by_keyword = causes_for_signal(
        _signal(fact="Der Händler hat die Listung reduziert.", stype="other")
    )
    assert CauseCode.distribution in by_keyword


def test_steps_without_signals_stay_unproven_not_deleted():
    bridge = _bridge()
    # Ohne MCI-Speicher bleibt jede Konfidenz null — die Beträge aber stehen.
    assert all(s.confidence == 0.0 for s in bridge.steps)
    assert bridge.gap_eur > 0
    summary = evidence_summary(bridge)
    assert summary["unbelegt"] > 0


def test_open_gaps_surface_large_but_unproven_causes():
    bridge = _bridge()
    gaps = open_gaps(bridge, min_amount_eur=1_000_000, max_confidence=0.4)
    assert gaps
    assert gaps[0].amount_eur >= gaps[-1].amount_eur
    assert "belegen" in gaps[0].research_question()


# --------------------------------------------------------------------------
# Nachhalten
# --------------------------------------------------------------------------
def _outcome(expected_mode, actual, low=None, high=None, measure_id="m1"):
    low = low if low is not None else expected_mode * 0.8
    high = high if high is not None else expected_mode * 1.2
    outcome = MeasureOutcome(
        measure_id=measure_id, measure_name="Test", market="DE",
        expected=Band(low=low, mode=expected_mode, high=high),
    )
    if actual is not None:
        outcome.actual_eur = actual
        outcome.status = "gemessen"
    return outcome


def test_open_measures_never_count_as_hits():
    outcomes = [_outcome(100, 100), _outcome(100, None)]
    assert hit_rate(outcomes) == 1.0  # nur der gemessene Fall zählt
    report = track_report(outcomes)
    assert report.n_open == 1
    assert report.n_measured == 1


def test_optimism_bias_is_positive_when_results_disappoint():
    outcomes = [_outcome(100, 60), _outcome(200, 120)]
    assert optimism_bias(outcomes) == pytest.approx(0.4)


def test_optimism_bias_is_negative_when_results_beat_expectations():
    assert optimism_bias([_outcome(100, 130)]) < 0


def test_calibration_stays_silent_below_the_minimum_case_count():
    from gtm.models import EvidenceClass
    outcomes = [_outcome(100, 50, measure_id="m1")]
    rows = calibration(outcomes, {"m1": EvidenceClass.assumed})
    assumed = next(r for r in rows if r.evidence_class is EvidenceClass.assumed)
    assert assumed.suggested_discount is None
    assert "Zu wenige Fälle" in assumed.note


def test_calibration_tightens_a_discount_that_was_too_mild():
    from gtm.models import EvidenceClass
    outcomes = [_outcome(100, 30, measure_id=f"m{i}") for i in range(4)]
    evidence = {f"m{i}": EvidenceClass.assumed for i in range(4)}
    rows = calibration(outcomes, evidence)
    assumed = next(r for r in rows if r.evidence_class is EvidenceClass.assumed)
    assert assumed.suggested_discount < assumed.current_discount
    assert "zu milde" in assumed.note


def test_expectations_are_frozen_from_the_portfolio():
    pf = _portfolio()
    frozen = expectations_from(pf, owner="Demo")
    assert len(frozen) == len(pf.allocations)
    assert all(o.status == "offen" and o.actual_eur is None for o in frozen)
    assert frozen[0].expected.mode == pf.allocations[0].effect_horizon.mode


def test_demo_history_shows_the_bias_follows_evidence_not_department():
    """Die unbequeme Aussage des Korpus: die Schlagseite hängt an der
    Evidenzklasse, nicht an der Abteilung."""
    from gtm.models import EvidenceClass
    outcomes = demo_data.historical_outcomes()
    rows = calibration(outcomes, demo_data.evidence_map())
    measured = next(r for r in rows if r.evidence_class is EvidenceClass.measured)
    assumed = next(r for r in rows if r.evidence_class is EvidenceClass.assumed)
    assert measured.mean_ratio > assumed.mean_ratio


# --------------------------------------------------------------------------
# Playbook-Transfer
# --------------------------------------------------------------------------
def test_similarity_is_symmetric_and_self_is_one():
    profiles = demo_data.market_profiles()
    assert similarity(profiles["DE"], profiles["DE"]) == 1.0
    assert similarity(profiles["DE"], profiles["PL"]) == pytest.approx(
        similarity(profiles["PL"], profiles["DE"])
    )


def test_transferability_never_exceeds_similarity():
    profiles = demo_data.market_profiles()
    for cand in transfer_candidates(demo_data.historical_outcomes(), profiles):
        assert cand.transferability <= cand.similarity + 1e-9


def test_distant_markets_come_with_written_objections():
    profiles = demo_data.market_profiles()
    candidates = transfer_candidates(demo_data.historical_outcomes(), profiles)
    distant = [c for c in candidates if c.similarity < 0.7]
    assert distant
    assert all(c.caveats for c in distant)


def test_unmeasured_outcomes_are_not_transferred():
    profiles = demo_data.market_profiles()
    outcomes = [_outcome(100_000, None)]
    assert transfer_candidates(outcomes, profiles) == []


# --------------------------------------------------------------------------
# Rollen
# --------------------------------------------------------------------------
def test_critique_is_produced_offline_and_names_concentration():
    bridge = _bridge()
    pf = _portfolio(bridge)
    roles = GtmRoles(backend=None)
    critique = roles.challenge(pf, bridge)
    assert critique.source == "offline-heuristic"
    assert critique.counter_argument
    assert critique.blind_spots


def test_rationale_states_what_the_package_does_not_do():
    bridge = _bridge()
    pf = _portfolio(bridge)
    text = GtmRoles(backend=None).rationale(pf, bridge)
    assert "schließt die Lücke nicht" in text


def test_diagnosis_marks_unproven_steps_as_such():
    bridge = _bridge()
    hypotheses = GtmRoles(backend=None).diagnose(bridge, store=None)
    assert hypotheses
    assert all(not h.supported for h in hypotheses)  # ohne Speicher kein Beleg


# --------------------------------------------------------------------------
# Diagrammdaten und Export
# --------------------------------------------------------------------------
def test_waterfall_builds_the_gap_from_zero():
    """Der Wasserfall baut die Lücke auf, statt sie vom Umsatz abzuziehen —
    sonst sind die Ursachen auf der Achse nicht mehr zu erkennen."""
    bridge = _bridge()
    rows = chartdata.waterfall_rows(bridge)
    steps = [r for r in rows if r["role"] != "Summe"]
    assert steps[0]["start"] == 0.0
    for earlier, later in zip(steps, steps[1:]):
        assert earlier["end"] == pytest.approx(later["start"])
    assert steps[-1]["end"] == pytest.approx(bridge.gap_eur)
    assert rows[-1]["label"] == "Lücke gesamt"


def test_timeline_never_decreases():
    pf = _portfolio()
    measures = {m.id: m for m in MEASURE_CATALOG}
    levels = [r["level"] for r in chartdata.timeline_rows(pf, measures, months=36)]
    assert all(b >= a - 1e-6 for a, b in zip(levels, levels[1:]))
    assert levels[-1] >= levels[0]


def test_one_pager_carries_the_bad_news_too():
    bridge = _bridge()
    pf = _portfolio(bridge)
    roles = GtmRoles(backend=None)
    text = decision_one_pager(pf, bridge, rationale=roles.rationale(pf, bridge),
                              critique=roles.challenge(pf, bridge))
    assert "Gegenrede" in text
    assert "Rechercheaufträge" in text
    assert "adressierbar" in text
    assert "Kein Wert stammt aus einem Sprachmodell" in text


def test_csv_exports_have_one_row_per_item():
    bridge = _bridge()
    pf = _portfolio(bridge)
    assert len(allocations_csv(pf).strip().splitlines()) == len(pf.allocations) + 1
    assert len(bridge_csv(bridge).strip().splitlines()) == len(bridge.steps) + 1


# --------------------------------------------------------------------------
# Speicher
# --------------------------------------------------------------------------
def test_store_roundtrip(tmp_path):
    with Store(tmp_path / "gtm.db") as store:
        assert store.is_empty()
        demo_data.seed(store)
        assert not store.is_empty()
        assert len(store.list_plan_figures("FY2026")) == 15
        assert store.get_meta("seeded") == "demo"

        pf = _portfolio()
        store.save_portfolio(pf)
        loaded = store.get_portfolio(pf.id)
        assert loaded is not None
        assert len(loaded.allocations) == len(pf.allocations)
        assert loaded.effect_horizon.mode == pytest.approx(pf.effect_horizon.mode)


def test_replacing_a_forecast_run_does_not_stack_rows(tmp_path):
    with Store(tmp_path / "gtm.db") as store:
        store.replace_plan_figures(demo_data.plan_figures(), "FY2026")
        store.replace_plan_figures(demo_data.plan_figures(), "FY2026")
        assert len(store.list_plan_figures("FY2026")) == 15


# --------------------------------------------------------------------------
# Diagramme
# --------------------------------------------------------------------------
altair = pytest.importorskip("altair", reason="Altair kommt mit dem UI-Extra")


def test_every_chart_builder_produces_something():
    from gtm import charts
    from gtm.allocate import frontier
    from gtm.playbook import similarity as sim

    bridge = _bridge()
    pf = _portfolio(bridge)
    measures = {m.id: m for m in MEASURE_CATALOG}
    outcomes = demo_data.historical_outcomes()
    points = frontier(bridge, MEASURE_CATALOG,
                      budgets=[500_000, 1_000_000, 2_500_000],
                      capacity_fte_months=200, horizon_months=12,
                      market_factors=demo_data.MARKET_COST_FACTORS,
                      max_measures=12)

    assert charts.bridge_waterfall(chartdata.waterfall_rows(bridge)) is not None
    assert charts.evidence_stack(chartdata.evidence_rows(bridge)) is not None
    assert charts.measure_bars(chartdata.measure_rows(pf)) is not None
    assert charts.frontier_lines(chartdata.frontier_rows(points)) is not None
    assert charts.marginal_lines(chartdata.marginal_rows(points)) is not None
    assert charts.effect_timeline(
        chartdata.timeline_rows(pf, measures, months=36), 12) is not None
    assert charts.market_coverage(chartdata.market_rows(pf, bridge)) is not None
    assert charts.outcome_dots(chartdata.outcome_rows(outcomes)) is not None
    assert charts.similarity_matrix(
        chartdata.similarity_rows(demo_data.market_profiles(), sim)) is not None
    assert charts.realization_bars(
        chartdata.realization_curve(MEASURE_CATALOG, 12)) is not None


def test_charts_return_none_instead_of_drawing_empty_frames():
    from gtm import charts

    assert charts.bridge_waterfall([]) is None
    assert charts.measure_bars([]) is None
    assert charts.outcome_dots([{"label": "x", "actual": None, "expected": 1,
                                 "expected_low": 0, "expected_high": 2,
                                 "status": "offen", "treffer": "offen"}]) is None


# --------------------------------------------------------------------------
# Rauchtest
# --------------------------------------------------------------------------
def test_demo_runs_end_to_end(capsys):
    from gtm.demo import main

    main()
    out = capsys.readouterr().out
    assert "Lückenbild" in out
    assert "Maßnahmenportfolio" in out
    assert "Nachhalten" in out
    assert "Playbook-Transfer" in out
