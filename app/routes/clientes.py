from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.cliente_service import (
    atualizar_cliente,
    criar_cliente,
    listar_cidades_clientes,
    listar_clientes,
    obter_cliente,
)

bp = Blueprint("clientes", __name__, url_prefix="/clientes")

MESES = [
    ("1", "Janeiro"),
    ("2", "Fevereiro"),
    ("3", "Março"),
    ("4", "Abril"),
    ("5", "Maio"),
    ("6", "Junho"),
    ("7", "Julho"),
    ("8", "Agosto"),
    ("9", "Setembro"),
    ("10", "Outubro"),
    ("11", "Novembro"),
    ("12", "Dezembro"),
]


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_clientes", ("busca", "cidade", "mes_aniversario")
    )
    with get_session(get_engine()) as db:
        itens = listar_clientes(
            db,
            busca=filtros["busca"],
            cidade=filtros["cidade"],
            mes_aniversario=filtros["mes_aniversario"],
        )
        cidades = listar_cidades_clientes(db)
    return render_template(
        "clientes/lista.html",
        itens=itens,
        filtros=filtros,
        cidades=cidades,
        meses=MESES,
    )


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    erro = None
    dados = {
        "nome": "",
        "whatsapp": "",
        "email": "",
        "cidade": "",
        "aniversario": "",
        "observacoes": "",
    }
    if request.method == "POST":
        dados = {k: request.form.get(k, "") for k in dados}
        with get_session(get_engine()) as db:
            try:
                criar_cliente(db, dados, usuario_id=current_user_id())
                flash("Cliente cadastrado com sucesso.", "ok")
                return redirect(url_for("clientes.listar"))
            except ValueError as exc:
                erro = str(exc)
    return render_template(
        "clientes/form.html", cliente=None, dados=dados, erro=erro
    ), (400 if erro else 200)


@bp.route("/<int:cliente_id>/editar", methods=["GET", "POST"])
def editar(cliente_id: int):
    erro = None
    with get_session(get_engine()) as db:
        cliente = obter_cliente(db, cliente_id)
        if cliente is None:
            flash("Cliente não encontrado.", "danger")
            return redirect(url_for("clientes.listar"))

        dados = {
            "nome": cliente.nome,
            "whatsapp": cliente.whatsapp or "",
            "email": cliente.email,
            "cidade": cliente.cidade,
            "aniversario": cliente.aniversario,
            "observacoes": cliente.observacoes,
        }
        if request.method == "POST":
            dados = {k: request.form.get(k, "") for k in dados}
            try:
                atualizar_cliente(db, cliente_id, dados, usuario_id=current_user_id())
                flash("Cliente atualizado com sucesso.", "ok")
                return redirect(url_for("clientes.listar"))
            except ValueError as exc:
                erro = str(exc)

    return render_template(
        "clientes/form.html", cliente=cliente, dados=dados, erro=erro
    ), (400 if erro else 200)
