"""Tests for cadence, gap matrix, correlation rules, country profile, spec-share."""

from datetime import datetime, timezone

import pytest

from mci import cadence, correlation, country, portfolio, specshare
from mci.db import Store
from mci.ingestion import RawDocument
from mci.ingestion.manual import manual_entry
from mci.models import OwnerType, Product, SourceClass
from mci.pipeline import Pipeline
from mci.seed import seed


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    seed(s)
    return s


# --- cadence ---------------------------------------------------------------
def test_cadence_insufficient_below_three():
    p = cadence.predict_from_dates("X", "launch", [
        datetime(2022, 1, 1, tzinfo=timezone.utc),
        datetime(2023, 1, 1, tzinfo=timezone.utc),
    ])
    assert p.status == "insufficient" and p.next_window is None


def test_cadence_predicts_window_and_confidence():
    dates = [datetime(y, 1, 1, tzinfo=timezone.utc) for y in (2020, 2021, 2022, 2023)]
    p = cadence.predict_from_dates("X", "launch", dates)
    assert p.status == "ok"
    assert p.mean_interval_days == pytest.approx(365.25, abs=1.5)
    assert p.next_window is not None
    lo, hi = p.next_window
    assert lo <= hi
    assert p.confidence > 0.0  # regular cadence -> some confidence


# --- gap matrix ------------------------------------------------------------
def test_gap_matrix_detects_gap_and_whitespace(store):
    # Own has AquaGuard (Verbundabdichtung); add a competitor product in a new app.
    store.upsert_product(Product(owner_type=OwnerType.competitor, line="RivalX",
                                 application="Sockelabdichtung", status="active"))
    cells = {c.application: c for c in portfolio.gap_matrix(store)}
    assert cells["Sockelabdichtung"].status == "gap"  # only competitor
    assert cells["Verbundabdichtung"].status == "whitespace"  # only own


# --- correlation rules -----------------------------------------------------
def test_correlation_r1_launch_likelihood(store):
    pipe = Pipeline(store)
    nordwall = "Nordwall Systeme"
    pipe.ingest(manual_entry(f"{nordwall} erhielt die ETA-24/0123 Zulassung im Segment Fassade.",
                             source_class=SourceClass.A))
    pipe.ingest(manual_entry(f"{nordwall} sucht Prozessingenieur für neues Werk.",
                             source_class=SourceClass.C))
    pipe.ingest(manual_entry(f"{nordwall} meldet hohe Capex für Werkserweiterung am Standort.",
                             source_class=SourceClass.A))
    insights = {i.rule_id for i in correlation.evaluate(store)}
    assert "R1" in insights


def test_correlation_r2_price_offensive(store):
    pipe = Pipeline(store)
    pipe.ingest(manual_entry("Severn Systems Bruttomarge sank deutlich im Quartal.",
                             source_class=SourceClass.A))
    pipe.ingest(manual_entry("Severn Systems meldet Capex für Kapazitätsaufbau am Standort.",
                             source_class=SourceClass.A))
    insights = {i.rule_id for i in correlation.evaluate(store)}
    assert "R2" in insights


# --- country profile -------------------------------------------------------
def test_country_profile_assembles(store):
    prof = country.build(store, "DE")
    assert prof.country == "DE"
    assert prof.competitor_density >= 1  # Nordwall is DE
    assert "Fachhandel" in prof.channel_structure


# --- spec-share ------------------------------------------------------------
def test_spec_share_counts_named_mentions(store):
    pipe = Pipeline(store)
    pipe.ingest(RawDocument(
        url="https://tender.example/1",
        text="In der Ausschreibung wurde das System von Nordwall namentlich vorgeschrieben.",
        source_class=SourceClass.B,
    ))
    timeline = specshare.spec_share_timeline(store)
    assert any("Nordwall" in entity for entity in timeline)
