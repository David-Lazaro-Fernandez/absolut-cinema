"""Dashboard ejecutivo del piloto CDMX: Cinemex frente a Cinépolis.

Entrada de Streamlit con navegación entre páginas (`views/`). La lista de páginas depende de la sesión: sin cookie
válida solo existen entrar, olvidé mi contraseña y restablecer; con sesión, la cartelera en tres capas, la dulcería y
el explorador de datos, y para el rol admin también usuarios y operaciones. Streamlit resuelve la URL contra esa lista, así que una
ruta que no corresponde al rol cae en la página por defecto. Los helpers compartidos viven en `ui/common.py`, la
sesión en `ui/session.py`, la lógica de negocio en `analytics/` y `archive/`, las cuentas en `auth/`.

Vive en la raíz del repo a propósito: Streamlit solo recarga en caliente los módulos que están bajo la carpeta del
script, y así ui/, views/, analytics/, archive/, auth/ y scraper/ también se recargan al editarlos.

Correr:  .venv/bin/streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analytics.labels import AUTH_TEXT, OPS_TEXT  # noqa: E402
from ui import session  # noqa: E402
from ui.common import PAGE_TITLE, inject_css  # noqa: E402

st.set_page_config(page_title=PAGE_TITLE, layout="wide")
inject_css()

user = session.current_user()
if user is None:
    # Sin barra de navegación: las tres páginas se enlazan entre sí y el correo apunta a /restablecer?token=…
    st.navigation([
        st.Page("views/login.py", title=AUTH_TEXT["login_title"], default=True),
        st.Page("views/olvide.py", title=AUTH_TEXT["forgot_title"], url_path="olvide"),
        st.Page("views/restablecer.py", title=AUTH_TEXT["reset_title"], url_path="restablecer"),
    ], position="hidden").run()
else:
    pages = [
        st.Page("views/cartelera.py", title="Cartelera", icon=":material/movie:", default=True),
        st.Page("views/dulceria.py", title="Dulcería", icon=":material/fastfood:"),
        st.Page("views/datos.py", title="Datos", icon=":material/table:", url_path="datos"),
    ]
    if user["role"] == "admin":
        pages.append(st.Page("views/usuarios.py", title=AUTH_TEXT["users_title"], icon=":material/group:", url_path="usuarios"))
        pages.append(st.Page("views/operaciones.py", title=OPS_TEXT["title"], icon=":material/monitor_heart:", url_path="operaciones"))
    # El enlace del correo debe abrir aunque haya una sesión (p. ej. otra persona en el mismo navegador).
    pages.append(st.Page("views/restablecer.py", title=AUTH_TEXT["reset_title"], url_path="restablecer", visibility="hidden"))
    session.account_sidebar(user)
    # Navegación arriba en escritorio; en pantallas chicas el CSS de ui/common.py la fija abajo, al alcance del
    # pulgar (Streamlit no conoce el tamaño de pantalla del lado del servidor, así que la condición es una regla @media).
    st.navigation(pages, position="top").run()
