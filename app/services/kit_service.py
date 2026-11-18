from typing import Any, Mapping
from sqlalchemy.orm import Session

from app.models import Kit, KitItem, Nicho, Produto
from app.services.audit_service import registrar_auditoria
from app.services.produto_service import calcular_margem
from app.utils.money import reais_para_centavos

NIVEIS_KIT = {
    "basico": "Básico / Lembrança",
    "medio": "Presente / Padrão",
    "premium": "Premium / Deluxe",
}


def _validar_itens_kit(session: Session, itens: list[Mapping[str, Any]]) -> list[tuple[Produto, int]]:
    if not itens:
        raise ValueError("Adicione pelo menos um produto ao kit.")

    vistos: set[int] = set()
    validados: list[tuple[Produto, int]] = []
    for item in itens:
        try:
            pid = int(item["produto_id"])
            qtd = int(item.get("quantidade", 1))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Item inválido na composição do kit.") from exc
        if qtd <= 0:
            raise ValueError("Quantidade de cada produto no kit deve ser pelo menos 1.")
        if pid in vistos:
            raise ValueError("Não repita o mesmo produto duas vezes no kit (some a quantidade).")
        produto = session.get(Produto, pid)
        if produto is None:
            raise ValueError("Um dos produtos selecionados não existe.")
        vistos.add(pid)
        validados.append((produto, qtd))
    return validados


def _validar_cabecalho_kit(session: Session, dados: Mapping[str, Any]) -> dict[str, Any]:
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("O nome do kit é obrigatório.")

    nivel = str(dados.get("nivel") or "medio").strip().lower()
    if nivel not in NIVEIS_KIT:
        raise ValueError("Nível do kit inválido.")

    nicho_raw = dados.get("nicho_id")
    nicho_id: int | None = None
    if nicho_raw not in (None, "", "0"):
        try:
            nicho_id = int(nicho_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Nicho inválido para o kit.") from exc
        if session.get(Nicho, nicho_id) is None:
            raise ValueError("Nicho selecionado não encontrado.")

    if "preco_centavos" in dados and dados["preco_centavos"] not in (None, ""):
        preco_centavos = int(dados["preco_centavos"])
    else:
        preco_centavos = reais_para_centavos(dados.get("preco", 0))
    if preco_centavos <= 0:
        raise ValueError("O preço de venda do kit deve ser maior que zero.")

    return {
        "nome": nome,
        "nivel": nivel,
        "nicho_id": nicho_id,
        "preco_centavos": preco_centavos,
        "descricao": str(dados.get("descricao") or "").strip(),
    }


def _calcular_resumo_kit(
    kit: Kit,
    composicao: list[tuple[Produto, int]],
    nichos_map: dict[int, Nicho],
) -> dict[str, Any]:
    custo_total = sum(p.custo_centavos * qtd for p, qtd in composicao)
    soma_avulsa = sum(p.preco_centavos * qtd for p, qtd in composicao)
    economia = max(0, soma_avulsa - kit.preco_centavos)
    disponivel = (
        min(max(0, p.estoque_atual) // qtd for p, qtd in composicao)
        if composicao
        else 0
    )
    calc = calcular_margem(custo_total, kit.preco_centavos)
    nicho = nichos_map.get(kit.nicho_id) if kit.nicho_id else None

    return {
        "id": kit.id,
        "nome": kit.nome,
        "nivel": kit.nivel,
        "nivel_label": NIVEIS_KIT.get(kit.nivel, kit.nivel),
        "nicho_id": kit.nicho_id,
        "nicho_nome": nicho.nome if nicho else "Sem nicho",
        "nicho_cor": nicho.cor if nicho else "#6b7280",
        "preco_centavos": kit.preco_centavos,
        "custo_total_centavos": custo_total,
        "soma_avulsa_centavos": soma_avulsa,
        "economia_centavos": economia,
        "lucro_centavos": calc["lucro_centavos"],
        "margem_pct": calc["margem_pct"],
        "estoque_disponivel": disponivel,
        "descricao": kit.descricao,
        "ativo": bool(kit.ativo),
        "itens": [
            {
                "produto_id": p.id,
                "produto_nome": p.nome,
                "sku": p.sku,
                "quantidade": qtd,
                "estoque_atual": p.estoque_atual,
                "custo_unit_centavos": p.custo_centavos,
                "preco_unit_centavos": p.preco_centavos,
            }
            for p, qtd in composicao
        ],
    }


def criar_kit(
    session: Session,
    dados: Mapping[str, Any],
    itens: list[Mapping[str, Any]],
    usuario_id: int | None = None,
) -> Kit:
    cabecalho = _validar_cabecalho_kit(session, dados)
    composicao = _validar_itens_kit(session, itens)

    kit = Kit(**cabecalho, ativo=1)
    session.add(kit)
    session.flush()

    for produto, qtd in composicao:
        session.add(KitItem(kit_id=kit.id, produto_id=produto.id, quantidade=qtd))

    registrar_auditoria(
        session,
        acao="CRIAR_KIT",
        entidade="kit",
        entidade_id=kit.id,
        detalhes=f"Kit '{kit.nome}' ({kit.nivel}) criado com {len(composicao)} produto(s).",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(kit)
    return kit


def atualizar_kit(
    session: Session,
    kit_id: int,
    dados: Mapping[str, Any],
    itens: list[Mapping[str, Any]],
    usuario_id: int | None = None,
) -> Kit:
    kit = session.get(Kit, kit_id)
    if kit is None:
        raise ValueError("Kit não encontrado.")

    cabecalho = _validar_cabecalho_kit(session, dados)
    composicao = _validar_itens_kit(session, itens)

    for chave, valor in cabecalho.items():
        setattr(kit, chave, valor)

    session.query(KitItem).filter(KitItem.kit_id == kit_id).delete()
    for produto, qtd in composicao:
        session.add(KitItem(kit_id=kit_id, produto_id=produto.id, quantidade=qtd))

    registrar_auditoria(
        session,
        acao="EDITAR_KIT",
        entidade="kit",
        entidade_id=kit.id,
        detalhes=f"Kit '{kit.nome}' atualizado ({len(composicao)} itens).",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(kit)
    return kit


def alternar_ativo_kit(
    session: Session,
    kit_id: int,
    usuario_id: int | None = None,
) -> Kit:
    kit = session.get(Kit, kit_id)
    if kit is None:
        raise ValueError("Kit não encontrado.")
    kit.ativo = 0 if kit.ativo else 1
    acao = "REATIVAR_KIT" if kit.ativo else "INATIVAR_KIT"
    registrar_auditoria(
        session,
        acao=acao,
        entidade="kit",
        entidade_id=kit.id,
        detalhes=f"Kit '{kit.nome}' marcado como {'ativo' if kit.ativo else 'inativo'}.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(kit)
    return kit


def obter_kit_detalhe(session: Session, kit_id: int) -> dict[str, Any] | None:
    kit = session.get(Kit, kit_id)
    if kit is None:
        return None
    nichos_map = {n.id: n for n in session.query(Nicho).all()}
    produtos_map = {p.id: p for p in session.query(Produto).all()}
    kit_itens = session.query(KitItem).filter(KitItem.kit_id == kit_id).all()
    composicao = [
        (produtos_map[ki.produto_id], ki.quantidade)
        for ki in kit_itens
        if ki.produto_id in produtos_map
    ]
    resumo = _calcular_resumo_kit(kit, composicao, nichos_map)
    resumo["kit"] = kit
    return resumo


def listar_kits(
    session: Session,
    filtros: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    f = dict(filtros or {})
    ativo = str(f.get("ativo", "1") or "1")
    busca = str(f.get("busca", "") or "").strip().lower()
    nicho_id = str(f.get("nicho_id", "") or "").strip()
    nivel = str(f.get("nivel", "") or "").strip()

    query = session.query(Kit)
    if ativo == "1":
        query = query.filter(Kit.ativo == 1)
    elif ativo == "0":
        query = query.filter(Kit.ativo == 0)
    if nicho_id.isdigit():
        query = query.filter(Kit.nicho_id == int(nicho_id))
    if nivel in NIVEIS_KIT:
        query = query.filter(Kit.nivel == nivel)

    kits = query.order_by(Kit.nome).all()
    nichos_map = {n.id: n for n in session.query(Nicho).all()}
    produtos_map = {p.id: p for p in session.query(Produto).all()}

    todos_ki = session.query(KitItem).all()
    mapa_ki: dict[int, list[tuple[Produto, int]]] = {}
    for ki in todos_ki:
        if p := produtos_map.get(ki.produto_id):
            mapa_ki.setdefault(ki.kit_id, []).append((p, ki.quantidade))

    resultado: list[dict[str, Any]] = []
    for k in kits:
        if busca and busca not in f"{k.nome} {k.descricao}".lower():
            continue
        resultado.append(_calcular_resumo_kit(k, mapa_ki.get(k.id, []), nichos_map))
    return resultado
