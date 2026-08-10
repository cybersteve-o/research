"""Worldwide news & social feed builders (spec §7.1, §7.4).

News-, Social-Media- und weltweite Aktivitäten werden über RSS eingespeist —
kein proprietäres API, keine Scraper. Google News liefert für jede Suchanfrage
und jede Länder-/Sprachedition einen RSS-Feed; Reddit hat einen Such-RSS. Beide
werden hier nur als *URL* gebaut; das Abrufen macht ``fetch_rss`` (Netz), sodass
diese Funktionen offline testbar bleiben.

Die gebauten Feeds sind bewusst class-C-lastig (News/Social sind schwache
Evidenz). Der Auditor und die Triangulation sorgen dafür, dass daraus erst mit
einer unabhängigen Zweitquelle ein bestätigtes Signal wird.
"""

from __future__ import annotations

from urllib.parse import quote_plus


def google_news_search_rss(query: str, *, lang: str = "en", country: str = "US") -> str:
    """RSS feed for a Google News *search* — worldwide activity on a topic."""
    q = quote_plus(query)
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={lang}&gl={country}&ceid={country}:{lang}")


def google_news_top_rss(*, lang: str = "en", country: str = "US") -> str:
    """RSS feed for a Google News country/language edition (top stories)."""
    return f"https://news.google.com/rss?hl={lang}&gl={country}&ceid={country}:{lang}"


def reddit_search_rss(query: str, *, limit: int = 25) -> str:
    """RSS feed for a Reddit search (social chatter)."""
    q = quote_plus(query)
    return f"https://www.reddit.com/search.rss?q={q}&sort=new&limit={limit}"


# Country/language editions for broad worldwide market coverage out of the box.
_EDITIONS: list[tuple[str, str, str]] = [
    ("Welt (Deutsch)", "de", "DE"),
    ("World (English, US)", "en", "US"),
    ("World (English, UK)", "en", "GB"),
    ("Monde (Français)", "fr", "FR"),
    ("Mundo (Español)", "es", "ES"),
    ("Mondo (Italiano)", "it", "IT"),
    ("日本 (日本語)", "ja", "JP"),
    ("中国 (简体)", "zh-CN", "CN"),
    ("India (English)", "en", "IN"),
    ("Brasil (Português)", "pt-BR", "BR"),
    ("Türkiye (Türkçe)", "tr", "TR"),
]

# name -> ready RSS URL. A worldwide spread of top-stories editions.
CURATED_FEEDS: dict[str, str] = {
    f"Google News – {label}": google_news_top_rss(lang=lang, country=country)
    for label, lang, country in _EDITIONS
}
