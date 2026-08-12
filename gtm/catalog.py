"""Maßnahmenkatalog — Vertrieb und Marketing in einer Liste.

Der Katalog ist die eigentliche Fusionsleistung dieses Werkzeugs. Solange
Vertriebsmaßnahmen und Marketingmaßnahmen in getrennten Listen mit getrennten
Kennzahlen stehen, lassen sie sich nicht gegeneinander abwägen, und die
Budgetdiskussion entscheidet die lautere Stimme. Hier stehen sie in derselben
Tabelle, mit denselben Feldern, und werden nach demselben Maßstab bewertet.

Die Struktur — Wirkzeit, Kostenklasse, Reversibilität — ist bewusst dieselbe wie
im Hebelkatalog des Szenariomoduls (`mci/scenario/levers.py`), damit ein Hebel
aus der E8-Rechnung und eine Maßnahme aus diesem Cockpit dasselbe Objekt
beschreiben und nicht zwei Wahrheiten entstehen.

Zu den Zahlen: die Wirkungsgrade sind Bänder, keine Punkte, und jede Maßnahme
trägt ihre Evidenzklasse offen. `measured` heißt: wir haben das selbst gemessen.
`analog` heißt: woanders beobachtet, hier unterstellt. `assumed` heißt: das hat
noch nie jemand gemessen — solche Maßnahmen gehen mit 60 % Abschlag ins
Portfolio. Wer den Katalog an die eigene Realität anpasst, sollte zuerst die
Evidenzklassen ehrlich setzen und erst danach über die Bänder streiten.
"""

from __future__ import annotations

from .models import Band, CauseCode, EvidenceClass, Instrument, Measure


def _m(
    name: str,
    instrument: Instrument,
    addresses: list[CauseCode],
    grade: tuple[float, float, float],
    evidence: EvidenceClass,
    tte: int,
    ramp: int,
    cost: float,
    capacity: float,
    reversibility: str,
    *,
    basis: list[str] | None = None,
    note: str = "",
) -> Measure:
    low, mode, high = grade
    return Measure(
        name=name,
        instrument=instrument,
        addresses=addresses,
        effect_grade=Band(low=low, mode=mode, high=high),
        evidence_class=evidence,
        evidence_basis=basis or [],
        time_to_effect_months=tte,
        ramp_months=ramp,
        cost_full_eur=cost,
        capacity_fte_months=capacity,
        reversibility=reversibility,
        note=note,
    )


MEASURE_CATALOG: list[Measure] = [
    # ---- Distribution & Listung -------------------------------------------
    _m("Listungstiefe im Fachhandel erhöhen", Instrument.sales,
       [CauseCode.distribution], (0.20, 0.32, 0.45), EvidenceClass.measured,
       12, 6, 320_000, 14.0, "hoch",
       basis=["DE 2023: +6 pp Listungstiefe nach Sortimentsgespräch-Offensive"],
       note="Wirkt nur, wo der Handel überhaupt Regalfläche hat."),
    _m("Neue Handelspartner erschließen", Instrument.sales,
       [CauseCode.distribution], (0.10, 0.18, 0.28), EvidenceClass.analog,
       18, 9, 480_000, 22.0, "mittel",
       basis=["PL 2022: 11 neue Partner in 18 Monaten"]),
    _m("Händler-Co-Marketing / Abverkaufsaktionen", Instrument.joint,
       [CauseCode.distribution, CauseCode.competitive_loss], (0.10, 0.18, 0.28),
       EvidenceClass.measured, 6, 4, 260_000, 9.0, "hoch",
       basis=["AT 2024: Abverkauf +9 % in teilnehmenden Häusern"],
       note="Klassische Nahtstelle: Marketing zahlt, Vertrieb setzt durch."),
    _m("Produkt- und Verarbeitertrainings", Instrument.joint,
       [CauseCode.execution, CauseCode.distribution], (0.10, 0.17, 0.26),
       EvidenceClass.analog, 9, 6, 180_000, 12.0, "mittel"),

    # ---- Spezifikation & Planer -------------------------------------------
    _m("Spezifikationsarbeit bei Planern", Instrument.joint,
       [CauseCode.specification], (0.25, 0.40, 0.55), EvidenceClass.measured,
       27, 12, 420_000, 26.0, "niedrig",
       basis=["DE 2019–2023: Spec-Share +8 pp über vier Jahre"],
       note="Höchster Wirkungsgrad im Katalog — und mit Abstand die längste "
            "Wirkzeit. Wirkt nie auf die Lücke des laufenden Jahres."),
    _m("Referenzobjekt-Kampagne", Instrument.joint,
       [CauseCode.specification, CauseCode.competitive_loss], (0.10, 0.18, 0.28),
       EvidenceClass.analog, 9, 6, 210_000, 8.0, "mittel"),
    _m("Digitaler Planungskonfigurator", Instrument.marketing,
       [CauseCode.specification], (0.12, 0.20, 0.32), EvidenceClass.assumed,
       15, 9, 350_000, 10.0, "niedrig",
       note="Keine belastbare Messung — geht mit vollem Evidenzabschlag ein."),

    # ---- Wettbewerbsverluste ----------------------------------------------
    _m("Substitutionsschutz bei Schlüsselkunden", Instrument.sales,
       [CauseCode.competitive_loss], (0.16, 0.28, 0.40), EvidenceClass.measured,
       9, 6, 200_000, 11.0, "hoch",
       basis=["DE 2024: 7 von 9 gefährdeten Positionen gehalten"]),
    _m("Verarbeiterbindung / Loyalitätsprogramm", Instrument.joint,
       [CauseCode.competitive_loss, CauseCode.mix], (0.12, 0.20, 0.30),
       EvidenceClass.analog, 18, 9, 300_000, 10.0, "niedrig"),
    _m("Digitale Nachfragegenerierung Verarbeiter", Instrument.marketing,
       [CauseCode.competitive_loss, CauseCode.specification], (0.06, 0.12, 0.20),
       EvidenceClass.analog, 6, 4, 240_000, 6.0, "hoch",
       basis=["NL 2024: qualifizierte Anfragen +34 %"]),
    _m("Marke & Kommunikation (Dachkampagne)", Instrument.marketing,
       [CauseCode.competitive_loss], (0.08, 0.15, 0.26), EvidenceClass.assumed,
       24, 12, 600_000, 8.0, "mittel",
       note="Teuer, langsam, unbelegt. Steht im Katalog, weil die Diskussion "
            "sonst außerhalb des Werkzeugs geführt wird."),

    # ---- Preis & Mix -------------------------------------------------------
    _m("Value-Selling-Paket / Preisargumentation", Instrument.joint,
       [CauseCode.price], (0.18, 0.30, 0.44), EvidenceClass.analog,
       4, 3, 120_000, 7.0, "hoch",
       basis=["AT 2024: Rabattmittel −1,4 pp nach Argumentationstraining"]),
    _m("Konditionensystem nachschärfen", Instrument.sales,
       [CauseCode.price, CauseCode.mix], (0.25, 0.42, 0.58), EvidenceClass.measured,
       3, 2, 90_000, 5.0, "sehr niedrig",
       basis=["Konzernweit 2023: Rabattstreuung −2,1 pp"],
       note="Schnellster Hebel im Katalog — und der am schwersten "
            "zurückzunehmende. Wirkt sofort auf die Marge, in beide Richtungen."),
    _m("Sortimentslücke schließen", Instrument.joint,
       [CauseCode.mix], (0.25, 0.42, 0.58), EvidenceClass.analog,
       21, 12, 900_000, 30.0, "sehr niedrig"),

    # ---- Eigene Umsetzung --------------------------------------------------
    _m("Lieferfähigkeit & Verfügbarkeit sichern", Instrument.sales,
       [CauseCode.execution], (0.30, 0.48, 0.65), EvidenceClass.measured,
       6, 3, 260_000, 9.0, "mittel",
       basis=["DE 2023: Servicegrad 91 → 97 %, Nachbestellquote halbiert"]),
    _m("Regionale Fokussierung der Außendienstzeit", Instrument.sales,
       [CauseCode.execution, CauseCode.distribution], (0.10, 0.18, 0.28),
       EvidenceClass.measured, 9, 4, 70_000, 8.0, "hoch",
       basis=["FR 2024: Besuchszeit bei A-Kunden +18 %"]),
]


def by_id(measures: list[Measure] | None = None) -> dict[str, Measure]:
    return {m.id: m for m in (measures or MEASURE_CATALOG)}


def by_cause(cause: CauseCode, measures: list[Measure] | None = None) -> list[Measure]:
    return [m for m in (measures or MEASURE_CATALOG) if cause in m.addresses]


def by_instrument(
    instrument: Instrument, measures: list[Measure] | None = None
) -> list[Measure]:
    return [m for m in (measures or MEASURE_CATALOG) if m.instrument is instrument]


def applicable(measure: Measure, market: str) -> bool:
    return not measure.markets_applicable or market in measure.markets_applicable


def uncovered_causes(measures: list[Measure] | None = None) -> list[CauseCode]:
    """Ursachen, gegen die der Katalog keine Maßnahme kennt.

    Bis auf das Marktvolumen — das ist exogen und soll unbeantwortet bleiben —
    ist jede Lücke hier ein echter Mangel des Katalogs.
    """
    covered = {c for m in (measures or MEASURE_CATALOG) for c in m.addresses}
    return [c for c in CauseCode if c not in covered]
