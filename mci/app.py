"""Streamlit cockpit — the 5-Minuten-Prinzip (spec §4).

Run:  streamlit run mci/app.py

Ebene 0 (Lage) -> Ebene 1 (Cockpit) -> Ebene 2 (Signal cards) -> Ebene 3
(Evidenz). The strict Fakt / Ableitung / Hypothese separation (spec §3.2) is
rendered as three visually distinct blocks, and every signal drills down to its
source quote in two clicks (Erfolgskriterium §10.2).

This UI is optional; the core package and tests do not depend on Streamlit.
"""

from __future__ import annotations

import streamlit as st

from mci.briefing import (
    generate_briefing,
    mark_briefing_sent,
    render_markdown,
)
from mci.config import SETTINGS
from mci.db import Store
from mci.ingestion import RawDocument, fetch_html
from mci.ingestion.manual import manual_entry
from mci.models import SignalStatus, SourceClass
from mci.pipeline import Pipeline
from mci.scoring import priority_pct
from mci.seed import FOCUS_LINES, FOCUS_MARKETS, seed

st.set_page_config(page_title="Market & Competitive Intelligence", layout="wide")

STATUS_BADGE = {
    SignalStatus.confirmed: "🟢 bestätigt",
    SignalStatus.unconfirmed: "🟡 unbestätigt",
    SignalStatus.expired: "⚪ abgelaufen",
    SignalStatus.refuted: "🔴 widerlegt",
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


store = get_store()
pipe = get_pipeline(store)

# --- Sidebar: ingestion + status ------------------------------------------
with st.sidebar:
    st.header("Recherche & Eingabe")
    st.caption(
        f"LLM: {'✅ ' + pipe.model_id if pipe.backend.available else '⚠️ offline-Heuristik'}"
        f" · Kostendeckel ${SETTINGS.run_cost_cap_usd:.2f}/Lauf"
    )

    with st.form("manual"):
        st.subheader("Manuelle Eingabe (Außendienst)")
        note = st.text_area("Beobachtung", height=100,
                            placeholder="Messebesuch, Vertriebsfeedback, Kundengespräch …")
        klass = st.selectbox("Quellenklasse", [c.value for c in SourceClass], index=3)
        if st.form_submit_button("Signal extrahieren") and note.strip():
            res = pipe.ingest(manual_entry(note, source_class=SourceClass(klass)))
            if res.ok:
                st.success(f"{res.action}: {res.signal.headline if res.signal else ''}")
            else:
                st.error(f"{res.action}: {'; '.join(res.violations) or res.note}")

    with st.form("url"):
        st.subheader("Web-Quelle")
        url = st.text_input("URL", placeholder="https://…")
        if st.form_submit_button("Abrufen & extrahieren") and url.strip():
            try:
                doc = fetch_html(url.strip())
                res = pipe.ingest(doc)
                if res.ok:
                    st.success(f"{res.action}: {res.signal.headline if res.signal else ''}")
                else:
                    st.error(f"{res.action}: {'; '.join(res.violations) or res.note}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Ingestion fehlgeschlagen: {exc}")

    st.divider()
    st.caption(
        "Wettbewerber: " + ", ".join(c.name for c in store.list_competitors())
    )

# --- Main ------------------------------------------------------------------
st.title("Market & Competitive Intelligence")
st.caption(
    "KI-gestützte Ableitungsmaschine · KI-generierte Ableitungen sind gekennzeichnet"
)

briefing = generate_briefing(store)

# Ebene 0 — Lage
st.subheader("Ebene 0 — Lage")
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

st.divider()

# Ebene 1 — Cockpit
st.subheader("Ebene 1 — Cockpit (Top-Signale nach Priorität)")
for s in briefing.cockpit:
    who = ", ".join(s.entities.competitors or s.entities.markets) or "—"
    header = (
        f"**{priority_pct(s.priority)}** · {STATUS_BADGE.get(s.status, '')} · "
        f"{s.headline}  ·  _{who}_  ·  [{', '.join(s.decision_link)}]"
    )
    with st.expander(header):
        c1, c2 = st.columns([3, 1])
        with c1:
            # Fakt / Ableitung / Hypothese — visually separated (spec §3.2)
            st.markdown("**🟦 Fakt** (quellenbelegt)")
            st.write(s.fact)
            if s.derivation:
                st.markdown("**🟨 Ableitung** (KI-Schlussfolgerung)")
                st.write(s.derivation)
            if s.hypothesis:
                st.markdown("**🟧 Hypothese** (Vermutung)")
                st.write(s.hypothesis)
            if s.recommended_action:
                st.markdown(f"**Empfohlene Aktion:** {s.recommended_action}")
            if s.known_unknowns:
                st.markdown("**Wissenslücken:**")
                for u in s.known_unknowns:
                    st.markdown(f"- {u}")
        with c2:
            # Score breakdown — transparent, not a blackbox (spec §4, §9)
            st.markdown("**Score (Formel)**")
            st.write(
                {
                    "impact": s.impact,
                    "confidence": s.confidence,
                    "urgency": s.urgency,
                    "proximity": s.proximity,
                    "priority": s.priority,
                    "half_life_days": s.half_life_days,
                }
            )

        # Ebene 3 — Evidenz
        st.markdown("**Ebene 3 — Evidenz**")
        for eid in s.evidence_ids:
            ev = store.get_evidence(eid)
            if not ev:
                continue
            src = store.get_source(ev.source_id)
            src_line = (
                f"[{src.source_class.value}] {src.publisher or src.url}"
                if src else ev.source_id
            )
            loc = f" · {ev.page_or_locator}" if ev.page_or_locator else ""
            st.markdown(f"> „{ev.quote_short}"  f"  \n— {src_line}{loc}")
            if src:
                st.caption(src.url)

        with st.popover("Reasoning-Trace (KI)"):
            st.caption(
                f"prompt_version={s.prompt_version} · model={s.model_id} · "
                f"audit_passed={s.audit_passed}"
            )
            st.code(s.reasoning_trace or "—")

st.divider()

# Briefing export
st.subheader("Wöchentliches Briefing")
md = render_markdown(briefing)
st.download_button("Briefing als Markdown", md, file_name="briefing.md")
if st.button("Als gesendet markieren"):
    mark_briefing_sent(store)
    st.rerun()
with st.expander("Vorschau"):
    st.markdown(md)
