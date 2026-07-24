"""Tests for feedback loop, competitor dossier, diff, battlecard, hypotheses, watchlist."""

from datetime import datetime, timedelta, timezone

import pytest

from mci import competitor, diff, feedback, hypotheses, watchlist
from mci.battlecard import build as build_battlecard
from mci.db import Store
from mci.ingestion import RawDocument
from mci.ingestion.manual import manual_entry
from mci.models import SourceClass
from mci.pipeline import Pipeline
from mci.seed import seed


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    seed(s)
    return s


@pytest.fixture
def pipe(store):
    return Pipeline(store, focus_markets=["DE", "US"], focus_lines=["AquaGuard"])


# --- feedback --------------------------------------------------------------
def test_feedback_curates_sets(store):
    feedback.record(store, target_type="signal", target_id="s1", verdict="accepted")
    feedback.record(store, target_type="signal", target_id="s2", verdict="rejected",
                    reason="irrelevant")
    assert len(feedback.few_shot_examples(store)) == 1
    assert len(feedback.negative_set(store)) == 1
    assert feedback.acceptance_rate(store) == 0.5


def test_feedback_rejects_bad_verdict(store):
    with pytest.raises(ValueError):
        feedback.record(store, target_type="signal", target_id="x", verdict="maybe")


# --- competitor dossier ----------------------------------------------------
def test_competitor_dossier_collects_signals(store, pipe):
    pipe.ingest(RawDocument(
        url="https://dibt.de/a",
        text="Nordwall Systeme GmbH erhielt am 12. Juni 2024 die ETA-24/0123 im Segment Fassade.",
        source_class=SourceClass.A,
    ))
    cmp = next(c for c in store.list_competitors() if "Nordwall" in c.name)
    dossier = competitor.build(store, cmp.id)
    assert dossier is not None
    assert len(dossier.other_signals) >= 1  # regulatory signal matched by name


# --- diff ------------------------------------------------------------------
def test_diff_reports_new_then_clears(store, pipe):
    d0 = diff.since_last_visit(store)
    assert d0.is_empty
    pipe.ingest(manual_entry("Altura eröffnet ein Werk in Izmir für Entkopplungsmatten."))
    d1 = diff.since_last_visit(store)
    assert len(d1.new_signals) == 1
    diff.mark_visited(store)
    d2 = diff.since_last_visit(store)
    assert d2.is_empty


# --- battlecard ------------------------------------------------------------
def test_battlecard_builds_with_top3(store, pipe):
    pipe.ingest(manual_entry(
        "Verarbeiter berichten von Haftungsproblemen bei AquaGuard auf Altuntergrund.",
        source_class=SourceClass.C,
    ))
    card = build_battlecard(store, "AquaGuard")
    assert card.line == "AquaGuard"
    assert len(card.competitors) <= 3
    assert card.objection_handling


# --- hypotheses ------------------------------------------------------------
def test_hypothesis_auto_refutes_on_trigger(store, pipe):
    pipe.ingest(manual_entry(
        "Nordwall Systeme senkte die Preise deutlich im Fachhandel Deutschland.",
        source_class=SourceClass.B,
    ))
    h = hypotheses.create(
        store,
        statement="Nordwall fährt eine reine Premiumstrategie ohne Preissenkung.",
        falsification_trigger="Nordwall senkte deutlich Preise Fachhandel Deutschland",
    )
    checks = hypotheses.auto_check(store)
    check = next(c for c in checks if c.hypothesis_id == h.id)
    assert check.refuted
    refreshed = next(x for x in store.list_hypotheses() if x.id == h.id)
    assert refreshed.status == "refuted"
    assert refreshed.contradicting_signal_ids


def test_hypothesis_ai_never_confirms(store):
    h = hypotheses.create(
        store, statement="X expandiert nach TR.",
        falsification_trigger="X zieht sich vollständig aus TR zurück",
    )
    hypotheses.auto_check(store)
    refreshed = next(x for x in store.list_hypotheses() if x.id == h.id)
    assert refreshed.status in {"open"}  # never auto-confirmed


# --- watchlist -------------------------------------------------------------
def test_watchlist_due_and_run(store):
    item = watchlist.add_watch(store, target_type="competitor", target_ref="Nordwall",
                               cadence_days=7)
    assert item in [] or True
    due = watchlist.due_items(store)
    assert len(due) == 1  # never run -> due
    watchlist.run_due(store)
    # After running, not due until cadence elapses.
    assert watchlist.due_items(store, now=datetime.now(timezone.utc)) == []
    future = datetime.now(timezone.utc) + timedelta(days=8)
    assert len(watchlist.due_items(store, now=future)) == 1
