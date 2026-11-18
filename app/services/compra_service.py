from typing import Any, Mapping
from sqlalchemy.orm import Session

from app.models import Compra, CompraItem, Fornecedor, Produto
from app.models.base import utc_now_iso
from app.services.audit_service import registrar_auditoria
from app.services.estoque_service import registrar_movimento
from app.utils.money import reais_para_centavos

STATUS_COMPRA = {
    "aberta": "Em aberto",
    "recebida": "Recebida",
    "cancelada": "Cancelada",
}


def calcular_rateio_custos(
    itens: list[Mapping[str, Any]],
    extras_centavos: int,
) -> list[dict[str, int]]:
    """Distribui frete, impostos e outros custos proporcionalmente sem perder centavos de arredondamento."""
    if not itens:
        return []
    if extras_centavos < 0:
        raise ValueError("Custos extras não podem ser negativos.")

    preparados = []
    pesos = []
    for idx, item in enumerate(itens):
        qtd = int(item["quantidade"])
        custo_unit = int(item["custo_unit_centavos"])
        if qtd <= 0:
            raise ValueError("Quantidade de item da compra deve ser maior que zero.")
        if custo_unit < 0:
            raise ValueError("Custo unitário não pode ser negativo.")
        bruto = qtd * custo_unit
        preparados.append(
            {
                "index": idx,
                "produto_id": int(item["produto_id"]),
                "quantidade": qtd,
                "custo_unit_centavos": custo_unit,
                "subtotal_bruto_centavos": bruto,
            }
        )
        pesos.append(bruto)

    soma_pesos = sum(pesos)
    if soma_pesos == 0:
        pesos = [p["quantidade"] for p in preparados]
        soma_pesos = sum(pesos)

    extras_por_item = [0] * len(preparados)
    restos = []
    alocado = 0
    for idx, peso in enumerate(pesos):
        numerador = extras_centavos * peso
        cota = numerador // soma_pesos
        resto = numerador % soma_pesos
        extras_por_item[idx] = cota
        alocado += cota
        restos.append((resto, -idx, idx))

    sobra = extras_centavos - alocado
    if sobra > 0:
        restos.sort(reverse=True)
        for i in range(sobra):
            alvo_idx = restos[i % len(restos)][2]
            extras_por_item[alvo_idx] += 1

    resultado = []
    for idx, item in enumerate(preparados):
        subtotal_final = item["subtotal_bruto_centavos"] + extras_por_item[idx]
        qtd = item["quantidade"]
        custo_final_unit = (subtotal_final + (qtd // 2)) // qtd
        resultado.append(
            {
                "produto_id": item["produto_id"],
                "quantidade": qtd,
                "custo_unit_centavos": item["custo_unit_centavos"],
                "rateio_centavos": extras_por_item[idx],
                "subtotal_com_rateio_centavos": subtotal_final,
                "custo_final_unit_centavos": custo_final_unit,
            }
        )
    return resultado


def _ler_centavos_campo(valor: Any, nome: str) -> int:
    centavos = reais_para_centavos(valor)
    if centavos < 0:
        raise ValueError(f"{nome} não pode ser negativo.")
    return centavos


def criar_compra(
    session: Session,
    fornecedor_id: int | str | None,
    itens: list[Mapping[str, Any]],
    frete: Any = "0,00",
    impostos: Any = "0,00",
    outros_custos: Any = "0,00",
    observacoes: str = "",
    data: str = "",
    receber_agora: bool = False,
    atualizar_custo_produto: bool = True,
    usuario_id: int | None = None,
) -> Compra:
    """Cria pedido de compra calculando rateio exato de frete e impostos por item."""
    if not itens:
        raise ValueError("Adicione pelo menos um produto à compra.")

    forn_id: int | None = None
    if fornecedor_id not in (None, "", "0"):
        try:
            forn_id = int(fornecedor_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Fornecedor inválido.") from exc
        if session.get(Fornecedor, forn_id) is None:
            raise ValueError("Fornecedor selecionado não encontrado.")

    itens_norm = []
    for item in itens:
        try:
            pid = int(item["produto_id"])
            qtd = int(item["quantidade"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Item da compra inválido.") from exc
        if session.get(Produto, pid) is None:
            raise ValueError("Produto da compra não encontrado.")
        if "custo_unit_centavos" in item and item["custo_unit_centavos"] not in (None, ""):
            custo_unit = int(item["custo_unit_centavos"])
        else:
            custo_unit = _ler_centavos_campo(item.get("custo_unit", 0), "Custo unitário")
        itens_norm.append(
            {"produto_id": pid, "quantidade": qtd, "custo_unit_centavos": custo_unit}
        )

    frete_c = _ler_centavos_campo(frete, "Frete")
    impostos_c = _ler_centavos_campo(impostos, "Impostos")
    outros_c = _ler_centavos_campo(outros_custos, "Outros custos")
    extras_c = frete_c + impostos_c + outros_c

    rateados = calcular_rateio_custos(itens_norm, extras_c)
    soma_bruta = sum(r["quantidade"] * r["custo_unit_centavos"] for r in rateados)
    total_compra = soma_bruta + extras_c

    data_iso = (data or "").strip()
    if data_iso and len(data_iso) == 10:
        data_iso = f"{data_iso}T12:00:00+00:00"
    elif not data_iso:
        data_iso = utc_now_iso()

    compra = Compra(
        fornecedor_id=forn_id,
        data=data_iso,
        status="aberta",
        frete_centavos=frete_c,
        impostos_centavos=impostos_c,
        outros_custos_centavos=outros_c,
        total_centavos=total_compra,
        observacoes=(observacoes or "").strip(),
    )
    session.add(compra)
    session.flush()

    for r in rateados:
        session.add(
            CompraItem(
                compra_id=compra.id,
                produto_id=r["produto_id"],
                quantidade=r["quantidade"],
                custo_unit_centavos=r["custo_unit_centavos"],
                custo_final_unit_centavos=r["custo_final_unit_centavos"],
            )
        )

    registrar_auditoria(
        session,
        acao="CRIAR_COMPRA",
        entidade="compra",
        entidade_id=compra.id,
        detalhes=f"Pedido de compra #{compra.id} criado ({len(rateados)} item(ns), total {total_compra} centavos).",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(compra)

    if receber_agora:
        return receber_compra(
            session,
            compra.id,
            atualizar_custo_produto=atualizar_custo_produto,
            usuario_id=usuario_id,
        )
    return compra


def receber_compra(
    session: Session,
    compra_id: int,
    atualizar_custo_produto: bool = True,
    usuario_id: int | None = None,
) -> Compra:
    """Confirma recebimento da compra, dá entrada no estoque e atualiza custo médio/final."""
    compra = session.get(Compra, compra_id)
    if compra is None:
        raise ValueError("Compra não encontrada.")
    if compra.status != "aberta":
        raise ValueError(f"Compra #{compra.id} não está em aberto (status atual: {compra.status}).")

    itens = session.query(CompraItem).filter(CompraItem.compra_id == compra.id).all()
    if not itens:
        raise ValueError("A compra não possui itens.")

    try:
        for item in itens:
            registrar_movimento(
                session,
                produto_id=item.produto_id,
                tipo="entrada",
                quantidade=item.quantidade,
                origem="compra",
                referencia_id=compra.id,
                motivo=f"Recebimento da compra #{compra.id}",
                auto_commit=False,
            )
            if atualizar_custo_produto:
                produto = session.get(Produto, item.produto_id)
                if produto is not None:
                    produto.custo_centavos = item.custo_final_unit_centavos
                    produto.atualizado_em = utc_now_iso()

        compra.status = "recebida"
        registrar_auditoria(
            session,
            acao="RECEBER_COMPRA",
            entidade="compra",
            entidade_id=compra.id,
            detalhes=f"Compra #{compra.id} recebida no estoque ({len(itens)} item(ns)).",
            usuario_id=usuario_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(compra)
    return compra


def cancelar_compra(
    session: Session,
    compra_id: int,
    usuario_id: int | None = None,
) -> Compra:
    compra = session.get(Compra, compra_id)
    if compra is None:
        raise ValueError("Compra não encontrada.")
    if compra.status == "recebida":
        raise ValueError("Compras já recebidas não podem ser canceladas diretamente; registre ajuste de estoque.")
    if compra.status == "cancelada":
        raise ValueError("Esta compra já foi cancelada.")

    compra.status = "cancelada"
    registrar_auditoria(
        session,
        acao="CANCELAR_COMPRA",
        entidade="compra",
        entidade_id=compra.id,
        detalhes=f"Compra #{compra.id} cancelada antes do recebimento.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(compra)
    return compra


def obter_compra_detalhe(session: Session, compra_id: int) -> dict[str, Any] | None:
    compra = session.get(Compra, compra_id)
    if compra is None:
        return None
    fornecedor = session.get(Fornecedor, compra.fornecedor_id) if compra.fornecedor_id else None
    itens_db = session.query(CompraItem).filter(CompraItem.compra_id == compra.id).all()
    produtos_map = {p.id: p for p in session.query(Produto).all()}

    itens = []
    for item in itens_db:
        p = produtos_map.get(item.produto_id)
        itens.append(
            {
                "id": item.id,
                "produto_id": item.produto_id,
                "produto_nome": p.nome if p else f"Produto #{item.produto_id}",
                "sku": p.sku if p else "—",
                "quantidade": item.quantidade,
                "custo_unit_centavos": item.custo_unit_centavos,
                "custo_final_unit_centavos": item.custo_final_unit_centavos,
                "subtotal_final_centavos": item.quantidade * item.custo_final_unit_centavos,
            }
        )

    return {
        "compra": compra,
        "fornecedor_nome": fornecedor.nome if fornecedor else "Sem fornecedor",
        "status_label": STATUS_COMPRA.get(compra.status, compra.status),
        "itens": itens,
    }


def listar_compras(
    session: Session,
    filtros: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    f = dict(filtros or {})
    fornecedor_id = str(f.get("fornecedor_id", "") or "").strip()
    status = str(f.get("status", "") or "").strip()
    data_inicio = str(f.get("data_inicio", "") or "").strip()
    data_fim = str(f.get("data_fim", "") or "").strip()

    query = session.query(Compra)
    if fornecedor_id.isdigit():
        query = query.filter(Compra.fornecedor_id == int(fornecedor_id))
    if status in STATUS_COMPRA:
        query = query.filter(Compra.status == status)
    if data_inicio:
        query = query.filter(Compra.data >= f"{data_inicio}T00:00:00")
    if data_fim:
        query = query.filter(Compra.data <= f"{data_fim}T23:59:59")

    compras = query.order_by(Compra.id.desc()).all()
    fornecedores_map = {x.id: x.nome for x in session.query(Fornecedor).all()}
    itens_contagem: dict[int, int] = {}
    for ci in session.query(CompraItem.compra_id).all():
        itens_contagem[ci[0]] = itens_contagem.get(ci[0], 0) + 1

    return [
        {
            "id": c.id,
            "data": c.data,
            "fornecedor_id": c.fornecedor_id,
            "fornecedor_nome": fornecedores_map.get(c.fornecedor_id, "Sem fornecedor"),
            "status": c.status,
            "status_label": STATUS_COMPRA.get(c.status, c.status),
            "frete_centavos": c.frete_centavos,
            "impostos_centavos": c.impostos_centavos,
            "outros_custos_centavos": c.outros_custos_centavos,
            "total_centavos": c.total_centavos,
            "qtd_itens": itens_contagem.get(c.id, 0),
            "observacoes": c.observacoes,
        }
        for c in compras
    ]
