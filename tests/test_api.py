"""La API pública (`api/main.py`) sobre la captura grabada, abierta como en producción: `snapshots.db` en un archivo
y `analytics.connect()` en solo lectura. Punto de partida: Forum Tepic (Cinemex, con su Platino en el mismo edificio)."""
import re
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
import anyio.to_thread  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import analytics  # noqa: E402
from api import main  # noqa: E402
from scraper import config  # noqa: E402

FORUM_TEPIC = {"lat": 21.493764, "lng": -104.8664}
DAY = "2026-09-26"                                     # un día de la captura grabada, ya pasado: sin recorte `from_now`


@pytest.fixture
def client(capture_db, tmp_path, monkeypatch):
    memory = capture_db("cinemex", "cinepolis")
    path = tmp_path / "snapshots.db"
    with sqlite3.connect(path) as disk:
        memory.backup(disk)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(analytics, "today", lambda: DAY)
    main._cache.clear()
    main._hits.clear()
    return TestClient(main.app)


def test_a_search_returns_only_what_is_near(client):
    res = client.get("/v1/a-donde-ir/funciones", params={**FORUM_TEPIC, "fecha": DAY, "radio": 1})
    assert res.status_code == 200 and res.headers["cache-control"] == "public, max-age=60"
    body = res.json()
    assert set(body) == {"summary", "complete", "snacks_unpriced", "unpriced", "sites", "titles"}
    assert body["unpriced"] and all(r["distance_km"] <= 1 for r in body["unpriced"])
    assert {r["chain"] for r in body["unpriced"]} == {"cinemex"}                     # nada de Hermosillo


def test_a_search_shows_only_what_the_page_needs(client):
    body = client.get("/v1/a-donde-ir/funciones", params={**FORUM_TEPIC, "fecha": DAY, "radio": 1}).json()
    assert set(body["unpriced"][0]) == set(main.Show.__annotations__)
    assert not {"adult_price", "child_price", "senior_price", "cinema_id", "movie_id"} & set(body["unpriced"][0])
    assert set(body["titles"][0]) == {"title_norm", "title"}
    assert "saving" not in body["summary"] and "priciest" not in body["summary"]


def test_the_request_is_validated(client):
    base = {**FORUM_TEPIC, "fecha": DAY}
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "radio": 50}).status_code == 422
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "adultos": 0}).status_code == 422
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "fecha": "2027-01-01"}).status_code == 422
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "dulceria": "nachos"}).status_code == 422
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "combo": "Combo Inventado"}).status_code == 422
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "combo": "Maxicombo Familiar"}).status_code == 200
    assert client.get("/v1/a-donde-ir/funciones", params={**base, "sitio": "abc"}).status_code == 422


def test_only_today_and_tomorrow_can_be_searched(client):
    def status(day):
        return client.get("/v1/a-donde-ir/funciones", params={**FORUM_TEPIC, "fecha": day}).status_code
    assert status("2026-09-26") == 200 and status("2026-09-27") == 200 and status("2026-09-28") == 422


def test_no_cinema_fills_a_tab(client):
    body = client.get("/v1/a-donde-ir/funciones", params={**FORUM_TEPIC, "fecha": DAY, "radio": 15}).json()
    for tab in ("complete", "snacks_unpriced", "unpriced"):
        counts = Counter(r["cinema_name"] for r in body[tab])
        assert max(counts.values(), default=0) <= main.PER_CINEMA


def test_a_movie_shows_all_its_times(client):
    params = {**FORUM_TEPIC, "fecha": DAY, "radio": 15, "pelicula": "resident evil noche cero"}
    counts = Counter(r["cinema_name"] for r in client.get("/v1/a-donde-ir/funciones", params=params).json()["unpriced"])
    assert counts["Forum Tepic"] > main.PER_CINEMA


def test_only_the_configured_sites_get_cors(client):
    params = {**FORUM_TEPIC, "fecha": DAY}
    allowed = client.get("/v1/a-donde-ir/funciones", params=params, headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = client.get("/v1/a-donde-ir/funciones", params=params, headers={"Origin": "https://otro.example"})
    assert "access-control-allow-origin" not in other.headers


def test_each_ip_has_a_limit_per_minute(client, monkeypatch):
    monkeypatch.setattr(config, "API_REQUESTS_PER_MINUTE", 2)
    spoofed = [client.get("/salud", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(3)]
    assert spoofed == [200, 200, 429]                   # X-Forwarded-For del cliente no cuenta
    other = TestClient(main.app, client=("198.51.100.8", 50000))
    assert other.get("/salud").status_code == 200


def test_the_api_computes_only_a_few_searches_at_a_time(monkeypatch):
    monkeypatch.setattr(config, "API_THREADS", 3)
    with TestClient(main.app) as started:
        assert started.portal.call(lambda: anyio.to_thread.current_default_thread_limiter().total_tokens) == 3


def test_health_shows_the_commit_the_api_started_with(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with TestClient(main.app) as started:
        assert started.get("/salud").json()["commit"] is None
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "api.commit").write_text("35d4437a1b2c3d4e5f60718293a4b5c6d7e8f901\n")
    with TestClient(main.app) as started:
        assert started.get("/salud").json()["commit"] == "35d4437"


def test_responses_are_compressed(client):
    res = client.get("/v1/a-donde-ir/opciones", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200 and res.headers["content-encoding"] == "gzip"


def test_the_options_come_before_the_search(client):
    res = client.get("/v1/a-donde-ir/opciones")
    assert res.status_code == 200 and res.headers["cache-control"] == "public, max-age=300"
    assert set(res.json()) == {"plazas", "dates", "formats", "cinemas", "snacks", "combos", "captured_at"}
    assert res.json()["captured_at"].endswith("+00:00")


def test_the_page_omits_only_the_api_defaults():
    source = (Path(__file__).parent.parent / "marketing" / "lib" / "api.ts").read_text()
    page = dict(re.findall(r"^  (\w+): '([^']*)',$", source.split("const API_DEFAULTS")[1].split("};")[0], re.M))
    parameters = main.app.openapi()["paths"]["/v1/a-donde-ir/funciones"]["get"]["parameters"]
    api = {p["name"]: p["schema"]["default"] for p in parameters if p["schema"].get("default") is not None}
    assert page == {name: f"{value:g}" if isinstance(value, float) else str(value) for name, value in api.items()}
