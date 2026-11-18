from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.models import IdeiaImpressao
from app.routes.helpers import current_user_id, get_engine, get_settings
from app.services.audit_service import registrar_auditoria
from app.services.config_service import get_config, set_config
from app.services.ideia_3d_service import (
    criar_ideia,
    listar_ideias,
    processar_ideia,
    processar_pendentes,
    sincronizar_com_google_sheets,
)

bp = Blueprint("ideias_3d", __name__, url_prefix="/ideias-3d")


@bp.route("")
def listar():
    status = request.args.get("status", "").strip()
    with get_session(get_engine()) as db:
        ideias = listar_ideias(db, status=status or None)
        webapp_url = get_config(db, "google_sheets_webapp_url", "")
    return render_template(
        "ideias_3d/lista.html",
        ideias=ideias,
        status_filtro=status,
        webapp_url=webapp_url,
    )


@bp.route("/nova", methods=["POST"])
def nova():
    termo = request.form.get("termo_ideia", "").strip()
    observacoes = request.form.get("observacoes", "").strip()
    if not termo:
        flash("Digite uma ideia de impressão 3D antes de salvar.", "warn")
        return redirect(url_for("ideias_3d.listar"))

    with get_session(get_engine()) as db:
        ideia = criar_ideia(db, termo_ideia=termo, observacoes=observacoes)
        registrar_auditoria(db, "criar", "ideia_impressao", ideia.id, f"Ideia: {termo}", current_user_id())
        db.commit()
    flash(f"Ideia '{termo}' anotada! O robô das 06h (ou o botão Processar) vai minerar preços e fatiar.", "ok")
    return redirect(url_for("ideias_3d.listar"))


@bp.route("/<int:ideia_id>/processar", methods=["POST"])
def processar_uma(ideia_id: int):
    settings = get_settings()
    modelos_dir = (settings.data_dir / "modelos_3d") if settings.testing else (settings.project_dir / "modelos_3d")
    with get_session(get_engine()) as db:
        try:
            res = processar_ideia(db, ideia_id, base_modelos_dir=modelos_dir)
            registrar_auditoria(db, "processar", "ideia_impressao", ideia_id, f"Fatiado: {res['gramas']}g", current_user_id())
            db.commit()
            flash(f"Ideia '{res['termo_ideia']}' analisada e fatiada ({res['gramas']}g estimados)!", "ok")
        except Exception as exc:
            db.rollback()
            flash(f"Erro ao processar ideia: {exc}", "err")
    return redirect(url_for("ideias_3d.listar"))


@bp.route("/processar-pendentes", methods=["POST"])
def processar_todas_pendentes():
    settings = get_settings()
    modelos_dir = (settings.data_dir / "modelos_3d") if settings.testing else (settings.project_dir / "modelos_3d")
    with get_session(get_engine()) as db:
        res = processar_pendentes(db, base_modelos_dir=modelos_dir)
        db.commit()
    if res:
        flash(f"{len(res)} ideia(s) processada(s) com pesquisa de marketplace e fatiamento!", "ok")
    else:
        flash("Nenhuma ideia pendente para processar.", "info")
    return redirect(url_for("ideias_3d.listar"))


@bp.route("/<int:ideia_id>/excluir", methods=["POST"])
def excluir(ideia_id: int):
    with get_session(get_engine()) as db:
        item = db.get(IdeiaImpressao, ideia_id)
        if item is not None:
            db.delete(item)
            db.commit()
            flash("Nota de impressão removida.", "ok")
    return redirect(url_for("ideias_3d.listar"))


@bp.route("/sincronizar", methods=["POST"])
def sincronizar():
    nova_url = request.form.get("google_sheets_webapp_url", "").strip()
    with get_session(get_engine()) as db:
        if "google_sheets_webapp_url" in request.form:
            set_config(db, "google_sheets_webapp_url", nova_url)
            db.commit()
        res = sincronizar_com_google_sheets(db, webapp_url=nova_url or None)
        db.commit()
    if res.get("ok"):
        flash(f"Sincronização Google Sheets concluída! Importadas: {res['importadas']} | Enviadas: {res['enviadas']}.", "ok")
    else:
        flash(res.get("motivo", "Falha ao sincronizar com Google Sheets."), "warn")
    return redirect(url_for("ideias_3d.listar"))
