"""Ciclo de una cuenta sobre la base SQLite de `auth/` (un `app.db` temporal): invitar, fijar contraseña, entrar,
bloquear tras fallos, restablecer, desactivar, cerrar sesión y podar."""
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not hasattr(hashlib, "scrypt"):         # el Python del sistema de macOS no lo trae; auth/ corre en el venv
    pytest.skip("sin hashlib.scrypt", allow_module_level=True)
from auth import db, errors, flows, security, sessions, users  # noqa: E402

PASSWORD = "una-contraseña-larga-123"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "app.db")
    yield c
    c.close()


def _admin(conn):
    user, link = flows.invite(conn, None, "Admin@Test.mx", "Admin", "admin", send_mail=False)
    flows.redeem_token(conn, link.split("token=")[1], PASSWORD)
    return user


def test_invite_redeem_and_login(conn):
    user = _admin(conn)
    assert user["email"] == "admin@test.mx" and user["role"] == "admin"
    cookie, logged = flows.login(conn, "ADMIN@test.mx", PASSWORD, ip="1.2.3.4")
    assert logged["id"] == user["id"]
    assert sessions.current_session(conn, cookie)["email"] == "admin@test.mx"
    assert isinstance(users.by_id(conn, user["id"])["last_login_at"], datetime)       # las fechas vuelven como datetime


def test_a_used_invite_cannot_be_redeemed_twice(conn):
    _, link = flows.invite(conn, None, "v@test.mx", "V", send_mail=False)
    raw = link.split("token=")[1]
    flows.redeem_token(conn, raw, PASSWORD)
    with pytest.raises(errors.TokenInvalid):
        flows.redeem_token(conn, raw, PASSWORD)


def test_lockout_after_max_fails(conn):
    _admin(conn)
    for _ in range(security.MAX_FAILS):
        with pytest.raises((errors.InvalidCredentials, errors.AccountLocked)):
            flows.login(conn, "admin@test.mx", "mala")
    with pytest.raises(errors.AccountLocked):
        flows.login(conn, "admin@test.mx", PASSWORD)                                  # ni con la buena


def test_duplicate_email_and_last_admin(conn):
    admin = _admin(conn)
    with pytest.raises(errors.DuplicateEmail):
        users.create(conn, "ADMIN@test.mx", "Otra")
    viewer, _ = flows.invite(conn, admin["id"], "v@test.mx", "V", send_mail=False)
    with pytest.raises(errors.SelfChange):
        flows.set_role(conn, admin["id"], admin["id"], "viewer")
    flows.set_role(conn, admin["id"], viewer["id"], "admin")
    assert users.by_id(conn, viewer["id"])["role"] == "admin"


def test_deactivate_revokes_sessions_and_logout(conn):
    admin = _admin(conn)
    viewer, link = flows.invite(conn, admin["id"], "v@test.mx", "V", send_mail=False)
    flows.redeem_token(conn, link.split("token=")[1], PASSWORD)
    cookie, _ = flows.login(conn, "v@test.mx", PASSWORD)
    flows.deactivate(conn, admin["id"], viewer["id"])
    assert sessions.current_session(conn, cookie) is None
    with pytest.raises(errors.AccountInactive):
        flows.login(conn, "v@test.mx", PASSWORD)
    own, _ = flows.login(conn, "admin@test.mx", PASSWORD)
    flows.logout(conn, own)
    assert sessions.current_session(conn, own) is None


def test_prune_removes_only_old_closed_sessions(conn):
    admin = _admin(conn)
    old = datetime.now(timezone.utc) - timedelta(days=200)
    sessions.create(conn, admin["id"], now=old)                                   # caducó hace más de 90 días
    sessions.create(conn, admin["id"])                                            # vigente
    n_sessions, _ = sessions.prune(conn)
    assert n_sessions == 1
    assert db.one(conn, "SELECT count(*) AS n FROM session")["n"] == 1


def test_list_users_flags(conn):
    admin = _admin(conn)
    flows.invite(conn, admin["id"], "v@test.mx", "V", send_mail=False)
    out = {u["email"]: u for u in users.list_users(conn)}
    assert out["admin@test.mx"]["has_password"] is True and out["admin@test.mx"]["pending_invite"] is False
    assert out["v@test.mx"]["has_password"] is False and out["v@test.mx"]["pending_invite"] is True
