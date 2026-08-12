"""Allokation — welche Maßnahme, in welchem Markt, mit welchem Einsatz.

Das Verfahren ist bewusst ein gieriger Grenznutzen-Algorithmus und kein
Black-Box-Optimierer: das Budget wird in kleinen Scheiben vergeben, jede Scheibe
geht dorthin, wo sie im Betrachtungszeitraum den größten zusätzlichen Euro
bringt. Weil die Wirkung konkav über der Dosis verläuft, ist dieses Vorgehen bei
stetiger Dosis nachweislich nahe am Optimum — und, was hier mehr zählt, es ist
in einem Satz erklärbar und reproduzierbar. Ein Portfolio, das man in der
Sitzung nicht erklären kann, wird nicht beschlossen.

Drei Grenzen hält der Allokator ein, und jede davon verhindert einen typischen
Planungsfehler:

* **Ursachendeckel.** Die Maßnahmen einer Ursache können zusammen nie mehr
  zurückholen, als diese Ursache an Lücke hergibt. Ohne diesen Deckel summieren
  sich Maßnahmenpläne regelmäßig auf ein Vielfaches des Problems.
* **Horizont.** Was im Zeitraum nicht wirkt, bekommt kein Geld aus diesem Topf —
  es landet in `too_slow` und damit in der Diskussion, wo es hingehört: im
  Mehrjahresbudget.
* **Kapazität.** Geld ist selten die bindende Grenze. Wer 40 Maßnahmen
  beschließt und 12 Personen hat, hat nichts beschlossen. Der Allokator meldet,
  welche der beiden Grenzen tatsächlich bindet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bridge import Bridge
from .catalog import MEASURE_CATALOG, applicable
from .effects import (
    DOSE_STEP,
    MIN_DOSE,
    MIN_PAYBACK_RATIO,
    acts_within,
    addressed_gap,
    capacity_for,
    cause_headroom,
    cost_for,
    effect_for,
)
from .fmt import eur as _eur
from .models import (
    EVIDENCE_LABELS,
    INSTRUMENT_LABELS,
    Allocation,
    Band,
    CauseCode,
    EvidenceClass,
    Instrument,
    Measure,
    Portfolio,
)

# Ab diesem Anteil unbelegter Wirkung ist das Portfolio eine Wette.
ASSUMED_WARN_SHARE = 0.40


@dataclass
class _Candidate:
    """Eine Maßnahme in einem Markt, während der Allokation."""

    measure: Measure
    market: str
    addressed_gap: float
    cause_share: dict[CauseCode, float]
    market_factor: float = 1.0
    dose: float = 0.0
    eff_horizon: Band = field(default_factory=Band)
    eff_run_rate: Band = field(default_factory=Band)
    cost: float = 0.0
    capacity: float = 0.0


def _build_candidates(
    bridge: Bridge,
    measures: list[Measure],
    horizon_months: int,
    market_factors: dict[str, float],
) -> tuple[list[_Candidate], list[str]]:
    candidates: list[_Candidate] = []
    too_slow: set[str] = set()
    for market in bridge.markets:
        steps = bridge.steps_for_market(market)
        for measure in measures:
            if not applicable(measure, market):
                continue
            gap, shares = addressed_gap(measure, steps)
            if gap <= 0:
                continue
            if not acts_within(measure, horizon_months):
                too_slow.add(measure.name)
                continue
            candidates.append(_Candidate(
                measure=measure,
                market=market,
                addressed_gap=gap,
                cause_share=shares,
                market_factor=market_factors.get(market, 1.0),
            ))
    return candidates, sorted(too_slow)


def allocate(
    bridge: Bridge,
    measures: list[Measure] | None = None,
    *,
    budget_eur: float,
    capacity_fte_months: float = float("inf"),
    horizon_months: int = 12,
    market_factors: dict[str, float] | None = None,
    max_measures: int | None = None,
) -> Portfolio:
    """Verteilt Budget und Kapazität auf Maßnahmen und Märkte.

    `max_measures` begrenzt die Zahl gleichzeitig laufender Maßnahmen — das
    Aufmerksamkeitsbudget der Führung. Ein Paket mit vierzig Positionen ist kein
    Beschluss, sondern eine Liste; ist die Grenze erreicht, fließt weiteres Geld
    in die Vertiefung laufender Maßnahmen statt in neue.
    """
    measures = measures if measures is not None else MEASURE_CATALOG
    market_factors = market_factors or {}

    candidates, too_slow = _build_candidates(
        bridge, measures, horizon_months, market_factors
    )

    # Ursachendeckel je Markt: so viel Lücke gibt jede Ursache maximal her.
    headroom: dict[tuple[str, CauseCode], float] = {}
    for market in bridge.markets:
        for cause, amount in cause_headroom(bridge.steps_for_market(market)).items():
            headroom[(market, cause)] = amount

    budget_left = float(budget_eur)
    capacity_left = float(capacity_fte_months)

    while True:
        best: tuple[float, _Candidate, dict] | None = None
        slots_left = (
            max_measures - sum(1 for c in candidates if c.dose > 0)
            if max_measures else None
        )

        for cand in candidates:
            if cand.dose >= 1.0:
                continue
            if cand.dose <= 0 and slots_left is not None and slots_left <= 0:
                continue
            # Der Einstieg springt auf die Mindestdosis, danach geht es in
            # kleinen Schritten weiter — eine Maßnahme wird ganz gefahren oder
            # gar nicht angefangen.
            new_dose = MIN_DOSE if cand.dose <= 0 else min(1.0, cand.dose + DOSE_STEP)
            m, f = cand.measure, cand.market_factor
            marg_cost = cost_for(m, new_dose, f) - cost_for(m, cand.dose, f)
            marg_cap = capacity_for(m, new_dose, f) - capacity_for(m, cand.dose, f)
            if marg_cost <= 0 or marg_cost > budget_left or marg_cap > capacity_left:
                continue

            h_new, r_new = effect_for(m, cand.addressed_gap, new_dose, horizon_months)
            h_old, r_old = effect_for(m, cand.addressed_gap, cand.dose, horizon_months)
            marg_run_mode = r_new.mode - r_old.mode
            if marg_run_mode <= 0:
                continue

            # Ursachendeckel: keine Scheibe darf mehr zurückholen, als die
            # Ursache noch hergibt.
            clip = 1.0
            for cause, share in cand.cause_share.items():
                want = marg_run_mode * share
                if want <= 0:
                    continue
                have = max(0.0, headroom.get((cand.market, cause), 0.0))
                clip = min(clip, have / want)
            clip = max(0.0, min(1.0, clip))
            if clip <= 0.0:
                continue

            marg_h = Band(low=(h_new.low - h_old.low) * clip,
                          mode=(h_new.mode - h_old.mode) * clip,
                          high=(h_new.high - h_old.high) * clip)
            marg_r = Band(low=(r_new.low - r_old.low) * clip,
                          mode=marg_run_mode * clip,
                          high=(r_new.high - r_old.high) * clip)
            if marg_h.mode <= 0:
                continue
            # Jede Scheibe muss sich selbst tragen.
            if marg_r.mode < marg_cost * MIN_PAYBACK_RATIO:
                continue

            score = marg_h.mode / marg_cost
            payload = {"dose": new_dose, "cost": marg_cost, "cap": marg_cap,
                       "h": marg_h, "r": marg_r}
            if best is None or score > best[0]:
                best = (score, cand, payload)

        if best is None:
            break

        _, cand, p = best
        cand.dose = p["dose"]
        cand.cost += p["cost"]
        cand.capacity += p["cap"]
        cand.eff_horizon = cand.eff_horizon + p["h"]
        cand.eff_run_rate = cand.eff_run_rate + p["r"]
        budget_left -= p["cost"]
        capacity_left -= p["cap"]
        for cause, share in cand.cause_share.items():
            key = (cand.market, cause)
            headroom[key] = max(0.0, headroom.get(key, 0.0) - p["r"].mode * share)

    chosen = [c for c in candidates if c.dose > 0]
    allocations = [
        Allocation(
            measure_id=c.measure.id,
            measure_name=c.measure.name,
            instrument=c.measure.instrument,
            market=c.market,
            period=bridge.period,
            dose=round(c.dose, 4),
            cost_eur=round(c.cost, 2),
            capacity_fte_months=round(c.capacity, 2),
            effect_horizon=c.eff_horizon,
            effect_run_rate=c.eff_run_rate,
            addresses=list(c.measure.addresses),
            evidence_class=c.measure.evidence_class,
        )
        for c in chosen
    ]
    allocations.sort(key=lambda a: a.effect_horizon.mode, reverse=True)

    chosen_names = {c.measure.name for c in chosen}
    dominated = sorted({c.measure.name for c in candidates} - chosen_names)

    total_h = Band()
    total_r = Band()
    for a in allocations:
        total_h = total_h + a.effect_horizon
        total_r = total_r + a.effect_run_rate

    portfolio = Portfolio(
        period=bridge.period,
        horizon_months=horizon_months,
        budget_eur=budget_eur,
        capacity_fte_months=(
            capacity_fte_months if capacity_fte_months != float("inf") else 0.0
        ),
        allocations=allocations,
        dominated=dominated,
        too_slow=too_slow,
        gap_eur=bridge.gap_eur,
        cost_used_eur=round(sum(a.cost_eur for a in allocations), 2),
        capacity_used=round(sum(a.capacity_fte_months for a in allocations), 2),
        effect_horizon=total_h,
        effect_run_rate=total_r,
    )
    portfolio.warnings = _warnings(
        portfolio, bridge, budget_left, capacity_left,
        _binding_constraint(candidates, budget_left, capacity_left),
    )
    return portfolio


def _binding_constraint(
    candidates: list[_Candidate], budget_left: float, capacity_left: float
) -> str:
    """Welche Grenze den Abbruch verursacht hat: Budget, Kapazität, beide — oder keine.

    Wird nachträglich bestimmt statt während des Laufs mitgeschleppt: es zählt
    nur, was am Ende noch möglich gewesen wäre. „Keine" ist dabei ein
    vollwertiges Ergebnis und die interessanteste Antwort — dann ist nicht das
    Geld knapp, sondern der Katalog leer.
    """
    blocked_by_budget = blocked_by_capacity = False
    for cand in candidates:
        if cand.dose >= 1.0:
            continue
        next_dose = MIN_DOSE if cand.dose <= 0 else min(1.0, cand.dose + DOSE_STEP)
        m, f = cand.measure, cand.market_factor
        need_cost = cost_for(m, next_dose, f) - cost_for(m, cand.dose, f)
        need_cap = capacity_for(m, next_dose, f) - capacity_for(m, cand.dose, f)
        if need_cost <= 0:
            continue
        over_budget = need_cost > budget_left
        over_capacity = need_cap > capacity_left
        blocked_by_budget = blocked_by_budget or (over_budget and not over_capacity)
        blocked_by_capacity = blocked_by_capacity or (over_capacity and not over_budget)
        if over_budget and over_capacity:
            blocked_by_budget = blocked_by_capacity = True

    if blocked_by_budget and blocked_by_capacity:
        return "beide"
    if blocked_by_capacity:
        return "kapazitaet"
    if blocked_by_budget:
        return "budget"
    return "keine"


def _warnings(
    pf: Portfolio,
    bridge: Bridge,
    budget_left: float,
    capacity_left: float,
    binding: str,
) -> list[str]:
    out: list[str] = []

    if pf.effect_horizon.mode > 0:
        assumed = sum(
            a.effect_horizon.mode for a in pf.allocations
            if a.evidence_class is EvidenceClass.assumed
        )
        share = assumed / pf.effect_horizon.mode
        if share >= ASSUMED_WARN_SHARE:
            out.append(
                f"{share:.0%} der erwarteten Wirkung stammt aus Maßnahmen ohne "
                f"gemessene Evidenz. Das Portfolio ist in diesem Umfang eine "
                f"Wette — vor dem Beschluss gehört mindestens ein Test dazu."
            )

    # Welche Grenze bindet wirklich? Die Antwort ändert die Entscheidung: bei
    # Kapazitätsbindung hilft mehr Geld nicht.
    if binding == "kapazitaet":
        out.append(
            f"Bindende Grenze ist die Kapazität, nicht das Budget — "
            f"{_eur(budget_left)} bleiben ungenutzt. Mehr Geld schließt hier "
            f"nichts; mehr Hände schon."
        )
    elif binding == "budget":
        out.append(
            f"Bindende Grenze ist das Budget. {capacity_left:,.1f} "
            f"FTE-Monate bleiben ungenutzt."
        )
    elif binding == "beide":
        out.append(
            f"Budget und Kapazität binden gleichzeitig: {_eur(budget_left)} und "
            f"{capacity_left:,.1f} FTE-Monate sind übrig, reichen aber für keine "
            f"weitere Maßnahme in sinnvoller Dosis."
        )
    else:
        out.append(
            f"Weder Budget noch Kapazität binden — {_eur(budget_left)} bleiben "
            f"ungenutzt, weil keine weitere Maßnahme im Horizont noch etwas "
            f"beiträgt. Nicht das Geld ist knapp, sondern der Maßnahmenkatalog."
        )

    if pf.gap_eur > 0:
        if pf.coverage < 1.0:
            out.append(
                f"Das Portfolio schließt {pf.coverage:.0%} der Lücke. "
                f"{_eur(pf.residual_gap_eur)} bleiben offen und müssen über die "
                f"Planrevision gehen, nicht über weitere Maßnahmen."
            )
        addressable = bridge.addressable_eur
        if addressable > 0 and pf.effect_horizon.mode > addressable:
            out.append(
                "Die erwartete Wirkung übersteigt die adressierbare Lücke — "
                "das deutet auf doppelt gezählte Ursachen hin."
            )

    if pf.too_slow:
        out.append(
            f"{len(pf.too_slow)} Maßnahme(n) wirken erst nach dem Horizont von "
            f"{pf.horizon_months} Monaten: {', '.join(pf.too_slow)}. Sie gehören "
            f"ins Mehrjahresbudget, nicht in dieses Paket."
        )

    if pf.allocations and pf.joint_share < 0.2:
        out.append(
            f"Nur {pf.joint_share:.0%} der Wirkung kommt aus gemeinsam "
            f"getragenen Maßnahmen. Für eine zusammengeführte Einheit ist das "
            f"wenig — das Portfolio ist noch die Summe zweier Abteilungen."
        )
    return out


@dataclass
class FrontierPoint:
    budget_eur: float
    effect_horizon_eur: float
    coverage: float
    n_measures: int
    marginal_return: float = 0.0            # im Horizont, je zusätzlichem Euro
    effect_run_rate_eur: float = 0.0
    marginal_return_run_rate: float = 0.0   # eingeschwungen, je zusätzlichem Euro


def frontier(
    bridge: Bridge,
    measures: list[Measure] | None = None,
    *,
    budgets: list[float],
    capacity_fte_months: float = float("inf"),
    horizon_months: int = 12,
    market_factors: dict[str, float] | None = None,
    max_measures: int | None = None,
) -> list[FrontierPoint]:
    """Effizienzgrenze: was jedes Budgetniveau bringt — und was der nächste Euro noch.

    Der Grenzertrag ist die eigentlich interessante Spalte — und er wird
    zweimal ausgewiesen. Im Horizont sinkt er schnell unter eins, weil
    Aufbaumaßnahmen im ersten Jahr wenig liefern; eingeschwungen liegt er höher.
    Wer nur die erste Spalte liest, hält jede Investition in die Zukunft für
    Verschwendung. Erst wo *beide* unter eins fallen, sollte eine
    Budgetdiskussion enden.
    """
    points: list[FrontierPoint] = []
    prev: FrontierPoint | None = None
    for b in sorted(budgets):
        pf = allocate(
            bridge, measures, budget_eur=b,
            capacity_fte_months=capacity_fte_months,
            horizon_months=horizon_months, market_factors=market_factors,
            max_measures=max_measures,
        )
        pt = FrontierPoint(
            budget_eur=b,
            effect_horizon_eur=pf.effect_horizon.mode,
            effect_run_rate_eur=pf.effect_run_rate.mode,
            coverage=pf.coverage,
            n_measures=len(pf.allocations),
        )
        if prev is not None and b > prev.budget_eur:
            step = b - prev.budget_eur
            pt.marginal_return = (
                pt.effect_horizon_eur - prev.effect_horizon_eur
            ) / step
            pt.marginal_return_run_rate = (
                pt.effect_run_rate_eur - prev.effect_run_rate_eur
            ) / step
        points.append(pt)
        prev = pt
    return points


def summary_lines(pf: Portfolio) -> list[str]:
    """Der Beschlusstext in wenigen Zeilen — für Export und Sitzung."""
    lines = [
        f"Lücke gegen Plan: {_eur(pf.gap_eur)}",
        f"Portfolio: {len(pf.allocations)} Maßnahmen, {_eur(pf.cost_used_eur)} "
        f"von {_eur(pf.budget_eur)} eingesetzt",
        f"Erwartete Wirkung in {pf.horizon_months} Monaten: "
        f"{_eur(pf.effect_horizon.low)} – {_eur(pf.effect_horizon.high)} "
        f"(Erwartungswert {_eur(pf.effect_horizon.mode)})",
        f"Voll eingeschwungen p. a.: {_eur(pf.effect_run_rate.mode)}",
        f"Verbleibende Lücke: {_eur(pf.residual_gap_eur)}",
    ]
    if pf.allocations:
        mix: dict[Instrument, float] = {}
        for a in pf.allocations:
            mix[a.instrument] = mix.get(a.instrument, 0.0) + a.effect_horizon.mode
        total = sum(mix.values()) or 1.0
        parts = ", ".join(
            f"{INSTRUMENT_LABELS[inst]} {value / total:.0%}"
            for inst, value in sorted(mix.items(), key=lambda t: t[1], reverse=True)
        )
        lines.append(f"Wirkungsanteile nach Träger — {parts}")
    return lines


def evidence_mix(pf: Portfolio) -> dict[str, float]:
    """Anteil der Wirkung je Evidenzklasse — für die Ampel in der Oberfläche."""
    total = pf.effect_horizon.mode or 1.0
    out: dict[str, float] = {}
    for a in pf.allocations:
        label = EVIDENCE_LABELS[a.evidence_class]
        out[label] = out.get(label, 0.0) + a.effect_horizon.mode / total
    return out
