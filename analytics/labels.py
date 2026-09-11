"""Textos para directivos. Cualquier cosa que se muestre a un usuario sale de aquí, no de los
nombres internos (chain, kind, franjas, buckets)."""

US = "cinemex"            # la cadena del cliente: en las frases hablamos en primera persona
THEM = "cinepolis"

CHAIN_LABEL = {"cinemex": "Cinemex", "cinepolis": "Cinépolis"}

# Paleta (ver DESIGN.md). El rojo significa Cinemex o acción; Cinépolis va en tinta (casi negro) para
# no competir con él. Cinemex siempre primero en las escalas, nunca se ciclan.
RED = "#E31837"            # rojo Cinemex
RED_DARK = "#9E0F26"       # hover / activo; primer tono de la rampa
RED_SOFT = "#FDEDF0"       # fondo suave para chips y hover
INK = "#191A1E"            # texto fuerte; serie Cinépolis
GRAY_DARK = "#3A3C42"      # texto de etiquetas en gráficas
GRAY = "#5C6068"           # texto secundario
GRAY_LIGHT = "#F6F6F4"     # fondo de página
LINE = "#E4E5E9"           # bordes y divisores
PAPER = "#FFFFFF"          # tarjetas
CHAIN_COLOR = {"cinemex": RED, "cinepolis": INK}
NEUTRAL = "#C9CBD0"        # líneas de referencia (la barra del dumbbell)
GRID = "#ECEDEF"           # rejilla de gráficas
RED_RAMP = [RED_DARK, RED, "#F08497", "#F7CDD5"]                 # ordinal de un solo tono para cubetas ordenadas
DIVERGING = [INK, "#8C8E95", "#EFEFEF", "#F6B7C2", RED]          # Cinépolis (tinta) ↔ centro ↔ Cinemex (rojo)
WARN = "#B45309"           # ámbar: estado con problema, solo en la página de operaciones (el rojo es Cinemex)
OK = "#2F6F4E"             # verde apagado: estado sano, solo en la página de operaciones

# Franjas horarias: (clave, hora inicio, hora fin exclusiva, etiqueta). La matiné 10–12 va aparte
# porque existe en fin de semana y es donde una cadena puede ganar barato.
SLOTS = [
    ("antes_10", 0, 10, "Antes de 10:00 A.M."),
    ("de_10_a_12", 10, 12, "10:00 A.M. a 12:00 P.M."),
    ("de_12_a_15", 12, 15, "12:00 P.M. a 3:00 P.M."),
    ("de_15_a_18", 15, 18, "3:00 P.M. a 6:00 P.M."),
    ("de_18_a_21", 18, 21, "6:00 P.M. a 9:00 P.M."),
    ("despues_21", 21, 24, "Después de 9:00 P.M."),
]
SLOT_LABEL = {k: label for k, _, _, label in SLOTS}
SLOT_SHORT = {"antes_10": "Antes de 10 A.M.", "de_10_a_12": "10 A.M. – 12 P.M.", "de_12_a_15": "12 – 3 P.M.",
              "de_15_a_18": "3 – 6 P.M.", "de_18_a_21": "6 – 9 P.M.", "despues_21": "Después de 9 P.M."}
PRIME_START_HOUR = 18
# Filtro global de franja: solo se puede cortar en los límites de SLOTS, así ninguna franja queda partida.
HOUR_MARKS = sorted({lo for _, lo, _, _ in SLOTS} | {hi for _, _, hi, _ in SLOTS})
FULL_DAY = (0, 24)
HOUR_PRESETS = {"Todo el día": FULL_DAY, "Después de las 6 PM": (PRIME_START_HOUR, 24), "Matiné, antes de las 12 PM": (0, 12)}            # horario prime: vie–dom de 6:00 P.M. en adelante
PRIME_LABEL = "viernes a domingo, de 6:00 P.M. en adelante"

WEEKDAY_LABEL = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Mix de formato: la sala manda sobre la tecnología, y la tecnología sobre el 3D.
FORMAT_BUCKETS = ["premium", "large", "3d4d", "traditional"]
FORMAT_LABEL = {"premium": "Premium / VIP", "large": "Gran formato", "3d4d": "3D o 4D", "traditional": "Tradicional"}
LANGUAGE_LABEL = {"spanish": "Español", "subtitled": "Subtitulada", "original": "Español", "other": "Otro"}
PLATFORM_LABEL = {"rappi": "Rappi", "didi": "DiDi Food"}
CINEMA_TYPE_LABEL = {"vip": "VIP", "traditional": "Tradicional"}
# Plaza: cada cadena la nombra distinto (Cinépolis por slug de ciudad, Cinemex por id de estado). Hoy solo CDMX; al
# abrir más plazas se amplía con el catálogo de ciudades de cada API.
CITY_LABEL = {"cdmx": "CDMX", "8": "CDMX"}

LANGUAGE_BUCKETS = ["spanish", "subtitled"]

KIND_LABEL = {
    "added": "Función nueva",
    "removed": "Función cancelada",
    "expired": "Función concluida",
    "moved": "Cambio de horario o sala",
    "changed": "Cambio de idioma o formato",
    "availability": "Cambio de ocupación",
}
KIND_PLURAL = {
    "added": "funciones nuevas",
    "removed": "funciones canceladas",
    "expired": "funciones concluidas",
    "moved": "cambios de horario o sala",
    "changed": "cambios de idioma o formato",
    "availability": "cambios de ocupación",
}
# Línea de tiempo por función.
KIND_LABEL["first_seen"] = "Publicada"
FIELD_LABEL = {"datetime_local": "Hora", "screen": "Sala", "language": "Idioma", "format": "Formato", "experience": "Experiencia",
               "premium_tier": "Tipo de sala", "movie_id": "Película", "availability": "Ocupación"}
STATUS_LABEL = {"current": "Vigente", "removed": "Cancelada", "expired": "Concluida"}
VS_NOW_LABEL = {"same": "Igual que hoy", "changed": "Cambió después", "gone": "Ya no está publicada"}

KIND_HELP = {
    "added": "Apareció una función que no estaba en la cartelera publicada.",
    "removed": "Una función publicada desapareció cuando faltaban más de 30 minutos para empezar.",
    "expired": "La función empezó y salió de la cartelera publicada; se guarda solo para reconstruir la historia.",
    "moved": "La misma función cambió de hora o de sala.",
    "changed": "La misma función cambió de idioma (doblada/subtitulada), formato o experiencia.",
    "availability": "Cambió el nivel de ocupación reportado por la cadena.",
}

COLUMN_LABEL = {
    "status": "Estado", "first_seen": "Publicada", "vs_now": "Frente a hoy", "changes": "Cambios", "detected_at": "Detectado",
    "platform": "Plataforma", "store_name": "Tienda", "stores": "Tiendas", "address": "Dirección",
    "description": "Descripción", "pct_single_price": "% productos con precio único", "last_sampled": "Última lectura",
    "product_name": "Producto", "category": "Categoría", "products": "Productos", "listings": "Referencias",
    "avg_price": "Precio promedio",
    "spread_pct": "Máx. vs mín. %", "distinct_prices": "Precios distintos", "price": "Precio", "categories": "Categorías",
    "chain": "Cadena", "cinemas": "Cines", "shows": "Funciones", "movies": "Películas",
    "pct_subtitled": "% subtituladas", "shows_per_cinema": "Funciones por cine",
    "pct_prime": "% en horario prime", "pct_evening": "% de 6:00 P.M. en adelante",
    "total": "Total", "title": "Película", "title_norm": "Película",
    "title_cinemex": "Título en Cinemex", "title_cinepolis": "Título en Cinépolis",
    "shows_cinemex": "Funciones Cinemex", "shows_cinepolis": "Funciones Cinépolis",
    "cinemas_cinemex": "Cines Cinemex", "cinemas_cinepolis": "Cines Cinépolis",
    "per_cinema_cinemex": "Por cine Cinemex", "per_cinema_cinepolis": "Por cine Cinépolis",
    "share_cinemex": "% programación Cinemex", "share_cinepolis": "% programación Cinépolis",
    "gap_pp": "Diferencia (puntos)", "shows_total": "Funciones totales",
    "kind": "Tipo de cambio", "movie_title": "Película",
    "cinema_id": "Cine", "cinema_name": "Cine", "date": "Fecha", "datetime_local": "Función",
    "show_id": "Id", "n": "Cambios",
    "hhi": "Índice de concentración (HHI)", "top3_pct": "Peso del Top 3", "titles_per_cinema": "Títulos por complejo",
    "titles": "Títulos distintos",
    "screens": "Salas", "seats": "Butacas", "avg_seats": "Butacas por sala", "min_seats": "Sala más chica",
    "max_seats": "Sala más grande", "seats_offered": "Butacas ofertadas", "pct_known": "% funciones con aforo",
    "share_shows": "% de funciones", "share_seats": "% de butacas", "avg_seats_per_show": "Butacas por función",
    "samples": "Muestras", "avg_sold_pct": "% vendido (promedio)", "min_sold_pct": "Mínimo", "max_sold_pct": "Máximo",
    "sold": "Vendidos", "sold_pct": "% vendido", "minutes_to_start": "Minutos antes", "sampled_at": "Muestreado",
    "availability": "Semáforo", "format_bucket": "Formato", "day_type": "Tipo de día", "median_price": "Precio general (mediana)",
    "min_price": "Mínimo", "max_price": "Máximo", "screen": "Sala",
}
DAY_TYPE_LABEL = {"weekday": "Lunes y jueves", "promo": "Martes y miércoles", "weekend": "Viernes a domingo"}
AVAILABILITY_LABEL = {"#FFBE06": "Amarillo", "#FF804A": "Naranja", "#A2ACBA": "Gris", "(sin color)": "Sin color",
                      "high": "Alta disponibilidad", "mid": "Media", "low": "Baja"}


def hour_12(hour, minute=0):
    """17 -> '5:00 P.M.'; 0 -> '12:00 A.M.'"""
    suffix = "A.M." if hour < 12 else "P.M."
    h = hour % 12 or 12
    return f"{h}:{minute:02d} {suffix}"


def hour_mark(hour):
    """Etiqueta de una marca del filtro de franja: 18 -> '6:00 P.M.', 24 -> 'medianoche', 0 -> 'apertura'."""
    return "apertura" if hour == 0 else "medianoche" if hour == 24 else hour_12(hour)


def hours_label(hours):
    """'Todo el día', 'de 6:00 P.M. en adelante', 'antes de 12:00 P.M.' o 'de 10:00 A.M. a 3:00 P.M.'."""
    h0, h1 = hours or FULL_DAY
    if (h0, h1) == FULL_DAY:
        return "Todo el día"
    if h1 == 24:
        return f"de {hour_12(h0)} en adelante"
    if h0 == 0:
        return f"antes de {hour_12(h1)}"
    return f"de {hour_12(h0)} a {hour_12(h1)}"


def time_12(hhmm):
    """'17:30' -> '5:30 P.M.'"""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return hour_12(h, m)


def date_es(iso, with_year=True):
    """'2026-09-07' -> 'lunes 7 de septiembre de 2026'"""
    from datetime import date
    d = date.fromisoformat(iso)
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    s = f"{dias[d.weekday()]} {d.day} de {meses[d.month - 1]}"
    return f"{s} de {d.year}" if with_year else s


def range_es(d0, d1):
    if d0 == d1:
        return date_es(d0)
    return f"del {date_es(d0, with_year=False)} al {date_es(d1)}"


def range_short(d0, d1):
    """'2026-09-08','2026-09-09' -> 'mar 8 – mié 9 sep 2026'"""
    from datetime import date
    a, b = date.fromisoformat(d0), date.fromisoformat(d1)
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    if a == b:
        return f"{dias[a.weekday()]} {a.day} {meses[a.month - 1]} {a.year}"
    if a.month == b.month:
        return f"{dias[a.weekday()]} {a.day} – {dias[b.weekday()]} {b.day} {meses[b.month - 1]} {b.year}"
    return f"{dias[a.weekday()]} {a.day} {meses[a.month - 1]} – {dias[b.weekday()]} {b.day} {meses[b.month - 1]} {b.year}"


# --- Cuentas y acceso (auth/, ui/auth.py, views/login|olvide|restablecer|usuarios) ---
ROLE_LABEL = {"admin": "Administrador", "viewer": "Consulta"}
ROLE_HELP = {"admin": "Gestiona cuentas y ve todo.", "viewer": "Ve la cartelera, la dulcería y los datos."}
AUTH_TEXT = {
    "app_name": "Absolut Cinema",
    "login_title": "Entrar",
    "login_lead": "Inteligencia de cartelera de Cinemex frente a Cinépolis.",
    "email": "Correo",
    "password": "Contraseña",
    "password_confirm": "Confirma la contraseña",
    "enter": "Entrar",
    "forgot": "¿Olvidaste tu contraseña?",
    "back_to_login": "Volver a entrar",
    "logout": "Cerrar sesión",
    "forgot_title": "Restablecer contraseña",
    "forgot_lead": "Escribe tu correo y te enviaremos un enlace para elegir una contraseña nueva.",
    "send_link": "Enviar enlace",
    "forgot_done": "Si el correo está registrado, en unos minutos recibirás un enlace. Revisa también la carpeta de spam.",
    "reset_title": "Elige tu contraseña nueva",
    "invite_title": "Bienvenido: elige tu contraseña",
    "reset_lead": "Para la cuenta {email}. Mínimo 12 caracteres.",
    "save_password": "Guardar contraseña",
    "reset_done": "Contraseña guardada. Ya puedes entrar con ella.",
    "password_mismatch": "Las contraseñas no coinciden.",
    "password_short": "La contraseña debe tener al menos 12 caracteres.",
    "password_is_email": "La contraseña no puede ser tu correo.",
    "token_missing": "Este enlace no es válido. Pide uno nuevo desde “¿Olvidaste tu contraseña?”.",
    "signed_in_as": "Sesión de",
    "continue": "Si la página no se recarga sola, continúa aquí.",
    "pg_unavailable": "El archivo histórico no responde en este momento. Inténtalo en unos minutos.",
    # Mensajes por clase de error de auth.errors (type(e).__name__).
    "InvalidCredentials": "Correo o contraseña incorrectos.",
    "AccountInactive": "Correo o contraseña incorrectos.",
    "AccountLocked": "Demasiados intentos. Vuelve a intentarlo en {minutes} minutos.",
    "TokenInvalid": "Este enlace ya no sirve: caducó o ya se usó. Pide uno nuevo desde “¿Olvidaste tu contraseña?”.",
    "WeakPassword": "La contraseña no cumple la regla mínima.",
    "DuplicateEmail": "Ya existe una cuenta con ese correo.",
    "LastAdmin": "No puedes dejar el sistema sin administradores.",
    "SelfChange": "No puedes cambiar tu propia cuenta desde aquí.",
    # Página de usuarios.
    "users_title": "Usuarios",
    "users_lead": "Quién entra al tablero y con qué rol. Las cuentas nuevas reciben un enlace para elegir su contraseña.",
    "new_account": "Nueva cuenta",
    "name": "Nombre",
    "role": "Rol",
    "create_and_invite": "Crear y enviar invitación",
    "invite_sent": "Invitación enviada a {email}.",
    "invite_link_console": "Correo en modo consola: comparte este enlace con la persona.",
    "manage_account": "Administrar una cuenta",
    "pick_account": "Cuenta",
    "deactivate": "Desactivar",
    "activate": "Reactivar",
    "resend_link": "Reenviar enlace",
    "change_role": "Cambiar rol",
    "done": "Listo.",
    "mail_failed": "La cuenta quedó creada pero el correo no salió: {error}. Usa “Reenviar enlace” más tarde.",
}
MAIL_INVITE = {
    "subject": "Tu acceso a Absolut Cinema",
    "text": ("Hola {name}:\n\nTe creamos una cuenta en Absolut Cinema, el tablero de cartelera de Cinemex frente a "
             "Cinépolis. Elige tu contraseña en este enlace (vale {hours} horas):\n\n{link}\n\n"
             "Si no esperabas este correo, ignóralo.\n"),
    "html": ("<p>Hola {name}:</p><p>Te creamos una cuenta en <b>Absolut Cinema</b>, el tablero de cartelera de Cinemex "
             "frente a Cinépolis. Elige tu contraseña en este enlace (vale {hours} horas):</p>"
             "<p><a href=\"{link}\">{link}</a></p><p>Si no esperabas este correo, ignóralo.</p>"),
}
MAIL_RESET = {
    "subject": "Restablecer tu contraseña de Absolut Cinema",
    "text": ("Hola {name}:\n\nPediste restablecer tu contraseña. Elige una nueva en este enlace (vale {minutes} "
             "minutos y solo una vez):\n\n{link}\n\nSi no fuiste tú, ignora este correo: tu contraseña no cambia.\n"),
    "html": ("<p>Hola {name}:</p><p>Pediste restablecer tu contraseña. Elige una nueva en este enlace (vale {minutes} "
             "minutos y solo una vez):</p><p><a href=\"{link}\">{link}</a></p>"
             "<p>Si no fuiste tú, ignora este correo: tu contraseña no cambia.</p>"),
}

# --- Explorador de datos (archive/, views/datos.py) ---
DATASET_LABEL = {
    "cinemas": "Cines y salas",
    "auditoriums": "Salas y aforo",
    "week_showtimes": "Funciones de la semana",
    "ticket_prices": "Precio del boleto",
    "concession_prices": "Dulcería en sala (Cinépolis)",
    "delivery_prices": "Dulcería a domicilio",
}
DATASET_HELP = {
    "cinemas": "Un renglón por complejo, con sus salas y butacas medidas en el plano de asientos.",
    "auditoriums": "Un renglón por sala: butacas totales y fuera de servicio según la última medición.",
    "week_showtimes": "Funciones publicadas en el rango de fechas, tal como están hoy; las cerradas dicen si se cancelaron o concluyeron.",
    "ticket_prices": "Boleto general y rango de boletos por cine, formato y tipo de día, con la fecha de la lectura.",
    "concession_prices": "Menú en línea de Cinépolis por complejo; la última lectura de cada producto.",
    "delivery_prices": "Precios de Cinemex y Cinépolis en Rappi y DiDi Food; la última lectura de cada producto por tienda.",
}
DATA_TEXT = {
    "title": "Datos",
    "lead": "Las tablas del archivo histórico, para ordenar, filtrar, buscar y descargar.",
    "dataset": "Tabla",
    "chain": "Cadena",
    "both": "Ambas",
    "cinemas": "Cines",
    "dates": "Fechas",
    "platform": "Plataforma",
    "category": "Categoría",
    "all": "Todas",
    "search": "Buscar",
    "search_help": "Parte del nombre; sin distinguir mayúsculas.",
    "only_open": "Solo funciones vigentes",
    "latest_only": "Solo la última lectura de cada producto",
    "format": "Formato",
    "day_type": "Tipo de día",
    "rows": "{n} renglones",
    "truncated": "Se muestran los primeros {n}; afina los filtros para ver el resto.",
    "download": "Descargar CSV",
    "empty": "No hay renglones con esos filtros.",
    "no_history": "El archivo histórico aún no tiene esta tabla poblada.",
}
COLUMN_LABEL.update({
    "city_id": "Plaza", "lat": "Latitud", "lng": "Longitud", "last_seen": "Última vez vista", "first_seen_at": "Publicada",
    "broken": "Fuera de servicio", "show_date": "Fecha", "starts_at": "Inicio", "language": "Idioma", "format": "Formato",
    "experience": "Experiencia", "premium_tier": "Nivel premium", "closed_at": "Cerrada", "closed_kind": "Cierre",
    "general_price": "Precio general", "fee_price": "Cargo por servicio", "sub_category": "Subcategoría",
    "promotion_type": "Promoción", "active": "Activa", "in_stock": "En existencia", "store_slug": "Tienda (clave)",
    "movie_title": "Película", "sampled_at": "Muestreado",
    "email": "Correo", "name": "Nombre", "role": "Rol", "last_login_at": "Último acceso", "created_at": "Creada",
    "pending_invite": "Invitación pendiente", "has_password": "Con contraseña", "id": "Id",
})

# --- Operaciones (scraper/health.py, archive/status.py, views/operaciones.py; solo admin) ---
# La página es para ingeniería: los nombres de tablas y logs se muestran tal cual, a diferencia del resto del tablero.
OPS_TEXT = {
    "title": "Operaciones",
    "lead": "Estado de la captura, de la base local, del archivo en PostgreSQL y de los servicios. Solo para quien opera la plataforma.",
    "window": "Ventana",
    "hours": "{n} h",
    "all_ok": "Sin problemas en las últimas {hours} h.",
    "problems": "{n} problema(s) en las últimas {hours} h:",
    "checked_at": "Revisado",
    "ok": "OK",
    "failed": "Falló",
    "never": "Nunca",
    "ago": "hace {minutes} min",
    "ago_h": "hace {hours} h",
    # Captura.
    "capture": "Captura de cartelera",
    "capture_lead": "Lo mismo que revisa scraper.health cada mañana, en vivo.",
    "signal": "Señal",
    "last_at": "Última captura",
    "last_age": "Antigüedad",
    "last_result": "Resultado",
    "last_shows": "Funciones leídas",
    "captures": "Capturas en la ventana",
    "expected": "Programadas",
    "missing": "Programadas sin captura",
    "failed_runs": "Fallidas",
    "occ_t60": "Planos T−60",
    "occ_post": "Planos post-inicio",
    "prices_7d": "Precios (7 días)",
    "concessions_8d": "Cines con dulcería (8 días)",
    "delivery_8d": "Tiendas a domicilio (8 días)",
    "calibration": "Calibración del semáforo",
    "no_snapshots": "Sin capturas",
    "none": "Ninguna",
    # Corridas.
    "runs": "Corridas recientes",
    "runs_lead": "Cada corrida de scraper.run por cadena: resultado, volumen, llamadas a la API y duración. El error literal cuando falló.",
    "runs_days": "Días",
    "runs_empty": "No hay corridas en ese rango.",
    "runs_chart_y": "Duración (s)",
    "runs_chart_x": "Captura",
    "runs_failed_legend": "Corrida fallida",
    # Postgres.
    "postgres": "Archivo histórico en PostgreSQL",
    "postgres_lead": "Conexión de solo lectura con el mismo rol que usa el tablero.",
    "pg_down": "PostgreSQL no responde: {error}",
    "latency": "Latencia",
    "server_version": "Versión",
    "database": "Base",
    "db_size": "Tamaño",
    "connections": "Conexiones abiertas",
    "server_time": "Hora del servidor",
    "tables": "Tablas del esquema public",
    "watermarks": "Marcas de agua del sync",
    # Sync.
    "sync": "Sincronización SQLite → PostgreSQL",
    "sync_lead": "Última corrida de sync.run según data/logs/sync_status.json. El rezago es lo que falta por copiar, por tabla.",
    "sync_missing": "El sync no ha corrido nunca en esta máquina (no existe sync_status.json).",
    "sync_last": "Última corrida",
    "sync_result": "Resultado",
    "sync_duration": "Duración",
    "sync_error": "Error",
    "sync_lag": "Rezago por tabla",
    "sync_counts": "Copiado en la última corrida",
    "sync_no_lag": "Sin rezago: el archivo está al día.",
    # Servidor.
    "server": "Servidor y almacenamiento",
    "server_lead": "Commit en ejecución, último despliegue y respaldo, y cuánto ocupan la base y el crudo.",
    "commit": "Commit",
    "no_git": "Sin información de git",
    "last_deploy": "Último despliegue",
    "last_backup": "Último respaldo",
    "no_line": "Sin registro en esta máquina",
    "db_file": "snapshots.db",
    "wal_file": "WAL pendiente",
    "raw_dir": "Crudo (data/raw)",
    "backups_dir": "Respaldos locales",
    "disk_free": "Espacio libre en disco",
    # Logs.
    "logs": "Registros",
    "logs_lead": "La cola de cada log de data/logs. La línea más reciente va al final.",
    "log": "Log",
    "lines": "Líneas",
    "log_empty": "Este log no existe todavía en esta máquina.",
    "log_meta": "{size} · última escritura {when}",
    # Pendiente.
    "pending": "Lo que esta página aún no ve",
    "pending_lead": "Dos señales que hoy no se registran. Se declaran en vez de estimarse.",
    "pending_items": [
        ("Cambio en scraper/store.py", "Fallos por llamada a las APIs",
         "Los reintentos de scraper/http.py no se guardan; solo queda el resultado final de cada corrida. Contar 429, 403 del WAF "
         "o timeouts por cadena pide una tabla aditiva en SQLite."),
        ("Permiso IAM cloudwatch:GetMetricData", "Métricas de la instancia RDS",
         "CPU, almacenamiento libre y conexiones vienen de CloudWatch. El servidor ya usa boto3 para SES; falta el permiso y "
         "una consulta cacheada."),
    ],
}
COLUMN_LABEL.update({
    "taken_at": "Inicio", "finished_at": "Fin", "ok": "OK", "n_shows": "Funciones", "n_cinemas": "Cines", "n_events": "Eventos",
    "calls": "Llamadas", "duration_s": "Duración (s)", "error": "Error", "table_name": "Tabla", "rows_estimate": "Filas (estimado)",
    "size_bytes": "Tamaño", "partitions": "Particiones", "source_table": "Tabla origen", "last_id": "Último id", "synced_at": "Sincronizado",
})
