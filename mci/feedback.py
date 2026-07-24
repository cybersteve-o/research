"""Lernschleife (spec §5.5).

Every PM verdict (accepted / rejected / edited, with a short reason) is stored.
Accepted derivations become few-shot examples for the prompt library; rejected
ones go into a negative set. Without this loop the hit rate stays constant.

This module only *curates* the sets. Wiring the few-shot examples into live
prompts is a prompt-assembly concern; `few_shot_examples()` returns them ready
to inject.
"""

from __future__ import annotations

from .db import Store

ACCEPTED = "accepted"
REJECTED = "rejected"
EDITED = "edited"
_VALID = {ACCEPTED, REJECTED, EDITED}


def record(
    store: Store,
    *,
    target_type: str,
    target_id: str,
    verdict: str,
    reason: str = "",
    edited_payload: str = "",
) -> None:
    if verdict not in _VALID:
        raise ValueError(f"verdict must be one of {_VALID}, got {verdict!r}")
    store.add_feedback(
        target_type=target_type,
        target_id=target_id,
        verdict=verdict,
        reason=reason,
        edited_payload=edited_payload,
    )


def few_shot_examples(store: Store, target_type: str | None = None) -> list[dict]:
    """Accepted (and edited) items — positive examples for the prompt library."""
    out = []
    for row in store.list_feedback():
        if row["verdict"] in {ACCEPTED, EDITED} and (
            target_type is None or row["target_type"] == target_type
        ):
            out.append(row)
    return out


def negative_set(store: Store, target_type: str | None = None) -> list[dict]:
    return [
        row
        for row in store.list_feedback(verdict=REJECTED)
        if target_type is None or row["target_type"] == target_type
    ]


def acceptance_rate(store: Store, target_type: str | None = None) -> float | None:
    rows = [
        r
        for r in store.list_feedback()
        if target_type is None or r["target_type"] == target_type
    ]
    if not rows:
        return None
    accepted = sum(1 for r in rows if r["verdict"] in {ACCEPTED, EDITED})
    return round(accepted / len(rows), 4)
