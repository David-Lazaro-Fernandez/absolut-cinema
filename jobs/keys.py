"""Llaves de los trabajos programados y el área a la que pertenece cada una.

Una llave es el nombre estable de un trabajo: es el argumento de `make job KEY=…`, el sufijo de su unidad de systemd
(`absolut-cinema-{llave}`) y el campo `key` de `data/logs/jobs.jsonl`. Renombrar una llave renombra su unidad.
El área es la capa del repo dueña del trabajo (tabla de `AGENTS.md`); agrupa la página Operaciones.
"""

SNAPSHOT = "snapshot"
SEATS = "seats"
PRICES = "prices"
DELIVERY = "delivery"
CAPACITY = "capacity"
CALIBRATE_CINEMEX = "calibrate-cinemex"
PRESALE = "presale"
HEALTH = "health"
AUTH_PRUNE = "auth-prune"
BACKUP = "backup"
DEPLOY = "deploy"

CAPTURE, ACCESS, OPERATIONS = "captura", "acceso", "operación"

AREA = {
    SNAPSHOT: CAPTURE,
    SEATS: CAPTURE,
    PRICES: CAPTURE,
    DELIVERY: CAPTURE,
    CAPACITY: CAPTURE,
    CALIBRATE_CINEMEX: CAPTURE,
    PRESALE: CAPTURE,
    HEALTH: OPERATIONS,
    AUTH_PRUNE: ACCESS,
    BACKUP: OPERATIONS,
    DEPLOY: OPERATIONS,
}

ALL = tuple(AREA)
