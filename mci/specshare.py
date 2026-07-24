"""Spec-Share-Tracking (spec §2.3, E3/E4/E7).

Wie oft wird wessen System namentlich in Ausschreibungs-/Leistungstexten
vorgeschrieben — ein führender Indikator für Umsatz 6–18 Monate später.

Counts named mentions of competitor and own entities in channel/tender signals,
bucketed by month, and reports each entity's share of total mentions per month.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .db import Store
from .models import OwnerType, SignalType


@dataclass
class SpecSharePoint:
    period: str  # YYYY-MM
    entity: str
    mentions: int
    share: float  # entity mentions / total mentions in the period


def _mention_count(text: str, names: list[str]) -> int:
    hay = text.lower()
    count = 0
    for n in names:
        n = n.strip().lower()
        if n and re.search(rf"\b{re.escape(n)}\b", hay):
            count += 1
    return count


def _entity_names(store: Store) -> dict[str, list[str]]:
    """Map a display entity -> its name/alias/line variants for matching."""
    names: dict[str, list[str]] = {}
    for c in store.list_competitors():
        names[c.name] = [c.name, *c.aliases]
    for p in store.list_products():
        if p.owner_type == OwnerType.own and p.line:
            names.setdefault(f"(eigen) {p.line}", []).append(p.line)
    return names


def spec_share_timeline(store: Store) -> dict[str, list[SpecSharePoint]]:
    entity_names = _entity_names(store)
    # period -> entity -> mentions
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for s in store.list_signals():
        if s.type != SignalType.channel:
            continue
        text = f"{s.headline} {s.fact}"
        # bucket by source publication month if available, else first_seen
        period = None
        for eid in s.evidence_ids:
            ev = store.get_evidence(eid)
            if ev:
                src = store.get_source(ev.source_id)
                if src and src.published_at:
                    period = src.published_at.strftime("%Y-%m")
                    break
        period = period or s.first_seen.strftime("%Y-%m")

        for entity, names in entity_names.items():
            c = _mention_count(text, names)
            if c:
                buckets[period][entity] += c

    # compute shares
    out: dict[str, list[SpecSharePoint]] = defaultdict(list)
    for period, counts in sorted(buckets.items()):
        total = sum(counts.values()) or 1
        for entity, m in counts.items():
            out[entity].append(
                SpecSharePoint(period=period, entity=entity, mentions=m,
                               share=round(m / total, 4))
            )
    return dict(out)
