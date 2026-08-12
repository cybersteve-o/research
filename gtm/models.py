"""Domänenmodell des Wirkungs- und Allokationscockpits.

Die dritte Säule des Dreiklangs: der Absatzforecast sagt, *wo wir landen*, das
MCI-Tool sagt, *was draußen passiert* — dieses Paket beantwortet, *was wir tun,
was es wert ist und ob es gewirkt hat*.

Zwei Regeln werden unverändert aus `mci` übernommen und sind nicht verhandelbar:

* **Keine Zahl ohne Band** — jede Wirkung ist ein Dreiecksband, nie ein Punkt.
* **Die KI setzt keine Zahlen** — die LLM-Rollen liefern Ursachen, Formulierungen
  und Gegenargumente; jeder Euro in diesem Paket wird in `effects.py` und
  `allocate.py` aus prüfbaren Eingaben berechnet.

Eine dritte Regel ist neu und gehört diesem Paket:

* **Kein Effekt ohne Evidenzklasse** — jede Maßnahme sagt, ob ihre Wirkung
  `gemessen` (eigene Historie), `analog` (Referenzfall anderswo) oder
  `angenommen` (hat noch nie jemand gemessen) ist. Schwache Evidenz wird
  deterministisch abgewertet und ausgewiesen, nicht stillschweigend
  weggemittelt.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CauseCode(str, enum.Enum):
    """Ursachenklassen der Planlücke — die Stufen der Revenue Bridge.

    Bewusst klein gehalten: sieben Ursachen, die sich sauber gegeneinander
    abgrenzen und für die es jeweils *andere* Maßnahmen gibt. Wer die Liste
    erweitert, muss auch den Maßnahmenkatalog erweitern, sonst entsteht eine
    Ursache, auf die niemand antworten kann.
    """

    market_volume = "market_volume"          # Marktvolumen / Nachfrage insgesamt
    distribution = "distribution"            # Distribution, Listung, Verfügbarkeit
    competitive_loss = "competitive_loss"    # direkter Verlust an den Wettbewerb
    price = "price"                          # Preis, Rabatt, Konditionen
    mix = "mix"                              # Produkt- und Kundenmix
    specification = "specification"          # Spezifikation, Planer, Ausschreibung
    execution = "execution"                  # eigene Umsetzung: Kapazität, Lieferfähigkeit


CAUSE_LABELS: dict[CauseCode, str] = {
    CauseCode.market_volume: "Marktvolumen",
    CauseCode.distribution: "Distribution & Listung",
    CauseCode.competitive_loss: "Verlust an Wettbewerb",
    CauseCode.price: "Preis & Konditionen",
    CauseCode.mix: "Produkt- & Kundenmix",
    CauseCode.specification: "Spezifikation & Planer",
    CauseCode.execution: "Eigene Umsetzung",
}

# Ursachen, die das Unternehmen selbst nicht bewegen kann. Maßnahmen dagegen
# anzusetzen ist der häufigste Planungsfehler — die Brücke markiert sie.
EXOGENOUS_CAUSES = {CauseCode.market_volume}


class Instrument(str, enum.Enum):
    """Wer die Maßnahme trägt.

    `joint` ist keine Verlegenheitskategorie, sondern der Kern der Fusion:
    Maßnahmen, die nur wirken, wenn Vertrieb und Marketing gemeinsam liefern.
    Ihr Anteil am Portfolio ist eine direkt ablesbare Integrationskennzahl.
    """

    sales = "sales"
    marketing = "marketing"
    joint = "joint"


INSTRUMENT_LABELS: dict[Instrument, str] = {
    Instrument.sales: "Vertrieb",
    Instrument.marketing: "Marketing",
    Instrument.joint: "Gemeinsam",
}


class EvidenceClass(str, enum.Enum):
    """Woher die Wirkungsannahme stammt (analog zu `mci.scenario.AssumptionClass`)."""

    measured = "measured"    # eigene, gemessene Historie
    analog = "analog"        # Referenzfall aus anderem Markt / anderer Linie
    assumed = "assumed"      # reine Annahme


EVIDENCE_LABELS: dict[EvidenceClass, str] = {
    EvidenceClass.measured: "gemessen",
    EvidenceClass.analog: "analog",
    EvidenceClass.assumed: "angenommen",
}

# Deterministischer Abschlag je Evidenzklasse. Eine Maßnahme, deren Wirkung nie
# jemand gemessen hat, geht mit 60 % ihrer behaupteten Wirkung ins Portfolio.
# Das ist keine Bestrafung, sondern die ehrliche Erwartung über viele Fälle.
EVIDENCE_DISCOUNT: dict[EvidenceClass, float] = {
    EvidenceClass.measured: 1.00,
    EvidenceClass.analog: 0.85,
    EvidenceClass.assumed: 0.60,
}


class Band(BaseModel):
    """Dreiecksband. Ein Punktwert ist als low==mode==high darzustellen — die
    Oberfläche zeigt ihn dann als (nullbreites) Band, nie als nackte Präzision.
    """

    low: float = 0.0
    mode: float = 0.0
    high: float = 0.0

    @property
    def is_point(self) -> bool:
        return self.low == self.mode == self.high

    def scaled(self, factor: float) -> "Band":
        return Band(low=self.low * factor, mode=self.mode * factor,
                    high=self.high * factor)

    def __add__(self, other: "Band") -> "Band":
        return Band(low=self.low + other.low, mode=self.mode + other.mode,
                    high=self.high + other.high)


class PlanFigure(BaseModel):
    """Eine Zeile aus dem Absatzforecast: Plan gegen Prognose.

    Das ist die Schnittstelle zur ersten Säule. `source` hält fest, woher die
    Zeile kommt — solange dort "demo" steht, ist die Kopplung erzählt und nicht
    echt, und die Oberfläche sagt das auch.
    """

    id: str = Field(default_factory=lambda: _id("pln"))
    market: str                       # DE, AT, PL, ...
    line: str = ""                    # Produktlinie
    period: str = "FY2026"
    plan_eur: float = 0.0
    forecast_eur: float = 0.0
    currency: str = "EUR"
    source: str = "demo"              # demo | csv | api | manual
    updated_at: datetime = Field(default_factory=_now)

    @property
    def gap_eur(self) -> float:
        """Lücke gegen Plan. Positiv = Unterdeckung, negativ = Überdeckung."""
        return self.plan_eur - self.forecast_eur


class BridgeStep(BaseModel):
    """Eine Stufe der Revenue Bridge: dieser Teil der Lücke geht auf diese Ursache.

    `amount_eur` ist positiv, wenn die Ursache die Lücke *vergrößert*. Die Summe
    aller Stufen eines Marktes muss die Gesamtlücke ergeben; was übrig bleibt,
    landet in einer eigenen Stufe `unexplained` — siehe `bridge.py`. Ein hoher
    unerklärter Rest ist ein Befund, kein Schönheitsfehler.
    """

    id: str = Field(default_factory=lambda: _id("brs"))
    market: str = ""
    line: str = ""
    period: str = "FY2026"
    cause: CauseCode | None = None    # None == unerklärter Rest
    amount_eur: float = 0.0
    confidence: float = 0.0           # 0..1 — wie gut belegt die Zuordnung ist
    evidence_signal_ids: list[str] = Field(default_factory=list)  # MCI-Signale
    note: str = ""

    @property
    def is_unexplained(self) -> bool:
        return self.cause is None

    @property
    def is_exogenous(self) -> bool:
        return self.cause in EXOGENOUS_CAUSES


class Measure(BaseModel):
    """Eine Maßnahme aus dem Katalog — noch ohne Markt und ohne Dosis.

    `effect_grade` ist der Wirkungsgrad: welchen Anteil der adressierten
    Ursachenlücke die Maßnahme bei vollem Einsatz zurückholt, als Band. Nicht
    ein Euro-Betrag — der ergibt sich erst aus der Lücke des jeweiligen Marktes.
    Dieselbe Maßnahme ist in einem Markt mit großer Lücke mehr wert als in einem
    mit kleiner, und genau das soll die Allokation sehen.
    """

    id: str = Field(default_factory=lambda: _id("msr"))
    name: str = ""
    instrument: Instrument = Instrument.sales
    addresses: list[CauseCode] = Field(default_factory=list)

    effect_grade: Band = Field(default_factory=Band)
    evidence_class: EvidenceClass = EvidenceClass.assumed
    evidence_basis: list[str] = Field(default_factory=list)

    time_to_effect_months: int = 12   # bis die Wirkung einsetzt
    ramp_months: int = 6              # bis sie voll eingeschwungen ist
    cost_full_eur: float = 0.0        # Kosten bei Dosis 1.0, je Markt
    capacity_fte_months: float = 0.0  # Kapazitätsbedarf bei Dosis 1.0
    reversibility: str = "mittel"     # hoch | mittel | niedrig | sehr niedrig

    markets_applicable: list[str] = Field(default_factory=list)  # leer = alle
    note: str = ""

    @property
    def has_evidence(self) -> bool:
        return self.evidence_class is not EvidenceClass.assumed or bool(self.evidence_basis)


class Allocation(BaseModel):
    """Eine Maßnahme, in einem Markt, mit einer Dosis — und was sie bringt."""

    id: str = Field(default_factory=lambda: _id("alc"))
    measure_id: str = ""
    measure_name: str = ""
    instrument: Instrument = Instrument.sales
    market: str = ""
    period: str = "FY2026"

    dose: float = 0.0                 # 0..1 Einsatzgrad
    cost_eur: float = 0.0
    capacity_fte_months: float = 0.0

    effect_horizon: Band = Field(default_factory=Band)   # im Betrachtungszeitraum
    effect_run_rate: Band = Field(default_factory=Band)  # voll eingeschwungen, p.a.
    addresses: list[CauseCode] = Field(default_factory=list)
    evidence_class: EvidenceClass = EvidenceClass.assumed

    @property
    def efficiency(self) -> float:
        """Wirkung im Horizont je eingesetztem Euro."""
        return (self.effect_horizon.mode / self.cost_eur) if self.cost_eur else 0.0


class Portfolio(BaseModel):
    """Das Ergebnis der Allokation: was getan wird, was es kostet, was es bringt."""

    id: str = Field(default_factory=lambda: _id("pf"))
    period: str = "FY2026"
    horizon_months: int = 12
    budget_eur: float = 0.0
    capacity_fte_months: float = 0.0

    allocations: list[Allocation] = Field(default_factory=list)
    dominated: list[str] = Field(default_factory=list)   # nie gewählt: "lasst es"
    too_slow: list[str] = Field(default_factory=list)    # wirkt erst nach dem Horizont

    gap_eur: float = 0.0
    cost_used_eur: float = 0.0
    capacity_used: float = 0.0
    effect_horizon: Band = Field(default_factory=Band)
    effect_run_rate: Band = Field(default_factory=Band)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)

    @property
    def residual_gap_eur(self) -> float:
        """Was nach allen Maßnahmen offen bleibt. Nie unter null geschönt."""
        return max(0.0, self.gap_eur - self.effect_horizon.mode)

    @property
    def coverage(self) -> float:
        return (self.effect_horizon.mode / self.gap_eur) if self.gap_eur > 0 else 0.0

    @property
    def joint_share(self) -> float:
        """Anteil gemeinsam getragener Maßnahmen an der Wirkung —
        die Integrationskennzahl der fusionierten Einheit."""
        total = self.effect_horizon.mode
        if total <= 0:
            return 0.0
        joint = sum(a.effect_horizon.mode for a in self.allocations
                    if a.instrument is Instrument.joint)
        return joint / total


class MarketProfile(BaseModel):
    """Strukturmerkmale eines Marktes — Grundlage des Playbook-Transfers.

    Alle Merkmale sind auf 0..1 normiert, damit die Ähnlichkeit als gewichteter
    Abstand rechenbar bleibt. Die Werte sind Einschätzungen und als solche
    gekennzeichnet; sie ersetzen keine Marktforschung.
    """

    market: str
    channel_concentration: float = 0.5   # 0 = zersplittert, 1 = wenige große Kanäle
    regulation_intensity: float = 0.5
    competitive_density: float = 0.5
    maturity: float = 0.5                # 0 = früh, 1 = gesättigt
    price_level: float = 0.5             # relativ zum Konzerndurchschnitt
    note: str = ""


class MeasureOutcome(BaseModel):
    """Nachhalten: was wir erwartet haben, was eingetreten ist.

    Nichts hier wird von einer KI gefüllt. Ein Mensch trägt das Ergebnis ein,
    das Modul aggregiert nur — genau wie `mci.tracking`. Eine offene Maßnahme
    zählt nie als Treffer; offen bleibt offen, und das hält die Quote ehrlich.
    """

    id: str = Field(default_factory=lambda: _id("out"))
    measure_id: str = ""
    measure_name: str = ""
    market: str = ""
    period: str = "FY2026"

    expected: Band = Field(default_factory=Band)
    actual_eur: float | None = None
    status: str = "offen"             # offen | gemessen | abgebrochen
    owner: str = ""
    note: str = ""
    decided_at: datetime = Field(default_factory=_now)
    measured_at: datetime | None = None

    @property
    def deviation_eur(self) -> float | None:
        if self.actual_eur is None:
            return None
        return self.actual_eur - self.expected.mode

    @property
    def within_band(self) -> bool | None:
        if self.actual_eur is None:
            return None
        return self.expected.low <= self.actual_eur <= self.expected.high
