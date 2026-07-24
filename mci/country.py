"""Länder-Steckbrief (spec §4, E4).

Marktvolumen, Wachstum, Baukonjunktur, Kanalstruktur, Regulatorik,
Wettbewerbsdichte — assembled from the Market entity plus market_data and
regulatory signals mapped to the country. Feeds the E4 market decision.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .db import Store
from .models import Signal, SignalType


def _touches_country(signal: Signal, country: str) -> bool:
    if country in signal.entities.markets:
        return True
    return bool(re.search(rf"\b{re.escape(country)}\b", f"{signal.headline} {signal.fact}"))


class CountryProfile(BaseModel):
    country: str
    region: str = ""
    size_estimate: str = ""
    growth_rate: str = ""
    channel_structure: str = ""
    construction_indicators: list[Signal] = Field(default_factory=list)
    regulatory: list[Signal] = Field(default_factory=list)
    competitor_density: int = 0
    competitors: list[str] = Field(default_factory=list)


def build(store: Store, country: str) -> CountryProfile:
    market = next((m for m in store.list_markets() if m.country == country), None)
    signals = store.list_signals()
    construction = [
        s for s in signals
        if s.type == SignalType.market_data and _touches_country(s, country)
    ]
    regulatory = [
        s for s in signals
        if s.type == SignalType.regulatory and _touches_country(s, country)
    ]
    competitors = [c for c in store.list_competitors() if c.country == country]

    return CountryProfile(
        country=country,
        region=market.region if market else "",
        size_estimate=market.size_estimate if market else "",
        growth_rate=market.growth_rate if market else "",
        channel_structure=market.channel_structure if market else "",
        construction_indicators=construction,
        regulatory=regulatory,
        competitor_density=len(competitors),
        competitors=[c.name for c in competitors],
    )
