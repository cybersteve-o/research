"""Strategiehebel-Katalog (spec §6.4).

Entscheidend sind Wirkzeit und Reversibilität. Every lever carries an
`evidence_basis`; levers without one are flagged as such by the packaging step.
"""

from __future__ import annotations

from .models import Lever

LEVER_CATALOG: list[Lever] = [
    Lever(name="Distribution ausbauen", affects_driver="distributionsgrad",
          time_to_effect_months=18, cost_class="mittel-hoch", reversibility="mittel"),
    Lever(name="Listungstiefe erhöhen", affects_driver="listungstiefe",
          time_to_effect_months=12, cost_class="mittel", reversibility="hoch"),
    Lever(name="Planer-/Spezifikationsarbeit", affects_driver="spec_share",
          time_to_effect_months=27, cost_class="mittel", reversibility="niedrig"),
    Lever(name="Substitutionsschutz", affects_driver="durchsetzungsquote",
          time_to_effect_months=9, cost_class="niedrig-mittel", reversibility="hoch"),
    Lever(name="Verarbeiterbindung", affects_driver="abverkaufsrate",
          time_to_effect_months=18, cost_class="mittel", reversibility="niedrig"),
    Lever(name="Sortimentslücke schließen", affects_driver="marktanteil_direkt",
          time_to_effect_months=21, cost_class="hoch", reversibility="sehr niedrig"),
    Lever(name="Preis/Konditionen", affects_driver="preisniveau",
          time_to_effect_months=3, cost_class="sofort", reversibility="sehr niedrig"),
    Lever(name="Marke/Kommunikation", affects_driver="mehrere",
          time_to_effect_months=24, cost_class="mittel", reversibility="mittel"),
    Lever(name="Regionale Fokussierung", affects_driver="effizienz",
          time_to_effect_months=9, cost_class="niedrig", reversibility="hoch"),
    Lever(name="Zukauf / Partnerschaft", affects_driver="distributionsgrad",
          time_to_effect_months=12, cost_class="sehr hoch", reversibility="sehr niedrig"),
]


def lever_by_driver(driver: str) -> list[Lever]:
    return [lv for lv in LEVER_CATALOG if lv.affects_driver == driver]
