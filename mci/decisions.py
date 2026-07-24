"""Handlungsfelder je Entscheidungskategorie (spec §5.4).

Encodes the seven decision denkrahmen (E1–E7) and the *mandatory* output
structure the Strategist must fill — free text is not allowed. The Null-Option
is compulsory (a system that always recommends action breeds Aktionismus).

Confidence is NOT set by the LLM (spec §9). It is aggregated deterministically
from the underlying signals' confidence, and capped when nothing in the cluster
is triangulated — so the Konfidenz-Gate (spec §5.4) actually bites.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from .config import SETTINGS
from .models import Signal, SignalStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Per-decision frame (spec §5.4 table): question + result form + typical review
# horizon in days.
class DecisionFrame(BaseModel):
    code: str
    name: str
    question: str
    result_form: str
    review_horizon_days: int


DECISION_FRAMES: dict[str, DecisionFrame] = {
    "E1": DecisionFrame(
        code="E1", name="Portfolio",
        question="Welche Sortimentslücke oder welcher Variantenüberhang entsteht — "
                 "und wie lange bleibt das Fenster offen?",
        result_form="Sortimentsempfehlung mit Zeitfenster und betroffenem Umsatz",
        review_horizon_days=90),
    "E2": DecisionFrame(
        code="E2", name="Roadmap",
        question="Welches Entwicklungsfenster schließt sich wann?",
        result_form="Priorisierung mit harter Deadline und Begründung",
        review_horizon_days=60),
    "E3": DecisionFrame(
        code="E3", name="Preis/Position",
        question="Wo entsteht Preisdruck, wo bleibt Differenzierungsspielraum?",
        result_form="Positionierungsaussage und Preiskorridor-Hinweis",
        review_horizon_days=45),
    "E4": DecisionFrame(
        code="E4", name="Markt",
        question="Wo ist Nachfrage-Momentum UND Marktzugang gleichzeitig gegeben?",
        result_form="Ressourcenallokations-Empfehlung je Land",
        review_horizon_days=90),
    "E5": DecisionFrame(
        code="E5", name="Reaktion",
        question="Ignorieren, kontern, beschleunigen oder kommunikativ neutralisieren?",
        result_form="Reaktionsoptionen mit Aufwand-/Wirkungsschätzung",
        review_horizon_days=30),
    "E6": DecisionFrame(
        code="E6", name="Frühwarnung",
        question="Was verändert die Spielregeln, bevor es allgemein sichtbar wird?",
        result_form="Watchlist-Eintrag mit definiertem Beobachtungstrigger",
        review_horizon_days=30),
    "E7": DecisionFrame(
        code="E7", name="Argumentation",
        question="Was ist die belegte Faktenlage — und was ist ausdrücklich unbekannt?",
        result_form="One-Pager mit durchgehender Evidenzkette",
        review_horizon_days=120),
}


class Option(BaseModel):
    label: str
    rationale: str = ""
    effort: str = ""  # e.g. niedrig | mittel | hoch
    risk: str = ""


class ActionField(BaseModel):
    """Pflichtstruktur jedes Handlungsfelds (spec §5.4)."""

    id: str = ""
    decision_category: str
    observation: str
    signal_ids: list[str] = Field(default_factory=list)
    interpretation: str = ""
    options: list[Option] = Field(default_factory=list)  # must include Null-Option
    recommendation: str = ""
    confidence: float = 0.0
    assumptions: list[str] = Field(default_factory=list)
    falsification_trigger: str = ""
    review_date: str = ""
    known_unknowns: list[str] = Field(default_factory=list)

    # Advocatus Diaboli attached beside the recommendation (spec §5.4).
    counter_argument: str = ""
    alternative_explanation: str = ""

    # provenance
    gated: bool = False  # True when the confidence gate limited the output
    created_at: datetime = Field(default_factory=_now)
    prompt_version: str = ""
    model_id: str = ""


def aggregate_confidence(signals: list[Signal]) -> float:
    """Deterministic cluster confidence.

    Uses the strongest signal as the base, but caps at 0.5 when no signal in the
    cluster is `confirmed` — you cannot claim high strategic confidence on
    un-triangulated evidence alone.
    """
    if not signals:
        return 0.0
    base = max(s.confidence for s in signals)
    has_confirmed = any(s.status == SignalStatus.confirmed for s in signals)
    if not has_confirmed:
        base = min(base, 0.5)
    return round(base, 4)


def below_gate(confidence: float) -> bool:
    return confidence < SETTINGS.confidence_gate


def review_date_for(code: str) -> str:
    horizon = DECISION_FRAMES.get(code)
    days = horizon.review_horizon_days if horizon else 60
    return (_now() + timedelta(days=days)).date().isoformat()


def enforce_structure(field: ActionField) -> list[str]:
    """Validate the mandatory structure. Returns violations (empty == ok)."""
    problems: list[str] = []
    if field.decision_category not in DECISION_FRAMES:
        problems.append(f"unknown decision_category {field.decision_category}")
    labels = [o.label.strip().lower() for o in field.options]
    has_null = any(
        lbl in {"nichts tun", "null-option", "ignorieren", "do nothing", "beobachten"}
        for lbl in labels
    )
    if not has_null:
        problems.append("missing Null-Option (mandatory)")
    if len(field.options) < 2:
        problems.append("fewer than two options")
    if not field.signal_ids:
        problems.append("no signal_ids backing the field")
    if field.gated and field.confidence >= SETTINGS.confidence_gate:
        problems.append("gated flag set but confidence above gate")
    return problems
