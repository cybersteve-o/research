"""Tests for the rich demo corpus and the chart data shaping."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mci import chartdata, demo_data
from mci.db import Store
from mci.ingestion.manual import manual_entry
from mci.models import SignalStatus, SourceClass
from mci.pipeline import Pipeline
from mci.seed import FOCUS_LINES, FOCUS_MARKETS, seed


def _loaded_store() -> Store:
    store = Store(Path(tempfile.mkdtemp()) / "demo.db")
    seed(store)
    pipe = Pipeline(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    for doc in demo_data.documents():
        pipe.ingest(doc)
    for note in demo_data.manual_notes():
        pipe.ingest(manual_entry(note, source_class=SourceClass.C))
    return store


def test_demo_corpus_fills_the_store():
    store = _loaded_store()
    signals = store.list_signals()
    assert len(signals) >= 20, "demo should produce a substantial picture"
    assert any(s.status == SignalStatus.confirmed for s in signals), "triangulation"


def test_guardrails_reject_the_hedged_samples():
    """The two hedged documents must be rejected, not stored as facts."""
    store = Store(Path(tempfile.mkdtemp()) / "g.db")
    seed(store)
    pipe = Pipeline(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    rejected = [d for d in demo_data.documents() if not pipe.ingest(d).ok]
    assert len(rejected) >= 2
    assert all("dürfte" in d.text or "vermutlich" in d.text for d in rejected)


def test_competitors_are_resolved_from_text():
    """Entity resolution must attach tracked competitors, else every
    competitor-scoped view (dossier, cadence, SWOT, sentiment) stays empty."""
    store = _loaded_store()
    named = [s for s in store.list_signals() if s.entities.competitors]
    assert len(named) >= 10
    all_names = {n for s in named for n in s.entities.competitors}
    assert "Nordwall Systeme GmbH" in all_names
    assert "Altura Building Products" in all_names


def test_chart_rows_are_populated_and_well_formed():
    store = _loaded_store()
    sent = chartdata.sentiment_rows(store)
    assert sent and {"brand", "score", "n"} <= set(sent[0])

    trend = chartdata.trend_rows(store)
    assert trend and {"term", "count", "momentum"} <= set(trend[0])

    tl = chartdata.timeline_rows(store)
    assert tl and {"entity", "date", "type", "priority"} <= set(tl[0])

    matrix = chartdata.matrix_rows(store)
    assert matrix and {"entity", "kind", "count"} <= set(matrix[0])

    vol = chartdata.volume_rows(store)
    assert vol and {"period", "status", "count"} <= set(vol[0])


def test_charts_use_event_time_not_import_time():
    """Charts must spread over real time; a batch import must not collapse
    every point onto today."""
    store = _loaded_store()
    periods = {r["period"] for r in chartdata.volume_rows(store)}
    assert len(periods) >= 6, f"expected a multi-month spread, got {periods}"


def test_chart_builders_handle_empty_input():
    from mci import charts
    assert charts.sentiment_bars([]) is None
    assert charts.trend_momentum([]) is None
    assert charts.spec_share_lines([]) is None
    assert charts.activity_timeline([]) is None
    assert charts.activity_matrix([]) is None
    assert charts.signals_over_time([]) is None


def test_chart_builders_produce_charts():
    from mci import charts
    store = _loaded_store()
    assert charts.sentiment_bars(chartdata.sentiment_rows(store)) is not None
    assert charts.trend_momentum(chartdata.trend_rows(store)) is not None
    assert charts.activity_timeline(chartdata.timeline_rows(store)) is not None
    assert charts.activity_matrix(chartdata.matrix_rows(store)) is not None
    assert charts.signals_over_time(chartdata.volume_rows(store)) is not None
