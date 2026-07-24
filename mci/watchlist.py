"""Watchlist mit Kadenz (spec §7.2, §5.2).

A watchlist item targets a competitor, market, URL, or a saved query strategy,
with a cadence in days. `due_items` returns what is due now; a scheduler
(APScheduler in the full stack, or cron/`send_later` here) calls `run_due` on a
timer. Running an item refreshes its query strategy via the Scout and, when a
live fetcher + pipeline are supplied, ingests fresh sources.

The `known_unknowns` of existing signals feed lückengetriebene Recherche
(spec §5.2): `gap_queries` turns them into the next run's work list.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from .db import Store
from .llm.client import AnthropicBackend
from .llm.roles import Roles
from .models import SignalStatus, _new_id


class WatchlistItem(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("wl"))
    target_type: str = "competitor"  # competitor | market | url | query
    target_ref: str = ""
    cadence_days: int = 7
    last_run: datetime | None = None
    query_strategy: dict = Field(default_factory=dict)
    enabled: bool = True


def add_watch(
    store: Store,
    *,
    target_type: str,
    target_ref: str,
    cadence_days: int = 7,
) -> WatchlistItem:
    item = WatchlistItem(
        target_type=target_type, target_ref=target_ref, cadence_days=cadence_days
    )
    store.upsert_watchlist(item)
    return item


def due_items(store: Store, now: datetime | None = None) -> list[WatchlistItem]:
    now = now or datetime.now(timezone.utc)
    due = []
    for item in store.list_watchlist():
        if not item.enabled:
            continue
        if item.last_run is None:
            due.append(item)
        elif now - item.last_run >= timedelta(days=item.cadence_days):
            due.append(item)
    return due


def gap_queries(store: Store) -> list[str]:
    """Lückengetriebene Recherche: turn open known_unknowns into a work list."""
    out: list[str] = []
    for s in store.list_signals(
        statuses=[SignalStatus.unconfirmed, SignalStatus.confirmed]
    ):
        out.extend(s.known_unknowns)
    seen: set[str] = set()
    return [q for q in out if not (q in seen or seen.add(q))]


def run_due(
    store: Store,
    *,
    backend: AnthropicBackend | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Refresh query strategy for each due item and mark it run.

    Live crawling is delegated to the caller (needs a fetcher + pipeline); this
    keeps the cadence bookkeeping and plan refresh, which is the offline-safe
    part. Returns a per-item summary.
    """
    now = now or datetime.now(timezone.utc)
    roles = Roles(backend or AnthropicBackend())
    summary: list[dict] = []
    for item in due_items(store, now):
        question = f"Aktualisiere Intelligence zu {item.target_type} {item.target_ref}"
        item.query_strategy = roles.scout_plan(question, [item.target_ref])
        item.last_run = now
        store.upsert_watchlist(item)
        summary.append({"id": item.id, "target": item.target_ref, "planned": True})
    return summary
