"""Reglas puras de seguridad: hash de contraseñas, tokens de un solo uso y bloqueo por intentos fallidos.
Sin base de datos ni red, para poder probarlas en memoria (tests/test_security.py)."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

# scrypt con los parámetros recomendados por la stdlib (n=2**14, r=8, p=1): ~50 ms por verificación, suficiente
# para un login humano y sin dependencias externas.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 12

MAX_FAILS = 10                 # intentos fallidos seguidos antes de bloquear la cuenta
LOCK_MINUTES = 15              # duración del bloqueo
RESET_TTL_MIN = 60             # vida del enlace de restablecimiento
INVITE_TTL_HOURS = 72          # vida del enlace de invitación
SESSION_TTL_DAYS = 30          # vida de la cookie; se extiende con el uso
SESSION_TOUCH_MINUTES = 60     # cada cuánto se refresca `last_seen_at` para no escribir en cada corrida
RESET_MAX_PER_HOUR = 3         # tope de enlaces de restablecimiento por cuenta y hora


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password):
    """'scrypt$n$r$p$sal$hash', todo en base64 url-safe. Cada llamada usa una sal nueva."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored):
    """True si la contraseña corresponde al hash guardado. Comparación en tiempo constante; False con hash vacío
    (cuenta invitada que aún no fijó contraseña)."""
    if not stored or not password:
        return False
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        expected = _unb64(digest)
        got = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


def check_strength(password, email=""):
    """Regla mínima para directivos: 12 caracteres y que no sea el propio correo. Devuelve None si pasa; si no,
    la clave del mensaje en `labels.AUTH_TEXT`."""
    if password is None or len(password) < MIN_PASSWORD_LENGTH:
        return "password_short"
    if email and password.strip().lower() == email.strip().lower():
        return "password_is_email"
    return None


def new_token():
    """(valor en claro para el enlace o la cookie, sha256 hex para la base). Solo el hash se guarda."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_usable(token, now=None):
    """Un token sirve si no se ha usado y no ha caducado."""
    now = now or datetime.now(timezone.utc)
    return token is not None and token.get("used_at") is None and token["expires_at"] > now


def locked_until(failed_logins, last_failed_at):
    """Instante hasta el que la cuenta queda bloqueada tras `failed_logins` fallos seguidos, o None si no aplica."""
    if failed_logins < MAX_FAILS or last_failed_at is None:
        return None
    return last_failed_at + timedelta(minutes=LOCK_MINUTES)


def minutes_left(until, now=None):
    """Minutos (redondeados hacia arriba, mínimo 1) que faltan para `until`; 0 si ya pasó."""
    now = now or datetime.now(timezone.utc)
    if until is None or until <= now:
        return 0
    return max(1, -(-int((until - now).total_seconds()) // 60))


def normalize_email(email):
    return (email or "").strip().lower()
