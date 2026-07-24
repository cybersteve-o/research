"""Eval-Harness gegen das Gold-Set (spec §5.6).

Runs each annotated case through the full pipeline (fresh store per case, so
dedup/triangulation don't interfere) and computes the quality metrics. Without
this, one cannot tell whether the system is useful or just sounds good.

Run:  python -m mci.eval
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .db import Store
from .ingestion import RawDocument
from .models import SourceClass
from .pipeline import Pipeline
from .schema import _HEDGE_RE

_GOLD = Path(__file__).resolve().parent.parent / "gold_set" / "cases.json"

# Confidence bands for calibration.
_BANDS = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]


@dataclass
class EvalReport:
    n_cases: int
    evidence_coverage: float
    interpretation_leak_rate: float
    extraction_recall: float
    rejection_precision: float
    signal_type_accuracy: float
    decision_link_accuracy: float
    calibration: dict[str, dict] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "n_cases": self.n_cases,
            "evidence_coverage": self.evidence_coverage,
            "interpretation_leak_rate": self.interpretation_leak_rate,
            "extraction_recall": self.extraction_recall,
            "rejection_precision": self.rejection_precision,
            "signal_type_accuracy": self.signal_type_accuracy,
            "decision_link_accuracy": self.decision_link_accuracy,
            "calibration": self.calibration,
            "failures": self.failures,
        }


def load_cases(path: Path = _GOLD) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(num: int, den: int) -> float:
    return round(num / den, 4) if den else 1.0


def run_eval(cases: list[dict] | None = None) -> EvalReport:
    cases = cases or load_cases()

    n_signal_expected = 0
    n_signal_produced = 0
    evidence_ok = 0
    leaks = 0
    type_ok = 0
    link_ok = 0
    n_reject_expected = 0
    n_reject_correct = 0
    calib_hits: dict[int, list[bool]] = {i: [] for i in range(len(_BANDS))}
    failures: list[str] = []

    for case in cases:
        # Fresh store per case → deterministic, no cross-case dedup.
        store = Store(":memory:")
        pipe = Pipeline(store, focus_markets=["DE", "US"], focus_lines=["AquaGuard"])
        doc = RawDocument(
            url=case["url"],
            text=case["text"],
            source_class=SourceClass(case.get("source_class", "C")),
        )
        res = pipe.ingest(doc)

        if case["expect"] == "reject":
            n_reject_expected += 1
            reason = case.get("reject_reason_contains", "")
            ok = (not res.ok) and any(reason in v for v in res.violations)
            n_reject_correct += int(ok)
            if not ok:
                failures.append(f"{case['id']}: expected reject~'{reason}', got {res.action}")
            continue

        # expect == "signal"
        n_signal_expected += 1
        if not res.ok or res.signal is None:
            failures.append(f"{case['id']}: expected signal, got {res.action} {res.violations}")
            store.close()
            continue

        sig = res.signal
        n_signal_produced += 1
        evidence_ok += int(bool(sig.evidence_ids))
        leaks += int(bool(_HEDGE_RE.search(sig.fact)))

        type_match = sig.type.value == case.get("expected_signal_type")
        type_ok += int(type_match)

        expected_links = set(case.get("expected_decision_link", []))
        link_match = bool(expected_links & set(sig.decision_link)) if expected_links else True
        link_ok += int(link_match)

        # calibration: treat "correct extraction" as type+link match
        correct = type_match and link_match
        for i, (lo, hi) in enumerate(_BANDS):
            if lo <= sig.confidence < hi:
                calib_hits[i].append(correct)
                break

        if not type_match:
            failures.append(f"{case['id']}: type {sig.type.value} != {case.get('expected_signal_type')}")
        store.close()

    calibration = {
        f"{_BANDS[i][0]:.2f}-{_BANDS[i][1]:.2f}": {
            "n": len(v),
            "hit_rate": round(sum(v) / len(v), 4) if v else None,
        }
        for i, v in calib_hits.items()
    }

    return EvalReport(
        n_cases=len(cases),
        evidence_coverage=_pct(evidence_ok, n_signal_produced),
        interpretation_leak_rate=_pct(leaks, n_signal_produced),
        extraction_recall=_pct(n_signal_produced, n_signal_expected),
        rejection_precision=_pct(n_reject_correct, n_reject_expected),
        signal_type_accuracy=_pct(type_ok, n_signal_produced),
        decision_link_accuracy=_pct(link_ok, n_signal_produced),
        calibration=calibration,
        failures=failures,
    )


def main() -> None:
    report = run_eval()
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
