"""Gesamt-Empfehlung / Lagebild (requirement: „was sagt uns die Informationslage
und welche Schlüsse kann man daraus ziehen").

Synthesises across *everything* the tool holds — signals, early-warning alerts,
rising trends, correlation patterns, sentiment, decision action-fields and open
gaps — into one executive read: findings (what the data shows), conclusions
(what follows), and a short prioritised recommendation list.

Rule-based and honest: findings are facts from the store; conclusions and
recommendations are labelled interpretation, each carries its confidence, and the
open-gaps list plus a confidence figure keep the read from over-claiming. No
number is invented — the report only aggregates what is already source-linked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mci import alerts as alerts_mod
from mci import correlation, sentiment, trends
from mci import watchlist as watchlist_mod
from mci.briefing import generate_briefing
from mci.db import Store
from mci.models import SignalStatus
from mci.scoring import priority_pct


@dataclass
class Recommendation:
    action: str
    rationale: str
    priority: str = "mittel"          # hoch | mittel | niedrig
    decision_link: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class SituationReport:
    findings: list[str] = field(default_factory=list)        # what the data shows
    conclusions: list[str] = field(default_factory=list)     # what follows
    recommendations: list[Recommendation] = field(default_factory=list)
    open_gaps: list[str] = field(default_factory=list)
    confidence: float = 0.0
    n_signals: int = 0
    n_confirmed: int = 0

    @property
    def is_empty(self) -> bool:
        return self.n_signals == 0


_PRIO_ORDER = {"hoch": 0, "mittel": 1, "niedrig": 2}


def build(store: Store) -> SituationReport:
    """Aggregate the whole data basis into findings, conclusions, recommendations."""
    signals = store.list_signals()
    confirmed = [s for s in signals if s.status == SignalStatus.confirmed]
    competitors = store.list_competitors()
    rep = SituationReport(n_signals=len(signals), n_confirmed=len(confirmed))
    if not signals:
        rep.recommendations.append(Recommendation(
            action="Datenbasis aufbauen",
            rationale="Noch keine Signale erfasst — über Recherche/Upload/News einspeisen.",
            priority="hoch", decision_link=["E6"]))
        return rep

    active_alerts = alerts_mod.detect(store)
    rising = [t for t in trends.radar(store) if t.momentum > 0.1][:3]
    insights = correlation.evaluate(store)
    sent = sentiment.competitor_sentiment(store)
    fields = store.list_action_fields()
    gaps = watchlist_mod.gap_queries(store)
    briefing = generate_briefing(store)

    pct = round(100 * len(confirmed) / len(signals))
    rep.findings.append(
        f"{len(signals)} Signale erfasst, davon {len(confirmed)} bestätigt "
        f"({pct} %); {len(competitors)} Wettbewerber beobachtet.")
    for a in active_alerts[:3]:
        rep.findings.append(f"{a.icon} {a.kind}: {a.entity} — {a.headline}")
    for t in rising:
        rep.findings.append(f"🔼 Aufkommendes Thema „{t.term}“ ({t.count} Nennungen).")
    for ins in insights[:2]:
        rep.findings.append(f"🔗 Muster {ins.rule_id} ({ins.entity}): {ins.conclusion}")
    worst = min((b for b in sent if b.n >= 2), key=lambda b: b.avg_score, default=None)
    if worst and worst.avg_score < -0.15:
        rep.findings.append(f"🔴 Negative Marktstimmung zu {worst.competitor} "
                            f"(Score {worst.avg_score:+.2f}).")

    # --- conclusions (derivations) ---
    if active_alerts:
        kinds = ", ".join(sorted({a.kind for a in active_alerts}))
        rep.conclusions.append(f"Akuter Handlungs-/Beobachtungsdruck durch: {kinds}.")
    hot = {c for s in confirmed for c in s.decision_link if c.startswith("E")}
    if hot:
        rep.conclusions.append(
            f"Belastbare Signale konzentrieren sich auf Entscheidungsfelder "
            f"{', '.join(sorted(hot))} — hier zuerst entscheiden.")
    if rising:
        rep.conclusions.append(
            f"Frühzeitige Positionierung zu „{rising[0].term}“ prüfen, bevor das "
            f"Thema Mainstream wird.")
    if worst and worst.avg_score < -0.15:
        rep.conclusions.append(
            f"Schwäche bei {worst.competitor} → Differenzierungs-/Angriffschance (E3, E7).")
    if gaps:
        rep.conclusions.append(
            f"Aussagekraft noch begrenzt: {len(gaps)} offene Wissenslücken — "
            f"vor harten Entscheidungen triangulieren.")

    # --- recommendations (prioritised) ---
    for f in sorted(fields, key=lambda x: x.confidence, reverse=True)[:3]:
        prio = "hoch" if (f.confidence >= 0.6 and not getattr(f, "gated", False)) else "mittel"
        rep.recommendations.append(Recommendation(
            action=f.recommendation or f"Handlungsfeld {f.decision_category} schärfen",
            rationale=(f.interpretation or f.observation)[:160],
            priority=prio, decision_link=[f.decision_category], confidence=f.confidence))
    for a in active_alerts[:2]:
        rep.recommendations.append(Recommendation(
            action=f"Auf „{a.kind}“ bei {a.entity} reagieren/beobachten",
            rationale=a.headline, priority=a.level,
            decision_link=a.decision_link or ["E5"], confidence=0.5))
    if not fields:
        rep.recommendations.append(Recommendation(
            action="Cluster-Synthese ausführen",
            rationale="Es liegen Signale vor, aber noch keine gebündelten Handlungsfelder.",
            priority="hoch", decision_link=["E7"], confidence=0.4))
    if not rep.recommendations and briefing.cockpit:
        top = briefing.cockpit[0]
        rep.recommendations.append(Recommendation(
            action=f"Top-Signal priorisieren: {top.headline}",
            rationale=f"Höchste Priorität ({priority_pct(top.priority)}).",
            priority="mittel", decision_link=top.decision_link, confidence=top.confidence))

    rep.recommendations.sort(key=lambda r: (_PRIO_ORDER.get(r.priority, 9), -r.confidence))
    rep.recommendations = rep.recommendations[:5]

    rep.open_gaps = gaps[:6]
    base = len(confirmed) / len(signals)
    penalty = min(0.3, 0.03 * len(gaps))
    rep.confidence = round(max(0.0, base - penalty), 2)
    return rep


def narrative(rep: SituationReport) -> str:
    """A short executive summary of the report as plain prose."""
    if rep.is_empty:
        return ("Noch keine Datenbasis: Es liegen keine Signale vor. Speise über "
                "Recherche, Datei-Upload oder News-Feeds erste Quellen ein.")
    parts = [
        f"Die Informationslage umfasst {rep.n_signals} Signale "
        f"({rep.n_confirmed} bestätigt).",
    ]
    if len(rep.findings) > 1:
        parts.append("Auffällig: " + rep.findings[1].split(": ", 1)[-1] + ".")
    if rep.conclusions:
        parts.append("Schluss: " + rep.conclusions[0])
    if rep.recommendations:
        r = rep.recommendations[0]
        parts.append(f"Empfehlung ({r.priority}): {r.action}.")
    parts.append(f"Konfidenz der Gesamteinschätzung: {rep.confidence:.0%}"
                 + (f"; {len(rep.open_gaps)} offene Wissenslücken." if rep.open_gaps else "."))
    return " ".join(parts)
