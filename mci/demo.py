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
    return md


if __name__ == "__main__":
    run()
