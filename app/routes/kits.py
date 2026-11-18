from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_session
from app.models import Produto
from app.routes.helpers import current_user_id, gerenciar_filtros_sessao, get_engine
from app.services.kit_service import (
    NIVEIS_KIT,
    alternar_ativo_kit,
    atualizar_kit,
    criar_kit,
    listar_kits,
    obter_kit_detalhe,
)
from app.services.nicho_service import listar_nichos

bp = Blueprint("kits", __name__, url_prefix="/kits")


def _valor_reais_str(centavos: int) -> str:
    return f"{centavos / 100:.2f}".replace(".", ",")


def _extrair_itens_form() -> list[dict[str, str]]:
    pids = request.form.getlist("produto_id")
    qtds = request.form.getlist("quantidade")
    itens = []
    for idx, pid in enumerate(pids):
        pid_clean = (pid or "").strip()
        if not pid_clean:
            continue
        qtd = qtds[idx].strip() if idx < len(qtds) and qtds[idx].strip() else "1"
        itens.append({"produto_id": pid_clean, "quantidade": qtd})
    return itens


def _carregar_opcoes_kit(db):
    nichos = listar_nichos(db, ativo="1")
    produtos = db.query(Produto).filter(Produto.ativo == 1).order_by(Produto.nome).all()
    return nichos, produtos


@bp.route("")
def listar():
    filtros = gerenciar_filtros_sessao(
        "filtros_kits",
        ("busca", "nicho_id", "nivel", "ativo"),
        padroes={"ativo": "1"},
    )
    with get_session(get_engine()) as db:
        itens = listar_kits(db, filtros)
        nichos = listar_nichos(db, ativo="1")
    return render_template(
        "kits/lista.html",
        itens=itens,
        filtros=filtros,
        nichos=nichos,
        niveis=NIVEIS_KIT,
    )


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    erro = None
    dados = {"nome": "", "nivel": "medio", "nicho_id": "", "preco": "0,00", "descricao": ""}
    itens_form: list[dict[str, str]] = [{"produto_id": "", "quantidade": "1"}]

    with get_session(get_engine()) as db:
        nichos, produtos = _carregar_opcoes_kit(db)
        if request.method == "POST":
            dados = {
                "nome": request.form.get("nome", ""),
                "nivel": request.form.get("nivel", "medio"),
                "nicho_id": request.form.get("nicho_id", ""),
                "preco": request.form.get("preco", "0,00"),
                "descricao": request.form.get("descricao", ""),
            }
            itens_form = _extrair_itens_form() or [{"produto_id": "", "quantidade": "1"}]
            try:
                criar_kit(db, dados, _extrair_itens_form(), usuario_id=current_user_id())
                flash("Kit criado com sucesso.", "ok")
                return redirect(url_for("kits.listar"))
            except ValueError as exc:
                erro = str(exc)

    return render_template(
        "kits/form.html",
        kit=None,
        dados=dados,
        itens_form=itens_form,
        nichos=nichos,
        produtos=produtos,
        niveis=NIVEIS_KIT,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:kit_id>/editar", methods=["GET", "POST"])
def editar(kit_id: int):
    erro = None
    with get_session(get_engine()) as db:
        detalhe = obter_kit_detalhe(db, kit_id)
        if detalhe is None:
            flash("Kit não encontrado.", "danger")
            return redirect(url_for("kits.listar"))

        kit = detalhe["kit"]
        nichos, produtos = _carregar_opcoes_kit(db)
        dados = {
            "nome": kit.nome,
            "nivel": kit.nivel,
            "nicho_id": str(kit.nicho_id) if kit.nicho_id else "",
            "preco": _valor_reais_str(kit.preco_centavos),
            "descricao": kit.descricao,
        }
        itens_form = [
            {"produto_id": str(i["produto_id"]), "quantidade": str(i["quantidade"])}
            for i in detalhe["itens"]
        ] or [{"produto_id": "", "quantidade": "1"}]

        if request.method == "POST":
            dados = {
                "nome": request.form.get("nome", ""),
                "nivel": request.form.get("nivel", "medio"),
                "nicho_id": request.form.get("nicho_id", ""),
                "preco": request.form.get("preco", "0,00"),
                "descricao": request.form.get("descricao", ""),
            }
            itens_form = _extrair_itens_form() or [{"produto_id": "", "quantidade": "1"}]
            try:
                atualizar_kit(db, kit_id, dados, _extrair_itens_form(), usuario_id=current_user_id())
                flash("Kit atualizado com sucesso.", "ok")
                return redirect(url_for("kits.listar"))
            except ValueError as exc:
                erro = str(exc)

    return render_template(
        "kits/form.html",
        kit=kit,
        dados=dados,
        itens_form=itens_form,
        nichos=nichos,
        produtos=produtos,
        niveis=NIVEIS_KIT,
        erro=erro,
    ), (400 if erro else 200)


@bp.route("/<int:kit_id>/alternar", methods=["POST"])
def alternar(kit_id: int):
    with get_session(get_engine()) as db:
        try:
            kit = alternar_ativo_kit(db, kit_id, usuario_id=current_user_id())
            estado = "reativado" if kit.ativo else "inativado"
            flash(f"Kit '{kit.nome}' {estado}.", "ok")
        except ValueError as exc:
            flash(str(exc), "danger")
    return redirect(url_for("kits.listar"))
