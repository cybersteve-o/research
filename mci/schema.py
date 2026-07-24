"""Signal-Extraktion — verbindliches Ausgabeschema für das LLM (spec §7.3).

The guardrails here are *hard*, not advisory (spec §3.3, §7.3):

  * A signal without at least one evidence object is rejected — no retry with
    loosened rules.
  * `fact` may not contain hedging language ("vermutlich", "dürfte",
    "plant offenbar", …) — that belongs in `derivation`/`hypothesis`. Checked
    rule-based, in DE and EN.
  * Quotes are capped at 15 words (copyright-clean, spec §7.3).
  * Every signal must map to at least one decision (spec §1) — signals without
    decision link go to the archive, not the cockpit.

`validate_extraction` returns a list of violations. Empty list == pass. The
pipeline treats any violation as a rejection; it never silently repairs.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from .models import DECISION_CODES

MAX_HEADLINE_CHARS = 100
MAX_QUOTE_WORDS = 15

# Hedge / speculation markers that must never appear in `fact`. These signal
# interpretation, which belongs in `derivation` or `hypothesis`.
HEDGE_PATTERNS: tuple[str, ...] = (
    # German
    r"\bvermutlich\b",
    r"\bwahrscheinlich\b",
    r"\bd(?:ü|ue)rfte\b",
    r"\bk(?:ö|oe)nnte\b",
    r"\bsollte wohl\b",
    r"\bplant offenbar\b",
    r"\boffenbar\b",
    r"\banscheinend\b",
    r"\bscheint\b",
    r"\bm(?:ö|oe)glicherweise\b",
    r"\bevtl\.?\b",
    r"\bwohl\b",
    r"\bdeutet darauf hin\b",
    # English
    r"\blikely\b",
    r"\bprobably\b",
    r"\bpresumably\b",
    r"\bappears to\b",
    r"\bseems to\b",
    r"\bmight\b",
    r"\bcould be\b",
    r"\bsuggests that\b",
    r"\bwe (?:believe|think|expect)\b",
)

_HEDGE_RE = re.compile("|".join(HEDGE_PATTERNS), re.IGNORECASE)


class EvidenceIn(BaseModel):
    source_url: str
    quote: str = ""  # max 15 words
    retrieved_at: str = ""


class EntitiesIn(BaseModel):
    competitors: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Exact shape the Extractor LLM must return (spec §7.3).

    Pydantic enforces types and required fields; `validate_extraction` enforces
    the semantic guardrails that a type system can't express.
    """

    signal_type: str
    headline: str
    fact: str
    derivation: str = ""
    hypothesis: str = ""
    confidence: float = 0.0
    confidence_reasoning: str = ""
    evidence: list[EvidenceIn] = Field(default_factory=list)
    entities: EntitiesIn = Field(default_factory=EntitiesIn)
    decision_link: list[str] = Field(default_factory=list)
    impact: int = 1
    urgency: int = 1
    # KI schätzt Reaktionsfenster in Monaten; die Formel mappt auf urgency-Stufe
    # (spec §5.3). Optional — falls gesetzt, überschreibt es `urgency`.
    reaction_window_months: float | None = None
    half_life_days: int = 30
    known_unknowns: list[str] = Field(default_factory=list)
    recommended_action: str | None = None

    @field_validator("signal_type")
    @classmethod
    def _known_signal_type(cls, v: str) -> str:
        from .models import SignalType

        allowed = {t.value for t in SignalType}
        if v not in allowed:
            return SignalType.other.value
        return v


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def validate_extraction(result: ExtractionResult) -> list[str]:
    """Return a list of hard-guardrail violations. Empty == pass.

    The pipeline rejects any non-empty result; it does not attempt a lenient
    retry (spec §7.3).
    """
    violations: list[str] = []

    # Evidenzzwang: no signal without at least one evidence object.
    if not result.evidence:
        violations.append("no_evidence: signal has zero evidence objects")
    else:
        for i, ev in enumerate(result.evidence):
            if not ev.source_url.strip():
                violations.append(f"evidence[{i}].source_url is empty")
            wc = _word_count(ev.quote)
            if wc > MAX_QUOTE_WORDS:
                violations.append(
                    f"evidence[{i}].quote has {wc} words (max {MAX_QUOTE_WORDS})"
                )

    # Fakt-Reinheit: no hedging language in `fact`.
    hedge = _HEDGE_RE.search(result.fact)
    if hedge:
        violations.append(
            f"fact_contains_hedge: '{hedge.group(0)}' belongs in "
            "derivation/hypothesis, not fact"
        )

    if not result.fact.strip():
        violations.append("empty_fact: fact field is blank")

    # Headline length + non-empty.
    if not result.headline.strip():
        violations.append("empty_headline")
    elif len(result.headline) > MAX_HEADLINE_CHARS:
        violations.append(
            f"headline too long: {len(result.headline)} chars "
            f"(max {MAX_HEADLINE_CHARS})"
        )

    # Relevanzmapping / Entscheidungsbezug: at least one valid decision code.
    if not result.decision_link:
        violations.append("no_decision_link: signal maps to no decision (E1..E8)")
    else:
        bad = [c for c in result.decision_link if c not in DECISION_CODES]
        if bad:
            violations.append(f"invalid_decision_codes: {bad}")

    # Bounded ordinal inputs from the LLM.
    if not 1 <= result.impact <= 5:
        violations.append(f"impact out of range 1..5: {result.impact}")
    if not 1 <= result.urgency <= 5:
        violations.append(f"urgency out of range 1..5: {result.urgency}")

    return violations


class SchemaViolation(Exception):
    """Raised when an extraction fails hard guardrails."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))
