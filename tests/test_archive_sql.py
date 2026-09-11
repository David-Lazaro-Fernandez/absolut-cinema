"""Armado de filtros del explorador (archive/sql.py) sin Postgres."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive import sql  # noqa: E402


def test_where_skips_missing_values_and_keeps_order():
    frag, params = sql.where([("chain = %s", "cinemex"), ("name ILIKE %s", None), ("id = ANY(%s)", ["a", "b"]),
                              ("x = %s", ""), ("y = ANY(%s)", [])])
    assert frag == " WHERE chain = %s AND id = ANY(%s)"
    assert params == ["cinemex", ["a", "b"]]


def test_where_empty_and_custom_prefix():
    assert sql.where([("a = %s", None)]) == ("", [])
    frag, params = sql.where([("a = %s", 1)], prefix="AND")
    assert frag == " AND a = %s" and params == [1]


def test_like():
    assert sql.like("  Coyote ") == "%Coyote%"
    assert sql.like("") is None and sql.like(None) is None
