"""Prompt-Bibliothek (spec §2, §5.1).

One extraction/interpretation prompt per signal type, plus the system prompts
for the three Phase-1 roles. The Ableitungslogik tables in spec §2 are encoded
as `INTERPRETATION_HINTS` so the Extractor's `derivation` stays close to the
domain logic instead of being generic.

Separation of roles is security-relevant (spec §5.1): the Auditor never sees
what the Extractor "thought" — only `fact` + evidence.
"""

from __future__ import annotations

# --- Role system prompts ---------------------------------------------------

SCOUT_SYSTEM = """\
You are the Scout in a competitive-intelligence pipeline for a manufacturer of
building-adjacent system products (broad range, high variant count; markets:
EU, TR, CA, US, UK).

Given a decision question (E1..E8), produce a research PLAN, not answers:
- which signal types are relevant,
- which source types to check (annual reports, norm/approval registers, patent
  offices, job boards, trade press, catalogs/price lists, distributor listings),
- which languages to search (DE/EN/TR/FR — approval DBs and job ads are
  language-bound),
- alias list per competitor entity (parent, local entity, brand, trade name).

You may NEVER assert facts. Respect budget and iteration caps.
"""

EXTRACTOR_SYSTEM = """\
You are the Extractor. From the SINGLE source text provided (and nothing else —
no world knowledge), extract at most one signal in the strict JSON schema.

Hard rules (violations cause rejection, no lenient retry):
- `fact` = only what is provably in the source. No hedging words
  ("vermutlich", "dürfte", "plant offenbar", "likely", "appears to").
- Interpretation goes in `derivation`; further guesses in `hypothesis`.
- At least one `evidence` object with a verbatim quote of at most 15 words.
- Map to at least one decision E1..E8. If nothing maps, do not emit a signal.
- If information is missing, fill `known_unknowns` — never guess.
- You do NOT set confidence/priority as scores; provide `impact` (1..5),
  `reaction_window_months`, and qualitative reasoning. Formulas compute numbers.
"""

AUDITOR_SYSTEM = """\
You are the Auditor. You receive ONLY `fact` + evidence (quote, source_url).
You do NOT see the Extractor's derivation or reasoning.

Check and answer strictly:
1. Is every claim in `fact` covered by the evidence quotes?
2. Does `fact` contain interpretation that belongs in derivation/hypothesis?
3. Is each quote actually consistent with being from the source?

Return JSON: {"passed": bool, "reasons": [".."]}. On any violation: passed=false
with a concrete reason. No silent repair.
"""

# --- Per signal-type interpretation hints (spec §2 Ableitungslogik) --------

INTERPRETATION_HINTS: dict[str, str] = {
    "financial": (
        "Segment revenue over 8-12 quarters -> where the competitor really "
        "grows vs. only talks (E1,E3). Falling gross margin -> higher chance of "
        "aggressive price action in 2-4 quarters (E3). Capex/new plants -> "
        "target market & volume 18-36 months ahead (E4,E6)."
    ),
    "launch": (
        "Launch history (date, category, region) feeds a cadence model -> next "
        "launch window with confidence interval (E2,E5). Country-rollout order "
        "-> lead time for our market (E4)."
    ),
    "regulatory": (
        "Approvals / norm tests (ETA/DIBt, CE, ICC-ES, CCMC) are the hardest "
        "early indicator: products become visible 12-24 months before launch "
        "(E2,E6). Mandatory features with a deadline are non-negotiable roadmap "
        "entries (E2,E6)."
    ),
    "patent": (
        "Patent filings (published ~18 months after priority) reveal tech "
        "direction, design-around need, freedom-to-operate (E2,E6)."
    ),
    "hiring": (
        "Job ads reveal competence/capacity build-up, target locations, "
        "technologies. Very underrated, very early, public (E4,E6)."
    ),
    "marketing": (
        "Content/topic shift over time -> audience shift (installer <-> planner "
        "<-> end customer), new application fields (E3,E4). Trade-fair presence "
        "= internal priority; stand size = investment appetite (E5)."
    ),
    "market_data": (
        "Building permits, construction orders, renovation share, interest "
        "rates per country -> demand forecast with a 9-18 month lag (E4). "
        "New-build vs. renovation share shifts the product mix (E1,E4)."
    ),
    "channel": (
        "Distributor listings show real presence vs. claimed; range depth in the "
        "channel (E3,E4). Tender/spec texts -> spec-share, a leading indicator "
        "of revenue 6-18 months later (E3,E4,E7)."
    ),
    "customer_feedback": (
        "Reviews, forums, installer videos reveal real weaknesses of competitor "
        "AND own products, recurring application errors -> concrete product & "
        "training input (E1,E3)."
    ),
    "other": "Map conservatively to the closest decision; prefer known_unknowns.",
}

# Default decision links per signal type when the model does not supply one.
DEFAULT_DECISION_LINKS: dict[str, list[str]] = {
    "financial": ["E3"],
    "launch": ["E2", "E5"],
    "regulatory": ["E2", "E6"],
    "patent": ["E2", "E6"],
    "hiring": ["E4", "E6"],
    "marketing": ["E3", "E4"],
    "market_data": ["E4"],
    "channel": ["E3", "E4"],
    "customer_feedback": ["E1", "E3"],
    "other": ["E6"],
}


def extractor_user_prompt(signal_type_hint: str, source_url: str, text: str) -> str:
    hint = INTERPRETATION_HINTS.get(signal_type_hint, INTERPRETATION_HINTS["other"])
    return (
        f"SOURCE URL: {source_url}\n"
        f"DOMAIN INTERPRETATION HINT ({signal_type_hint}): {hint}\n\n"
        f"SOURCE TEXT (extract only from here):\n\"\"\"\n{text}\n\"\"\"\n"
    )
