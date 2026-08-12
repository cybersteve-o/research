"""Drei Rollen: Diagnostiker, Begründer, Advocatus Diaboli.

Die Rollentrennung aus `mci.llm.analysis` wird hier beibehalten und ist kein
Zierrat: **der Advocatus Diaboli sieht die Begründung des Portfolios nicht.** Er
bekommt nur das Ergebnis — welche Maßnahmen, welche Beträge, welche
Evidenzklassen — und muss seinen Einwand selbst finden. Wer ihm die Begründung
zeigt, bekommt eine höfliche Umformulierung derselben Argumente zurück.

Alle drei Rollen laufen ohne API-Schlüssel weiter. Der Offline-Pfad ist keine
Notlösung, sondern der Normalfall dieser Demo: er ist regelbasiert, wiederholbar
und sagt nur Dinge, die aus den Daten folgen. Der LLM-Pfad formuliert besser und
findet mehr, aber er entscheidet nichts, was der Offline-Pfad nicht auch
entscheiden würde.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..bridge import Bridge
from ..fmt import eur as _eur
from ..models import (
    CAUSE_LABELS,
    EVIDENCE_LABELS,
    CauseCode,
    EvidenceClass,
    Instrument,
    Portfolio,
)

try:
    from mci.llm.client import AnthropicBackend
except Exception:  # noqa: BLE001  # pragma: no cover - ohne mci-Paket
    AnthropicBackend = None  # type: ignore[assignment,misc]


DIAGNOSE_SYSTEM = """\
Du bist der Diagnostiker. Du bekommst eine Brückenstufe (Markt, Ursache, Betrag)
und die dazu gefundenen Marktsignale. Formuliere in einem Satz, was die Signale
über diese Ursache aussagen. Du setzt keine Zahlen und änderst keine Beträge.
Wenn die Signale die Zuordnung nicht stützen, sagst du das ausdrücklich.
Antworte als JSON: {"statement": "..", "supports": true|false}."""

RATIONALE_SYSTEM = """\
Du bist der Begründer. Du bekommst ein fertig gerechnetes Maßnahmenportfolio und
schreibst die Beschlussbegründung: warum dieser Zuschnitt, was er nicht leistet,
welche Annahme ihn trägt. Keine neuen Zahlen, keine Werbung. Höchstens 150 Wörter.
Antworte als JSON: {"rationale": ".."}."""

ADVOCATUS_SYSTEM = """\
Du bist der Advocatus Diaboli. Du bekommst ein Maßnahmenportfolio, aber NICHT
die Begründung dafür. Nenne das stärkste Argument dagegen und die plausibelste
alternative Lesart der Lage. Antworte als JSON:
{"counter_argument": "..", "alternative_explanation": "..", "blind_spots": [".."]}."""


@dataclass
class CauseHypothesis:
    market: str
    cause: CauseCode
    statement: str
    supporting_signal_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    supported: bool = True

    @property
    def label(self) -> str:
        return CAUSE_LABELS[self.cause]


@dataclass
class PortfolioCritique:
    counter_argument: str = ""
    alternative_explanation: str = ""
    blind_spots: list[str] = field(default_factory=list)
    source: str = "offline-heuristic"


@dataclass
class GtmRoles:
    """Die Rollen, gebündelt. `backend` darf None sein — dann rein offline."""

    backend: object | None = None

    @property
    def available(self) -> bool:
        return bool(self.backend is not None and getattr(self.backend, "available", False))

    @property
    def model_id(self) -> str:
        return "claude" if self.available else "offline-heuristic"

    # ---- Diagnostiker ------------------------------------------------------
    def diagnose(self, bridge: Bridge, store=None) -> list[CauseHypothesis]:
        """Was die Signale zu jeder Brückenstufe sagen.

        Der Offline-Pfad zitiert die Schlagzeilen der stützenden Signale, statt
        sie zu paraphrasieren — ohne Sprachmodell ist eine Paraphrase nur ein
        Risiko, keine Leistung.
        """
        from ..link import evidence_for  # spät, um Zyklen zu vermeiden

        out: list[CauseHypothesis] = []
        for step in sorted(bridge.steps, key=lambda s: s.amount_eur, reverse=True):
            if step.cause is None or step.amount_eur <= 0:
                continue
            signals = evidence_for(store, step.market, step.cause) if store else []
            headlines = [getattr(s, "headline", "") for s in signals if
                         getattr(s, "headline", "")]
            if headlines:
                statement = (
                    f"{step.market}: {CAUSE_LABELS[step.cause]} mit "
                    f"{_eur(step.amount_eur)} belegt durch "
                    f"{len(headlines)} Signal(e) — "
                    + "; ".join(headlines[:2])
                )
                supported = True
            else:
                statement = (
                    f"{step.market}: {CAUSE_LABELS[step.cause]} mit "
                    f"{_eur(step.amount_eur)} ist derzeit unbelegt. Die Zuordnung "
                    f"stammt aus der Planung, nicht aus der Marktbeobachtung."
                )
                supported = False
            out.append(CauseHypothesis(
                market=step.market, cause=step.cause, statement=statement,
                supporting_signal_ids=list(step.evidence_signal_ids),
                confidence=step.confidence, supported=supported,
            ))
        return out

    # ---- Begründer ---------------------------------------------------------
    def rationale(self, portfolio: Portfolio, bridge: Bridge) -> str:
        """Die Beschlussbegründung — offline aus den Fakten des Portfolios."""
        if not portfolio.allocations:
            return (
                "Kein Portfolio zustande gekommen: Bei diesem Budget wirkt keine "
                "Maßnahme innerhalb des Horizonts genug, um die Kosten zu tragen."
            )
        top = portfolio.allocations[0]
        markets = sorted({a.market for a in portfolio.allocations})
        fast = [a for a in portfolio.allocations
                if a.effect_horizon.mode > 0 and a.dose >= 0.5]
        parts = [
            f"Das Paket setzt {_eur(portfolio.cost_used_eur)} auf "
            f"{len(portfolio.allocations)} Maßnahmen in {len(markets)} Märkten "
            f"({', '.join(markets)}) und erwartet daraus im Horizont von "
            f"{portfolio.horizon_months} Monaten "
            f"{portfolio.effect_horizon.low:,.0f} bis "
            f"{_eur(portfolio.effect_horizon.high)}.",
            f"Größter Einzelbeitrag: „{top.measure_name}“ in {top.market} mit "
            f"{_eur(top.effect_horizon.mode)}.",
            f"Voll eingeschwungen läge die Wirkung bei "
            f"{_eur(portfolio.effect_run_rate.mode)} pro Jahr — die Differenz zum "
            f"Horizontwert ist nicht verloren, sondern fällt später an.",
        ]
        if portfolio.residual_gap_eur > 0:
            parts.append(
                f"Das Paket schließt die Lücke nicht: "
                f"{_eur(portfolio.residual_gap_eur)} bleiben offen. Wer sie "
                f"schließen will, muss den Plan ändern, nicht das Budget erhöhen — "
                f"die dafür nötigen Maßnahmen wirken nicht schnell genug."
            )
        if len(fast) < len(portfolio.allocations):
            parts.append(
                f"{len(portfolio.allocations) - len(fast)} Maßnahmen laufen "
                f"bewusst auf Teildosis: ihr Grenznutzen fällt schneller als der "
                f"anderer Maßnahmen."
            )
        return " ".join(parts)

    # ---- Advocatus Diaboli -------------------------------------------------
    def challenge(self, portfolio: Portfolio, bridge: Bridge) -> PortfolioCritique:
        """Der Einwand — ohne Kenntnis der Begründung, ausschließlich aus dem Ergebnis."""
        blind: list[str] = []

        # 1. Wie viel Wirkung steht auf unbelegten Annahmen?
        if portfolio.effect_horizon.mode > 0:
            assumed = sum(a.effect_horizon.mode for a in portfolio.allocations
                          if a.evidence_class is EvidenceClass.assumed)
            share = assumed / portfolio.effect_horizon.mode
            if share > 0.25:
                blind.append(
                    f"{share:.0%} der erwarteten Wirkung stammt aus Maßnahmen der "
                    f"Klasse „{EVIDENCE_LABELS[EvidenceClass.assumed]}“. Wenn diese "
                    f"Annahme falsch ist, fehlt das Ergebnis, nicht nur der Puffer."
                )

        # 2. Klumpenrisiko Markt.
        by_market: dict[str, float] = {}
        for a in portfolio.allocations:
            by_market[a.market] = by_market.get(a.market, 0.0) + a.effect_horizon.mode
        if by_market:
            top_market, top_value = max(by_market.items(), key=lambda t: t[1])
            total = sum(by_market.values()) or 1.0
            if top_value / total > 0.5:
                blind.append(
                    f"{top_value / total:.0%} der Wirkung hängt an einem einzigen "
                    f"Markt ({top_market}). Eine lokale Fehlannahme kippt das "
                    f"ganze Paket."
                )

        # 3. Kurzfrist über Preis — der teuerste Weg, eine Lücke zu schließen.
        price_effect = sum(
            a.effect_horizon.mode for a in portfolio.allocations
            if CauseCode.price in a.addresses
        )
        if portfolio.effect_horizon.mode > 0:
            price_share = price_effect / portfolio.effect_horizon.mode
            if price_share > 0.3:
                blind.append(
                    f"{price_share:.0%} der Wirkung kommt aus Preis- und "
                    f"Konditionsmaßnahmen. Das ist Umsatz, der über die Marge "
                    f"bezahlt wird, und er lässt sich kaum zurücknehmen."
                )

        # 4. Unerklärter Rest.
        if bridge.gap_eur > 0:
            unexplained_share = bridge.unexplained_eur / bridge.gap_eur
            if unexplained_share > 0.2:
                blind.append(
                    f"{unexplained_share:.0%} der Lücke sind keiner Ursache "
                    f"zugeordnet. Das Portfolio behandelt den erklärten Teil und "
                    f"unterstellt, dass der Rest sich gleich verhält."
                )

        # 5. Trägt die Fusion?
        if portfolio.allocations and portfolio.joint_share < 0.25:
            blind.append(
                f"Nur {portfolio.joint_share:.0%} der Wirkung stammt aus gemeinsam "
                f"getragenen Maßnahmen — das Paket ist noch die Summe zweier "
                f"Abteilungsprogramme."
            )

        counter = (
            "Das Portfolio unterstellt, dass die Ursachenzerlegung stimmt. Sie ist "
            "aber genau dort am schwächsten belegt, wo die Beträge am größten sind. "
            "Ein Paket, das auf einer Zerlegung mit dieser Belegdichte aufsetzt, "
            "optimiert womöglich sehr präzise das falsche Problem."
        )
        alternative = (
            "Plausible Gegenlesart: Die Lücke ist überwiegend Nachfrage- und "
            "Preisniveaueffekt und wäre auch ohne jede Maßnahme in ähnlicher Höhe "
            "eingetreten. Dann misst das Nachhalten später den Markt und schreibt "
            "ihn den Maßnahmen gut."
        )
        if not portfolio.allocations:
            counter = ("Es gibt kein Portfolio zu kritisieren — bei diesem Budget "
                       "trägt keine Maßnahme ihre Kosten im Horizont.")
        return PortfolioCritique(
            counter_argument=counter,
            alternative_explanation=alternative,
            blind_spots=blind,
            source=self.model_id,
        )


def default_roles() -> GtmRoles:
    """Rollen mit LLM-Backend, wenn eines verfügbar ist — sonst offline."""
    backend = None
    if AnthropicBackend is not None:
        try:
            backend = AnthropicBackend()
        except Exception:  # noqa: BLE001  # pragma: no cover
            backend = None
    return GtmRoles(backend=backend)


def instrument_split(portfolio: Portfolio) -> dict[str, float]:
    """Wirkungsanteile nach Träger — Vertrieb, Marketing, gemeinsam."""
    total = portfolio.effect_horizon.mode or 1.0
    out: dict[str, float] = {}
    for a in portfolio.allocations:
        key = Instrument(a.instrument).name
        out[key] = out.get(key, 0.0) + a.effect_horizon.mode / total
    return out
