"""Wöchentliches Briefing (spec §4, §8).

Implements the 5-Minuten-Prinzip up to Ebene 1:
  * Ebene 0 — Lage: three "Das hat sich geändert" sentences.
  * Ebene 1 — Cockpit: Top-5 signals, one line each:
    Was · Wer · Warum relevant · Empfohlene Aktion · Konfidenz.

Plus the aggregated `known_unknowns` — the working list that drives the next,
gap-driven research run (spec §5.2 Lückengetriebene Recherche).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .db import Store
from .models import Signal, SignalStatus
from .scoring import priority_pct

_LAST_BRIEFING_KEY = "last_briefing_at"


@dataclass
class Briefing:
    generated_at: datetime
    since: datetime
    changed: list[Signal] = field(default_factory=list)  # new/updated in window
    cockpit: list[Signal] = field(default_factory=list)  # top-5 by priority
    known_unknowns: list[str] = field(default_factory=list)


def _who(signal: Signal) -> str:
    ents = signal.entities.competitors or signal.entities.markets
    return ", ".join(ents) if ents else "—"


def generate_briefing(store: Store, *, window_days: int = 7, top_n: int = 5) -> Briefing:
    now = datetime.now(timezone.utc)
    last = store.get_meta(_LAST_BRIEFING_KEY)
    since = (
        datetime.fromisoformat(last)
        if last
        else now - timedelta(days=window_days)
    )

    active = store.list_signals(
        statuses=[SignalStatus.unconfirmed, SignalStatus.confirmed]
    )
    changed = [s for s in active if s.last_seen >= since]
    changed.sort(key=lambda s: s.priority, reverse=True)

    cockpit = sorted(active, key=lambda s: s.priority, reverse=True)[:top_n]

    unknowns: list[str] = []
    for s in cockpit:
        unknowns.extend(s.known_unknowns)
    # de-dup preserving order
    seen: set[str] = set()
    unknowns = [u for u in unknowns if not (u in seen or seen.add(u))]

    return Briefing(
        generated_at=now, since=since, changed=changed, cockpit=cockpit,
        known_unknowns=unknowns,
    )


def mark_briefing_sent(store: Store) -> None:
    store.set_meta(_LAST_BRIEFING_KEY, datetime.now(timezone.utc).isoformat())


def render_markdown(briefing: Briefing) -> str:
    lines: list[str] = []
    lines.append("# Wöchentliches Briefing")
    lines.append(
        f"_Stand: {briefing.generated_at:%Y-%m-%d %H:%M UTC} · "
        f"Änderungen seit {briefing.since:%Y-%m-%d}_\n"
    )

    # Ebene 0 — Lage
    lines.append("## Ebene 0 — Lage (10 Sekunden)")
    if not briefing.changed:
        lines.append("- Keine relevanten Änderungen im Zeitfenster.")
    else:
        for s in briefing.changed[:3]:
            conf = f"{int(s.confidence * 100)} %"
            status = "bestätigt" if s.status == SignalStatus.confirmed else "unbestätigt"
            lines.append(f"- **{s.headline}** ({status}, Konfidenz {conf})")
    lines.append("")

    # Ebene 1 — Cockpit
    lines.append("## Ebene 1 — Cockpit (Top 5)")
    lines.append("| Prio | Was | Wer | Warum relevant | Empfohlene Aktion | Konfidenz |")
    lines.append("|---|---|---|---|---|---|")
    for s in briefing.cockpit:
        action = s.recommended_action or "beobachten"
        why = (s.derivation or "—")[:80]
        decisions = ",".join(s.decision_link)
        lines.append(
            f"| {priority_pct(s.priority)} | {s.headline[:60]} | {_who(s)} | "
            f"{why} ({decisions}) | {action} | {int(s.confidence * 100)} % |"
        )
    lines.append("")

    # Known unknowns -> next research run
    lines.append("## Wissenslücken (Arbeitsliste nächster Lauf)")
    if not briefing.known_unknowns:
        lines.append("- keine offen markiert")
    else:
        for u in briefing.known_unknowns:
            lines.append(f"- {u}")
    lines.append("")
    lines.append(
        "_KI-generierte Ableitungen sind gekennzeichnet; jede Aussage ist bis "
        "zur Originalquelle nachvollziehbar (Ebene 3)._"
    )
    return "\n".join(lines)
