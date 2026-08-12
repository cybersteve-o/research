"""GTM — Wirkungs- und Allokationscockpit.

Die dritte Säule neben Absatzforecast und Markt-/Wettbewerbsrecherche:

    Forecast  ▸  „Wo landen wir?“
    MCI       ▸  „Was passiert draußen, und warum?“
    GTM       ▸  „Was tun wir — und hat es gewirkt?“

Der Weg durch das Paket entspricht dem Weg durch die Entscheidung:

    forecast  ▸  bridge  ▸  link  ▸  catalog  ▸  effects  ▸  allocate
                                                      ▸  tracking  ▸  playbook

`python -m gtm.demo` läuft die ganze Kette offline durch, ohne API-Schlüssel.
"""

from .allocate import allocate, frontier
from .bridge import Bridge, build as build_bridge
from .models import (
    Allocation,
    Band,
    BridgeStep,
    CauseCode,
    EvidenceClass,
    Instrument,
    MarketProfile,
    Measure,
    MeasureOutcome,
    PlanFigure,
    Portfolio,
)

__all__ = [
    "Allocation",
    "Band",
    "Bridge",
    "BridgeStep",
    "CauseCode",
    "EvidenceClass",
    "Instrument",
    "MarketProfile",
    "Measure",
    "MeasureOutcome",
    "PlanFigure",
    "Portfolio",
    "allocate",
    "build_bridge",
    "frontier",
]
