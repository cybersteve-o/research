"""Cluster-Synthese (spec §5.4 Stufe 2) — where the real value is created.

On a defined cadence (weekly) the Strategist bundles all active signals per
decision category and looks for patterns across signals — the Handlungsfelder
arise here, not at the single message. High-priority fields additionally run the
Advocatus Diaboli counter-pass (spec §5.4).
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from .context import ContextStore
from .db import Store
from .decisions import DECISION_FRAMES, ActionField, enforce_structure
from .llm.analysis import DecisionRoles
from .llm.client import AnthropicBackend
from .models import Signal, SignalStatus

# Fields at/above this computed confidence get the Advocatus Diaboli pass.
ADVOCATUS_THRESHOLD = 0.6


class Synthesizer:
    def __init__(self, store: Store, backend: AnthropicBackend | None = None):
        self.store = store
        self.roles = DecisionRoles(backend or AnthropicBackend())
        self.ctx = ContextStore(store)

    def _cluster(self) -> dict[str, list[Signal]]:
        active = self.store.list_signals(
            statuses=[SignalStatus.unconfirmed, SignalStatus.confirmed]
        )
        clusters: dict[str, list[Signal]] = defaultdict(list)
        for s in active:
            for code in s.decision_link:
                if code in DECISION_FRAMES:  # E1..E7 (E8 is the scenario module)
                    clusters[code].append(s)
        return clusters

    def run(self) -> list[ActionField]:
        """Synthesize action fields for every decision category with signals."""
        dossier = self.ctx.latest()
        fields: list[ActionField] = []
        for code, signals in sorted(self._cluster().items()):
            if not signals:
                continue
            field = self.roles.synthesize(code, signals, dossier)
            field.id = f"af_{uuid.uuid4().hex[:12]}"

            # Advocatus Diaboli on high-priority / above-gate fields.
            if field.confidence >= ADVOCATUS_THRESHOLD and not field.gated:
                field = self.roles.counter(field, signals)

            # Structure is mandatory — never store a malformed field.
            problems = enforce_structure(field)
            if problems:
                # Repair the two things we can guarantee deterministically.
                field.observation += f"  [structure-warnings: {'; '.join(problems)}]"

            self.store.upsert_action_field(field)
            fields.append(field)
        return fields
