from datetime import datetime, timezone
from typing import Any, Mapping
from sqlalchemy.orm import Session

from app.models import (
    Cliente,
    Kit,
    KitItem,
    Produto,
    ProdutoImagem,
    ProdutoNicho,
    Venda,
    VendaItem,
)
from app.services.audit_service import registrar_auditoria
from app.services.estoque_service import registrar_movimento
from app.utils.money import reais_para_centavos

CANAIS_VENDA = {
    "loja": "Loja Física",
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
    "ml": "Mercado Livre",
    "shopee": "Shopee",
}

FORMAS_PAGAMENTO = {
    "pix": "Pix",
    "dinheiro": "Dinheiro",
    "debito": "Débito",
    "credito": "Crédito",
}

STATUS_VENDA = {
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}


def buscar_itens_pdv(
    session: Session,
    busca: str = "",
    nicho_id: str = "",
    limite: int = 36,
) -> dict[str, list[dict[str, Any]]]:
    """Busca produtos e kits ativos para o PDV com estoque em tempo real."""
    termo = (busca or "").strip().lower()
    nid = int(nicho_id) if str(nicho_id or "").isdigit() else None

    q_prod = session.query(Produto).filter(Produto.ativo == 1)
    if nid is not None:
        subq = session.query(ProdutoNicho.produto_id).filter(ProdutoNicho.nicho_id == nid)
        q_prod = q_prod.filter(Produto.id.in_(subq))

    produtos_db = q_prod.order_by(Produto.estoque_atual.desc(), Produto.nome.asc()).all()
    mapa_imgs: dict[int, str] = {}
    for img in (
        session.query(ProdutoImagem)
        .order_by(ProdutoImagem.principal.desc(), ProdutoImagem.ordem, ProdutoImagem.id)
        .all()
    ):
        mapa_imgs.setdefault(img.produto_id, img.arquivo)

    produtos: list[dict[str, Any]] = []
    for p in produtos_db:
        if termo:
            cod = (p.codigo_barras or "").lower()
            if termo not in p.nome.lower() and termo not in p.sku.lower() and termo not in cod:
                continue
        produtos.append(
            {
                "tipo": "produto",
                "id": p.id,
                "nome": p.nome,
                "sku": p.sku,
                "codigo_barras": p.codigo_barras or "",
                "unidade": p.unidade,
                "preco_centavos": p.preco_centavos,
                "custo_centavos": p.custo_centavos,
                "estoque_disponivel": max(0, p.estoque_atual),
                "imagem_principal": mapa_imgs.get(p.id),
                "match_exato_barras": bool(termo and p.codigo_barras and p.codigo_barras.lower() == termo),
            }
        )
        if len(produtos) >= limite:
            break

    q_kits = session.query(Kit).filter(Kit.ativo == 1)
    if nid is not None:
        q_kits = q_kits.filter(Kit.nicho_id == nid)
    kits_db = q_kits.order_by(Kit.nome.asc()).all()

    todos_prods = {p.id: p for p in session.query(Produto).all()}
    todos_ki = session.query(KitItem).all()
    mapa_ki: dict[int, list[tuple[Produto, int]]] = {}
    for ki in todos_ki:
        if prod := todos_prods.get(ki.produto_id):
            mapa_ki.setdefault(ki.kit_id, []).append((prod, ki.quantidade))

    kits: list[dict[str, Any]] = []
    for k in kits_db:
        if termo and termo not in f"{k.nome} {k.descricao}".lower():
            continue
        comp = mapa_ki.get(k.id, [])
        disp = min(max(0, p.estoque_atual) // q for p, q in comp) if comp else 0
        kits.append(
            {
                "tipo": "kit",
                "id": k.id,
                "nome": k.nome,
                "sku": f"KIT-{k.id:03d}",
                "codigo_barras": "",
                "unidade": "kit",
                "preco_centavos": k.preco_centavos,
                "custo_centavos": sum(p.custo_centavos * q for p, q in comp),
                "estoque_disponivel": disp,
                "imagem_principal": None,
                "match_exato_barras": False,
            }
        )

    return {"produtos": produtos, "kits": kits}


def registrar_venda(
    session: Session,
    dados: Mapping[str, Any],
    itens: list[Mapping[str, Any]],
    usuario_id: int | None = None,
) -> Venda:
    """Registra venda congelando preços/custos e baixando estoque (produtos e componentes de kits)."""
    if not itens:
        raise ValueError("Adicione pelo menos um produto ou kit à venda.")

    canal = str(dados.get("canal") or "loja").strip().lower()
    if canal not in CANAIS_VENDA:
        raise ValueError("Canal de venda inválido.")

    forma = str(dados.get("forma_pagamento") or "pix").strip().lower()
    if forma not in FORMAS_PAGAMENTO:
        raise ValueError("Forma de pagamento inválida.")

    cliente_id: int | None = None
    cli_raw = dados.get("cliente_id")
    if cli_raw not in (None, "", "0"):
        try:
            cliente_id = int(cli_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Cliente inválido.") from exc
        if session.get(Cliente, cliente_id) is None:
            raise ValueError("Cliente selecionado não encontrado.")

    desconto_geral = (
        int(dados["desconto_centavos"])
        if "desconto_centavos" in dados and dados["desconto_centavos"] not in (None, "")
        else reais_para_centavos(dados.get("desconto", 0))
    )
    frete_c = (
        int(dados["frete_centavos"])
        if "frete_centavos" in dados and dados["frete_centavos"] not in (None, "")
        else reais_para_centavos(dados.get("frete", 0))
    )
    if desconto_geral < 0 or frete_c < 0:
        raise ValueError("Desconto e frete não podem ser negativos.")

    try:
        venda = Venda(
            cliente_id=cliente_id,
            canal=canal,
            forma_pagamento=forma,
            status="concluida",
            subtotal_centavos=0,
            desconto_centavos=desconto_geral,
            frete_centavos=frete_c,
            total_centavos=0,
            observacoes=str(dados.get("observacoes") or "").strip(),
        )
        session.add(venda)
        session.flush()

        subtotal = 0
        for item in itens:
            tipo_item = str(item.get("tipo") or "produto").strip().lower()
            try:
                item_id = int(item["id"])
                qtd = int(item.get("quantidade", 1))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Item da venda inválido.") from exc
            if qtd <= 0:
                raise ValueError("Quantidade vendida deve ser maior que zero.")

            item_desc = (
                int(item["desconto_centavos"])
                if "desconto_centavos" in item and item["desconto_centavos"] not in (None, "")
                else reais_para_centavos(item.get("desconto", 0))
            )
            if item_desc < 0:
                raise ValueError("Desconto do item não pode ser negativo.")

            if tipo_item == "produto":
                prod = session.get(Produto, item_id)
                if prod is None or not prod.ativo:
                    raise ValueError("Produto não encontrado ou inativo.")

                preco_u = (
                    int(item["preco_unit_centavos"])
                    if "preco_unit_centavos" in item and item["preco_unit_centavos"] not in (None, "")
                    else prod.preco_centavos
                )
                custo_u = prod.custo_centavos

                registrar_movimento(
                    session,
                    produto_id=prod.id,
                    tipo="saida",
                    quantidade=qtd,
                    origem="venda",
                    referencia_id=venda.id,
                    motivo=f"Venda #{venda.id}",
                    auto_commit=False,
                )
                vi = VendaItem(
                    venda_id=venda.id,
                    produto_id=prod.id,
                    kit_id=None,
                    quantidade=qtd,
                    preco_unit_centavos=preco_u,
                    custo_unit_centavos=custo_u,
                    desconto_centavos=item_desc,
                )
            elif tipo_item == "kit":
                kit = session.get(Kit, item_id)
                if kit is None or not kit.ativo:
                    raise ValueError("Kit não encontrado ou inativo.")
                kit_itens = session.query(KitItem).filter(KitItem.kit_id == kit.id).all()
                if not kit_itens:
                    raise ValueError(f"O kit '{kit.nome}' não possui produtos cadastrados.")

                custo_kit = 0
                for ki in kit_itens:
                    comp = session.get(Produto, ki.produto_id)
                    if comp is None:
                        raise ValueError("Componente do kit não encontrado.")
                    custo_kit += comp.custo_centavos * ki.quantidade
                    registrar_movimento(
                        session,
                        produto_id=comp.id,
                        tipo="saida",
                        quantidade=ki.quantidade * qtd,
                        origem="venda_kit",
                        referencia_id=venda.id,
                        motivo=f"Venda #{venda.id} — Kit {kit.nome}",
                        auto_commit=False,
                    )

                preco_u = (
                    int(item["preco_unit_centavos"])
                    if "preco_unit_centavos" in item and item["preco_unit_centavos"] not in (None, "")
                    else kit.preco_centavos
                )
                vi = VendaItem(
                    venda_id=venda.id,
                    produto_id=None,
                    kit_id=kit.id,
                    quantidade=qtd,
                    preco_unit_centavos=preco_u,
                    custo_unit_centavos=custo_kit,
                    desconto_centavos=item_desc,
                )
            else:
                raise ValueError("Tipo de item de venda desconhecido.")

            session.add(vi)
            linha_total = (qtd * vi.preco_unit_centavos) - item_desc
            if linha_total < 0:
                raise ValueError("Desconto do item excede o valor do item.")
            subtotal += linha_total

        if desconto_geral > subtotal:
            raise ValueError("Desconto geral não pode ser maior que o subtotal da venda.")

        venda.subtotal_centavos = subtotal
        venda.total_centavos = subtotal - desconto_geral + frete_c

        registrar_auditoria(
            session,
            acao="REGISTRAR_VENDA",
            entidade="venda",
            entidade_id=venda.id,
            detalhes=f"Venda #{venda.id} ({canal}/{forma}) concluída: total {venda.total_centavos} centavos.",
            usuario_id=usuario_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(venda)
    return venda


def cancelar_venda(
    session: Session,
    venda_id: int,
    motivo: str = "",
    usuario_id: int | None = None,
) -> Venda:
    """Cancela venda concluída e devolve todos os itens (inclusive componentes de kits) ao estoque."""
    venda = session.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada.")
    if venda.status == "cancelada":
        raise ValueError("Esta venda já foi cancelada.")

    motivo_final = (motivo or "").strip() or f"Estorno da venda #{venda.id}"
    itens = session.query(VendaItem).filter(VendaItem.venda_id == venda.id).all()

    try:
        for item in itens:
            if item.produto_id is not None:
                registrar_movimento(
                    session,
                    produto_id=item.produto_id,
                    tipo="entrada",
                    quantidade=item.quantidade,
                    origem="cancelamento_venda",
                    referencia_id=venda.id,
                    motivo=motivo_final,
                    auto_commit=False,
                )
            elif item.kit_id is not None:
                kit_itens = (
                    session.query(KitItem).filter(KitItem.kit_id == item.kit_id).all()
                )
                for ki in kit_itens:
                    registrar_movimento(
                        session,
                        produto_id=ki.produto_id,
                        tipo="entrada",
                        quantidade=ki.quantidade * item.quantidade,
                        origem="cancelamento_venda",
                        referencia_id=venda.id,
                        motivo=motivo_final,
                        auto_commit=False,
                    )

        venda.status = "cancelada"
        registrar_auditoria(
            session,
            acao="CANCELAR_VENDA",
            entidade="venda",
            entidade_id=venda.id,
            detalhes=f"Venda #{venda.id} cancelada ({motivo_final}). Estoque devolvido.",
            usuario_id=usuario_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(venda)
    return venda


def obter_venda_detalhe(session: Session, venda_id: int) -> dict[str, Any] | None:
    venda = session.get(Venda, venda_id)
    if venda is None:
        return None
    cliente = session.get(Cliente, venda.cliente_id) if venda.cliente_id else None
    itens_db = session.query(VendaItem).filter(VendaItem.venda_id == venda.id).all()
    produtos_map = {p.id: p for p in session.query(Produto).all()}
    kits_map = {k.id: k for k in session.query(Kit).all()}

    itens = []
    custo_total = 0
    for item in itens_db:
        if item.produto_id is not None:
            p = produtos_map.get(item.produto_id)
            nome = p.nome if p else f"Produto #{item.produto_id}"
            sku = p.sku if p else "—"
            tipo_label = "Produto"
        else:
            k = kits_map.get(item.kit_id) if item.kit_id else None
            nome = k.nome if k else f"Kit #{item.kit_id}"
            sku = f"KIT-{item.kit_id:03d}" if item.kit_id else "KIT"
            tipo_label = "Kit"

        linha_total = (item.quantidade * item.preco_unit_centavos) - item.desconto_centavos
        custo_linha = item.quantidade * item.custo_unit_centavos
        custo_total += custo_linha
        itens.append(
            {
                "id": item.id,
                "tipo": tipo_label,
                "nome": nome,
                "sku": sku,
                "quantidade": item.quantidade,
                "preco_unit_centavos": item.preco_unit_centavos,
                "custo_unit_centavos": item.custo_unit_centavos,
                "desconto_centavos": item.desconto_centavos,
                "subtotal_centavos": linha_total,
            }
        )

    lucro_estimado = (venda.subtotal_centavos - venda.desconto_centavos) - custo_total
    return {
        "venda": venda,
        "cliente_nome": cliente.nome if cliente else "Consumidor não identificado",
        "canal_label": CANAIS_VENDA.get(venda.canal, venda.canal),
        "forma_label": FORMAS_PAGAMENTO.get(venda.forma_pagamento, venda.forma_pagamento),
        "status_label": STATUS_VENDA.get(venda.status, venda.status),
        "custo_total_centavos": custo_total,
        "lucro_estimado_centavos": lucro_estimado,
        "itens": itens,
    }


def listar_vendas(
    session: Session,
    filtros: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    f = dict(filtros or {})
    canal = str(f.get("canal", "") or "").strip()
    forma = str(f.get("forma_pagamento", "") or "").strip()
    status = str(f.get("status", "") or "").strip()
    data_inicio = str(f.get("data_inicio", "") or "").strip()
    data_fim = str(f.get("data_fim", "") or "").strip()
    busca = str(f.get("busca", "") or "").strip().lower()

    query = session.query(Venda)
    if canal in CANAIS_VENDA:
        query = query.filter(Venda.canal == canal)
    if forma in FORMAS_PAGAMENTO:
        query = query.filter(Venda.forma_pagamento == forma)
    if status in STATUS_VENDA:
        query = query.filter(Venda.status == status)
    if data_inicio:
        query = query.filter(Venda.data >= f"{data_inicio}T00:00:00")
    if data_fim:
        query = query.filter(Venda.data <= f"{data_fim}T23:59:59")

    vendas = query.order_by(Venda.id.desc()).all()
    clientes_map = {c.id: c.nome for c in session.query(Cliente).all()}

    itens_por_venda: dict[int, list[VendaItem]] = {}
    for vi in session.query(VendaItem).all():
        itens_por_venda.setdefault(vi.venda_id, []).append(vi)

    resultado = []
    for v in vendas:
        cliente_nome = clientes_map.get(v.cliente_id, "Consumidor não identificado")
        if busca and busca not in cliente_nome.lower() and busca not in f"#{v.id}" and busca not in v.observacoes.lower():
            continue
        vis = itens_por_venda.get(v.id, [])
        custo_total = sum(vi.quantidade * vi.custo_unit_centavos for vi in vis)
        lucro = (v.subtotal_centavos - v.desconto_centavos) - custo_total
        resultado.append(
            {
                "id": v.id,
                "data": v.data,
                "cliente_nome": cliente_nome,
                "canal": v.canal,
                "canal_label": CANAIS_VENDA.get(v.canal, v.canal),
                "forma_pagamento": v.forma_pagamento,
                "forma_label": FORMAS_PAGAMENTO.get(v.forma_pagamento, v.forma_pagamento),
                "status": v.status,
                "status_label": STATUS_VENDA.get(v.status, v.status),
                "total_centavos": v.total_centavos,
                "lucro_centavos": lucro,
                "qtd_itens": sum(vi.quantidade for vi in vis),
            }
        )
    return resultado


def resumo_vendas_hoje(session: Session, data_hoje_iso: str | None = None) -> dict[str, int]:
    """Calcula quantidade, faturamento e lucro bruto do dia atual (somente vendas concluídas)."""
    dia = data_hoje_iso or datetime.now(timezone.utc).date().isoformat()
    vendas = (
        session.query(Venda)
        .filter(Venda.status == "concluida", Venda.data.startswith(dia))
        .all()
    )
    if not vendas:
        return {"qtd": 0, "faturamento_centavos": 0, "lucro_centavos": 0}

    ids = [v.id for v in vendas]
    vis = session.query(VendaItem).filter(VendaItem.venda_id.in_(ids)).all()
    custo_total = sum(vi.quantidade * vi.custo_unit_centavos for vi in vis)
    faturamento = sum(v.total_centavos for v in vendas)
    receita_produtos = sum(v.subtotal_centavos - v.desconto_centavos for v in vendas)
    return {
        "qtd": len(vendas),
        "faturamento_centavos": faturamento,
        "lucro_centavos": receita_produtos - custo_total,
    }
