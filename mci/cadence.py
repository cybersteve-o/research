"""Launch-Kadenz-Modell (spec §2.2, §4).

Mittlerer Abstand + Streuung je Kategorie → prognostiziertes nächstes
Launch-Fenster mit Konfidenzintervall. Der stärkste Prognosehebel der Branche.

Honest about small samples: with fewer than two intervals (three launches) no
prediction is made — the tool says `insufficient`, never a fabricated date.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .db import Store
from .models import Product, SignalType


@dataclass
class CadencePrediction:
    entity: str
    category: str
    n_launches: int
    mean_interval_days: float | None = None
    stdev_days: float | None = None
    last_launch: datetime | None = None
    next_window: tuple[datetime, datetime] | None = None
    confidence: float = 0.0
    status: str = "insufficient"  # ok | insufficient
    dates: list[datetime] = field(default_factory=list)


def _intervals(dates: list[datetime]) -> list[float]:
    dates = sorted(dates)
    return [
        (dates[i + 1] - dates[i]).total_seconds() / 86400.0
        for i in range(len(dates) - 1)
    ]


def predict_from_dates(entity: str, category: str, dates: list[datetime]) -> CadencePrediction:
    dates = sorted(d for d in dates if d is not None)
    if len(dates) < 3:
        return CadencePrediction(
            entity=entity, category=category, n_launches=len(dates),
            last_launch=dates[-1] if dates else None, dates=dates,
            status="insufficient",
        )
    ivals = _intervals(dates)
    mean = statistics.mean(ivals)
    stdev = statistics.pstdev(ivals) if len(ivals) > 1 else 0.0
    last = dates[-1]
    # Prediction band: mean ± 1 stdev around the last launch.
    lo = last + timedelta(days=max(0.0, mean - stdev))
    hi = last + timedelta(days=mean + stdev)

    # Confidence: more launches + lower relative dispersion -> higher confidence.
    cv = (stdev / mean) if mean else 1.0
    n_factor = min(1.0, (len(dates) - 2) / 4.0)  # saturates around 6 launches
    confidence = round(max(0.0, min(1.0, (1.0 - min(cv, 1.0)) * n_factor)), 4)

    return CadencePrediction(
        entity=entity, category=category, n_launches=len(dates),
        mean_interval_days=round(mean, 1), stdev_days=round(stdev, 1),
        last_launch=last, next_window=(lo, hi), confidence=confidence,
        status="ok", dates=dates,
    )


def _launch_dates_for(store: Store, competitor_id: str, category: str) -> list[datetime]:
    dates: list[datetime] = []
    # Known launched products.
    for p in store.list_products():
        if p.competitor_id == competitor_id and p.launch_date and (
            not category or p.application == category
        ):
            dates.append(p.launch_date)
    # Launch-type signals mentioning the competitor (event time = first_seen proxy).
    from .competitor import signal_mentions

    competitor = next((c for c in store.list_competitors() if c.id == competitor_id), None)
    if competitor:
        for s in store.list_signals():
            if s.type == SignalType.launch and signal_mentions(s, competitor):
                src_date = None
                for eid in s.evidence_ids:
                    ev = store.get_evidence(eid)
                    if ev:
                        src = store.get_source(ev.source_id)
                        if src and src.published_at:
                            src_date = src.published_at
                            break
                dates.append(src_date or s.first_seen)
    return dates


def predict(store: Store, competitor_id: str, category: str = "") -> CadencePrediction:
    competitor = next((c for c in store.list_competitors() if c.id == competitor_id), None)
    name = competitor.name if competitor else competitor_id
    dates = _launch_dates_for(store, competitor_id, category)
    return predict_from_dates(name, category or "all", dates)
