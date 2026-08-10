"""Volltextsuche über Signale und Evidenz + gespeicherte Sichten.

Once the store holds a few hundred signals, browsing stops working — you need to
ask "everything about price moves in TR since March". This module provides that
without a search engine dependency: tokenised matching over headline, fact,
derivation and the stored evidence quotes, combined with structured filters.

Ranking is deliberately simple and explainable: term coverage first (how many of
the query's terms the signal matches), then the signal's own priority. No opaque
relevance score — the user can always see why a hit ranked where it did.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from mci.db import Store
from mci.models import Signal, SignalStatus, SignalType

_WORD_RE = re.compile(r"[\wäöüß]+", re.IGNORECASE)
_SAVED_VIEWS_KEY = "saved_views"


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


@dataclass
class Hit:
    signal: Signal
    matched_terms: list[str] = field(default_factory=list)
    coverage: float = 0.0     # share of query terms matched, 0..1
    in_evidence: bool = False  # matched inside a source quote

    @property
    def why(self) -> str:
        where = "Evidenz" if self.in_evidence else "Signal"
        return f"{len(self.matched_terms)} Treffer in {where}: " \
               f"{', '.join(self.matched_terms)}"


def search(
    store: Store,
    query: str = "",
    *,
    statuses: list[SignalStatus] | None = None,
    types: list[SignalType] | None = None,
    competitors: list[str] | None = None,
    markets: list[str] | None = None,
    since_days: int | None = None,
    limit: int = 50,
) -> list[Hit]:
    """Full-text + structured search. An empty query returns filtered signals."""
    terms = _tokens(query)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)
              if since_days else None)

    hits: list[Hit] = []
    for s in store.list_signals():
        if statuses and s.status not in statuses:
            continue
        if types and s.type not in types:
            continue
        if competitors and not (set(competitors) & set(s.entities.competitors)):
            continue
        if markets and not (set(markets) & set(s.entities.markets)):
            continue
        if cutoff:
            when = s.last_seen or s.first_seen
            if when and when < cutoff:
                continue

        if not terms:
            hits.append(Hit(signal=s, coverage=1.0))
            continue

        haystack = set(_tokens(f"{s.headline} {s.fact} {s.derivation} {s.hypothesis}"))
        matched = [t for t in terms if t in haystack]
        in_evidence = False
        if len(matched) < len(terms):
            # Fall back to the source quotes — the evidence often carries wording
            # the condensed signal dropped.
            quote_words: set[str] = set()
            for eid in s.evidence_ids:
                ev = store.get_evidence(eid)
                if ev:
                    quote_words |= set(_tokens(ev.quote_short))
            extra = [t for t in terms if t not in matched and t in quote_words]
            if extra:
                matched += extra
                in_evidence = True
        if not matched:
            continue
        hits.append(Hit(signal=s, matched_terms=matched,
                        coverage=round(len(matched) / len(terms), 3),
                        in_evidence=in_evidence))

    hits.sort(key=lambda h: (h.coverage, h.signal.priority), reverse=True)
    return hits[:limit]


# --- Saved views ----------------------------------------------------------
# Stored as JSON in the meta table so a useful filter survives the session.

def save_view(store: Store, name: str, spec: dict) -> None:
    """Persist a named filter spec (overwrites one with the same name)."""
    views = list_views(store)
    views[name] = spec
    store.set_meta(_SAVED_VIEWS_KEY, json.dumps(views, ensure_ascii=False))


def list_views(store: Store) -> dict[str, dict]:
    raw = store.get_meta(_SAVED_VIEWS_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def delete_view(store: Store, name: str) -> None:
    views = list_views(store)
    views.pop(name, None)
    store.set_meta(_SAVED_VIEWS_KEY, json.dumps(views, ensure_ascii=False))
