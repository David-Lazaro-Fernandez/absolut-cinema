"""Dashboard ejecutivo del piloto CDMX: Cinemex frente a Cinépolis.

Entrada de Streamlit con navegación entre páginas (`views/`): la cartelera en tres capas con sus filtros, y la
dulcería como página propia. Los helpers compartidos viven en `ui/common.py`; la lógica de negocio en `analytics/`.

Vive en la raíz del repo a propósito: Streamlit solo recarga en caliente los módulos que están bajo la carpeta del
script, y así ui/, views/, analytics/ y scraper/ también se recargan al editarlos.

Correr:  .venv/bin/streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui.common import PAGE_TITLE, inject_css  # noqa: E402

st.set_page_config(page_title=PAGE_TITLE, layout="wide")
inject_css()
# Navegación arriba en escritorio; en pantallas chicas el CSS de ui/common.py la fija abajo, al alcance del pulgar
# (Streamlit no conoce el tamaño de pantalla del lado del servidor, así que la condición es una regla @media).
st.navigation([
    st.Page("views/cartelera.py", title="Cartelera", icon=":material/movie:", default=True),
    st.Page("views/dulceria.py", title="Dulcería", icon=":material/fastfood:"),
], position="top").run()
