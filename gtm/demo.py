"""End-to-end-Demo ohne API-Schlüssel: `python -m gtm.demo`.

Läuft die vollständige Kette durch — Forecast einlesen, Brücke bauen, Belege aus
dem MCI-Speicher anhängen, Portfolio rechnen, Effizienzgrenze abtasten, Einwand
einholen, Vorjahresbilanz ziehen, Transferkandidaten bestimmen — und druckt, was
in der Vorführung auf den Tisch gehört.

Die Ausgabe ist bewusst so gebaut, dass die unbequemen Stellen nicht am Ende
stehen: was das Paket *nicht* leistet, steht direkt neben dem, was es leistet.
"""

from __future__ import annotations

from pathlib import Path

from . import demo_data
from .allocate import allocate, evidence_mix, frontier, summary_lines
from .bridge import build as build_bridge
from .catalog import MEASURE_CATALOG
from .config import SETTINGS
from .fmt import eur as _eur
from .link import evidence_summary, open_gaps
from .llm.roles import default_roles, instrument_split
from .models import CAUSE_LABELS, INSTRUMENT_LABELS, Instrument
from .playbook import transfer_candidates
from .tracking import report as track_report

RULE = "─" * 72


def _head(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def _open_mci_store():
    """MCI-Speicher öffnen, wenn vorhanden. Fehlt er, läuft alles ohne Belege."""
    try:
        from mci.db import Store as MciStore
    except Exception:  # noqa: BLE001
        return None, "MCI-Paket nicht importierbar"
    path = Path(SETTINGS.mci_db_path)
    if not path.exists():
        return None, f"keine MCI-Datenbank unter {path}"
    try:
        return MciStore(path), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"MCI-Datenbank nicht lesbar: {exc}"


def main() -> None:
    period = demo_data.PERIOD
    horizon = SETTINGS.horizon_months

    # --- 1. Erste Säule: Plan und Prognose ---------------------------------
    figures = demo_data.plan_figures(period)
    bridge = build_bridge(figures, demo_data.attributions(period), period=period)

    _head(f"1 · Lückenbild {period}")
    print(f"Plan      {_eur(bridge.plan_eur)}")
    print(f"Forecast  {_eur(bridge.forecast_eur)}")
    print(f"Lücke     {_eur(bridge.gap_eur)}\n")
    for cause, amount in bridge.by_cause():
        label = CAUSE_LABELS[cause] if cause else "Unerklärt"
        share = amount / bridge.gap_eur if bridge.gap_eur else 0
        marker = "  (exogen)" if cause and cause.value == "market_volume" else ""
        print(f"  {label:<24} {_eur(amount):>14}  {share:>5.0%}{marker}")
    print(f"\nAdressierbar: {_eur(bridge.addressable_eur)} von "
          f"{_eur(bridge.gap_eur)} — der Rest ist exogen oder unerklärt.")
    for w in bridge.warnings:
        print(f"  ! {w}")

    # --- 2. Zweite Säule: Belege aus der Recherche -------------------------
    _head("2 · Kopplung an die Recherche")
    store, reason = _open_mci_store()
    if store is None:
        print(f"Keine Belege angehängt ({reason}).")
        print("Das Cockpit läuft weiter — die Brückenstufen bleiben unbelegt,")
        print("und genau das weist die Oberfläche dann auch aus.")
    else:
        from .link import attach_evidence
        attach_evidence(bridge, store)
        for label, amount in evidence_summary(bridge).items():
            print(f"  {label:<16} {_eur(amount):>14}")
        gaps = open_gaps(bridge)
        if gaps:
            print("\nRechercheaufträge (großer Betrag, schwacher Beleg):")
            for gap in gaps[:5]:
                print(f"  · {gap.research_question()}")
        store.close()

    # --- 3. Dritte Säule: das Portfolio ------------------------------------
    _head(f"3 · Maßnahmenportfolio · Budget "
          f"{_eur(SETTINGS.default_budget_eur)} · Horizont {horizon} Monate")
    portfolio = allocate(
        bridge, MEASURE_CATALOG,
        budget_eur=SETTINGS.default_budget_eur,
        capacity_fte_months=SETTINGS.default_capacity_fte_months,
        horizon_months=horizon,
        market_factors=demo_data.MARKET_COST_FACTORS,
        max_measures=SETTINGS.default_max_measures,
    )
    for line in summary_lines(portfolio):
        print(f"  {line}")

    print("\n  Maßnahmen:")
    for a in portfolio.allocations:
        print(f"    {a.market}  {a.measure_name:<44} "
              f"Dosis {a.dose:>4.0%}  {_eur(a.cost_eur):>12}  "
              f"→ {_eur(a.effect_horizon.mode):>12}")

    print("\n  Wirkungsanteile nach Träger:")
    for key, share in sorted(instrument_split(portfolio).items(),
                             key=lambda t: t[1], reverse=True):
        print(f"    {INSTRUMENT_LABELS[Instrument[key]]:<14} {share:>5.0%}")

    print("\n  Evidenzmischung:")
    for label, share in sorted(evidence_mix(portfolio).items(),
                               key=lambda t: t[1], reverse=True):
        print(f"    {label:<14} {share:>5.0%}")

    if portfolio.dominated:
        print("\n  Nicht gewählt (wirkt im Horizont, trägt aber die Kosten nicht "
              "oder verliert gegen bessere Maßnahmen):")
        for name in portfolio.dominated:
            print(f"    · {name}")
    if portfolio.too_slow:
        print(f"\n  Wirkt erst nach {horizon} Monaten — gehört ins Mehrjahresbudget:")
        for name in portfolio.too_slow:
            print(f"    · {name}")
    if portfolio.warnings:
        print("\n  Hinweise:")
        for w in portfolio.warnings:
            print(f"    ! {w}")

    # --- 4. Effizienzgrenze -------------------------------------------------
    _head("4 · Effizienzgrenze — was der nächste Euro noch bringt")
    budgets = [250_000, 500_000, 750_000, 1_000_000,
               1_500_000, 2_500_000, 4_000_000]
    print(f"  {'Budget':>12} {'Wirkung Hor.':>14} {'Deckung':>9} {'Maßn.':>6} "
          f"{'Grenz. Hor.':>12} {'Grenz. p.a.':>12}")
    for point in frontier(
        bridge, MEASURE_CATALOG, budgets=budgets,
        capacity_fte_months=SETTINGS.default_capacity_fte_months,
        horizon_months=horizon, market_factors=demo_data.MARKET_COST_FACTORS,
        max_measures=SETTINGS.default_max_measures,
    ):
        marg_h = f"{point.marginal_return:.2f} €/€" if point.marginal_return else "—"
        marg_r = (f"{point.marginal_return_run_rate:.2f} €/€"
                  if point.marginal_return_run_rate else "—")
        print(f"  {_eur(point.budget_eur):>12} "
              f"{_eur(point.effect_horizon_eur):>14} "
              f"{point.coverage:>8.0%} {point.n_measures:>6} "
              f"{marg_h:>12} {marg_r:>12}")

    # --- 5. Der Einwand -----------------------------------------------------
    _head("5 · Advocatus Diaboli — kennt das Ergebnis, nicht die Begründung")
    roles = default_roles()
    print(f"  Quelle: {roles.model_id}\n")
    print(f"  Begründung: {roles.rationale(portfolio, bridge)}\n")
    critique = roles.challenge(portfolio, bridge)
    print(f"  Einwand: {critique.counter_argument}\n")
    print(f"  Gegenlesart: {critique.alternative_explanation}")
    if critique.blind_spots:
        print("\n  Blinde Flecken:")
        for spot in critique.blind_spots:
            print(f"    · {spot}")

    # --- 6. Bilanz des Vorjahres -------------------------------------------
    _head("6 · Nachhalten — was von den letzten Beschlüssen übrig blieb")
    outcomes = demo_data.historical_outcomes()
    rep = track_report(
        outcomes,
        instrument_of=demo_data.instrument_map(),
        evidence_of=demo_data.evidence_map(),
    )
    for line in rep.lines:
        print(f"  {line}")
    print("\n  Kalibrierung der Evidenzabschläge:")
    for row in rep.calibration:
        ratio = f"{row.mean_ratio:.2f}" if row.mean_ratio is not None else "—"
        print(f"    {row.label:<14} n={row.n:<3} Ist/Erwartung {ratio:>5}  {row.note}")

    # --- 7. Playbook-Transfer ----------------------------------------------
    _head("7 · Playbook-Transfer — was sich global weiterreichen lässt")
    profiles = demo_data.market_profiles()
    candidates = transfer_candidates(outcomes, profiles)
    for cand in candidates[:6]:
        print(f"  {cand.source_market} → {cand.target_market}  "
              f"{cand.measure_name:<44} "
              f"Übertragbarkeit {cand.transferability:.2f}  [{cand.verdict}]")
        print(f"      erwartete Wirkung {_eur(cand.expected_effect.low)} – "
              f"{_eur(cand.expected_effect.high)}")
        for caveat in cand.caveats[:2]:
            print(f"      ⚠ {caveat}")

    _head("Fertig")
    print("Oberfläche:  streamlit run gtm/app.py")
    print("Tests:       pytest -q tests/test_gtm_*.py")


if __name__ == "__main__":
    main()
