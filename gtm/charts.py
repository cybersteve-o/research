"""Diagramme des Cockpits (Altair — liegt Streamlit bei, keine neue Abhängigkeit).

Die Palette ist dieselbe wie im MCI-Paket und aus gutem Grund unverändert
übernommen: **Farbe folgt der Entität, nicht dem Rang** — ein Markt, der im
Recherchewerkzeug blau ist, bleibt im Cockpit blau. Zwei Werkzeuge mit
unterschiedlichen Farben für dieselbe Sache erzeugen in der Vorführung genau die
Verwirrung, die der Dreiklang auflösen soll.

Die Palette hat die sechs Farbprüfungen bestanden (Helligkeitsband, Chroma-
Untergrenze, Trennung bei Farbfehlsichtigkeit, Normalsicht-Untergrenze,
Kontrast). Drei Töne liegen im Hellmodus unter 3:1 gegen die Fläche — deshalb
trägt jedes Diagramm **Entlastung**: Legende, Tooltips, und die Oberfläche
stellt zu jedem Bild eine Tabelle daneben.

Eine Achse je Diagramm, nie zwei Skalen. Wo zwei Größen unterschiedlicher
Einheit auftreten (Wirkung und Grenzertrag), stehen zwei Diagramme.

Jede Funktion gibt None zurück, wenn nichts zu zeichnen ist — die Aufrufer
schreiben dann eine Zeile Text statt einen leeren Rahmen zu zeichnen.
"""

from __future__ import annotations

try:  # Altair kommt mit Streamlit; ohne UI-Extra fehlt es, das ist zulässig.
    import altair as alt
except Exception:  # noqa: BLE001  # pragma: no cover
    alt = None  # type: ignore[assignment]

# Feste kategoriale Reihenfolge — validierte Paare für Hell und Dunkel.
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
                "#008300", "#4a3aa7", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}
NEUTRAL = "#9a9a94"
SURFACE = "#fcfcfb"

_HEIGHT = 280


def _available() -> bool:
    return alt is not None


def _base(data: list[dict]):
    return alt.Chart(alt.Data(values=data))


def bridge_waterfall(rows: list[dict]):
    """Die Lücke, Ursache für Ursache aufgebaut.

    Die Rolle einer Stufe trägt die Farbe, nicht ihre Größe: die Summe neutral,
    Ursachen in der Serienfarbe, Exogenes abgesetzt und der unerklärte Rest in
    Warnfarbe. So springt ins Auge, welcher Teil der Lücke überhaupt bearbeitbar
    ist — und welcher nur erklärt werden kann.
    """
    if not _available() or not rows:
        return None
    roles = ["Ursache", "Exogen", "Unerklärt", "Summe"]
    colours = [SERIES_LIGHT[0], SERIES_LIGHT[3], STATUS["serious"], NEUTRAL]
    order = [r["label"] for r in sorted(rows, key=lambda r: r["order"])]
    bars = (
        _base(rows)
        .mark_bar(cornerRadius=4, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("label:N", title=None, sort=order,
                    axis=alt.Axis(labelAngle=-35, labelLimit=160)),
            y=alt.Y("start:Q", title="Anteil an der Lücke (€)",
                    axis=alt.Axis(format="~s")),
            y2=alt.Y2("end:Q"),
            color=alt.Color("role:N", title="Rolle",
                            scale=alt.Scale(domain=roles, range=colours)),
            tooltip=[alt.Tooltip("label:N", title="Stufe"),
                     alt.Tooltip("role:N", title="Rolle"),
                     alt.Tooltip("amount:Q", title="Betrag", format=",.0f")],
        )
    )
    # Direktbeschriftung: die Beträge stehen am Balken, damit die drei Töne
    # unter 3:1 Kontrast nicht allein die Identität tragen müssen.
    labels = (
        _base(rows)
        .mark_text(dy=-8, fontSize=11, color="#3b3b36")
        .encode(
            x=alt.X("label:N", sort=order),
            y=alt.Y("end:Q"),
            text=alt.Text("amount:Q", format=",.2s"),
        )
    )
    return (bars + labels).properties(height=_HEIGHT + 60)


def evidence_stack(rows: list[dict]):
    """Wie gut die Lücke je Markt belegt ist — Zustand, also Statusfarben."""
    if not _available() or not rows:
        return None
    order = ["belegt", "schwach belegt", "unbelegt"]
    present = [b for b in order if any(r["band"] == b for r in rows)]
    colours = {"belegt": STATUS["good"], "schwach belegt": STATUS["warning"],
               "unbelegt": STATUS["serious"]}
    return (
        _base(rows)
        .mark_bar(cornerRadius=3, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("market:N", title=None),
            y=alt.Y("amount:Q", title="Lücke (€)", stack=True),
            color=alt.Color("band:N", title="Belegdichte",
                            scale=alt.Scale(domain=present,
                                            range=[colours[b] for b in present])),
            tooltip=[alt.Tooltip("market:N", title="Markt"),
                     alt.Tooltip("band:N", title="Belegdichte"),
                     alt.Tooltip("amount:Q", title="Betrag", format=",.0f")],
        )
        .properties(height=_HEIGHT)
    )


def measure_bars(rows: list[dict]):
    """Wirkung je Maßnahme mit Band.

    Der Balken zeigt den Erwartungswert, die aufgesetzte Linie das Band. Ein
    Balken ohne Band wäre in diesem Werkzeug eine Lüge — es gibt keine Wirkung
    ohne Unsicherheit.
    """
    if not _available() or not rows:
        return None
    instruments = ["Vertrieb", "Marketing", "Gemeinsam"]
    present = [i for i in instruments if any(r["instrument"] == i for r in rows)]
    colours = {"Vertrieb": SERIES_LIGHT[0], "Marketing": SERIES_LIGHT[1],
               "Gemeinsam": SERIES_LIGHT[2]}
    order = [r["label"] for r in rows]

    bars = (
        _base(rows)
        .mark_bar(cornerRadius=4, height=16)
        .encode(
            x=alt.X("effect:Q", title="Wirkung im Horizont (€)",
                    axis=alt.Axis(format="~s")),
            y=alt.Y("label:N", title=None, sort=order,
                    axis=alt.Axis(labelLimit=320)),
            color=alt.Color("instrument:N", title="Träger",
                            scale=alt.Scale(domain=present,
                                            range=[colours[i] for i in present])),
            tooltip=[alt.Tooltip("label:N", title="Maßnahme"),
                     alt.Tooltip("instrument:N", title="Träger"),
                     alt.Tooltip("evidence:N", title="Evidenz"),
                     alt.Tooltip("dose:Q", title="Dosis", format=".0%"),
                     alt.Tooltip("cost:Q", title="Kosten", format=",.0f"),
                     alt.Tooltip("effect_low:Q", title="Wirkung min", format=",.0f"),
                     alt.Tooltip("effect:Q", title="Wirkung erwartet", format=",.0f"),
                     alt.Tooltip("effect_high:Q", title="Wirkung max", format=",.0f")],
        )
    )
    band = (
        _base(rows)
        .mark_rule(strokeWidth=2, color="#5b5b55")
        .encode(
            x=alt.X("effect_low:Q"),
            x2=alt.X2("effect_high:Q"),
            y=alt.Y("label:N", sort=order),
        )
    )
    return (bars + band).properties(height=max(_HEIGHT, 26 * len(rows)))


def frontier_lines(rows: list[dict]):
    """Wirkung über dem Budget. Zwei Reihen, eine Einheit, eine Achse."""
    if not _available() or not rows:
        return None
    series = ["Im Horizont", "Eingeschwungen p. a."]
    present = [s for s in series if any(r["series"] == s for r in rows)]
    return (
        _base(rows)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=70))
        .encode(
            x=alt.X("budget:Q", title="Budget (€)", axis=alt.Axis(format="~s")),
            y=alt.Y("effect:Q", title="Wirkung (€)", axis=alt.Axis(format="~s")),
            color=alt.Color("series:N", title="Betrachtung",
                            scale=alt.Scale(domain=present,
                                            range=SERIES_LIGHT[:len(present)])),
            tooltip=[alt.Tooltip("series:N", title="Betrachtung"),
                     alt.Tooltip("budget:Q", title="Budget", format=",.0f"),
                     alt.Tooltip("effect:Q", title="Wirkung", format=",.0f"),
                     alt.Tooltip("n:Q", title="Maßnahmen")],
        )
        .properties(height=_HEIGHT)
    )


def marginal_lines(rows: list[dict]):
    """Grenzertrag je zusätzlichem Euro, mit der Eins-Linie als Maßstab.

    Unterhalb der Linie kostet zusätzliches Budget mehr, als es zurückholt.
    """
    if not _available() or not rows:
        return None
    series = ["Im Horizont", "Eingeschwungen p. a."]
    present = [s for s in series if any(r["series"] == s for r in rows)]
    lines = (
        _base(rows)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=70))
        .encode(
            x=alt.X("budget:Q", title="Budget (€)", axis=alt.Axis(format="~s")),
            y=alt.Y("marginal:Q", title="Grenzertrag (€ je €)"),
            color=alt.Color("series:N", title="Betrachtung",
                            scale=alt.Scale(domain=present,
                                            range=SERIES_LIGHT[:len(present)])),
            tooltip=[alt.Tooltip("series:N", title="Betrachtung"),
                     alt.Tooltip("budget:Q", title="Budget", format=",.0f"),
                     alt.Tooltip("marginal:Q", title="Grenzertrag", format=".2f")],
        )
    )
    breakeven = (
        alt.Chart(alt.Data(values=[{"y": 1.0}]))
        .mark_rule(strokeDash=[5, 4], strokeWidth=1.5, color=NEUTRAL)
        .encode(y=alt.Y("y:Q"))
    )
    return (lines + breakeven).properties(height=_HEIGHT)


def effect_timeline(rows: list[dict], horizon_months: int):
    """Wirkungsniveau über der Zeit, mit der Horizontlinie.

    Das Bild, das die Jahresdiskussion beendet: alles rechts der Linie ist
    beschlossen, aber im Betrachtungszeitraum nicht verdient.
    """
    if not _available() or not rows:
        return None
    area = (
        _base(rows)
        .mark_area(opacity=0.25, color=SERIES_LIGHT[0])
        .encode(
            x=alt.X("month:Q", title="Monate ab Beschluss"),
            y=alt.Y("level:Q", title="Wirkungsniveau, annualisiert (€)",
                    axis=alt.Axis(format="~s")),
        )
    )
    line = (
        _base(rows)
        .mark_line(strokeWidth=2, color=SERIES_LIGHT[0])
        .encode(
            x=alt.X("month:Q"),
            y=alt.Y("level:Q"),
            tooltip=[alt.Tooltip("month:Q", title="Monat"),
                     alt.Tooltip("level:Q", title="Niveau p. a.", format=",.0f")],
        )
    )
    horizon = (
        alt.Chart(alt.Data(values=[{"x": horizon_months}]))
        .mark_rule(strokeDash=[5, 4], strokeWidth=1.5, color=STATUS["serious"])
        .encode(x=alt.X("x:Q"))
    )
    return (area + line + horizon).properties(height=_HEIGHT)


def market_coverage(rows: list[dict]):
    """Lücke und Wirkung je Markt nebeneinander — eine Einheit, eine Achse."""
    if not _available() or not rows:
        return None
    long: list[dict] = []
    for r in rows:
        long.append({"market": r["market"], "kind": "Lücke", "value": r["gap"]})
        long.append({"market": r["market"], "kind": "Wirkung", "value": r["effect"]})
    order = [r["market"] for r in rows]
    return (
        alt.Chart(alt.Data(values=long))
        .mark_bar(cornerRadius=3, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("market:N", title=None, sort=order),
            y=alt.Y("value:Q", title="€", axis=alt.Axis(format="~s")),
            xOffset=alt.XOffset("kind:N"),
            color=alt.Color("kind:N", title=None,
                            scale=alt.Scale(domain=["Lücke", "Wirkung"],
                                            range=[NEUTRAL, SERIES_LIGHT[0]])),
            tooltip=[alt.Tooltip("market:N", title="Markt"),
                     alt.Tooltip("kind:N", title=None),
                     alt.Tooltip("value:Q", title="Betrag", format=",.0f")],
        )
        .properties(height=_HEIGHT)
    )


def outcome_dots(rows: list[dict]):
    """Erwartungsband als Linie, Ergebnis als Punkt — Treffer oder daneben."""
    if not _available() or not rows:
        return None
    measured = [r for r in rows if r["actual"] is not None]
    if not measured:
        return None
    order = [r["label"] for r in measured]
    band = (
        alt.Chart(alt.Data(values=measured))
        .mark_rule(strokeWidth=3, color=NEUTRAL, opacity=0.55)
        .encode(
            x=alt.X("expected_low:Q", title="€", axis=alt.Axis(format="~s")),
            x2=alt.X2("expected_high:Q"),
            y=alt.Y("label:N", title=None, sort=order),
        )
    )
    dots = (
        alt.Chart(alt.Data(values=measured))
        .mark_circle(size=150, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("actual:Q"),
            y=alt.Y("label:N", sort=order),
            color=alt.Color("treffer:N", title="Ergebnis",
                            scale=alt.Scale(domain=["im Band", "daneben"],
                                            range=[STATUS["good"], STATUS["critical"]])),
            tooltip=[alt.Tooltip("label:N", title="Maßnahme"),
                     alt.Tooltip("expected_low:Q", title="Erwartet min", format=",.0f"),
                     alt.Tooltip("expected:Q", title="Erwartet", format=",.0f"),
                     alt.Tooltip("expected_high:Q", title="Erwartet max", format=",.0f"),
                     alt.Tooltip("actual:Q", title="Eingetreten", format=",.0f"),
                     alt.Tooltip("treffer:N", title="Ergebnis")],
        )
    )
    return (band + dots).properties(height=max(_HEIGHT, 28 * len(measured)))


def similarity_matrix(rows: list[dict]):
    """Marktähnlichkeit — Magnitude, also ein Farbton hell nach dunkel."""
    if not _available() or not rows:
        return None
    return (
        _base(rows)
        .mark_rect(cornerRadius=3, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("target:N", title="Zielmarkt"),
            y=alt.Y("source:N", title="Ursprungsmarkt"),
            color=alt.Color("similarity:Q", title="Ähnlichkeit",
                            scale=alt.Scale(scheme="blues", domain=[0, 1])),
            tooltip=[alt.Tooltip("source:N", title="Von"),
                     alt.Tooltip("target:N", title="Nach"),
                     alt.Tooltip("similarity:Q", title="Ähnlichkeit", format=".2f")],
        )
        .properties(height=_HEIGHT)
    )


def realization_bars(rows: list[dict]):
    """Realisierungsanteil je Maßnahme im Horizont — was wann ankommt.

    Die Maßnahmen mit Anteil null sind der Punkt dieses Bildes: sie sind nicht
    schlecht, sie sind nur zu langsam für diesen Zeitraum.
    """
    if not _available() or not rows:
        return None
    order = [r["measure"] for r in rows]
    return (
        _base(rows)
        .mark_bar(cornerRadius=4, height=14)
        .encode(
            x=alt.X("realization:Q", title="Anteil der Jahreswirkung im Horizont",
                    axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("measure:N", title=None, sort=order),
            color=alt.Color(
                "realization:Q", title="Anteil", legend=None,
                scale=alt.Scale(domain=[0, 0.5, 1],
                                range=[STATUS["critical"], STATUS["warning"],
                                       STATUS["good"]])),
            tooltip=[alt.Tooltip("measure:N", title="Maßnahme"),
                     alt.Tooltip("instrument:N", title="Träger"),
                     alt.Tooltip("time_to_effect:Q", title="Wirkzeit (Monate)"),
                     alt.Tooltip("realization:Q", title="Realisierung", format=".0%")],
        )
        .properties(height=max(_HEIGHT, 24 * len(rows)))
    )
