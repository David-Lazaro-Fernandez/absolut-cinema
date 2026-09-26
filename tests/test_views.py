"""Recorrido de cada pantalla del dashboard con `streamlit.testing.v1.AppTest`: acceso (login, olvidé, restablecer),
cartelera, dulcería, independientes, datos, usuarios y operaciones, con los roles admin y viewer.

Las cuentas viven en un `app.db` temporal que crea este módulo, así que acceso y usuarios corren en cualquier máquina,
también en CI. Las páginas de datos necesitan `data/snapshots.db` real (cartelera, dulcería, datos, operaciones) y se
omiten donde no existe; independientes y datos corren además sobre una base armada con la captura grabada de las tres
cadenas (`tests/conftest.py`), así que también corren en CI. La cookie se simula parcheando `ui.session._raw_cookie`; lo único que AppTest no ejerce es el
ciclo real de la cookie en el navegador.

Las cuentas de prueba (`pytest-admin@example.test`, `pytest-viewer@example.test`) se crean una vez por corrida.
"""
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile  # noqa: E402

from scraper import config  # noqa: E402

# Base de cuentas desechable: auth.connect() la lee de config en cada llamada, también dentro de AppTest.
config.APP_DB_PATH = Path(tempfile.mkdtemp(prefix="absolut-app-")) / "app.db"

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import analytics  # noqa: E402
import auth  # noqa: E402
from analytics.labels import AUTH_TEXT, CHAIN_LABEL, DATASET_LABEL, INDEP_TEXT, OPS_TEXT  # noqa: E402
from auth import security, sessions, users  # noqa: E402
from ui import session  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")
ADMIN, VIEWER = "pytest-admin@example.test", "pytest-viewer@example.test"
PASSWORD = "contraseña-de-pruebas-123"


needs_sqlite = pytest.mark.skipif(not config.DB_PATH.exists(), reason="sin data/snapshots.db")


@pytest.fixture(scope="module")
def conn():
    c = auth.connect()
    yield c
    c.close()


def _account(conn, email, role):
    """Cuenta de prueba con contraseña conocida, activa y con el rol pedido; se crea si no existe."""
    user = users.by_email(conn, email)
    if user is None:
        user = users.create(conn, email, f"Pytest {role}", role)
    conn.execute("UPDATE account SET active = 1, role = ?, locked_until = NULL, failed_logins = 0 WHERE id = ?",
                 (role, user["id"]))
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
def test_login_page_rejects_bad_credentials(monkeypatch, admin):
    at = _run(monkeypatch)
    _clean(at)
    assert [t.label for t in at.text_input] == [AUTH_TEXT["email"], AUTH_TEXT["password"]]
    at.text_input[0].set_value(ADMIN).run()
    at.text_input[1].set_value("incorrecta").run()
    at.button[0].click().run()
    _clean(at)
    assert [e.value for e in at.error] == [AUTH_TEXT["InvalidCredentials"]]


def test_login_page_accepts_good_credentials(monkeypatch, admin):
    at = _run(monkeypatch)
    at.text_input[0].set_value(ADMIN).run()
    at.text_input[1].set_value(PASSWORD).run()
    at.button[0].click().run()
    _clean(at)
    assert not at.error
    assert any(AUTH_TEXT["continue"] in m.value for m in at.markdown)   # el iframe puso la cookie y quedó el enlace de respaldo


def test_forgot_page_answers_the_same_for_any_email(monkeypatch, conn):
    at = _run(monkeypatch, page="olvide")
    _clean(at)
    at.text_input[0].set_value("nadie@example.test").run()
    at.button[0].click().run()
    _clean(at)
    assert [s.value for s in at.success] == [AUTH_TEXT["forgot_done"]]


def test_reset_page_with_bad_token(monkeypatch):
    at = _run(monkeypatch, page="restablecer", query={"token": "basura"})
    _clean(at)
    assert [e.value for e in at.error] == [AUTH_TEXT["TokenInvalid"]]
    at = _run(monkeypatch, page="restablecer")
    assert [e.value for e in at.error] == [AUTH_TEXT["token_missing"]]


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
def test_cartelera_for_admin(monkeypatch, conn, admin):
    at = _run(monkeypatch, cookie=_cookie(conn, admin))
    _clean(at)
    assert [b.label for b in at.sidebar.button] == [AUTH_TEXT["logout"]]
    assert len(at.dataframe) > 0


@needs_sqlite
def test_dulceria_for_viewer(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="dulceria")
    _clean(at)
    assert len(at.dataframe) > 0


@needs_sqlite
@pytest.mark.parametrize("dataset", list(DATASET_LABEL))
def test_datos_each_dataset(monkeypatch, conn, viewer, dataset):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="datos")
    at.sidebar.selectbox(key="dataset").set_value(dataset).run()
    _clean(at)
    assert len(at.dataframe) == 1 or at.info   # tabla con datos, o el aviso de "sin renglones"


@needs_sqlite
def test_datos_filters_apply(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="datos")
    at.sidebar.selectbox(key="dataset").set_value("week_showtimes").run()
    total = len(at.dataframe[0].value)
    at.sidebar.radio(key="chain").set_value("cinemex").run()
    _clean(at)
    assert len(at.dataframe[0].value) <= total
    assert set(at.dataframe[0].value["Cadena"]) <= {"Cinemex"}   # el botón de descarga no lo expone AppTest


@needs_sqlite
def test_independientes_for_viewer(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="independientes")
    _clean(at)


def _to_tomorrow(db):
    """Mueve la cartelera grabada a mañana, conservando la hora, para que la página la cuente sin congelar el reloj."""
    tomorrow = date.fromisoformat(analytics.today()) + timedelta(days=1)
    for r in db.execute("SELECT chain, show_id, date, datetime_local, datetime_utc FROM current_showtime").fetchall():
        delta = tomorrow - date.fromisoformat(r[2])
        db.execute("UPDATE current_showtime SET date = ?, datetime_local = ?, datetime_utc = ? WHERE chain = ? AND show_id = ?",
                   (tomorrow.isoformat(), (datetime.fromisoformat(r[3]) + delta).isoformat(),
                    (datetime.fromisoformat(r[4]) + delta).isoformat(), r[0], r[1]))


@pytest.fixture
def recorded_db(capture_db, tmp_path, monkeypatch):
    """`config.DB_PATH` apuntando a una base con la captura grabada de las tres cadenas, con Cinemex mudado a CDMX,
    Cinépolis a Guadalajara y la cartelera movida a mañana. Vacía la caché de Streamlit antes y después para no mezclar bases entre pruebas."""
    mem = capture_db("cinemex", "cinepolis", "cineteca")
    mem.execute("UPDATE current_showtime SET city_id = '15' WHERE chain = 'cinemex'")
    mem.execute("UPDATE cinema SET city_id = '15' WHERE chain = 'cinemex'")
    mem.execute("UPDATE current_showtime SET city_id = 'guadalajara' WHERE chain = 'cinepolis'")
    mem.execute("UPDATE cinema SET city_id = 'guadalajara' WHERE chain = 'cinepolis'")
    _to_tomorrow(mem)
    mem.commit()                                        # backup() espera sin fin a una transacción abierta
    path = tmp_path / "snapshots.db"
    with sqlite3.connect(path) as dst:
        mem.backup(dst)
    monkeypatch.setattr(config, "DB_PATH", path)
    st.cache_data.clear()
    yield path
    st.cache_data.clear()


def test_independientes_with_recorded_capture(monkeypatch, conn, viewer, recorded_db):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="independientes")
    at.sidebar.radio(key="indep_period").set_value(INDEP_TEXT["period_tomorrow"]).run()
    _clean(at)
    assert len(at.dataframe) >= 2                       # sedes y cartelera completa
    assert INDEP_TEXT["ocupacion_pending"] in [i.value for i in at.info]
    at.sidebar.radio(key="plaza").set_value("gdl").run()
    _clean(at)
    assert [i.value for i in at.info] == [INDEP_TEXT["no_plaza"]]


def test_datos_with_the_cineteca(monkeypatch, conn, viewer, recorded_db):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="datos")
    at.sidebar.selectbox(key="dataset").set_value("cinemas").run()
    _clean(at)
    at.sidebar.radio(key="chain").set_value("cineteca").run()
    _clean(at)
    assert set(at.dataframe[0].value["Cadena"]) == {CHAIN_LABEL["cineteca"]}


def test_usuarios_for_admin_lists_and_rejects_duplicate(monkeypatch, conn, admin, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, admin), page="usuarios")
    _clean(at)
    table = at.dataframe[0].value
    assert {ADMIN, VIEWER} <= set(table["Correo"])
    at.text_input[0].set_value("Duplicado").run()
    at.text_input[1].set_value(VIEWER).run()
    at.button[0].click().run()
    assert [e.value for e in at.error] == [AUTH_TEXT["DuplicateEmail"]]


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
def test_viewer_cannot_open_usuarios(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="usuarios")
    _clean(at)
    assert AUTH_TEXT["create_and_invite"] not in [b.label for b in at.button]
    assert len(at.dataframe) > 1                          # cayó en la cartelera


@needs_sqlite
def test_operaciones_for_admin(monkeypatch, conn, admin):
    at = _run(monkeypatch, cookie=_cookie(conn, admin), page="operaciones")
    _clean(at)
    assert at.success or at.warning                       # el veredicto de scraper.health, en un sentido o en otro
    assert len(at.dataframe) >= 2                         # trabajos y corridas
    assert at.slider(key="job_days")                      # la sección de trabajos programados del registro
    assert at.code                                        # la cola del log de corridas
    at.selectbox(key="log_name").set_value("sample").run()
    _clean(at)
    assert at.code or at.info                             # cola del log de muestreo, o el aviso de que no existe aquí


@needs_sqlite
def test_viewer_cannot_open_operaciones(monkeypatch, conn, viewer):
    at = _run(monkeypatch, cookie=_cookie(conn, viewer), page="operaciones")
    _clean(at)
    assert OPS_TEXT["title"] not in "".join(m.value for m in at.markdown)
    assert len(at.dataframe) > 1                          # cayó en la cartelera


@needs_sqlite
def test_logout_revokes_session(monkeypatch, conn, admin):
    cookie = _cookie(conn, admin)
    at = _run(monkeypatch, cookie=cookie)
    at.sidebar.button(key="logout").click().run()
    _clean(at)
    assert sessions.current_session(conn, cookie) is None
