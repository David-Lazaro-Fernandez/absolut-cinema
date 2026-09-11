"""Envío de correos de acceso (invitación, restablecimiento). Dos backends elegidos por `config.MAIL_BACKEND`:
`console` escribe el correo completo en data/logs/mail.log (desarrollo: de ahí se copia el enlace) y `ses` lo manda
por Amazon SES con las credenciales del rol de la instancia (boto3 lee AWS_REGION del entorno)."""
from datetime import datetime, timezone

from scraper import config


def send(to, subject, text, html=None):
    """Envía un correo. Con `console` nunca falla; con `ses` deja pasar el error de boto3 para que la vista lo
    reporte (el token ya quedó creado y el admin puede reenviarlo)."""
    backend = _BACKENDS.get(config.MAIL_BACKEND)
    if backend is None:
        raise ValueError(f"AC_MAIL_BACKEND desconocido: {config.MAIL_BACKEND!r} (console | ses)")
    backend(to, subject, text, html)


def _console(to, subject, text, html):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(config.MAIL_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"--- {stamp} para: {to} | asunto: {subject}\n{text}\n\n")


def _ses(to, subject, text, html):
    import boto3  # solo en el servidor; el venv de desarrollo no lo necesita con el backend console

    body = {"Text": {"Data": text, "Charset": "UTF-8"}}
    if html:
        body["Html"] = {"Data": html, "Charset": "UTF-8"}
    boto3.client("ses").send_email(
        Source=config.MAIL_FROM,
        Destination={"ToAddresses": [to]},
        Message={"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body},
    )


_BACKENDS = {"console": _console, "ses": _ses}
