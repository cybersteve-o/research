"""Export: der Beschluss-Einseiter und die Maßnahmentabelle.

Was ein Gremium mitnimmt, entscheidet, ob ein Werkzeug benutzt wird. Deshalb
enthält der Einseiter nicht nur das Paket, sondern in derselben Reihenfolge auch
das, was gegen es spricht: den unerklärten Rest, die Evidenzmischung, die
verbleibende Lücke und den Einwand des Advocatus Diaboli.

Markdown und CSV kommen ohne zusätzliche Abhängigkeiten aus. Wer DOCX oder PPTX
braucht, kann die Ausgabe durch `mci.export` schicken — die Formatierer dort
arbeiten auf denselben Strukturen.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .allocate import evidence_mix
from .bridge import Bridge
from .fmt import eur as _eur
from .link import open_gaps
from .models import CAUSE_LABELS, EVIDENCE_LABELS, INSTRUMENT_LABELS, Portfolio


def decision_one_pager(
    portfolio: Portfolio,
    bridge: Bridge,
    *,
    rationale: str = "",
    critique=None,
    title: str = "Maßnahmenbeschluss",
) -> str:
    """Der Einseiter für die Sitzung — Beschluss, Begründung und Einwände."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out: list[str] = [
        f"# {title} · {portfolio.period}",
        "",
        f"_Erstellt {stamp} · Horizont {portfolio.horizon_months} Monate · "
        f"Budgetrahmen {_eur(portfolio.budget_eur)}_",
        "",
        "## Lage",
        "",
        f"- Plan **{_eur(bridge.plan_eur)}**, Forecast **{_eur(bridge.forecast_eur)}**, "
        f"Lücke **{_eur(bridge.gap_eur)}**",
        f"- Davon adressierbar: **{_eur(bridge.addressable_eur)}** "
        f"(ohne exogene Ursachen und ohne den unerklärten Rest von "
        f"{_eur(bridge.unexplained_eur)})",
        "",
        "### Ursachen",
        "",
        "| Ursache | Betrag | Anteil | Belegt |",
        "|---|---:|---:|---|",
    ]

    confidence_by_cause: dict[str, list[float]] = {}
    for step in bridge.steps:
        if step.cause is None:
            continue
        confidence_by_cause.setdefault(
            CAUSE_LABELS[step.cause], []
        ).append(step.confidence)

    for cause, amount in bridge.by_cause():
        label = CAUSE_LABELS[cause] if cause else "Unerklärt"
        share = amount / bridge.gap_eur if bridge.gap_eur else 0.0
        confidences = confidence_by_cause.get(label, [])
        if not confidences or max(confidences) <= 0:
            evidence = "nein"
        elif max(confidences) >= 0.6:
            evidence = "ja"
        else:
            evidence = "schwach"
        out.append(f"| {label} | {_eur(amount)} | {share:.0%} | {evidence} |")

    out += [
        "",
        "## Beschlussvorschlag",
        "",
        f"**{len(portfolio.allocations)} Maßnahmen · {_eur(portfolio.cost_used_eur)} · "
        f"{portfolio.capacity_used:.0f} FTE-Monate**",
        "",
        "| Markt | Maßnahme | Träger | Dosis | Kosten | Wirkung im Horizont | "
        "Eingeschwungen p. a. | Evidenz |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for a in portfolio.allocations:
        out.append(
            f"| {a.market} | {a.measure_name} | {INSTRUMENT_LABELS[a.instrument]} | "
            f"{a.dose:.0%} | {_eur(a.cost_eur)} | "
            f"{_eur(a.effect_horizon.low)} – {_eur(a.effect_horizon.high)} | "
            f"{_eur(a.effect_run_rate.mode)} | {EVIDENCE_LABELS[a.evidence_class]} |"
        )

    out += [
        "",
        "## Was der Beschluss leistet — und was nicht",
        "",
        f"- Erwartete Wirkung im Horizont: **{_eur(portfolio.effect_horizon.low)} – "
        f"{_eur(portfolio.effect_horizon.high)}** "
        f"(Erwartungswert {_eur(portfolio.effect_horizon.mode)})",
        f"- Voll eingeschwungen: **{_eur(portfolio.effect_run_rate.mode)}** pro Jahr",
        f"- Deckung der Lücke: **{portfolio.coverage:.0%}** — "
        f"offen bleiben **{_eur(portfolio.residual_gap_eur)}**",
        f"- Anteil gemeinsam getragener Maßnahmen: **{portfolio.joint_share:.0%}**",
    ]
    mix = evidence_mix(portfolio)
    if mix:
        parts = ", ".join(f"{label} {share:.0%}" for label, share in
                          sorted(mix.items(), key=lambda t: t[1], reverse=True))
        out.append(f"- Evidenzmischung der Wirkung: {parts}")

    if portfolio.too_slow:
        out += [
            "",
            f"**Nicht in diesem Paket, weil außerhalb des Horizonts wirksam:** "
            f"{', '.join(portfolio.too_slow)}. Diese Maßnahmen gehören in die "
            f"Mehrjahresplanung — sie fallen nicht weg, sie fallen später an.",
        ]
    if portfolio.dominated:
        out.append(
            f"\n**Bewusst nicht gewählt:** {', '.join(portfolio.dominated)}."
        )

    if rationale:
        out += ["", "## Begründung", "", rationale]

    if portfolio.warnings:
        out += ["", "## Hinweise", ""]
        out += [f"- {w}" for w in portfolio.warnings]

    if critique is not None:
        out += [
            "", "## Gegenrede",
            "",
            f"**Einwand.** {critique.counter_argument}",
            "",
            f"**Alternative Lesart.** {critique.alternative_explanation}",
        ]
        if critique.blind_spots:
            out += ["", "**Blinde Flecken.**", ""]
            out += [f"- {spot}" for spot in critique.blind_spots]

    gaps = open_gaps(bridge)
    if gaps:
        out += [
            "", "## Rechercheaufträge",
            "",
            "Große Beträge mit schwachem Beleg. Diese Fragen gehören ins "
            "Recherchewerkzeug, bevor der nächste Beschluss ansteht.",
            "",
        ]
        out += [f"- {g.research_question()}" for g in gaps[:8]]

    out += [
        "", "---", "",
        "_Alle Wirkungsangaben sind Bänder, keine Punktwerte. Jede Zahl folgt aus "
        "der Kette: adressierte Lücke × Wirkungsgrad × Sättigung × Evidenzabschlag "
        "× Realisierungsanteil. Kein Wert stammt aus einem Sprachmodell._",
    ]
    return "\n".join(out)


def allocations_csv(portfolio: Portfolio) -> str:
    """Die Maßnahmentabelle als CSV — für die Weiterverarbeitung im Controlling."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "Markt", "Maßnahme", "Träger", "Dosis", "Kosten_EUR", "FTE_Monate",
        "Wirkung_Horizont_min", "Wirkung_Horizont_erwartet", "Wirkung_Horizont_max",
        "Wirkung_p_a_erwartet", "Evidenzklasse", "Periode",
    ])
    for a in portfolio.allocations:
        writer.writerow([
            a.market, a.measure_name, INSTRUMENT_LABELS[a.instrument],
            f"{a.dose:.2f}", f"{a.cost_eur:.0f}", f"{a.capacity_fte_months:.1f}",
            f"{a.effect_horizon.low:.0f}", f"{a.effect_horizon.mode:.0f}",
            f"{a.effect_horizon.high:.0f}", f"{a.effect_run_rate.mode:.0f}",
            EVIDENCE_LABELS[a.evidence_class], a.period,
        ])
    return buffer.getvalue()


def bridge_csv(bridge: Bridge) -> str:
    """Die Ursachenzerlegung als CSV, inklusive Belegdichte."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "Markt", "Ursache", "Betrag_EUR", "Konfidenz", "Signale", "Notiz",
    ])
    for step in sorted(bridge.steps, key=lambda s: s.amount_eur, reverse=True):
        writer.writerow([
            step.market,
            CAUSE_LABELS[step.cause] if step.cause else "Unerklärt",
            f"{step.amount_eur:.0f}",
            f"{step.confidence:.2f}",
            len(step.evidence_signal_ids),
            step.note,
        ])
    return buffer.getvalue()
