# Gold-Set (spec §5.6)

Manually annotated sources with the expected extraction outcome. Used as a
**regression test on every prompt change** and to compute the quality metrics.

- Target size: **50–80 cases** (spec §5.6). `cases.json` ships a representative
  starter set of 8 covering each signal type plus two guardrail-rejection cases;
  grow it as real sources are triaged.
- Each case fixes: expected `signal_type`, a required subset of `decision_link`,
  terms that must appear in `fact`, and — for rejections — the reason substring.

Run the harness:

```bash
python -m mci.eval              # prints the metrics report
pytest tests/test_eval.py       # asserts the hard thresholds hold
```

## Metrics (spec §5.6)

| Metric | Meaning | Hard threshold |
|---|---|---|
| `evidence_coverage` | Signals carrying ≥1 evidence object | **≥ 0.95** (spec §10.6) |
| `interpretation_leak_rate` | Facts containing hedging language | **0.0** |
| `extraction_recall` | Expected signals actually produced | tracked |
| `rejection_precision` | Reject-cases rejected for the right reason | tracked |
| `signal_type_accuracy` | Correct signal type | tracked |
| `decision_link_accuracy` | Expected decision code(s) present | tracked |
| `calibration` | Hit rate per confidence band | tracked (monotonic goal) |

Every signal stores `prompt_version` and `model_id`, so a quality jump is
attributable to a specific prompt/model change (spec §5.6).
