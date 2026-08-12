"""Konfiguration des Cockpits.

Bewusst klein: alles, was das Verhalten des Werkzeugs steuert, steht entweder
hier oder als benannte Konstante in dem Modul, das sie verwendet. Verstreute
Magic Numbers sind in einem Werkzeug, dessen Zweck Nachvollziehbarkeit ist,
besonders schädlich.

Den API-Schlüssel und das Modell-Routing teilt sich das Cockpit mit dem
MCI-Paket — ein Haus, eine Konfiguration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(
        os.environ.get("GTM_DB_PATH", str(_REPO_ROOT / "data" / "gtm.db"))
    )
    # Pfad zur MCI-Datenbank für die Kopplung an die Recherche-Säule.
    mci_db_path: Path = Path(
        os.environ.get("MCI_DB_PATH", str(_REPO_ROOT / "data" / "mci.db"))
    )

    # Standard-Betrachtungszeitraum in Monaten. Zwölf, weil die Lücke, um die
    # es geht, üblicherweise eine Jahreslücke ist.
    horizon_months: int = int(os.environ.get("GTM_HORIZON_MONTHS", "12"))

    # Voreinstellung der Regler in der Oberfläche.
    default_budget_eur: float = float(os.environ.get("GTM_BUDGET_EUR", "2500000"))
    default_capacity_fte_months: float = float(
        os.environ.get("GTM_CAPACITY_FTE_MONTHS", "200")
    )
    # Wie viele Maßnahmen eine Führungsmannschaft gleichzeitig wirklich steuern
    # kann. Keine technische Grenze, sondern eine organisatorische.
    default_max_measures: int = int(os.environ.get("GTM_MAX_MEASURES", "12"))

    prompt_version: str = "gtm-2026-08"

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def mci_available(self) -> bool:
        return self.mci_db_path.exists()


SETTINGS = Settings()
