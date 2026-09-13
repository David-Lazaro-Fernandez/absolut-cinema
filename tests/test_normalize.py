"""Normalización de crudos: geografía por cine, hora UTC y las dos formas de crudo (piloto por área / ciudad única y
nacional por estado / `cityId`), porque el archivo se reconstruye desde los crudos viejos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import normalize  # noqa: E402


def _cinepolis_raw(cinemas, city_id=None):
    raw = {"chain": "cinepolis", "cinemas": cinemas, "movies": {"m1": {"id": "m1", "name": "Peli", "genre": ["Drama"], "length": "100"}},
           "billboards": [{"movie_id": "m1", "cinemas": [c["id"] for c in cinemas],
                           "schedules": [{"cinemaId": c["id"], "dates": [{"date": "2026-09-11", "languages": [{"language": "ESP", "showtimes": [
                               {"sessionId": "77", "datetime": "2026-09-11T15:00:00", "screen": 3, "availability": "", "format": {"name": "2D"}}]}]}]}
                                         for c in cinemas]}]}
    if city_id:
        raw["city_id"] = city_id
    return raw


def test_cinepolis_national_raw_has_city_timezone_and_utc():
    raw = _cinepolis_raw([{"id": "cinepolis-carrousel-tijuana", "cityId": "tijuana", "name": "Carrousel", "vistaId": "9", "timezone": "America/Tijuana"}])
    (r,) = normalize.rows("cinepolis", raw)
    assert (r["city_id"], r["state_id"]) == ("tijuana", None)
    assert r["datetime_local"] == "2026-09-11T15:00:00" and r["datetime_utc"] == "2026-09-11T22:00:00+00:00"   # Tijuana en UTC−7 (horario de verano)
    (c,) = normalize.cinemas("cinepolis", raw)
    assert c == {"chain": "cinepolis", "cinema_id": "cinepolis-carrousel-tijuana", "name": "Carrousel", "lat": None, "lng": None,
                 "city_id": "tijuana", "state_id": None, "timezone": "America/Tijuana", "vista_id": "9"}


def test_cinepolis_pilot_raw_uses_capture_city_and_reference_timezone():
    raw = _cinepolis_raw([{"id": "cinepolis-ajusco-cdmx", "name": "Ajusco", "vistaId": 236}], city_id="cdmx")
    (r,) = normalize.rows("cinepolis", raw)
    assert r["city_id"] == "cdmx" and r["datetime_utc"] == "2026-09-11T21:00:00+00:00"                          # CDMX es UTC−6 todo el año


def _cinemex_raw(unit_key, unit):
    session = {"id": 65618606, "datetime": "2026-09-11T13:00:00-07:00", "tz_offset": -25200, "auditorium_number": "10", "availability": "high"}
    cinema = {"id": 300, "name": "Galerías", "lat": 32.5, "lng": -117.0, "state": {"id": 2, "name": "Baja California"}, "area": {"id": 3, "name": "Tijuana"},
              "movies": [{"id": 5, "name": "Peli", "info": {"genre": ["Drama"], "duration": "1h 40m"}, "versions": [{"label": "Español", "type": ["traditional", "lang_es"], "sessions": [session]}]}]}
    unit["days"] = [{"date": "2026-09-11", "data": {"cinemas": [cinema]}}]
    return {"chain": "cinemex", unit_key: [unit]}


def test_cinemex_national_raw_by_state():
    raw = _cinemex_raw("states", {"state_id": 2})
    (r,) = normalize.rows("cinemex", raw)
    assert (r["cinema_id"], r["city_id"], r["state_id"]) == ("300", "3", "2")
    assert r["datetime_local"] == "2026-09-11T13:00:00" and r["datetime_utc"] == "2026-09-11T20:00:00+00:00"    # el offset viene en el propio datetime
    (c,) = normalize.cinemas("cinemex", raw)
    assert (c["city_id"], c["state_id"], c["timezone"], c["vista_id"]) == ("3", "2", None, None)


def test_cinemex_pilot_raw_by_area_reads_the_same():
    assert normalize.rows("cinemex", _cinemex_raw("areas", {"area_id": 3})) == normalize.rows("cinemex", _cinemex_raw("states", {"state_id": 2}))


def test_new_columns_are_not_tracked_by_the_diff():
    assert {"city_id", "state_id", "datetime_utc"} <= set(normalize.COLUMNS)
    assert not {"city_id", "state_id", "datetime_utc"} & set(normalize.TRACKED_FIELDS)
