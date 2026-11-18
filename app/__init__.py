import time
from typing import Any, Mapping
from flask import Flask, flash, redirect, request, session, url_for

from app.config import build_settings
from app.db import get_session, init_db
from app.routes import (
    auth,
    clientes,
    compras,
    estoque,
    extras,
    fornecedores,
    ideias_3d,
    kits,
    main,
    nichos,
    produtos,
    relatorios,
    vendas,
)
from app.security import ensure_csrf_token, validate_csrf_or_abort
from app.services.auth_service import has_admin_user
from app.services.backup_service import list_backups
from app.services.config_service import get_all_config
from app.services.estoque_service import contar_estoque_critico
from app.utils.money import centavos_para_brl


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    """Fábrica principal da aplicação Flask local da Loja Itamarandiba."""
    settings = build_settings(test_config)
    engine = init_db(settings)

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "loja_itamarandiba_sess"
    app.config["TESTING"] = settings.testing
    app.config["LOJA_SETTINGS"] = settings
    app.extensions["engine"] = engine

    app.jinja_env.filters["brl"] = centavos_para_brl

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(nichos.bp)
    app.register_blueprint(fornecedores.bp)
    app.register_blueprint(clientes.bp)
    app.register_blueprint(produtos.bp)
    app.register_blueprint(kits.bp)
    app.register_blueprint(compras.bp)
    app.register_blueprint(estoque.bp)
    app.register_blueprint(vendas.bp)
    app.register_blueprint(relatorios.bp)
    app.register_blueprint(extras.bp)
    app.register_blueprint(ideias_3d.bp)

    @app.before_request
    def _proteger_requisicao():
        if request.endpoint == "static" or request.endpoint == "main.health":
            return None

        ensure_csrf_token()
        validate_csrf_or_abort()

        with get_session(app.extensions["engine"]) as db:
            existe_admin = has_admin_user(db)
            if not existe_admin:
                if request.endpoint != "auth.primeiro_acesso":
                    return redirect(url_for("auth.primeiro_acesso"))
                return None

            if request.endpoint == "auth.login":
                return None

            if request.endpoint == "auth.primeiro_acesso":
                if session.get("user_id"):
                    return redirect(url_for("main.inicio"))
                return redirect(url_for("auth.login"))

            if not session.get("user_id"):
                return redirect(url_for("auth.login"))

            cfg = get_all_config(db)
            try:
                timeout_min = max(1, int(cfg.get("sessao_expira_minutos", settings.session_timeout_minutes)))
            except ValueError:
                timeout_min = settings.session_timeout_minutes

            agora = int(time.time())
            ultima_atividade = session.get("last_activity")
            if ultima_atividade is not None and (agora - int(ultima_atividade)) > timeout_min * 60:
                csrf_keep = session.get("csrf_token")
                session.clear()
                if csrf_keep:
                    session["csrf_token"] = csrf_keep
                flash("Sua sessão expirou por inatividade. Entre novamente.", "warn")
                return redirect(url_for("auth.login"))

            session["last_activity"] = agora
        return None

    @app.context_processor
    def _injetar_globais():
        with get_session(app.extensions["engine"]) as db:
            cfg = get_all_config(db)
            estoque_critico_count = contar_estoque_critico(db)
        backups = list_backups(settings.backup_dir)
        backup_recente = backups[0] if backups else None
        return {
            "csrf_token": ensure_csrf_token,
            "cfg": cfg,
            "usuario_nome": session.get("user_name"),
            "backup_recente": backup_recente,
            "estoque_critico_count": estoque_critico_count,
        }

    return app
