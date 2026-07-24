"""Domain model (spec §7.2).

Every entity is versioned in spirit: signals carry `first_seen`/`last_seen`
and a `superseded_by` link so the tool can show *what changed* (Delta statt
Snapshot, spec §3.1) rather than only a current snapshot.

The strict trennung of Fakt / Ableitung / Hypothese (spec §3.2) is baked into
the `Signal` model: `fact`, `derivation`, and `hypothesis` are separate fields
and are validated separately (see schema.py).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SourceClass(str, enum.Enum):
    """Quellenklassen mit Gewicht (spec §3.4)."""

    A = "A"  # Primärquelle: Geschäftsbericht, Normregister, Patentamt, Herstellerdok.
    B = "B"  # Fachpresse / Verband / Marktstudie
    C = "C"  # Social Media, Foren, Blogs
    D = "D"  # Gerücht / Einzelaussage


class SignalType(str, enum.Enum):
    financial = "financial"
    launch = "launch"
    regulatory = "regulatory"
    patent = "patent"
    hiring = "hiring"
    marketing = "marketing"
    market_data = "market_data"
    channel = "channel"
    customer_feedback = "customer_feedback"
    other = "other"


class SignalStatus(str, enum.Enum):
    unconfirmed = "unconfirmed"
    confirmed = "confirmed"
    expired = "expired"
    refuted = "refuted"


class OwnerType(str, enum.Enum):
    own = "own"
    competitor = "competitor"


# Halbwertszeiten je Signaltyp in Tagen (spec §3.6). Defaults; a signal may
# override its own half_life_days.
DEFAULT_HALF_LIFE_DAYS: dict[SignalType, int] = {
    SignalType.financial: 120,
    SignalType.launch: 180,
    SignalType.regulatory: 730,
    SignalType.patent: 730,
    SignalType.hiring: 120,
    SignalType.marketing: 60,
    SignalType.market_data: 180,
    SignalType.channel: 180,
    SignalType.customer_feedback: 180,
    SignalType.other: 30,  # Schlagzeile 30 Tage
}

# Valid decision codes (spec §1). E8 is the scenario module (spec §6).
DECISION_CODES = {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"}


class Source(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("src"))
    url: str
    title: str = ""
    publisher: str = ""
    source_class: SourceClass = SourceClass.C
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=_now)
    hash: str = ""  # content hash for exact-dup detection / caching
    content_ref: str = ""  # path or key to stored raw content


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ev"))
    source_id: str
    quote_short: str  # max 15 Wörter (enforced in schema.py)
    page_or_locator: str = ""  # PDF page / DOM anchor
    extracted_at: datetime = Field(default_factory=_now)


class Competitor(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("cmp"))
    name: str
    country: str = ""
    hq: str = ""
    segments: list[str] = Field(default_factory=list)
    parent_company: str = ""
    aliases: list[str] = Field(default_factory=list)


class Product(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("prd"))
    owner_type: OwnerType
    competitor_id: str | None = None
    line: str = ""
    variant: str = ""
    application: str = ""
    launch_date: datetime | None = None
    status: str = "active"  # active | discontinued
    markets: list[str] = Field(default_factory=list)


class Market(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("mkt"))
    country: str
    region: str = ""
    channel_structure: str = ""
    size_estimate: str = ""
    growth_rate: str = ""
    source_ref: str = ""


class SignalEntities(BaseModel):
    competitors: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)


class Signal(BaseModel):
    """The atomic Signalkarte (spec §4)."""

    id: str = Field(default_factory=lambda: _new_id("sig"))
    type: SignalType
    headline: str  # max 100 chars, factual
    fact: str  # what is provably in the source — no interpretation
    derivation: str = ""  # what follows — explicitly a conclusion
    hypothesis: str = ""  # optional further guess, marked as such

    evidence_ids: list[str] = Field(default_factory=list)
    entities: SignalEntities = Field(default_factory=SignalEntities)
    decision_link: list[str] = Field(default_factory=list)  # E1..E8

    # Scoring factors (spec §4). Set deterministically by scoring.py from
    # LLM-supplied qualitative inputs — the LLM never sets these numbers.
    impact: int = 1  # 1..5
    confidence: float = 0.0  # 0..1
    urgency: int = 1  # 1..5
    proximity: float = 0.0  # 0..1
    priority: float = 0.0

    half_life_days: int = 30
    status: SignalStatus = SignalStatus.unconfirmed
    first_seen: datetime = Field(default_factory=_now)
    last_seen: datetime = Field(default_factory=_now)
    superseded_by: str | None = None

    known_unknowns: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    confidence_reasoning: str = ""

    # Reproducibility / audit (spec §5.6).
    prompt_version: str = ""
    model_id: str = ""
    reasoning_trace: str = ""
    audit_passed: bool = False


class Derivation(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("der"))
    signal_ids: list[str] = Field(default_factory=list)
    statement: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    author: str = "llm"  # llm | human


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("hyp"))
    competitor_id: str | None = None
    statement: str = ""
    supporting_signal_ids: list[str] = Field(default_factory=list)
    contradicting_signal_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    falsification_trigger: str = ""
    review_date: datetime | None = None
    status: str = "open"  # open | confirmed | refuted
