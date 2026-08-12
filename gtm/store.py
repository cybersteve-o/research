"""SQLite-Persistenz — gleiche Bauart wie `mci.db`.

Pydantic-Modelle werden als JSON-Blob abgelegt, mit wenigen hochgezogenen
Spalten zum Filtern und Sortieren. Das Modell bleibt die einzige Quelle der
Wahrheit, das Schema bleibt klein.

Gelöscht wird auch hier nichts, was eine Entscheidung dokumentiert: ein
beschlossenes Portfolio und ein eingetragenes Ergebnis bleiben stehen. Ein
Werkzeug, aus dem man unbequeme Ergebnisse entfernen kann, hat keine Bilanz.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import (
    BridgeStep,
    MarketProfile,
    Measure,
    MeasureOutcome,
    PlanFigure,
    Portfolio,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_figures (
    id TEXT PRIMARY KEY,
    market TEXT,
    line TEXT,
    period TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_period ON plan_figures(period);

CREATE TABLE IF NOT EXISTS bridge_steps (
    id TEXT PRIMARY KEY,
    market TEXT,
    period TEXT,
    cause TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_steps_period ON bridge_steps(period);

CREATE TABLE IF NOT EXISTS measures (
    id TEXT PRIMARY KEY,
    name TEXT,
    instrument TEXT,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,
    period TEXT,
    created_at TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pf_created ON portfolios(created_at DESC);

CREATE TABLE IF NOT EXISTS outcomes (
    id TEXT PRIMARY KEY,
    measure_id TEXT,
    market TEXT,
    period TEXT,
    status TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_out_status ON outcomes(status);

CREATE TABLE IF NOT EXISTS market_profiles (
    market TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _dump(model) -> str:
    return model.model_dump_json()


class Store:
    """Speicher des Cockpits. Als Kontextmanager verwendbar."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- Planzeilen --------------------------------------------------------
    def upsert_plan_figure(self, figure: PlanFigure) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO plan_figures (id, market, line, period, data) "
            "VALUES (?,?,?,?,?)",
            (figure.id, figure.market, figure.line, figure.period, _dump(figure)),
        )
        self.conn.commit()

    def replace_plan_figures(self, figures: list[PlanFigure], period: str) -> None:
        """Ersetzt den Planstand einer Periode — ein Forecast-Lauf ersetzt den
        vorherigen, statt sich danebenzulegen."""
        self.conn.execute("DELETE FROM plan_figures WHERE period = ?", (period,))
        for f in figures:
            self.conn.execute(
                "INSERT OR REPLACE INTO plan_figures (id, market, line, period, data) "
                "VALUES (?,?,?,?,?)",
                (f.id, f.market, f.line, f.period, _dump(f)),
            )
        self.conn.commit()

    def list_plan_figures(self, period: str | None = None) -> list[PlanFigure]:
        if period:
            rows = self.conn.execute(
                "SELECT data FROM plan_figures WHERE period = ?", (period,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM plan_figures").fetchall()
        return [PlanFigure.model_validate_json(r["data"]) for r in rows]

    # ---- Brückenstufen -----------------------------------------------------
    def upsert_bridge_step(self, step: BridgeStep) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO bridge_steps (id, market, period, cause, data) "
            "VALUES (?,?,?,?,?)",
            (step.id, step.market, step.period,
             step.cause.value if step.cause else "", _dump(step)),
        )
        self.conn.commit()

    def replace_bridge_steps(self, steps: list[BridgeStep], period: str) -> None:
        self.conn.execute("DELETE FROM bridge_steps WHERE period = ?", (period,))
        for s in steps:
            self.conn.execute(
                "INSERT OR REPLACE INTO bridge_steps (id, market, period, cause, data) "
                "VALUES (?,?,?,?,?)",
                (s.id, s.market, s.period, s.cause.value if s.cause else "", _dump(s)),
            )
        self.conn.commit()

    def list_bridge_steps(self, period: str | None = None) -> list[BridgeStep]:
        if period:
            rows = self.conn.execute(
                "SELECT data FROM bridge_steps WHERE period = ?", (period,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM bridge_steps").fetchall()
        return [BridgeStep.model_validate_json(r["data"]) for r in rows]

    # ---- Maßnahmenkatalog --------------------------------------------------
    def upsert_measure(self, measure: Measure) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO measures (id, name, instrument, data) "
            "VALUES (?,?,?,?)",
            (measure.id, measure.name, measure.instrument.value, _dump(measure)),
        )
        self.conn.commit()

    def list_measures(self) -> list[Measure]:
        rows = self.conn.execute("SELECT data FROM measures ORDER BY name").fetchall()
        return [Measure.model_validate_json(r["data"]) for r in rows]

    def delete_measure(self, measure_id: str) -> None:
        self.conn.execute("DELETE FROM measures WHERE id = ?", (measure_id,))
        self.conn.commit()

    # ---- Portfolios --------------------------------------------------------
    def save_portfolio(self, portfolio: Portfolio) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO portfolios (id, period, created_at, data) "
            "VALUES (?,?,?,?)",
            (portfolio.id, portfolio.period,
             portfolio.created_at.isoformat(), _dump(portfolio)),
        )
        self.conn.commit()

    def list_portfolios(self, limit: int = 20) -> list[Portfolio]:
        rows = self.conn.execute(
            "SELECT data FROM portfolios ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Portfolio.model_validate_json(r["data"]) for r in rows]

    def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        row = self.conn.execute(
            "SELECT data FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
        return Portfolio.model_validate_json(row["data"]) if row else None

    # ---- Nachhalten --------------------------------------------------------
    def upsert_outcome(self, outcome: MeasureOutcome) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO outcomes "
            "(id, measure_id, market, period, status, data) VALUES (?,?,?,?,?,?)",
            (outcome.id, outcome.measure_id, outcome.market, outcome.period,
             outcome.status, _dump(outcome)),
        )
        self.conn.commit()

    def list_outcomes(self, status: str | None = None) -> list[MeasureOutcome]:
        if status:
            rows = self.conn.execute(
                "SELECT data FROM outcomes WHERE status = ?", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM outcomes").fetchall()
        return [MeasureOutcome.model_validate_json(r["data"]) for r in rows]

    def get_outcome(self, outcome_id: str) -> MeasureOutcome | None:
        row = self.conn.execute(
            "SELECT data FROM outcomes WHERE id = ?", (outcome_id,)
        ).fetchone()
        return MeasureOutcome.model_validate_json(row["data"]) if row else None

    # ---- Marktprofile ------------------------------------------------------
    def upsert_market_profile(self, profile: MarketProfile) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO market_profiles (market, data) VALUES (?,?)",
            (profile.market, _dump(profile)),
        )
        self.conn.commit()

    def list_market_profiles(self) -> list[MarketProfile]:
        rows = self.conn.execute(
            "SELECT data FROM market_profiles ORDER BY market"
        ).fetchall()
        return [MarketProfile.model_validate_json(r["data"]) for r in rows]

    def market_profiles(self) -> dict[str, MarketProfile]:
        return {p.market: p for p in self.list_market_profiles()}

    # ---- Meta --------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value)
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def is_empty(self) -> bool:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM plan_figures").fetchone()
        return row["n"] == 0

    def stats(self) -> dict:
        def count(table: str) -> int:
            return self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]

        return {
            "Planzeilen": count("plan_figures"),
            "Brückenstufen": count("bridge_steps"),
            "Maßnahmen": count("measures"),
            "Portfolios": count("portfolios"),
            "Nachhalten": count("outcomes"),
            "Marktprofile": count("market_profiles"),
        }


def json_dump(obj) -> str:
    """Kleine Hilfe für Exporte, die kein Pydantic-Modell sind."""
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
