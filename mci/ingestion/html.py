"""HTML ingestion via httpx + trafilatura, robots.txt-aware (spec §7.4, §7.5)."""

from __future__ import annotations

import urllib.robotparser
from urllib.parse import urlparse

from . import RawDocument, classify_source

_UA = "MCI-Bot/0.1 (competitive-intelligence; respects robots.txt)"


class RobotsDisallowed(Exception):
    pass


def _robots_allows(url: str) -> bool:
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # If robots.txt can't be fetched, be conservative and allow — but do not
        # attempt to bypass any access barrier (spec §7.5).
        return True
    return rp.can_fetch(_UA, url)


def fetch_html(url: str, *, respect_robots: bool = True, timeout: float = 20.0) -> RawDocument:
    """Fetch and extract main text from an HTML page.

    Raises RobotsDisallowed if robots.txt forbids the fetch.
    """
    try:
        import httpx  # noqa: PLC0415
        import trafilatura  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "HTML ingestion needs `httpx` and `trafilatura` "
            "(pip install httpx trafilatura)"
        ) from exc

    if respect_robots and not _robots_allows(url):
        raise RobotsDisallowed(f"robots.txt disallows fetching {url}")

    resp = httpx.get(
        url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True
    )
    resp.raise_for_status()
    html = resp.text

    text = trafilatura.extract(html, include_comments=False, favor_precision=True) or ""
    meta = trafilatura.extract_metadata(html)
    title = getattr(meta, "title", "") or ""
    publisher = getattr(meta, "sitename", "") or urlparse(url).hostname or ""

    return RawDocument(
        url=url,
        text=text.strip(),
        title=title,
        publisher=publisher,
        source_class=classify_source(url, publisher),
        channel="web",
    )
