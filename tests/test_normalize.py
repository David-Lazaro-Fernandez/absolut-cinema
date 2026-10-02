"""Normalización de crudos: geografía por cine, hora UTC y las dos formas de crudo (piloto por área / ciudad única y
nacional por estado / `cityId`), porque el archivo se reconstruye desde los crudos viejos."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import date  # noqa: E402

from scraper import (  # noqa: E402
    cabanas,
    cinemania,
    cineteca_gdl,
    cineteca_mty,
    epic,
    lumos,
    normalize,
    papalote_mty,
    raly,
    states,
    tonala,
)


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


def test_veezi_dates_take_the_year_of_their_weekday():
    today = date(2026, 9, 30)
    assert cineteca_gdl.show_date("Wednesday 30, September", today) == "2026-09-30"
    assert cineteca_gdl.show_date("Wednesday 23, December", today) == "2026-12-23"
    assert cineteca_gdl.show_date("Friday 1, January", today) == "2027-01-01"
    assert cineteca_gdl.show_date("miércoles 30, septiembre", today) is None
    assert cineteca_gdl.show_time("3:00 PM") == "15:00" and cineteca_gdl.show_time("12:15 AM") == "00:15"
    assert cineteca_gdl.show_time("03:00 p. m.") is None


def test_a_conarte_day_lists_each_film_with_its_times():
    html = ('<input id="fecha" value="20261001"><ul><li><a class="max_wrap" href="https://conarte.org.mx/cineteca/smaragda/">'
            '<div class="schedule"><p class="schedule_hours">15:45 h. 9:30 h.</p></div>'
            '<div class="title"><h2><strong>FESTIVAL DE CINE EUROPEO: Smaragda</strong></h2></div></a></li></ul>')
    assert cineteca_mty.parse_day(html) == [
        {"slug": "smaragda", "title": "FESTIVAL DE CINE EUROPEO: Smaragda", "times": ["15:45", "09:30"]}]
    assert cineteca_mty.parse_day('<div class="no-events"><h2>No hay películas en esta fecha.</h2></div>') == []


def test_lumos_reads_the_language_from_the_title_or_the_attributes():
    assert lumos.split_title("Digger SUB") == ("Digger", "subtitled")
    assert lumos.split_title("Mary Y Max ESP") == ("Mary Y Max", "spanish")
    assert lumos.split_title("Verity") == ("Verity", None)
    assert lumos.attribute_language(["2D", "Doblada al español"]) == "spanish"
    assert lumos.attribute_language(["2D"]) is None
    assert lumos.is_vip("Sala VIP 3") and not lumos.is_vip("Sala 9")


def test_a_fever_ticket_label_carries_title_and_language():
    assert papalote_mty.label_title("T-Rex | SP Familiar") == "T-Rex"
    assert papalote_mty.label_title("Acceso General Subtitulada") is None
    assert papalote_mty.label_language("Acceso General Subtitulada") == "subtitled"
    assert papalote_mty.label_language("La Gran Barrera de Coral 3D | SP") == "spanish"
    assert papalote_mty.label_language("Acceso General") == "other"


def test_a_tonala_event_page_lists_its_shows():
    data = '0:{"eventDetail":{"name":"DIGGER","url":"cine/digger-2161"},"entertainments":[{"id":8052,"celebrationDate":"2026-10-02 13:30:00"}]}'
    page = '<script>self.__next_f.push([1,' + json.dumps(data) + '])</script>'
    assert tonala.event(page) == {"name": "DIGGER", "entertainments": [{"id": 8052, "celebrationDate": "2026-10-02 13:30:00"}]}
    home = '<script>self.__next_f.push([1,' + json.dumps('{"url":"cine/digger-2161"},{"url":"artes-escenicas/x-1"}') + '])</script>'
    assert tonala.event_urls(home) == ["cine/digger-2161"]


def test_a_cinemania_day_page_dates_its_tab():
    html = ('<a class="cinemania-dia activo" href="?dia=viernes"><span class="cinemania-dia-nombre">VIE.</span>'
            '<span class="cinemania-dia-fecha">02 OCT.</span></a>'
            '<div class="cinemania-horario-card"><h3> DIGGER</h3><div class="cinemania-meta">B15 •Comedia •129 min</div>'
            '<span class="cinemania-hora">14:00</span><span class="cinemania-hora">19:30</span>'
            '<a href="https://www.passline.com/sitio-evento/digger">Comprar</a></div>')
    page = cinemania.parse_day(html)
    assert page.active == "viernes" and page.dates == {"viernes": "02 OCT."}
    film, = page.films
    assert film["title"].strip() == "DIGGER" and film["times"] == ["14:00", "19:30"] and film["slug"] == "digger"
    assert cinemania.meta(film["meta"].strip()) == ("B15", "Comedia", 129)
    assert cinemania.tab_date("02 OCT.", date(2026, 10, 2)) == "2026-10-02"
    assert cinemania.tab_date("01 ENE.", date(2026, 12, 30)) == "2027-01-01"
    assert cinemania.tab_date("32 FOO", date(2026, 10, 2)) is None


def test_raly_reads_its_hand_edited_schedule():
    html = ('<blockquote><p><strong>DOBLADA<br /></strong><strong><span class="h-hora pm">DIGGER<br /></span>'
            '<span class="h-hora pm">3:40 </span><span class="h-hora am">11:00</span></strong></p></blockquote>'
            '<blockquote><p><strong>SUBTITULADA<br />VERITY<br /><span class="h-hora pm">10:20</span></strong></p></blockquote>')
    assert raly.parse(html) == [{"label": "DOBLADA", "title": "DIGGER", "times": [("3:40", "pm"), ("11:00", "am")]},
                                {"label": "SUBTITULADA", "title": "VERITY", "times": [("10:20", "pm")]}]
    assert raly.hour("3:40", "pm") == "15:40" and raly.hour("12:15", "pm") == "12:15" and raly.hour("x", "pm") is None
    # Del viernes al miércoles de la semana de cine; un jueves cubre la semana entera.
    assert raly.dates(date(2026, 10, 2)) == ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"]
    assert len(raly.dates(date(2026, 10, 8))) == 7 and raly.dates(date(2026, 10, 7)) == ["2026-10-07"]


def test_cabanas_reads_dates_hour_and_price_from_its_text():
    today = date(2026, 10, 2)
    assert cabanas.shows("8, 9 Y 10 de octubre, 19 h. Entrada $65", today) == [
        ("2026-10-08", "19:00"), ("2026-10-09", "19:00"), ("2026-10-10", "19:00")]
    assert cabanas.shows("4 de septiembre, 16:30 h. y 2 de octubre, 17:30 h.", today) == [
        ("2026-09-04", "16:30"), ("2026-10-02", "17:30")]
    assert cabanas.shows("15 de enero, 19 h.", date(2026, 12, 20)) == [("2027-01-15", "19:00")]
    assert cabanas.price_cents("Entrada $65") == 6500 and cabanas.price_cents("Entrada gratuita") == 0
    assert cabanas.price_cents("Estreno") is None


def test_epic_keeps_the_spanish_title_and_the_general_ticket():
    assert epic.title("Heart of the Beast / El corazón de la bestia") == "El corazón de la bestia"
    assert epic.title("Digger") == "Digger"
    tickets = [{"Description": "MARTES 2X1", "PriceInCents": 11750}, {"Description": "GENERAL", "PriceInCents": 23500}]
    assert json.loads(epic.fare(tickets))["general_cents"] == 23500
    assert epic.fare([{"Description": "MARTES 2X1", "PriceInCents": 11750}]) is None
