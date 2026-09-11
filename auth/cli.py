"""Administración de cuentas desde la línea de comandos (así se crea el primer admin).

Uso: .venv/bin/python -m auth.cli create --email E --name N [--role admin|viewer] [--no-mail]
                               | list | reset --email E | deactivate --email E | activate --email E | prune
Siempre imprime el enlace además de enviarlo por correo; con AC_MAIL_BACKEND=console también queda en
data/logs/mail.log. Sale con 1 en error.
"""
import argparse
import sys

from . import flows, sessions, users
from .db import connect
from .errors import AuthError


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m auth.cli", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create", help="cuenta nueva con enlace de invitación")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", choices=("admin", "viewer"), default="viewer")
    p.add_argument("--no-mail", action="store_true", help="no envía correo; solo imprime el enlace")
    sub.add_parser("list", help="todas las cuentas")
    for cmd, help_ in (("reset", "enlace nuevo de restablecimiento o invitación"),
                       ("deactivate", "desactiva la cuenta y cierra sus sesiones"),
                       ("activate", "reactiva la cuenta")):
        p = sub.add_parser(cmd, help=help_)
        p.add_argument("--email", required=True)
        if cmd == "reset":
            p.add_argument("--no-mail", action="store_true")
    sub.add_parser("prune", help="borra sesiones y tokens vencidos hace más de 90 días")
    args = ap.parse_args(argv)

    with connect() as conn:
        try:
            return _run(conn, args)
        except AuthError as e:
            print(f"error: {type(e).__name__} {e}", file=sys.stderr)
            return 1


def _run(conn, args):
    if args.cmd == "create":
        user, link = flows.invite(conn, None, args.email, args.name, args.role, send_mail=not args.no_mail)
        print(f"cuenta {user['id']} {user['email']} ({user['role']})\nenlace: {link}")
    elif args.cmd == "list":
        for u in users.list_users(conn):
            state = "activa" if u["active"] else "inactiva"
            extra = " · invitación pendiente" if u["pending_invite"] else ("" if u["has_password"] else " · sin contraseña")
            last = u["last_login_at"].strftime("%Y-%m-%d %H:%M") if u["last_login_at"] else "nunca"
            print(f"{u['id']:>4}  {u['email']:<40} {u['role']:<7} {state:<9} último acceso: {last}{extra}")
    elif args.cmd == "prune":
        n_sessions, n_tokens = sessions.prune(conn)
        print(f"borradas {n_sessions} sesiones y {n_tokens} tokens")
    else:
        user = users.by_email(conn, args.email)
        if user is None:
            print(f"error: no hay cuenta con {args.email}", file=sys.stderr)
            return 1
        if args.cmd == "reset":
            print(f"enlace: {flows.resend(conn, None, user['id'], send_mail=not args.no_mail)}")
        elif args.cmd == "deactivate":
            flows.deactivate(conn, None, user["id"])
            print(f"{user['email']} desactivada")
        elif args.cmd == "activate":
            flows.activate(conn, None, user["id"])
            print(f"{user['email']} activada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
