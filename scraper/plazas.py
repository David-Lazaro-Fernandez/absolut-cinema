"""Plazas: qué cines de cada cadena forman una misma zona metropolitana comparable.

Cada API nombra la geografía distinto y con distinta granularidad: Cinépolis por slug de ciudad (`cityId`, 154 el
2026-09-11) y Cinemex por área dentro de un estado (`area.id`, ~100). Una plaza es la unión de las llaves de ambas
cadenas que caen en la misma zona; se curó el 2026-09-11 por distancia de cada cine al centroide metropolitano
(CDMX 45 km, Guadalajara 35 km, Monterrey 40 km). `cdmx` se define igual que el piloto (ciudad `cdmx` de Cinépolis,
las seis áreas del estado 8 de Cinemex) para que las cifras del dashboard no se muevan; Cinépolis lista aparte 28
cines de la zona metropolitana (Neza, Ecatepec, Coacalco, Cuautitlán, Chalco…) que Cinemex sí incluye en su estado 8,
así que ampliar la plaza a metrópoli es una decisión pendiente con el cliente.

Lo comparten el scraper (para acotar el muestreo de planos, `config.SEATS_PLAZAS`) y `analytics/` (filtro de plaza
del dashboard). Solo librería estándar; las etiquetas para el usuario viven en `analytics/labels.py`.
"""

PLAZAS = {
    "cdmx": {"cinepolis": ("cdmx",),
             "cinemex": ("15", "16", "17", "18", "19", "20"),                      # Centro, Nor-oriente, Norte, Oriente, Poniente, Sur
             "cineteca": ("001", "002", "003")},                                   # Cineteca: Chapultepec, de las Artes, México (Xoco)
    "gdl": {"cinepolis": ("guadalajara", "tlajomulco"),
            "cinemex": ("35", "38")},                                              # Guadalajara, Tonalá
    "mty": {"cinepolis": ("monterrey",),
            "cinemex": ("42", "43", "44", "46", "47", "48", "49", "104")},        # Apodaca … Salinas Victoria
}


def city_ids(plaza, chain):
    """Llaves de ciudad/área de una cadena dentro de una plaza; vacío si la plaza no existe."""
    return tuple(PLAZAS.get(plaza, {}).get(chain, ()))


def city_ids_for(plazas, chain):
    """Unión de las llaves de varias plazas para una cadena, sin repetidos y en orden estable."""
    out = []
    for plaza in plazas:
        for cid in city_ids(plaza, chain):
            if cid not in out:
                out.append(cid)
    return tuple(out)
