"""RSS / news ingestion via feedparser (spec §7.1, §7.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from . import RawDocument, classify_source


def fetch_rss(feed_url: str, *, limit: int = 20) -> list[RawDocument]:
    try:
        import feedparser  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "RSS ingestion needs `feedparser` (pip install feedparser)"
        ) from exc

    parsed = feedparser.parse(feed_url)
    publisher = parsed.feed.get("title", "") if hasattr(parsed, "feed") else ""
    docs: list[RawDocument] = []
    for entry in parsed.entries[:limit]:
        link = entry.get("link", feed_url)
        summary = entry.get("summary", "") or entry.get("description", "")
        title = entry.get("title", "")
        text = f"{title}. {summary}".strip()
        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        docs.append(
            RawDocument(
                url=link,
                text=text,
                title=title,
                publisher=publisher,
                source_class=classify_source(link, publisher),
                published_at=published,
                channel="rss",
            )
        )
    return docs
