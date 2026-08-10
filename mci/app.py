"""Streamlit cockpit — Market & Competitive Intelligence (spec §4, §7.1).

Run:  streamlit run mci/app.py

The UI is organised into clearly separated **work areas** (tabs), each with a
short "?" help note stating what it is for. The path a signal travels —
Quelle ▸ Signal ▸ Entscheidung ▸ Export — is the same left-to-right order as the
tabs, so the tool reads as one workflow rather than a pile of features.

This UI is optional; the core package and tests do not depend on Streamlit.

Work areas (tabs): Übersicht (Lagebild, Frühwarnung, Assistent) · Recherche ·
Signale · Wettbewerber (incl. anlegen/bearbeiten/löschen) · Märkte (Länder-
Steckbrief + Referenzmärkte verwalten) · Trend-Radar · Entscheidungen · Szenario
· Assistent · Briefing.
"""

from __future__ import annotations

import os
import sys

# Make `import mci` work when the app is launched as a script (e.g.
# `streamlit run mci/app.py` or on Streamlit Cloud), where only this file's
# own folder is on sys.path — not the repo root that holds the `mci` package.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st

from mci import (
    alerts as alerts_mod,
    assistant as assistant_mod,
    correlation,
    country,
    portfolio,
    recommendation as recommendation_mod,
    research,
    sentiment as sentiment_mod,
    sources,
    specshare,
    summarize as summarize_mod,
    swot as swot_mod,
    trends as trends_mod,
)
from mci import battlecard as battlecard_mod
from mci import cadence as cadence_mod
from mci import competitor as competitor_mod
from mci import diff as diff_mod
from mci import hypotheses as hypotheses_mod
from mci import watchlist as watchlist_mod
from mci.briefing import generate_briefing, mark_briefing_sent, render_markdown
from mci.config import SETTINGS
from mci.db import Store
from mci.demo import SAMPLES
from mci.export import one_pager_markdown
from mci.ingestion import extract_file, fetch_html, fetch_rss
from mci.ingestion.feeds import CURATED_FEEDS, google_news_search_rss
from mci.ingestion.manual import manual_entry
from mci.models import Competitor, Market, SignalStatus, SourceClass
from mci.pipeline import Pipeline
from mci.scenario import Scenario, run_simulation
from mci.scenario.models import (
    Assumption,
    CompetitorResponse,
    Distribution,
    ReferenceCase,
)
from mci.scoring import priority_pct
from mci.seed import FOCUS_LINES, FOCUS_MARKETS, seed
from mci.synthesis import Synthesizer

st.set_page_config(
    page_title="Market & Competitive Intelligence",
    page_icon="🧭",
    layout="wide",
)

# --- light polish; theme-neutral, works in light & dark --------------------
st.markdown(
    """
    <style>
      .block-container {padding-top: 2.2rem; max-width: 1200px;}
      div[data-testid="stMetric"] {
          background: rgba(128,128,128,0.06);
          border: 1px solid rgba(128,128,128,0.18);
          border-radius: 12px; padding: 12px 16px;
      }
      div[data-testid="stMetricLabel"] {opacity: 0.8;}
      .stTabs [data-baseweb="tab"] {font-size: 1rem; padding: 6px 14px;}
      .fakt  {border-left: 4px solid #2f6feb; padding: 2px 12px; margin: 4px 0;}
      .abl   {border-left: 4px solid #d9a406; padding: 2px 12px; margin: 4px 0;}
      .hypo  {border-left: 4px solid #e8590c; padding: 2px 12px; margin: 4px 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

STATUS_BADGE = {
    SignalStatus.confirmed: "🟢 bestätigt",
    SignalStatus.unconfirmed: "🟡 unbestätigt",
    SignalStatus.expired: "⚪ abgelaufen",
    SignalStatus.refuted: "🔴 widerlegt",
}
VERDICT_STYLE = {
    "plausibel": ("✅", "success"),
    "ambitioniert": ("🟠", "warning"),
    "unplausibel ohne Strukturbruch": ("⛔", "error"),
}


@st.cache_resource
def get_store() -> Store:
    SETTINGS.ensure_dirs()
    store = Store(SETTINGS.db_path)
    if not store.list_competitors():
        seed(store)
    return store


def get_pipeline(store: Store) -> Pipeline:
    return Pipeline(store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)


def _csv(text: str) -> list[str]:
    """Split a comma-separated input into a clean list."""
    return [x.strip() for x in text.split(",") if x.strip()]


def report(res) -> None:
    """Turn an IngestResult into a user-facing toast."""
    if res.ok:
        st.success(f"{res.action}: {res.signal.headline if res.signal else ''}")
    else:
        st.warning(f"{res.action}: {'; '.join(res.violations) or res.note}")


store = get_store()
pipe = get_pipeline(store)

signals = store.list_signals()
confirmed = [s for s in signals if s.status == SignalStatus.confirmed]
competitors = store.list_competitors()
open_gaps = watchlist_mod.gap_queries(store)
due_watch = watchlist_mod.due_items(store)
briefing = generate_briefing(store)

# ==========================================================================
# Sidebar — global system status only (all real work lives in the tabs)
# ==========================================================================
with st.sidebar:
    st.header("System")
    backend_ok = pipe.backend.available
    st.markdown(
        f"**Analyse-Backend**\n\n"
        f"{'✅ ' + pipe.model_id if backend_ok else '⚠️ Offline-Heuristik'}"
    )
    st.caption(
        "Ohne `ANTHROPIC_API_KEY` laufen Scout/Extractor/Auditor als "
        "deterministische Offline-Heuristik — kennzeichnet ihre Grenzen selbst "
        "und erfindet nie Evidenz." if not backend_ok else
        "Claude ist aktiv. Der Kostendeckel bremst pro Lauf."
    )
    st.metric("Kostendeckel / Lauf", f"${SETTINGS.run_cost_cap_usd:.2f}")
    st.divider()
    st.caption("**Beobachtete Wettbewerber**")
    for c in competitors:
        st.caption(f"· {c.name} ({c.country})")

# ==========================================================================
# Header + KPI band
# ==========================================================================
st.title("🧭 Market & Competitive Intelligence")
st.caption(
    "KI-gestützte **Ableitungsmaschine**, kein News-Aggregator. "
    "Jede KI-Ableitung ist gekennzeichnet und bis zur Originalquelle nachvollziehbar."
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Signale gesamt", len(signals),
          help="Alle gespeicherten Signal-Cards. Jedes ist quellenbelegt (Evidenzzwang).")
k2.metric("Bestätigt", len(confirmed),
          help="Durch eine unabhängige Zweitquelle trianguliert (Status 🟢).")
k3.metric("Wettbewerber", len(competitors),
          help="Aktiv beobachtete Wettbewerber.")
k4.metric("Offene Wissenslücken", len(open_gaps),
          help="Bekannte Unbekannte über alle Signale — die Arbeitsliste für den "
               "nächsten Rechercheschritt (Tab „Recherche“).")

st.write("")

(tab_home, tab_research, tab_signals, tab_comp, tab_markets, tab_trends, tab_dec,
 tab_scn, tab_chat, tab_brief) = st.tabs([
    "🏠 Übersicht",
    "➕ Recherche & Eingabe",
    "📡 Signale",
    "🏢 Wettbewerber",
    "🌍 Märkte",
    "📈 Trend-Radar",
    "🎯 Entscheidungen",
    "🔮 Szenario (E8)",
    "💬 Assistent",
    "📤 Briefing & Export",
])

# --------------------------------------------------------------------------
# TAB 1 — Übersicht (Lage + Veränderung seit letztem Besuch)
# --------------------------------------------------------------------------
with tab_home:
    st.subheader(
        "🧠 Lagebild & Empfehlung",
        divider="blue",
        help="Synthese über die gesamte Datenbasis: Was sagt uns die "
             "Informationslage (Befunde), welche Schlüsse folgen (Konklusionen) "
             "und was ist zu tun (priorisierte Empfehlungen)? Regelbasiert, mit "
             "Konfidenz und offenen Wissenslücken.",
    )
    rep = recommendation_mod.build(store)
    r1, r2, r3 = st.columns(3)
    r1.metric("Signale", rep.n_signals)
    r2.metric("Bestätigt", rep.n_confirmed)
    r3.metric("Konfidenz Gesamtbild", f"{rep.confidence:.0%}",
              help="Anteil belegter (triangulierter) Signale, abzüglich offener Lücken.")

    cf, cc = st.columns(2)
    with cf:
        st.markdown("**Befunde — was die Daten zeigen**")
        if rep.findings:
            for f in rep.findings:
                st.markdown(f"- {f}")
        else:
            st.caption("Noch keine Befunde.")
    with cc:
        st.markdown("**Schlüsse — was daraus folgt**")
        if rep.conclusions:
            for c in rep.conclusions:
                st.markdown(f"- {c}")
        else:
            st.caption("Noch keine Schlüsse ableitbar.")

    st.markdown("**Empfehlungen — priorisiert**")
    if rep.recommendations:
        badge = {"hoch": "🔴", "mittel": "🟠", "niedrig": "🟡"}
        for r in rep.recommendations:
            links = f" · [{', '.join(r.decision_link)}]" if r.decision_link else ""
            st.markdown(f"{badge.get(r.priority, '•')} **{r.action}** — {r.rationale} "
                        f"_(Konfidenz {r.confidence:.0%}{links})_")
    else:
        st.caption("Noch keine Empfehlungen — Datenbasis aufbauen.")
    if rep.open_gaps:
        st.caption("Offene Wissenslücken: " + " · ".join(rep.open_gaps))

    with st.container(border=True):
        st.markdown("**🤖 KI-Assistent** — Lagebild zusammenfassen oder gezielt fragen",
                    help="Der Assistent antwortet nur aus belegten Signalen. Die "
                         "Zusammenfassung wird aus dem Lagebild oben erzeugt.")
        ac1, ac2 = st.columns([1, 2])
        with ac1:
            if st.button("📝 Zusammenfassung generieren", use_container_width=True):
                st.session_state["home_summary"] = recommendation_mod.narrative(rep)
        if st.session_state.get("home_summary"):
            st.info(st.session_state["home_summary"])
        with ac2:
            aq = st.text_input("Frage an den Assistenten",
                               placeholder="z. B. „Was macht Nordwall bei Zulassungen?“",
                               label_visibility="collapsed")
        if aq and aq.strip():
            ans = assistant_mod.answer(store, aq)
            st.markdown(ans.text)
            st.caption(ans.confidence_note)
            for c in ans.citations[:3]:
                st.markdown(f"> „{c.quote}“ — {c.source}")
            if ans.follow_up_query:
                st.caption(f"🔎 Rechercheauftrag: `{ans.follow_up_query}`")

    st.subheader(
        "🚨 Frühwarnsystem",
        divider="red",
        help="Meldet sofort Preisänderungen, neue Produkte und Zulassungen der "
             "Wettbewerber. Regelbasiert und mit Quell-Signal — keine Blackbox.",
    )
    active_alerts = alerts_mod.detect(store)
    if not active_alerts:
        st.caption("Keine akuten Frühwarnungen im Zeitfenster.")
    else:
        for a in active_alerts[:6]:
            st.markdown(f"{a.icon} **{a.kind}** · _{a.entity}_ · {a.headline}  "
                        f"`{a.at:%Y-%m-%d}`")

    st.subheader(
        "Lage in 10 Sekunden",
        divider="blue",
        help="Ebene 0 des 5-Minuten-Prinzips: die wenigen Signale mit der "
             "höchsten Priorität, die sich zuletzt verändert haben.",
    )
    if not briefing.changed:
        st.info("Keine relevanten Änderungen im Zeitfenster.")
    else:
        cols = st.columns(min(3, len(briefing.changed)))
        for col, s in zip(cols, briefing.changed[:3]):
            with col:
                st.metric(
                    label=STATUS_BADGE.get(s.status, s.status.value),
                    value=f"{priority_pct(s.priority)} Prio",
                    delta=f"{int(s.confidence * 100)} % Konfidenz",
                )
                st.caption(s.headline)

    st.subheader(
        "Was ist neu seit deinem letzten Besuch?",
        divider="gray",
        help="Diff-Ansicht: neue und frisch bestätigte Signale sowie neue "
             "Handlungsfelder seit dem letzten Öffnen dieser Ansicht.",
    )
    d = diff_mod.since_last_visit(store)
    if d.is_empty:
        st.caption("Nichts Neues — du bist auf dem Stand.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Neue Signale", len(d.new_signals))
        c2.metric("Neu bestätigt", len(d.confirmed_since))
        c3.metric("Neue Handlungsfelder", len(d.new_action_fields))
        for s in d.new_signals[:5]:
            st.markdown(f"- 🆕 {s.headline}")
        for s in d.confirmed_since[:5]:
            st.markdown(f"- 🟢 {s.headline}")
    if st.button("Als gesehen markieren", help="Setzt den Diff-Zeitpunkt auf jetzt."):
        diff_mod.mark_visited(store)
        st.rerun()

# --------------------------------------------------------------------------
# TAB 2 — Recherche & Eingabe (populate the tool sensibly)
# --------------------------------------------------------------------------
with tab_research:
    st.subheader(
        "So füllst du das Tool",
        divider="blue",
        help="Vier gleichrangige Eingabekanäle. Der Recherche-Assistent macht "
             "die Suche lückengetrieben statt zufällig.",
    )
    st.caption(
        "Regel: Das Tool erfindet nie Zahlen oder Fakten. Es verdichtet, was du "
        "hier einspeist. Ziel jedes Eintrags ist ein **quellenbelegtes Signal**, "
        "das später zu einem Entscheidungs-One-Pager wird."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("**✍️ Manuelle Beobachtung**")
            st.caption("Außendienst, Messe, Vertriebsfeedback, Kundengespräch.")
            with st.form("manual", clear_on_submit=True):
                note = st.text_area("Beobachtung", height=120,
                                    placeholder="Was hast du gesehen/gehört? Nur Fakten — "
                                                "Vermutungen werden automatisch getrennt.")
                klass = st.selectbox(
                    "Quellenklasse", [c.value for c in SourceClass], index=3,
                    help="A amtlich/Norm · B Fachpresse/Verband · C Firmenquelle/Job "
                         "· D Gerücht/Blog. Bestimmt mit über die Konfidenz.")
                if st.form_submit_button("Signal extrahieren", type="primary") and note.strip():
                    report(pipe.ingest(manual_entry(note, source_class=SourceClass(klass))))

    with col_b:
        with st.container(border=True):
            st.markdown("**🔗 Web-Quelle abrufen**")
            st.caption("URL einfügen — Text wird geholt, extrahiert, auditiert.")
            with st.form("url", clear_on_submit=True):
                url = st.text_input("URL", placeholder="https://…")
                if st.form_submit_button("Abrufen & extrahieren", type="primary") and url.strip():
                    try:
                        report(pipe.ingest(fetch_html(url.strip())))
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Ingestion fehlgeschlagen: {exc}")

    col_c, col_d = st.columns(2)
    with col_c:
        with st.container(border=True):
            st.markdown("**📄 Datei einspielen (PDF & mehr)**")
            st.caption("PDF, TXT, Markdown, CSV, HTML. PDFs werden seitenweise mit "
                       "Seitenlokator als Evidenz erfasst.")
            up = st.file_uploader(
                "Datei(en) wählen", type=["pdf", "txt", "md", "csv", "tsv", "html", "htm", "json"],
                accept_multiple_files=True, label_visibility="collapsed",
                help="Eigene Berichte, Studien, Kataloge, Preislisten oder gespeicherte Artikel.")
            klass_f = st.selectbox("Quellenklasse", [c.value for c in SourceClass], index=0,
                                   key="fileclass",
                                   help="Eigene Dokumente/Studien i. d. R. A.")
            if st.button("Dateien extrahieren", type="primary", disabled=not up):
                import tempfile as _tmp
                from pathlib import Path as _Path
                added = 0
                for uf in up or []:
                    tmp = _Path(_tmp.mkdtemp()) / uf.name
                    tmp.write_bytes(uf.getbuffer())
                    try:
                        for doc in extract_file(tmp, source_class=SourceClass(klass_f)):
                            added += 1 if pipe.ingest(doc).ok else 0
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"{uf.name}: {exc}")
                if added:
                    st.success(f"{added} Signal(e) aus Datei(en) extrahiert.")

    with col_d:
        with st.container(border=True):
            st.markdown("**🌐 News weltweit (RSS)**")
            st.caption("Google-News-Feeds pro Thema oder Länder-Edition. News sind "
                       "schwache Evidenz — erst mit Zweitquelle wird daraus „bestätigt“.")
            topic = st.text_input("Thema / Suchbegriff",
                                  placeholder="z. B. Wettbewerbername, „Fassadenplatte Zulassung“")
            edition = st.selectbox("Länder-Edition (Top-News)", ["(keine)"] + list(CURATED_FEEDS),
                                   help="Alternativ zum Thema: die Top-News einer Weltregion.")
            limit = st.slider("Max. Einträge", 3, 25, 8)
            if st.button("News abrufen & extrahieren", type="primary"):
                feed = (google_news_search_rss(topic) if topic.strip()
                        else CURATED_FEEDS.get(edition) if edition != "(keine)" else None)
                if not feed:
                    st.warning("Thema eingeben oder eine Länder-Edition wählen.")
                else:
                    try:
                        docs = fetch_rss(feed, limit=limit)
                        added = sum(1 for d in docs if pipe.ingest(d).ok)
                        st.success(f"{added}/{len(docs)} News-Einträge zu Signalen verdichtet.")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"News-Abruf fehlgeschlagen: {exc}")

    st.subheader(
        "🔎 Recherche-Assistent (lückengetrieben)",
        divider="gray",
        help="Baut aus den offenen Wissenslücken des Tools + den Wettbewerbern + "
             "den Fokusmärkten konkrete Suchanfragen mit fertigen Klick-Links. "
             "Du suchst, findest eine echte Quelle und fügst ihre URL oben ein.",
    )
    plan = research.suggested_queries(
        store, focus_markets=FOCUS_MARKETS, focus_lines=FOCUS_LINES)
    st.caption(f"{len(plan)} vorgeschlagene Suchschritte — offene Lücken zuerst.")
    for sq in plan[:16]:
        with st.container(border=True):
            top = st.columns([4, 3])
            with top[0]:
                st.markdown(f"**{sq.label}** · `{sq.query}`")
                st.caption(f"{sq.rationale}  ·  [{', '.join(sq.decision_link)}]")
            with top[1]:
                link_md = "  ·  ".join(f"[{name}]({href})" for name, href in sq.links.items())
                st.markdown("🔗 " + link_md)

    st.subheader(
        "🏛️ Autoritative Quellen weltweit",
        divider="gray",
        help="Kuratiertes Register belastbarer Erstquellen je Markt — "
             "Zulassungs-/Norm-/Patent-/Statistikstellen. Immer von einer "
             "reputablen Quelle aus starten, nie von einem Blog.",
    )
    mkt = st.selectbox(
        "Markt", [c for c, _ in sources.WORLD_MARKETS],
        format_func=sources.market_name,
        help="Weltmärkte — nicht auf den Heimatmarkt beschränkt.")
    auth = sources.authoritative_for(mkt)
    acols = st.columns(2)
    for i, s in enumerate(auth):
        with acols[i % 2]:
            st.markdown(f"[{s.name}]({s.url}) · `{s.klass}` — {s.scope}")

    st.subheader(
        "Beispieldaten",
        divider="gray",
        help="Lädt eine kleine, realistische Beispiel-Recherche, damit du sofort "
             "ein befülltes Cockpit siehst (inkl. Triangulation und einer "
             "abgelehnten Falschmeldung).",
    )
    if st.button("Beispiel-Recherche laden",
                 help="Speist die Demo-Dokumente durch die volle Pipeline."):
        added = 0
        for doc in SAMPLES:
            res = pipe.ingest(doc)
            added += 1 if res.ok else 0
        st.success(f"{added} Beispiel-Signale eingespeist. Wechsle zu „📡 Signale“.")
        st.rerun()

# --------------------------------------------------------------------------
# TAB 3 — Signale (cockpit cards, drill-down to evidence)
# --------------------------------------------------------------------------
with tab_signals:
    st.subheader(
        "Signal-Cockpit",
        divider="blue",
        help="Alle Signale nach Priorität. Jede Card trennt strikt Fakt (blau), "
             "Ableitung (gelb) und Hypothese (orange) und lässt sich bis zur "
             "Originalquelle aufklappen (Ebene 3).",
    )
    f1, f2 = st.columns([2, 2])
    status_pick = f1.multiselect(
        "Status", [s.value for s in SignalStatus],
        default=[SignalStatus.confirmed.value, SignalStatus.unconfirmed.value],
        help="Nach Bestätigungsgrad filtern.")
    who_pick = f2.selectbox(
        "Wettbewerber", ["(alle)"] + [c.name for c in competitors],
        help="Auf einen Wettbewerber einschränken.")

    view = [s for s in sorted(signals, key=lambda x: x.priority, reverse=True)
            if (not status_pick or s.status.value in status_pick)]
    if who_pick != "(alle)":
        view = [s for s in view if who_pick in (s.entities.competitors or [])]

    if not view:
        st.info("Keine Signale für diesen Filter. Speise welche im Tab „Recherche“ ein.")
    for s in view:
        who = ", ".join(s.entities.competitors or s.entities.markets) or "—"
        header = (f"**{priority_pct(s.priority)}** · {STATUS_BADGE.get(s.status, '')} · "
                  f"{s.headline}  ·  _{who}_  ·  [{', '.join(s.decision_link)}]")
        with st.expander(header):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f'<div class="fakt"><b>🟦 Fakt</b> (quellenbelegt)<br>{s.fact}</div>',
                            unsafe_allow_html=True)
                if s.derivation:
                    st.markdown(f'<div class="abl"><b>🟨 Ableitung</b> (KI)<br>{s.derivation}</div>',
                                unsafe_allow_html=True)
                if s.hypothesis:
                    st.markdown(f'<div class="hypo"><b>🟧 Hypothese</b><br>{s.hypothesis}</div>',
                                unsafe_allow_html=True)
                if s.recommended_action:
                    st.markdown(f"**Empfohlene Aktion:** {s.recommended_action}")
                if s.known_unknowns:
                    st.markdown("**Wissenslücken:**")
                    for u in s.known_unknowns:
                        st.markdown(f"- {u}")
            with c2:
                st.markdown("**Score (Formel)**",
                            help="Deterministisch berechnet — das LLM setzt keine Zahlen.")
                st.write({"impact": s.impact, "confidence": s.confidence,
                          "urgency": s.urgency, "proximity": s.proximity,
                          "priority": s.priority, "half_life_days": s.half_life_days})

            st.markdown("**Ebene 3 — Evidenz**",
                        help="Wörtliches Quellenzitat je Signal. Zwei Klicks bis zur Quelle.")
            for eid in s.evidence_ids:
                ev = store.get_evidence(eid)
                if not ev:
                    continue
                src = store.get_source(ev.source_id)
                src_line = (f"[{src.source_class.value}] {src.publisher or src.url}"
                            if src else ev.source_id)
                loc = f" · {ev.page_or_locator}" if ev.page_or_locator else ""
                st.markdown(f"> „{ev.quote_short}“  \n— {src_line}{loc}")
                if src:
                    st.caption(src.url)

            with st.popover("Reasoning-Trace (KI)"):
                st.caption(f"prompt_version={s.prompt_version} · model={s.model_id} · "
                           f"audit_passed={s.audit_passed}")
                st.code(s.reasoning_trace or "—")

# --------------------------------------------------------------------------
# TAB 4 — Wettbewerber (dossier, cadence, battlecard, portfolio, spec-share)
# --------------------------------------------------------------------------
with tab_comp:
    st.subheader(
        "Wettbewerber-Analyse",
        divider="blue",
        help="Alles zu einem Wettbewerber an einem Ort: Dossier, Launch-Rhythmus, "
             "Battlecard, Portfolio-Lücken und Spec-Share.",
    )

    with st.expander("⚙️ Wettbewerber anlegen / bearbeiten / löschen"):
        names = ["➕ Neu anlegen"] + [c.name for c in competitors]
        pick_c = st.selectbox("Auswählen", names, key="mng_comp_pick",
                              help="Bestehenden zum Bearbeiten wählen oder „Neu anlegen“. "
                                   "Änderungen wirken sofort im ganzen Tool.")
        editing_c = next((c for c in competitors if c.name == pick_c), None)
        with st.form("comp_form"):
            name = st.text_input("Name*", value=editing_c.name if editing_c else "")
            cc1, cc2 = st.columns(2)
            country_i = cc1.text_input("Land", value=editing_c.country if editing_c else "")
            hq = cc2.text_input("HQ", value=editing_c.hq if editing_c else "")
            parent = st.text_input("Muttergesellschaft",
                                   value=editing_c.parent_company if editing_c else "")
            segments = st.text_input("Segmente (Komma-getrennt)",
                                     value=", ".join(editing_c.segments) if editing_c else "")
            aliases = st.text_input("Aliase (Komma-getrennt)",
                                    value=", ".join(editing_c.aliases) if editing_c else "")
            b1, b2 = st.columns(2)
            save_c = b1.form_submit_button("💾 Speichern", type="primary",
                                           use_container_width=True)
            del_c = b2.form_submit_button("🗑️ Löschen", use_container_width=True,
                                          disabled=editing_c is None)
        if save_c:
            if not name.strip():
                st.error("Name ist erforderlich.")
            else:
                data = dict(name=name.strip(), country=country_i.strip(), hq=hq.strip(),
                            parent_company=parent.strip(),
                            segments=_csv(segments), aliases=_csv(aliases))
                if editing_c:
                    data["id"] = editing_c.id
                store.upsert_competitor(Competitor(**data))
                st.success(f"Gespeichert: {name.strip()}")
                st.rerun()
        if del_c and editing_c:
            store.delete_competitor(editing_c.id)
            st.warning(f"Gelöscht: {editing_c.name}")
            st.rerun()

    if competitors:
        pick = st.selectbox("Wettbewerber wählen", [c.name for c in competitors])
        chosen = next((c for c in competitors if c.name == pick), None)
    else:
        st.info("Noch keine Wettbewerber. Lege oben welche an.")
        chosen = None

    if chosen:
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("**📇 Dossier**",
                            help="Verdichtetes Profil aus allen Signalen zu diesem Wettbewerber.")
                dossier = competitor_mod.build(store, chosen.id)
                if dossier:
                    st.caption(f"HQ {chosen.hq} · {chosen.country} · Segmente: "
                               f"{', '.join(chosen.segments) or '—'}")
                    n_sig = (len(dossier.launch_timeline) + len(dossier.financial_timeline)
                             + len(dossier.other_signals))
                    st.write(f"Signale: {n_sig} · Launches: {len(dossier.launch_timeline)}")
                    for s in (dossier.launch_timeline + dossier.other_signals)[:5]:
                        st.markdown(f"- {s.headline}")
                    for q in (dossier.open_questions or [])[:3]:
                        st.caption(f"❓ {q}")
                else:
                    st.caption("Noch keine Signale zu diesem Wettbewerber.")
        with col2:
            with st.container(border=True):
                st.markdown("**⏱️ Launch-Rhythmus**",
                            help="Mittlerer Abstand zwischen Launches → nächstes "
                                 "erwartetes Fenster. Unter drei Launches: ehrlich "
                                 "„insufficient“.")
                pred = cadence_mod.predict(store, chosen.id)
                if pred.status == "ok" and pred.next_window:
                    lo, hi = pred.next_window
                    st.metric("Nächstes Fenster",
                              f"{lo:%Y-%m} … {hi:%Y-%m}",
                              delta=f"{int(pred.confidence*100)} % Konfidenz")
                    st.caption(f"Ø Intervall {pred.mean_interval_days:.0f} d "
                               f"· {pred.n_launches} Launches")
                else:
                    st.caption(f"Datenlage unzureichend ({pred.n_launches} Launches).")

        with st.container(border=True):
            st.markdown("**🛡️ Battlecard**",
                        help="Bekannte Schwächen der Top-Wettbewerber je Produktlinie, "
                             "belegt aus Kundenfeedback-Signalen.")
            line = st.selectbox("Produktlinie", FOCUS_LINES or ["Abdichtung"])
            bc = battlecard_mod.build(store, line)
            if bc.competitors:
                for e in bc.competitors:
                    weak = "; ".join(e.known_weaknesses) or "—"
                    st.markdown(f"- **{e.name}** — Schwächen: {weak}")
                if bc.own_strengths:
                    st.caption("Eigene Stärken: " + "; ".join(bc.own_strengths))
            else:
                st.caption("Noch keine Battlecard-Evidenz (Kundenfeedback fehlt).")

        colp, cols = st.columns(2)
        with colp:
            with st.container(border=True):
                st.markdown("**🧩 Portfolio-Lücken (E1)**",
                            help="Gap / Whitespace / Overlap / Overhang je Anwendung "
                                 "aus eigenem vs. Wettbewerber-Sortiment.")
                cells = portfolio.gap_matrix(store)
                if cells:
                    st.dataframe([c.as_dict() for c in cells], use_container_width=True,
                                 hide_index=True)
                else:
                    st.caption("Keine Portfolio-Daten.")
        with cols:
            with st.container(border=True):
                st.markdown("**📈 Spec-Share**",
                            help="Anteil der namentlichen Nennungen je Wettbewerber "
                                 "über die Zeit — ein Proxy für Sichtbarkeit.")
                timeline = specshare.spec_share_timeline(store)
                if timeline:
                    periods = sorted({p.period for pts in timeline.values() for p in pts})
                    chart = {ent: {p.period: round(p.share, 3) for p in pts}
                             for ent, pts in timeline.items()}
                    rows = [{"Periode": per, **{ent: chart[ent].get(per) for ent in chart}}
                            for per in periods]
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("Noch keine Nennungen erfasst.")

        cols_sw = st.columns(2)
        with cols_sw[0]:
            with st.container(border=True):
                st.markdown("**🧭 SWOT-Analyse**",
                            help="Stärken/Schwächen/Chancen/Risiken, regelbasiert aus "
                                 "den Signalen abgeleitet (Interpretation, kein Fakt).")
                sw = swot_mod.swot(store, chosen.id)
                if sw and not sw.is_empty():
                    for title, items in (("💪 Stärken", sw.strengths),
                                         ("⚠️ Schwächen", sw.weaknesses),
                                         ("🌱 Chancen", sw.opportunities),
                                         ("⛈️ Risiken", sw.threats)):
                        if items:
                            st.markdown(f"**{title}**")
                            for it in items:
                                st.markdown(f"- {it}")
                else:
                    st.caption("Zu wenig Signale für eine SWOT.")
        with cols_sw[1]:
            with st.container(border=True):
                st.markdown("**😊 Sentiment (Voice of Customer)**",
                            help="Ob die erfassten Kunden-/Marktstimmen positiv oder "
                                 "negativ über die Marke sprechen. Lexikonbasiert.")
                bs = next((b for b in sentiment_mod.competitor_sentiment(store)
                           if b.competitor == chosen.name), None)
                if bs:
                    icon = {"positiv": "🟢", "negativ": "🔴", "neutral": "⚪"}[bs.label]
                    st.metric("Tendenz", f"{icon} {bs.label}",
                              delta=f"Score {bs.avg_score:+.2f}")
                    st.caption(f"{bs.positive} positiv · {bs.negative} negativ · "
                               f"{bs.neutral} neutral  (n={bs.n})")
                else:
                    st.caption("Noch keine Stimmen zu dieser Marke erfasst.")

        with st.container(border=True):
            st.markdown("**📊 Wettbewerbs-Matrix**",
                        help="Automatischer Aktivitätsvergleich aller Wettbewerber "
                             "(Launches, Zulassungen, Kapazität, Finanzen, Feedback, "
                             "Sentiment).")
            rows = swot_mod.matrix(store)
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.caption("Keine Wettbewerberdaten.")

# --------------------------------------------------------------------------
# TAB — Trend-Radar
# --------------------------------------------------------------------------
with tab_trends:
    st.subheader(
        "Trend-Radar",
        divider="blue",
        help="Zeigt aufkommende Themen anhand ihres Momentums — wie viel häufiger "
             "ein Begriff in der jüngeren als in der älteren Hälfte des Zeitfensters "
             "auftaucht. Steigende Begriffe sind das frühe, schwache Signal, bevor "
             "ein Trend Mainstream wird.",
    )
    cwin1, cwin2 = st.columns(2)
    win = cwin1.slider("Zeitfenster (Tage)", 30, 365, 180, step=30)
    minc = cwin2.slider("Mindest-Nennungen", 2, 6, 2)
    radar = trends_mod.radar(store, window_days=win, min_count=minc)
    if not radar:
        st.info("Noch zu wenig Signale für ein Trendbild. Speise mehr News/Quellen ein.")
    else:
        rows = [{"": t.arrow, "Trend": t.term, "Nennungen": t.count,
                 "Momentum": t.momentum,
                 "seit": f"{t.first_seen:%Y-%m}" if t.first_seen else "—"}
                for t in radar]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("🔼 steigend · ▶️ stabil · 🔽 fallend")

# --------------------------------------------------------------------------
# TAB 5 — Entscheidungen (synthesis, correlation, hypotheses, watchlist)
# --------------------------------------------------------------------------
with tab_dec:
    st.subheader(
        "Handlungsfelder (Cluster-Synthese)",
        divider="blue",
        help="Der eigentliche Wertschritt: Signale werden je Entscheidungsrahmen "
             "E1–E7 gebündelt. Jedes Feld hat Pflicht-Null-Option, Konfidenz-Gate "
             "und einen Advocatus-Diaboli-Gegenpart.",
    )
    if st.button("Synthese jetzt ausführen", type="primary",
                 help="Bündelt alle aktiven Signale neu zu Handlungsfeldern."):
        Synthesizer(store).run()
        st.rerun()

    fields = store.list_action_fields()
    if not fields:
        st.info("Noch keine Handlungsfelder. Führe die Synthese aus (Button oben).")
    for f in fields:
        gate = " 🔒 gated" if getattr(f, "gated", False) else ""
        with st.expander(f"**{f.decision_category}** · Konfidenz {f.confidence:.0%}{gate} · "
                         f"{f.recommendation[:80]}"):
            st.markdown(f"**Beobachtung:** {f.observation}")
            if f.interpretation:
                st.markdown(f"**Interpretation:** {f.interpretation}")
            if f.options:
                st.markdown("**Optionen:**")
                for o in f.options:
                    st.markdown(f"- **{o.label}** — {o.rationale} "
                                f"_(Aufwand {o.effort or '?'}, Risiko {o.risk or '?'})_")
            st.markdown(f"**Empfehlung:** {f.recommendation}")
            if f.counter_argument:
                st.markdown(f"**⚖️ Advocatus Diaboli:** {f.counter_argument}")
            if f.alternative_explanation:
                st.markdown(f"**Alternative Erklärung:** {f.alternative_explanation}")
            if f.falsification_trigger:
                st.markdown(f"**Falsifikations-Trigger:** {f.falsification_trigger}")
            if f.known_unknowns:
                st.caption("Wissenslücken: " + "; ".join(f.known_unknowns))

    st.subheader(
        "Korrelationsregeln (§2.5)",
        divider="gray",
        help="Explizite, nachvollziehbare Regeln R1–R4, die mehrere Signale zu "
             "einem Muster verbinden — nie eine LLM-Meinung.",
    )
    insights = correlation.evaluate(store)
    if insights:
        for ins in insights:
            st.markdown(f"- **{ins.rule_id}** · {ins.entity}: {ins.conclusion} "
                        f"_(Konfidenz {ins.confidence:.0%}, [{', '.join(ins.decision_link)}])_")
    else:
        st.caption("Keine Kombinationsregel ausgelöst.")

    colh, colw = st.columns(2)
    with colh:
        st.subheader(
            "Hypothesen",
            divider="gray",
            help="Vermutungen mit automatischer Falsifikation: die KI darf eine "
                 "Hypothese widerlegen, aber nie bestätigen.",
        )
        checks = hypotheses_mod.auto_check(store)
        hyps = store.list_hypotheses()
        if not hyps:
            st.caption("Keine offenen Hypothesen.")
        for h in hyps[:8]:
            st.markdown(f"- [{getattr(h, 'status', '?')}] "
                        f"{getattr(h, 'statement', getattr(h, 'text', ''))}")
    with colw:
        st.subheader(
            "Watchlist",
            divider="gray",
            help="Fällige Beobachtungspunkte und lückengetriebene Recherche-Queries.",
        )
        if due_watch:
            for item in due_watch[:8]:
                st.markdown(f"- ⏰ {item.target_type} **{item.target_ref}**")
        else:
            st.caption("Nichts fällig.")
        if open_gaps:
            st.caption("Offene Lücken: " + " · ".join(open_gaps[:5]))

# --------------------------------------------------------------------------
# TAB 6 — Szenario (E8 target check)
# --------------------------------------------------------------------------
with tab_scn:
    st.subheader(
        "E8 — Zielprüfung (Szenario)",
        divider="blue",
        help="Prüft ein Marktanteilsziel gegen einen Treiberbaum per Monte-Carlo. "
             "Der Referenzklassen-Check (Outside View) überstimmt naiven Optimismus: "
             "verlangt ein Treiber mehr Bewegung als je historisch beobachtet, "
             "lautet das Urteil „unplausibel ohne Strukturbruch“.",
    )
    with st.form("scenario"):
        c1, c2, c3 = st.columns(3)
        target = c1.number_input("Ziel: +pp Marktanteil", value=2.0, step=0.5,
                                 help="Angestrebter Marktanteilsgewinn in Prozentpunkten.")
        market = c2.selectbox("Markt", [c for c, _ in sources.WORLD_MARKETS],
                              format_func=sources.market_name)
        horizon = c3.number_input("Horizont (Monate)", value=24, step=6, min_value=6)

        st.markdown("**Treiber 1 — Listungstiefe**")
        d1a, d1b, d1c = st.columns(3)
        base1 = d1a.number_input("Ist", value=0.34, step=0.01, key="b1")
        tgt1 = d1b.number_input("Ziel", value=0.46, step=0.01, key="t1")
        ref1 = d1c.number_input("Bester je beobachteter Jahreswert", value=0.06, step=0.01,
                                key="r1",
                                help="Referenzklasse: die größte historisch belegte "
                                     "Jahresbewegung dieses Treibers.")

        st.markdown("**Treiber 2 — Distributionsgrad**")
        d2a, d2b, _ = st.columns(3)
        base2 = d2a.number_input("Ist", value=0.60, step=0.01, key="b2")
        tgt2 = d2b.number_input("Ziel", value=0.66, step=0.01, key="t2")

        st.markdown("**Wettbewerber-Reaktion**")
        r1, r2 = st.columns(2)
        comp_name = r1.text_input("Am stärksten betroffen", value="Nordwall")
        comp_adj = r2.number_input("Netto-Effekt (pp)", value=-0.3, step=0.1,
                                   help="Erwartete Reaktion des Wettbewerbers, meist negativ. "
                                        "Nicht modelliert ⇒ Szenario gilt als unvollständig.")
        run = st.form_submit_button("Monte-Carlo laufen lassen", type="primary")

    if run:
        scn = Scenario(target_metric="market_share_pp", target_value=target,
                       market=market, horizon_months=int(horizon), mode="inverse")
        asmp = [
            Assumption(driver_node="listungstiefe", baseline=base1, value=tgt1,
                       distribution=Distribution(low=min(base1, tgt1), mode=tgt1,
                                                 high=tgt1 + abs(tgt1 - base1))),
            Assumption(driver_node="distributionsgrad", baseline=base2, value=tgt2,
                       distribution=Distribution(low=min(base2, tgt2), mode=tgt2,
                                                 high=tgt2 + abs(tgt2 - base2))),
        ]
        refs = [ReferenceCase(driver="listungstiefe", observed_delta=ref1,
                              description="bester je beobachteter Jahreswert")]
        sim = run_simulation(scn, asmp, seed=1, reference_cases=refs,
                             competitor_response=CompetitorResponse(
                                 most_affected=comp_name, modeled=bool(comp_name),
                                 net_effect_adjustment=comp_adj))

        icon, kind = VERDICT_STYLE.get(sim.verdict, ("•", "info"))
        getattr(st, kind)(f"{icon} Urteil: **{sim.verdict}**")
        m1, m2, m3 = st.columns(3)
        m1.metric("P(Ziel erreicht)", f"{sim.p_target_hit:.0%}")
        m2.metric("Median", f"{sim.outcome_median:+g} pp")
        m3.metric("80 %-Band",
                  f"[{sim.outcome_band_80[0]:+g}, {sim.outcome_band_80[1]:+g}]")

        if sim.sensitivity:
            st.markdown("**Tornado — Sensitivität**",
                        help="Welche Annahme das Ergebnis am stärksten bewegt.")
            st.dataframe(sim.sensitivity, use_container_width=True, hide_index=True)
        for w in sim.extrapolation_warnings:
            st.warning(f"⚠️ {w}")
        if sim.denominator_warning:
            st.warning(f"⚠️ {sim.denominator_warning}")
        if sim.incomplete:
            st.error("Szenario unvollständig: Wettbewerber-Reaktion nicht modelliert.")

# --------------------------------------------------------------------------
# TAB — Chat-Assistent + Zusammenfassung
# --------------------------------------------------------------------------
with tab_chat:
    st.subheader(
        "Chat-Assistent",
        divider="blue",
        help="Frag in natürlicher Sprache, z. B. „Was macht Nordwall bei "
             "Zulassungen?“. Der Assistent antwortet ausschließlich aus den "
             "erfassten, quellenbelegten Signalen — und sagt ehrlich „kein "
             "Beleg“, statt Zahlen zu erfinden.",
    )
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for role, content in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(content)

    q = st.chat_input("Frage zu Wettbewerbern, Signalen, Märkten …")
    if q:
        st.session_state.chat.append(("user", q))
        with st.chat_message("user"):
            st.markdown(q)
        ans = assistant_mod.answer(store, q)
        parts = [ans.text, f"\n\n_{ans.confidence_note}_"]
        for c in ans.citations:
            parts.append(f"\n> „{c.quote}“ — {c.source}")
        if ans.follow_up_query:
            parts.append(f"\n\n🔎 Rechercheauftrag: `{ans.follow_up_query}`")
        reply = "".join(parts)
        st.session_state.chat.append(("assistant", reply))
        with st.chat_message("assistant"):
            st.markdown(reply)

    st.subheader(
        "Automatische Zusammenfassung",
        divider="gray",
        help="Fasst einen langen Text (Bericht/Studie) extraktiv in wenige Sätze "
             "zusammen — es werden nur Sätze zurückgegeben, die im Original stehen.",
    )
    long = st.text_area("Text einfügen", height=150,
                        placeholder="Langen Bericht oder Studientext hier einfügen …")
    n = st.slider("Sätze", 1, 6, 3)
    if st.button("Zusammenfassen", disabled=not long.strip()):
        st.success(summarize_mod.summarize(long, max_sentences=n))

# --------------------------------------------------------------------------
# TAB — Märkte (Länder-Steckbrief + Referenzmärkte verwalten)
# --------------------------------------------------------------------------
with tab_markets:
    st.subheader(
        "Märkte",
        divider="blue",
        help="Länder-/Marktprofile ansehen und eigene Referenzmärkte anlegen, "
             "bearbeiten und löschen. Änderungen wirken sofort im ganzen Tool.",
    )

    with st.container(border=True):
        st.markdown("**🌍 Länder-Steckbrief**",
                    help="Marktprofil je Land: Bauindikatoren, Regulatorik, "
                         "Wettbewerberdichte.")
        cty = st.selectbox("Land", [c for c, _ in sources.WORLD_MARKETS],
                           format_func=sources.market_name)
        prof = country.build(store, cty)
        cc1, cc2 = st.columns(2)
        cc1.metric("Wettbewerberdichte", prof.competitor_density)
        cc2.metric("Bauindikatoren", len(prof.construction_indicators))
        if prof.competitors:
            st.caption("Präsent: " + ", ".join(prof.competitors))

    st.subheader(
        "Referenzmärkte verwalten",
        divider="gray",
        help="Eigene Marktdatensätze mit Größe, Wachstum, Kanalstruktur und Quelle.",
    )
    markets = store.list_markets()
    m_labels = ["➕ Neu anlegen"] + [f"{m.country} · {m.region}".strip(" ·") for m in markets]
    pick_m = st.selectbox("Auswählen", m_labels, key="mng_mkt_pick",
                          help="Bestehenden zum Bearbeiten wählen oder „Neu anlegen“.")
    editing_m = markets[m_labels.index(pick_m) - 1] if pick_m != "➕ Neu anlegen" else None

    with st.form("mkt_form"):
        mcountry = st.text_input("Land / Markt*",
                                 value=editing_m.country if editing_m else "",
                                 help="Ländercode oder Marktname, z. B. DE, US, „DACH“.")
        mm0a, mm0b = st.columns(2)
        mregion = mm0a.text_input("Region", value=editing_m.region if editing_m else "")
        mchannel = mm0b.text_input("Kanalstruktur",
                                   value=editing_m.channel_structure if editing_m else "")
        mm1, mm2 = st.columns(2)
        msize = mm1.text_input("Größe (Schätzung)",
                               value=editing_m.size_estimate if editing_m else "")
        mgrowth = mm2.text_input("Wachstum",
                                 value=editing_m.growth_rate if editing_m else "")
        msource = st.text_input("Quelle", value=editing_m.source_ref if editing_m else "")
        mb1, mb2 = st.columns(2)
        save_m = mb1.form_submit_button("💾 Speichern", type="primary",
                                        use_container_width=True)
        del_m = mb2.form_submit_button("🗑️ Löschen", use_container_width=True,
                                       disabled=editing_m is None)
    if save_m:
        if not mcountry.strip():
            st.error("Land / Markt ist erforderlich.")
        else:
            data = dict(country=mcountry.strip(), region=mregion.strip(),
                        channel_structure=mchannel.strip(), size_estimate=msize.strip(),
                        growth_rate=mgrowth.strip(), source_ref=msource.strip())
            if editing_m:
                data["id"] = editing_m.id
            store.upsert_market(Market(**data))
            st.success(f"Gespeichert: {mcountry.strip()}")
            st.rerun()
    if del_m and editing_m:
        store.delete_market(editing_m.id)
        st.warning(f"Gelöscht: {editing_m.country}")
        st.rerun()

    if markets:
        st.caption("Angelegte Referenzmärkte:")
        st.dataframe(
            [{"Land": m.country, "Region": m.region, "Kanal": m.channel_structure,
              "Größe": m.size_estimate, "Wachstum": m.growth_rate} for m in markets],
            use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------
# TAB 7 — Briefing & Export
# --------------------------------------------------------------------------
with tab_brief:
    st.subheader(
        "Wöchentliches Briefing",
        divider="blue",
        help="Der Standardausgabe-Report: Lage, Cockpit-Top-5 und die Wissenslücken-"
             "Arbeitsliste — als Markdown exportierbar.",
    )
    md = render_markdown(briefing)
    cexp1, cexp2 = st.columns(2)
    cexp1.download_button("⬇️ Briefing (Markdown)", md, file_name="briefing.md",
                          use_container_width=True)
    if cexp2.button("Als gesendet markieren", use_container_width=True):
        mark_briefing_sent(store)
        st.rerun()
    with st.expander("Vorschau"):
        st.markdown(md)

    st.subheader(
        "Entscheidungs-One-Pager",
        divider="gray",
        help="Ein Handlungsfeld als komiteefertiger One-Pager mit durchgehender "
             "Evidenzkette (E7).",
    )
    fields = store.list_action_fields()
    if fields:
        labels = [f"{f.decision_category} · {f.recommendation[:60]}" for f in fields]
        idx = st.selectbox("Handlungsfeld", range(len(fields)),
                           format_func=lambda i: labels[i])
        op = one_pager_markdown(fields[idx], store)
        st.download_button("⬇️ One-Pager (Markdown)", op,
                           file_name="one_pager.md", use_container_width=True)
        with st.expander("Vorschau"):
            st.markdown(op)
    else:
        st.caption("Noch keine Handlungsfelder — führe im Tab „Entscheidungen“ die "
                   "Synthese aus.")
