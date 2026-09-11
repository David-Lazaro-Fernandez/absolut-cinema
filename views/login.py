"""Página de entrada: correo y contraseña. Sin sesión es la única página visible junto con "olvidé mi contraseña"
y "restablecer". Al entrar, `ui.session` pone la cookie y recarga."""
from ui import session
from ui.common import *  # noqa: F401,F403

_, col, _ = st.columns([1, 1.1, 1])
with col, st.container(key="acceso"):
    md(f'<div class="marca">Absolut <span>Cinema</span></div><p class="acceso-lead">{esc(AUTH_TEXT["login_lead"])}</p>')
    with st.form("login", border=False):
        email = st.text_input(AUTH_TEXT["email"], autocomplete="email")
        password = st.text_input(AUTH_TEXT["password"], type="password", autocomplete="current-password")
        sent = st.form_submit_button(AUTH_TEXT["enter"])
    if sent:
        session.sign_in(email, password)
    st.page_link("views/olvide.py", label=AUTH_TEXT["forgot"])
