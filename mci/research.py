"""Recherche-Assistent — turns the tool's own open questions into a concrete,
gap-driven search plan with ready-to-click deep links (spec §5.5, *lückengetrieben*).

There is deliberately **no live crawler** here. The tool proposes *where to look*;
the human runs the search, opens a real source, and pastes its URL back into the
ingestion box. That keeps the Evidenzzwang intact: every stored fact still traces
to a source a human actually opened, not to a scraped snippet nobody read.

The plan is built from three inputs, so research always follows the value chain
source -> signal -> decision instead of random browsing:

1. **Lücken** — every open ``known_unknown`` already in the store becomes a query
   (this is the spec's gap-driven loop; answering these is the whole point).
2. **Wettbewerber** — for each tracked competitor, the hard early indicators:
   approvals, capacity build-up (jobs / plants), launches.
3. **Märkte** — focus-market demand + market-access questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote_plus

from mci.db import Store
from mci.watchlist import gap_queries

# Search engines / registers we can deep-link into. Each maps a raw query string
# to a ready URL. Registers (DIBt, EUR-Lex) are class-A sources for this domain.
_ENGINES: dict[str, str] = {
    "Google": "https://www.google.com/search?q={q}",
    "News": "https://news.google.com/search?q={q}",
    "LinkedIn Jobs": "https://www.linkedin.com/jobs/search/?keywords={q}",
    "DIBt-Register": "https://www.dibt.de/de/service/zulassungsdownload?tx_solr[q]={q}",
}


@dataclass
class SearchQuery:
    """One concrete research step: a query, why it matters, and where to run it."""

    label: str
    query: str
    rationale: str
    decision_link: list[str] = field(default_factory=list)
    engines: tuple[str, ...] = ("Google", "News")

    @property
    def links(self) -> dict[str, str]:
        """Engine name -> ready-to-open URL for this query."""
        q = quote_plus(self.query)
        return {name: _ENGINES[name].format(q=q) for name in self.engines if name in _ENGINES}


def _competitor_queries(store: Store) -> list[SearchQuery]:
    out: list[SearchQuery] = []
    for c in store.list_competitors():
        out.append(SearchQuery(
            label=f"{c.name} — Zulassungen",
            query=f'"{c.name}" (ETA OR CE OR Zulassung OR approval)',
            rationale="Approvals/Normtests sind der härteste Frühindikator (E2, E6).",
            decision_link=["E2", "E6"],
            engines=("Google", "News", "DIBt-Register"),
        ))
        out.append(SearchQuery(
            label=f"{c.name} — Kapazität",
            query=f'"{c.name}" (new plant OR Werk OR expansion OR investment)',
            rationale="Werk/Invest zeigt Kapazitätsaufbau und Zielregionen (E4).",
            decision_link=["E4"],
        ))
        out.append(SearchQuery(
            label=f"{c.name} — Personal",
            query=f'"{c.name}" (process engineer OR R&D OR product manager)',
            rationale="Stellenanzeigen verraten Kompetenzaufbau und Technologiepfad (E4, E6).",
            decision_link=["E4", "E6"],
            engines=("LinkedIn Jobs", "Google"),
        ))
    return out


def _market_queries(store: Store, focus_markets: list[str], focus_lines: list[str]) -> list[SearchQuery]:
    out: list[SearchQuery] = []
    lines = " OR ".join(focus_lines) if focus_lines else "Abdichtung OR Entkopplung"
    for m in focus_markets:
        out.append(SearchQuery(
            label=f"Markt {m} — Nachfrage",
            query=f"({lines}) construction OR renovation demand {m}",
            rationale="Nachfrage-Momentum + Marktzugang gleichzeitig = Allokationssignal (E4).",
            decision_link=["E4"],
        ))
    return out


def _gap_queries(store: Store) -> list[SearchQuery]:
    out: list[SearchQuery] = []
    for gap in gap_queries(store):
        out.append(SearchQuery(
            label="Offene Wissenslücke",
            query=gap,
            rationale="Direkt aus einer offenen Wissenslücke des Tools abgeleitet (lückengetrieben).",
            decision_link=["E7"],
        ))
    return out


def suggested_queries(
    store: Store,
    *,
    focus_markets: list[str] | None = None,
    focus_lines: list[str] | None = None,
    limit: int = 30,
) -> list[SearchQuery]:
    """Build the gap-driven research plan.

    Order matters: the tool's own open questions come first (closing them is the
    point), then competitor early-indicators, then market questions. Deduplicated
    on the query string so the same search never appears twice.
    """
    plan: list[SearchQuery] = []
    plan.extend(_gap_queries(store))
    plan.extend(_competitor_queries(store))
    plan.extend(_market_queries(store, focus_markets or [], focus_lines or []))

    seen: set[str] = set()
    deduped: list[SearchQuery] = []
    for sq in plan:
        key = sq.query.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sq)
    return deduped[:limit]
