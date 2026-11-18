from datetime import datetime, timezone
from flask import Blueprint, Response, flash, render_template, request

from app.db import get_session
from app.models import Produto
from app.routes.helpers import current_user_id, get_engine
from app.services.cliente_service import listar_clientes
from app.services.config_service import get_all_config
from app.services.estoque_service import listar_posicao_estoque
from app.services.extras_service import (
    calcular_custo_importacao,
    gerar_barras_svg,
    gerar_modelo_importacao_xlsx,
    importar_produtos_planilha,
)
from app.services.fornecedor_service import listar_fornecedores
from app.utils.whatsapp import formatar_whatsapp_link

bp = Blueprint("extras", __name__, url_prefix="/extras")


@bp.route("")
def index():
    return render_template("extras/index.html")


@bp.route("/etiquetas", methods=["GET", "POST"])
def etiquetas():
    with get_session(get_engine()) as db:
        produtos = db.query(Produto).filter(Produto.ativo == 1).order_by(Produto.nome).all()

    selecionados: list[dict] = []
    if request.method == "POST":
        pids = request.form.getlist("produto_id")
        qtds = request.form.getlist("qtd")
        mapa = {p.id: p for p in produtos}
        for idx, pid_raw in enumerate(pids):
            if not str(pid_raw).isdigit():
                continue
            prod = mapa.get(int(pid_raw))
            if prod is None:
                continue
            try:
                qtd = max(1, min(60, int(qtds[idx]) if idx < len(qtds) else 1))
            except ValueError:
                qtd = 1
            svg = gerar_barras_svg(prod.codigo_barras or prod.sku)
            for _ in range(qtd):
                selecionados.append({"produto": prod, "svg": svg})
    else:
        pid_q = request.args.get("produto_id", "").strip()
        qtd_q = request.args.get("qtd", "1").strip()
        if pid_q.isdigit():
            prod = next((p for p in produtos if p.id == int(pid_q)), None)
            if prod:
                qtd = max(1, min(60, int(qtd_q) if qtd_q.isdigit() else 1))
                svg = gerar_barras_svg(prod.codigo_barras or prod.sku)
                for _ in range(qtd):
                    selecionados.append({"produto": prod, "svg": svg})

    return render_template("extras/etiquetas.html", produtos=produtos, etiquetas=selecionados)


@bp.route("/whatsapp")
def whatsapp():
    mes = request.args.get("mes_aniversario", "").strip()
    if not mes.isdigit():
        mes = str(datetime.now(timezone.utc).month)
    msg_aniv = request.args.get(
        "msg_aniv",
        "Olá {nome}! Aqui é da Loja Itamarandiba. Parabéns pelo seu mês! Temos condições especiais esperando por você.",
    ).strip()
    msg_forn = request.args.get(
        "msg_forn",
        "Olá! Gostaria de solicitar cotação e prazo de entrega para reposição de estoque.",
    ).strip()

    with get_session(get_engine()) as db:
        aniversariantes = listar_clientes(db, mes_aniversario=mes)
        fornecedores = listar_fornecedores(db, ativo="1")
        criticos = listar_posicao_estoque(db, status="baixo") + listar_posicao_estoque(db, status="zerado")

    for a in aniversariantes:
        texto = msg_aniv.replace("{nome}", a["nome"].split()[0])
        a["link_personalizado"] = formatar_whatsapp_link(a.get("whatsapp") or "", texto)

    lista_criticos = ", ".join(f"{c['nome']} ({c['sku']})" for c in criticos[:5])
    for f in fornecedores:
        texto_f = msg_forn + (f" Itens em baixa: {lista_criticos}." if lista_criticos else "")
        f["link_cotacao"] = formatar_whatsapp_link(f.get("whatsapp") or "", texto_f)

    return render_template(
        "extras/whatsapp.html",
        mes_aniversario=mes,
        msg_aniv=msg_aniv,
        msg_forn=msg_forn,
        aniversariantes=aniversariantes,
        fornecedores=fornecedores,
    )


@bp.route("/importacao", methods=["GET", "POST"])
def importacao():
    with get_session(get_engine()) as db:
        cfg = get_all_config(db)
        margem_padrao = cfg.get("margem_alvo_pct", "45")

    dados = {
        "valor_lote": "100,00",
        "moeda": "USD",
        "cotacao_usd": "5,50",
        "frete_brl": "50,00",
        "imposto_pct": "20",
        "outros_brl": "0,00",
        "quantidade": "10",
        "margem_alvo_pct": margem_padrao,
        "taxa_venda_pct": "0",
    }
    resultado = None

    if request.method == "POST":
        for k in dados:
            dados[k] = request.form.get(k, dados[k]).strip()
        resultado = calcular_custo_importacao(**dados)

    return render_template("extras/importacao.html", dados=dados, resultado=resultado)


@bp.route("/importar/modelo")
def baixar_modelo():
    conteudo = gerar_modelo_importacao_xlsx()
    return Response(
        conteudo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo_produtos_loja.xlsx"'},
    )


@bp.route("/importar", methods=["GET", "POST"])
def importar():
    resumo = None
    erro = None
    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            erro = "Selecione um arquivo .xlsx ou .csv para importar."
        else:
            try:
                with get_session(get_engine()) as db:
                    resumo = importar_produtos_planilha(
                        db,
                        arquivo.read(),
                        arquivo.filename,
                        usuario_id=current_user_id(),
                    )
                flash(
                    f"{resumo['criados']} produto(s) importado(s)! Duplicados ignorados: {resumo['duplicados']}.",
                    "ok" if resumo["criados"] > 0 else "warn",
                )
            except ValueError as exc:
                erro = str(exc)

    return render_template("extras/importar.html", resumo=resumo, erro=erro), (400 if erro else 200)
