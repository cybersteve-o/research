"""Tests for the overall situation report / recommendation (mci/recommendation.py)."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from mci import recommendation
from mci.db import Store
from mci.models import Competitor, Signal, SignalEntities, SignalStatus, SignalType


def _store() -> Store:
    return Store(Path(tempfile.mkdtemp()) / "rec.db")


def _sig(type_, headline, fact, comp, *, status=SignalStatus.unconfirmed,
         priority=2.0, links=None) -> Signal:
    now = datetime.now(timezone.utc)
    return Signal(type=type_, headline=headline, fact=fact,
                  entities=SignalEntities(competitors=[comp]),
                  status=status, priority=priority, first_seen=now, last_seen=now,
                  decision_link=links or [])


def test_empty_store_is_honest():
    rep = recommendation.build(_store())
    assert rep.is_empty
    assert rep.recommendations and "Datenbasis" in rep.recommendations[0].action
    assert "keine" in recommendation.narrative(rep).lower()


def test_report_aggregates_findings_conclusions_recommendations():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(SignalType.launch, "Acme neue Platte",
                          "Acme kündigt neue Platte an", "Acme",
                          status=SignalStatus.confirmed, priority=3.0, links=["E2"]))
    st.upsert_signal(_sig(SignalType.marketing, "Acme senkt Preise",
                          "Acme senkt die Preise", "Acme", links=["E3"]))
    rep = recommendation.build(st)
    assert not rep.is_empty
    assert rep.findings and rep.conclusions and rep.recommendations
    # the price/launch alerts should drive a conclusion about action pressure
    assert any("Handlungs" in c or "Beobachtung" in c for c in rep.conclusions)
    assert 0.0 <= rep.confidence <= 1.0


def test_recommendations_bounded_and_prioritised():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    for i in range(8):
        st.upsert_signal(_sig(SignalType.launch, f"Launch {i}", f"Acme launch {i}", "Acme"))
    rep = recommendation.build(st)
    assert len(rep.recommendations) <= 5
    order = [ {"hoch":0,"mittel":1,"niedrig":2}[r.priority] for r in rep.recommendations ]
    assert order == sorted(order)


def test_narrative_is_nonempty_prose():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(SignalType.regulatory, "ETA", "Acme erhielt ETA", "Acme",
                          status=SignalStatus.confirmed, links=["E2"]))
    text = recommendation.narrative(recommendation.build(st))
    assert "Informationslage" in text and len(text) > 40
