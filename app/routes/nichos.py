from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.nicho_service import (
    alternar_ativo_nicho,
    atualizar_nicho,
    criar_nicho,
    listar_nichos,
    obter_nicho,
)

bp = Blueprint("nichos", __name__, url_prefix="/nichos")


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_nichos", ("busca", "ativo"), padroes={"ativo": "1"}
    )
    with get_session(get_engine()) as db:
        itens = listar_nichos(db, ativo=filtros["ativo"], busca=filtros["busca"])
    return render_template("nichos/lista.html", itens=itens, filtros=filtros)


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    erro = None
    form_data = {"nome": "", "cor": "#c2410c", "descricao": ""}
    if request.method == "POST":
        form_data = {
            "nome": request.form.get("nome", ""),
            "cor": request.form.get("cor", "#c2410c"),
            "descricao": request.form.get("descricao", ""),
        }
        with get_session(get_engine()) as db:
            try:
                criar_nicho(
                    db,
                    nome=form_data["nome"],
                    cor=form_data["cor"],
                    descricao=form_data["descricao"],
                    usuario_id=current_user_id(),
                )
                flash("Nicho criado com sucesso.", "ok")
                return redirect(url_for("nichos.listar"))
            except ValueError as exc:
                erro = str(exc)
    return render_template("nichos/form.html", nicho=None, dados=form_data, erro=erro), (
        400 if erro else 200
    )


@bp.route("/<int:nicho_id>/editar", methods=["GET", "POST"])
def editar(nicho_id: int):
    erro = None
    with get_session(get_engine()) as db:
        nicho = obter_nicho(db, nicho_id)
        if nicho is None:
            flash("Nicho não encontrado.", "danger")
            return redirect(url_for("nichos.listar"))

        dados = {
            "nome": nicho.nome,
            "cor": nicho.cor,
            "descricao": nicho.descricao,
        }
        if request.method == "POST":
            dados = {
                "nome": request.form.get("nome", ""),
                "cor": request.form.get("cor", "#c2410c"),
                "descricao": request.form.get("descricao", ""),
            }
            try:
                atualizar_nicho(
                    db,
                    nicho_id,
                    nome=dados["nome"],
                    cor=dados["cor"],
                    descricao=dados["descricao"],
                    usuario_id=current_user_id(),
                )
                flash("Nicho atualizado com sucesso.", "ok")
                return redirect(url_for("nichos.listar"))
            except ValueError as exc:
                erro = str(exc)

    return render_template("nichos/form.html", nicho=nicho, dados=dados, erro=erro), (
        400 if erro else 200
    )


@bp.route("/<int:nicho_id>/alternar", methods=["POST"])
def alternar(nicho_id: int):
    with get_session(get_engine()) as db:
        try:
            nicho = alternar_ativo_nicho(db, nicho_id, usuario_id=current_user_id())
            estado = "reativado" if nicho.ativo else "inativado"
            flash(f"Nicho '{nicho.nome}' {estado}.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("nichos.listar"))
