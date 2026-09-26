"""Textos para directivos. Cualquier cosa que se muestre a un usuario sale de aquí, no de los
nombres internos (chain, kind, franjas, buckets)."""

US = "cinemex"            # la cadena del cliente: en las frases hablamos en primera persona
THEM = "cinepolis"
COMPARED = (US, THEM)      # las cadenas del head-to-head; la Cineteca se captura pero no entra a los shares

CHAIN_LABEL = {"cinemex": "Cinemex", "cinepolis": "Cinépolis", "cineteca": "Cineteca Nacional"}

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
INDEP = "#8C8E95"          # gris medio: serie de la Cineteca, cine independiente (el centro de DIVERGING)
CHAIN_COLOR = {"cinemex": RED, "cinepolis": INK, "cineteca": INDEP}
NEUTRAL = "#C9CBD0"        # líneas de referencia (la barra del dumbbell)
GRID = "#ECEDEF"           # rejilla de gráficas
RED_RAMP = [RED_DARK, RED, "#F08497", "#F7CDD5"]                 # ordinal de un solo tono para cubetas ordenadas
DIVERGING = [INK, INDEP, "#EFEFEF", "#F6B7C2", RED]          # Cinépolis (tinta) ↔ centro ↔ Cinemex (rojo)
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
# Plazas (claves de scraper/plazas.py) y el alcance nacional (`plaza=None` en analytics). El título de la cartelera
# nombra la plaza elegida; en nacional dice "nacional".
PLAZA_LABEL = {"cdmx": "CDMX", "gdl": "Guadalajara", "mty": "Monterrey"}
NATIONAL_LABEL = "Nacional"
ZONE_TEXT = {
    "header": "Zona",
    "select": "Plaza a comparar",
    "caption": "Las participaciones se calculan solo con los cines de la plaza elegida; en Nacional entran todos los capturados.",
    "title": "Cartelera {plaza}",
    "title_national": "Cartelera nacional",
    "page_title": "Cartelera · Cinemex frente a Cinépolis",
}


def plaza_title(plaza):
    """'Cartelera CDMX' | 'Cartelera nacional', para el encabezado de la cartelera."""
    return ZONE_TEXT["title"].format(plaza=PLAZA_LABEL[plaza]) if plaza else ZONE_TEXT["title_national"]

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
    "db_unavailable": "El acceso no está disponible en este momento. Inténtalo en unos minutos.",
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

# --- Explorador de datos (analytics/datasets.py, views/datos.py) ---
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
    "city_id": "Ciudad / área", "state_id": "Estado", "plaza": "Plaza", "sample_cinema": "Cine de muestra", "timezone": "Zona horaria",
    "lat": "Latitud", "lng": "Longitud", "last_seen": "Última vez vista", "first_seen_at": "Publicada",
    "broken": "Fuera de servicio", "show_date": "Fecha", "starts_at": "Inicio", "language": "Idioma", "format": "Formato",
    "experience": "Experiencia", "premium_tier": "Nivel premium", "closed_at": "Cerrada", "closed_kind": "Cierre",
    "general_price": "Precio general", "fee_price": "Cargo por servicio", "sub_category": "Subcategoría",
    "promotion_type": "Promoción", "active": "Activa", "in_stock": "En existencia", "store_slug": "Tienda (clave)",
    "movie_title": "Película", "sampled_at": "Muestreado",
    "email": "Correo", "name": "Nombre", "role": "Rol", "last_login_at": "Último acceso", "created_at": "Creada",
    "pending_invite": "Invitación pendiente", "has_password": "Con contraseña", "id": "Id",
})

# --- Oferta independiente (analytics/independents.py, views/independientes.py) ---
INDEP_TEXT = {
    "nav": "Independientes",
    "title": "Oferta independiente: la <span>Cineteca Nacional</span>",
    "meta_zone": "Zona",
    "meta_zone_value": "CDMX (sus tres sedes)",
    "meta_period": "Periodo",
    "meta_note": "Fuera de los shares frente a Cinépolis: cine de autor, un solo precio",
    "no_db": "Aún no hay datos: la base no existe todavía. Ver la página de cartelera.",
    "no_plaza": "La Cineteca solo tiene sedes en CDMX. Elige CDMX o Nacional en la zona para ver su oferta.",
    "no_data": "No hay cartelera de la Cineteca publicada para {period}. Se captura con la cartelera, tres veces al día.",
    "period_header": "Periodo",
    "period_today": "Hoy",
    "period_tomorrow": "Mañana",
    "period_week": "Resto de la semana de cine (hasta el {d1})",
    "period_pick": "Elegir fechas",
    "period_range": "Del … al …",
    "period_caption": "La Cineteca publica su cartelera hasta el miércoles de la semana en curso.",
    "layer1": "Lo que importa hoy",
    "layer1_desc": "El hallazgo de la oferta independiente, si cruza su umbral; el mismo que aparece en la cartelera.",
    "layer1_none": "Ningún título de la Cineteca cruza el umbral: llenar {pct} % de sus butacas en al menos {n} funciones medidas sin que lo exhibamos en CDMX.",
    "layer1_pending": "El hallazgo se enciende cuando la lectura de los planos de la Cineteca esté confirmada con una función llena.",
    "layer2": "Evidencia",
    "layer2_desc": "Qué programa, cuánto se llena, cuánto se parece a nuestra cartelera y a qué horas.",
    "q_programa": "¿Qué programa la Cineteca en este periodo?",
    "q_ocupacion": "¿Cuánto se llena?",
    "q_solape": "¿Compite con nuestra cartelera?",
    "q_franjas": "¿A qué horas programa?",
    "programa_chart": "Títulos con más funciones, en % de su programación",
    "programa_note": "Cada sede cuenta sus funciones; el título agrupa las versiones doblada y subtitulada.",
    "ocupacion_pending": "Pendiente: la lectura del plano de asientos de la Cineteca aún no se confirma con una función llena. "
                         "Se desbloquea al comparar el % vendido de una función agotada contra lo que muestra su sitio; "
                         "los planos ya se guardan y se recalculan sin volver a pedirlos.",
    "ocupacion_few": "Pendiente: hay {n} funciones medidas de la Cineteca en la última semana; hacen falta {min} para leer su ocupación.",
    "ocupacion_chart": "% de butacas vendidas por sede y franja, última semana",
    "ocupacion_titles": "Títulos con más ocupación",
    "solape_chart": "Sus títulos con más funciones, según si también los exhibimos en CDMX",
    "solape_only": "Solo en la Cineteca: la oportunidad",
    "franjas_chart": "% de la programación de cada cadena por franja",
    "status": {"shared": "También en Cinemex", "indep_only": "Solo en la Cineteca"},
    "leer_programa": "Cada barra es la parte de las funciones de la Cineteca en el periodo que se lleva un título, sumando sus tres "
                     "sedes (Chapultepec, de las Artes y México). La Cineteca marca el idioma en el título (DOB, SUB); aquí se agrupan "
                     "las versiones de una misma película. \"Lengua original\" son las funciones sin marca de idioma, lo normal en su "
                     "cartelera. Para hoy solo se cuentan funciones que aún no empiezan.",
    "leer_ocupacion": "La ocupación se lee del plano de asientos de cada función entre 15 y 75 minutos después de empezar: la "
                      "asistencia final. Se pondera por butacas, así una sala grande pesa más. La sala sale del plano, no de la "
                      "cartelera, que no la publica.",
    "leer_solape": "Una película de la Cineteca cuenta como \"También en Cinemex\" si en el mismo periodo tenemos al menos una función "
                   "de ella en algún cine de CDMX. Las películas se emparejan por título con las mismas reglas que Cinemex y "
                   "Cinépolis. Mucho cine de autor no tiene pareja en nuestra cartelera: es el dato, no un error.",
    "leer_franjas": "Cada barra es la parte de la programación de cada cadena que empieza en esa franja, en % de sus propias "
                    "funciones del periodo: la Cineteca contra Cinemex en CDMX. No se compara con Cinépolis ni entra a los shares "
                    "de la cartelera.",
    "layer3": "Apéndice",
    "layer3_desc": "La cartelera completa del periodo, el aforo de sus salas y lo que aún no se captura.",
    "app_board": "Cartelera completa del periodo",
    "app_board_summary": "{titles} títulos · {shows} funciones",
    "app_capacity": "Aforo por sala",
    "app_capacity_summary": "{screens} salas medidas en {cinemas} sedes",
    "app_capacity_empty": "Aún no hay salas medidas: el aforo sale del plano de las funciones que ya empezaron.",
    "app_pending": "Pendientes",
    "app_pending_summary": "precio del boleto y sala en la cartelera",
    "pending_items": [
        "**Precio del boleto.** No se captura todavía. El boleto general está en la página de compra de la Cineteca, que pide "
        "una cookie de sesión; se desbloquea al darle manejo de cookies a la captura o al verificar el servicio de boletos "
        "de su taquilla en línea. Sin cifra hasta capturarlo.",
        "**Sala en la cartelera.** La cartelera pública no dice en qué sala es cada función; la sala solo llega del plano de "
        "asientos, así que el aforo ofertado por título no se puede calcular como en las cadenas.",
    ],
    "back": "Volver a la cartelera",
    "link": "Ver la oferta independiente: qué programa y cuánto llena la Cineteca",
    "footer": "Fuentes: cartelera pública de la Cineteca Nacional (sedes Chapultepec, de las Artes y México), capturada con la "
              "cartelera de las cadenas tres veces al día; ocupación leída del plano de asientos de cada función después de "
              "empezar. La Cineteca no entra a los shares de Cinemex frente a Cinépolis. Historia desde el {first}.",
}
COLUMN_LABEL.update({
    "shows_indep": "Funciones Cineteca", "share_indep": "% programación Cineteca", "shows_vs": "Funciones Cinemex CDMX",
    "cinemas_vs": "Cines Cinemex CDMX", "subtitled": "Subtituladas", "spanish": "En español", "other": "Lengua original",
    "first_date": "Desde", "last_date": "Hasta", "slot": "Franja", "days": "Días", "share": "% de funciones",
})

# --- Operaciones (scraper/health.py, views/operaciones.py; solo admin) ---
# La página es para ingeniería: los nombres de tablas y logs se muestran tal cual, a diferencia del resto del tablero.
OPS_TEXT = {
    "title": "Operaciones",
    "lead": "Estado de la captura, de las bases SQLite y de los servicios. Solo para quien opera la plataforma.",
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
    "last_cinemas": "Cines leídos (máximo 7 días)",
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
    # Registro por geografía.
    "coverage": "Cobertura por ciudad y área",
    "coverage_lead": "Funciones vigentes y cines por cadena y llave geográfica de cada API (Cinépolis ciudad, Cinemex área), con la "
                     "plaza a la que pertenecen. Es el registro para decidir qué plazas entran al muestreo de planos (AC_SEATS_PLAZAS).",
    "coverage_seats": "Planos de asientos acotados a: {plazas}",
    "coverage_no_plaza": "—",
    # Trabajos programados (jobs/registry.py y data/logs/jobs.jsonl).
    "jobs": "Trabajos programados",
    "jobs_lead": "Cada trabajo del registro (jobs/registry.py) con su horario y lo que dejó jobs.run en data/logs/jobs.jsonl: "
                 "última corrida, fallos y el pico de memoria del paso más pesado. Sin corridas en la ventana, el trabajo no ha "
                 "pasado por jobs.run en esta máquina.",
    "jobs_days": "Días",
    "jobs_status": {"ok": "OK", "failed": "Falló", "timeout": "Tope de tiempo", "skipped": "Ya corría"},
    "jobs_off": "Apagado",
    # Corridas.
    "runs": "Corridas recientes",
    "runs_lead": "Cada corrida de scraper.run por cadena: resultado, volumen, llamadas a la API y duración. El error literal cuando falló.",
    "runs_days": "Días",
    "runs_empty": "No hay corridas en ese rango.",
    "runs_chart_y": "Duración (s)",
    "runs_chart_x": "Captura",
    "runs_failed_legend": "Corrida fallida",
    # Unidades de captura (scraper/units.py, tabla snapshot_unit).
    "units": "Unidades de captura",
    "units_lead": "Cada captura se descarga por partes que fallan por separado: Cinemex por estado de su API, Cinépolis por lotes "
                  "de hasta 30 cines agrupados por estado. Una unidad que falla conserva la cartelera anterior de sus cines "
                  "(columna Conservadas) y no genera cambios. Las que fallaron recientemente van primero.",
    "units_empty": "Sin capturas por unidades en ese rango (existen desde el 2026-09-25).",
    "units_failed_now": "Falló en la última captura",
    # Servidor.
    "server": "Servidor y almacenamiento",
    "server_lead": "Commit en ejecución, último despliegue y respaldo, y cuánto ocupan las bases y el crudo.",
    "commit": "Commit",
    "no_git": "Sin información de git",
    "last_deploy": "Último despliegue",
    "last_backup": "Último respaldo",
    "no_line": "Sin registro en esta máquina",
    "db_file": "snapshots.db",
    "wal_file": "WAL pendiente",
    "app_db_file": "app.db (cuentas y sesiones)",
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
    "calls": "Llamadas", "duration_s": "Duración (s)", "error": "Error", "table_name": "Tabla",
    "size_bytes": "Tamaño",
    "key": "Trabajo", "area": "Área", "schedule": "Horario", "timeout_min": "Tope (min)", "last_started_at": "Última corrida",
    "last_status": "Resultado", "last_duration_s": "Duración (s)", "last_max_rss_mb": "Memoria (MB)", "runs": "Corridas",
    "failures": "Fallidas", "peak_rss_mb": "Memoria pico (MB)",
    "unit": "Unidad", "label": "Alcance", "last_at": "Última captura", "last_ok": "OK", "last_error": "Último error",
    "avg_calls": "Llamadas (media)", "avg_duration_s": "Duración media (s)", "avg_shows": "Funciones (media)",
})
