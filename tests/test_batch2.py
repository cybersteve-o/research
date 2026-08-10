"""Tests for decision tracking, search, source reliability and the own profile."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mci import profile, reliability, search, tracking
from mci.db import Store
from mci.models import (
    Competitor,
    Evidence,
    Signal,
    SignalEntities,
    SignalStatus,
    SignalType,
    Source,
    SourceClass,
)


def _store() -> Store:
    return Store(Path(tempfile.mkdtemp()) / "b2.db")


def _sig(**kw) -> Signal:
    now = datetime.now(timezone.utc)
    base = dict(type=SignalType.launch, headline="H", fact="F",
                first_seen=now, last_seen=now, priority=1.0)
    base.update(kw)
    return Signal(**base)


# ------------------------------------------------------------------ tracking
def test_record_and_resolve_decision():
    st = _store()
    rec = tracking.record_decision(
        st, field_id="af_1", decision_category="E2",
        recommendation="Roadmap vorziehen", decision="Beschlossen für Q3",
        owner="PM Bau", confidence=0.7)
    assert rec.status == "offen" and not rec.is_resolved

    out = tracking.resolve(st, rec.id, status="eingetreten", note="Launch kam")
    assert out.is_resolved and out.score == 1.0 and out.resolved_at is not None


def test_notes_accumulate():
    st = _store()
    rec = tracking.record_decision(st, recommendation="X")
    tracking.add_note(st, rec.id, "Erste Rückmeldung")
    tracking.add_note(st, rec.id, "Zweite Rückmeldung")
    assert len(st.get_decision(rec.id).notes) == 2
    # blank notes are ignored
    tracking.add_note(st, rec.id, "   ")
    assert len(st.get_decision(rec.id).notes) == 2


def test_unknown_status_rejected():
    st = _store()
    rec = tracking.record_decision(st, recommendation="X")
    with pytest.raises(ValueError):
        tracking.resolve(st, rec.id, status="vielleicht")


def test_track_record_hit_rate_and_bias():
    st = _store()
    # Confidently predicted, did not happen -> optimistic
    r1 = tracking.record_decision(st, decision_category="E2",
                                  recommendation="A", confidence=0.9)
    tracking.resolve(st, r1.id, status="nicht eingetreten")
    # Confidently predicted, happened -> calibrated
    r2 = tracking.record_decision(st, decision_category="E2",
                                  recommendation="B", confidence=0.8)
    tracking.resolve(st, r2.id, status="eingetreten")
    # Still open -> must not count towards the hit rate
    tracking.record_decision(st, decision_category="E5", recommendation="C")

    tr = tracking.track_record(st)
    assert tr.total == 3 and tr.resolved == 2 and tr.open == 1
    assert tr.hit_rate == 0.5                     # (0 + 1) / 2
    assert tr.optimism_bias == pytest.approx(0.35)  # ((0.9-0)+(0.8-1))/2
    assert "zu optimistisch" in tr.verdict
    assert tr.by_category["E2"] == 2


def test_track_record_empty_is_honest():
    tr = tracking.track_record(_store())
    assert tr.total == 0 and tr.hit_rate is None
    assert tr.verdict == "noch keine Datenbasis"


# -------------------------------------------------------------------- search
def _store_with_signals() -> Store:
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(headline="Acme senkt Preise",
                          fact="Acme senkt die Preise in DE um 6 Prozent",
                          type=SignalType.marketing, priority=3.0,
                          entities=SignalEntities(competitors=["Acme"], markets=["DE"])))
    st.upsert_signal(_sig(headline="Acme Zulassung",
                          fact="Acme erhielt eine Zulassung in US",
                          type=SignalType.regulatory, status=SignalStatus.confirmed,
                          entities=SignalEntities(competitors=["Acme"], markets=["US"])))
    return st


def test_search_ranks_by_coverage():
    st = _store_with_signals()
    hits = search.search(st, "preise senken DE")
    assert hits
    assert "preise" in hits[0].matched_terms
    assert hits[0].coverage >= hits[-1].coverage


def test_search_structured_filters():
    st = _store_with_signals()
    assert len(search.search(st, "", markets=["US"])) == 1
    assert len(search.search(st, "", types=[SignalType.regulatory])) == 1
    assert len(search.search(st, "", statuses=[SignalStatus.confirmed])) == 1
    assert search.search(st, "", competitors=["Nobody"]) == []


def test_search_falls_back_to_evidence_quotes():
    st = _store()
    src = Source(url="https://x.example", publisher="X", source_class=SourceClass.B)
    st.upsert_source(src)
    ev = Evidence(source_id=src.id, quote_short="Kapazitätsausbau in Vietnam geplant")
    st.add_evidence(ev)
    st.upsert_signal(_sig(headline="Werk", fact="Neues Werk", evidence_ids=[ev.id]))
    hits = search.search(st, "Vietnam")
    assert hits and hits[0].in_evidence


def test_search_respects_recency_window():
    st = _store()
    old = datetime.now(timezone.utc) - timedelta(days=120)
    st.upsert_signal(_sig(headline="Alt", fact="Alt", first_seen=old, last_seen=old))
    assert search.search(st, "", since_days=30) == []
    assert len(search.search(st, "", since_days=365)) == 1


def test_saved_views_roundtrip():
    st = _store()
    search.save_view(st, "Preisdruck DE", {"query": "preis", "markets": ["DE"]})
    assert search.list_views(st)["Preisdruck DE"]["markets"] == ["DE"]
    search.save_view(st, "Preisdruck DE", {"query": "rabatt"})  # overwrite
    assert search.list_views(st)["Preisdruck DE"]["query"] == "rabatt"
    search.delete_view(st, "Preisdruck DE")
    assert search.list_views(st) == {}


# --------------------------------------------------------------- reliability
def test_source_scores_need_history():
    st = _store()
    src = Source(url="https://blog.example", publisher="Blog", source_class=SourceClass.D)
    st.upsert_source(src)
    ev = Evidence(source_id=src.id, quote_short="q")
    st.add_evidence(ev)
    st.upsert_signal(_sig(evidence_ids=[ev.id]))
    scores = reliability.score_sources(st)
    assert scores and scores[0].score is None
    assert scores[0].label == "unbewertet"


def test_confirmed_source_scores_higher_than_refuted():
    st = _store()

    def _publisher(name: str, klass: SourceClass, status: SignalStatus) -> None:
        src = Source(url=f"https://{name}.example", publisher=name, source_class=klass)
        st.upsert_source(src)
        for _ in range(reliability.MIN_HISTORY):
            ev = Evidence(source_id=src.id, quote_short="q")
            st.add_evidence(ev)
            st.upsert_signal(_sig(evidence_ids=[ev.id], status=status))

    _publisher("Amtsblatt", SourceClass.A, SignalStatus.confirmed)
    _publisher("Geruecht", SourceClass.D, SignalStatus.refuted)
    by_name = {s.publisher: s for s in reliability.score_sources(st)}
    assert by_name["Amtsblatt"].score > by_name["Geruecht"].score
    assert by_name["Amtsblatt"].label == "verlässlich"


# ------------------------------------------------------------------- profile
def test_profile_roundtrip_and_completeness():
    st = _store()
    assert not profile.load(st).configured

    saved = profile.save(st, profile.OwnProfile(
        company="Muster Bau AG", product_lines=["AquaLine"],
        focus_markets=["DE", "AT"], positioning="Premium"))
    assert saved.configured
    again = profile.load(st)
    assert again.company == "Muster Bau AG" and again.focus_markets == ["DE", "AT"]


def test_profile_incomplete_stays_unconfigured():
    st = _store()
    saved = profile.save(st, profile.OwnProfile(company="Nur Name"))
    assert not saved.configured


def test_effective_markets_and_lines_fall_back():
    st = _store()
    assert profile.effective_markets(st, ["DE"]) == ["DE"]
    profile.save(st, profile.OwnProfile(company="C", product_lines=["L"],
                                        focus_markets=["TR"]))
    assert profile.effective_markets(st, ["DE"]) == ["TR"]
    assert profile.effective_lines(st, ["X"]) == ["L"]
