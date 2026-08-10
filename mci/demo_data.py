"""Rich demo dataset — a believable, fully-populated intelligence picture.

`mci.demo`'s five samples prove the pipeline works; this module fills the whole
cockpit so an MVP/PoC walkthrough has something to show in *every* view:
launch cadence needs ≥3 dated launches per competitor, the trend radar needs
terms spread across time, spec-share needs mentions per month, sentiment needs
customer voice, and the correlation rules need co-occurring signal types.

Everything is fictional but internally consistent. Documents are dated relative
to "now" so the picture stays fresh whenever the demo is run, and they flow
through the *real* pipeline — extraction, guardrails, auditor, scoring — so
nothing here bypasses the evidence rules. Two documents are deliberately
rejectable (hedged "facts") to show the guardrails biting.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .ingestion import RawDocument
from .models import SourceClass


def _ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _doc(days: int, url: str, title: str, publisher: str, klass: SourceClass,
         text: str, channel: str = "web") -> RawDocument:
    return RawDocument(url=url, text=text, title=title, publisher=publisher,
                       source_class=klass, published_at=_ago(days), channel=channel)


def documents() -> list[RawDocument]:
    """The full demo corpus, newest last so 'first_seen' ordering looks natural."""
    d: list[RawDocument] = []

    # ---------------- Nordwall (DE) — approvals + launch cadence ------------
    for n, (days, eta) in enumerate([(400, "ETA-23/0451"), (250, "ETA-24/0088"),
                                     (95, "ETA-24/0123")]):
        d.append(_doc(
            days, f"https://www.dibt.de/register/{eta.lower().replace('/', '-')}",
            f"{eta} Nordwall", "dibt.de", SourceClass.A,
            f"Nordwall Systeme GmbH erhielt die Europäische Technische Bewertung "
            f"{eta} für ein Verbundabdichtungssystem im Segment Fassade für den "
            f"Markt DE. Die Bewertung deckt Anwendungen im Neubau und in der "
            f"Sanierung ab."))
    # independent second source -> triangulates the newest ETA to "confirmed"
    d.append(_doc(
        93, "https://fachpresse-bau.example/nordwall-eta-24-0123",
        "Nordwall ETA — Fachbericht", "Fachpresse Bau (Verband)", SourceClass.B,
        "Nordwall Systeme GmbH erhielt die Europäische Technische Bewertung "
        "ETA-24/0123 für ein Verbundabdichtungssystem im Segment Fassade für den "
        "Markt DE. Meldung laut Fachpresse."))
    # Launch history — three dated, distinctly worded launches give the cadence
    # model a rhythm (near-identical texts would be merged as duplicates).
    d.append(_doc(
        430, "https://www.nordwall.example/presse/aquastop-1k",
        "Nordwall Markteinführung AquaStop 1K", "nordwall.example", SourceClass.C,
        "Nordwall Systeme GmbH bringt das einkomponentige Verbundabdichtungs"
        "system AquaStop 1K auf den Markt, zunächst exklusiv über den Fachhandel "
        "in DE."))
    d.append(_doc(
        250, "https://www.nordwall.example/presse/aquastop-2k",
        "Nordwall Markteinführung AquaStop 2K", "nordwall.example", SourceClass.C,
        "Mit AquaStop 2K stellt Nordwall Systeme GmbH erstmals eine zwei"
        "komponentige Variante für den Schwimmbadbau vor. Der Vertrieb startet "
        "über Objektpartner in DE und AT."))
    d.append(_doc(
        70, "https://www.nordwall.example/presse/aquastop-rapid",
        "Nordwall Markteinführung AquaStop Rapid", "nordwall.example", SourceClass.C,
        "Nordwall Systeme GmbH erweitert das Sortiment um AquaStop Rapid mit "
        "verkürzter Trocknungszeit von vier Stunden. Die Markteinführung "
        "adressiert die Sanierung im Bestand."))
    d.append(_doc(
        60, "https://www.nordwall.example/presse/werk-koeln",
        "Nordwall erweitert Werk Köln", "nordwall.example", SourceClass.C,
        "Nordwall Systeme GmbH investiert 24 Mio. EUR in eine zusätzliche "
        "Produktionslinie am Standort Köln für Verbundabdichtung. Die Inbetrieb"
        "nahme ist für 2027 geplant."))
    d.append(_doc(
        21, "https://news.example/nordwall-preise",
        "Nordwall passt Preise an", "Bau-News", SourceClass.B,
        "Nordwall Systeme GmbH senkt die Preise für Verbundabdichtung im "
        "Fachhandel DE um 6 Prozent zum 1. des kommenden Quartals."))
    d.append(_doc(
        12, "https://bewertungen.example/nordwall",
        "Kundenstimmen Nordwall", "Bewertungsportal", SourceClass.C,
        "Verarbeiter berichten: Das Nordwall Verbundsystem ist zuverlässig und "
        "hochwertig, die Verarbeitung ist einfach und schnell."))

    # ---------------- Altura (US) — capacity + hiring + patent --------------
    d.append(_doc(
        300, "https://careers.altura.example/job/process-engineer-tr",
        "Altura hiring Izmir", "careers.altura.example", SourceClass.C,
        "Altura Building Products sucht einen Process Engineer für ein neues Werk "
        "in Izmir, TR, mit Schwerpunkt Extrusion von Entkopplungsmatten. Der "
        "Produktionsstart ist für 2026 geplant."))
    d.append(_doc(
        180, "https://ppubs.uspto.gov/altura-decoupling",
        "Altura Patent Entkopplung", "uspto.gov", SourceClass.A,
        "Altura Building Products meldete ein Patent für eine dünnschichtige "
        "Entkopplungsmatte mit reduzierter Aufbauhöhe für den Markt US an."))
    d.append(_doc(
        150, "https://www.sec.gov/edgar/altura-10q",
        "Altura Quartalsbericht", "sec.gov", SourceClass.A,
        "Altura Building Products meldet für das Quartal einen Umsatz von 412 Mio. "
        "USD im Segment Untergrund, ein Plus von 9 Prozent gegenüber dem Vorjahr."))
    d.append(_doc(
        390, "https://www.altura.example/news/decomat-basic",
        "Altura Launch DecoMat Basic", "altura.example", SourceClass.C,
        "Altura Building Products bringt die Entkopplungsmatte DecoMat Basic für "
        "den Sanierungsmarkt US auf den Markt. Die Auslieferung erfolgt über "
        "Pro-Dealer."))
    d.append(_doc(
        210, "https://www.altura.example/news/decomat-pro",
        "Altura Launch DecoMat Pro", "altura.example", SourceClass.C,
        "Mit DecoMat Pro stellt Altura Building Products eine verstärkte Variante "
        "für Objektflächen vor. Die Markteinführung umfasst die Märkte US und CA."))
    d.append(_doc(
        75, "https://www.altura.example/news/decomat-thin",
        "Altura Launch DecoMat Thin", "altura.example", SourceClass.C,
        "Altura Building Products erweitert das Programm um DecoMat Thin mit nur "
        "3 mm Aufbauhöhe. Der Roll-out startet im laufenden Quartal in den USA."))
    d.append(_doc(
        30, "https://careers.altura.example/job/rd-lead-de",
        "Altura R&D Lead DE", "careers.altura.example", SourceClass.C,
        "Altura Building Products sucht einen R&D Lead für Abdichtungssysteme mit "
        "Dienstsitz in Deutschland. Der Aufbau eines europäischen Entwicklungs"
        "teams ist vorgesehen."))
    d.append(_doc(
        8, "https://bewertungen.example/altura",
        "Kundenstimmen Altura", "Bewertungsportal", SourceClass.C,
        "Verarbeiter berichten zu Altura Building Products: Lieferverzögerung und "
        "Beschwerde beim Service; die Entkopplungsmatte sei teuer und die Qualität "
        "schwach."))

    # ---------------- Marmara (TR) — market + channel ------------------------
    d.append(_doc(
        220, "https://www.tuik.gov.tr/insaat-2026",
        "Bauindikatoren TR", "tuik.gov.tr", SourceClass.A,
        "Die Zahl der Baugenehmigungen in der Türkei stieg im Jahresvergleich um "
        "14 Prozent, der Sanierungsanteil liegt bei 38 Prozent."))
    d.append(_doc(
        120, "https://www.marmara.example/haber/ihracat",
        "Marmara Export", "marmara.example", SourceClass.C,
        "Marmara Yapı A.Ş. beliefert ab sofort Distributoren in DE und NL mit "
        "Fliesenverlegesystemen. Der Aufbau eines Lagers in Rotterdam läuft."))
    d.append(_doc(
        45, "https://fachpresse-bau.example/marmara-preis",
        "Marmara Preisoffensive", "Fachpresse Bau (Verband)", SourceClass.B,
        "Marmara Yapı A.Ş. bietet Fliesenverlegesysteme in DE mit einem Rabatt von "
        "12 Prozent gegenüber dem Vorjahrespreis an."))

    # ---------------- CanardBuild (CA) — launch + trade fair -----------------
    d.append(_doc(
        260, "https://nrc.canada.ca/ccmc-canard-1",
        "CCMC Bewertung Canard", "nrc.canada.ca", SourceClass.A,
        "CanardBuild Inc. erhielt eine CCMC-Bewertung für ein Fassadensystem im "
        "Markt CA."))
    d.append(_doc(
        140, "https://www.canardbuild.example/news/thin-panel",
        "Canard dünnschichtige Platte", "canardbuild.example", SourceClass.C,
        "CanardBuild Inc. führt eine dünnschichtige Fassadenplatte für den "
        "Sanierungsmarkt in CA ein."))
    d.append(_doc(
        35, "https://news.example/canard-messe",
        "Canard auf der Messe", "Bau-News", SourceClass.B,
        "CanardBuild Inc. zeigte auf der Fachmesse erstmals eine dünnschichtige "
        "Fassadenplatte für die Sanierung mit reduzierter Aufbauhöhe."))

    # ---------------- Severn (UK) — regulatory + rumour ----------------------
    d.append(_doc(
        200, "https://www.gov.uk/severn-standard",
        "Severn Normung UK", "gov.uk", SourceClass.A,
        "Severn Systems Ltd ist als Hersteller in der aktualisierten britischen "
        "Norm für Bodensysteme gelistet."))
    # deliberately rejectable — hedged 'fact'
    d.append(_doc(
        18, "https://blog.example/severn-rumor",
        "Severn rumour", "blog.example", SourceClass.D,
        "Severn Systems dürfte wahrscheinlich bald die Preise senken, vermutlich "
        "um Marktanteile zu gewinnen."))

    # ---------------- market-wide context ------------------------------------
    d.append(_doc(
        90, "https://ec.europa.eu/eurostat/bau-2026",
        "Bauindikatoren EU", "ec.europa.eu", SourceClass.A,
        "Die Sanierungsquote im EU-Wohnbau liegt bei 1,2 Prozent jährlich; der "
        "Neubau ist im Jahresvergleich um 5 Prozent rückläufig."))
    d.append(_doc(
        25, "https://www.census.gov/construction/2026",
        "US Bauausgaben", "census.gov", SourceClass.A,
        "Die Bauausgaben im US-Wohnungsbau lagen im Berichtsmonat 3 Prozent über "
        "dem Vorjahreswert, getragen von der Sanierung."))
    # second rejectable sample
    d.append(_doc(
        5, "https://blog.example/markt-spekulation",
        "Marktspekulation", "blog.example", SourceClass.D,
        "Der Sanierungsmarkt dürfte vermutlich boomen und die Preise könnten "
        "möglicherweise steigen."))

    return d


def manual_notes() -> list[str]:
    """Field-sales observations — the manual channel, co-equal to web/PDF."""
    return [
        "Auf der Messe zeigte CanardBuild Inc. erstmals eine dünnschichtige "
        "Fassadenplatte für den Sanierungsmarkt in CA.",
        "Ein Fachhändler in DE berichtet, dass Nordwall Systeme GmbH "
        "Verlegewerkzeug kostenlos zum Verbundsystem beilegt.",
        "Ausschreibung in NL nennt Marmara Yapı A.Ş. erstmals als zugelassenes "
        "Fabrikat für Fliesenverlegesysteme.",
    ]
