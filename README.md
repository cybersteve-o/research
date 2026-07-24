# Market & Competitive Intelligence Tool — Phase 1 MVP

A **KI-gestützte Ableitungsmaschine**, not a news aggregator. Value comes from
condensing raw signals into a few evidence-backed decision drafts (spec §0).

This repository implements **Phase 1** of
[`marketintelligencetoolspec`](#) (spec §8): the functioning core.

> Scope: Scout + Extractor + Auditor · web/PDF/RSS/manual ingestion ·
> evidence-backed signal cards · deterministic hybrid scoring · weekly briefing.
> Deliberately **not** in Phase 1: cluster synthesis, scoring fine-tuning, the
> full agent roster, the E8 scenario module (see *Deferred* below).

## Why this design

Three failure modes are engineered out from the start (spec §5):

| Failure mode | Guard in this codebase |
|---|---|
| **Invented facts** | Evidenzzwang + Auditor pass before storage (`schema.py`, `pipeline.py`) |
| **Invented precision** | The LLM sets **no** numbers; `scoring.py` computes every score deterministically |
| **Invented certainty** | `known_unknowns` is first-class; hedging in `fact` is rejected |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: pip install pydantic  (core only)

# End-to-end offline run — no API key needed:
python -m mci.demo

# Test suite (runs fully offline):
pytest -q

# Cockpit UI:
streamlit run mci/app.py
```

The whole system runs **without an Anthropic API key**: the Scout/Extractor/
Auditor roles fall back to a deterministic offline heuristic that flags its own
limits in `known_unknowns` and never fabricates evidence. Set `ANTHROPIC_API_KEY`
(see `.env.example`) to switch the roles onto Claude.

## Architecture (spec §7.1)

```
Quellen ─► Ingestion ─► Extraktion ─► Auditor ─► Scoring ─► Speicher ─► Views
           (html/pdf/     (strict      (fact vs   (formula,   (SQLite)   (briefing
            rss/manual)    schema)      evidence)  no LLM #s)             /Streamlit)
```

| Module | Responsibility | Spec |
|---|---|---|
| `mci/models.py` | Domain entities, enums, half-lives, decision codes | §7.2, §3.6 |
| `mci/schema.py` | LLM output schema + **hard guardrails** (evidence, fact purity, quote length, decision link) | §7.3, §3.3 |
| `mci/scoring.py` | `priority = impact × confidence × urgency × proximity`, fully deterministic | §4, §5.3 |
| `mci/llm/roles.py` | Scout, Extractor, Auditor — LLM path + offline fallback | §5.1 |
| `mci/llm/prompts.py` | Prompt-Bibliothek: per-signal-type interpretation hints | §2, §5.1 |
| `mci/llm/client.py` | Claude backend with **cost cap** + content cache | §5.7 |
| `mci/ingestion/` | HTML (robots-aware), PDF (page locators), RSS, manual | §7.1, §7.4, §7.5 |
| `mci/pipeline.py` | Orchestration, dedup, **triangulation → confirmed** | §7.1, §3.5 |
| `mci/briefing.py` | Weekly briefing: Ebene 0 Lage + Ebene 1 Cockpit + Lückenliste | §4, §8 |
| `mci/app.py` | Streamlit cockpit, Fakt/Ableitung/Hypothese split, 2-click evidence | §4 |

## Quality principles wired in (spec §3)

- **Delta statt Snapshot** — signals carry `first_seen`/`last_seen`/`superseded_by`; the briefing shows *what changed*.
- **Fakt / Ableitung / Hypothese** — separate fields, separately validated, separately rendered.
- **Jede Aussage hat Evidenz** — no signal is stored without ≥1 evidence object; hard schema rejection, no lenient retry.
- **Quellenklassen A–D** — rule-based domain classifier (`classify_source`); weights feed confidence.
- **Triangulation** — a second *independent* source flips status to `confirmed` and re-scores.
- **Halbwertszeit** — per-type decay reduces confidence with age.
- **„Unbekannt" ist zulässig** — explicit `known_unknowns`, aggregated into the next research run.

## Scoring is transparent, never a blackbox

```
confidence = source_class_weight × triangulation_factor × recency_factor
priority   = impact × confidence × urgency × proximity
```

The LLM only supplies qualitative inputs (`impact` category, `reaction_window_months`,
source class for unknown domains). Every number is computed in `scoring.py` and
is reproducible — a signal stores its `prompt_version` and `model_id` (spec §5.6).

## Compliance (spec §7.5)

`robots.txt` is honoured; no paywall/access-barrier bypass; manual entries are
attributable; every stored claim is traceable to its source. Personal profiling
of competitor employees is out of scope by design — job ads are treated as
aggregate capacity signals only.

## Deferred to Phase 2/3 (spec §8)

Analyst & Strategist roles, cluster synthesis, hybrid-scoring feedback loop,
competitor dossiers, battlecards, launch-cadence model, portfolio-gap matrix,
gold-set eval harness, and the **E8 scenario module** (`Scenario`/`Assumption`/
`Lever`/`Simulation` — spec §6). The data model and scoring are structured so
these slot in without rework.
