"""Cluster-synthesis tests (spec §5.4)."""

import pytest

from mci.context import ContextStore
from mci.db import Store
from mci.decisions import enforce_structure
from mci.ingestion import RawDocument
from mci.models import SourceClass
from mci.pipeline import Pipeline
from mci.synthesis import Synthesizer


@pytest.fixture
def store_with_signals(tmp_path):
    store = Store(tmp_path / "t.db")
    pipe = Pipeline(store, focus_markets=["DE", "US"], focus_lines=["AquaGuard"])
    # A confirmed regulatory signal (E2,E6) via two independent sources.
    base = (
        "Nordwall Systeme GmbH erhielt am 12. Juni 2024 die Europäische "
        "Technische Bewertung ETA-24/0123 für ein Verbundabdichtungssystem "
        "im Segment Fassade für den Markt DE."
    )
    pipe.ingest(RawDocument(url="https://dibt.de/a", text=base, source_class=SourceClass.A))
    pipe.ingest(RawDocument(url="https://fp.example/b", text=base + " Meldung laut Fachpresse.",
                            source_class=SourceClass.A))
    # A hiring signal (E4,E6).
    pipe.ingest(RawDocument(
        url="https://careers.altura.example/j",
        text="Altura Building Products sucht einen Process Engineer für ein Werk in Izmir.",
        source_class=SourceClass.C,
    ))
    return store


def test_synthesis_creates_structured_fields(store_with_signals):
    synth = Synthesizer(store_with_signals)
    fields = synth.run()
    assert fields, "expected at least one action field"
    for f in fields:
        assert enforce_structure(f) == [], f"structure invalid: {f.decision_category}"
        assert len(f.options) >= 2
        labels = [o.label.lower() for o in f.options]
        assert any("nichts tun" in l or "beobachten" in l for l in labels)
        assert 0.0 <= f.confidence <= 1.0


def test_confidence_gate_limits_low_confidence_field(store_with_signals):
    synth = Synthesizer(store_with_signals)
    fields = {f.decision_category: f for f in synth.run()}
    # E4 rests on a single unconfirmed C-class hiring signal -> below gate.
    e4 = fields.get("E4")
    assert e4 is not None
    assert e4.gated is True
    assert "recherchieren" in e4.recommendation.lower() or "beobachten" in e4.recommendation.lower()


def test_persisted_and_retrievable(store_with_signals):
    Synthesizer(store_with_signals).run()
    assert store_with_signals.list_action_fields()
    assert store_with_signals.list_action_fields("E2")


def test_dossier_drives_impact(store_with_signals):
    from mci.context import ContextDossier, ProductWeight
    cs = ContextStore(store_with_signals)
    cs.save(ContextDossier(product_weights=[
        ProductWeight(line="AquaGuard", market="DE", revenue_weight=0.5),
    ]))
    # Just ensure synthesis still runs with a dossier present.
    fields = Synthesizer(store_with_signals).run()
    assert fields
