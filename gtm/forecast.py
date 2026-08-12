"""Schnittstelle zur ersten Säule: der Absatzforecast.

Das Cockpit rechnet nicht selbst vorher — es übernimmt Plan und Prognose aus dem
bestehenden Forecast-System. Dieses Modul ist die einzige Stelle, an der diese
Daten hereinkommen, damit der Anschluss an das echte System später ein Austausch
von einer Funktion ist und keine Operation am offenen Herzen.

Drei Wege sind vorgesehen: CSV, JSON und eine Liste von Dictionaries für den
direkten Aufruf aus einer API-Anbindung. Alle drei landen bei `from_rows`, das
prüft und normalisiert.

`source` wird an jeder Zeile mitgeführt. Solange dort „demo“ steht, sagt die
Oberfläche das auch — eine erzählte Kopplung darf nicht wie eine echte aussehen.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import BridgeStep, CauseCode, PlanFigure

REQUIRED_COLUMNS = ("market", "period", "plan_eur", "forecast_eur")


class ForecastFormatError(ValueError):
    """Die Eingabe passt nicht auf die erwartete Struktur."""


@dataclass
class LoadResult:
    figures: list[PlanFigure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.figures)


def _to_float(value, column: str, row_no: int) -> float:
    """Zahl einlesen, deutsche und englische Schreibweise.

    Die Regeln, in dieser Reihenfolge:

    1. Kommen Punkt und Komma vor, ist das **rechtere** das Dezimalzeichen
       (``1.234.567,89`` deutsch, ``1,234,567.89`` englisch).
    2. Kommt nur eines der Zeichen vor, und zwar **mehrfach**, ist es
       Tausendertrenner (``1.000.000``).
    3. Kommt es einmal vor und stehen **genau drei** Ziffern dahinter, gilt es
       ebenfalls als Tausendertrenner (``1.000`` ist eintausend).

    Regel 3 ist eine Setzung und die einzige Stelle im Paket, an der geraten
    wird: ``1.500`` heisst deutsch Tausendfuenfhundert und englisch Eins Komma
    Fuenf. Fuer Planwerte in Euro ist die erste Lesart die richtige. Wer
    Nachkommastellen braucht, schreibt sie zweistellig (``1.50``) oder liefert
    die Zahl als echten numerischen Typ - dann greift keine dieser Regeln.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    cleaned = str(value).strip().replace("\u20ac", "")
    for junk in (" ", "\u00a0", "\u202f", "'"):
        cleaned = cleaned.replace(junk, "")
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("+-")

    has_dot, has_comma = "." in cleaned, "," in cleaned
    if has_dot and has_comma:
        decimal_sep = "." if cleaned.rfind(".") > cleaned.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        cleaned = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        tail = cleaned.rsplit(sep, 1)[1]
        if cleaned.count(sep) > 1 or (len(tail) == 3 and tail.isdigit()):
            cleaned = cleaned.replace(sep, "")       # Tausendertrenner
        else:
            cleaned = cleaned.replace(sep, ".")      # Dezimalzeichen

    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ForecastFormatError(
            f"Zeile {row_no}: Spalte \u201e{column}\u201c ist keine Zahl: {value!r}"
        ) from exc
    return -number if negative else number


def from_rows(rows: list[dict], *, source: str = "api") -> LoadResult:
    """Normalisiert Rohzeilen zu Planzeilen und meldet, was auffällt."""
    result = LoadResult()
    if not rows:
        result.warnings.append("Keine Zeilen empfangen.")
        return result

    missing = [c for c in REQUIRED_COLUMNS if c not in rows[0]]
    if missing:
        raise ForecastFormatError(
            f"Pflichtspalten fehlen: {', '.join(missing)}. "
            f"Erwartet werden mindestens {', '.join(REQUIRED_COLUMNS)}."
        )

    for i, row in enumerate(rows, start=1):
        market = str(row.get("market", "")).strip()
        if not market:
            result.warnings.append(f"Zeile {i} ohne Markt — übersprungen.")
            continue
        figure = PlanFigure(
            market=market,
            line=str(row.get("line", "") or "").strip(),
            period=str(row.get("period", "FY2026")).strip(),
            plan_eur=_to_float(row.get("plan_eur"), "plan_eur", i),
            forecast_eur=_to_float(row.get("forecast_eur"), "forecast_eur", i),
            currency=str(row.get("currency", "EUR") or "EUR").strip(),
            source=source,
        )
        if figure.plan_eur <= 0:
            result.warnings.append(
                f"{figure.market}/{figure.line or '—'}: Plan ist 0 oder negativ."
            )
        result.figures.append(figure)

    result.warnings.extend(validate(result.figures))
    return result


def from_csv(path: str | Path, *, source: str = "csv", delimiter: str = ";") -> LoadResult:
    """Liest eine CSV. Semikolon als Standard, weil Excel im deutschsprachigen
    Raum so exportiert."""
    text = Path(path).read_text(encoding="utf-8-sig")
    sample = text.split("\n", 1)[0]
    if delimiter not in sample and "," in sample:
        delimiter = ","
    rows = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
    return from_rows(rows, source=source)


def from_json(path: str | Path, *, source: str = "json") -> LoadResult:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("figures", data.get("rows", []))
    return from_rows(list(data), source=source)


def validate(figures: list[PlanFigure]) -> list[str]:
    """Plausibilitätsprüfungen, die vor jeder Entscheidung laufen sollten."""
    warnings: list[str] = []
    if not figures:
        return ["Keine Planzeilen geladen."]

    periods = {f.period for f in figures}
    if len(periods) > 1:
        warnings.append(
            f"Mehrere Perioden in einer Datei ({', '.join(sorted(periods))}) — "
            f"die Brücke rechnet immer nur eine davon."
        )
    seen: set[tuple[str, str, str]] = set()
    for f in figures:
        key = (f.market, f.line, f.period)
        if key in seen:
            warnings.append(
                f"Doppelte Zeile für {f.market}/{f.line or '—'}/{f.period} — "
                f"die Lücke wird dadurch doppelt gezählt."
            )
        seen.add(key)

    total_plan = sum(f.plan_eur for f in figures)
    total_gap = sum(f.gap_eur for f in figures)
    if total_plan > 0 and total_gap / total_plan > 0.5:
        warnings.append(
            f"Die Lücke beträgt {total_gap / total_plan:.0%} des Plans. Das ist "
            f"kein Maßnahmenthema mehr, sondern eine Planrevision."
        )
    return warnings


def attributions_from_rows(rows: list[dict], *, period: str = "FY2026") -> list[BridgeStep]:
    """Ursachenzuordnungen aus Rohzeilen (market, cause, amount_eur, note)."""
    steps: list[BridgeStep] = []
    for i, row in enumerate(rows, start=1):
        raw_cause = str(row.get("cause", "")).strip()
        try:
            cause = CauseCode(raw_cause)
        except ValueError as exc:
            raise ForecastFormatError(
                f"Zeile {i}: unbekannte Ursache {raw_cause!r}. Erlaubt sind: "
                f"{', '.join(c.value for c in CauseCode)}."
            ) from exc
        steps.append(BridgeStep(
            market=str(row.get("market", "")).strip(),
            line=str(row.get("line", "") or "").strip(),
            period=str(row.get("period", period)).strip(),
            cause=cause,
            amount_eur=_to_float(row.get("amount_eur"), "amount_eur", i),
            note=str(row.get("note", "") or "").strip(),
        ))
    return steps


def to_rows(figures: list[PlanFigure]) -> list[dict]:
    """Rückweg — damit sich ein geladener Stand exportieren und prüfen lässt."""
    return [
        {
            "market": f.market, "line": f.line, "period": f.period,
            "plan_eur": f.plan_eur, "forecast_eur": f.forecast_eur,
            "gap_eur": f.gap_eur, "currency": f.currency, "source": f.source,
        }
        for f in figures
    ]
