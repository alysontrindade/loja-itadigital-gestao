from datetime import date
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.models import Produto
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.compra_service import (
    STATUS_COMPRA,
    cancelar_compra,
    criar_compra,
    listar_compras,
    obter_compra_detalhe,
    receber_compra,
)
from app.services.fornecedor_service import listar_fornecedores

bp = Blueprint("compras", __name__, url_prefix="/compras")


def _extrair_itens_compra() -> list[dict[str, str]]:
    pids = request.form.getlist("produto_id")
    qtds = request.form.getlist("quantidade")
    custos = request.form.getlist("custo_unit")
    itens = []
    for idx, pid in enumerate(pids):
        pid_clean = (pid or "").strip()
        if not pid_clean:
            continue
        qtd = qtds[idx].strip() if idx < len(qtds) and qtds[idx].strip() else "1"
        custo = custos[idx].strip() if idx < len(custos) and custos[idx].strip() else "0,00"
        itens.append({"produto_id": pid_clean, "quantidade": qtd, "custo_unit": custo})
    return itens


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_compras",
        ("fornecedor_id", "status", "data_inicio", "data_fim"),
    )
    with get_session(get_engine()) as db:
        itens = listar_compras(db, filtros)
        fornecedores = listar_fornecedores(db, ativo="todos")
    return render_template(
        "compras/lista.html",
        itens=itens,
        filtros=filtros,
        fornecedores=fornecedores,
        status_opcoes=STATUS_COMPRA,
    )


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    erro = None
    dados = {
        "fornecedor_id": "",
        "data": date.today().isoformat(),
        "frete": "0,00",
        "impostos": "0,00",
        "outros_custos": "0,00",
        "observacoes": "",
        "receber_agora": "0",
        "atualizar_custo_produto": "1",
    }
    itens_form = [{"produto_id": "", "quantidade": "1", "custo_unit": "0,00"}]

    with get_session(get_engine()) as db:
        fornecedores = listar_fornecedores(db, ativo="1")
        produtos = db.query(Produto).filter(Produto.ativo == 1).order_by(Produto.nome).all()

        if request.method == "POST":
            dados = {
                "fornecedor_id": request.form.get("fornecedor_id", ""),
                "data": request.form.get("data", date.today().isoformat()),
                "frete": request.form.get("frete", "0,00"),
                "impostos": request.form.get("impostos", "0,00"),
                "outros_custos": request.form.get("outros_custos", "0,00"),
                "observacoes": request.form.get("observacoes", ""),
                "receber_agora": "1" if request.form.get("receber_agora") == "1" else "0",
                "atualizar_custo_produto": (
                    "1" if request.form.get("atualizar_custo_produto", "1") == "1" else "0"
                ),
            }
            extraidos = _extrair_itens_compra()
            itens_form = extraidos or itens_form
            try:
                compra = criar_compra(
                    db,
                    fornecedor_id=dados["fornecedor_id"] or None,
                    itens=extraidos,
                    frete=dados["frete"],
                    impostos=dados["impostos"],
                    outros_custos=dados["outros_custos"],
                    observacoes=dados["observacoes"],
                    data=dados["data"],
                    receber_agora=dados["receber_agora"] == "1",
                    atualizar_custo_produto=dados["atualizar_custo_produto"] == "1",
                    usuario_id=current_user_id(),
                )
                msg = (
                    f"Compra #{compra.id} registrada e lançada no estoque!"
                    if compra.status == "recebida"
                    else f"Pedido de compra #{compra.id} criado em aberto."
                )
                flash(msg, "ok")
                return redirect(url_for("compras.detalhe", compra_id=compra.id))
            except ValueError as exc:
                erro = str(exc)

    return render_template(
        "compras/form.html",
        dados=dados,
        itens_form=itens_form,
        fornecedores=fornecedores,
        produtos=produtos,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:compra_id>")
def detalhe(compra_id: int):
    with get_session(get_engine()) as db:
        info = obter_compra_detalhe(db, compra_id)
        if info is None:
            flash("Pedido de compra não encontrado.", "danger")
            return redirect(url_for("compras.listar"))
    return render_template("compras/detalhe.html", info=info)


@bp.route("/<int:compra_id>/receber", methods=["POST"])
def receber(compra_id: int):
    atualizar_custo = request.form.get("atualizar_custo_produto", "1") != "0"
    with get_session(get_engine()) as db:
        try:
            receber_compra(
                db,
                compra_id,
                atualizar_custo_produto=atualizar_custo,
                usuario_id=current_user_id(),
            )
            flash("Compra recebida! Estoque e custos dos itens atualizados.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("compras.detalhe", compra_id=compra_id))


@bp.route("/<int:compra_id>/cancelar", methods=["POST"])
def cancelar(compra_id: int):
    with get_session(get_engine()) as db:
        try:
            cancelar_compra(db, compra_id, usuario_id=current_user_id())
            flash("Pedido de compra cancelado.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("compras.detalhe", compra_id=compra_id))
