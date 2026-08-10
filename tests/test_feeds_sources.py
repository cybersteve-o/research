"""Tests for worldwide feed builders and the authoritative source registry."""

from __future__ import annotations

from mci.ingestion.feeds import (
    CURATED_FEEDS,
    google_news_search_rss,
    google_news_top_rss,
    reddit_search_rss,
)
from mci.sources import (
    GLOBAL_SOURCES,
    WORLD_MARKETS,
    authoritative_for,
    market_name,
)


def test_google_news_search_encodes_and_scopes():
    url = google_news_search_rss('"Acme Co" Werk', lang="de", country="DE")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert " " not in url  # query is url-encoded
    assert "hl=de" in url and "gl=DE" in url and "ceid=DE:de" in url


def test_top_and_reddit_builders():
    assert google_news_top_rss(lang="ja", country="JP").endswith("ceid=JP:ja")
    r = reddit_search_rss("construction chemicals")
    assert r.startswith("https://www.reddit.com/search.rss?q=") and "sort=new" in r


def test_curated_feeds_span_multiple_markets():
    assert len(CURATED_FEEDS) >= 8
    assert all(u.startswith("https://news.google.com/rss") for u in CURATED_FEEDS.values())


def test_world_markets_cover_multiple_regions():
    codes = {c for c, _ in WORLD_MARKETS}
    # at least one market from Europe, Americas, Asia, MEA
    assert {"DE", "US", "CN", "TR"} <= codes
    assert market_name("JP") == "Japan"


def test_authoritative_for_market_then_eu_then_global():
    de = authoritative_for("DE")
    names = [s.name for s in de]
    assert any("DIBt" in n for n in names)          # market-specific
    assert any("EUR-Lex" in n for n in names)       # EU appended for European market
    assert any(s in de for s in GLOBAL_SOURCES)     # global baseline appended
    # deduped on URL
    urls = [s.url for s in de]
    assert len(urls) == len(set(urls))


def test_unknown_market_still_gets_global_sources():
    out = authoritative_for("ZZ")
    assert out, "unknown market should still yield the global baseline"
    assert all(s in GLOBAL_SOURCES for s in out)
