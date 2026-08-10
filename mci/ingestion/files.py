"""Multi-format file ingestion — one entry point for uploaded documents.

"Auch PDF oder andere Dateiformate sollen eingespielt werden können." Uploaded
files travel the exact same evidence path as web/manual input: everything is
normalised to ``list[RawDocument]`` and handed to the pipeline. A price list, a
study, an annual report, a scraped-and-saved article or a plain field note all
end up auditable and source-linked.

Dispatch by extension:
* ``.pdf``                 -> page-wise via ``extract_pdf`` (page locator kept).
* ``.txt .md .markdown``   -> read as-is.
* ``.csv .tsv .log .json`` -> read as-is (raw text supports evidence extraction;
                              structured parsing is a later enrichment).
* ``.html .htm``           -> main text via trafilatura when present, else a
                              dependency-free tag strip.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import RawDocument
from ..models import SourceClass
from .pdf import extract_pdf

_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".text"}
_HTML_SUFFIXES = {".html", ".htm"}
SUPPORTED_SUFFIXES = {".pdf"} | _TEXT_SUFFIXES | _HTML_SUFFIXES

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def _strip_html(raw: str) -> str:
    try:
        import trafilatura  # noqa: PLC0415
        extracted = trafilatura.extract(raw)
        if extracted:
            return extracted.strip()
    except Exception:  # noqa: BLE001  (trafilatura missing or failed -> fallback)
        pass
    text = _TAG_RE.sub(" ", raw)
    return _WS_RE.sub("\n\n", text).strip()


def extract_file(
    path: str | Path,
    *,
    url: str = "",
    source_class: SourceClass | None = None,
) -> list[RawDocument]:
    """Turn a file on disk into RawDocuments, dispatching by extension.

    ``source_class`` defaults per type: PDFs and uploaded documents are treated
    as class A (own reports/studies/catalogs, spec §3.4); loose text/HTML files
    default to class C. Pass an explicit class to override.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Nicht unterstütztes Format '{suffix}'. Erlaubt: "
            f"{', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    if suffix == ".pdf":
        return extract_pdf(path, url=url, source_class=source_class or SourceClass.A)

    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_html(raw) if suffix in _HTML_SUFFIXES else raw.strip()
    if not text:
        return []
    return [RawDocument(
        url=url or path.as_uri(),
        text=text,
        title=path.stem,
        publisher=path.name,
        source_class=source_class or SourceClass.C,
        channel="file",
        meta={"file": str(path), "suffix": suffix},
    )]
