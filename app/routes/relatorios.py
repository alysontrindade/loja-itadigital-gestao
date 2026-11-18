from datetime import date
from flask import Blueprint, Response, render_template, request

from app.db import get_session
from app.routes.helpers import gerenciar_filtros_sessao, get_engine
from app.services.config_service import get_all_config
from app.services.nicho_service import listar_nichos
from app.services.relatorio_service import (
    exportar_relatorio_csv,
    exportar_relatorio_xlsx,
    gerar_relatorio_completo,
)
from app.services.venda_service import CANAIS_VENDA, FORMAS_PAGAMENTO

bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

CAMPOS_FILTRO_RELATORIO = (
    "data_inicio",
    "data_fim",
    "canal",
    "forma_pagamento",
    "nicho_id",
    "mes_aniversario",
)


@bp.route("")
def index():
    filtros = gerenciar_filtros_sessao("filtros_relatorios", CAMPOS_FILTRO_RELATORIO)
    with get_session(get_engine()) as db:
        rel = gerar_relatorio_completo(db, filtros)
        nichos = listar_nichos(db, ativo="1")

    return render_template(
        "relatorios/index.html",
        rel=rel,
        filtros=filtros,
        nichos=nichos,
        canais=CANAIS_VENDA,
        formas=FORMAS_PAGAMENTO,
    )


@bp.route("/exportar/xlsx")
def exportar_xlsx():
    filtros = gerenciar_filtros_sessao("filtros_relatorios", CAMPOS_FILTRO_RELATORIO)
    with get_session(get_engine()) as db:
        cfg = get_all_config(db)
        rel = gerar_relatorio_completo(db, filtros)
    conteudo = exportar_relatorio_xlsx(rel, nome_loja=cfg.get("nome_loja", "Loja Itamarandiba"))
    nome_arquivo = f"relatorio_loja_{date.today().isoformat()}.xlsx"
    return Response(
        conteudo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@bp.route("/exportar/csv")
def exportar_csv():
    secao = request.args.get("secao", "vendas").strip().lower()
    if secao not in ("vendas", "abc", "nichos", "estoque"):
        secao = "vendas"
    filtros = gerenciar_filtros_sessao("filtros_relatorios", CAMPOS_FILTRO_RELATORIO)
    with get_session(get_engine()) as db:
        rel = gerar_relatorio_completo(db, filtros)
    conteudo = exportar_relatorio_csv(rel, secao=secao)
    nome_arquivo = f"relatorio_{secao}_{date.today().isoformat()}.csv"
    return Response(
        conteudo,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
