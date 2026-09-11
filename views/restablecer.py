"""Fijar una contraseña nueva desde el enlace del correo (`?token=`). Sirve para aceptar una invitación y para
restablecer; el texto cambia según el propósito del enlace. Funciona con o sin sesión abierta."""
from ui import session
from ui.common import *  # noqa: F401,F403

token = st.query_params.get("token")
info = session.peek_token(token) if token else None

_, col, _ = st.columns([1, 1.1, 1])
with col, st.container(key="acceso"):
    md('<div class="marca">Absolut <span>Cinema</span></div>')
    if st.session_state.get("password_saved"):
        st.success(AUTH_TEXT["reset_done"])
        st.page_link("views/login.py", label=AUTH_TEXT["back_to_login"])
    elif info is None:
        st.error(AUTH_TEXT["token_missing"] if not token else AUTH_TEXT["TokenInvalid"])
        st.page_link("views/olvide.py", label=AUTH_TEXT["forgot_title"])
    else:
        title = AUTH_TEXT["invite_title"] if info["purpose"] == "invite" else AUTH_TEXT["reset_title"]
        md(f'<h2 class="acceso-h">{esc(title)}</h2>'
           f'<p class="acceso-lead">{esc(AUTH_TEXT["reset_lead"].format(email=info["email"]))}</p>')
        with st.form("restablecer", border=False):
            p1 = st.text_input(AUTH_TEXT["password"], type="password", autocomplete="new-password")
            p2 = st.text_input(AUTH_TEXT["password_confirm"], type="password", autocomplete="new-password")
            sent = st.form_submit_button(AUTH_TEXT["save_password"])
        if sent:
            if p1 != p2:
                st.error(AUTH_TEXT["password_mismatch"])
            else:
                problem = session.redeem_token(token, p1)
                if problem:
                    st.error(problem)
                else:
                    st.query_params.clear()
                    st.session_state["password_saved"] = True
                    st.rerun()
