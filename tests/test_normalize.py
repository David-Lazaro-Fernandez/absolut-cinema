"""Normalización de crudos: geografía por cine, hora UTC y las dos formas de crudo (piloto por área / ciudad única y
nacional por estado / `cityId`), porque el archivo se reconstruye desde los crudos viejos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import normalize, states  # noqa: E402


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
    assert (r["city_id"], r["state_id"], r["state_code"]) == ("tijuana", None, "02")      # Baja California (INEGI)
    assert r["datetime_local"] == "2026-09-11T15:00:00" and r["datetime_utc"] == "2026-09-11T22:00:00+00:00"   # Tijuana en UTC−7 (horario de verano)
    (c,) = normalize.cinemas("cinepolis", raw)
    assert c == {"chain": "cinepolis", "cinema_id": "cinepolis-carrousel-tijuana", "name": "Carrousel", "lat": None, "lng": None,
                 "city_id": "tijuana", "state_id": None, "state_code": "02", "timezone": "America/Tijuana", "vista_id": "9"}


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
    assert (r["cinema_id"], r["city_id"], r["state_id"], r["state_code"]) == ("300", "3", "2", "02")
    assert r["datetime_local"] == "2026-09-11T13:00:00" and r["datetime_utc"] == "2026-09-11T20:00:00+00:00"    # el offset viene en el propio datetime
    (c,) = normalize.cinemas("cinemex", raw)
    assert (c["city_id"], c["state_id"], c["timezone"], c["vista_id"]) == ("3", "2", None, None)


def test_cinemex_pilot_raw_by_area_reads_the_same():
    assert normalize.rows("cinemex", _cinemex_raw("areas", {"area_id": 3})) == normalize.rows("cinemex", _cinemex_raw("states", {"state_id": 2}))


def test_new_columns_are_not_tracked_by_the_diff():
    assert {"city_id", "state_id", "state_code", "datetime_utc"} <= set(normalize.COLUMNS)
    assert not {"city_id", "state_id", "state_code", "datetime_utc"} & set(normalize.TRACKED_FIELDS)


def test_state_code_is_per_cinema_not_per_city():
    # La "ciudad" cdmx de Cinépolis cruza la frontera: Zona Esmeralda está en el Estado de México.
    assert states.state_code("cinepolis", "cinepolis-city-center-zona-esmeralda-cdmx", "cdmx") == "15"
    assert states.state_code("cinepolis", "cinepolis-ajusco-cdmx", "cdmx") == "09"
    assert states.state_code("cinepolis", "cine-que-aun-no-existe", "cdmx") == "09"          # cine nuevo: el de su ciudad
    assert states.state_code("cinepolis", "cine-que-aun-no-existe", "ciudad-nueva") is None


def _cineteca_raw():
    from scraper import cineteca
    return {"chain": "cineteca", "sedes": cineteca.SEDES, "dates": ["2026-09-27"], "days": [{"date": "2026-09-27", "films": [
        {"titulo": "Cars 20 aniversario DOB", "film_id": "HO00009933", "clasificacion": "AA",
         "sedes": [{"codigo_sede": "003", "nombre_sede": "Cineteca México", "horarios": [{"hora": "16:00", "session_id": "50011"}]}]},
        {"titulo": "Deshilando luz", "film_id": "HO00008666", "clasificacion": "B",
         "sedes": [{"codigo_sede": "001", "nombre_sede": "Cineteca Chapultepec", "horarios": [{"hora": "13:30", "session_id": "15061"}]}]}]}]}


def test_cineteca_rows_carry_sede_language_and_cdmx_utc():
    rows = {r["show_id"]: r for r in normalize.rows("cineteca", _cineteca_raw())}
    cars = rows["003:50011"]
    # show_id lleva la sede porque el sessionId de Vista solo es único por cine; el idioma sale del título (DOB = doblada).
    assert (cars["cinema_id"], cars["language"], cars["premium_tier"], cars["format"]) == ("003", "spanish", "traditional", "2D")
    assert cars["state_code"] == "09" and cars["screen"] is None       # CDMX; la sala llega del plano, no de la cartelera
    assert cars["datetime_local"] == "2026-09-27T16:00:00" and cars["datetime_utc"] == "2026-09-27T22:00:00+00:00"   # CDMX es UTC−6
    assert set(cars) == set(normalize.COLUMNS)                          # una fila completa, sin columnas de más ni de menos
    assert rows["001:15061"]["language"] == "other"                    # sin marca de idioma: lengua original de cine de autor


def test_cineteca_cinemas_are_the_three_cdmx_sedes():
    cinemas = normalize.cinemas("cineteca", _cineteca_raw())
    assert [c["cinema_id"] for c in cinemas] == ["001", "002", "003"]
    assert all(c["state_code"] == "09" and c["vista_id"] == c["cinema_id"] and c["timezone"] == "America/Mexico_City" for c in cinemas)
