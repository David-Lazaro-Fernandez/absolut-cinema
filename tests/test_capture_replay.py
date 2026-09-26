"""La captura de punta a punta contra respuestas reales grabadas de ambas APIs (`scripts/capture_fixtures.py`), sin red:
`snapshot()` de cada cadena pide lo mismo que pedía, `normalize` extrae las mismas funciones y cines, y `store` las
escribe sin alterarlas. Si una prueba de aquí falla tras un cambio que altera el dato a propósito, se revisa la
diferencia y se regenera el esperado con `python3 scripts/capture_fixtures.py --expected`."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import config, normalize, run, store  # noqa: E402
from scripts import capture_fixtures as fixtures  # noqa: E402

CHAINS = sorted(fixtures.SCOPES)
_SHOW_DIFFS = 8


def _describe(got, expected):
    """Las diferencias entre dos resultados, legibles: funciones de más o de menos y campos cambiados."""
    lines = []
    for part in ("cinemas", "units"):
        if got[part] != expected[part]:
            lines.append(f"{part}: se obtuvo {got[part]!r}\n  se esperaba {expected[part]!r}")
    got_rows = {r["show_id"]: r for r in got["rows"]}
    exp_rows = {r["show_id"]: r for r in expected["rows"]}
    extra, missing = sorted(set(got_rows) - set(exp_rows)), sorted(set(exp_rows) - set(got_rows))
    if extra:
        lines.append(f"{len(extra)} funciones de más, p. ej. {extra[:_SHOW_DIFFS]}")
    if missing:
        lines.append(f"{len(missing)} funciones de menos, p. ej. {missing[:_SHOW_DIFFS]}")
    changed = [(sid, col, exp_rows[sid].get(col), got_rows[sid].get(col))
               for sid in sorted(set(got_rows) & set(exp_rows))
               for col in sorted(set(got_rows[sid]) | set(exp_rows[sid])) if got_rows[sid].get(col) != exp_rows[sid].get(col)]
    if changed:
        cols = sorted({c for _, c, _, _ in changed})
        lines.append(f"{len(changed)} campos cambiados en {cols}:")
        lines += [f"  {sid} {col}: {old!r} -> {new!r}" for sid, col, old, new in changed[:_SHOW_DIFFS]]
    return "\n".join(lines)


@pytest.fixture(scope="module", params=CHAINS)
def captured(request):
    chain = request.param
    raw = fixtures.replay(chain)
    return chain, raw, fixtures.result(chain, raw), fixtures.load(chain, "expected")


def test_the_capture_extracts_the_same_data_from_the_same_responses(captured):
    chain, _, got, expected = captured
    assert got == expected, f"{chain}: la captura cambió el dato extraído\n{_describe(got, expected)}"


def test_the_recorded_data_follows_the_rules(captured):
    chain, _, got, _ = captured
    assert fixtures.problems(chain, got) == []


def test_every_recorded_unit_succeeds(captured):
    # Una petición que la captura ya no hace igual (otra URL, otro cuerpo) no está grabada y tumba su unidad.
    chain, _, got, _ = captured
    assert [u["unit"] for u in got["units"] if not u["ok"]] == [], [u["error"] for u in got["units"] if not u["ok"]]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)      # run.commit registra en run.log: fuera del log real
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(store.SCHEMA)
    yield c
    c.close()


def _as_stored(value):
    # SQLite devuelve según la afinidad de la columna: 3 y "3", o 100 y 100.0, son el mismo dato.
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def test_the_store_keeps_every_show_and_cinema_as_extracted(captured, conn):
    chain, raw, got, _ = captured
    taken_at = fixtures.load(chain, "responses")["recorded_at"]
    assert run.commit(conn, chain, store.begin_snapshot(conn, chain, taken_at), taken_at, raw, 0, save_raw=False)
    _, stored = store.load_current(conn, chain)
    assert set(stored) == {r["show_id"] for r in got["rows"]}
    for r in got["rows"]:
        diffs = {c: (r[c], stored[r["show_id"]][c]) for c in normalize.COLUMNS
                 if _as_stored(r[c]) != _as_stored(stored[r["show_id"]][c])}
        assert not diffs, f"{r['show_id']}: {diffs}"
    cinemas = {row["cinema_id"]: dict(row) for row in conn.execute("SELECT * FROM cinema WHERE chain = ?", (chain,))}
    for c in got["cinemas"]:
        assert {k: _as_stored(v) for k, v in c.items()} == {k: _as_stored(cinemas[c["cinema_id"]][k]) for k in c}


def test_capturing_the_same_responses_again_changes_nothing(captured, conn):
    chain, raw, _, _ = captured
    taken_at = fixtures.load(chain, "responses")["recorded_at"]
    for _ in range(2):
        assert run.commit(conn, chain, store.begin_snapshot(conn, chain, taken_at), taken_at, raw, 0, save_raw=False)
    last = conn.execute("SELECT n_events FROM snapshot WHERE chain = ? ORDER BY id DESC LIMIT 1", (chain,)).fetchone()
    assert last["n_events"] == 0


def test_a_renamed_field_in_the_api_is_caught():
    # Lo que pasó el 2026-09-08: Cinemex renombró `screen_number` a `auditorium_number` sin aviso. Si la API renombra
    # un campo que la captura lee, las reglas lo señalan en vez de guardar funciones sin sala.
    recorded = fixtures.load("cinemex", "responses")
    billboards = [c["response"] for c in recorded["calls"] if isinstance(c["response"], dict)]
    for payload in billboards:
        for c in payload.get("cinemas") or []:
            for m in c.get("movies") or []:
                for v in m.get("versions") or []:
                    for s in v.get("sessions") or []:
                        s["room"] = s.pop("auditorium_number", None)
    got = fixtures.result("cinemex", fixtures.replay("cinemex", recorded))
    assert any(p.startswith("screen vacío") for p in fixtures.problems("cinemex", got))
