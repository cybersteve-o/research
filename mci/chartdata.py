"""Turn the store into chart-ready row dicts.

Kept separate from `charts.py` so the data shaping is testable without Altair and
the chart layer stays purely declarative. Every function returns a plain
``list[dict]`` — which doubles as the table fallback each chart needs for relief.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from mci import sentiment as sentiment_mod
from mci import specshare, trends
from mci.db import Store
from mci.models import SignalStatus, SignalType

_STATUS_DE = {
    SignalStatus.confirmed: "bestätigt",
    SignalStatus.unconfirmed: "unbestätigt",
    SignalStatus.refuted: "widerlegt",
    SignalStatus.expired: "abgelaufen",
}

# Activity buckets for the competitor × type matrix.
_KINDS: dict[str, set[SignalType]] = {
    "Launch": {SignalType.launch},
    "Zulassung": {SignalType.regulatory, SignalType.patent},
    "Kapazität": {SignalType.hiring, SignalType.channel},
    "Finanzen": {SignalType.financial},
    "Feedback": {SignalType.customer_feedback},
    "Marketing": {SignalType.marketing},
}


def event_date(store: Store, signal):
    """When the event happened — source publication date, else ingestion time.

    Charts must show *when things happened*, not when we imported them;
    otherwise a batch import collapses every point onto one day.
    """
    for eid in signal.evidence_ids:
        ev = store.get_evidence(eid)
        if not ev:
            continue
        src = store.get_source(ev.source_id)
        if src and src.published_at:
            return src.published_at
    return signal.last_seen or signal.first_seen


def sentiment_rows(store: Store) -> list[dict]:
    return [{"brand": b.competitor, "score": b.avg_score, "n": b.n,
             "label": b.label}
            for b in sentiment_mod.competitor_sentiment(store)]


def trend_rows(store: Store, *, window_days: int = 180, min_count: int = 2,
               top: int = 12) -> list[dict]:
    return [{"term": t.term, "count": t.count, "momentum": t.momentum}
            for t in trends.radar(store, window_days=window_days,
                                  min_count=min_count, top=top)]


def spec_share_rows(store: Store) -> list[dict]:
    out: list[dict] = []
    for entity, points in specshare.spec_share_timeline(store).items():
        for p in points:
            out.append({"entity": entity, "period": p.period,
                        "share": round(p.share, 4), "mentions": p.mentions})
    return sorted(out, key=lambda r: (r["period"], r["entity"]))


def timeline_rows(store: Store, *, limit: int = 60) -> list[dict]:
    rows: list[dict] = []
    for s in store.list_signals():
        entity = ", ".join(s.entities.competitors) or (
            ", ".join(s.entities.markets) or "—")
        when = event_date(store, s)
        if not when:
            continue
        rows.append({"entity": entity, "date": when.isoformat(),
                     "type": s.type.value, "headline": s.headline[:70],
                     "priority": round(s.priority, 2)})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:limit]


def matrix_rows(store: Store) -> list[dict]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    names = [c.name for c in store.list_competitors()]
    for s in store.list_signals():
        for name in s.entities.competitors:
            if name not in names:
                continue
            for kind, types in _KINDS.items():
                if s.type in types:
                    counts[(name, kind)] += 1
    return [{"entity": e, "kind": k, "count": n} for (e, k), n in sorted(counts.items())]


def volume_rows(store: Store) -> list[dict]:
    counts: Counter[tuple[str, str]] = Counter()
    for s in store.list_signals():
        when = event_date(store, s)
        if not when:
            continue
        counts[(f"{when:%Y-%m}", _STATUS_DE.get(s.status, s.status.value))] += 1
    return [{"period": p, "status": st, "count": n}
            for (p, st), n in sorted(counts.items())]
