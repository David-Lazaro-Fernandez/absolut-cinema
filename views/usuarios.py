"""Usuarios (solo admin): quién entra al tablero y con qué rol. Crear una cuenta manda un enlace de invitación;
las demás acciones (desactivar, reactivar, cambiar rol, reenviar enlace) operan sobre una cuenta elegida."""
from ui import session
from ui.common import *  # noqa: F401,F403

me = st.session_state["auth"]["user"]
session.require_admin(me)

md(f"""
<div class="enc">
  <h1>{esc(AUTH_TEXT["users_title"])}</h1>
  <div class="meta"><span>{esc(AUTH_TEXT["users_lead"])}</span></div>
</div>
""")

users = load_auth("list_users")
if not users.empty:
    shown = users[["name", "email", "role", "active", "last_login_at", "pending_invite", "created_at"]]
    st.dataframe(pretty(shown), width="stretch", hide_index=True,
                 column_config={COLUMN_LABEL["active"]: st.column_config.CheckboxColumn(),
                                COLUMN_LABEL["pending_invite"]: st.column_config.CheckboxColumn()})

col_new, col_manage = st.columns(2, gap="large")

with col_new, seccion("nueva-cuenta"):
    md(f'<h3 class="pregunta">{esc(AUTH_TEXT["new_account"])}</h3>')
    with st.form("nueva_cuenta", clear_on_submit=True, border=False):
        name = st.text_input(AUTH_TEXT["name"])
        email = st.text_input(AUTH_TEXT["email"], autocomplete="off")
        role = st.selectbox(AUTH_TEXT["role"], options=list(ROLE_LABEL), format_func=ROLE_LABEL.get,
                            help=" ".join(f"{ROLE_LABEL[r]}: {ROLE_HELP[r]}" for r in ROLE_LABEL))
        sent = st.form_submit_button(AUTH_TEXT["create_and_invite"])
    if sent and name.strip() and email.strip():
        result = session.invite(me["id"], email, name, role)
        if result["error"]:
            st.error(result["error"])
        else:
            st.success(AUTH_TEXT["invite_sent"].format(email=esc(email.strip())))
            if result["link"]:
                st.caption(AUTH_TEXT["invite_link_console"])
                st.code(result["link"], language=None)
            if result["mail_error"]:
                st.warning(AUTH_TEXT["mail_failed"].format(error=result["mail_error"]))

with col_manage, seccion("administrar-cuenta"):
    md(f'<h3 class="pregunta">{esc(AUTH_TEXT["manage_account"])}</h3>')
    others = users[users["id"] != me["id"]] if not users.empty else users
    if others.empty:
        st.caption(AUTH_TEXT["done"])
    else:
        labels = {str(r.id): f"{r.name} · {r.email}" for r in others.itertuples()}   # claves texto: estables entre reruns
        target = int(st.selectbox(AUTH_TEXT["pick_account"], options=list(labels), format_func=labels.get, key="target_user"))
        row = others[others["id"] == target].iloc[0]
        b1, b2 = st.columns(2)
        if row["active"]:
            act = b1.button(AUTH_TEXT["deactivate"], key="deactivate", width="stretch")
        else:
            act = b1.button(AUTH_TEXT["activate"], key="activate", width="stretch")
        resend = b2.button(AUTH_TEXT["resend_link"], key="resend", width="stretch")
        # El selector lleva la cuenta en su clave: así al cambiar de cuenta arranca en el rol actual de esa cuenta y
        # el cambio solo ocurre con el botón, nunca por arrastrar el estado del selector anterior.
        r1, r2 = st.columns([3, 2])
        new_role = r1.selectbox(AUTH_TEXT["change_role"], options=list(ROLE_LABEL), format_func=ROLE_LABEL.get,
                                index=list(ROLE_LABEL).index(row["role"]), key=f"new_role_{target}", label_visibility="collapsed")
        change = r2.button(AUTH_TEXT["change_role"], key="set_role", disabled=new_role == row["role"], width="stretch")
        action = None
        if act:
            action = ("deactivate" if row["active"] else "activate", {})
        elif resend:
            action = ("resend", {})
        elif change:
            action = ("set_role", {"role": new_role})
        if action:
            result = session.manage(me["id"], target, *action)
            if result["error"]:
                st.error(result["error"])
            else:
                if result.get("link"):
                    st.caption(AUTH_TEXT["invite_link_console"])
                    st.code(result["link"], language=None)
                if result.get("mail_error"):
                    st.warning(AUTH_TEXT["mail_failed"].format(error=result["mail_error"]))
                if action[0] != "resend":
                    st.rerun()
