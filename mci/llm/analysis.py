"""Phase-2 roles: Analyst, Strategist, Advocatus Diaboli (spec §5.1, §5.4).

Each has an LLM path and a deterministic offline fallback. Role separation is
preserved (spec §5.1): the Advocatus Diaboli receives the recommendation but
NOT its rationale, so its counter-argument is genuinely independent.

None of these roles set scores. The Analyst names *affected lines*; the impact
number is computed from the dossier's revenue weights. The Strategist's
confidence is aggregated from the underlying signals, not authored.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import SETTINGS
from ..context import ContextDossier
from ..decisions import (
    DECISION_FRAMES,
    ActionField,
    Option,
    aggregate_confidence,
    below_gate,
    review_date_for,
)
from ..models import Signal
from ..scoring import impact_from_revenue_weight
from .client import AnthropicBackend

ANALYST_SYSTEM = """\
You are the Analyst. Assess a signal in the company's context (dossier provided).
Name which OWN product lines are affected and estimate the reaction window in
months. You provide categories and justifications, never finished numbers
(spec §5.3). Output JSON: {"affected_lines":[..], "reaction_window_months": n,
"reach":"..", "rationale":".."}."""

STRATEGIST_SYSTEM = """\
You are the Strategist. Given a cluster of signals for ONE decision category,
produce exactly the mandatory action-field structure. At least two options
including the Null-Option ("Nichts tun"). Do NOT set confidence — it is computed.
Below the confidence gate you may only recommend "beobachten mit Trigger" or
"gezielt recherchieren". Output the action-field JSON."""

ADVOCATUS_SYSTEM = """\
You are the Advocatus Diaboli. You receive a recommendation and the signals, but
NOT the reasoning behind the recommendation. Provide the strongest argument
against it and the most plausible alternative explanation of the signals.
Output JSON: {"counter_argument":"..", "alternative_explanation":".."}."""


@dataclass
class AnalystAssessment:
    affected_lines: list[str]
    revenue_weight: float
    impact: int
    reaction_window_months: float | None
    reach: str
    rationale: str


@dataclass
class DecisionRoles:
    backend: AnthropicBackend

    @property
    def model_id(self) -> str:
        return SETTINGS.models.strong if self.backend.available else "offline-heuristic"

    # ---- Analyst -----------------------------------------------------------
    def assess(self, signal: Signal, dossier: ContextDossier | None) -> AnalystAssessment:
        if self.backend.available:
            try:
                ctx = dossier.as_prompt_context() if dossier else "(kein Dossier)"
                data = self.backend.complete_json(
                    system=ANALYST_SYSTEM,
                    user=f"{ctx}\n\nSIGNAL fact: {signal.fact}\n"
                    f"decision_link: {signal.decision_link}\n"
                    f"entities: {signal.entities.model_dump()}",
                    model=SETTINGS.models.strong,
                    max_tokens=600,
                )
                return self._assemble_assessment(signal, dossier, data)
            except Exception:
                pass
        return self._offline_assess(signal, dossier)

    def _assemble_assessment(
        self, signal: Signal, dossier: ContextDossier | None, data: dict
    ) -> AnalystAssessment:
        affected = data.get("affected_lines") or signal.entities.products
        weight = dossier.revenue_weight_for(affected) if dossier else 0.0
        return AnalystAssessment(
            affected_lines=affected,
            revenue_weight=weight,
            impact=impact_from_revenue_weight(weight) if dossier else signal.impact,
            reaction_window_months=data.get("reaction_window_months"),
            reach=data.get("reach", ""),
            rationale=data.get("rationale", ""),
        )

    def _offline_assess(
        self, signal: Signal, dossier: ContextDossier | None
    ) -> AnalystAssessment:
        affected = list(signal.entities.products)
        if not affected and dossier:
            low = signal.fact.lower()
            affected = [
                w.line for w in dossier.product_weights
                if w.line.lower() in low
            ]
            affected = list(dict.fromkeys(affected))
        weight = dossier.revenue_weight_for(affected) if dossier else 0.0
        impact = impact_from_revenue_weight(weight) if dossier else signal.impact
        return AnalystAssessment(
            affected_lines=affected,
            revenue_weight=weight,
            impact=impact,
            reaction_window_months=None,
            reach="offline: Reichweite nicht bewertet",
            rationale="offline heuristic; impact aus Umsatzgewicht der betroffenen Linien",
        )

    # ---- Strategist --------------------------------------------------------
    def synthesize(
        self,
        decision_code: str,
        signals: list[Signal],
        dossier: ContextDossier | None,
    ) -> ActionField:
        confidence = aggregate_confidence(signals)
        gated = below_gate(confidence)
        if self.backend.available and not gated:
            try:
                field = self._llm_synthesize(decision_code, signals, dossier, confidence)
                if field is not None:
                    return field
            except Exception:
                pass
        return self._offline_synthesize(decision_code, signals, confidence, gated)

    def _llm_synthesize(self, decision_code, signals, dossier, confidence) -> ActionField | None:
        ctx = dossier.as_prompt_context() if dossier else "(kein Dossier)"
        frame = DECISION_FRAMES[decision_code]
        facts = "\n".join(f"- ({s.id}) {s.fact}" for s in signals)
        data = self.backend.complete_json(
            system=STRATEGIST_SYSTEM,
            user=f"{ctx}\n\nKATEGORIE {decision_code} — {frame.name}\n"
            f"FRAGE: {frame.question}\nERGEBNISFORM: {frame.result_form}\n\n"
            f"SIGNALE:\n{facts}",
            model=SETTINGS.models.strong,
            max_tokens=1400,
        )
        options = [Option(**o) for o in data.get("options", [])]
        field = ActionField(
            decision_category=decision_code,
            observation=data.get("observation", ""),
            signal_ids=[s.id for s in signals],
            interpretation=data.get("interpretation", ""),
            options=options or self._default_options(signals),
            recommendation=data.get("recommendation", ""),
            confidence=confidence,  # computed, not from LLM
            assumptions=data.get("assumptions", []),
            falsification_trigger=data.get("falsification_trigger", ""),
            review_date=review_date_for(decision_code),
            known_unknowns=_collect_unknowns(signals),
            gated=False,
            prompt_version=SETTINGS.prompt_version,
            model_id=self.model_id,
        )
        return field

    def _offline_synthesize(
        self, decision_code: str, signals: list[Signal], confidence: float, gated: bool
    ) -> ActionField:
        frame = DECISION_FRAMES[decision_code]
        top = max(signals, key=lambda s: s.priority)
        observation = (
            f"{len(signals)} Signal(e) in Kategorie {decision_code} ({frame.name}); "
            f"stärkstes: {top.headline}"
        )
        interpretation = top.derivation or frame.question

        if gated:
            # Below the gate: only observe/research, no action recommendation.
            options = [
                Option(label="Beobachten", rationale="Konfidenz unter Gate",
                       effort="niedrig", risk="verpasstes Fenster"),
                Option(label="Gezielt recherchieren",
                       rationale="Wissenslücken schließen", effort="niedrig", risk="Zeit"),
            ]
            recommendation = (
                f"Konfidenz {confidence:.2f} < Gate {SETTINGS.confidence_gate}: "
                f"beobachten mit Trigger bzw. gezielt recherchieren — keine "
                f"Handlungsempfehlung."
            )
        else:
            options = self._default_options(signals)
            recommendation = (
                f"Option '{options[1].label}' — {frame.result_form}. "
                f"Gestützt auf {len(signals)} Signal(e), Konfidenz {confidence:.2f}."
            )

        return ActionField(
            decision_category=decision_code,
            observation=observation,
            signal_ids=[s.id for s in signals],
            interpretation=interpretation,
            options=options,
            recommendation=recommendation,
            confidence=confidence,
            assumptions=[f"Signalstatus: {top.status.value}"],
            falsification_trigger=(
                f"Wenn innerhalb des Reviewzeitraums kein weiteres Signal die "
                f"Beobachtung stützt oder ein widersprechendes Signal auftritt."
            ),
            review_date=review_date_for(decision_code),
            known_unknowns=_collect_unknowns(signals),
            gated=gated,
            prompt_version=SETTINGS.prompt_version,
            model_id=self.model_id,
        )

    @staticmethod
    def _default_options(signals: list[Signal]) -> list[Option]:
        top = max(signals, key=lambda s: s.priority)
        return [
            Option(label="Nichts tun", rationale="Null-Option: Signal beobachten",
                   effort="keiner", risk="verpasstes Zeitfenster"),
            Option(label="Handeln auf stärkstes Signal",
                   rationale=top.derivation[:120] or top.headline,
                   effort="mittel", risk="Fehlallokation bei Fehlinterpretation"),
        ]

    # ---- Advocatus Diaboli -------------------------------------------------
    def counter(self, field: ActionField, signals: list[Signal]) -> ActionField:
        """Attach counter-argument + alternative explanation (spec §5.4).

        Receives recommendation + signals but NOT the interpretation/reasoning.
        """
        if self.backend.available:
            try:
                facts = "\n".join(f"- {s.fact}" for s in signals)
                data = self.backend.complete_json(
                    system=ADVOCATUS_SYSTEM,
                    user=f"RECOMMENDATION: {field.recommendation}\n\nSIGNALS:\n{facts}",
                    model=SETTINGS.models.strong,
                    max_tokens=500,
                )
                field.counter_argument = data.get("counter_argument", "")
                field.alternative_explanation = data.get("alternative_explanation", "")
                return field
            except Exception:
                pass
        # Offline counter-pass.
        unconfirmed = [s for s in signals if s.status.value != "confirmed"]
        field.counter_argument = (
            f"{len(unconfirmed)} von {len(signals)} Signalen sind unbestätigt; "
            f"die Empfehlung könnte auf Rauschen beruhen. Null-Option prüfen."
        )
        field.alternative_explanation = (
            "Die Signale könnten Kommunikation/Signaling des Wettbewerbers sein, "
            "nicht tatsächliche Handlung — beobachtbarer Trigger nötig."
        )
        return field


def _collect_unknowns(signals: list[Signal]) -> list[str]:
    out: list[str] = []
    for s in signals:
        out.extend(s.known_unknowns)
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]
