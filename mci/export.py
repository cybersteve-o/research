"""Gremien-Export (spec §4 Entscheidungs-One-Pager, §7.4, §7.5).

Markdown is the guaranteed, dependency-free format. DOCX/PPTX/XLSX are produced
via optional libraries (python-docx / python-pptx / openpyxl) and raise a clear
ImportError when the library is missing — the core never depends on them.

Compliance (spec §7.5): every export is stamped as containing AI-generated
derivations, and no unverified AI derivation is presented as fact.
"""

from __future__ import annotations

from pathlib import Path

from .db import Store
from .decisions import DECISION_FRAMES, ActionField
from .scenario.models import Scenario, Simulation

AI_NOTICE = (
    "_Hinweis: Dieses Dokument enthält KI-generierte Ableitungen (gekennzeichnet). "
    "Fakten sind bis zur Originalquelle belegt; Empfehlungen sind PM-Entscheidung._"
)


# --- Entscheidungs-One-Pager (E7) -----------------------------------------
def one_pager_markdown(field: ActionField, store: Store) -> str:
    frame = DECISION_FRAMES.get(field.decision_category)
    lines = [
        f"# Entscheidungs-One-Pager — {field.decision_category} "
        f"{frame.name if frame else ''}",
        "",
        "## Situation",
        field.observation,
        "",
        "## Interpretation (KI-Ableitung)",
        field.interpretation or "—",
        "",
        "## Optionen",
    ]
    for o in field.options:
        lines.append(f"- **{o.label}** — {o.rationale} "
                     f"(Aufwand: {o.effort or '—'}, Risiko: {o.risk or '—'})")
    lines += [
        "",
        "## Empfehlung",
        field.recommendation,
        f"\n_Konfidenz: {field.confidence:.2f}"
        f"{' · unter Gate (nur beobachten/recherchieren)' if field.gated else ''}_",
        "",
        "## Gegenposition (Advocatus Diaboli)",
        f"- Stärkstes Gegenargument: {field.counter_argument or '—'}",
        f"- Alternative Erklärung: {field.alternative_explanation or '—'}",
        "",
        "## Annahmen",
    ]
    lines += [f"- {a}" for a in (field.assumptions or ["—"])]
    lines += [
        "",
        "## Falsifikations-Trigger",
        field.falsification_trigger or "—",
        f"\n**Review-Datum:** {field.review_date or '—'}",
        "",
        "## Offene Fragen (known unknowns)",
    ]
    lines += [f"- {u}" for u in (field.known_unknowns or ["—"])]

    # Evidenzkette
    lines += ["", "## Evidenz"]
    for sid in field.signal_ids:
        sig = store.get_signal(sid)
        if not sig:
            continue
        lines.append(f"- **{sig.headline}** ({sig.status.value})")
        for eid in sig.evidence_ids:
            ev = store.get_evidence(eid)
            if not ev:
                continue
            src = store.get_source(ev.source_id)
            cls = f"[{src.source_class.value}] " if src else ""
            url = src.url if src else ev.source_id
            lines.append(f"  - „{ev.quote_short}" f" — {cls}{url}")

    lines += ["", "---", AI_NOTICE]
    return "\n".join(lines)


# --- Scenario report (E8) --------------------------------------------------
def scenario_markdown(scenario: Scenario, sims: list[Simulation]) -> str:
    lines = [
        f"# Szenario / Zielprüfung — {scenario.market} "
        f"{scenario.target_value:+g} {scenario.target_metric} in "
        f"{scenario.horizon_months} Monaten",
        "",
        f"Modus: {scenario.mode} · Produktlinie: {scenario.product_line or '—'}",
        "",
        "## Strategiepakete",
        "| Paket | P(Ziel) | Median | 80%-Band | Referenz (Faktor) | "
        "Wettbewerbsreaktion | Urteil |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in sims:
        ratio = s.reference_class.get("worst_ratio_vs_best")
        cr = s.competitor_response
        cr_txt = (f"{cr.most_affected}: {cr.net_effect_adjustment:+g}pp"
                  if cr.modeled else "⚠️ nicht modelliert")
        flag = " ⚠️unvollständig" if s.incomplete else ""
        lines.append(
            f"| {s.package_label or '—'} | {s.p_target_hit:.0%} | "
            f"{s.outcome_median:+g} | [{s.outcome_band_80[0]:+g}, {s.outcome_band_80[1]:+g}] | "
            f"{ratio if ratio is not None else '—'} | {cr_txt} | "
            f"**{s.verdict}**{flag} |"
        )

    # Detail per package: sensitivity tornado, breakeven, warnings
    for s in sims:
        lines += ["", f"### Paket: {s.package_label or s.id}"]
        lines.append("**Sensitivität (Tornado, Top 3):**")
        for r in s.sensitivity[:3]:
            lines.append(f"- {r['driver']}: Swing {r['swing_pp']} pp")
        if s.breakeven:
            lines.append(
                f"**Breakeven:** {s.breakeven.get('driver')} bei "
                f"{s.breakeven.get('breakeven_value')}"
                f"{' — ' + s.breakeven['note'] if s.breakeven.get('note') else ''}"
            )
        for w in s.extrapolation_warnings:
            lines.append(f"- ⚠️ Extrapolation: {w}")
        if s.denominator_warning:
            lines.append(f"- ⚠️ {s.denominator_warning}")

    lines += ["", "---", AI_NOTICE]
    return "\n".join(lines)


def write(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- Optional Office formats ----------------------------------------------
def export_one_pager_docx(field: ActionField, store: Store, path: str | Path) -> Path:
    try:
        from docx import Document  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError("DOCX export needs python-docx (pip install python-docx)") from exc

    doc = Document()
    frame = DECISION_FRAMES.get(field.decision_category)
    doc.add_heading(f"Entscheidungs-One-Pager — {field.decision_category} "
                    f"{frame.name if frame else ''}", level=0)
    doc.add_heading("Situation", level=1)
    doc.add_paragraph(field.observation)
    doc.add_heading("Empfehlung", level=1)
    doc.add_paragraph(field.recommendation)
    doc.add_paragraph(f"Konfidenz: {field.confidence:.2f}")
    doc.add_heading("Optionen", level=1)
    for o in field.options:
        doc.add_paragraph(f"{o.label} — {o.rationale}", style="List Bullet")
    doc.add_heading("Gegenposition", level=1)
    doc.add_paragraph(field.counter_argument or "—")
    doc.add_heading("Falsifikations-Trigger", level=1)
    doc.add_paragraph(field.falsification_trigger or "—")
    doc.add_paragraph(AI_NOTICE.strip("_"))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def export_packages_xlsx(sims: list[Simulation], path: str | Path) -> Path:
    try:
        from openpyxl import Workbook  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError("XLSX export needs openpyxl (pip install openpyxl)") from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "Strategiepakete"
    ws.append(["Paket", "P(Ziel)", "Median", "Band80_lo", "Band80_hi",
               "Faktor_vs_best", "Urteil", "Unvollständig"])
    for s in sims:
        ratio = s.reference_class.get("worst_ratio_vs_best")
        ws.append([
            s.package_label, s.p_target_hit, s.outcome_median,
            s.outcome_band_80[0], s.outcome_band_80[1],
            ratio if ratio is not None else "", s.verdict, s.incomplete,
        ])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def export_one_pager_pptx(field: ActionField, path: str | Path) -> Path:
    try:
        from pptx import Presentation  # noqa: PLC0415
        from pptx.util import Inches  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError("PPTX export needs python-pptx (pip install python-pptx)") from exc

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = f"{field.decision_category}: Empfehlung"
    body = slide.placeholders[1].text_frame
    body.text = field.recommendation
    for o in field.options:
        p = body.add_paragraph()
        p.text = f"Option: {o.label}"
        p.level = 1
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path
