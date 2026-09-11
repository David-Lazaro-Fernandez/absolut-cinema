"""Olvidé mi contraseña: pide el correo y manda el enlace. Responde lo mismo exista o no la cuenta."""
from ui import session
from ui.common import *  # noqa: F401,F403

_, col, _ = st.columns([1, 1.1, 1])
with col, st.container(key="acceso"):
    md(f'<div class="marca">Absolut <span>Cinema</span></div>'
       f'<h2 class="acceso-h">{esc(AUTH_TEXT["forgot_title"])}</h2><p class="acceso-lead">{esc(AUTH_TEXT["forgot_lead"])}</p>')
    if st.session_state.get("reset_sent"):
        st.success(AUTH_TEXT["forgot_done"])
    else:
        with st.form("olvide", border=False):
            email = st.text_input(AUTH_TEXT["email"], autocomplete="email")
            sent = st.form_submit_button(AUTH_TEXT["send_link"])
        if sent and email.strip():
            session.request_reset(email)
            st.session_state["reset_sent"] = True
            st.rerun()
    st.page_link("views/login.py", label=AUTH_TEXT["back_to_login"])
