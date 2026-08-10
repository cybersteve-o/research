"""Authoritative source registry & world-market list (spec §3.4, §5.5).

"Märkte weltweit beobachten und aussagekräftige Quellen einbeziehen" needs two
things the tool can hold explicitly:

* a **world-market list** so research is not silently limited to a home market;
* a curated **registry of authoritative sources per region** — the approval /
  standards / patent / statistics bodies that count as class-A/B evidence in this
  domain. The research assistant deep-links into these so a human always starts
  from a reputable source, never a random blog.

This is a static, auditable table on purpose. No live directory lookups — the
same reason the rest of the tool has no hidden magic.
"""

from __future__ import annotations

from dataclasses import dataclass

# Major markets by region (ISO-3166 alpha-2). Not exhaustive — the spread that
# covers most construction-materials / industrial activity worldwide.
WORLD_MARKETS: list[tuple[str, str]] = [
    # Europe
    ("DE", "Deutschland"), ("FR", "Frankreich"), ("UK", "Vereinigtes Königreich"),
    ("IT", "Italien"), ("ES", "Spanien"), ("NL", "Niederlande"),
    ("PL", "Polen"), ("SE", "Schweden"), ("CH", "Schweiz"),
    # Americas
    ("US", "USA"), ("CA", "Kanada"), ("BR", "Brasilien"), ("MX", "Mexiko"),
    # Asia-Pacific
    ("CN", "China"), ("JP", "Japan"), ("IN", "Indien"), ("KR", "Südkorea"),
    ("AU", "Australien"), ("SG", "Singapur"),
    # MEA
    ("TR", "Türkei"), ("AE", "VAE"), ("SA", "Saudi-Arabien"), ("ZA", "Südafrika"),
]

_MARKET_NAMES = dict(WORLD_MARKETS)


def market_name(code: str) -> str:
    return _MARKET_NAMES.get(code.upper(), code)


@dataclass(frozen=True)
class AuthSource:
    """One authoritative source with a ready entry URL and its evidence class."""

    name: str
    url: str
    klass: str  # A amtlich/Norm · B Fachpresse/Verband · C Firmenquelle
    scope: str = ""  # short note on what it covers


# Sources that apply everywhere (patent/standards/scholarly baseline).
GLOBAL_SOURCES: list[AuthSource] = [
    AuthSource("WIPO PATENTSCOPE", "https://patentscope.wipo.int/search/en/search.jsf",
               "A", "Weltweite Patentanmeldungen"),
    AuthSource("Espacenet (EPO)", "https://worldwide.espacenet.com/patent/",
               "A", "Patente weltweit"),
    AuthSource("ISO Standards", "https://www.iso.org/standards.html",
               "A", "Internationale Normen"),
    AuthSource("Google Scholar", "https://scholar.google.com/",
               "B", "Studien / Marktforschung"),
    AuthSource("Google News (weltweit)", "https://news.google.com/",
               "C", "Nachrichten weltweit"),
]

# Region / market specific registries. Keyed by ISO-3166 alpha-2.
AUTHORITATIVE_SOURCES: dict[str, list[AuthSource]] = {
    "DE": [
        AuthSource("DIBt Zulassungen", "https://www.dibt.de/de/service/zulassungsdownload",
                   "A", "Bauzulassungen (ETA/abZ)"),
        AuthSource("DPMA Register", "https://register.dpma.de/", "A", "Patente/Marken DE"),
        AuthSource("Bundesanzeiger", "https://www.bundesanzeiger.de/", "A", "Jahresabschlüsse"),
        AuthSource("Destatis", "https://www.destatis.de/", "A", "Statistik/Bau"),
    ],
    "EU": [
        AuthSource("EUR-Lex", "https://eur-lex.europa.eu/", "A", "EU-Recht/Normen"),
        AuthSource("EOTA (ETA)", "https://www.eota.eu/", "A", "Europ. Techn. Bewertungen"),
        AuthSource("Eurostat", "https://ec.europa.eu/eurostat", "A", "EU-Statistik"),
    ],
    "US": [
        AuthSource("USPTO", "https://ppubs.uspto.gov/pubwebapp/", "A", "Patente US"),
        AuthSource("SEC EDGAR", "https://www.sec.gov/cgi-bin/browse-edgar", "A", "Filings"),
        AuthSource("ICC-ES", "https://icc-es.org/", "A", "Bauprodukt-Bewertungen"),
        AuthSource("US Census – Construction", "https://www.census.gov/construction/",
                   "A", "Bau-/Marktdaten"),
    ],
    "UK": [
        AuthSource("GOV.UK", "https://www.gov.uk/", "A", "Regulatorik"),
        AuthSource("IPO (UK Patents)", "https://www.gov.uk/search-for-patent", "A", "Patente UK"),
        AuthSource("ONS", "https://www.ons.gov.uk/", "A", "Statistik UK"),
    ],
    "FR": [
        AuthSource("INPI", "https://www.inpi.fr/", "A", "Patente/Marken FR"),
        AuthSource("CSTB", "https://www.cstb.fr/", "A", "Bau-Zulassungen FR"),
    ],
    "JP": [
        AuthSource("JPO / J-PlatPat", "https://www.j-platpat.inpit.go.jp/", "A", "Patente JP"),
        AuthSource("e-Stat", "https://www.e-stat.go.jp/en", "A", "Statistik JP"),
    ],
    "CN": [
        AuthSource("CNIPA", "https://english.cnipa.gov.cn/", "A", "Patente CN"),
        AuthSource("National Bureau of Statistics", "http://www.stats.gov.cn/english/",
                   "A", "Statistik CN"),
    ],
    "IN": [
        AuthSource("IP India", "https://ipindia.gov.in/", "A", "Patente IN"),
        AuthSource("BIS", "https://www.bis.gov.in/", "A", "Normen IN"),
    ],
    "BR": [
        AuthSource("INPI Brasil", "https://www.gov.br/inpi/", "A", "Patente BR"),
        AuthSource("ABNT", "https://www.abnt.org.br/", "A", "Normen BR"),
    ],
    "CA": [
        AuthSource("CCMC (NRC)", "https://nrc.canada.ca/en/certifications-evaluations-standards",
                   "A", "Bau-Bewertungen CA"),
        AuthSource("CIPO", "https://www.ic.gc.ca/opic-cipo/", "A", "Patente CA"),
    ],
    "TR": [
        AuthSource("TÜRKPATENT", "https://www.turkpatent.gov.tr/", "A", "Patente TR"),
        AuthSource("TÜİK", "https://www.tuik.gov.tr/", "A", "Statistik TR"),
    ],
}


def authoritative_for(market: str) -> list[AuthSource]:
    """Market-specific sources first, then EU (for European markets), then global.

    Deduplicated on URL so the same register never shows twice.
    """
    code = market.upper()
    european = {"DE", "FR", "UK", "IT", "ES", "NL", "PL", "SE", "CH"}
    out: list[AuthSource] = list(AUTHORITATIVE_SOURCES.get(code, []))
    if code in european:
        out += AUTHORITATIVE_SOURCES.get("EU", [])
    out += GLOBAL_SOURCES

    seen: set[str] = set()
    deduped: list[AuthSource] = []
    for s in out:
        if s.url in seen:
            continue
        seen.add(s.url)
        deduped.append(s)
    return deduped
