"""Context dossier tests (spec §5.3)."""

from mci.context import (
    ContextDossier,
    ContextStore,
    ProductWeight,
    StrategicPriority,
)
from mci.db import Store
from mci.scoring import impact_from_revenue_weight


def _dossier() -> ContextDossier:
    return ContextDossier(
        product_weights=[
            ProductWeight(line="AquaGuard", market="DE", revenue_weight=0.30, margin_weight=0.4),
            ProductWeight(line="AquaGuard", market="US", revenue_weight=0.15, margin_weight=0.3),
            ProductWeight(line="DecoTrim", market="DE", revenue_weight=0.10, margin_weight=0.2),
        ],
        strategic_priorities=[
            StrategicPriority(year=2026, text="AquaGuard in US ausbauen",
                              lines=["AquaGuard"], markets=["US"]),
        ],
    )


def test_versioning_increments(tmp_path):
    store = Store(tmp_path / "t.db")
    cs = ContextStore(store)
    d1 = cs.save(_dossier())
    d2 = cs.save(_dossier())
    assert d1.version == 1 and d2.version == 2
    assert cs.latest().version == 2
    assert cs.history() == [1, 2]


def test_revenue_weight_sums_lines_and_markets():
    d = _dossier()
    assert d.revenue_weight_for(["AquaGuard"]) == 0.45
    assert d.revenue_weight_for(["AquaGuard"], markets=["DE"]) == 0.30
    assert d.revenue_weight_for(["Unknown"]) == 0.0


def test_impact_maps_from_weight():
    assert impact_from_revenue_weight(0.45) == 5
    assert impact_from_revenue_weight(0.30) == 4
    assert impact_from_revenue_weight(0.15) == 3
    assert impact_from_revenue_weight(0.05) == 2
    assert impact_from_revenue_weight(0.01) == 1


def test_prompt_context_mentions_lines():
    ctx = _dossier().as_prompt_context()
    assert "AquaGuard" in ctx and "Strategische Prioritäten" in ctx
