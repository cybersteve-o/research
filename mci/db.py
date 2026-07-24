"""SQLite persistence (spec §7.4: SQLite für lokalen Erstlauf).

Pydantic models are stored as JSON blobs, with a few promoted columns on the
signal table for ordering/filtering (priority, status, decision links). This
keeps the schema tiny while the model stays the single source of truth.

Deletion is intentionally absent: the tool archives, never deletes
(spec §5.5 — "Signale löschen (nur archivieren)").
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import (
    Competitor,
    Evidence,
    Market,
    Product,
    Signal,
    SignalStatus,
    Source,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    hash TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(hash);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitors (
    id TEXT PRIMARY KEY,
    name TEXT,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS markets (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    type TEXT,
    status TEXT,
    priority REAL,
    decision_link TEXT,
    first_seen TEXT,
    last_seen TEXT,
    superseded_by TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_priority ON signals(priority DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _dump(model) -> str:
    return model.model_dump_json()


class Store:
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

    # ---- Sources -----------------------------------------------------------
    def upsert_source(self, source: Source) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sources(id, hash, data) VALUES (?,?,?)",
            (source.id, source.hash, _dump(source)),
        )
        self.conn.commit()

    def source_by_hash(self, content_hash: str) -> Source | None:
        row = self.conn.execute(
            "SELECT data FROM sources WHERE hash = ? LIMIT 1", (content_hash,)
        ).fetchone()
        return Source.model_validate_json(row["data"]) if row else None

    def get_source(self, source_id: str) -> Source | None:
        row = self.conn.execute(
            "SELECT data FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        return Source.model_validate_json(row["data"]) if row else None

    # ---- Evidence ----------------------------------------------------------
    def add_evidence(self, evidence: Evidence) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO evidence(id, source_id, data) VALUES (?,?,?)",
            (evidence.id, evidence.source_id, _dump(evidence)),
        )
        self.conn.commit()

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        row = self.conn.execute(
            "SELECT data FROM evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        return Evidence.model_validate_json(row["data"]) if row else None

    # ---- Competitors / Products / Markets ---------------------------------
    def upsert_competitor(self, c: Competitor) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO competitors(id, name, data) VALUES (?,?,?)",
            (c.id, c.name, _dump(c)),
        )
        self.conn.commit()

    def list_competitors(self) -> list[Competitor]:
        rows = self.conn.execute("SELECT data FROM competitors ORDER BY name").fetchall()
        return [Competitor.model_validate_json(r["data"]) for r in rows]

    def upsert_product(self, p: Product) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO products(id, data) VALUES (?,?)", (p.id, _dump(p))
        )
        self.conn.commit()

    def list_products(self) -> list[Product]:
        rows = self.conn.execute("SELECT data FROM products").fetchall()
        return [Product.model_validate_json(r["data"]) for r in rows]

    def upsert_market(self, m: Market) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO markets(id, data) VALUES (?,?)", (m.id, _dump(m))
        )
        self.conn.commit()

    def list_markets(self) -> list[Market]:
        rows = self.conn.execute("SELECT data FROM markets").fetchall()
        return [Market.model_validate_json(r["data"]) for r in rows]

    # ---- Signals -----------------------------------------------------------
    def upsert_signal(self, s: Signal) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO signals
               (id, type, status, priority, decision_link,
                first_seen, last_seen, superseded_by, data)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                s.id,
                s.type.value,
                s.status.value,
                s.priority,
                json.dumps(s.decision_link),
                s.first_seen.isoformat(),
                s.last_seen.isoformat(),
                s.superseded_by,
                _dump(s),
            ),
        )
        self.conn.commit()

    def get_signal(self, signal_id: str) -> Signal | None:
        row = self.conn.execute(
            "SELECT data FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        return Signal.model_validate_json(row["data"]) if row else None

    def list_signals(
        self,
        *,
        statuses: Iterable[SignalStatus] | None = None,
        include_superseded: bool = False,
        order_by_priority: bool = True,
        limit: int | None = None,
    ) -> list[Signal]:
        clauses: list[str] = []
        params: list = []
        if statuses is not None:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(s.value for s in statuses)
        if not include_superseded:
            clauses.append("superseded_by IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ORDER BY priority DESC" if order_by_priority else "ORDER BY last_seen DESC"
        sql = f"SELECT data FROM signals {where} {order}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.conn.execute(sql, params).fetchall()
        return [Signal.model_validate_json(r["data"]) for r in rows]

    def signals_since(self, since: datetime) -> list[Signal]:
        rows = self.conn.execute(
            "SELECT data FROM signals WHERE last_seen >= ? ORDER BY priority DESC",
            (since.isoformat(),),
        ).fetchall()
        return [Signal.model_validate_json(r["data"]) for r in rows]

    # ---- Meta (e.g. last briefing timestamp) ------------------------------
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, value)
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
