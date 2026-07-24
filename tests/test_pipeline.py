"""End-to-end pipeline tests (offline, no API key)."""

import pytest

from mci.db import Store
from mci.ingestion import RawDocument, classify_source
from mci.ingestion.manual import manual_entry
from mci.models import SignalStatus, SourceClass
from mci.pipeline import Pipeline


@pytest.fixture
def pipe(tmp_path):
    store = Store(tmp_path / "t.db")
    return Pipeline(store, focus_markets=["DE", "US"], focus_lines=["AquaGuard"])


def _eta_doc(url: str, suffix: str = "") -> RawDocument:
    return RawDocument(
        url=url,
        text=(
            "Nordwall Systeme GmbH erhielt am 12. Juni 2024 die Europäische "
            "Technische Bewertung ETA-24/0123 für ein Verbundabdichtungssystem "
            "im Segment Fassade für den Markt DE." + suffix
        ),
        title="ETA",
        source_class=SourceClass.A,
    )


def test_created_signal_has_evidence_and_scores(pipe):
    res = pipe.ingest(_eta_doc("https://dibt.de/a"))
    assert res.ok and res.action == "created"
    sig = res.signal
    assert sig.evidence_ids, "signal must carry evidence"
    assert sig.audit_passed
    assert 0.0 <= sig.confidence <= 1.0
    assert sig.priority > 0
    assert sig.prompt_version and sig.model_id == "offline-heuristic"
    assert "DE" in sig.entities.markets  # relevanz-mapping fired


def test_hedged_fact_is_rejected(pipe):
    doc = RawDocument(
        url="https://blog.example/x",
        text="Severn dürfte wahrscheinlich bald die Preise senken, vermutlich aggressiv.",
        source_class=SourceClass.D,
    )
    res = pipe.ingest(doc)
    assert not res.ok and res.action == "rejected"
    assert any("hedge" in v for v in res.violations)


def test_second_independent_source_triangulates_to_confirmed(pipe):
    r1 = pipe.ingest(_eta_doc("https://dibt.de/a"))
    assert r1.signal.status == SignalStatus.unconfirmed
    # Second, independently-worded source stating the same fact.
    r2 = pipe.ingest(_eta_doc("https://fachpresse.example/b", suffix=" Meldung laut Fachpresse."))
    assert r2.action == "triangulated"
    assert r2.signal.status == SignalStatus.confirmed
    assert r2.signal.confidence > r1.signal.confidence


def test_same_source_again_is_duplicate_not_new(pipe):
    pipe.ingest(_eta_doc("https://dibt.de/a"))
    res = pipe.ingest(_eta_doc("https://dibt.de/a"))
    assert res.action == "duplicate"
    # only one signal exists
    assert len(pipe.store.list_signals()) == 1


def test_manual_channel_is_ingested(pipe):
    note = manual_entry("Altura eröffnet ein neues Werk in Izmir für Entkopplungsmatten.")
    res = pipe.ingest(note)
    assert res.ok and res.signal is not None


def test_classify_source_rules():
    assert classify_source("https://www.dibt.de/x") == SourceClass.A
    assert classify_source("https://www.linkedin.com/y") == SourceClass.C
    assert classify_source("https://unknown.example/z") == SourceClass.C
