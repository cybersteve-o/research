"""Diff-Ansicht — „Was hat sich seit deinem letzten Besuch geändert" (spec §4).

Prevents re-reading everything. Tracks a per-view last-visit timestamp in the
meta table and reports new signals, freshly triangulated (status-changed)
signals, and new action fields since then.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .db import Store
from .decisions import ActionField
from .models import Signal, SignalStatus

_VISIT_KEY = "last_visit"


@dataclass
class Diff:
    since: datetime
    new_signals: list[Signal] = field(default_factory=list)
    confirmed_since: list[Signal] = field(default_factory=list)
    new_action_fields: list[ActionField] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.new_signals or self.confirmed_since or self.new_action_fields)


def since_last_visit(store: Store) -> Diff:
    raw = store.get_meta(_VISIT_KEY)
    since = (
        datetime.fromisoformat(raw)
        if raw
        else datetime.now(timezone.utc).replace(year=2000)
    )
    signals = store.list_signals(include_superseded=True)
    new_signals = [s for s in signals if s.first_seen >= since]
    confirmed = [
        s
        for s in signals
        if s.status == SignalStatus.confirmed
        and s.last_seen >= since
        and s.first_seen < since  # became confirmed after first appearing
    ]
    fields = [f for f in store.list_action_fields() if f.created_at >= since]
    return Diff(
        since=since,
        new_signals=new_signals,
        confirmed_since=confirmed,
        new_action_fields=fields,
    )


def mark_visited(store: Store) -> None:
    store.set_meta(_VISIT_KEY, datetime.now(timezone.utc).isoformat())
