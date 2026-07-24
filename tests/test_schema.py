"""Guardrail tests (spec §7.3) — the hard rules must bite."""

from mci.schema import EvidenceIn, ExtractionResult, validate_extraction


def _base(**over) -> ExtractionResult:
    data = dict(
        signal_type="regulatory",
        headline="Nordwall erhielt ETA-24/0123",
        fact="Nordwall erhielt am 12. Juni 2024 die ETA-24/0123.",
        evidence=[EvidenceIn(source_url="https://dibt.de/x", quote="ETA-24/0123")],
        decision_link=["E2"],
        impact=3,
        urgency=2,
    )
    data.update(over)
    return ExtractionResult(**data)


def test_valid_extraction_passes():
    assert validate_extraction(_base()) == []


def test_missing_evidence_rejected():
    v = validate_extraction(_base(evidence=[]))
    assert any("no_evidence" in x for x in v)


def test_hedge_in_fact_rejected():
    v = validate_extraction(_base(fact="Nordwall dürfte bald die Preise senken."))
    assert any("hedge" in x for x in v)


def test_english_hedge_in_fact_rejected():
    v = validate_extraction(_base(fact="Nordwall likely lowers prices."))
    assert any("hedge" in x for x in v)


def test_quote_too_long_rejected():
    long_quote = " ".join(f"word{i}" for i in range(20))
    v = validate_extraction(
        _base(evidence=[EvidenceIn(source_url="https://x", quote=long_quote)])
    )
    assert any("words" in x for x in v)


def test_no_decision_link_rejected():
    v = validate_extraction(_base(decision_link=[]))
    assert any("no_decision_link" in x for x in v)


def test_invalid_decision_code_rejected():
    v = validate_extraction(_base(decision_link=["E9"]))
    assert any("invalid_decision_codes" in x for x in v)


def test_impact_out_of_range_rejected():
    v = validate_extraction(_base(impact=9))
    assert any("impact" in x for x in v)


def test_empty_source_url_rejected():
    v = validate_extraction(
        _base(evidence=[EvidenceIn(source_url="  ", quote="ok")])
    )
    assert any("source_url" in x for x in v)


def test_unknown_signal_type_coerced_to_other():
    r = _base(signal_type="totally_made_up")
    assert r.signal_type == "other"
