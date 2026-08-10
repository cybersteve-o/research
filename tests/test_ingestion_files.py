"""Tests for multi-format file ingestion (mci/ingestion/files.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mci.ingestion import extract_file
from mci.models import SourceClass


def _tmp(name: str, content: str) -> Path:
    p = Path(tempfile.mkdtemp()) / name
    p.write_text(content, encoding="utf-8")
    return p


def test_plain_text_becomes_one_document():
    p = _tmp("note.txt", "Wettbewerber X eröffnet Werk in Vietnam.")
    docs = extract_file(p)
    assert len(docs) == 1
    d = docs[0]
    assert "Vietnam" in d.text
    assert d.channel == "file"
    assert d.source_class == SourceClass.C
    assert d.url.startswith("file://")


def test_markdown_and_csv_supported():
    assert extract_file(_tmp("a.md", "# Titel\nInhalt"))[0].text.startswith("# Titel")
    assert "a;b" in extract_file(_tmp("t.csv", "a;b\n1;2"))[0].text


def test_html_is_stripped_to_text():
    p = _tmp("page.html", "<html><body><h1>Zulassung</h1><p>ETA erteilt</p></body></html>")
    text = extract_file(p)[0].text
    assert "Zulassung" in text and "ETA erteilt" in text
    assert "<" not in text and ">" not in text


def test_explicit_source_class_override():
    p = _tmp("study.txt", "Marktstudie 2026")
    assert extract_file(p, source_class=SourceClass.A)[0].source_class == SourceClass.A


def test_unsupported_extension_raises():
    with pytest.raises(ValueError):
        extract_file(_tmp("data.xyz", "irrelevant"))


def test_empty_file_yields_nothing():
    assert extract_file(_tmp("empty.txt", "   ")) == []
