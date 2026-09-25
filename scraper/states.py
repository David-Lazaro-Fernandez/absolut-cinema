"""Estado de cada cine con la clave de entidad de INEGI (`"01"`–`"32"`), común a ambas cadenas.

Ninguna API da el estado real: Cinépolis no publica estado (su "ciudad" `cdmx` incluye cines de Cd. López Mateos, en el
Estado de México) y el "estado 8" de Cinemex es "CDMX y Área Metropolitana". El estado sale de las coordenadas de cada
cine cruzadas con los polígonos estatales de INEGI (`scripts/cinema_states.py`, una vez, fuera del scraper) y se versiona
en `scraper/cinema_states.csv`. Un cine que aún no está en ese archivo toma el estado más común de los cines de su misma
llave geográfica de la API (ciudad de Cinépolis, área de Cinemex); `unmapped()` los lista para volver a correr el script.

Solo librería estándar.
"""
import csv
from collections import Counter
from functools import lru_cache
from pathlib import Path

MAPPING_PATH = Path(__file__).resolve().parent / "cinema_states.csv"

# Clave de entidad de INEGI → nombre corto para pantalla.
STATES = {
    "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur", "04": "Campeche",
    "05": "Coahuila", "06": "Colima", "07": "Chiapas", "08": "Chihuahua", "09": "Ciudad de México",
    "10": "Durango", "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo", "14": "Jalisco",
    "15": "Estado de México", "16": "Michoacán", "17": "Morelos", "18": "Nayarit", "19": "Nuevo León",
    "20": "Oaxaca", "21": "Puebla", "22": "Querétaro", "23": "Quintana Roo", "24": "San Luis Potosí",
    "25": "Sinaloa", "26": "Sonora", "27": "Tabasco", "28": "Tamaulipas", "29": "Tlaxcala", "30": "Veracruz",
    "31": "Yucatán", "32": "Zacatecas",
}


@lru_cache(maxsize=1)
def _mapping():
    by_cinema, by_place = {}, {}
    if MAPPING_PATH.exists():
        with open(MAPPING_PATH, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                by_cinema[(r["chain"], r["cinema_id"])] = r["state_code"]
                by_place.setdefault((r["chain"], r["city_id"]), Counter())[r["state_code"]] += 1
    return by_cinema, {k: c.most_common(1)[0][0] for k, c in by_place.items()}


def state_code(chain, cinema_id, city_id=None):
    """Clave INEGI del estado del cine; si el cine no está mapeado, la más común de su `city_id`; si tampoco, None."""
    by_cinema, by_place = _mapping()
    return by_cinema.get((chain, str(cinema_id))) or by_place.get((chain, str(city_id) if city_id is not None else None))


def is_mapped(chain, cinema_id):
    return (chain, str(cinema_id)) in _mapping()[0]


def unmapped(cinemas):
    """De `cinemas` (dicts con `chain` y `cinema_id`), los que no están en `cinema_states.csv`."""
    return [c for c in cinemas if not is_mapped(c["chain"], c["cinema_id"])]
