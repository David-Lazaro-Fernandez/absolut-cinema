"""Recorrido de cada pantalla del dashboard con `streamlit.testing.v1.AppTest`: acceso (login, olvidé, restablecer),
cartelera, dulcería, datos y usuarios, con los roles admin y viewer.

Necesitan datos reales: `data/snapshots.db` para cartelera y dulcería, y el Postgres de desarrollo (esquema `app` y
archivo) para acceso, usuarios y datos. Donde falte alguno, las pruebas se omiten; en CI hoy no hay bases, así que
estas pruebas cubren la máquina de desarrollo y el servidor, no el gate de `stable`. La cookie se simula parcheando
`ui.session._raw_cookie`; lo único que AppTest no ejerce es el ciclo real de la cookie en el navegador.

Las cuentas de prueba (`pytest-admin@example.test`, `pytest-viewer@example.test`) se crean una vez y se reutilizan.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import config  # noqa: E402

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import auth  # noqa: E402
from analytics.labels import AUTH_TEXT, DATASET_LABEL  # noqa: E402
from auth import security, sessions, users  # noqa: E402
from ui import session  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")
ADMIN, VIEWER = "pytest-admin@example.test", "pytest-viewer@example.test"
PASSWORD = "contraseña-de-pruebas-123"


def _postgres_ready():
    try:
        conn = auth.connect()
    except Exception:
        return False
    try:
        auth.rows(conn, "SELECT 1 FROM app.account LIMIT 1")
        auth.rows(conn, "SELECT 1 FROM cinema LIMIT 1")
        return True
    except Exception:
        return False
    finally:
        conn.close()


needs_sqlite = pytest.mark.skipif(not config.DB_PATH.exists(), reason="sin data/snapshots.db")
needs_postgres = pytest.mark.skipif(not _postgres_ready(), reason="sin Postgres con el esquema app y el archivo")


@pytest.fixture(scope="module")
def conn():
    if not _postgres_ready():
        pytest.skip("sin Postgres")
    c = auth.connect()
    yield c
    c.close()


def _account(conn, email, role):
    """Cuenta de prueba con contraseña conocida, activa y con el rol pedido; se crea si no existe."""
    user = users.by_email(conn, email)
    if user is None:
        user = users.create(conn, email, f"Pytest {role}", role)
    with conn.cursor() as cur:
        cur.execute("UPDATE app.account SET active = true, role = %s::app.role_t, locked_until = NULL, failed_logins = 0 "
                    "WHERE id = %s", (role, user["id"]))
    users.set_password(conn, user["id"], PASSWORD)
    return users.by_id(conn, email and user["id"])


@pytest.fixture(scope="module")
def admin(conn):
    return _account(conn, ADMIN, "admin")


@pytest.fixture(scope="module")
def viewer(conn):
    return _account(conn, VIEWER, "viewer")


def _cookie(conn, user):
    return sessions.create(conn, user["id"], ip="127.0.0.1", user_agent="pytest")


def _run(monkeypatch, cookie=None, page=None, query=None):
    """Corre app.py como si el navegador trajera `cookie`, en la página pedida."""
    monkeypatch.setattr(session, "_raw_cookie", lambda: cookie)
    at = AppTest.from_file(APP, default_timeout=120)
    if page:
        at.switch_page(f"views/{page}.py")
    for k, v in (query or {}).items():
        at.query_params[k] = v
    return at.run()


def _clean(at):
    assert not at.exception, [e.message for e in at.exception]


# --- acceso ------------------------------------------------------------------------------------------
@needs_postgres
def test_login_page_rejects_bad_credentials(monkeypatch, admin):
    at = _run(monkeypatch)
    _clean(at)
    assert [t.label for t in at.text_input] == [AUTH_TEXT["email"], AUTH_TEXT["password"]]
    at.text_input[0].set_value(ADMIN).run()
    at.text_input[1].set_value("incorrecta").run()
    at.button[0].click().run()
    _clean(at)
    assert [e.value for e in at.error] == [AUTH_TEXT["InvalidCredentials"]]


@needs_postgres
def test_login_page_accepts_good_credentials(monkeypatch, admin):
    at = _run(monkeypatch)
    at.text_input[0].set_value(ADMIN).run()
    at.text_input[1].set_value(PASSWORD).run()
    at.button[0].click().run()
    _clean(at)
    assert not at.error
    assert any(AUTH_TEXT["continue"] in m.value for m in at.markdown)   # el iframe puso la cookie y quedó el enlace de respaldo


@needs_postgres
def test_forgot_page_answers_the_same_for_any_email(monkeypatch, conn):
    at = _run(monkeypatch, page="olvide")
    _clean(at)
    at.text_input[0].set_value("nadie@example.test").run()
    at.button[0].click().run()
    _clean(at)
    assert [s.value for s in at.success] == [AUTH_TEXT["forgot_done"]]


@needs_postgres
def test_reset_page_with_bad_token(monkeypatch):
    at = _run(monkeypatch, page="restablecer", query={"token": "basura"})
    _clean(at)
    assert [e.value for e in at.error] == [AUTH_TEXT["TokenInvalid"]]
    at = _run(monkeypatch, page="restablecer")
    assert [e.value for e in at.error] == [AUTH_TEXT["token_missing"]]


@needs_postgres
def test_reset_page_sets_a_new_password(monkeypatch, conn, viewer):
    link = auth.resend(conn, None, viewer["id"], send_mail=False)
    token = link.split("token=")[1]
    at = _run(monkeypatch, page="restablecer", query={"token": token})
    _clean(at)
    at.text_input[0].set_value("nueva-contraseña-larga-1").run()
    at.text_input[1].set_value("otra").run()
    at.button[0].click().run()
    assert [e.value for e in at.error] == [AUTH_TEXT["password_mismatch"]]
    at.text_input[1].set_value("nueva-contraseña-larga-1").run()
    at.button[0].click().run()
    _clean(at)
    assert [s.value for s in at.success] == [AUTH_TEXT["reset_done"]]
    assert security.verify_password("nueva-contraseña-larga-1", users.password_hash(conn, viewer["id"]))
    users.set_password(conn, viewer["id"], PASSWORD)   # deja la cuenta como la encontró


# --- páginas con sesión ------------------------------------------------------------------------------
@needs_sqlite
@needs_postgres
def test_cartelera_for_admin(monkeypatch, conn, admin):
    at = _run(monkeypatch, cookie=_cookie(conn, admin))
    _clean(at)
    assert [b.label for b in at.sidebar.button] == [AUTH_TEXT["logout"]]
    assert len(at.dataframe) > 0


@needs_sqlite
@needs_postgres
def test_dulceria_for_viewer(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="dulceria")
    _clean(at)
    assert len(at.dataframe) > 0


@needs_postgres
@pytest.mark.parametrize("dataset", list(DATASET_LABEL))
def test_datos_each_dataset(monkeypatch, conn, viewer, dataset):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="datos")
    at.sidebar.selectbox(key="dataset").set_value(dataset).run()
    _clean(at)
    assert len(at.dataframe) == 1 or at.info   # tabla con datos, o el aviso de "sin renglones"


@needs_postgres
def test_datos_filters_apply(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="datos")
    at.sidebar.selectbox(key="dataset").set_value("week_showtimes").run()
    total = len(at.dataframe[0].value)
    at.sidebar.radio(key="chain").set_value("cinemex").run()
    _clean(at)
    assert len(at.dataframe[0].value) <= total
    assert set(at.dataframe[0].value["Cadena"]) <= {"Cinemex"}   # el botón de descarga no lo expone AppTest


@needs_postgres
def test_usuarios_for_admin_lists_and_rejects_duplicate(monkeypatch, conn, admin, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, admin), page="usuarios")
    _clean(at)
    table = at.dataframe[0].value
    assert {ADMIN, VIEWER} <= set(table["Correo"])
    at.text_input[0].set_value("Duplicado").run()
    at.text_input[1].set_value(VIEWER).run()
    at.button[0].click().run()
    assert [e.value for e in at.error] == [AUTH_TEXT["DuplicateEmail"]]


@needs_postgres
def test_usuarios_role_change_is_explicit(monkeypatch, conn, admin, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, admin), page="usuarios")
    at.selectbox(key="target_user").set_value(str(viewer["id"])).run()
    assert at.button(key="set_role").disabled            # mismo rol que tiene: nada que cambiar
    at.selectbox(key=f"new_role_{viewer['id']}").set_value("admin").run()
    assert not at.button(key="set_role").disabled
    assert users.by_id(conn, viewer["id"])["role"] == "viewer"   # elegir en el selector no cambia nada por sí solo
    at.button(key="set_role").click().run()
    _clean(at)
    assert users.by_id(conn, viewer["id"])["role"] == "admin"
    auth.set_role(conn, admin["id"], viewer["id"], "viewer")


@needs_sqlite
@needs_postgres
def test_viewer_cannot_open_usuarios(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="usuarios")
    _clean(at)
    assert AUTH_TEXT["create_and_invite"] not in [b.label for b in at.button]
    assert len(at.dataframe) > 1                          # cayó en la cartelera


@needs_sqlite
@needs_postgres
def test_logout_revokes_session(monkeypatch, conn, admin):
    cookie = _cookie(conn, admin)
    at = _run(monkeypatch, cookie=cookie)
    at.sidebar.button(key="logout").click().run()
    _clean(at)
    assert sessions.current_session(conn, cookie) is None
