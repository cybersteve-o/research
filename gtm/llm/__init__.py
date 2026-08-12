"""LLM-Rollen des Cockpits — mit deterministischem Offline-Pfad.

Wie im MCI-Paket gilt: die Rollen liefern Sprache, Hypothesen und
Gegenargumente. Zahlen setzen sie nie. Ohne API-Schlüssel läuft alles über die
Offline-Heuristik weiter, die ihre eigenen Grenzen benennt.
"""

from .roles import CauseHypothesis, GtmRoles, PortfolioCritique

__all__ = ["CauseHypothesis", "GtmRoles", "PortfolioCritique"]
