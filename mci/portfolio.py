"""Portfolio-Gap-Matrix (spec §4, E1).

Eigene Varianten × Wettbewerbsvarianten je Anwendungsfall → Lücken, Überhänge,
Überschneidungen. Feeds the E1 portfolio decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import Store
from .models import OwnerType

# When own variants exceed competitor variants by this factor -> Variantenüberhang.
OVERHANG_FACTOR = 2


@dataclass
class GapCell:
    application: str
    own_variants: list[str] = field(default_factory=list)
    competitor_variants: list[str] = field(default_factory=list)
    status: str = "covered"  # gap | whitespace | overlap | overhang

    def as_dict(self) -> dict:
        return {
            "application": self.application,
            "own": self.own_variants,
            "competitor": self.competitor_variants,
            "status": self.status,
        }


def gap_matrix(store: Store) -> list[GapCell]:
    products = store.list_products()
    apps = sorted({p.application for p in products if p.application})
    cells: list[GapCell] = []
    for app in apps:
        own = [p for p in products if p.owner_type == OwnerType.own and p.application == app]
        comp = [p for p in products if p.owner_type == OwnerType.competitor and p.application == app]
        own_labels = [f"{p.line} {p.variant}".strip() for p in own]
        comp_labels = [f"{p.line} {p.variant}".strip() for p in comp]

        if not own and comp:
            status = "gap"  # competitor covers it, we don't -> Sortimentslücke
        elif own and not comp:
            status = "whitespace"  # we lead / no competitor here
        elif len(own_labels) >= OVERHANG_FACTOR * max(1, len(comp_labels)):
            status = "overhang"  # Variantenüberhang
        else:
            status = "overlap"

        cells.append(GapCell(app, own_labels, comp_labels, status))
    return cells


def gaps(store: Store) -> list[GapCell]:
    return [c for c in gap_matrix(store) if c.status == "gap"]
