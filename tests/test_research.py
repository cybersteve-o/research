"""Tests for the gap-driven research assistant (mci/research.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mci.db import Store
from mci.ingestion.manual import manual_entry
from mci.models import SourceClass
from mci.pipeline import Pipeline
from mci.research import SearchQuery, suggested_queries
from mci.seed import FOCUS_LINES, FOCUS_MARKETS, seed


def _store() -> Store:
    path = Path(tempfile.mkdtemp()) / "research.db"
    store = Store(path)
    seed(store)
    return store


def test_links_are_urlencoded_and_open_real_engines():
    sq = SearchQuery(label="x", query='"Acme Co" (ETA OR CE)', rationale="r",
                     engines=("Google", "News"))
    links = sq.links
    assert set(links) == {"Google", "News"}
    # Query is url-encoded (quotes/spaces/parens escaped), no raw spaces leak.
    assert " " not in links["Google"]
    assert "Acme" in links["Google"]
    assert links["Google"].startswith("https://")


def test_plan_covers_every_competitor():
    store = _store()
    plan = suggested_queries(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    assert plan, "plan should not be empty once competitors are seeded"
    text = " ".join(q.query for q in plan)
    for c in store.list_competitors():
        assert c.name in text, f"{c.name} missing from research plan"


def test_open_known_unknowns_lead_the_plan():
    """A signal's open known_unknowns must surface as gap-driven queries first."""
    store = _store()
    pipe = Pipeline(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    pipe.ingest(manual_entry(
        "Auf der Messe zeigte CanardBuild Inc. erstmals eine dünnschichtige "
        "Fassadenplatte für den Sanierungsmarkt in CA.",
        source_class=SourceClass.C,
    ))
    plan = suggested_queries(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    gap_labelled = [q for q in plan if q.label == "Offene Wissenslücke"]
    assert gap_labelled, "open known_unknowns should appear as gap queries"
    # Gap queries lead the plan (closing them is the point).
    assert plan[0].label == "Offene Wissenslücke"


def test_queries_are_deduped():
    store = _store()
    plan = suggested_queries(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    keys = [q.query.lower().strip() for q in plan]
    assert len(keys) == len(set(keys))
