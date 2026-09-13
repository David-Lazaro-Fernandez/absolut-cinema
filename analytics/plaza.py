"""Filtro de plaza para las consultas: qué cines entran en una comparación.

La membresía (qué ciudades de Cinépolis y qué áreas de Cinemex forman cada plaza) vive en `scraper/plazas.py` y la
comparte el muestreo de planos; aquí solo se traduce a SQL. `plaza=None` significa nacional: sin filtro. Las filas de
`current_showtime` llevan `city_id`; las tablas de muestreo no, y se filtran a través de la dimensión `cinema`.
"""
from scraper.plazas import PLAZAS, city_ids

from .db import rows


def _pairs(plaza):
    """[(chain, (city_id, …)), …] de la plaza; ValueError si no existe (es un error de programación, no un dato)."""
    if plaza not in PLAZAS:
        raise ValueError(f"plaza desconocida: {plaza!r}; las conocidas son {sorted(PLAZAS)}")
    return [(chain, city_ids(plaza, chain)) for chain in ("cinemex", "cinepolis") if city_ids(plaza, chain)]


def plaza_where(plaza, alias=""):
    """Cláusula `AND (…)` sobre `chain` y `city_id` de una tabla que los tiene (`current_showtime`). Devuelve
    (sql, params); vacío para `plaza=None`. `alias` es el prefijo de la tabla ('s.')."""
    if plaza is None:
        return "", []
    parts, params = [], []
    for chain, keys in _pairs(plaza):
        parts.append(f"({alias}chain = ? AND {alias}city_id IN ({','.join('?' for _ in keys)}))")
        params += [chain, *keys]
    return " AND (" + " OR ".join(parts) + ")", params


def plaza_cinema_where(plaza, alias=""):
    """Cláusula `AND …` para tablas sin geografía propia (`occupancy_sample`, `price_sample`, `concession_price`,
    `auditorium`, `event`): el cine debe estar en la plaza según la dimensión `cinema`."""
    if plaza is None:
        return "", []
    parts, params = [], []
    for chain, keys in _pairs(plaza):
        parts.append(f"(chain = ? AND city_id IN ({','.join('?' for _ in keys)}))")
        params += [chain, *keys]
    return f" AND {alias}cinema_id IN (SELECT cinema_id FROM cinema WHERE {' OR '.join(parts)})", params


def plazas(conn):
    """Plazas definidas que tienen cines en la base: `plaza`, `cinemas_cinemex`, `cinemas_cinepolis`, en el orden de
    `scraper.plazas.PLAZAS`. Es la lista del selector del dashboard."""
    out = []
    for plaza in PLAZAS:
        where, params = plaza_where(plaza)
        r = rows(conn, f"""
            SELECT SUM(chain = 'cinemex') cinemas_cinemex, SUM(chain = 'cinepolis') cinemas_cinepolis
            FROM cinema WHERE 1 = 1{where}""", params)[0]
        if r["cinemas_cinemex"] or r["cinemas_cinepolis"]:
            out.append({"plaza": plaza, "cinemas_cinemex": r["cinemas_cinemex"] or 0, "cinemas_cinepolis": r["cinemas_cinepolis"] or 0})
    return out


def plaza_coverage(conn, limit=None):
    """Registro de la captura por geografía cruda: por cadena y `city_id` (Cinépolis ciudad, Cinemex área), cines,
    funciones vigentes, el estado de Cinemex, un nombre de cine de muestra y la plaza a la que pertenece (None si
    ninguna). Ordenado por funciones descendentes. Es la base para decidir qué plazas entran al muestreo de planos."""
    data = rows(conn, f"""
        SELECT c.chain, c.city_id, MAX(c.state_id) state_id, COUNT(DISTINCT c.cinema_id) cinemas, COUNT(s.show_id) shows,
               MIN(c.name) sample_cinema
        FROM cinema c LEFT JOIN current_showtime s ON s.chain = c.chain AND s.cinema_id = c.cinema_id
        GROUP BY c.chain, c.city_id ORDER BY shows DESC, c.chain, c.city_id{' LIMIT ?' if limit else ''}""",
                (limit,) if limit else ())
    membership = {(chain, key): plaza for plaza in PLAZAS for chain, keys in _pairs(plaza) for key in keys}
    for r in data:
        r["plaza"] = membership.get((r["chain"], r["city_id"]))
    return data
