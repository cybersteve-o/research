"""Manual entry — a co-equal channel (spec §7.1).

Field sales, trade-fair visits, customer conversations. The source class must be
chosen by the human entering it (typically C/D for hearsay, higher only with a
document), so it defaults to D and is caller-overridable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import RawDocument
from ..models import SourceClass


def manual_entry(
    text: str,
    *,
    url: str = "manual://entry",
    title: str = "Manuelle Eingabe",
    publisher: str = "internal",
    source_class: SourceClass = SourceClass.D,
    observed_at: datetime | None = None,
) -> RawDocument:
    return RawDocument(
        url=url,
        text=text.strip(),
        title=title,
        publisher=publisher,
        source_class=source_class,
        published_at=observed_at or datetime.now(timezone.utc),
        channel="manual",
    )
