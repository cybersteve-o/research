"""Automatische Zusammenfassung (requirement: „Lange Berichte oder Studien
werden in wenigen Sätzen zusammengefasst").

Deterministic extractive summariser: rank sentences by normalised term
frequency, return the top-k in their original order. Extractive on purpose —
it only ever returns sentences that literally appear in the source, so a summary
can never introduce a claim the source did not make (same Evidenzzwang spirit as
the rest of the tool). An LLM abstractive summary can be layered on later behind
the existing backend, but is never required.
"""

from __future__ import annotations

import re
from collections import Counter

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[\wäöüß]+", re.IGNORECASE)
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "is",
    "are", "was", "were", "be", "by", "at", "as", "that", "this", "it", "from",
    "der", "die", "das", "und", "oder", "von", "zu", "in", "für", "auf", "mit",
    "ist", "sind", "war", "waren", "ein", "eine", "einen", "im", "am", "des",
    "den", "dem", "als", "auch", "wird", "werden", "hat", "haben",
}


def _sentences(text: str) -> list[str]:
    parts = _SENT_RE.split((text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 0]


def summarize(text: str, *, max_sentences: int = 3) -> str:
    """Return a short extractive summary (few sentences), original order kept."""
    sents = _sentences(text)
    if len(sents) <= max_sentences:
        return " ".join(sents)

    freq: Counter[str] = Counter()
    for s in sents:
        for w in _WORD_RE.findall(s.lower()):
            if w not in _STOP and len(w) > 2:
                freq[w] += 1
    if not freq:
        return " ".join(sents[:max_sentences])
    top = max(freq.values())

    scored: list[tuple[int, float]] = []
    for idx, s in enumerate(sents):
        words = [w for w in _WORD_RE.findall(s.lower()) if w not in _STOP and len(w) > 2]
        if not words:
            scored.append((idx, 0.0))
            continue
        score = sum(freq[w] for w in words) / (len(words) * top)
        scored.append((idx, round(score, 4)))

    chosen = sorted(sorted(scored, key=lambda x: x[1], reverse=True)[:max_sentences],
                    key=lambda x: x[0])
    return " ".join(sents[i] for i, _ in chosen)
