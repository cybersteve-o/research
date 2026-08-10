"""Pipeline orchestration (spec §7.1).

    Quellen -> Ingestion -> Normalisierung -> Entity Resolution ->
    Signal-Extraktion (strict schema) -> Anreicherung -> Scoring -> Speicher

Phase-1 guarantees enforced here:
  * Evidenzzwang + Auditor-Pass before anything is stored (spec §5.3, §7.3).
  * Triangulation: a matching signal from a *second, independent* source flips
    status to `confirmed` and re-scores (spec §3.5).
  * Dedup: near-duplicate signals are merged, not re-created (spec §7.4).
  * Every number comes from scoring.py — the LLM sets none (spec §9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher

from .config import SETTINGS
from .db import Store
from .ingestion import RawDocument
from .llm.client import AnthropicBackend, CostCapExceeded
from .llm.roles import Roles
from .models import (
    Evidence,
    Signal,
    SignalEntities,
    SignalStatus,
    SignalType,
    SourceClass,
)
from .schema import ExtractionResult, validate_extraction
from .scoring import score

# Near-duplicate threshold for signal merge (spec §7.4: embedding sim > 0.92).
DEDUP_THRESHOLD = 0.90


@dataclass
class IngestResult:
    ok: bool
    action: str  # "created" | "triangulated" | "duplicate" | "rejected" | "aborted"
    signal: Signal | None = None
    violations: list[str] = field(default_factory=list)
    note: str = ""


def _fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class Pipeline:
    def __init__(
        self,
        store: Store,
        *,
        backend: AnthropicBackend | None = None,
        focus_markets: list[str] | None = None,
        focus_lines: list[str] | None = None,
    ):
        self.store = store
        self.backend = backend or AnthropicBackend()
        self.roles = Roles(self.backend)
        self.focus_markets = focus_markets or []
        self.focus_lines = focus_lines or []

    @property
    def model_id(self) -> str:
        return SETTINGS.models.medium if self.backend.available else "offline-heuristic"

    # -- main entry ---------------------------------------------------------
    def ingest(self, raw: RawDocument) -> IngestResult:
        """Run one document through the full pipeline."""
        try:
            return self._ingest(raw)
        except CostCapExceeded as exc:
            return IngestResult(ok=False, action="aborted", note=str(exc))

    def _ingest(self, raw: RawDocument) -> IngestResult:
        # 1. Normalise / register source (content hash = dedup + cache key).
        source = self.store.source_by_hash(raw.hash)
        if source is None:
            source = raw.to_source()
            self.store.upsert_source(source)

        # 2. Extract under strict schema.
        result = self.roles.extract(raw.url, raw.text)
        if result is None:
            return IngestResult(ok=False, action="rejected", note="empty/too-short source")

        # 3. Hard guardrails — reject, never lenient-retry (spec §7.3).
        violations = validate_extraction(result)
        if violations:
            return IngestResult(ok=False, action="rejected", violations=violations)

        # 4. Auditor pass: fact <-> evidence coverage, fact purity (spec §5.3).
        audit = self.roles.audit(result.fact, result.evidence, raw.text)
        if not audit.get("passed", False):
            return IngestResult(
                ok=False,
                action="rejected",
                violations=[f"auditor: {r}" for r in audit.get("reasons", [])],
            )

        # 5. Persist evidence bound to this source.
        evidence_objs = [
            Evidence(
                source_id=source.id,
                quote_short=ev.quote,
                page_or_locator=raw.locator,
            )
            for ev in result.evidence
        ]
        for ev in evidence_objs:
            self.store.add_evidence(ev)

        # 6. Dedup / triangulation against existing signals.
        merged = self._try_triangulate(result, source_id=source.id, evidence=evidence_objs)
        if merged is not None:
            return merged

        # 7. New signal — enrich, score, store.
        signal = self._build_signal(result, raw, source, evidence_objs)
        self.store.upsert_signal(signal)
        return IngestResult(ok=True, action="created", signal=signal)

    # -- helpers ------------------------------------------------------------
    def _independent_source_count(self, evidence_ids: list[str]) -> int:
        seen: set[str] = set()
        for eid in evidence_ids:
            ev = self.store.get_evidence(eid)
            if ev:
                seen.add(ev.source_id)
        return len(seen) or 1

    def _age_days(self, source) -> float:
        ref = source.published_at or source.retrieved_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ref).total_seconds() / 86400.0)

    def _enrich_entities(self, result: ExtractionResult, raw: RawDocument) -> SignalEntities:
        """Relevanzmapping (spec §3.9): map the signal onto focus markets/lines
        that actually appear in the source text."""
        low = raw.text.lower()
        markets = list(result.entities.markets)
        products = list(result.entities.products)
        # Market codes are short (DE, US) — match as whole words to avoid
        # catching "de" inside German words like "Fassade".
        for m in self.focus_markets:
            if re.search(rf"\b{re.escape(m)}\b", raw.text) and m not in markets:
                markets.append(m)
        # Product lines are distinctive brand names — substring match is fine.
        for line in self.focus_lines:
            if line.lower() in low and line not in products:
                products.append(line)
        # Resolve tracked competitors by name or alias. The extractor may miss a
        # company (the offline heuristic has no NER), but the watchlist is known,
        # so match against it — otherwise dossier, cadence, SWOT and sentiment
        # would all stay empty even though the text names the competitor.
        competitors = list(result.entities.competitors)
        for comp in self.store.list_competitors():
            if comp.name in competitors:
                continue
            needles = [comp.name, *(comp.aliases or [])]
            if any(re.search(rf"\b{re.escape(n)}", raw.text, re.IGNORECASE)
                   for n in needles if n):
                competitors.append(comp.name)
        return SignalEntities(
            competitors=competitors,
            products=products,
            markets=markets,
        )

    def _build_signal(
        self,
        result: ExtractionResult,
        raw: RawDocument,
        source,
        evidence_objs: list[Evidence],
    ) -> Signal:
        entities = self._enrich_entities(result, raw)
        evidence_ids = [e.id for e in evidence_objs]
        independent = self._independent_source_count(evidence_ids)
        breakdown = score(
            impact=result.impact,
            source_class=source.source_class,
            independent_sources=independent,
            age_days=self._age_days(source),
            half_life_days=result.half_life_days,
            reaction_window_months=result.reaction_window_months,
            signal_markets=entities.markets,
            signal_products=entities.products,
            focus_markets=self.focus_markets,
            focus_lines=self.focus_lines,
        )
        status = (
            SignalStatus.confirmed if independent >= 2 else SignalStatus.unconfirmed
        )
        trace = (
            f"derivation={result.derivation!r}; hypothesis={result.hypothesis!r}; "
            f"confidence_reasoning={result.confidence_reasoning!r}; "
            f"score={breakdown.as_dict()}"
        )
        return Signal(
            type=SignalType(result.signal_type),
            headline=result.headline,
            fact=result.fact,
            derivation=result.derivation,
            hypothesis=result.hypothesis,
            evidence_ids=evidence_ids,
            entities=entities,
            decision_link=result.decision_link,
            impact=breakdown.impact,
            confidence=breakdown.confidence,
            urgency=breakdown.urgency,
            proximity=breakdown.proximity,
            priority=breakdown.priority,
            half_life_days=result.half_life_days,
            status=status,
            known_unknowns=result.known_unknowns,
            recommended_action=result.recommended_action,
            confidence_reasoning=result.confidence_reasoning,
            prompt_version=SETTINGS.prompt_version,
            model_id=self.model_id,
            reasoning_trace=trace,
            audit_passed=True,
        )

    def _try_triangulate(
        self,
        result: ExtractionResult,
        *,
        source_id: str,
        evidence: list[Evidence],
    ) -> IngestResult | None:
        """If a near-duplicate signal exists, merge into it. A second,
        independent source confirms it (spec §3.5)."""
        fp_new = _fingerprint(f"{result.headline} {result.fact}")
        best: Signal | None = None
        best_ratio = 0.0
        for existing in self.store.list_signals(order_by_priority=False):
            fp = _fingerprint(f"{existing.headline} {existing.fact}")
            ratio = _similarity(fp_new, fp)
            if ratio > best_ratio:
                best_ratio, best = ratio, existing

        if best is None or best_ratio < DEDUP_THRESHOLD:
            return None

        existing_sources = {
            self.store.get_evidence(eid).source_id
            for eid in best.evidence_ids
            if self.store.get_evidence(eid)
        }
        now = datetime.now(timezone.utc)

        if source_id in existing_sources:
            # Same source again — just refresh last_seen (spec: last_seen++).
            best.last_seen = now
            self.store.upsert_signal(best)
            return IngestResult(ok=True, action="duplicate", signal=best)

        # Independent second source -> triangulation.
        best.evidence_ids.extend(e.id for e in evidence)
        best.last_seen = now
        independent = self._independent_source_count(best.evidence_ids)
        source = self.store.get_source(source_id)
        breakdown = score(
            impact=best.impact,
            source_class=source.source_class if source else SourceClass.C,
            independent_sources=independent,
            age_days=self._age_days(source) if source else 0.0,
            half_life_days=best.half_life_days,
            reaction_window_months=None,  # keep existing urgency mapping stable
            signal_markets=best.entities.markets,
            signal_products=best.entities.products,
            focus_markets=self.focus_markets,
            focus_lines=self.focus_lines,
        )
        best.confidence = breakdown.confidence
        best.priority = round(
            best.impact * breakdown.confidence * best.urgency * best.proximity, 4
        )
        best.status = SignalStatus.confirmed if independent >= 2 else best.status
        self.store.upsert_signal(best)
        return IngestResult(ok=True, action="triangulated", signal=best)
