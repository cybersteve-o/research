"""End-to-end offline demo: `python -m mci.demo`.

Seeds entities, ingests a handful of sample documents through the full pipeline
(Extractor -> guardrails -> Auditor -> scoring -> store), then prints the weekly
briefing. Runs with no API key — the offline heuristic roles are used.

The samples double as a tiny smoke test of the whole flow. A rejected sample is
included on purpose to show the guardrails biting (hedging in a "fact").
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .briefing import generate_briefing, mark_briefing_sent, render_markdown
from .db import Store
from .ingestion import RawDocument
from .ingestion.manual import manual_entry
from .models import SourceClass
from .pipeline import Pipeline
from .seed import FOCUS_LINES, FOCUS_MARKETS, seed

# Sample documents (stand-ins for fetched web/PDF text). Two of them describe
# the same approval from different sources -> should triangulate to "confirmed".
SAMPLES: list[RawDocument] = [
    RawDocument(
        url="https://www.dibt.de/register/eta-24-0123",
        text=(
            "Nordwall Systeme GmbH erhielt am 12. Juni 2024 die Europäische "
            "Technische Bewertung ETA-24/0123 für ein neues Verbundabdichtungs-"
            "system im Segment Fassade für den Markt DE. Die Bewertung deckt "
            "Anwendungen im Neubau ab."
        ),
        title="ETA-24/0123 Nordwall",
        publisher="dibt.de",
        source_class=SourceClass.A,
    ),
    RawDocument(
        url="https://fachpresse-bau.example/nordwall-eta",
        text=(
            "Nordwall Systeme GmbH erhielt am 12. Juni 2024 die Europäische "
            "Technische Bewertung ETA-24/0123 für ein neues Verbundabdichtungs-"
            "system im Segment Fassade für den Markt DE. Meldung laut Fachpresse."
        ),
        title="Nordwall ETA — Fachbericht",
        publisher="Fachpresse Bau (Verband)",
        source_class=SourceClass.B,
    ),
    RawDocument(
        url="https://careers.altura.example/job/process-engineer-tr",
        text=(
            "Altura Building Products sucht einen Process Engineer für ein neues "
            "Werk in Izmir, TR, mit Schwerpunkt Extrusion von Entkopplungsmatten. "
            "Start der Produktion für 2026 geplant."
        ),
        title="Altura hiring Izmir",
        publisher="careers.altura.example",
        source_class=SourceClass.C,
    ),
    # This one should be REJECTED by the guardrails: the "fact" hedges.
    RawDocument(
        url="https://blog.example/severn-rumor",
        text=(
            "Severn Systems dürfte wahrscheinlich bald die Preise senken, "
            "vermutlich um Marktanteile zu gewinnen."
        ),
        title="Severn rumor",
        publisher="blog.example",
        source_class=SourceClass.D,
    ),
]


def run(db_path: str | Path | None = None) -> str:
    if db_path is None:
        db_path = Path(tempfile.mkdtemp()) / "mci_demo.db"
    store = Store(db_path)
    seed(store)
    pipe = Pipeline(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)

    print(f"DB: {db_path}\n")
    for doc in SAMPLES:
        res = pipe.ingest(doc)
        tag = res.action.upper()
        detail = ""
        if res.violations:
            detail = " | " + "; ".join(res.violations)
        elif res.signal:
            detail = (
                f" | prio={res.signal.priority} conf={res.signal.confidence} "
                f"status={res.signal.status.value}"
            )
        print(f"[{tag:12}] {doc.title}{detail}")

    # A field-sales manual note as a co-equal channel.
    note = manual_entry(
        "Auf der Messe zeigte CanardBuild Inc. erstmals eine dünnschichtige "
        "Fassadenplatte für den Sanierungsmarkt in CA.",
        source_class=SourceClass.C,
    )
    res = pipe.ingest(note)
    print(f"[{res.action.upper():12}] manual field note")

    print(f"\nLLM backend available: {pipe.backend.available} (model: {pipe.model_id})")
    print(f"Run cost so far: ${pipe.backend.usage.cost_usd:.4f}\n")

    briefing = generate_briefing(store)
    md = render_markdown(briefing)
    mark_briefing_sent(store)
    print(md)

    _showcase_phase23(store)
    return md


def _showcase_phase23(store: Store) -> None:
    """Quick offline showcase of the Phase 2/3 layers."""
    from mci import correlation, export
    from mci.synthesis import Synthesizer
    from mci.scenario import Scenario, run_simulation
    from mci.scenario.models import Assumption, CompetitorResponse, Distribution

    print("\n" + "=" * 60)
    print("PHASE 2 — Cluster-Synthese (Handlungsfelder)")
    fields = Synthesizer(store).run()
    for f in fields:
        flag = " [gated]" if f.gated else ""
        print(f"  {f.decision_category}: conf={f.confidence:.2f}{flag} — {f.recommendation[:70]}")

    print("\nPHASE 3 — Korrelationsregeln (§2.5)")
    for ins in correlation.evaluate(store):
        print(f"  {ins.rule_id} {ins.entity}: {ins.conclusion}")
    if not correlation.evaluate(store):
        print("  (keine Kombinationsregel ausgelöst)")

    print("\nPHASE 3 — E8 Zielprüfung: +2,0 pp Marktanteil DE in 24 Monaten")
    scn = Scenario(target_metric="market_share_pp", target_value=2.0, market="DE",
                   horizon_months=24, mode="inverse")
    asmp = [
        Assumption(driver_node="listungstiefe", baseline=0.34, value=0.46,
                   distribution=Distribution(low=0.40, mode=0.46, high=0.50)),
        Assumption(driver_node="distributionsgrad", baseline=0.60, value=0.66,
                   distribution=Distribution(low=0.62, mode=0.66, high=0.70)),
    ]
    from mci.scenario.models import ReferenceCase
    refs = [ReferenceCase(driver="listungstiefe", observed_delta=0.06,
                          description="bester je beobachteter Jahreswert")]
    sim = run_simulation(scn, asmp, seed=1, reference_cases=refs,
                         competitor_response=CompetitorResponse(
                             most_affected="Nordwall", modeled=True,
                             net_effect_adjustment=-0.3))
    print(f"  P(Ziel erreicht) = {sim.p_target_hit:.0%} · Median {sim.outcome_median:+g} pp "
          f"· 80%-Band [{sim.outcome_band_80[0]:+g}, {sim.outcome_band_80[1]:+g}]")
    print(f"  Urteil: {sim.verdict}")
    for w in sim.extrapolation_warnings:
        print(f"  ⚠️ {w}")

    if fields:
        print("\nPHASE 3 — One-Pager (Auszug):")
        op = export.one_pager_markdown(fields[0], store)
        print("  " + op.splitlines()[0])


if __name__ == "__main__":
    run()
