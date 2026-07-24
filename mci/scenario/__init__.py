"""Szenario- und Zielprüfungsmodul E8 (spec §6).

The honest answer to "how realistic is target X" is never a point forecast. This
module answers the inversion (spec §6.1): *what would all have to be true for the
target to hold, and how plausible is each condition given the evidence?* It
delivers a Bedingungsliste mit Plausibilitätsurteil, not a Prognosezahl.

Deliberately no ML model (spec §7.4): the case counts are too small; a
transparent driver tree is more defensible in a committee.
"""

from .engine import (
    build_packages,
    run_simulation,
    verdict_for,
)
from .levers import LEVER_CATALOG, Lever
from .models import (
    Assumption,
    AssumptionClass,
    DriverNode,
    Outcome,
    ReferenceCase,
    Scenario,
    Simulation,
)

__all__ = [
    "Assumption",
    "AssumptionClass",
    "DriverNode",
    "Outcome",
    "ReferenceCase",
    "Scenario",
    "Simulation",
    "Lever",
    "LEVER_CATALOG",
    "run_simulation",
    "build_packages",
    "verdict_for",
]
