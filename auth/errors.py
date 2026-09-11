"""Errores de acceso. Las vistas los traducen con `analytics.labels.AUTH_TEXT[type(e).__name__]`; nunca llegan
al usuario con el texto interno."""


class AuthError(Exception):
    """Base de los errores de cuentas y sesiones."""


class InvalidCredentials(AuthError):
    """Correo o contraseña incorrectos. Se muestra igual que `AccountInactive` para no revelar cuentas."""


class AccountInactive(AuthError):
    """La cuenta existe pero está desactivada."""


class AccountLocked(AuthError):
    """Demasiados intentos fallidos; `minutes` dice cuánto falta para volver a intentar."""

    def __init__(self, minutes):
        super().__init__(f"cuenta bloqueada {minutes} min")
        self.minutes = minutes


class TokenInvalid(AuthError):
    """El enlace no existe, caducó o ya se usó."""


class WeakPassword(AuthError):
    """La contraseña no cumple la regla mínima de `auth.security.check_strength`."""


class DuplicateEmail(AuthError):
    """Ya hay una cuenta con ese correo."""


class LastAdmin(AuthError):
    """La acción dejaría el sistema sin administradores activos."""


class SelfChange(AuthError):
    """Un administrador no puede desactivarse ni cambiarse el rol a sí mismo."""


class MailFailed(AuthError):
    """La cuenta o el enlace quedaron creados pero el correo no salió; `link` permite entregarlo por otro canal."""

    def __init__(self, link, cause):
        super().__init__(str(cause))
        self.link = link
        self.cause = cause
