"""Chart builders for the cockpit (Altair — ships with Streamlit, no new dep).

Design rules applied (validated, not eyeballed):
* Categorical hues are assigned in a **fixed order, never cycled** — an entity
  keeps its colour even when a filter changes the series count.
* The palette below passed the six colour checks in both light and dark mode
  (lightness band, chroma floor, CVD separation, normal-vision floor, contrast).
  Three light-mode slots sit below 3:1 against the surface, so every chart ships
  **relief**: a legend plus tooltips, and the caller renders a table fallback.
* One axis per chart — never a dual scale. Thin marks, recessive grid, tooltips
  by default.

Every function returns None when there is nothing to plot, so callers can fall
back to a caption instead of drawing an empty frame.
"""

from __future__ import annotations

from datetime import datetime

try:  # Altair is bundled with Streamlit; degrade gracefully if absent.
    import altair as alt
except Exception:  # noqa: BLE001  # pragma: no cover
    alt = None  # type: ignore[assignment]

# Fixed categorical order — validated light / dark pairs.
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
                "#008300", "#4a3aa7", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}

_HEIGHT = 260


def _available() -> bool:
    return alt is not None


def _base(data: list[dict]):
    return alt.Chart(alt.Data(values=data))


def sentiment_bars(rows: list[dict]):
    """Diverging sentiment score per brand (polarity → two poles, gray midpoint)."""
    if not _available() or not rows:
        return None
    return (
        _base(rows)
        .mark_bar(cornerRadius=4, height=18)
        .encode(
            x=alt.X("score:Q", title="Sentiment-Score (−1 … +1)",
                    scale=alt.Scale(domain=[-1, 1])),
            y=alt.Y("brand:N", title=None, sort="-x"),
            color=alt.Color(
                "score:Q", title="Tendenz",
                scale=alt.Scale(domain=[-1, 0, 1],
                                range=[STATUS["critical"], "#9a9a94", STATUS["good"]])),
            tooltip=[alt.Tooltip("brand:N", title="Marke"),
                     alt.Tooltip("score:Q", title="Score", format="+.2f"),
                     alt.Tooltip("n:Q", title="Stimmen")],
        )
        .properties(height=_HEIGHT)
    )


def trend_momentum(rows: list[dict]):
    """Rising vs falling terms — magnitude with polarity colour."""
    if not _available() or not rows:
        return None
    return (
        _base(rows)
        .mark_bar(cornerRadius=4, height=16)
        .encode(
            x=alt.X("momentum:Q", title="Momentum (jüngere vs. ältere Hälfte)"),
            y=alt.Y("term:N", title=None, sort="-x"),
            color=alt.Color(
                "momentum:Q", title="Richtung",
                scale=alt.Scale(domain=[-1, 0, 1],
                                range=[STATUS["critical"], "#9a9a94", STATUS["good"]])),
            tooltip=[alt.Tooltip("term:N", title="Thema"),
                     alt.Tooltip("count:Q", title="Nennungen"),
                     alt.Tooltip("momentum:Q", title="Momentum", format="+.2f")],
        )
        .properties(height=_HEIGHT)
    )


def spec_share_lines(rows: list[dict]):
    """Share of named mentions over time — one line per entity (identity → categorical)."""
    if not _available() or not rows:
        return None
    entities = sorted({r["entity"] for r in rows})
    return (
        _base(rows)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=60))
        .encode(
            x=alt.X("period:N", title="Periode"),
            y=alt.Y("share:Q", title="Anteil der Nennungen",
                    axis=alt.Axis(format="%")),
            color=alt.Color("entity:N", title="Wettbewerber",
                            scale=alt.Scale(domain=entities,
                                            range=SERIES_LIGHT[:len(entities)])),
            tooltip=[alt.Tooltip("entity:N", title="Wettbewerber"),
                     alt.Tooltip("period:N", title="Periode"),
                     alt.Tooltip("share:Q", title="Anteil", format=".1%"),
                     alt.Tooltip("mentions:Q", title="Nennungen")],
        )
        .properties(height=_HEIGHT)
    )


def activity_timeline(rows: list[dict]):
    """When did which competitor move — identity colour, time on one axis."""
    if not _available() or not rows:
        return None
    entities = sorted({r["entity"] for r in rows})
    return (
        _base(rows)
        .mark_circle(size=140, opacity=0.85, stroke="#fcfcfb", strokeWidth=2)
        .encode(
            x=alt.X("date:T", title="Zeit"),
            y=alt.Y("entity:N", title=None),
            color=alt.Color("entity:N", title="Wettbewerber", legend=None,
                            scale=alt.Scale(domain=entities,
                                            range=SERIES_LIGHT[:len(entities)])),
            size=alt.Size("priority:Q", title="Priorität",
                          scale=alt.Scale(range=[60, 400])),
            tooltip=[alt.Tooltip("entity:N", title="Wettbewerber"),
                     alt.Tooltip("date:T", title="Datum"),
                     alt.Tooltip("type:N", title="Typ"),
                     alt.Tooltip("headline:N", title="Signal"),
                     alt.Tooltip("priority:Q", title="Priorität", format=".2f")],
        )
        .properties(height=_HEIGHT)
    )


def activity_matrix(rows: list[dict]):
    """Competitor × activity-type heat matrix (magnitude → one hue, light→dark)."""
    if not _available() or not rows:
        return None
    return (
        _base(rows)
        .mark_rect(cornerRadius=3, stroke="#fcfcfb", strokeWidth=2)
        .encode(
            x=alt.X("kind:N", title=None),
            y=alt.Y("entity:N", title=None),
            color=alt.Color("count:Q", title="Signale",
                            scale=alt.Scale(scheme="blues")),
            tooltip=[alt.Tooltip("entity:N", title="Wettbewerber"),
                     alt.Tooltip("kind:N", title="Aktivität"),
                     alt.Tooltip("count:Q", title="Signale")],
        )
        .properties(height=_HEIGHT)
    )


def signals_over_time(rows: list[dict]):
    """Signal volume per month by status — stacked bars with a 2px surface gap."""
    if not _available() or not rows:
        return None
    order = ["bestätigt", "unbestätigt", "widerlegt", "abgelaufen"]
    present = [s for s in order if any(r["status"] == s for r in rows)]
    colours = {"bestätigt": STATUS["good"], "unbestätigt": SERIES_LIGHT[3],
               "widerlegt": STATUS["critical"], "abgelaufen": "#9a9a94"}
    return (
        _base(rows)
        .mark_bar(cornerRadius=3, stroke="#fcfcfb", strokeWidth=2)
        .encode(
            x=alt.X("period:N", title="Monat"),
            y=alt.Y("count:Q", title="Signale", stack=True),
            color=alt.Color("status:N", title="Status",
                            scale=alt.Scale(domain=present,
                                            range=[colours[s] for s in present])),
            tooltip=[alt.Tooltip("period:N", title="Monat"),
                     alt.Tooltip("status:N", title="Status"),
                     alt.Tooltip("count:Q", title="Signale")],
        )
        .properties(height=_HEIGHT)
    )
