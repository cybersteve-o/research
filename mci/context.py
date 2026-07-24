"""Kontext-Dossier über eigene Daten (spec §5.3).

Without knowledge of the own portfolio, every impact assessment is generic. The
Analyst and Strategist take this dossier as an abrufbaren Kontext: own product
lines/variants, relative revenue & contribution-margin weights per line and
market, current-year strategic priorities, running dev projects, and past
decisions with their rationale.

The dossier is **versioned** (spec §5.3 "gepflegt, versioniert") — every save
creates a new immutable version, so a signal scored last month can be replayed
against the dossier that was current then.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .db import Store


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProductWeight(BaseModel):
    """Relative economic weight of an own line in a market (0..1 each)."""

    line: str
    market: str
    revenue_weight: float = 0.0  # share of total revenue
    margin_weight: float = 0.0   # relative contribution-margin weight


class StrategicPriority(BaseModel):
    year: int
    text: str
    lines: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)


class DevProject(BaseModel):
    name: str
    line: str = ""
    status: str = "active"  # planned | active | paused | done
    target_market: str = ""
    note: str = ""


class PastDecision(BaseModel):
    question: str
    decision: str
    rationale: str = ""
    decision_category: str = ""  # E1..E8
    date: datetime = Field(default_factory=_now)


class ContextDossier(BaseModel):
    version: int = 0
    updated_at: datetime = Field(default_factory=_now)
    product_weights: list[ProductWeight] = Field(default_factory=list)
    strategic_priorities: list[StrategicPriority] = Field(default_factory=list)
    dev_projects: list[DevProject] = Field(default_factory=list)
    past_decisions: list[PastDecision] = Field(default_factory=list)

    # -- retrieval helpers used by Analyst/Strategist -----------------------
    def revenue_weight_for(self, lines: list[str], markets: list[str] | None = None) -> float:
        """Summed revenue weight of the given lines (optionally market-filtered)."""
        lset = {x.strip().lower() for x in lines if x.strip()}
        mset = {x.strip().lower() for x in (markets or []) if x.strip()}
        total = 0.0
        for w in self.product_weights:
            if w.line.strip().lower() in lset and (
                not mset or w.market.strip().lower() in mset
            ):
                total += w.revenue_weight
        return round(min(total, 1.0), 4)

    def priorities_for(self, lines: list[str], markets: list[str]) -> list[StrategicPriority]:
        lset = {x.lower() for x in lines}
        mset = {x.lower() for x in markets}
        out = []
        for p in self.strategic_priorities:
            if (not p.lines or lset & {x.lower() for x in p.lines}) and (
                not p.markets or mset & {x.lower() for x in p.markets}
            ):
                out.append(p)
        return out

    def as_prompt_context(self) -> str:
        """Compact serialisation injected into Analyst/Strategist prompts."""
        lines = [f"Kontext-Dossier v{self.version} (Stand {self.updated_at:%Y-%m-%d}):"]
        if self.product_weights:
            lines.append("Produktlinien (Umsatz-/Marge-Gewicht je Markt):")
            for w in self.product_weights:
                lines.append(
                    f"  - {w.line} @ {w.market}: rev={w.revenue_weight:.2f} "
                    f"margin={w.margin_weight:.2f}"
                )
        if self.strategic_priorities:
            lines.append("Strategische Prioritäten:")
            for p in self.strategic_priorities:
                lines.append(f"  - [{p.year}] {p.text}")
        if self.dev_projects:
            lines.append("Laufende Entwicklungsprojekte:")
            for d in self.dev_projects:
                lines.append(f"  - {d.name} ({d.line}, {d.status})")
        if self.past_decisions:
            lines.append("Vergangene Entscheidungen:")
            for pd in self.past_decisions[-5:]:
                lines.append(f"  - [{pd.decision_category}] {pd.question} -> {pd.decision}")
        return "\n".join(lines)


_CTX_TABLE = """
CREATE TABLE IF NOT EXISTS context_versions (
    version INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ContextStore:
    """Versioned persistence for the dossier, layered on the same SQLite DB."""

    def __init__(self, store: Store):
        self.store = store
        self.store.conn.executescript(_CTX_TABLE)
        self.store.conn.commit()

    def save(self, dossier: ContextDossier) -> ContextDossier:
        row = self.store.conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM context_versions"
        ).fetchone()
        dossier.version = int(row["v"]) + 1
        dossier.updated_at = _now()
        self.store.conn.execute(
            "INSERT INTO context_versions(version, data, created_at) VALUES (?,?,?)",
            (dossier.version, dossier.model_dump_json(), dossier.updated_at.isoformat()),
        )
        self.store.conn.commit()
        return dossier

    def latest(self) -> ContextDossier | None:
        row = self.store.conn.execute(
            "SELECT data FROM context_versions ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return ContextDossier.model_validate_json(row["data"]) if row else None

    def get_version(self, version: int) -> ContextDossier | None:
        row = self.store.conn.execute(
            "SELECT data FROM context_versions WHERE version = ?", (version,)
        ).fetchone()
        return ContextDossier.model_validate_json(row["data"]) if row else None

    def history(self) -> list[int]:
        rows = self.store.conn.execute(
            "SELECT version FROM context_versions ORDER BY version"
        ).fetchall()
        return [int(r["version"]) for r in rows]
