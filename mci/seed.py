"""Seed entities for the Phase-1 MVP (spec §8: 5 Wettbewerber, 2 Produktlinien,
2 Märkte).

The competitor names here are illustrative placeholders — replace them with
your real watchlist. They carry no facts, only entity stubs (name, country,
aliases) so the pipeline has something to resolve against.
"""

from __future__ import annotations

from .db import Store
from .models import Competitor, Market, OwnerType, Product

# --- 5 competitors (placeholders — replace with your real watchlist) -------
COMPETITORS = [
    Competitor(name="Nordwall Systeme GmbH", country="DE", hq="Köln",
               segments=["Fassade", "Abdichtung"], aliases=["Nordwall", "NWS"]),
    Competitor(name="Altura Building Products", country="US", hq="Chicago",
               segments=["Untergrund", "Entkopplung"], aliases=["Altura", "ABP"]),
    Competitor(name="Marmara Yapı A.Ş.", country="TR", hq="Istanbul",
               segments=["Fliesenverlege", "Abdichtung"], aliases=["Marmara", "MYAS"]),
    Competitor(name="CanardBuild Inc.", country="CA", hq="Toronto",
               segments=["Fassade", "Dämmung"], aliases=["Canard", "CanardBuild"]),
    Competitor(name="Severn Systems Ltd", country="UK", hq="Bristol",
               segments=["Abdichtung", "Bodensysteme"], aliases=["Severn", "SSL"]),
]

# --- 2 own product lines ---------------------------------------------------
OWN_PRODUCTS = [
    Product(owner_type=OwnerType.own, line="AquaGuard",
            application="Verbundabdichtung", markets=["DE", "US"]),
    Product(owner_type=OwnerType.own, line="DecoTrim",
            application="Entkopplung/Untergrund", markets=["DE", "TR"]),
]

# --- 2 focus markets -------------------------------------------------------
MARKETS = [
    Market(country="DE", region="EU", channel_structure="Fachhandel, DIY, Direkt",
           size_estimate="hoch", growth_rate="flach"),
    Market(country="US", region="NA", channel_structure="Distributor, Pro-Dealer",
           size_estimate="sehr hoch", growth_rate="moderat"),
]

FOCUS_MARKETS = ["DE", "US"]
FOCUS_LINES = ["AquaGuard", "DecoTrim"]


def seed(store: Store) -> None:
    for c in COMPETITORS:
        store.upsert_competitor(c)
    for p in OWN_PRODUCTS:
        store.upsert_product(p)
    for m in MARKETS:
        store.upsert_market(m)
