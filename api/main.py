"""API pública de "¿A dónde ir?": las funciones cerca de un punto que caben en el presupuesto de un grupo.

Responde la búsqueda con `analytics.recommend_search`, sin entregar el catálogo completo. Es anónima: CORS solo para
los sitios de `config.API_ORIGINS` y `config.API_REQUESTS_PER_MINUTE` peticiones por minuto por IP. Corre en un solo
proceso detrás de Caddy. Uvicorn lee la IP del visitante de X-Forwarded-For solo en conexiones de 127.0.0.1
(`FORWARDED_ALLOW_IPS`).

Local: `make api`; la documentación interactiva queda en http://localhost:8000/docs.
"""
import threading
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated, Literal

import anyio.to_thread
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from typing_extensions import TypedDict  # Pydantic lo exige así antes de Python 3.12

import analytics
from analytics import recommender
from scraper import config

DAYS_AHEAD = 1                     # el demo solo ofrece hoy y mañana
MAX_PEOPLE = 20
MAX_RADIUS_KM = 15.0
PER_CINEMA = 6                     # todos los cines del radio salen, sin entregar su cartelera entera
_CACHE_SIZE = 16                   # solo `opciones` y `salud`: iguales para todos y chicas
_MAX_TRACKED_IPS = 10_000


# Lo que sale de la API. FastAPI quita cualquier otra llave de los dicts de `analytics`: los precios por tipo de
# persona, los ids de cine y película y la fecha de muestreo no salen.
class SnackItem(TypedDict):
    name: str
    units: int
    price: float


class Promo(TypedDict):
    name: str
    kind: str
    includes: str
    program: str | None
    program_about: str | None
    condition: str
    price: float
    price_max: float | None
    people: int
    applied: bool


class Show(TypedDict):
    chain: str
    show_id: str
    cinema_name: str
    lat: float
    lng: float
    title: str
    date: str
    datetime_local: str
    language: str
    format_bucket: str
    distance_km: float
    buy_url: str | None
    box_office_only: bool
    tickets_total: float | None
    snacks_total: float | None
    snacks_items: list[SnackItem] | None
    snack_reference: float | None
    total: float | None
    promo: Promo | None


class Summary(TypedDict):
    shows: int
    cinemas: int
    snacks_unpriced: int
    unpriced: int
    nearest: Show | None
    cheapest: Show | None


class SiteCinema(TypedDict):
    chain: str
    chain_label: str
    cinema_name: str


class Site(TypedDict):
    lat: float
    lng: float
    distance_km: float
    shows: int
    cinemas: list[SiteCinema]


class Title(TypedDict):
    title_norm: str
    title: str


class Search(TypedDict):
    summary: Summary
    complete: list[Show]
    snacks_unpriced: list[Show]
    unpriced: list[Show]
    sites: list[Site]
    titles: list[Title]


class Plaza(TypedDict):
    plaza: str
    label: str
    lat: float
    lng: float
    bbox: list[float]


class Day(TypedDict):
    date: str


class OptionCinema(TypedDict):
    chain: str
    chain_label: str
    cinema_name: str
    lat: float
    lng: float


# `for` ("all", "children" o "adults") es palabra reservada: el TypedDict va con la sintaxis funcional.
Combo = TypedDict("Combo", {"name": str, "min": int, "max": int, "for": str})


class Options(TypedDict):
    plazas: list[Plaza]
    dates: list[Day]
    formats: list[str]
    cinemas: list[OptionCinema]
    snacks: list[str]
    combos: list[Combo]
    captured_at: str | None


@asynccontextmanager
async def _lifespan(app):
    # Cada búsqueda en curso ocupa ~13 MB; con 2 núcleos, más hilos solo suman memoria (docs/ec2-sizing.md).
    anyio.to_thread.current_default_thread_limiter().total_tokens = config.API_THREADS
    global _commit
    _commit = _started_commit()
    yield


def _started_commit():
    """Commit corto que anotó el ExecStartPre. None sin archivo (p. ej. con `make api`)."""
    try:
        return (config.DATA_DIR / "run" / "api.commit").read_text().strip()[:7] or None
    except OSError:
        return None


app = FastAPI(title="Matiné API", version="1", docs_url="/docs", redoc_url=None, lifespan=_lifespan)
_cache = OrderedDict()
_cache_lock = threading.Lock()
_hits = {}
_commit = None


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else ""
    now = time.monotonic()
    if len(_hits) > _MAX_TRACKED_IPS:
        _hits.clear()
    window = _hits.setdefault(ip, deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= config.API_REQUESTS_PER_MINUTE:
        return JSONResponse({"detail": "Demasiadas peticiones. Intenta en un minuto."}, status_code=429,
                            headers={"Retry-After": "60"})
    window.append(now)
    return await call_next(request)


# CORS se agrega después del límite para envolverlo: así un 429 también lleva sus cabeceras.
app.add_middleware(CORSMiddleware, allow_origins=list(config.API_ORIGINS), allow_methods=["GET"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)


def _connect():
    try:
        return analytics.connect()
    except FileNotFoundError:
        raise HTTPException(503, "La base de datos no está disponible.") from None


def _read(key, compute):
    """`compute(conn)` con caché. La llave incluye el id de la última captura: una captura nueva la invalida."""
    conn = _connect()
    try:
        version = conn.execute("SELECT MAX(id) FROM snapshot").fetchone()[0]
        with _cache_lock:
            if (version, *key) in _cache:
                _cache.move_to_end((version, *key))
                return _cache[(version, *key)]
        value = compute(conn)
    finally:
        conn.close()
    with _cache_lock:
        _cache[(version, *key)] = value
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return value


def _days():
    first = date.fromisoformat(analytics.today())
    return first.isoformat(), (first + timedelta(days=DAYS_AHEAD)).isoformat()


@app.get("/salud")
def health():
    """200 con la hora de la última captura de cada cadena y el commit que corre la API (None si no se sabe)."""
    return {**_read(("salud", int(time.time() // 60)), lambda conn: {
        "ok": True,
        "last_capture": {r["chain"]: r["taken_at"] for r in conn.execute(
            "SELECT chain, MAX(taken_at) taken_at FROM snapshot WHERE ok = 1 GROUP BY chain ORDER BY chain")}}),
        "commit": _commit}


@app.get("/v1/a-donde-ir/opciones")
def options(response: Response) -> Options:
    """Plazas (centro y caja), días con funciones, formatos, cines para las sugerencias, paquetes de dulcería y combos.
    `captured_at` es la hora de la captura más reciente."""
    d0, d1 = _days()
    response.headers["Cache-Control"] = "public, max-age=300"
    return _read(("opciones", d0), lambda conn: {
        **analytics.recommend_options(conn, d0=d0, d1=d1),
        "captured_at": conn.execute("SELECT MAX(taken_at) FROM snapshot WHERE ok = 1").fetchone()[0]})


@app.get("/v1/a-donde-ir/funciones")
def shows(response: Response,
          lat: Annotated[float, Query(ge=-90, le=90)], lng: Annotated[float, Query(ge=-180, le=180)],
          fecha: Annotated[date, Query(description="Día de la función (AAAA-MM-DD)")],
          adultos: Annotated[int, Query(ge=0, le=MAX_PEOPLE)] = 2,
          ninos: Annotated[int, Query(ge=0, le=MAX_PEOPLE)] = 0,
          mayores: Annotated[int, Query(ge=0, le=MAX_PEOPLE)] = 0,
          dulceria: Literal[recommender.SNACK_PACKAGES] = "none",
          combo: Annotated[str | None, Query(max_length=120, description="Nombre de un combo de `opciones`; manda sobre `dulceria`")] = None,
          presupuesto: Annotated[float | None, Query(gt=0)] = None,
          radio: Annotated[float, Query(gt=0, le=MAX_RADIUS_KM)] = 5.0,
          desde: Annotated[int, Query(ge=0, le=23)] = 0, hasta: Annotated[int, Query(ge=1, le=24)] = 24,
          pelicula: Annotated[str | None, Query(max_length=200)] = None,
          formato: Annotated[str | None, Query(max_length=20)] = None,
          orden: Literal[recommender.SORTS] = "distance",
          sitio: Annotated[str | None, Query(pattern=r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$",
                                             description="lat,lng de un edificio: todas sus funciones")] = None) -> Search:
    """Las funciones cerca de (`lat`, `lng`) que caben, un punto por edificio para el mapa y las películas cercanas.
    Hasta `PER_CINEMA` funciones por cine; con `pelicula`, todas las de esa película. Los empates no favorecen a
    ninguna cadena."""
    people = adultos + ninos + mayores
    if not 1 <= people <= MAX_PEOPLE:
        raise HTTPException(422, f"El grupo debe tener entre 1 y {MAX_PEOPLE} personas.")
    first, last = _days()
    if not first <= fecha.isoformat() <= last:
        raise HTTPException(422, f"La fecha debe estar entre {first} y {last}.")
    if desde >= hasta:
        raise HTTPException(422, "`desde` debe ser menor que `hasta`.")
    if combo is not None and combo not in recommender.COMBOS:
        raise HTTPException(422, "`combo` debe ser uno de los combos de `opciones`.")
    site = tuple(float(x) for x in sitio.split(",")) if sitio else None
    params = dict(lat=round(lat, 4), lng=round(lng, 4), d0=fecha.isoformat(), d1=fecha.isoformat(),
                  hours=(desde, hasta), adults=adultos, children=ninos, seniors=mayores, snacks=dulceria, combo=combo,
                  budget=presupuesto, radius_km=radio, title_norm=pelicula, formats=(formato,) if formato else None,
                  sort=orden, per_cinema=None if pelicula else PER_CINEMA, limit=None, favor_us=False, site=site)
    response.headers["Cache-Control"] = "public, max-age=60"
    # Sin caché en el servidor: dos visitantes casi nunca piden lo mismo, y el navegador ya guarda la suya.
    conn = _connect()
    try:
        return analytics.recommend_search(conn, **params)
    finally:
        conn.close()
