from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.fornecedor_service import (
    TIPOS_FORNECEDOR,
    alternar_ativo_fornecedor,
    atualizar_fornecedor,
    criar_fornecedor,
    listar_cidades_fornecedores,
    listar_fornecedores,
    obter_fornecedor,
)
from app.utils.money import centavos_para_brl

bp = Blueprint("fornecedores", __name__, url_prefix="/fornecedores")


def _valor_reais_str(centavos: int) -> str:
    return f"{centavos / 100:.2f}".replace(".", ",")


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_fornecedores",
        ("busca", "tipo", "cidade", "ativo"),
        padroes={"ativo": "1"},
    )
    with get_session(get_engine()) as db:
        itens = listar_fornecedores(
            db,
            busca=filtros["busca"],
            tipo=filtros["tipo"],
            cidade=filtros["cidade"],
            ativo=filtros["ativo"],
        )
        cidades = listar_cidades_fornecedores(db)
    return render_template(
        "fornecedores/lista.html",
        itens=itens,
        filtros=filtros,
        tipos=TIPOS_FORNECEDOR,
        cidades=cidades,
    )


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    erro = None
    dados = {
        "nome": "",
        "tipo": "atacado",
        "contato": "",
        "whatsapp": "",
        "site": "",
        "cidade_uf": "",
        "prazo_dias": "0",
        "pedido_minimo": "0,00",
        "observacoes": "",
    }
    if request.method == "POST":
        dados = {k: request.form.get(k, "") for k in dados}
        with get_session(get_engine()) as db:
            try:
                criar_fornecedor(db, dados, usuario_id=current_user_id())
                flash("Fornecedor cadastrado com sucesso.", "ok")
                return redirect(url_for("fornecedores.listar"))
            except ValueError as exc:
                erro = str(exc)
    return render_template(
        "fornecedores/form.html",
        fornecedor=None,
        dados=dados,
        tipos=TIPOS_FORNECEDOR,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:fornecedor_id>/editar", methods=["GET", "POST"])
def editar(fornecedor_id: int):
    erro = None
    with get_session(get_engine()) as db:
        fornecedor = obter_fornecedor(db, fornecedor_id)
        if fornecedor is None:
            flash("Fornecedor não encontrado.", "danger")
            return redirect(url_for("fornecedores.listar"))

        dados = {
            "nome": fornecedor.nome,
            "tipo": fornecedor.tipo,
            "contato": fornecedor.contato,
            "whatsapp": fornecedor.whatsapp,
            "site": fornecedor.site,
            "cidade_uf": fornecedor.cidade_uf,
            "prazo_dias": str(fornecedor.prazo_dias),
            "pedido_minimo": _valor_reais_str(fornecedor.pedido_minimo_centavos),
            "observacoes": fornecedor.observacoes,
        }
        if request.method == "POST":
            dados = {k: request.form.get(k, "") for k in dados}
            try:
                atualizar_fornecedor(db, fornecedor_id, dados, usuario_id=current_user_id())
                flash("Fornecedor atualizado com sucesso.", "ok")
                return redirect(url_for("fornecedores.listar"))
            except ValueError as exc:
                erro = str(exc)

    return render_template(
        "fornecedores/form.html",
        fornecedor=fornecedor,
        dados=dados,
        tipos=TIPOS_FORNECEDOR,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:fornecedor_id>/alternar", methods=["POST"])
def alternar(fornecedor_id: int):
    with get_session(get_engine()) as db:
        try:
            f = alternar_ativo_fornecedor(db, fornecedor_id, usuario_id=current_user_id())
            estado = "reativado" if f.ativo else "inativado"
            flash(f"Fornecedor '{f.nome}' {estado}.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("fornecedores.listar"))
