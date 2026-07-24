"""Agentenrollen (spec §5.1) — Phase 1: Scout, Extractor, Auditor.

Each role has two paths:
  * LLM path — used when an Anthropic backend is available.
  * Offline path — a deterministic heuristic so the whole pipeline (and the
    test suite) runs with no API key. The offline path is honest: it flags its
    own limits in `known_unknowns` and never fabricates evidence.

The Auditor's offline path is genuinely useful even without an LLM: it re-checks
fact purity and verifies that each quote actually occurs in the source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import SETTINGS
from ..models import DEFAULT_HALF_LIFE_DAYS, SignalType
from ..schema import (
    MAX_QUOTE_WORDS,
    EntitiesIn,
    EvidenceIn,
    ExtractionResult,
    _HEDGE_RE,
    _word_count,
)
from .client import AnthropicBackend
from .prompts import (
    AUDITOR_SYSTEM,
    DEFAULT_DECISION_LINKS,
    EXTRACTOR_SYSTEM,
    INTERPRETATION_HINTS,
    SCOUT_SYSTEM,
    extractor_user_prompt,
)

# --- keyword tables for offline signal-type detection ----------------------

_TYPE_KEYWORDS: list[tuple[SignalType, tuple[str, ...]]] = [
    (SignalType.regulatory, ("eta", "dibt", "icc-es", "ccmc", "zulassung", "approval",
                             "norm", " en ", "ce-kennz", "brandschutz")),
    (SignalType.patent, ("patent", "uspto", "epo", "priorit", "anmeldung ep")),
    (SignalType.hiring, ("stellenanzeige", "m/w/d", "career", "hiring", "sucht ",
                         "recruit", "job ", "vacanc")),
    (SignalType.financial, ("umsatz", "revenue", "marge", "margin", "quartal",
                            "quarter", "ebit", "capex", "geschäftsbericht",
                            "annual report", "guidance")),
    (SignalType.launch, ("launch", "markteinführung", "unveil", "introduce",
                         "neue produkt", "new product", "vorstell")),
    (SignalType.channel, ("distributor", "fachhandel", "listing", "ausschreibung",
                          "tender", "spec ", "sortiment")),
    (SignalType.market_data, ("baugenehmig", "building permit", "construction",
                              "zins", "interest rate", "renovation", "sanierung")),
    (SignalType.customer_feedback, ("review", "bewertung", "forum", "complaint",
                                    "erfahrung", "verarbeiter")),
    (SignalType.marketing, ("messe", "bau ", "coverings", "cersaie", "campaign",
                            "linkedin", "kampagne")),
]

# Conservative default reaction window (months) per signal type.
_DEFAULT_WINDOW: dict[SignalType, float] = {
    SignalType.regulatory: 18,
    SignalType.patent: 18,
    SignalType.launch: 9,
    SignalType.financial: 6,
    SignalType.hiring: 12,
    SignalType.channel: 9,
    SignalType.market_data: 12,
    SignalType.marketing: 6,
    SignalType.customer_feedback: 12,
    SignalType.other: 12,
}

# Split on sentence punctuation followed by a capital/digit, but NOT when the
# period follows a digit (German ordinal dates like "12. Juni") — the lookbehind
# requires a non-digit, non-space char before the punctuation.
_SENT_SPLIT = re.compile(r"(?<=[^\d\s])[.!?]\s+(?=[A-ZÄÖÜ0-9])")
_NUMERIC = re.compile(r"\d")


def _detect_type(text: str) -> SignalType:
    low = f" {text.lower()} "
    for stype, kws in _TYPE_KEYWORDS:
        if any(kw in low for kw in kws):
            return stype
    return SignalType.other


def _first_factual_sentence(text: str) -> str:
    sentences = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]
    for s in sentences:
        if len(s) >= 20 and not _HEDGE_RE.search(s):
            return s
    return sentences[0] if sentences else text.strip()


def _clip_words(text: str, n: int) -> str:
    words = re.findall(r"\S+", text)
    return " ".join(words[:n])


@dataclass
class Roles:
    """Bundles the three Phase-1 roles over a shared backend."""

    backend: AnthropicBackend

    # ---- Scout -------------------------------------------------------------
    def scout_plan(self, decision_question: str, entities: list[str]) -> dict:
        if self.backend.available:
            try:
                return self.backend.complete_json(
                    system=SCOUT_SYSTEM,
                    user=f"Decision question: {decision_question}\n"
                    f"Known entities: {', '.join(entities) or '(none)'}",
                    model=SETTINGS.models.medium,
                    max_tokens=800,
                )
            except Exception:
                pass  # fall through to offline plan
        return self._offline_scout_plan(decision_question, entities)

    @staticmethod
    def _offline_scout_plan(decision_question: str, entities: list[str]) -> dict:
        return {
            "decision_question": decision_question,
            "signal_types": ["regulatory", "launch", "hiring", "financial", "channel"],
            "source_types": [
                "approval/norm registers (ETA/DIBt, CE, ICC-ES, CCMC)",
                "annual reports & investor decks",
                "patent offices",
                "job boards / career pages",
                "trade press & associations",
                "distributor listings / tender texts",
            ],
            "languages": ["de", "en", "tr", "fr"],
            "aliases": {e: [e] for e in entities},
            "note": "offline plan (no LLM) — templated by decision category",
        }

    # ---- Extractor ---------------------------------------------------------
    def extract(self, source_url: str, text: str) -> ExtractionResult | None:
        stype = _detect_type(text)
        if self.backend.available:
            try:
                data = self.backend.complete_json(
                    system=EXTRACTOR_SYSTEM,
                    user=extractor_user_prompt(stype.value, source_url, text),
                    model=SETTINGS.models.medium,
                    max_tokens=1200,
                )
                return ExtractionResult.model_validate(data)
            except Exception:
                pass  # fall through to offline extraction
        return self._offline_extract(source_url, text, stype)

    @staticmethod
    def _offline_extract(
        source_url: str, text: str, stype: SignalType
    ) -> ExtractionResult | None:
        text = text.strip()
        if len(text) < 20:
            return None
        sentence = _first_factual_sentence(text)
        quote = _clip_words(sentence, MAX_QUOTE_WORDS)
        # ensure the quote is short enough even if a single "word" is long
        if _word_count(quote) > MAX_QUOTE_WORDS:
            quote = " ".join(quote.split()[:MAX_QUOTE_WORDS])

        headline = sentence[:100]
        impact = 3 if _NUMERIC.search(sentence) else 2
        return ExtractionResult(
            signal_type=stype.value,
            headline=headline,
            fact=sentence,
            derivation=INTERPRETATION_HINTS[stype.value],
            hypothesis="",
            confidence_reasoning="offline heuristic; confidence computed by formula",
            evidence=[EvidenceIn(source_url=source_url, quote=quote, retrieved_at="")],
            entities=EntitiesIn(),
            decision_link=list(DEFAULT_DECISION_LINKS[stype.value]),
            impact=impact,
            urgency=1,
            reaction_window_months=_DEFAULT_WINDOW[stype],
            half_life_days=DEFAULT_HALF_LIFE_DAYS[stype],
            known_unknowns=[
                "Offline-Heuristik: keine unabhängige Zweitquelle geprüft",
                "Betroffene eigene Produktlinie nicht automatisch gemappt",
            ],
            recommended_action=None,
        )

    # ---- Auditor -----------------------------------------------------------
    def audit(self, fact: str, evidence: list[EvidenceIn], source_text: str) -> dict:
        """Return {"passed": bool, "reasons": [...]}.

        The Auditor sees only `fact` + evidence (spec §5.1). The offline path
        verifies quote occurrence against the source text.
        """
        if self.backend.available:
            try:
                ev_lines = "\n".join(
                    f"- quote: {e.quote!r} (url: {e.source_url})" for e in evidence
                )
                return self.backend.complete_json(
                    system=AUDITOR_SYSTEM,
                    user=f"FACT:\n{fact}\n\nEVIDENCE:\n{ev_lines}",
                    model=SETTINGS.models.strong,
                    max_tokens=500,
                )
            except Exception:
                pass
        return self._offline_audit(fact, evidence, source_text)

    @staticmethod
    def _offline_audit(
        fact: str, evidence: list[EvidenceIn], source_text: str
    ) -> dict:
        reasons: list[str] = []
        if not evidence:
            reasons.append("no evidence to cover the fact")

        hedge = _HEDGE_RE.search(fact)
        if hedge:
            reasons.append(f"fact contains interpretation marker '{hedge.group(0)}'")

        norm_source = _normalize_ws(source_text).lower()
        for e in evidence:
            q = _normalize_ws(e.quote).lower()
            if q and q not in norm_source:
                reasons.append(f"quote not found verbatim in source: {e.quote!r}")

        return {"passed": not reasons, "reasons": reasons}


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
