# Market & Competitive Intelligence Tool

A **KI-gestützte Ableitungsmaschine**, not a news aggregator. Value comes from
condensing raw signals into a few evidence-backed decision drafts (spec §0).

> **Zwei Anwendungen in diesem Repository.**
> `mci/` beantwortet *„Was passiert draußen, und warum?"* — Signale, Wettbewerb,
> Szenarien. `gtm/` beantwortet *„Was tun wir, und hat es gewirkt?"* — die
> Planlücke, das gemeinsame Maßnahmenportfolio von Vertrieb und Marketing, die
> Wirkungsbilanz. Zusammen mit dem Absatzforecast bilden sie einen Regelkreis
> statt drei nebeneinanderstehender Werkzeuge. Siehe
> [Die dritte Säule](#die-dritte-säule--wirkungs--und-allokationscockpit-gtm).

This repository implements **all three phases** of
[`marketintelligencetoolspec`](#) (spec §8):

- **Phase 1 — MVP core:** Scout + Extractor + Auditor · ingestion from web, PDF
  & other file formats, worldwide news + social RSS, and manual notes ·
  authoritative-source registry across world markets · evidence-backed signal
  cards · deterministic hybrid scoring · weekly briefing.
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
| `mci/ingestion/` | HTML (robots-aware), PDF (page locators), multi-format upload (txt/md/csv/html), worldwide news + social RSS, manual | §7.1, §7.4, §7.5 |
| `mci/sources.py` | World-market list + curated **authoritative source registry** per region (approval/norm/patent/statistics bodies) | §3.4, §5.5 |
| `mci/research.py` | Gap-driven research plan with ready deep links (Google/News/X/Reddit/LinkedIn/registers) | §5.5 |
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
| `mci/alerts.py` | Frühwarnsystem: rule-based alerts on price moves, launches, approvals | §4 |
| `mci/sentiment.py` | Voice-of-market sentiment per brand (offline lexicon, DE+EN) | §4 |
| `mci/summarize.py` | Extractive few-sentence summaries of long reports/studies | §4 |
| `mci/swot.py` | Competitive matrix + rule-derived SWOT per competitor | §4 |
| `mci/trends.py` | Trend-Radar: rising-term momentum before mainstream | §4 |
| `mci/assistant.py` | Evidence-grounded chat assistant (answers only from stored sources) | §4 |
| `mci/recommendation.py` | Overall situation report: findings → conclusions → prioritised recommendations across the whole data basis | §4, §5.4 |
| `mci/tracking.py` | Entscheidungs-Nachhalten: recommendation → decision → outcome; hit rate + optimism bias | §5.5, §6.6.8 |
| `mci/search.py` | Full-text + structured search over signals and evidence, with saved views | §4 |
| `mci/reliability.py` | Source reliability: class prior + earned confirmation/refutation record | §3.4, §5.6 |
| `mci/profile.py` | Own-company profile (lines, markets, positioning) — replaces the placeholder seed | §5.3 |
| `mci/charts.py` + `mci/chartdata.py` | Validated-palette Altair charts and their (testable) data shaping | §4 |
| `mci/demo_data.py` | Rich 14-month demo corpus for an end-to-end walkthrough | §8 |

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

## Die dritte Säule — Wirkungs- und Allokationscockpit (`gtm/`)

Der Absatzforecast sagt, **wo wir landen**. Das MCI-Tool sagt, **warum**. Beide
sind erkennend: keines bindet Geld, Kapazität oder Verantwortung. Genau dort
bricht es in der Praxis ab — die Lücke ist erklärt, und dann wird über
Maßnahmen gestritten, die sich nicht vergleichen lassen.

`gtm/` schließt den Kreis:

```
Forecast-Lücke gegen Plan
   └─► Ursachenzerlegung (Revenue Bridge, belegt aus MCI-Signalen)
         └─► Maßnahmenportfolio — Vertrieb UND Marketing in einer Wirkungswährung
               └─► Allokation über Märkte unter Budget-, Kapazitäts- und Aufmerksamkeitsgrenze
                     └─► Nachhalten: erwartete gegen eingetretene Wirkung
                           └─► Playbook-Transfer zwischen Märkten
```

```bash
python -m gtm.demo              # ganze Kette offline, ohne API-Schlüssel
streamlit run gtm/app.py        # Cockpit
pytest -q tests/test_gtm_*.py   # 66 Tests
```

### Was das Werkzeug unbequem macht

Ein Planungswerkzeug ist nur so viel wert wie die Wahrheiten, die es nicht
verschweigt. Vier davon sind fest eingebaut:

| Eingebaute Grenze | Warum |
|---|---|
| **Der unerklärte Rest bleibt stehen** | Was die Zerlegung nicht erklärt, wird als eigene Stufe ausgewiesen, nie auf die anderen verteilt. Eine Brücke mit 35 % unerklärt ist eine Rechercheaufgabe, keine Entscheidungsgrundlage. |
| **Exogenes wird markiert** | Gegen ein schrumpfendes Marktvolumen hilft kein Budget. Der Teil gehört in die Planrevision. |
| **Horizont schlägt Wirkungsgrad** | Die Maßnahme mit dem höchsten Wirkungsgrad im Katalog (Spezifikationsarbeit, 27 Monate Wirkzeit) trägt zur Jahreslücke **nichts** bei. Das Cockpit weist Wirkung *im Horizont* und *eingeschwungen* immer getrennt aus. |
| **Ursachendeckel** | Maßnahmen können zusammen nie mehr zurückholen, als die Ursache an Lücke hergibt — sonst summieren sich Pläne auf ein Vielfaches des Problems. |

### Wo die Zahlen herkommen

Dieselbe Hausregel wie in `mci`: **die KI setzt keine Zahlen.** Jeder Euro folgt
aus einer Kette, die `effects.breakdown()` Glied für Glied ausgibt:

```
adressierte Lücke × Wirkungsgrad(Band) × Sättigung(Dosis)
                  × Evidenzabschlag × Realisierungsanteil(Horizont)
```

Die LLM-Rollen liefern Ursachenhypothesen, Beschlussbegründung und Gegenrede —
der Advocatus Diaboli sieht dabei das Ergebnis, aber **nicht** die Begründung,
sonst bekommt man eine höfliche Umformulierung statt eines Einwands. Ohne
API-Schlüssel läuft alles über den deterministischen Offline-Pfad.

### Module

| Modul | Aufgabe |
|---|---|
| `gtm/forecast.py` | Schnittstelle zur ersten Säule: CSV/JSON/API → Planzeilen, mit deutscher **und** englischer Zahlenschreibweise |
| `gtm/bridge.py` | Revenue Bridge Plan ▸ Ursachen ▸ Forecast, inklusive unerklärtem Rest und Überattributions-Prüfung |
| `gtm/link.py` | Kopplung an `mci`: Signale als Beleg je Brückenstufe, Konfidenz aus Quellenklasse und Triangulation, Rechercheaufträge zurück |
| `gtm/catalog.py` | Maßnahmenkatalog — Vertrieb und Marketing in *einer* Tabelle, Struktur wie `mci/scenario/levers.py` |
| `gtm/effects.py` | Wirkungsrechnung: Sättigung, Realisierungsanteil, Evidenzabschlag, Mindestdosis, Amortisationsgrenze |
| `gtm/allocate.py` | Grenznutzen-Allokation unter Budget, Kapazität und Aufmerksamkeitsgrenze; Effizienzgrenze; dominierte Maßnahmen |
| `gtm/tracking.py` | Trefferquote, Optimismus-Bias je Träger, **Kalibrierung** der Evidenzabschläge gegen die Wirklichkeit |
| `gtm/playbook.py` | Marktähnlichkeit und Übertragbarkeit — mit den Einwänden gleich dabei |
| `gtm/export.py` | Beschluss-Einseiter (enthält die Gegenrede) und CSV |
| `gtm/app.py` | Streamlit-Cockpit in sieben Reitern |

Die Kopplung an `mci` ist **weich**: fehlt das Paket oder seine Datenbank, läuft
das Cockpit unverändert weiter — die Ursachen sind dann eben unbelegt, und die
Oberfläche sagt das auch.

## Everything runs offline

`python -m mci.demo` exercises all three phases with no API key. `pytest` runs
59 tests. Live web/PDF ingestion, the Streamlit UI, and DOCX/PPTX/XLSX export
use optional dependencies (`pip install -r requirements.txt`) and degrade with a
clear error when absent — the core never depends on them.
