"""Reglas puras de auth/security.py: hash de contraseñas, tokens de un solo uso y bloqueo por intentos."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth import security  # noqa: E402

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def test_hash_and_verify_roundtrip_with_fresh_salt():
    h1, h2 = security.hash_password("una contraseña larga"), security.hash_password("una contraseña larga")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert security.verify_password("una contraseña larga", h1) and security.verify_password("una contraseña larga", h2)
    assert not security.verify_password("otra", h1)


def test_verify_rejects_empty_or_malformed_hash():
    assert not security.verify_password("x", None)
    assert not security.verify_password("x", "")
    assert not security.verify_password("", security.hash_password("algo"))
    assert not security.verify_password("x", "bcrypt$nada")
    assert not security.verify_password("x", "scrypt$mal")


def test_check_strength():
    assert security.check_strength("corta") == "password_short"
    assert security.check_strength("ana@cinemex.com", "Ana@Cinemex.com") == "password_is_email"
    assert security.check_strength("doce caracteres!", "ana@cinemex.com") is None


def test_token_is_single_use_and_expires():
    raw, hashed = security.new_token()
    assert security.hash_token(raw) == hashed and len(raw) >= 40
    tok = {"used_at": None, "expires_at": NOW + timedelta(minutes=1)}
    assert security.is_usable(tok, NOW)
    assert not security.is_usable({**tok, "used_at": NOW}, NOW)
    assert not security.is_usable({**tok, "expires_at": NOW}, NOW)
    assert not security.is_usable(None, NOW)


def test_lockout_starts_at_max_fails_and_lasts_lock_minutes():
    assert security.locked_until(security.MAX_FAILS - 1, NOW) is None
    until = security.locked_until(security.MAX_FAILS, NOW)
    assert until == NOW + timedelta(minutes=security.LOCK_MINUTES)
    assert security.minutes_left(until, NOW) == security.LOCK_MINUTES
    assert security.minutes_left(until, NOW + timedelta(minutes=14, seconds=30)) == 1
    assert security.minutes_left(until, until) == 0
    assert security.minutes_left(None, NOW) == 0


def test_normalize_email():
    assert security.normalize_email("  Ana@Cinemex.COM ") == "ana@cinemex.com"
    assert security.normalize_email(None) == ""
