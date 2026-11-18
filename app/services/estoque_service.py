from typing import Any, Mapping
from sqlalchemy.orm import Session

from app.models import MovimentoEstoque, Nicho, Produto, ProdutoImagem, ProdutoNicho
from app.models.base import utc_now_iso
from app.services.audit_service import registrar_auditoria

TIPOS_MOVIMENTO = {
    "entrada": ("Entrada", 1),
    "ajuste_positivo": ("Ajuste (+)", 1),
    "saida": ("Saída", -1),
    "ajuste_negativo": ("Ajuste (-)", -1),
    "perda": ("Perda / Avaria", -1),
}

TIPOS_AJUSTE_MANUAL = {
    "ajuste_positivo": "Ajuste positivo (+)",
    "ajuste_negativo": "Ajuste negativo (-)",
    "perda": "Perda / Avaria (-)",
}

ORIGENS_LABEL = {
    "saldo_inicial": "Saldo inicial",
    "compra": "Compra recebida",
    "venda": "Venda",
    "venda_kit": "Venda (Kit)",
    "cancelamento_venda": "Estorno de venda",
    "ajuste_manual": "Ajuste manual",
    "perda": "Perda registrada",
}


def registrar_movimento(
    session: Session,
    produto_id: int,
    tipo: str,
    quantidade: int,
    origem: str,
    referencia_id: int | None = None,
    motivo: str = "",
    permite_negativo: bool = False,
    auto_commit: bool = False,
) -> MovimentoEstoque:
    """Registra movimento auditado e atualiza estoque_atual com proteção contra saldo negativo."""
    if tipo not in TIPOS_MOVIMENTO:
        raise ValueError("Tipo de movimentação de estoque inválido.")
    try:
        qtd = int(quantidade)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantidade de movimento inválida.") from exc
    if qtd <= 0:
        raise ValueError("A quantidade do movimento deve ser maior que zero.")

    produto = session.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado para movimentação de estoque.")

    _, sinal = TIPOS_MOVIMENTO[tipo]
    novo_saldo = produto.estoque_atual + (sinal * qtd)
    if not permite_negativo and novo_saldo < 0:
        raise ValueError(
            f"Estoque insuficiente para '{produto.nome}' (disponível: {produto.estoque_atual}, necessário: {qtd})."
        )

    produto.estoque_atual = novo_saldo
    produto.atualizado_em = utc_now_iso()

    movimento = MovimentoEstoque(
        produto_id=produto.id,
        tipo=tipo,
        quantidade=qtd,
        origem=origem,
        referencia_id=referencia_id,
        motivo=(motivo or "").strip(),
    )
    session.add(movimento)
    session.flush()

    if auto_commit:
        session.commit()
        session.refresh(movimento)
    return movimento


def ajustar_estoque_manual(
    session: Session,
    produto_id: int,
    tipo: str,
    quantidade: int,
    motivo: str,
    usuario_id: int | None = None,
) -> MovimentoEstoque:
    """Executa ajuste positivo, negativo ou perda exigindo motivo e registrando auditoria."""
    if tipo not in TIPOS_AJUSTE_MANUAL:
        raise ValueError("Tipo de ajuste manual inválido.")
    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise ValueError("Informe o motivo do ajuste ou perda de estoque.")

    produto = session.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado.")

    origem = "perda" if tipo == "perda" else "ajuste_manual"
    mov = registrar_movimento(
        session,
        produto_id=produto_id,
        tipo=tipo,
        quantidade=quantidade,
        origem=origem,
        motivo=motivo_limpo,
        permite_negativo=False,
        auto_commit=False,
    )
    registrar_auditoria(
        session,
        acao="AJUSTE_ESTOQUE",
        entidade="estoque",
        entidade_id=produto.id,
        detalhes=f"{TIPOS_AJUSTE_MANUAL[tipo]} de {quantidade} un em '{produto.nome}': {motivo_limpo}",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(mov)
    return mov


def contar_estoque_critico(session: Session) -> int:
    """Conta produtos ativos com estoque zerado ou abaixo/igual ao mínimo."""
    return (
        session.query(Produto)
        .filter(Produto.ativo == 1, Produto.estoque_atual <= Produto.estoque_minimo)
        .count()
    )


def listar_posicao_estoque(
    session: Session,
    busca: str = "",
    status: str = "",
    nicho_id: str = "",
) -> list[dict[str, Any]]:
    """Lista posição atual de estoque dos produtos ativos com valorização a custo e venda."""
    query = session.query(Produto).filter(Produto.ativo == 1)
    if str(nicho_id or "").isdigit():
        nid = int(nicho_id)
        subq = session.query(ProdutoNicho.produto_id).filter(ProdutoNicho.nicho_id == nid)
        query = query.filter(Produto.id.in_(subq))

    produtos = query.order_by(Produto.estoque_atual.asc(), Produto.nome.asc()).all()
    termo = (busca or "").strip().lower()

    nichos_por_id = {n.id: n for n in session.query(Nicho).all()}
    mapa_nichos: dict[int, list[dict]] = {}
    for pn in session.query(ProdutoNicho).all():
        if n := nichos_por_id.get(pn.nicho_id):
            mapa_nichos.setdefault(pn.produto_id, []).append(
                {"id": n.id, "nome": n.nome, "cor": n.cor}
            )

    mapa_imagens: dict[int, str] = {}
    for img in (
        session.query(ProdutoImagem)
        .order_by(ProdutoImagem.principal.desc(), ProdutoImagem.ordem, ProdutoImagem.id)
        .all()
    ):
        mapa_imagens.setdefault(img.produto_id, img.arquivo)

    itens: list[dict[str, Any]] = []
    for p in produtos:
        if termo and termo not in f"{p.nome} {p.sku} {p.codigo_barras or ''}".lower():
            continue
        est_status = (
            "zerado"
            if p.estoque_atual <= 0
            else "baixo"
            if p.estoque_atual <= p.estoque_minimo
            else "ok"
        )
        if status and est_status != status:
            continue
        itens.append(
            {
                "id": p.id,
                "sku": p.sku,
                "nome": p.nome,
                "unidade": p.unidade,
                "estoque_atual": p.estoque_atual,
                "estoque_minimo": p.estoque_minimo,
                "estoque_status": est_status,
                "custo_centavos": p.custo_centavos,
                "preco_centavos": p.preco_centavos,
                "valor_custo_total_centavos": max(0, p.estoque_atual) * p.custo_centavos,
                "valor_venda_total_centavos": max(0, p.estoque_atual) * p.preco_centavos,
                "nichos": mapa_nichos.get(p.id, []),
                "imagem_principal": mapa_imagens.get(p.id),
            }
        )
    return itens


def listar_movimentos(
    session: Session,
    produto_id: int | str | None = None,
    tipo: str = "",
    origem: str = "",
    data_inicio: str = "",
    data_fim: str = "",
    limite: int = 200,
) -> list[dict[str, Any]]:
    """Lista histórico de movimentações de estoque com filtros."""
    query = session.query(MovimentoEstoque)
    if produto_id not in (None, "") and str(produto_id).isdigit():
        query = query.filter(MovimentoEstoque.produto_id == int(produto_id))
    if tipo and tipo in TIPOS_MOVIMENTO:
        query = query.filter(MovimentoEstoque.tipo == tipo)
    if origem:
        query = query.filter(MovimentoEstoque.origem == origem)
    if data_inicio:
        query = query.filter(MovimentoEstoque.criado_em >= f"{data_inicio}T00:00:00")
    if data_fim:
        query = query.filter(MovimentoEstoque.criado_em <= f"{data_fim}T23:59:59")

    movs = query.order_by(MovimentoEstoque.id.desc()).limit(limite).all()
    produtos_map = {p.id: p for p in session.query(Produto).all()}

    resultado = []
    for m in movs:
        p = produtos_map.get(m.produto_id)
        tipo_label, sinal = TIPOS_MOVIMENTO.get(m.tipo, (m.tipo, 1))
        resultado.append(
            {
                "id": m.id,
                "produto_id": m.produto_id,
                "produto_nome": p.nome if p else f"Produto #{m.produto_id}",
                "produto_sku": p.sku if p else "—",
                "tipo": m.tipo,
                "tipo_label": tipo_label,
                "sinal": sinal,
                "quantidade": m.quantidade,
                "origem": m.origem,
                "origem_label": ORIGENS_LABEL.get(m.origem, m.origem),
                "referencia_id": m.referencia_id,
                "motivo": m.motivo,
                "criado_em": m.criado_em,
            }
        )
    return resultado
