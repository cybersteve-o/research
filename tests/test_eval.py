"""Gold-set regression thresholds (spec §5.6, §10)."""

from mci.eval import run_eval


def test_gold_set_hard_thresholds():
    r = run_eval()
    # Evidenzdeckung >= 95 % (spec §10.6)
    assert r.evidence_coverage >= 0.95, r.failures
    # No interpretation may leak into the fact field (spec §7.3)
    assert r.interpretation_leak_rate == 0.0, r.failures
    # Guardrail rejections must fire for the reject cases
    assert r.rejection_precision == 1.0, r.failures
    # Every expected signal is produced (offline heuristic must not drop them)
    assert r.extraction_recall == 1.0, r.failures


def test_gold_set_type_and_link_reasonable():
    r = run_eval()
    assert r.signal_type_accuracy >= 0.8, r.failures
    assert r.decision_link_accuracy >= 0.8, r.failures
