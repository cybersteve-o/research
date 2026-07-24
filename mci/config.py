"""Central configuration.

Reads from environment (optionally a local .env, parsed without extra deps).
Everything here is deterministic and inspectable — no hidden magic numbers
scattered through the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no python-dotenv dependency).

    Only sets keys that are not already present in the environment.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(_REPO_ROOT / ".env")


@dataclass(frozen=True)
class ModelRouting:
    """Model-Routing und Kostenkontrolle (spec §5.7).

    ~70 % of calls go to the small model (triage/dedup), ~25 % to the medium
    model (extraction/search), ~5 % to the strong model (synthesis/audit).
    """

    strong: str = os.environ.get("MCI_MODEL_STRONG", "claude-opus-4-8")
    medium: str = os.environ.get("MCI_MODEL_MEDIUM", "claude-sonnet-5")
    small: str = os.environ.get("MCI_MODEL_SMALL", "claude-haiku-4-5-20251001")


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
    models: ModelRouting = field(default_factory=ModelRouting)

    db_path: Path = Path(os.environ.get("MCI_DB_PATH", str(_REPO_ROOT / "data" / "mci.db")))
    llm_cache_dir: Path = _REPO_ROOT / "llm_cache"

    # Hard per-run cost cap (USD). Abort with partial result over this.
    run_cost_cap_usd: float = float(os.environ.get("MCI_RUN_COST_CAP_USD", "2.00"))

    # Confidence gate for the Strategist (spec §5.4). Not used by the Phase 1
    # pipeline, but the constant lives here so Phase 2 reads one source of truth.
    confidence_gate: float = float(os.environ.get("MCI_CONFIDENCE_GATE", "0.6"))

    # Prompt version stamped onto every signal for reproducibility (spec §5.6).
    prompt_version: str = "p1-2026-07"

    @property
    def llm_available(self) -> bool:
        return bool(self.anthropic_api_key)

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.llm_cache_dir.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
