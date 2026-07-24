"""Deterministic scoring tests (spec §4, §5.3)."""

import math

from mci.models import SourceClass
from mci.scoring import (
    PROXIMITY_FLOOR,
    compute_confidence,
    compute_proximity,
    priority_pct,
    recency_factor,
    score,
    triangulation_factor,
    urgency_from_window,
)


def test_source_class_ordering():
    # Same triangulation/recency: A > B > C > D.
    kw = dict(independent_sources=2, age_days=0, half_life_days=100)
    a = compute_confidence(SourceClass.A, **kw)
    b = compute_confidence(SourceClass.B, **kw)
    c = compute_confidence(SourceClass.C, **kw)
    d = compute_confidence(SourceClass.D, **kw)
    assert a > b > c > d


def test_triangulation_confirms():
    assert triangulation_factor(1) < triangulation_factor(2) <= triangulation_factor(3)


def test_recency_halves_at_half_life():
    assert math.isclose(recency_factor(100, 100), 0.5, rel_tol=1e-9)
    assert recency_factor(0, 100) == 1.0
    assert recency_factor(1000, 100) < 0.01


def test_urgency_mapping_monotonic():
    assert urgency_from_window(0.5) == 5
    assert urgency_from_window(3) == 4
    assert urgency_from_window(6) == 3
    assert urgency_from_window(12) == 2
    assert urgency_from_window(36) == 1
    assert urgency_from_window(None) == 1


def test_proximity_focus_match_and_floor():
    assert compute_proximity(["DE"], [], ["DE"], []) == 1.0
    assert compute_proximity(["TR"], [], ["DE"], []) == PROXIMITY_FLOOR
    # no focus configured -> neutral
    assert compute_proximity(["TR"], [], [], []) == 0.5


def test_priority_is_product_of_factors():
    b = score(
        impact=4,
        source_class=SourceClass.A,
        independent_sources=2,
        age_days=0,
        half_life_days=100,
        reaction_window_months=2,  # -> urgency 4
        signal_markets=["DE"],
        signal_products=[],
        focus_markets=["DE"],
        focus_lines=[],
    )
    expected = b.impact * b.confidence * b.urgency * b.proximity
    assert math.isclose(b.priority, round(expected, 4), rel_tol=1e-9)
    assert b.urgency == 4
    assert b.proximity == 1.0


def test_priority_pct_bounds():
    assert priority_pct(0) == 0
    assert priority_pct(25) == 100
    assert 0 <= priority_pct(8) <= 100


def test_llm_never_sets_numbers_only_qualitative_inputs():
    # confidence is fully determined by class/triangulation/recency, not passed in
    c1 = compute_confidence(SourceClass.B, independent_sources=1, age_days=10, half_life_days=120)
    c2 = compute_confidence(SourceClass.B, independent_sources=1, age_days=10, half_life_days=120)
    assert c1 == c2  # reproducible
