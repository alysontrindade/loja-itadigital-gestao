import time
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.db import get_session
from app.services.audit_service import registrar_auditoria
from app.services.auth_service import authenticate, create_admin_user, has_admin_user
from app.services.config_service import set_config

bp = Blueprint("auth", __name__)


def _engine():
    return current_app.extensions["engine"]


@bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    with get_session(_engine()) as db:
        if has_admin_user(db):
            if session.get("user_id"):
                return redirect(url_for("main.inicio"))
            return redirect(url_for("auth.login"))

        erro = None
        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            login_nome = request.form.get("login", "").strip().lower()
            senha = request.form.get("senha", "")
            confirmar = request.form.get("confirmar_senha", "")
            nome_loja = request.form.get("nome_loja", "").strip()

            if senha != confirmar:
                erro = "As senhas informadas não coincidem."
            else:
                try:
                    usuario = create_admin_user(db, nome=nome, login=login_nome, senha=senha)
                    if nome_loja:
                        set_config(db, "nome_loja", nome_loja)
                        db.commit()
                    session["user_id"] = usuario.id
                    session["user_name"] = usuario.nome
                    session["last_activity"] = int(time.time())
                    flash("Acesso configurado com sucesso! Bem-vindo ao sistema.", "ok")
                    return redirect(url_for("main.inicio"))
                except ValueError as exc:
                    erro = str(exc)

        return render_template("auth/setup.html", erro=erro), (400 if erro else 200)


@bp.route("/login", methods=["GET", "POST"])
def login():
    with get_session(_engine()) as db:
        if not has_admin_user(db):
            return redirect(url_for("auth.primeiro_acesso"))

        if session.get("user_id"):
            return redirect(url_for("main.inicio"))

        erro = None
        if request.method == "POST":
            login_nome = request.form.get("login", "")
            senha = request.form.get("senha", "")
            resultado = authenticate(db, login_nome, senha)
            if resultado.ok and resultado.user is not None:
                session["user_id"] = resultado.user.id
                session["user_name"] = resultado.user.nome
                session["last_activity"] = int(time.time())
                return redirect(url_for("main.inicio"))
            erro = resultado.message
            return render_template("auth/login.html", erro=erro), 401

        return render_template("auth/login.html", erro=erro)


@bp.route("/logout", methods=["POST"])
def logout():
    uid = session.get("user_id")
    if uid is not None:
        with get_session(_engine()) as db:
            registrar_auditoria(
                db,
                acao="LOGOUT",
                entidade="usuario",
                entidade_id=uid,
                detalhes="Sessão encerrada pelo usuário.",
                usuario_id=uid,
            )
            db.commit()

    csrf_keep = session.get("csrf_token")
    session.clear()
    if csrf_keep:
        session["csrf_token"] = csrf_keep
    flash("Sessão encerrada com segurança.", "ok")
    return redirect(url_for("auth.login"))
