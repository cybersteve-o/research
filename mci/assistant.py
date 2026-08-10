"""Chat-Assistent (requirement: „Ein KI-Bot, den Sie direkt fragen können:
‚Welchen Umsatz hat Konkurrent X letztes Quartal gemacht?'").

The critical design choice: the assistant answers **only from stored, source-
linked signals**. It retrieves the most relevant evidence and quotes it — it does
not compose numbers from thin air. If nothing in the store answers the question,
it says so ("kein Beleg in den erfassten Quellen") and turns the question into a
research query instead. That is the whole point of this tool: no invented facts,
no invented precision. With an API key the same retrieval can be handed to Claude
for phrasing, but the grounding set never changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mci.db import Store
from mci.models import Signal
from mci.scoring import priority_pct

_WORD_RE = re.compile(r"[\wäöüß]{3,}", re.IGNORECASE)
_STOP = {
    "welche", "welchen", "welcher", "welches", "was", "wie", "wer", "wann", "wo",
    "warum", "hat", "haben", "ist", "sind", "der", "die", "das", "ein", "eine",
    "und", "oder", "von", "für", "mit", "the", "what", "which", "how", "did",
    "does", "has", "have", "revenue", "umsatz", "letzte", "letztes", "letzten",
}


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "") if w.lower() not in _STOP}


@dataclass
class Citation:
    signal: Signal
    quote: str
    source: str


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False           # True when backed by stored evidence
    follow_up_query: str = ""        # a research query when unanswered

    @property
    def confidence_note(self) -> str:
        return ("Beleggestützt aus erfassten Quellen."
                if self.grounded else
                "Kein Beleg in den erfassten Quellen — als Rechercheauftrag ausgegeben.")


def _competitor_in_question(store: Store, question: str) -> str | None:
    low = question.lower()
    for c in store.list_competitors():
        if c.name.lower() in low or any(a.lower() in low for a in (c.aliases or [])):
            return c.name
    return None


def answer(store: Store, question: str, *, top_k: int = 3) -> Answer:
    """Retrieve the most relevant stored signals and answer honestly from them."""
    q_tokens = _tokens(question)
    focus = _competitor_in_question(store, question)

    scored: list[tuple[float, Signal]] = []
    for s in store.list_signals():
        if focus and focus not in s.entities.competitors:
            continue
        s_tokens = _tokens(f"{s.headline} {s.fact} {s.derivation}")
        overlap = len(q_tokens & s_tokens)
        if overlap == 0 and not focus:
            continue
        # rank by term overlap, then by the signal's own priority
        scored.append((overlap + min(s.priority, 5) / 10, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    hits = [s for _, s in scored[:top_k]]

    if not hits:
        query = question.strip().rstrip("?")
        return Answer(
            text=("Dazu liegt in den erfassten Signalen kein Beleg vor. "
                  "Ich habe die Frage als Rechercheauftrag notiert — bitte über "
                  "den Recherche-Assistenten eine Quelle einspeisen."),
            grounded=False, follow_up_query=query)

    citations: list[Citation] = []
    for s in hits:
        src_line = ""
        for eid in s.evidence_ids:
            ev = store.get_evidence(eid)
            if not ev:
                continue
            src = store.get_source(ev.source_id)
            src_line = (f"[{src.source_class.value}] {src.publisher or src.url}"
                        if src else ev.source_id)
            citations.append(Citation(signal=s, quote=ev.quote_short, source=src_line))
            break
        else:
            citations.append(Citation(signal=s, quote=s.fact, source="—"))

    lead = hits[0]
    who = ", ".join(lead.entities.competitors or lead.entities.markets) or "—"
    text = (f"**{lead.fact}**  \n"
            f"_{who} · {STATUS(lead)} · Priorität {priority_pct(lead.priority)}_")
    if len(hits) > 1:
        text += f"\n\nWeitere belegte Signale dazu: {len(hits) - 1}."
    return Answer(text=text, citations=citations, grounded=True)


def STATUS(s: Signal) -> str:
    return {"confirmed": "bestätigt", "unconfirmed": "unbestätigt",
            "refuted": "widerlegt", "expired": "abgelaufen"}.get(s.status.value, s.status.value)
