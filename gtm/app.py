"""Streamlit-Cockpit — Wirkung und Allokation.

Start:  streamlit run gtm/app.py

Die Reiter folgen dem Weg der Entscheidung, links nach rechts:

    Lückenbild ▸ Maßnahmen ▸ Allokation ▸ Zeitachse ▸ Nachhalten ▸ Playbooks ▸ Beschluss

Diese Oberfläche ist optional. Das Paket und seine Tests hängen nicht an
Streamlit; wer nur rechnen will, nimmt `gtm.allocate` direkt.
"""

from __future__ import annotations

import os
import sys

# `import gtm` funktionieren lassen, wenn die Datei als Skript gestartet wird —
# dann liegt nur ihr eigener Ordner auf sys.path, nicht das Repo-Wurzelverzeichnis.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st

from gtm import chartdata, charts, demo_data, fmt, forecast as forecast_io
from gtm.allocate import allocate, evidence_mix, frontier, summary_lines
from gtm.bridge import build as build_bridge
from gtm.catalog import MEASURE_CATALOG, uncovered_causes
from gtm.config import SETTINGS
from gtm.effects import breakdown
from gtm.export import allocations_csv, bridge_csv, decision_one_pager
from gtm.link import attach_evidence, evidence_summary, open_gaps
from gtm.llm.roles import default_roles
from gtm.models import (
    CAUSE_LABELS,
    EVIDENCE_LABELS,
    INSTRUMENT_LABELS,
    Band,
    MeasureOutcome,
)
from gtm.playbook import similarity, transfer_candidates
from gtm.store import Store
from gtm.tracking import expectations_from, report as track_report

st.set_page_config(page_title="Wirkungs- & Allokationscockpit",
                   page_icon="🎯", layout="wide")


# Formatierung kommt aus gtm.fmt, damit die Oberflaeche und der Export
# dieselbe Schreibweise verwenden.
_eur = fmt.eur
_mio = fmt.mio


# --------------------------------------------------------------------------
# Daten
# --------------------------------------------------------------------------
def _load_state() -> None:
    """Planzeilen und Ursachen in die Sitzung laden — Demokorpus als Vorgabe."""
    if "figures" not in st.session_state:
        st.session_state.figures = demo_data.plan_figures()
        st.session_state.attributions = demo_data.attributions()
        st.session_state.source_label = "Demokorpus"
    if "outcomes" not in st.session_state:
        st.session_state.outcomes = demo_data.historical_outcomes()


def _open_mci_store():
    """Den MCI-Speicher öffnen, falls vorhanden."""
    try:
        from mci.db import Store as MciStore
    except Exception:  # noqa: BLE001
        return None, "MCI-Paket nicht importierbar"
    if not SETTINGS.mci_db_path.exists():
        return None, f"keine Datenbank unter {SETTINGS.mci_db_path}"
    try:
        return MciStore(SETTINGS.mci_db_path), ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


_load_state()

# --------------------------------------------------------------------------
# Seitenleiste
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Datenstand")
    st.caption(f"Quelle: **{st.session_state.source_label}**")
    if st.session_state.source_label == "Demokorpus":
        st.warning("Erfundene Zahlen. Die Kopplung an den Forecast ist erzählt, "
                   "nicht echt.", icon="⚠️")

    uploaded = st.file_uploader(
        "Forecast ersetzen (CSV: market; line; period; plan_eur; forecast_eur)",
        type=["csv"],
    )
    if uploaded is not None:
        try:
            text = uploaded.getvalue().decode("utf-8-sig")
            import csv as _csv
            delimiter = ";" if ";" in text.split("\n", 1)[0] else ","
            rows = list(_csv.DictReader(text.splitlines(), delimiter=delimiter))
            result = forecast_io.from_rows(rows, source="csv")
            if result.ok:
                st.session_state.figures = result.figures
                st.session_state.source_label = f"CSV · {uploaded.name}"
                st.session_state.attributions = []
                st.success(f"{len(result.figures)} Planzeilen übernommen.")
                for warning in result.warnings:
                    st.caption(f"⚠️ {warning}")
            else:
                st.error("Keine verwertbaren Zeilen gefunden.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Datei nicht lesbar: {exc}")

    st.divider()
    st.markdown("### Kopplung Recherche")
    _mci_store, _mci_reason = _open_mci_store()
    if _mci_store is not None:
        st.success("MCI-Speicher verbunden", icon="🔗")
    else:
        st.info(f"Nicht verbunden — {_mci_reason}. Die Ursachen bleiben unbelegt.",
                icon="🔌")

    st.divider()
    st.markdown("### Rahmen")
    period = st.selectbox("Periode", sorted({f.period for f in st.session_state.figures}))
    all_markets = sorted({f.market for f in st.session_state.figures})
    markets = st.multiselect("Märkte", all_markets, default=all_markets)
    horizon = st.slider("Horizont (Monate)", 6, 36, SETTINGS.horizon_months, step=3)
    budget = st.slider("Budget (€)", 0, 6_000_000,
                       int(SETTINGS.default_budget_eur), step=100_000)
    capacity = st.slider("Kapazität (FTE-Monate)", 10, 400,
                         int(SETTINGS.default_capacity_fte_months), step=10)
    max_measures = st.slider("Gleichzeitig steuerbare Maßnahmen", 3, 30,
                             SETTINGS.default_max_measures)

# --------------------------------------------------------------------------
# Rechnen
# --------------------------------------------------------------------------
bridge = build_bridge(
    st.session_state.figures, st.session_state.attributions,
    period=period, markets=markets or None,
)
if _mci_store is not None:
    attach_evidence(bridge, _mci_store)

portfolio = allocate(
    bridge, MEASURE_CATALOG,
    budget_eur=float(budget),
    capacity_fte_months=float(capacity),
    horizon_months=horizon,
    market_factors=demo_data.MARKET_COST_FACTORS,
    max_measures=max_measures,
)
roles = default_roles()
rationale = roles.rationale(portfolio, bridge)
critique = roles.challenge(portfolio, bridge)
measures_by_id = {m.id: m for m in MEASURE_CATALOG}

st.title("Wirkungs- & Allokationscockpit")
st.caption(
    "Die dritte Säule: der Forecast sagt, wo wir landen · die Recherche sagt, "
    "warum · hier steht, was wir tun — und ob es gewirkt hat."
)

head = st.columns(4)
head[0].metric("Lücke gegen Plan", _mio(bridge.gap_eur))
head[1].metric("Davon adressierbar", _mio(bridge.addressable_eur),
               help="Ohne exogene Ursachen und ohne den unerklärten Rest.")
head[2].metric("Wirkung im Horizont", _mio(portfolio.effect_horizon.mode),
               help=f"Band: {_eur(portfolio.effect_horizon.low)} bis "
                    f"{_eur(portfolio.effect_horizon.high)}")
head[3].metric("Eingesetzt", _mio(portfolio.cost_used_eur),
               help=f"Von {_eur(portfolio.budget_eur)} Budgetrahmen.")

tabs = st.tabs([
    "Lückenbild", "Maßnahmen", "Allokation", "Zeitachse",
    "Nachhalten", "Playbooks", "Beschluss",
])

# --------------------------------------------------------------------------
# 1 · Lückenbild
# --------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Woraus die Lücke besteht")
    st.caption(
        "Plan minus Forecast, zerlegt in Ursachen. Was die Zerlegung nicht "
        "erklärt, bleibt als eigene Stufe stehen — es wird nicht auf die anderen "
        "verteilt."
    )
    chart = charts.bridge_waterfall(chartdata.waterfall_rows(bridge))
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Ursachen**")
        st.dataframe(
            [
                {
                    "Ursache": CAUSE_LABELS[cause] if cause else "Unerklärt",
                    "Betrag": _eur(amount),
                    "Anteil": f"{amount / bridge.gap_eur:.0%}" if bridge.gap_eur else "—",
                    "Bearbeitbar": "nein" if (cause is None or cause.value == "market_volume")
                                   else "ja",
                }
                for cause, amount in bridge.by_cause()
            ],
            use_container_width=True, hide_index=True,
        )
    with right:
        st.markdown("**Belegdichte**")
        evidence_chart = charts.evidence_stack(chartdata.evidence_rows(bridge))
        if evidence_chart is not None:
            st.altair_chart(evidence_chart, use_container_width=True)
        else:
            st.caption("Ohne verbundenen MCI-Speicher gibt es keine Belege — "
                       "jede Ursache steht dann allein auf der Planung.")
        for label, amount in evidence_summary(bridge).items():
            st.write(f"{label}: **{_eur(amount)}**")

    for warning in bridge.warnings:
        st.warning(warning, icon="⚠️")

    gaps = open_gaps(bridge)
    if gaps:
        st.markdown("**Rechercheaufträge** — großer Betrag, schwacher Beleg")
        st.caption("Diese Fragen gehören zurück ins Recherchewerkzeug. "
                   "Hier schließt sich der Kreis zwischen den drei Säulen.")
        for gap in gaps[:8]:
            st.write(f"· {gap.research_question()}")

# --------------------------------------------------------------------------
# 2 · Maßnahmen
# --------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Der gemeinsame Katalog")
    st.caption(
        "Vertrieb und Marketing in einer Tabelle, mit denselben Feldern und "
        "demselben Maßstab. Solange beide getrennte Listen führen, entscheidet "
        "in der Budgetrunde die lautere Stimme."
    )
    st.dataframe(
        [
            {
                "Maßnahme": m.name,
                "Träger": INSTRUMENT_LABELS[m.instrument],
                "Ursachen": ", ".join(CAUSE_LABELS[c] for c in m.addresses),
                "Wirkungsgrad": f"{m.effect_grade.low:.0%} / {m.effect_grade.mode:.0%} "
                                f"/ {m.effect_grade.high:.0%}",
                "Evidenz": EVIDENCE_LABELS[m.evidence_class],
                "Wirkzeit": f"{m.time_to_effect_months} Mon.",
                "Kosten (Basis)": _eur(m.cost_full_eur),
                "Reversibilität": m.reversibility,
            }
            for m in MEASURE_CATALOG
        ],
        use_container_width=True, hide_index=True,
    )

    missing = [c for c in uncovered_causes() if c.value != "market_volume"]
    if missing:
        st.warning(
            "Der Katalog kennt keine Maßnahme gegen: "
            + ", ".join(CAUSE_LABELS[c] for c in missing),
            icon="⚠️",
        )

    st.divider()
    st.subheader("Was im Horizont überhaupt ankommt")
    st.caption(
        f"Anteil der Jahreswirkung, der innerhalb von {horizon} Monaten anfällt. "
        f"Maßnahmen bei null sind nicht schlecht — sie sind zu langsam für "
        f"diesen Zeitraum."
    )
    realization_chart = charts.realization_bars(
        chartdata.realization_curve(MEASURE_CATALOG, horizon)
    )
    if realization_chart is not None:
        st.altair_chart(realization_chart, use_container_width=True)

    st.divider()
    st.subheader("Woher kommt die Zahl?")
    st.caption("Die vollständige Rechenkette einer einzelnen Maßnahme.")
    col_a, col_b, col_c = st.columns(3)
    pick = col_a.selectbox("Maßnahme", [m.name for m in MEASURE_CATALOG])
    pick_market = col_b.selectbox("Markt", bridge.markets or ["—"])
    pick_dose = col_c.slider("Dosis", 0.0, 1.0, 1.0, step=0.05)
    chosen = next(m for m in MEASURE_CATALOG if m.name == pick)
    if bridge.markets:
        detail = breakdown(
            chosen, bridge.steps_for_market(pick_market), pick_dose, horizon,
            market=pick_market,
            market_factor=demo_data.MARKET_COST_FACTORS.get(pick_market, 1.0),
        )
        st.dataframe(
            [{"Schritt": step, "Wert": value} for step, value in detail.as_rows()],
            use_container_width=True, hide_index=True,
        )
        if chosen.evidence_basis:
            st.caption("Evidenzbasis: " + " · ".join(chosen.evidence_basis))
        else:
            st.caption("Keine Evidenzbasis hinterlegt — die Wirkung ist eine "
                       "Annahme und wird entsprechend abgewertet.")

# --------------------------------------------------------------------------
# 3 · Allokation
# --------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Das Paket")
    for line in summary_lines(portfolio):
        st.write(f"· {line}")

    measure_chart = charts.measure_bars(chartdata.measure_rows(portfolio))
    if measure_chart is not None:
        st.altair_chart(measure_chart, use_container_width=True)
    else:
        st.info("Bei diesem Budget trägt keine Maßnahme ihre Kosten im Horizont.")

    st.dataframe(
        [
            {
                "Markt": a.market,
                "Maßnahme": a.measure_name,
                "Träger": INSTRUMENT_LABELS[a.instrument],
                "Dosis": f"{a.dose:.0%}",
                "Kosten": _eur(a.cost_eur),
                "Wirkung (Band)": f"{_eur(a.effect_horizon.low)} – "
                                  f"{_eur(a.effect_horizon.high)}",
                "p. a. eingeschwungen": _eur(a.effect_run_rate.mode),
                "Evidenz": EVIDENCE_LABELS[a.evidence_class],
            }
            for a in portfolio.allocations
        ],
        use_container_width=True, hide_index=True,
    )

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Wirkung je Träger**")
        st.caption("Der Anteil gemeinsam getragener Maßnahmen ist die "
                   "Integrationskennzahl der zusammengeführten Einheit.")
        st.dataframe(
            [
                {"Träger": r["instrument"], "Wirkung": _eur(r["effect"]),
                 "Kosten": _eur(r["cost"]), "Anteil": f"{r['share']:.0%}"}
                for r in chartdata.instrument_rows(portfolio)
            ],
            use_container_width=True, hide_index=True,
        )
    with cols[1]:
        st.markdown("**Lücke gegen Wirkung je Markt**")
        market_chart = charts.market_coverage(
            chartdata.market_rows(portfolio, bridge)
        )
        if market_chart is not None:
            st.altair_chart(market_chart, use_container_width=True)

    st.divider()
    st.subheader("Effizienzgrenze")
    st.caption(
        "Was jedes Budgetniveau bringt. Der Grenzertrag steht zweimal da: im "
        "Horizont fällt er schnell unter eins, weil Aufbaumaßnahmen im ersten "
        "Jahr wenig liefern. Erst wenn beide Kurven unter der gestrichelten "
        "Linie liegen, ist zusätzliches Budget wirklich verschwendet."
    )
    points = frontier(
        bridge, MEASURE_CATALOG,
        budgets=[b for b in [250_000, 500_000, 750_000, 1_000_000, 1_500_000,
                             2_000_000, 2_500_000, 3_500_000, 5_000_000]],
        capacity_fte_months=float(capacity), horizon_months=horizon,
        market_factors=demo_data.MARKET_COST_FACTORS, max_measures=max_measures,
    )
    fcols = st.columns(2)
    with fcols[0]:
        fchart = charts.frontier_lines(chartdata.frontier_rows(points))
        if fchart is not None:
            st.altair_chart(fchart, use_container_width=True)
    with fcols[1]:
        mchart = charts.marginal_lines(chartdata.marginal_rows(points))
        if mchart is not None:
            st.altair_chart(mchart, use_container_width=True)

    st.divider()
    left, right = st.columns(2)
    with left:
        if portfolio.dominated:
            st.markdown("**Bewusst nicht gewählt**")
            st.caption("Wirkt im Horizont, verliert aber gegen bessere Maßnahmen "
                       "oder trägt die eigenen Kosten nicht.")
            for name in portfolio.dominated:
                st.write(f"· {name}")
    with right:
        if portfolio.too_slow:
            st.markdown("**Zu langsam für diesen Horizont**")
            st.caption("Gehört ins Mehrjahresbudget. Fällt nicht weg — fällt später an.")
            for name in portfolio.too_slow:
                st.write(f"· {name}")

    for warning in portfolio.warnings:
        st.warning(warning, icon="⚠️")

    st.divider()
    st.markdown("**Begründung**")
    st.write(rationale)
    st.markdown(f"**Einwand** _(Quelle: {critique.source} — kennt das Ergebnis, "
                f"nicht die Begründung)_")
    st.write(critique.counter_argument)
    st.write(critique.alternative_explanation)
    for spot in critique.blind_spots:
        st.write(f"· {spot}")

# --------------------------------------------------------------------------
# 4 · Zeitachse
# --------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Wann die Wirkung ankommt")
    st.caption(
        "Das annualisierte Wirkungsniveau des Pakets über die Zeit. Die "
        "gestrichelte Linie ist der Horizont: alles rechts davon ist beschlossen, "
        "aber im Betrachtungszeitraum nicht verdient."
    )
    timeline = charts.effect_timeline(
        chartdata.timeline_rows(portfolio, measures_by_id, months=36), horizon
    )
    if timeline is not None:
        st.altair_chart(timeline, use_container_width=True)

    tcols = st.columns(3)
    tcols[0].metric("Im Horizont", _mio(portfolio.effect_horizon.mode))
    tcols[1].metric("Eingeschwungen p. a.", _mio(portfolio.effect_run_rate.mode))
    delta = portfolio.effect_run_rate.mode - portfolio.effect_horizon.mode
    tcols[2].metric("Erst nach dem Horizont", _mio(delta),
                    help="Nicht verloren — nur später.")

    st.info(
        "Wer die Jahreslücke schließen will, hat nur die schnell wirkenden Hebel. "
        "Die sind fast alle preisnah und gehen damit auf die Marge. Das ist keine "
        "Eigenart dieses Modells, sondern die Lage — das Werkzeug macht sie nur "
        "sichtbar, bevor die Diskussion beginnt.",
        icon="⏱️",
    )

# --------------------------------------------------------------------------
# 5 · Nachhalten
# --------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Erwartet gegen eingetreten")
    st.caption(
        "Ohne diesen Reiter ist das Cockpit ein Vorschlagsgenerator. Mit ihm "
        "bekommt es eine Bilanz. Offene Maßnahmen zählen nie als Treffer."
    )
    outcomes = st.session_state.outcomes
    rep = track_report(
        outcomes,
        instrument_of=demo_data.instrument_map(),
        evidence_of=demo_data.evidence_map(),
    )
    mcols = st.columns(4)
    mcols[0].metric("Gemessen", f"{rep.n_measured} / {rep.n_total}")
    mcols[1].metric("Trefferquote",
                    f"{rep.hit_rate:.0%}" if rep.hit_rate is not None else "—")
    mcols[2].metric("Optimismus-Bias",
                    f"{rep.optimism_bias:+.0%}" if rep.optimism_bias is not None else "—",
                    help="Positiv = die Ergebnisse fielen schwächer aus als erwartet.")
    mcols[3].metric("Erwartet vs. Ist",
                    f"{_mio(rep.actual_eur)}",
                    delta=_eur(rep.actual_eur - rep.expected_eur))

    for line in rep.lines:
        st.write(f"· {line}")

    dots = charts.outcome_dots(chartdata.outcome_rows(outcomes))
    if dots is not None:
        st.altair_chart(dots, use_container_width=True)

    st.markdown("**Schlagseite je Träger**")
    st.dataframe(
        [
            {"Träger": r.label, "Gemessen": r.n,
             "Bias": f"{r.bias:+.0%}" if r.bias is not None else "—",
             "Trefferquote": f"{r.hit_rate:.0%}" if r.hit_rate is not None else "—"}
            for r in rep.by_instrument
        ],
        use_container_width=True, hide_index=True,
    )

    st.markdown("**Kalibrierung der Evidenzabschläge**")
    st.caption(
        "Die Selbstkorrektur des Werkzeugs: stimmen die Abschläge, mit denen "
        "unbelegte Maßnahmen bewertet werden? Der Vorschlag wird berechnet, aber "
        "nie automatisch übernommen — ein Modell, das seine Parameter still "
        "nachzieht, ist nicht mehr prüfbar."
    )
    st.dataframe(
        [
            {"Evidenzklasse": r.label, "Fälle": r.n,
             "Ist/Erwartung": f"{r.mean_ratio:.2f}" if r.mean_ratio is not None else "—",
             "Abschlag heute": f"{r.current_discount:.2f}",
             "Vorschlag": f"{r.suggested_discount:.2f}" if r.suggested_discount else "—",
             "Befund": r.note}
            for r in rep.calibration
        ],
        use_container_width=True, hide_index=True,
    )

    st.divider()
    st.markdown("**Erwartung dieses Pakets einfrieren**")
    st.caption(
        "Der entscheidende Schritt: die Erwartung wird vor dem Ergebnis "
        "festgeschrieben. Wer erst hinterher notiert, was er erwartet hatte, misst "
        "seine Erinnerung, nicht seine Prognose."
    )
    owner = st.text_input("Verantwortlich", value="")
    if st.button("Erwartung festschreiben", type="primary",
                 disabled=not portfolio.allocations):
        SETTINGS.ensure_dirs()
        with Store(SETTINGS.db_path) as store:
            store.save_portfolio(portfolio)
            frozen = expectations_from(portfolio, owner=owner)
            for outcome in frozen:
                store.upsert_outcome(outcome)
        st.success(
            f"{len(portfolio.allocations)} Erwartungen gespeichert unter "
            f"{SETTINGS.db_path}. Ab jetzt zählt, was wirklich passiert."
        )

# --------------------------------------------------------------------------
# 6 · Playbooks
# --------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Was sich global weiterreichen lässt")
    st.caption(
        "Das Skalenversprechen einer global aufgestellten Einheit: eine gemessene "
        "Wirkung in einem Markt ist anderswo etwas wert — meistens teilweise, und "
        "genau dieses Teilweise ist die Zahl."
    )
    profiles = demo_data.market_profiles()
    pcols = st.columns([2, 3])
    with pcols[0]:
        matrix = charts.similarity_matrix(
            chartdata.similarity_rows(profiles, similarity)
        )
        if matrix is not None:
            st.altair_chart(matrix, use_container_width=True)
    with pcols[1]:
        st.dataframe(
            [
                {"Markt": p.market,
                 "Kanalstruktur": f"{p.channel_concentration:.2f}",
                 "Regulierung": f"{p.regulation_intensity:.2f}",
                 "Wettbewerbsdichte": f"{p.competitive_density:.2f}",
                 "Reife": f"{p.maturity:.2f}",
                 "Preisniveau": f"{p.price_level:.2f}"}
                for p in profiles.values()
            ],
            use_container_width=True, hide_index=True,
        )
        st.caption("Die Gewichte der Ähnlichkeit sind eine Setzung, keine Messung.")

    candidates = transfer_candidates(st.session_state.outcomes, profiles)
    recommended = [c for c in candidates if c.recommended]
    st.markdown(f"**{len(recommended)} von {len(candidates)} Transfers empfohlen**")
    for cand in recommended[:10]:
        with st.expander(
            f"{cand.source_market} → {cand.target_market} · {cand.measure_name} "
            f"· Übertragbarkeit {cand.transferability:.2f} ({cand.verdict})"
        ):
            st.write(
                f"Im Ursprungsmarkt gemessen: **{_eur(cand.source_effect_eur)}**. "
                f"Erwartet im Zielmarkt: **{_eur(cand.expected_effect.low)} – "
                f"{_eur(cand.expected_effect.high)}**."
            )
            st.write(f"Marktähnlichkeit {cand.similarity:.2f} · "
                     f"Belegstärke {cand.evidence_strength:.2f}")
            for caveat in cand.caveats:
                st.write(f"⚠ {caveat}")
            if not cand.caveats:
                st.write("Keine strukturellen Einwände gefunden.")

# --------------------------------------------------------------------------
# 7 · Beschluss
# --------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Der Einseiter für die Sitzung")
    st.caption(
        "Enthält in derselben Reihenfolge, was das Paket leistet und was gegen es "
        "spricht. Ein Beschlusspapier ohne Gegenrede ist eine Verkaufsunterlage."
    )
    one_pager = decision_one_pager(
        portfolio, bridge, rationale=rationale, critique=critique
    )
    st.download_button("Einseiter herunterladen (Markdown)", one_pager,
                       file_name=f"massnahmenbeschluss_{portfolio.period}.md",
                       mime="text/markdown", type="primary")
    dcols = st.columns(2)
    dcols[0].download_button("Maßnahmen als CSV", allocations_csv(portfolio),
                             file_name=f"massnahmen_{portfolio.period}.csv",
                             mime="text/csv")
    dcols[1].download_button("Ursachenzerlegung als CSV", bridge_csv(bridge),
                             file_name=f"luecke_{portfolio.period}.csv",
                             mime="text/csv")
    st.divider()
    st.markdown(one_pager)
