"""Trend-Radar (requirement: „Zeigt neue Markttrends, bevor sie massenhaft
genutzt werden").

Extracts recurring terms from recent signals and ranks them by *momentum* — how
much more often a term appears in the recent half of the window than the older
half. A term that is suddenly rising (even at low absolute volume) is exactly the
weak-but-early signal the radar is meant to surface, before it is mainstream.
Every trend keeps its sample signals for audit.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from mci.db import Store

_WORD_RE = re.compile(r"[\wäöüß]{4,}", re.IGNORECASE)
_STOP = {
    "eine", "einen", "einem", "einer", "wird", "werden", "haben", "hatte",
    "sich", "nach", "über", "unter", "durch", "gegen", "market", "markt",
    "neue", "neuen", "neues", "product", "produkt", "company", "gmbh", "inc",
    "this", "that", "with", "from", "have", "will", "sind", "auch", "mehr",
    "wurde", "worden", "diese", "dieser", "dieses", "sowie", "bzw",
}


@dataclass
class Trend:
    term: str
    count: int
    momentum: float          # recent share − older share, in [-1, 1]
    first_seen: datetime | None = None
    signal_ids: list[str] = field(default_factory=list)

    @property
    def arrow(self) -> str:
        return "🔼" if self.momentum > 0.1 else "🔽" if self.momentum < -0.1 else "▶️"


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "")
            if w.lower() not in _STOP}


def radar(store: Store, *, window_days: int = 180, min_count: int = 2,
          now: datetime | None = None, top: int = 15) -> list[Trend]:
    """Rank recurring terms by rising momentum over the window."""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    mid = now - timedelta(days=window_days / 2)

    count: dict[str, int] = defaultdict(int)
    recent: dict[str, int] = defaultdict(int)
    older: dict[str, int] = defaultdict(int)
    first: dict[str, datetime] = {}
    sids: dict[str, list[str]] = defaultdict(list)

    for s in store.list_signals():
        seen = s.last_seen or s.first_seen or now
        if seen < start:
            continue
        for term in _terms(f"{s.headline} {s.fact}"):
            count[term] += 1
            sids[term].append(s.id)
            if seen >= mid:
                recent[term] += 1
            else:
                older[term] += 1
            if term not in first or seen < first[term]:
                first[term] = seen

    trends: list[Trend] = []
    for term, c in count.items():
        if c < min_count:
            continue
        r, o = recent[term], older[term]
        momentum = round((r - o) / c, 3) if c else 0.0
        trends.append(Trend(term=term, count=c, momentum=momentum,
                            first_seen=first.get(term), signal_ids=sids[term][:5]))
    trends.sort(key=lambda t: (t.momentum, t.count), reverse=True)
    return trends[:top]
