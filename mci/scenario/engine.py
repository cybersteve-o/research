"""E8 engine: driver model + Monte-Carlo + reference class + verdict (spec §6.3–6.6).

Stdlib only (random/statistics) — no numpy dependency, so the module runs and
tests offline. numpy is a drop-in accelerator if the case counts ever grow.

Share model (Handelspfad, spec §6.2): market share ≈ the product of the
fractional path drivers (Distributionsgrad × Listungstiefe × Abverkaufsrate ×
realisiertes Preisniveau). Share delta in percentage points is
`(product_target − product_baseline) × 100`, then adjusted by the modeled
competitor response. Every output carries a band — never a point (spec §6.6.1).
"""

from __future__ import annotations

import math
import random
import statistics
from functools import reduce

from .models import (
    Assumption,
    AssumptionClass,
    CompetitorResponse,
    Distribution,
    ReferenceCase,
    Scenario,
    Simulation,
)

# Verdict thresholds (spec §6.5): a required driver movement well above the
# reference-class best observed makes the case unplausibel.
UNPLAUSIBLE_RATIO = 1.5   # required / best_observed above this -> Strukturbruch
AMBITIOUS_RATIO = 1.0     # at or above best observed -> ambitioniert


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _sample(dist: Distribution, rng: random.Random) -> float:
    if dist.type == "normal":
        return _clamp01(rng.gauss(dist.mean, dist.sd))
    if dist.type == "uniform":
        return _clamp01(rng.uniform(dist.low, dist.high))
    # triangular (default). Degenerate (low==mode==high) yields a point.
    if dist.low == dist.high:
        return _clamp01(dist.mode)
    return _clamp01(rng.triangular(dist.low, dist.high, dist.mode))


def _product(values: list[float]) -> float:
    return reduce(lambda a, b: a * b, values, 1.0)


def _baseline_product(assumptions: list[Assumption]) -> float:
    return _product([a.baseline for a in assumptions])


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def _delta_pp(sampled: list[float], baseline_product: float, comp_adj: float) -> float:
    return (_product(sampled) - baseline_product) * 100.0 + comp_adj


def _reference_check(
    assumptions: list[Assumption], reference_cases: list[ReferenceCase]
) -> tuple[dict, float]:
    """Compare each required driver movement to the reference-class best observed.

    Returns (reference_class dict, worst_ratio). worst_ratio drives the verdict.
    """
    ref_by_driver: dict[str, float] = {}
    for rc in reference_cases:
        ref_by_driver[rc.driver] = max(ref_by_driver.get(rc.driver, 0.0), rc.observed_delta)

    detail: dict[str, dict] = {}
    worst = 0.0
    for a in assumptions:
        required = a.value - a.baseline
        best = ref_by_driver.get(a.driver_node)
        ratio = (required / best) if best and best > 0 else None
        detail[a.driver_node] = {
            "required_delta": round(required, 4),
            "best_observed": best,
            "ratio_vs_best": round(ratio, 2) if ratio is not None else None,
        }
        if ratio is not None:
            worst = max(worst, ratio)
    return {"drivers": detail, "worst_ratio_vs_best": round(worst, 2) if worst else None}, worst


def _sensitivity(
    assumptions: list[Assumption], baseline_product: float, comp_adj: float
) -> list[dict]:
    """Tornado: swing of the outcome when each assumption moves low->high while
    the others sit at their mode (spec §6.6.3)."""
    modes = [a.distribution.mode or a.value for a in assumptions]
    rows: list[dict] = []
    for i, a in enumerate(assumptions):
        lo_vec = list(modes)
        hi_vec = list(modes)
        lo_vec[i] = a.distribution.low or a.value
        hi_vec[i] = a.distribution.high or a.value
        out_lo = _delta_pp(lo_vec, baseline_product, comp_adj)
        out_hi = _delta_pp(hi_vec, baseline_product, comp_adj)
        rows.append({
            "driver": a.driver_node,
            "swing_pp": round(abs(out_hi - out_lo), 3),
            "low_out": round(out_lo, 3),
            "high_out": round(out_hi, 3),
        })
    rows.sort(key=lambda r: r["swing_pp"], reverse=True)
    return rows


def _extrapolation_warnings(reference_class: dict) -> list[str]:
    warns = []
    for driver, d in reference_class.get("drivers", {}).items():
        ratio = d.get("ratio_vs_best")
        if ratio is not None and ratio > AMBITIOUS_RATIO:
            warns.append(
                f"{driver}: erforderliche Bewegung {d['required_delta']} übersteigt "
                f"historischen Bestwert {d['best_observed']} (Faktor {ratio})."
            )
    return warns


def _denominator_warning(assumptions: list[Assumption]) -> str:
    for a in assumptions:
        if "volumen" in a.driver_node.lower() and a.klasse == AssumptionClass.assumed:
            return (
                "Marktvolumen ist eine reine Annahme und dominiert die Unsicherheit "
                "(Nennerwarnung, spec §6.6.6)."
            )
    return ""


def verdict_for(worst_ratio: float, p_target_hit: float) -> str:
    """Rule-based, not an LLM opinion (spec §6.5)."""
    if worst_ratio and worst_ratio > UNPLAUSIBLE_RATIO:
        return "unplausibel ohne Strukturbruch"
    if (worst_ratio and worst_ratio >= AMBITIOUS_RATIO) or p_target_hit < 0.25:
        return "ambitioniert"
    return "plausibel"


def run_simulation(
    scenario: Scenario,
    assumptions: list[Assumption],
    *,
    reference_cases: list[ReferenceCase] | None = None,
    competitor_response: CompetitorResponse | None = None,
    n: int = 10000,
    seed: int | None = None,
    package_label: str = "",
    lever_set: list[str] | None = None,
) -> Simulation:
    reference_cases = reference_cases or []
    competitor_response = competitor_response or CompetitorResponse()
    rng = random.Random(seed)

    baseline_product = _baseline_product(assumptions)
    comp_adj = competitor_response.net_effect_adjustment

    deltas: list[float] = []
    for _ in range(n):
        sampled = [_sample(a.distribution, rng) for a in assumptions]
        deltas.append(_delta_pp(sampled, baseline_product, comp_adj))
    deltas.sort()

    hits = sum(1 for d in deltas if d >= scenario.target_value)
    p_hit = round(hits / n, 4) if n else 0.0
    median = round(statistics.median(deltas), 3)
    band80 = (round(_percentile(deltas, 0.10), 3), round(_percentile(deltas, 0.90), 3))

    ref_class, worst_ratio = _reference_check(assumptions, reference_cases)
    sensitivity = _sensitivity(assumptions, baseline_product, comp_adj)
    critical = [r["driver"] for r in sensitivity[:3]]
    breakeven = _breakeven(scenario, assumptions, baseline_product, comp_adj, sensitivity)

    verdict = verdict_for(worst_ratio, p_hit)
    incomplete = not competitor_response.modeled  # spec §6.3

    return Simulation(
        scenario_id=scenario.id,
        package_label=package_label,
        lever_set=lever_set or [],
        p_target_hit=p_hit,
        outcome_median=median,
        outcome_band_80=band80,
        sensitivity=sensitivity,
        competitor_response=competitor_response,
        reference_class=ref_class,
        critical_assumptions=critical,
        breakeven=breakeven,
        extrapolation_warnings=_extrapolation_warnings(ref_class),
        denominator_warning=_denominator_warning(assumptions),
        verdict=verdict,
        incomplete=incomplete,
    )


def _breakeven(
    scenario: Scenario,
    assumptions: list[Assumption],
    baseline_product: float,
    comp_adj: float,
    sensitivity: list[dict],
) -> dict:
    """Breakeven-Rückrechnung (spec §6.6.4): for the most sensitive driver, at
    which value does the (deterministic, others-at-mode) outcome meet target?"""
    if not sensitivity:
        return {}
    driver = sensitivity[0]["driver"]
    idx = next((i for i, a in enumerate(assumptions) if a.driver_node == driver), None)
    if idx is None:
        return {}
    modes = [a.distribution.mode or a.value for a in assumptions]

    def outcome(x: float) -> float:
        vec = list(modes)
        vec[idx] = x
        return _delta_pp(vec, baseline_product, comp_adj)

    lo, hi = 0.0, 1.0
    o_lo, o_hi = outcome(lo), outcome(hi)
    target = scenario.target_value
    if (o_lo - target) * (o_hi - target) > 0:
        return {"driver": driver, "breakeven_value": None,
                "note": "Ziel im Wertebereich [0,1] nicht erreichbar"}
    # bisection
    for _ in range(40):
        mid = (lo + hi) / 2
        if (outcome(lo) - target) * (outcome(mid) - target) <= 0:
            hi = mid
        else:
            lo = mid
    return {"driver": driver, "breakeven_value": round((lo + hi) / 2, 4)}


def build_packages(
    scenario: Scenario,
    packages: list[dict],
    *,
    reference_cases: list[ReferenceCase] | None = None,
    seed: int | None = 42,
) -> list[Simulation]:
    """Run a simulation per candidate package (spec §6.5).

    Each package dict: {"label": str, "assumptions": [Assumption],
                        "lever_set": [str], "competitor_response": CompetitorResponse}.
    """
    sims: list[Simulation] = []
    for pkg in packages:
        sims.append(
            run_simulation(
                scenario,
                pkg["assumptions"],
                reference_cases=reference_cases,
                competitor_response=pkg.get("competitor_response"),
                seed=seed,
                package_label=pkg.get("label", ""),
                lever_set=pkg.get("lever_set", []),
            )
        )
    return sims
