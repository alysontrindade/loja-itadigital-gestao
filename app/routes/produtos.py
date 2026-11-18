from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.routes.helpers import (
    current_user_id,
    gerenciar_filtros_sessao,
    get_engine,
    get_settings,
)
from app.services.config_service import get_all_config
from app.services.fornecedor_service import listar_fornecedores
from app.services.nicho_service import listar_nichos
from app.services.produto_service import (
    adicionar_imagens_produto,
    alternar_ativo_produto,
    atualizar_produto,
    calcular_margem,
    criar_produto,
    definir_imagem_principal,
    listar_produtos,
    obter_produto_detalhe,
    remover_imagem_produto,
    sugerir_sku,
    verificar_duplicidades_produto,
)

bp = Blueprint("produtos", __name__, url_prefix="/produtos")

CAMPOS_FILTRO_PRODUTOS = (
    "busca",
    "nicho_id",
    "fornecedor_id",
    "preco_min",
    "preco_max",
    "margem_min",
    "margem_max",
    "margem_abaixo_alvo",
    "estoque_status",
    "ativo",
    "ordenar",
)


def _valor_reais_str(centavos: int) -> str:
    return f"{centavos / 100:.2f}".replace(".", ",")


def _carregar_opcoes_formulario(db):
    nichos = listar_nichos(db, ativo="1")
    fornecedores = listar_fornecedores(db, ativo="1")
    return nichos, fornecedores


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_produtos",
        CAMPOS_FILTRO_PRODUTOS,
        padroes={"ativo": "1", "ordenar": "nome"},
    )
    with get_session(get_engine()) as db:
        cfg = get_all_config(db)
        margem_alvo = float(cfg.get("margem_alvo_pct", "45") or 45)
        itens = listar_produtos(db, filtros, margem_alvo_pct=margem_alvo)
        nichos, fornecedores = _carregar_opcoes_formulario(db)

    if request.headers.get("HX-Request") == "true" and request.headers.get("HX-Target") == "produtos-tabela":
        return render_template("produtos/_tabela.html", itens=itens, filtros=filtros)

    return render_template(
        "produtos/lista.html",
        itens=itens,
        filtros=filtros,
        nichos=nichos,
        fornecedores=fornecedores,
        margem_alvo=margem_alvo,
    )


@bp.route("/verificar-duplicidade")
def verificar_duplicidade():
    excluir_raw = request.args.get("excluir_id", "").strip()
    excluir_id = int(excluir_raw) if excluir_raw.isdigit() else None
    with get_session(get_engine()) as db:
        avisos = verificar_duplicidades_produto(
            db,
            nome=request.args.get("nome", ""),
            sku=request.args.get("sku", ""),
            codigo_barras=request.args.get("codigo_barras", ""),
            excluir_id=excluir_id,
        )
    return render_template("produtos/_duplicidade.html", avisos=avisos)


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    erro = None
    settings = get_settings()
    with get_session(get_engine()) as db:
        nichos, fornecedores = _carregar_opcoes_formulario(db)
        cfg = get_all_config(db)
        margem_alvo = float(cfg.get("margem_alvo_pct", "45") or 45)
        dados = {
            "sku": sugerir_sku(db),
            "codigo_barras": "",
            "nome": "",
            "descricao": "",
            "unidade": "un",
            "custo": "0,00",
            "preco": "0,00",
            "estoque_inicial": "0",
            "estoque_minimo": "3",
            "fornecedor_id": "",
        }
        nichos_selecionados: list[int] = []

        if request.method == "POST":
            dados = {k: request.form.get(k, "") for k in dados}
            nichos_selecionados = [
                int(x) for x in request.form.getlist("nichos") if str(x).isdigit()
            ]
            try:
                produto = criar_produto(
                    db,
                    dados,
                    nicho_ids=nichos_selecionados,
                    usuario_id=current_user_id(),
                )
            except ValueError as exc:
                db.rollback()
                erro = str(exc)
            else:
                arquivos = [f for f in request.files.getlist("imagens") if f and f.filename]
                if arquivos:
                    try:
                        adicionar_imagens_produto(
                            db,
                            settings,
                            produto.id,
                            arquivos,
                            usuario_id=current_user_id(),
                        )
                    except ValueError as img_exc:
                        db.rollback()
                        flash(
                            f"Produto '{produto.nome}' cadastrado, mas houve erro ao salvar foto: {img_exc}",
                            "warn",
                        )
                        return redirect(url_for("produtos.editar", produto_id=produto.id))
                flash(f"Produto '{produto.nome}' cadastrado com sucesso.", "ok")
                return redirect(url_for("produtos.listar"))

    return render_template(
        "produtos/form.html",
        produto=None,
        dados=dados,
        nichos=nichos,
        nichos_selecionados=nichos_selecionados,
        fornecedores=fornecedores,
        imagens=[],
        margem={"lucro_centavos": 0, "margem_pct": 0.0},
        margem_alvo=margem_alvo,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
def editar(produto_id: int):
    erro = None
    settings = get_settings()
    with get_session(get_engine()) as db:
        detalhe = obter_produto_detalhe(db, produto_id)
        if detalhe is None:
            flash("Produto não encontrado.", "danger")
            return redirect(url_for("produtos.listar"))

        produto = detalhe["produto"]
        nichos, fornecedores = _carregar_opcoes_formulario(db)
        cfg = get_all_config(db)
        margem_alvo = float(cfg.get("margem_alvo_pct", "45") or 45)

        dados = {
            "sku": produto.sku,
            "codigo_barras": produto.codigo_barras or "",
            "nome": produto.nome,
            "descricao": produto.descricao,
            "unidade": produto.unidade,
            "custo": _valor_reais_str(produto.custo_centavos),
            "preco": _valor_reais_str(produto.preco_centavos),
            "estoque_minimo": str(produto.estoque_minimo),
            "fornecedor_id": str(produto.fornecedor_id or ""),
        }
        nichos_selecionados = detalhe["nicho_ids"]
        imagens = detalhe["imagens"]
        margem = calcular_margem(produto.custo_centavos, produto.preco_centavos)

        if request.method == "POST":
            dados = {k: request.form.get(k, "") for k in dados}
            nichos_selecionados = [
                int(x) for x in request.form.getlist("nichos") if str(x).isdigit()
            ]
            try:
                atualizar_produto(
                    db,
                    produto_id,
                    dados,
                    nicho_ids=nichos_selecionados,
                    usuario_id=current_user_id(),
                )
                arquivos = [f for f in request.files.getlist("imagens") if f and f.filename]
                if arquivos:
                    adicionar_imagens_produto(
                        db,
                        settings,
                        produto_id,
                        arquivos,
                        usuario_id=current_user_id(),
                    )
                flash(f"Produto '{dados['nome']}' atualizado com sucesso.", "ok")
                return redirect(url_for("produtos.editar", produto_id=produto_id))
            except ValueError as exc:
                db.rollback()
                erro = str(exc)

    return render_template(
        "produtos/form.html",
        produto=produto,
        dados=dados,
        nichos=nichos,
        nichos_selecionados=nichos_selecionados,
        fornecedores=fornecedores,
        imagens=imagens,
        margem=margem,
        margem_alvo=margem_alvo,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:produto_id>/alternar", methods=["POST"])
def alternar(produto_id: int):
    with get_session(get_engine()) as db:
        try:
            p = alternar_ativo_produto(db, produto_id, usuario_id=current_user_id())
            estado = "reativado" if p.ativo else "inativado"
            flash(f"Produto '{p.nome}' {estado}.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("produtos.listar"))


@bp.route("/<int:produto_id>/imagens/<int:imagem_id>/principal", methods=["POST"])
def imagem_principal(produto_id: int, imagem_id: int):
    with get_session(get_engine()) as db:
        try:
            definir_imagem_principal(db, produto_id, imagem_id, usuario_id=current_user_id())
            flash("Foto principal atualizada.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("produtos.editar", produto_id=produto_id))


@bp.route("/<int:produto_id>/imagens/<int:imagem_id>/remover", methods=["POST"])
def imagem_remover(produto_id: int, imagem_id: int):
    with get_session(get_engine()) as db:
        try:
            remover_imagem_produto(
                db,
                get_settings(),
                produto_id,
                imagem_id,
                usuario_id=current_user_id(),
            )
            flash("Imagem removida.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("produtos.editar", produto_id=produto_id))
