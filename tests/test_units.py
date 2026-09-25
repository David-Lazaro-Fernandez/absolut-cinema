"""Captura por unidades (scraper/units.py): lotes de Cinépolis por estado, fallos aislados con reintento, errores del
sistema que detienen la cadena, escritura incremental de current_showtime y una captura con un estado caído de punta
a punta (sin eventos falsos en SQLite). Todo en memoria, sin red."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import config, diff, normalize, run, store, units  # noqa: E402
from scraper.http import ApiError, Blocked  # noqa: E402

TAKEN_1, TAKEN_2 = "2026-09-25T13:30:00+00:00", "2026-09-25T19:30:00+00:00"


# --- lotes por estado -------------------------------------------------------------------------------------------

def _cinemas(code, n):
    return [{"id": f"c-{code}-{i:02d}", "state_code": code} for i in range(n)]


def test_big_states_split_evenly_and_small_ones_share_a_batch():
    batches = units.pack_by_state(_cinemas("09", 51) + _cinemas("06", 3) + _cinemas("18", 4) + _cinemas("14", 29), size=30)
    assert all(len(b["cinema_ids"]) <= 30 for b in batches)
    by_unit = {b["unit"]: b for b in batches}
    assert len(by_unit["09-1de2"]["cinema_ids"]) == 26 and len(by_unit["09-2de2"]["cinema_ids"]) == 25
    assert "06+14" not in by_unit and any(set(b["state_codes"]) == {"06", "18"} for b in batches)   # Colima + Nayarit
    assert sorted(c for b in batches for c in b["cinema_ids"]) == sorted(c["id"] for c in
                                                                         _cinemas("09", 51) + _cinemas("06", 3) + _cinemas("18", 4) + _cinemas("14", 29))


def test_batches_are_stable_between_captures():
    cinemas = _cinemas("09", 51) + _cinemas("06", 3)
    assert units.pack_by_state(cinemas) == units.pack_by_state(list(reversed(cinemas)))


# --- ejecutor de unidades -----------------------------------------------------------------------------------------

def test_a_failed_unit_does_not_stop_the_others_and_is_retried():
    tries = {}

    def fetch(u, stats):
        stats["calls"] += 1
        tries[u["unit"]] = tries.get(u["unit"], 0) + 1
        if u["unit"] == "b" and tries["b"] == 1:
            raise ApiError("HTTP 502")          # transitorio: pasa en el reintento
        if u["unit"] == "c":
            raise ApiError("HTTP 500 siempre")
        return u["unit"]

    out = units.run_units([{"unit": k} for k in "abc"], fetch, workers=2, retries=1)
    rec = {r["unit"]: (r, d) for r, d in out}
    assert [r["unit"] for r, _ in out] == ["a", "b", "c"]
    assert rec["a"][0]["ok"] and rec["a"][1] == "a" and rec["a"][0]["attempts"] == 1
    assert rec["b"][0]["ok"] and rec["b"][0]["attempts"] == 2 and rec["b"][0]["calls"] == 2
    assert not rec["c"][0]["ok"] and rec["c"][1] is None and "500" in rec["c"][0]["error"] and rec["c"][0]["attempts"] == 2


def test_systemic_errors_stop_the_chain():
    def fetch(u, stats):
        raise Blocked("403 WAF")

    with pytest.raises(Blocked):
        units.run_units([{"unit": k} for k in "ab"], fetch)


def test_all_units_failing_fails_the_chain():
    def fetch(u, stats):
        raise ApiError("caído")

    with pytest.raises(ApiError, match="fallaron las 2 unidades"):
        units.run_units([{"unit": k} for k in "ab"], fetch, retries=0)


# --- escritura incremental ----------------------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)      # run.commit registra en run.log: fuera del log real
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(store.SCHEMA)
    yield c
    c.close()


def _row(show_id, **kw):
    base = {c: None for c in normalize.COLUMNS}
    base.update(chain="cinemex", show_id=show_id, cinema_id="1", movie_id="m", date="2026-09-26",
                datetime_local="2026-09-26T18:00:00", screen="3", duration_min=100, lat=19.4)
    base.update(kw)
    return base


def _table(conn):
    return {r["show_id"]: dict(r) for r in conn.execute("SELECT * FROM current_showtime")}


def test_apply_current_writes_only_the_difference(conn):
    store.apply_current(conn, "cinemex", 1, [_row("a"), _row("b"), _row("c")], {}, TAKEN_1)
    previous = {k: dict(v) for k, v in _table(conn).items()}
    # Mismo valor con otro tipo (3 frente a "3", 100.0 frente a 100) no es cambio; la sala 4 sí.
    rows = [_row("a", screen=3, duration_min=100.0), _row("b", screen="4"), _row("d")]
    written = store.apply_current(conn, "cinemex", 2, rows, previous, TAKEN_2, keep={"c"})
    assert written == {"inserted": 1, "updated": 1, "deleted": 0}
    table = _table(conn)
    assert set(table) == {"a", "b", "c", "d"}                        # c se conserva: su unidad falló
    assert table["a"]["snapshot_id"] == 1 and table["b"]["snapshot_id"] == 2 and table["b"]["screen"] == "4"
    assert table["b"]["first_seen"] == TAKEN_1 and table["d"]["first_seen"] == TAKEN_2
    written = store.apply_current(conn, "cinemex", 3, rows, {k: dict(v) for k, v in _table(conn).items()}, TAKEN_2)
    assert written["deleted"] == 1 and "c" not in _table(conn)       # sin `keep`, c ya no está publicada


# --- una captura con un estado caído, de punta a punta ------------------------------------------------------------

def _cinemex_raw(states, failed=()):
    """Crudo nacional de Cinemex con un cine por estado; los estados de `failed` fallaron y no traen cartelera."""
    raw = {"chain": "cinemex", "state_ids": [int(s) for s in states], "states": [], "units": [], "calls": 1}
    for sid, sessions in states.items():
        unit = {"unit": f"estado-{sid}", "label": f"Estado {sid}", "state_ids": [sid], "ok": sid not in failed,
                "error": None if sid not in failed else "ApiError: HTTP 502", "attempts": 1, "calls": 1, "duration_s": 1.0}
        raw["units"].append(unit)
        if sid in failed:
            continue
        cinema = {"id": int(sid) * 100, "name": f"Cine {sid}", "state": {"id": int(sid)}, "area": {"id": int(sid) * 10},
                  "movies": [{"id": 5, "name": "Peli", "info": {}, "versions": [{"label": "Español", "type": ["traditional"], "sessions": [
                      {"id": sid_ses, "datetime": f"2026-09-26T{hh}:00:00-06:00", "auditorium_number": "1"} for sid_ses, hh in sessions]}]}]}
        raw["states"].append({"state_id": int(sid), "days": [{"date": "2026-09-26", "data": {"cinemas": [cinema]}}]})
        unit["cinema_ids"] = [str(cinema["id"])]
    return raw


def _commit(conn, raw, taken_at):
    sid = store.begin_snapshot(conn, "cinemex", taken_at)
    assert run.commit(conn, "cinemex", sid, taken_at, raw, 1.0, save_raw=False)
    conn.commit()
    return sid


def test_a_failed_state_keeps_its_showtimes_and_makes_no_events(conn):
    _commit(conn, _cinemex_raw({"1": [(11, "18"), (12, "20")], "2": [(21, "18"), (22, "20")]}), TAKEN_1)
    # Segunda captura: el estado 2 falla; en el 1 la función 12 cambia de hora y la 11 se cancela.
    raw = _cinemex_raw({"1": [(12, "21")], "2": []}, failed={"2"})
    snap = _commit(conn, raw, TAKEN_2)
    events = {(r["show_id"], r["kind"]) for r in conn.execute("SELECT show_id, kind FROM event WHERE snapshot_id = ?", (snap,))}
    assert events == {("11", "removed"), ("12", "moved")}              # nada del estado 2
    assert {"21", "22"} <= set(_table(conn))                          # conservadas tal cual
    (unit,) = [dict(r) for r in conn.execute("SELECT * FROM snapshot_unit WHERE snapshot_id = ? AND ok = 0", (snap,))]
    assert unit["unit"] == "estado-2" and unit["carried"] == 2 and unit["n_cinemas"] == 1
    assert conn.execute("SELECT n_units, n_failed_units FROM snapshot WHERE id = ?", (snap,)).fetchone()[:] == (2, 1)
    # El alcance resuelto queda en el crudo: quien reconstruya la historia desde él no cierra esas funciones.
    assert diff.failed_cinemas(raw) == frozenset({"200"})
