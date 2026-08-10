"""Tests for the AI intelligence layer: sentiment, summary, alerts, SWOT,
trend radar, and the evidence-grounded chat assistant."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mci import alerts, assistant, sentiment, summarize, swot, trends
from mci.db import Store
from mci.models import Competitor, Signal, SignalEntities, SignalStatus, SignalType


def _store() -> Store:
    return Store(Path(tempfile.mkdtemp()) / "intel.db")


def _sig(type_, headline, fact, comp, *, days_ago=1, status=SignalStatus.unconfirmed,
         priority=2.0, known=None) -> Signal:
    now = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return Signal(
        type=type_, headline=headline, fact=fact,
        entities=SignalEntities(competitors=[comp]),
        status=status, priority=priority, first_seen=now, last_seen=now,
        known_unknowns=known or [],
    )


# ---------------------------------------------------------------- sentiment
def test_sentiment_polarity():
    assert sentiment.score_text("Das Produkt ist zuverlässig und hochwertig") > 0
    assert sentiment.score_text("The product is unreliable and a defect") < 0
    assert sentiment.label(sentiment.score_text("neutral statement about weather")) == "neutral"


def test_sentiment_negation_flips():
    assert sentiment.score_text("nicht gut") < 0


def test_competitor_sentiment_aggregates():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(SignalType.customer_feedback, "Lob", "Acme ist sehr zuverlässig", "Acme"))
    st.upsert_signal(_sig(SignalType.customer_feedback, "Kritik", "Acme defekt und teuer", "Acme"))
    out = {b.competitor: b for b in sentiment.competitor_sentiment(st)}
    assert out["Acme"].n == 2
    assert out["Acme"].positive == 1 and out["Acme"].negative == 1


# ---------------------------------------------------------------- summarize
def test_summary_is_extractive_and_short():
    text = ("Der Markt wächst. Der Wettbewerber senkt die Preise deutlich. "
            "Die Nachfrage nach Fassadenplatten steigt in Europa stark. "
            "Ein neues Werk wird gebaut. Das Wetter ist gut.")
    out = summarize.summarize(text, max_sentences=2)
    assert out.count(".") <= 2
    # every returned sentence must appear verbatim in the source (extractive)
    for part in out.split(". "):
        assert part.strip(". ") in text


# ------------------------------------------------------------------- alerts
def test_alerts_flag_price_and_launch():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(SignalType.marketing, "Acme senkt Preise", "Acme senkt die Preise um 10%", "Acme"))
    st.upsert_signal(_sig(SignalType.launch, "Neues Produkt", "Acme kündigt neue Platte an", "Acme"))
    st.upsert_signal(_sig(SignalType.regulatory, "ETA erteilt", "Acme erhielt eine ETA", "Acme"))
    kinds = {a.kind for a in alerts.detect(st)}
    assert "Preisänderung" in kinds and "Neues Produkt" in kinds and "Zulassung/Patent" in kinds


def test_alerts_respect_window_and_refuted():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(SignalType.launch, "Alt", "alter Launch", "Acme", days_ago=90))
    st.upsert_signal(_sig(SignalType.launch, "Widerlegt", "x", "Acme", status=SignalStatus.refuted))
    assert alerts.detect(st, window_days=21) == []


# --------------------------------------------------------------------- swot
def test_matrix_and_swot():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme", country="DE", segments=["Fassade"]))
    st.upsert_signal(_sig(SignalType.regulatory, "ETA", "Acme erhielt ETA", "Acme"))
    st.upsert_signal(_sig(SignalType.customer_feedback, "Mangel", "Acme defekt und mangelhaft", "Acme"))
    st.upsert_signal(_sig(SignalType.hiring, "Werk", "Acme baut Werk", "Acme"))
    rows = swot.matrix(st)
    assert rows and rows[0]["Wettbewerber"] == "Acme"
    assert rows[0]["Zulassungen/Patente"] == 1
    sw = swot.swot(st, st.list_competitors()[0].id)
    assert any("ETA" in s for s in sw.strengths)
    assert sw.weaknesses  # negative feedback picked up
    assert sw.threats     # hiring picked up


# ------------------------------------------------------------------- trends
def test_trend_radar_ranks_rising_term():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    # "sanierung" appears only recently -> positive momentum
    st.upsert_signal(_sig(SignalType.other, "Alt", "Fassade Neubau Thema", "Acme", days_ago=150))
    st.upsert_signal(_sig(SignalType.other, "Neu1", "Sanierung Fassade wichtig", "Acme", days_ago=5))
    st.upsert_signal(_sig(SignalType.other, "Neu2", "Sanierung Markt Sanierung", "Acme", days_ago=3))
    terms = {t.term: t for t in trends.radar(st, min_count=2)}
    assert "sanierung" in terms and terms["sanierung"].momentum > 0


# ---------------------------------------------------------------- assistant
def test_assistant_answers_from_evidence():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    st.upsert_signal(_sig(SignalType.launch, "Acme Fassadenplatte",
                          "Acme kündigte eine dünnschichtige Fassadenplatte an", "Acme"))
    ans = assistant.answer(st, "Was macht Acme bei Fassadenplatten?")
    assert ans.grounded
    assert "Fassadenplatte" in ans.text
    assert ans.citations


def test_assistant_is_honest_when_no_evidence():
    st = _store()
    st.upsert_competitor(Competitor(name="Acme"))
    ans = assistant.answer(st, "Welchen Umsatz hatte Acme letztes Quartal?")
    assert not ans.grounded
    assert "kein beleg" in ans.confidence_note.lower()
    assert ans.follow_up_query
