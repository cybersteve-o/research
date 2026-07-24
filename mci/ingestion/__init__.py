"""Ingestion (spec §7.1).

Five co-equal channels. Manuelle Eingabe (manual entry from field sales, trade
fairs, customer talks) is a first-class channel, not an afterthought — "Die
besten Signale kommen oft vom Außendienst" (spec §7.1).

Heavy parsers (trafilatura, httpx, pdfplumber, feedparser) are imported lazily
so the core package imports with only pydantic installed. Each fetcher raises a
clear error if its dependency is missing.

Compliance (spec §7.5): the HTML fetcher honours robots.txt and never attempts
to bypass paywalls or access barriers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..models import Source, SourceClass


@dataclass
class RawDocument:
    """Normalised ingestion output, ready for extraction."""

    url: str
    text: str
    title: str = ""
    publisher: str = ""
    source_class: SourceClass = SourceClass.C
    published_at: datetime | None = None
    locator: str = ""  # e.g. "p.4" for a PDF page
    channel: str = "web"  # web | pdf | rss | manual
    meta: dict = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.strip().encode("utf-8")).hexdigest()

    def to_source(self) -> Source:
        return Source(
            url=self.url,
            title=self.title,
            publisher=self.publisher,
            source_class=self.source_class,
            published_at=self.published_at,
            retrieved_at=datetime.now(timezone.utc),
            hash=self.hash,
            content_ref=self.locator,
        )


# --- Source-class classifier (spec §3.4, §5.3) -----------------------------
# Rule-based domain whitelist; unknown domains default to C, and the LLM may
# later propose a reclassification (Phase 2).

_CLASS_A_DOMAINS = {
    "epo.org", "uspto.gov", "wipo.int", "dpma.de",         # patent offices
    "dibt.de", "eota.eu", "iccsafe.org", "nrc-cnrc.gc.ca",  # norm/approval
    "sec.gov", "bundesanzeiger.de",                         # filings
}
_CLASS_B_HINTS = ("verband", "association", "fachpresse", "study", "studie",
                  "marktforschung", "research", "institut")
_CLASS_C_DOMAINS = {
    "linkedin.com", "youtube.com", "youtu.be", "reddit.com",
    "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com",
}


def classify_source(url: str, publisher: str = "") -> SourceClass:
    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    base = ".".join(host.split(".")[-2:]) if host else ""
    hay = f"{host} {publisher}".lower()

    if base in _CLASS_A_DOMAINS or host in _CLASS_A_DOMAINS:
        return SourceClass.A
    if base in _CLASS_C_DOMAINS or host in _CLASS_C_DOMAINS:
        return SourceClass.C
    if any(h in hay for h in _CLASS_B_HINTS):
        return SourceClass.B
    return SourceClass.C


from .html import fetch_html  # noqa: E402
from .manual import manual_entry  # noqa: E402
from .pdf import extract_pdf  # noqa: E402
from .rss import fetch_rss  # noqa: E402

__all__ = [
    "RawDocument",
    "classify_source",
    "fetch_html",
    "extract_pdf",
    "fetch_rss",
    "manual_entry",
]
