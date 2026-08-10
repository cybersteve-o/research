"""Sentiment-Analyse (requirement: „erkennt, ob Kunden positiv oder negativ
über eine Marke sprechen").

Deterministic lexicon scorer, DE + EN, with light negation handling. No model
download, no API — runs offline like the rest of the tool. Sentiment is treated
as a *derivation*, never a fact: a score is a computed interpretation of source
text, so it is labelled and always carries the underlying signal for audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mci.db import Store
from mci.models import SignalType

_POS = {
    # EN
    "good", "great", "excellent", "reliable", "love", "best", "easy", "fast",
    "recommend", "quality", "robust", "helpful", "improved", "strong", "wins",
    # DE
    "gut", "super", "spitze", "zuverlässig", "empfehlenswert", "empfehlen",
    "hochwertig", "stark", "schnell", "einfach", "überzeugend", "top", "besser",
}
_NEG = {
    # EN
    "bad", "poor", "unreliable", "slow", "expensive", "defect", "broken",
    "complaint", "worse", "worst", "fail", "failure", "weak", "delay", "issue",
    # DE
    "schlecht", "mangelhaft", "unzuverlässig", "teuer", "defekt", "kaputt",
    "beschwerde", "schwach", "verzögerung", "problem", "ärger", "reklamation",
}
_NEGATORS = {"not", "no", "never", "kein", "keine", "nicht", "ohne"}
_WORD_RE = re.compile(r"[\wäöüß]+", re.IGNORECASE)


def score_text(text: str) -> float:
    """Polarity in [-1, 1]. 0 = neutral / no polarity words found."""
    tokens = [t.lower() for t in _WORD_RE.findall(text or "")]
    if not tokens:
        return 0.0
    hits = 0
    total = 0
    for i, tok in enumerate(tokens):
        val = 1 if tok in _POS else -1 if tok in _NEG else 0
        if val == 0:
            continue
        if i > 0 and tokens[i - 1] in _NEGATORS:
            val = -val
        hits += val
        total += 1
    return 0.0 if total == 0 else round(hits / total, 3)


def label(score: float) -> str:
    if score > 0.15:
        return "positiv"
    if score < -0.15:
        return "negativ"
    return "neutral"


@dataclass
class BrandSentiment:
    competitor: str
    n: int = 0
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    avg_score: float = 0.0
    signal_ids: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return label(self.avg_score)


# Signal types whose text reflects how the market *talks about* a brand.
_VOICE_TYPES = {SignalType.customer_feedback, SignalType.marketing, SignalType.other}


def competitor_sentiment(store: Store) -> list[BrandSentiment]:
    """Aggregate voice-of-market sentiment per tracked competitor."""
    comps = store.list_competitors()
    out: dict[str, BrandSentiment] = {c.name: BrandSentiment(competitor=c.name) for c in comps}
    for s in store.list_signals():
        if s.type not in _VOICE_TYPES:
            continue
        text = f"{s.headline} {s.fact} {s.derivation}"
        sc = score_text(text)
        for name in s.entities.competitors:
            bs = out.get(name)
            if bs is None:
                continue
            bs.n += 1
            bs.signal_ids.append(s.id)
            bs.avg_score += sc
            lab = label(sc)
            setattr(bs, {"positiv": "positive", "negativ": "negative",
                         "neutral": "neutral"}[lab],
                    getattr(bs, {"positiv": "positive", "negativ": "negative",
                                 "neutral": "neutral"}[lab]) + 1)
    for bs in out.values():
        if bs.n:
            bs.avg_score = round(bs.avg_score / bs.n, 3)
    return [bs for bs in out.values() if bs.n]
