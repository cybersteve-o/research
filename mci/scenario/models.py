"""E8 data model (spec §6.7)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AssumptionClass(str, enum.Enum):
    """Gemessen / aus Analogie abgeleitet / reine Annahme (spec §6.6)."""

    measured = "measured"
    analog = "analog"
    assumed = "assumed"


class Distribution(BaseModel):
    """A sampling distribution for a driver's scenario value.

    type: triangular(low, mode, high) | normal(mean, sd) | uniform(low, high).
    Nie eine Zahl ohne Band (spec §6.6) — a point value must be given as a
    degenerate triangular with low==mode==high, which the UI still renders as a
    (zero-width) band, never as bare precision.
    """

    type: str = "triangular"
    low: float = 0.0
    mode: float = 0.0
    high: float = 0.0
    mean: float = 0.0
    sd: float = 0.0


class DriverNode(BaseModel):
    """Ein Treiberbaum-Knoten (spec §6.2)."""

    name: str
    path: str = "handel"  # handel | spez
    ist_wert: float = 0.0  # current baseline value (fraction 0..1 for share drivers)
    unsicherheitsband: tuple[float, float] = (0.0, 0.0)
    klasse: AssumptionClass = AssumptionClass.assumed
    quelle: str = ""
    letzte_pruefung: datetime | None = None


class Scenario(BaseModel):
    id: str = Field(default_factory=lambda: _id("scn"))
    target_metric: str = "market_share_pp"
    target_value: float = 0.0
    market: str = ""
    product_line: str = ""
    horizon_months: int = 24
    mode: str = "inverse"  # forward | inverse
    owner: str = ""
    created_at: datetime = Field(default_factory=_now)
    review_date: datetime | None = None
    status: str = "open"


class Assumption(BaseModel):
    id: str = Field(default_factory=lambda: _id("asm"))
    scenario_id: str = ""
    driver_node: str = ""
    value: float = 0.0  # scenario target value for the driver
    baseline: float = 0.0  # current value (for delta vs. reference class)
    distribution: Distribution = Field(default_factory=Distribution)
    klasse: AssumptionClass = AssumptionClass.assumed
    evidence_ids: list[str] = Field(default_factory=list)
    author: str = ""
    confirmed_by_human: bool = False  # spec §6.6.7 — KI schlägt vor, PM setzt
    note: str = ""


class Lever(BaseModel):
    id: str = Field(default_factory=lambda: _id("lev"))
    name: str = ""
    affects_driver: str = ""
    time_to_effect_months: int = 12
    cost_class: str = "mittel"
    reversibility: str = "mittel"
    evidence_basis: list[str] = Field(default_factory=list)


class ReferenceCase(BaseModel):
    """Referenzklasse (spec §6.3 Prüfung 2, Outside View)."""

    id: str = Field(default_factory=lambda: _id("ref"))
    description: str = ""
    entity_ref: str = ""
    driver: str = ""
    observed_delta: float = 0.0  # best/observed annual movement of that driver
    period: str = ""
    source_ids: list[str] = Field(default_factory=list)


class CompetitorResponse(BaseModel):
    most_affected: str = ""
    likely_response: str = ""
    net_effect_adjustment: float = 0.0  # pp adjustment to the outcome (usually < 0)
    modeled: bool = False  # spec §6.3: unmodeled -> scenario is incomplete


class Simulation(BaseModel):
    id: str = Field(default_factory=lambda: _id("sim"))
    scenario_id: str = ""
    package_label: str = ""
    lever_set: list[str] = Field(default_factory=list)
    p_target_hit: float = 0.0
    outcome_median: float = 0.0
    outcome_band_80: tuple[float, float] = (0.0, 0.0)
    sensitivity: list[dict] = Field(default_factory=list)  # tornado, sorted
    competitor_response: CompetitorResponse = Field(default_factory=CompetitorResponse)
    reference_class: dict = Field(default_factory=dict)
    critical_assumptions: list[str] = Field(default_factory=list)
    breakeven: dict = Field(default_factory=dict)
    extrapolation_warnings: list[str] = Field(default_factory=list)
    denominator_warning: str = ""
    verdict: str = ""  # plausibel | ambitioniert | unplausibel ohne Strukturbruch
    incomplete: bool = False
    run_at: datetime = Field(default_factory=_now)
    model_version: str = "e8-p3-2026-07"


class Outcome(BaseModel):
    """Nachhaltemodus (spec §6.6.8)."""

    id: str = Field(default_factory=lambda: _id("out"))
    scenario_id: str = ""
    measured_at: datetime = Field(default_factory=_now)
    actual_value: float = 0.0
    deviation: float = 0.0
    learning_note: str = ""
