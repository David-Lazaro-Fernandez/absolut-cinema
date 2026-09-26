"""Entrada de cada trabajo programado, por llave de `jobs.keys`.

Cada entrada dice qué corre (`steps`), cuándo (`schedule`, hora de America/Mexico_City, la zona del servidor), con qué
tope (`timeout_min`), dónde (`hosts`: `server` con systemd, `mac` con launchd) y qué escribe (`writes`, solo para la
documentación). Lo que no se declara toma el valor de `DEFAULTS`. Se leen con `entry(key)`, nunca indexando `REGISTRY`.

Un paso es una tupla `(intérprete, módulo o script, *argumentos)`:
  - `"python"`: el Python del sistema (`python3 -m módulo`), para `scraper/` y todo lo que es solo stdlib;
  - `"venv"`: `.venv/bin/python -m módulo`, para lo que necesita el venv (`auth/`: `hashlib.scrypt` y boto3);
  - `"bash"`: un script del repo.
Los pasos de un trabajo corren en orden y todos, aunque uno falle (igual que `make -k`); el trabajo falla si alguno falló.

Horario: una tupla de `"HH:MM"` (diario), `"*:MM"` (cada hora), `"Sun HH:MM"` (semanal, día en inglés de tres letras)
o `"1 HH:MM"` (mensual, día del mes).

Los trabajos que escriben en `snapshots.db` van a minutos distintos (capturas :30, planos :50, diarios :07) y además SQLite serializa cada transacción (WAL, `timeout` de `store.connect`). Las capturas descargan en paralelo
y escriben en segundos al final, así que no hace falta un candado de base entre trabajos: el candado de `jobs.run` es
por llave y evita que un mismo trabajo corra dos veces a la vez (timer y corrida a mano).
"""
from . import keys

DEFAULTS = {
    "steps": (),
    "schedule": (),
    "timeout_min": 30,
    "enabled": True,        # False: la unidad se instala pero el timer queda apagado (se enciende a mano)
    "hosts": ("server",),
    "egress": False,        # True: sale por WARP (Cinépolis); la unidad espera a warp-svc y privoxy
    "user": "absolut",
    "nice": 10,
    "jitter_min": 0,        # retraso aleatorio del timer, para no arrancar varios trabajos en el mismo segundo
    "catch_up": True,       # si el servidor estaba apagado a la hora programada, corre al arrancar
    "retries": 0,           # reintentos del trabajo completo si falla; los reintentos por petición ya están en http.py
    "retry_delay_s": 0,
    "writes": (),
    "description": "",
}

REGISTRY = {
    keys.SNAPSHOT: {
        "description": "Captura de cartelera: nacional de ambas cadenas más la Cineteca Nacional en CDMX (descarga en paralelo, 15–30 min)",
        "steps": (("python", "scraper.run"),),
        "schedule": ("07:30", "13:30", "20:30"),
        "timeout_min": 45,
        "hosts": ("server", "mac"),
        "egress": True,
        "nice": 5,
        "writes": ("snapshot", "snapshot_unit", "cinema", "current_showtime", "event", "data/raw"),
    },
    keys.SEATS: {
        "description": "Planos de asientos de las tres cadenas 15–75 min tras el inicio (asistencia final), plazas de AC_SEATS_PLAZAS",
        "steps": (("python", "scraper.sample", "--post-start"),
                  ("python", "scraper.sample", "--post-start", "--chain", "cinemex"),
                  ("python", "scraper.sample", "--post-start", "--chain", "cineteca")),
        "schedule": ("*:50",),
        "timeout_min": 30,
        "hosts": ("server", "mac"),
        "egress": True,
        "nice": 5,
        "writes": ("occupancy_sample",),
    },
    keys.PRICES: {
        "description": "Precios de boleto por cine, formato y tipo de día, y menú de dulcería de Cinépolis",
        "steps": (("python", "scraper.sample", "--prices"), ("python", "scraper.sample", "--concessions")),
        "schedule": ("06:07",),
        "timeout_min": 60,
        "hosts": ("server", "mac"),
        "egress": True,
        "jitter_min": 2,
        "writes": ("price_sample", "concession_price"),
    },
    keys.DELIVERY: {
        "description": "Dulcería a domicilio de ambas cadenas en Rappi y DiDi Food (las tiendas abren a las 13:00)",
        "steps": (("python", "scraper.delivery"),),
        "schedule": ("15:07",),
        "timeout_min": 60,
        "hosts": ("server", "mac"),
        "jitter_min": 2,
        "writes": ("delivery_price",),
    },
    keys.CAPACITY: {
        "description": "Aforo por sala de Cinépolis en AC_SEATS_PLAZAS, refresco mensual",
        "steps": (("python", "scraper.sample", "--capacity", "--refresh"),),
        "schedule": ("1 04:07",),
        "timeout_min": 90,
        "egress": True,
        "jitter_min": 2,
        "writes": ("auditorium",),
    },
    # Lee el color y lo vendido a T−60 en el mismo instante; se detiene sola al llegar a 100 muestras por nivel.
    keys.CALIBRATE_CINEMEX: {
        "description": "Calibración del semáforo de Cinemex contra el plano público, 100 funciones por nivel (tope 60 por corrida)",
        "steps": (("python", "scraper.sample", "--occupancy", "--chain", "cinemex", "--per-level", "100",
                   "--lead", "60", "--tolerance", "45", "--limit", "60"),),
        "schedule": ("19:07",),
        "timeout_min": 20,
        "hosts": ("server", "mac"),
        "jitter_min": 2,
        "catch_up": False,
        "writes": ("occupancy_sample",),
    },
    keys.PRESALE: {
        "description": "Preventas de ambas cadenas: panel de hasta 30 funciones por título en preventa, plano a diario",
        "steps": (("python", "scraper.presale"), ("python", "scraper.presale", "--chain", "cinepolis")),
        "schedule": ("10:07",),
        "timeout_min": 45,
        "hosts": ("server", "mac"),
        "egress": True,
        "jitter_min": 2,
        "writes": ("presale_sample", "data/raw/cinemex_presale"),
    },
    keys.HEALTH: {
        "description": "Salud de la captura en 24 h; sale con 1 si hay huecos o fallos",
        "steps": (("python", "scraper.health"),),
        "schedule": ("08:07",),
        "timeout_min": 5,
        "hosts": ("server", "mac"),
        "jitter_min": 2,
        "writes": ("data/logs/health.log",),
    },
    keys.AUTH_PRUNE: {
        "description": "Borra sesiones y enlaces de acceso vencidos hace más de 90 días",
        "steps": (("venv", "auth.cli", "prune"),),
        "schedule": ("Sun 04:07",),
        "timeout_min": 10,
        "writes": ("app.db: session", "token"),
    },
    # S3 falla de vez en cuando por red; un reintento a los 10 min basta y el respaldo del día no se pierde.
    keys.BACKUP: {
        "description": "Copia consistente de snapshots.db y del crudo al bucket",
        "steps": (("bash", "deploy/backup.sh"),),
        "schedule": ("05:07",),
        "timeout_min": 30,
        "nice": 0,
        "retries": 1,
        "retry_delay_s": 600,
        "writes": ("bucket de respaldo",),
    },
    # Como root: recarga unidades y reinicia el dashboard; el código lo trae como absolut (deploy/update.sh). Sin nada
    # nuevo en stable sale en segundos.
    keys.DEPLOY: {
        "description": "Trae origin/stable si se movió, reinstala si cambió requirements, sincroniza unidades y reinicia el dashboard",
        "steps": (("bash", "deploy/update.sh"),),
        "schedule": ("*:02", "*:17", "*:32", "*:47"),
        "timeout_min": 10,
        "user": "root",
        "nice": 0,
        "writes": ("código en /opt/absolut-cinema", "data/logs/deploy.log"),
    },
}

INTERPRETERS = ("python", "venv", "bash")
HOSTS = ("server", "mac")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos")


class RegistryError(Exception):
    """El registro no es coherente con `jobs.keys` o una entrada está mal formada."""


def entry(key):
    """La entrada completa de `key`, con los valores por defecto aplicados."""
    if key not in REGISTRY:
        raise RegistryError(f"trabajo desconocido: {key}; opciones: {', '.join(keys.ALL)}")
    return {**DEFAULTS, **REGISTRY[key], "key": key, "area": keys.AREA[key]}


def entries(host=None):
    """Todas las entradas en el orden de `keys.ALL`; con `host`, solo las que corren ahí."""
    return [entry(k) for k in keys.ALL if host is None or host in entry(k)["hosts"]]


def parse_schedule(spec):
    """`"07:30"`, `"*:50"`, `"Sun 04:07"` o `"1 04:07"` → `{"weekday", "day", "hour", "minute"}`; `None` = cualquiera.
    `weekday` va de 0 (lunes) a 6 (domingo)."""
    day_part, _, clock = spec.rpartition(" ")
    hh, _, mm = clock.partition(":")
    out = {"weekday": None, "day": None, "hour": None if hh == "*" else int(hh), "minute": int(mm)}
    if day_part in WEEKDAYS:
        out["weekday"] = WEEKDAYS.index(day_part)
    elif day_part:
        out["day"] = int(day_part)
    if not (0 <= out["minute"] < 60 and (out["hour"] is None or 0 <= out["hour"] < 24)
            and (out["day"] is None or 1 <= out["day"] <= 28)):
        raise RegistryError(f"horario inválido: {spec!r}")
    return out


def daily_times(key):
    """Las horas `"HH:MM"` en que corre `key` todos los días (lo que `scraper.health` espera ver capturado)."""
    return tuple(s for s in entry(key)["schedule"]
                 if (p := parse_schedule(s))["hour"] is not None and p["weekday"] is None and p["day"] is None)


def describe_schedule(schedule):
    """El horario en palabras: `07:30, 13:30, 20:30`, `cada hora a :22 y :52`, `domingos 04:07`, `día 1, 04:07`."""
    specs = [parse_schedule(s) for s in schedule]
    if all(p["hour"] is None for p in specs):
        return "cada hora a " + " y ".join(f":{p['minute']:02d}" for p in specs)
    parts = []
    for p in specs:
        clock = f"{p['hour']:02d}:{p['minute']:02d}"
        if p["weekday"] is not None:
            clock = f"{DAY_NAMES[p['weekday']]} {clock}"
        elif p["day"] is not None:
            clock = f"día {p['day']}, {clock}"
        parts.append(clock)
    return ", ".join(parts)


def validate():
    """Levanta `RegistryError` si alguna llave no tiene entrada o área, o si una entrada está mal formada."""
    if set(REGISTRY) != set(keys.AREA):
        missing, extra = set(keys.AREA) - set(REGISTRY), set(REGISTRY) - set(keys.AREA)
        raise RegistryError(f"llaves sin entrada: {sorted(missing)}; entradas sin llave: {sorted(extra)}")
    for key, raw in REGISTRY.items():
        unknown = set(raw) - set(DEFAULTS)
        if unknown:
            raise RegistryError(f"{key}: campos desconocidos {sorted(unknown)}")
        e = entry(key)
        if not e["steps"] or any(s[0] not in INTERPRETERS or len(s) < 2 for s in e["steps"]):
            raise RegistryError(f"{key}: pasos vacíos o con intérprete desconocido")
        if not e["schedule"] or not set(e["hosts"]) <= set(HOSTS):
            raise RegistryError(f"{key}: sin horario o con un host desconocido")
        for spec in e["schedule"]:
            parse_schedule(spec)


validate()
