"""Tests for competitor/market management (get + delete) in the Store."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mci.db import Store
from mci.models import Competitor, Market


def _store() -> Store:
    return Store(Path(tempfile.mkdtemp()) / "manage.db")


def test_competitor_get_update_delete():
    st = _store()
    c = Competitor(name="Acme", country="DE", segments=["Fassade"])
    st.upsert_competitor(c)
    assert st.get_competitor(c.id).name == "Acme"

    # edit keeps the same id
    c2 = Competitor(id=c.id, name="Acme GmbH", country="DE", aliases=["Acme"])
    st.upsert_competitor(c2)
    assert len(st.list_competitors()) == 1
    assert st.get_competitor(c.id).name == "Acme GmbH"
    assert st.get_competitor(c.id).aliases == ["Acme"]

    st.delete_competitor(c.id)
    assert st.get_competitor(c.id) is None
    assert st.list_competitors() == []


def test_market_get_update_delete():
    st = _store()
    m = Market(country="US", region="Nordamerika", size_estimate="groß")
    st.upsert_market(m)
    assert st.get_market(m.id).country == "US"

    m2 = Market(id=m.id, country="US", region="North America", growth_rate="+4%")
    st.upsert_market(m2)
    assert len(st.list_markets()) == 1
    assert st.get_market(m.id).growth_rate == "+4%"

    st.delete_market(m.id)
    assert st.get_market(m.id) is None
    assert st.list_markets() == []


def test_delete_missing_is_noop():
    st = _store()
    st.delete_competitor("does-not-exist")
    st.delete_market("nope")  # must not raise
