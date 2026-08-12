"""Demokorpus — fünf Märkte, drei Linien, eine Jahreslücke von 4,2 Mio €.

Erfunden, aber nicht beliebig. Die Zahlen sind so gewählt, dass die Fälle
auftreten, um die es dem Werkzeug geht:

* Ein Markt (PL), dessen Lücke überwiegend aus Distribution stammt — dort wirkt
  Geld.
* Ein Markt (NL), dessen Lücke überwiegend exogen ist — dort wirkt keins.
* Eine Ursache mit hohem Betrag und schwachem Beleg — die Rechercherückkopplung.
* Historische Ergebnisse, in denen die unbelegten Maßnahmen deutlich hinter der
  Erwartung blieben und die gemessenen nicht. Genau daraus zieht das Nachhalten
  seine unbequemste Aussage: die Schlagseite folgt der Evidenzklasse, nicht der
  Abteilung.

Wer den Korpus gegen echte Zahlen tauscht, ersetzt `plan_figures()` und
`attributions()` — alles andere hängt daran und nicht an diesen Werten.
"""

from __future__ import annotations

from .catalog import MEASURE_CATALOG
from .models import (
    Band,
    BridgeStep,
    CauseCode,
    MarketProfile,
    MeasureOutcome,
    PlanFigure,
)

PERIOD = "FY2026"
MARKETS = ["DE", "AT", "PL", "FR", "NL"]
LINES = ["Abdichtung", "Entkopplung", "Fassade"]

# Kostenfaktor je Markt: dieselbe Maßnahme kostet in Deutschland mehr als in
# Österreich, weil Fläche, Kundenzahl und Medienpreise andere sind.
MARKET_COST_FACTORS: dict[str, float] = {
    "DE": 1.40, "FR": 1.10, "PL": 0.70, "AT": 0.60, "NL": 0.60,
}

# (Markt, Linie, Plan, Forecast) in Euro.
_PLAN_ROWS: list[tuple[str, str, float, float]] = [
    ("DE", "Abdichtung", 140_000_000, 132_000_000),
    ("DE", "Entkopplung", 90_000_000, 86_000_000),
    ("DE", "Fassade", 70_000_000, 66_000_000),
    ("AT", "Abdichtung", 35_000_000, 32_000_000),
    ("AT", "Entkopplung", 25_000_000, 23_000_000),
    ("AT", "Fassade", 25_000_000, 23_000_000),
    ("PL", "Abdichtung", 40_000_000, 35_000_000),
    ("PL", "Entkopplung", 25_000_000, 22_000_000),
    ("PL", "Fassade", 25_000_000, 22_000_000),
    ("FR", "Abdichtung", 55_000_000, 53_000_000),
    ("FR", "Entkopplung", 35_000_000, 33_500_000),
    ("FR", "Fassade", 35_000_000, 33_500_000),
    ("NL", "Abdichtung", 35_000_000, 34_000_000),
    ("NL", "Entkopplung", 25_000_000, 24_000_000),
    ("NL", "Fassade", 20_000_000, 19_000_000),
]

# (Markt, Ursache, Betrag, Notiz). Was nicht zugeordnet ist, bleibt als
# unerklärter Rest stehen — siehe bridge.build().
_ATTRIBUTION_ROWS: list[tuple[str, CauseCode, float, str]] = [
    ("DE", CauseCode.competitive_loss, 5_500_000,
     "Nordwall gewinnt Positionen im Fachhandel, v. a. Abdichtung."),
    ("DE", CauseCode.distribution, 3_500_000,
     "Listungstiefe in zwei Verbundgruppen zurückgegangen."),
    ("DE", CauseCode.price, 2_500_000,
     "Rabattmittel über Plan, Streuung zwischen Regionen erheblich."),
    ("DE", CauseCode.execution, 1_500_000,
     "Servicegrad Abdichtung zwei Quartale unter Zielwert."),

    ("AT", CauseCode.competitive_loss, 2_200_000,
     "Nordwall mit aggressiver Konditionsoffensive im Osten."),
    ("AT", CauseCode.price, 1_800_000, "Preisdurchsetzung schwächer als geplant."),
    ("AT", CauseCode.distribution, 1_200_000, "Ein Verbund hat ausgelistet."),

    ("PL", CauseCode.distribution, 4_200_000,
     "Distributionsgrad deutlich unter Plan; Handelsstruktur zersplittert."),
    ("PL", CauseCode.competitive_loss, 2_500_000,
     "Lokaler Anbieter mit deutlich kürzeren Lieferzeiten."),
    ("PL", CauseCode.market_volume, 2_000_000,
     "Wohnungsneubau schwächer als der Planungsstand unterstellt hat."),
    ("PL", CauseCode.specification, 800_000, "Kaum Präsenz bei Planungsbüros."),

    ("FR", CauseCode.specification, 2_000_000,
     "In Ausschreibungen zunehmend nicht spezifiziert."),
    ("FR", CauseCode.mix, 1_200_000, "Sortimentslücke im mittleren Preissegment."),
    ("FR", CauseCode.distribution, 800_000, "Zwei Regionalhändler verloren."),

    ("NL", CauseCode.market_volume, 1_200_000, "Marktvolumen insgesamt rückläufig."),
    ("NL", CauseCode.competitive_loss, 800_000, "Wettbewerber mit Systemangebot."),
    ("NL", CauseCode.execution, 500_000, "Lieferzeiten über Wettbewerbsniveau."),
]

_PROFILE_ROWS: list[tuple[str, float, float, float, float, float, str]] = [
    ("DE", 0.65, 0.75, 0.80, 0.85, 0.70, "Starker Verbundhandel, hohe Normdichte."),
    ("AT", 0.70, 0.72, 0.65, 0.80, 0.72, "Struktur ähnlich DE, kleiner."),
    ("PL", 0.35, 0.45, 0.55, 0.40, 0.42, "Zersplitterter Handel, wachsend."),
    ("FR", 0.55, 0.68, 0.70, 0.75, 0.62, "Ausschreibungsgetrieben, Planer stark."),
    ("NL", 0.75, 0.60, 0.60, 0.78, 0.66, "Wenige große Kanäle, gesättigt."),
]

# Historische Ergebnisse aus FY2025 (Markt, Maßnahmenname, Band, Ist).
# `None` als Ist bedeutet: noch offen — zählt nie als Treffer.
_OUTCOME_ROWS: list[tuple[str, str, tuple[float, float, float], float | None]] = [
    ("DE", "Listungstiefe im Fachhandel erhöhen",
     (3_000_000, 3_800_000, 4_700_000), 3_200_000),
    ("DE", "Lieferfähigkeit & Verfügbarkeit sichern",
     (2_200_000, 3_000_000, 4_000_000), 3_400_000),
    ("DE", "Substitutionsschutz bei Schlüsselkunden",
     (1_500_000, 2_100_000, 2_900_000), 1_950_000),
    ("DE", "Marke & Kommunikation (Dachkampagne)",
     (1_500_000, 2_600_000, 4_000_000), 900_000),
    ("AT", "Händler-Co-Marketing / Abverkaufsaktionen",
     (1_100_000, 1_500_000, 2_000_000), 1_850_000),
    ("AT", "Value-Selling-Paket / Preisargumentation",
     (900_000, 1_200_000, 1_600_000), 1_400_000),
    ("AT", "Marke & Kommunikation (Dachkampagne)",
     (1_000_000, 1_800_000, 2_900_000), 700_000),
    ("FR", "Digitaler Planungskonfigurator",
     (1_100_000, 1_800_000, 2_800_000), 600_000),
    ("FR", "Regionale Fokussierung der Außendienstzeit",
     (500_000, 700_000, 950_000), 550_000),
    ("NL", "Digitale Nachfragegenerierung Verarbeiter",
     (600_000, 950_000, 1_500_000), 1_200_000),
    ("PL", "Neue Handelspartner erschließen",
     (1_600_000, 2_200_000, 3_000_000), 1_750_000),
    ("PL", "Referenzobjekt-Kampagne", (700_000, 1_100_000, 1_700_000), None),
]


def _measure_by_name(name: str):
    for m in MEASURE_CATALOG:
        if m.name == name:
            return m
    raise KeyError(f"Maßnahme nicht im Katalog: {name}")


def plan_figures(period: str = PERIOD) -> list[PlanFigure]:
    """Plan und Prognose je Markt und Linie — der Stand aus der ersten Säule."""
    return [
        PlanFigure(market=market, line=line, period=period,
                   plan_eur=plan, forecast_eur=forecast, source="demo")
        for market, line, plan, forecast in _PLAN_ROWS
    ]


def attributions(period: str = PERIOD) -> list[BridgeStep]:
    """Ursachenzuordnung der Lücke. Bewusst unvollständig."""
    return [
        BridgeStep(market=market, period=period, cause=cause,
                   amount_eur=amount, note=note)
        for market, cause, amount, note in _ATTRIBUTION_ROWS
    ]


def market_profiles() -> dict[str, MarketProfile]:
    """Strukturprofile für den Playbook-Transfer."""
    return {
        market: MarketProfile(
            market=market, channel_concentration=channel,
            regulation_intensity=regulation, competitive_density=density,
            maturity=maturity, price_level=price, note=note,
        )
        for market, channel, regulation, density, maturity, price, note in _PROFILE_ROWS
    }


def historical_outcomes(period: str = "FY2025") -> list[MeasureOutcome]:
    """Gemessene Ergebnisse des Vorjahres — Grundlage für Bilanz und Transfer."""
    out: list[MeasureOutcome] = []
    for market, name, (low, mode, high), actual in _OUTCOME_ROWS:
        measure = _measure_by_name(name)
        outcome = MeasureOutcome(
            measure_id=measure.id,
            measure_name=name,
            market=market,
            period=period,
            expected=Band(low=low, mode=mode, high=high),
            status="gemessen" if actual is not None else "offen",
            owner="Demo",
        )
        if actual is not None:
            outcome.actual_eur = actual
        out.append(outcome)
    return out


def instrument_map() -> dict:
    """Maßnahmen-ID ▸ Träger. Für die Bias-Auswertung nach Abteilung."""
    return {m.id: m.instrument for m in MEASURE_CATALOG}


def evidence_map() -> dict:
    """Maßnahmen-ID ▸ Evidenzklasse. Für die Kalibrierung."""
    return {m.id: m.evidence_class for m in MEASURE_CATALOG}


def seed(store) -> None:
    """Füllt einen leeren Speicher mit dem Demokorpus."""
    figures = plan_figures()
    store.replace_plan_figures(figures, PERIOD)
    store.replace_bridge_steps(attributions(), PERIOD)
    for profile in market_profiles().values():
        store.upsert_market_profile(profile)
    for outcome in historical_outcomes():
        store.upsert_outcome(outcome)
    store.set_meta("seeded", "demo")
