"""Committee export tests — the dependency-free Markdown path (spec §4, §7.5)."""

import pytest

from mci import export
from mci.db import Store
from mci.decisions import ActionField, Option
from mci.ingestion.manual import manual_entry
from mci.pipeline import Pipeline
from mci.scenario import Scenario, run_simulation
from mci.scenario.engine import _baseline_product  # noqa: F401  (ensure import path ok)
from mci.scenario.models import (
    Assumption,
    CompetitorResponse,
    Distribution,
)
from mci.synthesis import Synthesizer


def test_one_pager_markdown_has_mandatory_sections(tmp_path):
    store = Store(tmp_path / "t.db")
    pipe = Pipeline(store)
    pipe.ingest(manual_entry("Nordwall Systeme erhielt die ETA-24/0123 Zulassung im Segment Fassade."))
    fields = Synthesizer(store).run()
    field = fields[0]
    md = export.one_pager_markdown(field, store)
    for section in ["## Situation", "## Optionen", "## Empfehlung",
                    "## Gegenposition", "## Falsifikations-Trigger", "## Evidenz"]:
        assert section in md
    assert "KI-generierte Ableitungen" in md  # AI labeling (spec §7.5)


def test_scenario_markdown_shows_band_and_verdict():
    scn = Scenario(target_value=2.0, market="DE", target_metric="market_share_pp")
    asmp = [Assumption(driver_node="listungstiefe", baseline=0.34, value=0.40,
                       distribution=Distribution(low=0.34, mode=0.40, high=0.46))]
    sim = run_simulation(scn, asmp, seed=1,
                         competitor_response=CompetitorResponse(modeled=True))
    md = export.scenario_markdown(scn, [sim])
    assert "80%-Band" in md and "Urteil" in md
    assert sim.verdict in md
    assert "KI-generierte Ableitungen" in md


def test_optional_office_exports_raise_cleanly_if_missing(tmp_path):
    field = ActionField(decision_category="E2", observation="x",
                        options=[Option(label="Nichts tun"), Option(label="Handeln")],
                        signal_ids=["s"])
    store = Store(tmp_path / "t.db")
    # These libs may or may not be installed; if missing, must raise ImportError.
    for fn, path in [
        (lambda: export.export_one_pager_docx(field, store, tmp_path / "a.docx"), "docx"),
        (lambda: export.export_one_pager_pptx(field, tmp_path / "a.pptx"), "pptx"),
    ]:
        try:
            fn()
        except ImportError:
            pass  # acceptable — optional dependency absent
