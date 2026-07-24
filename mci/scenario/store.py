"""Persistence for the E8 module (spec §6.7) + Nachhaltemodus (spec §6.6.8).

Layered on the same SQLite DB. Each scenario gets a review date; after it
passes, `record_outcome` compares assumption against actual and stores the
deviation. Over cycles these outcomes become a hauseigene Referenzklasse and a
measure of how systematically the own planning is too optimistic — without this
rückblick the module stays a "Meinungsmaschine mit Nachkommastellen".
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from ..db import Store
from .models import Assumption, Outcome, ReferenceCase, Scenario, Simulation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assumptions (
    id TEXT PRIMARY KEY, scenario_id TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS simulations (
    id TEXT PRIMARY KEY, scenario_id TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reference_cases (
    id TEXT PRIMARY KEY, driver TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes (
    id TEXT PRIMARY KEY, scenario_id TEXT, data TEXT NOT NULL);
"""


class ScenarioStore:
    def __init__(self, store: Store):
        self.store = store
        self.store.conn.executescript(_SCHEMA)
        self.store.conn.commit()

    def _conn(self):
        return self.store.conn

    # -- Scenario -----------------------------------------------------------
    def save_scenario(self, scenario: Scenario) -> Scenario:
        self._conn().execute(
            "INSERT OR REPLACE INTO scenarios(id, data) VALUES (?,?)",
            (scenario.id, scenario.model_dump_json()),
        )
        self._conn().commit()
        return scenario

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        row = self._conn().execute(
            "SELECT data FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
        return Scenario.model_validate_json(row["data"]) if row else None

    def list_scenarios(self) -> list[Scenario]:
        rows = self._conn().execute("SELECT data FROM scenarios").fetchall()
        return [Scenario.model_validate_json(r["data"]) for r in rows]

    # -- Assumptions --------------------------------------------------------
    def save_assumptions(self, assumptions: list[Assumption]) -> None:
        for a in assumptions:
            self._conn().execute(
                "INSERT OR REPLACE INTO assumptions(id, scenario_id, data) VALUES (?,?,?)",
                (a.id, a.scenario_id, a.model_dump_json()),
            )
        self._conn().commit()

    def get_assumptions(self, scenario_id: str) -> list[Assumption]:
        rows = self._conn().execute(
            "SELECT data FROM assumptions WHERE scenario_id = ?", (scenario_id,)
        ).fetchall()
        return [Assumption.model_validate_json(r["data"]) for r in rows]

    # -- Simulations --------------------------------------------------------
    def save_simulation(self, sim: Simulation) -> None:
        self._conn().execute(
            "INSERT OR REPLACE INTO simulations(id, scenario_id, data) VALUES (?,?,?)",
            (sim.id, sim.scenario_id, sim.model_dump_json()),
        )
        self._conn().commit()

    def list_simulations(self, scenario_id: str) -> list[Simulation]:
        rows = self._conn().execute(
            "SELECT data FROM simulations WHERE scenario_id = ?", (scenario_id,)
        ).fetchall()
        return [Simulation.model_validate_json(r["data"]) for r in rows]

    # -- Reference cases ----------------------------------------------------
    def add_reference_case(self, rc: ReferenceCase) -> None:
        self._conn().execute(
            "INSERT OR REPLACE INTO reference_cases(id, driver, data) VALUES (?,?,?)",
            (rc.id, rc.driver, rc.model_dump_json()),
        )
        self._conn().commit()

    def list_reference_cases(self, driver: str | None = None) -> list[ReferenceCase]:
        if driver:
            rows = self._conn().execute(
                "SELECT data FROM reference_cases WHERE driver = ?", (driver,)
            ).fetchall()
        else:
            rows = self._conn().execute("SELECT data FROM reference_cases").fetchall()
        return [ReferenceCase.model_validate_json(r["data"]) for r in rows]

    # -- Nachhaltemodus -----------------------------------------------------
    def record_outcome(
        self, scenario_id: str, actual_value: float, *, learning_note: str = ""
    ) -> Outcome:
        """Compare the predicted median (latest simulation) to the actual result."""
        sims = self.list_simulations(scenario_id)
        predicted = sims[-1].outcome_median if sims else 0.0
        outcome = Outcome(
            scenario_id=scenario_id,
            measured_at=datetime.now(timezone.utc),
            actual_value=actual_value,
            deviation=round(actual_value - predicted, 4),
            learning_note=learning_note,
        )
        self._conn().execute(
            "INSERT OR REPLACE INTO outcomes(id, scenario_id, data) VALUES (?,?,?)",
            (outcome.id, scenario_id, outcome.model_dump_json()),
        )
        self._conn().commit()
        return outcome

    def list_outcomes(self) -> list[Outcome]:
        rows = self._conn().execute("SELECT data FROM outcomes").fetchall()
        return [Outcome.model_validate_json(r["data"]) for r in rows]

    def optimism_bias(self) -> float | None:
        """Mean(actual − predicted) across recorded outcomes.

        Negative -> plans systematically overshoot (too optimistic). This is the
        hauseigene calibration the Nachhaltemodus produces over cycles.
        """
        devs = [o.deviation for o in self.list_outcomes()]
        return round(statistics.mean(devs), 4) if devs else None
