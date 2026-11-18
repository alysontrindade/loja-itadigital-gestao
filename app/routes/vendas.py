import json
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.db import get_session
from app.models import Cliente
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.nicho_service import listar_nichos
from app.services.venda_service import (
    CANAIS_VENDA,
    FORMAS_PAGAMENTO,
    STATUS_VENDA,
    buscar_itens_pdv,
    cancelar_venda,
    listar_vendas,
    obter_venda_detalhe,
    registrar_venda,
)

bp = Blueprint("vendas", __name__)


def _render_pdv(db, erro=None, status_code=200):
    busca = request.args.get("busca", "").strip()
    nicho_id = request.args.get("nicho_id", "").strip()
    catalogo = buscar_itens_pdv(db, busca=busca, nicho_id=nicho_id, limite=40)
    nichos = listar_nichos(db, ativo="1")
    clientes = db.query(Cliente).order_by(Cliente.nome).all()
    return (
        render_template(
            "vendas/pdv.html",
            catalogo=catalogo,
            nichos=nichos,
            clientes=clientes,
            canais=CANAIS_VENDA,
            formas=FORMAS_PAGAMENTO,
            busca=busca,
            nicho_id=nicho_id,
            erro=erro,
        ),
        status_code,
    )


@bp.route("/pdv")
def pdv():
    with get_session(get_engine()) as db:
        return _render_pdv(db)


@bp.route("/pdv/buscar")
def buscar_pdv():
    busca = request.args.get("busca", "").strip()
    nicho_id = request.args.get("nicho_id", "").strip()
    formato = request.args.get("formato", "").strip().lower()
    with get_session(get_engine()) as db:
        catalogo = buscar_itens_pdv(db, busca=busca, nicho_id=nicho_id, limite=40)

    if formato == "json" or "application/json" in request.headers.get("Accept", ""):
        return jsonify(catalogo)

    return render_template("vendas/_pdv_resultados.html", catalogo=catalogo)


@bp.route("/pdv/finalizar", methods=["POST"])
def finalizar_pdv():
    raw_itens = request.form.get("itens_json", "[]")
    with get_session(get_engine()) as db:
        try:
            itens = json.loads(raw_itens)
            if not isinstance(itens, list):
                raise ValueError("Lista de itens inválida.")
            dados = {
                "cliente_id": request.form.get("cliente_id", ""),
                "canal": request.form.get("canal", "loja"),
                "forma_pagamento": request.form.get("forma_pagamento", "pix"),
                "desconto": request.form.get("desconto", "0,00"),
                "frete": request.form.get("frete", "0,00"),
                "observacoes": request.form.get("observacoes", ""),
            }
            venda = registrar_venda(db, dados, itens, usuario_id=current_user_id())
            flash(f"Venda #{venda.id} concluída com sucesso!", "ok")
            return redirect(url_for("vendas.detalhe", venda_id=venda.id))
        except (ValueError, json.JSONDecodeError) as exc:
            msg = str(exc) if isinstance(exc, ValueError) else "Dados do carrinho inválidos."
            return _render_pdv(db, erro=msg, status_code=400)


@bp.route("/vendas")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_vendas",
        ("busca", "canal", "forma_pagamento", "status", "data_inicio", "data_fim"),
    )
    with get_session(get_engine()) as db:
        itens = listar_vendas(db, filtros)

    concluidas = [v for v in itens if v["status"] == "concluida"]
    total_faturado = sum(v["total_centavos"] for v in concluidas)
    total_lucro = sum(v["lucro_centavos"] for v in concluidas)
    return render_template(
        "vendas/lista.html",
        itens=itens,
        filtros=filtros,
        canais=CANAIS_VENDA,
        formas=FORMAS_PAGAMENTO,
        status_opcoes=STATUS_VENDA,
        qtd_concluidas=len(concluidas),
        total_faturado=total_faturado,
        total_lucro=total_lucro,
    )


@bp.route("/vendas/<int:venda_id>")
def detalhe(venda_id: int):
    with get_session(get_engine()) as db:
        info = obter_venda_detalhe(db, venda_id)
        if info is None:
            flash("Venda não encontrada.", "danger")
            return redirect(url_for("vendas.listar"))
    return render_template("vendas/detalhe.html", info=info)


@bp.route("/vendas/<int:venda_id>/cancelar", methods=["POST"])
def cancelar(venda_id: int):
    motivo = request.form.get("motivo", "").strip()
    with get_session(get_engine()) as db:
        try:
            cancelar_venda(db, venda_id, motivo=motivo, usuario_id=current_user_id())
            flash(f"Venda #{venda_id} cancelada e estoque devolvido.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("vendas.detalhe", venda_id=venda_id))
