# Market & Competitive Intelligence Tool

A **KI-gestützte Ableitungsmaschine**, not a news aggregator. Value comes from
condensing raw signals into a few evidence-backed decision drafts (spec §0).

This repository implements **all three phases** of
[`marketintelligencetoolspec`](#) (spec §8):

- **Phase 1 — MVP core:** Scout + Extractor + Auditor · web/PDF/RSS/manual
  ingestion · evidence-backed signal cards · deterministic hybrid scoring ·
  weekly briefing.
- **Phase 2 — Decision support:** context dossier (RAG), Analyst + Strategist,
  cluster synthesis, learning loop, competitor dossiers, diff view, battlecards,
  hypotheses with auto-falsification, watchlist cadence, gold-set eval harness.
- **Phase 3 — Forecasting & scenarios:** launch-cadence model, portfolio-gap
  matrix, correlation rules, Advocatus Diaboli, country profiles, spec-share,
  the **E8 scenario module** (driver tree, Monte-Carlo, reference class,
  competitor response, verdict), and committee export.

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

### Phase 2 — decision support

| Module | Responsibility | Spec |
|---|---|---|
| `mci/context.py` | Versioned Kontext-Dossier (RAG over own portfolio) | §5.3 |
| `mci/decisions.py` | E1–E7 denkrahmen + mandatory action-field, confidence gate | §5.4 |
| `mci/llm/analysis.py` | Analyst, Strategist, Advocatus Diaboli (offline fallback) | §5.1, §5.4 |
| `mci/synthesis.py` | Weekly cluster synthesis per decision category | §5.4 |
| `mci/feedback.py` | Learning loop: few-shot / negative sets | §5.5 |
| `mci/competitor.py` | Wettbewerberakte (living document) | §4 |
| `mci/diff.py` | „Was hat sich seit deinem letzten Besuch geändert" | §4 |
| `mci/battlecard.py` | Battlecard per line (wir vs. Top 3) | §4 |
| `mci/hypotheses.py` | Hypotheses + automatic falsification (AI may refute, never confirm) | §3.8, §5.5 |
| `mci/watchlist.py` | Watchlist cadence + gap-driven research | §5.2, §7.2 |
| `mci/eval.py` + `gold_set/` | Gold-set + eval harness (regression on prompt change) | §5.6 |

### Phase 3 — forecasting & scenarios

| Module | Responsibility | Spec |
|---|---|---|
| `mci/cadence.py` | Launch-Kadenz-Modell → next window with confidence band | §2.2, §4 |
| `mci/portfolio.py` | Portfolio-Gap-Matrix (gap / whitespace / overlap / overhang) | §4, E1 |
| `mci/correlation.py` | Explicit correlation rules R1–R4 | §2.5 |
| `mci/country.py` | Länder-Steckbrief with construction/regulatory signals | §4, E4 |
| `mci/specshare.py` | Spec-Share timeline from tender/channel signals | §2.3 |
| `mci/scenario/` | **E8**: driver tree, Monte-Carlo, reference class, competitor response, rule-based verdict, Nachhaltemodus | §6 |
| `mci/export.py` | Entscheidungs-One-Pager + scenario report → Markdown/DOCX/PPTX/XLSX | §4, §7.4 |

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

## The E8 scenario module (spec §6)

Answers the honest inversion of a target question (spec §6.1): not "will we hit
+2pp share?" but *what would have to be true, and how plausible is each
condition?*

```python
from mci.scenario import Scenario, run_simulation
from mci.scenario.models import Assumption, CompetitorResponse, Distribution, ReferenceCase

scn = Scenario(target_metric="market_share_pp", target_value=2.0, market="DE", horizon_months=24)
asmp = [Assumption(driver_node="listungstiefe", baseline=0.34, value=0.46,
                   distribution=Distribution(low=0.40, mode=0.46, high=0.50))]
sim = run_simulation(scn, asmp, seed=1,
                     reference_cases=[ReferenceCase(driver="listungstiefe", observed_delta=0.06)],
                     competitor_response=CompetitorResponse(most_affected="Nordwall", modeled=True,
                                                            net_effect_adjustment=-0.3))
print(sim.verdict)  # -> "unplausibel ohne Strukturbruch"
```

Honesty rules enforced (spec §6.6): never a number without a band; the
reference-class check overrides a naive Monte-Carlo (a required movement above
the historical best observed forces "unplausibel"); mandatory sensitivity
(tornado), breakeven, extrapolation + denominator warnings; a scenario without a
modeled competitor response is flagged **incomplete**; and the Nachhaltemodus
compares assumption vs. actual over cycles to reveal systematic optimism.

## Everything runs offline

`python -m mci.demo` exercises all three phases with no API key. `pytest` runs
59 tests. Live web/PDF ingestion, the Streamlit UI, and DOCX/PPTX/XLSX export
use optional dependencies (`pip install -r requirements.txt`) and degrade with a
clear error when absent — the core never depends on them.
