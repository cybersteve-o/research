"""PDF ingestion via pdfplumber (spec §5.2 Dokumentenanreicherung, §7.4).

Returns one RawDocument per page so the page locator can be carried as evidence
("Seitenlokator wird als Evidenz mitgeführt", spec §5.2). Table extraction from
annual reports is left as a Phase-2 enrichment; the raw page text already
supports evidence-backed extraction.
"""

from __future__ import annotations

from pathlib import Path

from . import RawDocument
from ..models import SourceClass


def extract_pdf(
    path: str | Path, *, url: str = "", source_class: SourceClass = SourceClass.A
) -> list[RawDocument]:
    """Extract text page-by-page. Uploaded documents (own reports, studies,
    catalogs, price lists) are treated as class A by default (spec §3.4)."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PDF ingestion needs `pdfplumber` (pip install pdfplumber)"
        ) from exc

    path = Path(path)
    ref = url or path.as_uri()
    docs: list[RawDocument] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            docs.append(
                RawDocument(
                    url=ref,
                    text=text,
                    title=path.stem,
                    publisher=path.name,
                    source_class=source_class,
                    locator=f"p.{i}",
                    channel="pdf",
                    meta={"page": i, "file": str(path)},
                )
            )
    return docs
