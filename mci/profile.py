"""Eigenes Unternehmensprofil & Onboarding.

Out of the box the tool ships placeholder entities (AquaGuard, Nordwall …) so a
demo has something to show. That is exactly wrong for real use: relevance
scoring, portfolio gaps and the research plan all key off *your* lines and
markets. This module holds the own-company profile so a new user can make the
tool theirs in one pass instead of editing seed code.

Stored as JSON in the meta table — no schema migration, and the profile travels
with the database file.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from mci.db import Store

_KEY = "own_profile"


class OwnProfile(BaseModel):
    """Who we are — the frame every relevance judgement is made against."""

    company: str = ""
    product_lines: list[str] = Field(default_factory=list)
    focus_markets: list[str] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    positioning: str = ""
    configured: bool = False  # False while the placeholder seed is still in use

    @property
    def is_complete(self) -> bool:
        return bool(self.company and self.product_lines and self.focus_markets)


def load(store: Store) -> OwnProfile:
    raw = store.get_meta(_KEY)
    if not raw:
        return OwnProfile()
    try:
        return OwnProfile.model_validate_json(raw)
    except (ValueError, json.JSONDecodeError):
        return OwnProfile()


def save(store: Store, profile: OwnProfile) -> OwnProfile:
    profile.configured = profile.is_complete
    store.set_meta(_KEY, profile.model_dump_json())
    return profile


def effective_markets(store: Store, fallback: list[str]) -> list[str]:
    """Configured focus markets, else the seed defaults."""
    prof = load(store)
    return prof.focus_markets or fallback


def effective_lines(store: Store, fallback: list[str]) -> list[str]:
    """Configured product lines, else the seed defaults."""
    prof = load(store)
    return prof.product_lines or fallback
