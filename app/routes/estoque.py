from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.models import Produto
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.estoque_service import (
    ORIGENS_LABEL,
    TIPOS_AJUSTE_MANUAL,
    TIPOS_MOVIMENTO,
    ajustar_estoque_manual,
    contar_estoque_critico,
    listar_movimentos,
    listar_posicao_estoque,
)
from app.services.nicho_service import listar_nichos

bp = Blueprint("estoque", __name__, url_prefix="/estoque")


def _render_posicao(db, filtros, erro=None, ajuste_dados=None, status_code=200):
    itens = listar_posicao_estoque(
        db,
        busca=filtros["busca"],
        status=filtros["status"],
        nicho_id=filtros["nicho_id"],
    )
    nichos = listar_nichos(db, ativo="1")
    produtos = db.query(Produto).filter(Produto.ativo == 1).order_by(Produto.nome).all()
    criticos = contar_estoque_critico(db)
    total_custo = sum(i["valor_custo_total_centavos"] for i in itens)
    total_venda = sum(i["valor_venda_total_centavos"] for i in itens)
    total_unidades = sum(max(0, i["estoque_atual"]) for i in itens)

    return render_template(
        "estoque/posicao.html",
        itens=itens,
        filtros=filtros,
        nichos=nichos,
        produtos=produtos,
        tipos_ajuste=TIPOS_AJUSTE_MANUAL,
        criticos=criticos,
        total_custo=total_custo,
        total_venda=total_venda,
        total_unidades=total_unidades,
        erro=erro,
        ajuste_dados=ajuste_dados or {"produto_id": "", "tipo": "ajuste_positivo", "quantidade": "1", "motivo": ""},
    ), status_code


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_estoque",
        ("busca", "status", "nicho_id"),
    )
    with get_session(get_engine()) as db:
        return _render_posicao(db, filtros)


@bp.route("/ajustar", methods=["POST"])
def ajustar():
    filtros = gerenciar_filtros_sessao(
        "filtros_estoque",
        ("busca", "status", "nicho_id"),
    )
    ajuste_dados = {
        "produto_id": request.form.get("produto_id", "").strip(),
        "tipo": request.form.get("tipo", "").strip(),
        "quantidade": request.form.get("quantidade", "").strip(),
        "motivo": request.form.get("motivo", "").strip(),
    }
    with get_session(get_engine()) as db:
        try:
            pid = int(ajuste_dados["produto_id"])
            qtd = int(ajuste_dados["quantidade"])
            ajustar_estoque_manual(
                db,
                produto_id=pid,
                tipo=ajuste_dados["tipo"],
                quantidade=qtd,
                motivo=ajuste_dados["motivo"],
                usuario_id=current_user_id(),
            )
            flash("Movimentação manual de estoque registrada com sucesso.", "ok")
            return redirect(url_for("estoque.listar"))
        except (ValueError, TypeError) as exc:
            msg = str(exc) if isinstance(exc, ValueError) else "Selecione o produto e informe uma quantidade numérica válida."
            return _render_posicao(db, filtros, erro=msg, ajuste_dados=ajuste_dados, status_code=400)


@bp.route("/movimentos")
def movimentos():
    filtros = gerenciar_filtros_sessao(
        "filtros_movimentos",
        ("produto_id", "tipo", "origem", "data_inicio", "data_fim"),
    )
    with get_session(get_engine()) as db:
        itens = listar_movimentos(
            db,
            produto_id=filtros["produto_id"],
            tipo=filtros["tipo"],
            origem=filtros["origem"],
            data_inicio=filtros["data_inicio"],
            data_fim=filtros["data_fim"],
            limite=250,
        )
        produtos = db.query(Produto).order_by(Produto.nome).all()
    return render_template(
        "estoque/movimentos.html",
        itens=itens,
        filtros=filtros,
        produtos=produtos,
        tipos_mov=TIPOS_MOVIMENTO,
        origens_label=ORIGENS_LABEL,
    )
