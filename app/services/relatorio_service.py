import csv
from datetime import datetime, timezone
import io
from typing import Any, Mapping
import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session

from app.models import (
    Cliente,
    Compra,
    Fornecedor,
    Kit,
    KitItem,
    Nicho,
    Produto,
    ProdutoNicho,
    Venda,
    VendaItem,
)
from app.services.cliente_service import listar_clientes
from app.services.estoque_service import listar_posicao_estoque
from app.services.venda_service import CANAIS_VENDA, FORMAS_PAGAMENTO


def _centavos_para_float(centavos: int) -> float:
    return round((centavos or 0) / 100.0, 2)


def _formatar_brl_csv(centavos: int) -> str:
    return f"{(centavos or 0) / 100:.2f}".replace(".", ",")


def gerar_relatorio_completo(
    session: Session,
    filtros: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Consolida indicadores financeiros, Curva ABC, nichos, estoque e clientes do período."""
    f = dict(filtros or {})
    data_inicio = str(f.get("data_inicio", "") or "").strip()
    data_fim = str(f.get("data_fim", "") or "").strip()
    canal_filtro = str(f.get("canal", "") or "").strip()
    forma_filtro = str(f.get("forma_pagamento", "") or "").strip()
    nicho_filtro = str(f.get("nicho_id", "") or "").strip()
    mes_aniv = str(f.get("mes_aniversario", "") or "").strip()
    if not mes_aniv.isdigit():
        mes_aniv = str(datetime.now(timezone.utc).month)

    q_vendas = session.query(Venda)
    if data_inicio:
        q_vendas = q_vendas.filter(Venda.data >= f"{data_inicio}T00:00:00")
    if data_fim:
        q_vendas = q_vendas.filter(Venda.data <= f"{data_fim}T23:59:59")
    if canal_filtro in CANAIS_VENDA:
        q_vendas = q_vendas.filter(Venda.canal == canal_filtro)
    if forma_filtro in FORMAS_PAGAMENTO:
        q_vendas = q_vendas.filter(Venda.forma_pagamento == forma_filtro)

    todas_vendas = q_vendas.order_by(Venda.id.desc()).all()
    concluidas = [v for v in todas_vendas if v.status == "concluida"]
    canceladas = [v for v in todas_vendas if v.status == "cancelada"]

    ids_concluidas = [v.id for v in concluidas]
    itens_venda = (
        session.query(VendaItem).filter(VendaItem.venda_id.in_(ids_concluidas)).all()
        if ids_concluidas
        else []
    )

    produtos_map = {p.id: p for p in session.query(Produto).all()}
    kits_map = {k.id: k for k in session.query(Kit).all()}
    nichos_map = {n.id: n for n in session.query(Nicho).all()}
    clientes_map = {c.id: c for c in session.query(Cliente).all()}

    mapa_prod_nichos: dict[int, list[int]] = {}
    for pn in session.query(ProdutoNicho).all():
        if pn.nicho_id in nichos_map:
            mapa_prod_nichos.setdefault(pn.produto_id, []).append(pn.nicho_id)

    mapa_kit_itens: dict[int, list[KitItem]] = {}
    for ki in session.query(KitItem).all():
        mapa_kit_itens.setdefault(ki.kit_id, []).append(ki)

    itens_por_venda: dict[int, list[VendaItem]] = {}
    for vi in itens_venda:
        itens_por_venda.setdefault(vi.venda_id, []).append(vi)

    faturamento = sum(v.total_centavos for v in concluidas)
    descontos = sum(v.desconto_centavos for v in concluidas) + sum(vi.desconto_centavos for vi in itens_venda)
    fretes = sum(v.frete_centavos for v in concluidas)
    custo_total = sum(vi.quantidade * vi.custo_unit_centavos for vi in itens_venda)
    receita_produtos = sum(v.subtotal_centavos - v.desconto_centavos for v in concluidas)
    lucro_total = receita_produtos - custo_total
    margem_pct = round((lucro_total / receita_produtos) * 100, 1) if receita_produtos > 0 else 0.0
    qtd_vendas = len(concluidas)
    ticket_medio = (faturamento // qtd_vendas) if qtd_vendas > 0 else 0

    resumo = {
        "qtd_vendas": qtd_vendas,
        "qtd_canceladas": len(canceladas),
        "faturamento_centavos": faturamento,
        "descontos_centavos": descontos,
        "fretes_centavos": fretes,
        "custo_centavos": custo_total,
        "lucro_centavos": lucro_total,
        "margem_pct": margem_pct,
        "ticket_medio_centavos": ticket_medio,
    }

    # Quebra por Canal, Forma de Pagamento, Dia e Top Clientes
    canal_agg: dict[str, dict[str, int]] = {}
    forma_agg: dict[str, dict[str, int]] = {}
    dia_agg: dict[str, dict[str, int]] = {}
    cli_agg: dict[int, dict[str, int]] = {}
    vendas_lista: list[dict[str, Any]] = []

    for v in concluidas:
        vis = itens_por_venda.get(v.id, [])
        custo_v = sum(vi.quantidade * vi.custo_unit_centavos for vi in vis)
        lucro_v = (v.subtotal_centavos - v.desconto_centavos) - custo_v

        c_bucket = canal_agg.setdefault(v.canal, {"qtd": 0, "fat": 0, "lucro": 0})
        c_bucket["qtd"] += 1
        c_bucket["fat"] += v.total_centavos
        c_bucket["lucro"] += lucro_v

        p_bucket = forma_agg.setdefault(v.forma_pagamento, {"qtd": 0, "fat": 0, "lucro": 0})
        p_bucket["qtd"] += 1
        p_bucket["fat"] += v.total_centavos
        p_bucket["lucro"] += lucro_v

        dia = v.data[:10]
        d_bucket = dia_agg.setdefault(dia, {"qtd": 0, "fat": 0, "lucro": 0})
        d_bucket["qtd"] += 1
        d_bucket["fat"] += v.total_centavos
        d_bucket["lucro"] += lucro_v

        if v.cliente_id:
            cl_b = cli_agg.setdefault(v.cliente_id, {"qtd": 0, "fat": 0})
            cl_b["qtd"] += 1
            cl_b["fat"] += v.total_centavos

        cli = clientes_map.get(v.cliente_id) if v.cliente_id else None
        vendas_lista.append(
            {
                "id": v.id,
                "data": v.data[:16].replace("T", " "),
                "cliente_nome": cli.nome if cli else "Consumidor não identificado",
                "canal_label": CANAIS_VENDA.get(v.canal, v.canal),
                "forma_label": FORMAS_PAGAMENTO.get(v.forma_pagamento, v.forma_pagamento),
                "total_centavos": v.total_centavos,
                "custo_centavos": custo_v,
                "lucro_centavos": lucro_v,
            }
        )

    por_canal = sorted(
        [
            {
                "canal": ch,
                "canal_label": CANAIS_VENDA.get(ch, ch),
                "qtd": b["qtd"],
                "faturamento_centavos": b["fat"],
                "lucro_centavos": b["lucro"],
                "pct": round((b["fat"] / faturamento) * 100, 1) if faturamento > 0 else 0.0,
            }
            for ch, b in canal_agg.items()
        ],
        key=lambda x: x["faturamento_centavos"],
        reverse=True,
    )

    por_pagamento = sorted(
        [
            {
                "forma": fm,
                "forma_label": FORMAS_PAGAMENTO.get(fm, fm),
                "qtd": b["qtd"],
                "faturamento_centavos": b["fat"],
                "lucro_centavos": b["lucro"],
                "pct": round((b["fat"] / faturamento) * 100, 1) if faturamento > 0 else 0.0,
            }
            for fm, b in forma_agg.items()
        ],
        key=lambda x: x["faturamento_centavos"],
        reverse=True,
    )

    max_dia_fat = max((b["fat"] for b in dia_agg.values()), default=0)
    por_dia = [
        {
            "data": d,
            "qtd": b["qtd"],
            "faturamento_centavos": b["fat"],
            "lucro_centavos": b["lucro"],
            "largura_pct": round((b["fat"] / max_dia_fat) * 100, 1) if max_dia_fat > 0 else 0.0,
        }
        for d, b in sorted(dia_agg.items())
    ]

    # Curva ABC, Desempenho por Nicho e rastreamento de produtos vendidos
    abc_agg: dict[tuple[str, int], dict[str, Any]] = {}
    nicho_agg: dict[int | None, dict[str, Any]] = {}
    produtos_vendidos_ids: set[int] = set()
    nid_filtro_int = int(nicho_filtro) if nicho_filtro.isdigit() else None

    for vi in itens_venda:
        receita_item = (vi.quantidade * vi.preco_unit_centavos) - vi.desconto_centavos
        custo_item = vi.quantidade * vi.custo_unit_centavos
        lucro_item = receita_item - custo_item

        if vi.produto_id is not None:
            produtos_vendidos_ids.add(vi.produto_id)
            p = produtos_map.get(vi.produto_id)
            nichos_item = mapa_prod_nichos.get(vi.produto_id, [])
            chave = ("produto", vi.produto_id)
            nome = p.nome if p else f"Produto #{vi.produto_id}"
            sku = p.sku if p else "—"
        else:
            kit_id = vi.kit_id or 0
            k = kits_map.get(kit_id)
            nichos_item = [k.nicho_id] if (k and k.nicho_id in nichos_map) else []
            for ki in mapa_kit_itens.get(kit_id, []):
                produtos_vendidos_ids.add(ki.produto_id)
            chave = ("kit", kit_id)
            nome = k.nome if k else f"Kit #{kit_id}"
            sku = f"KIT-{kit_id:03d}"

        # Agrega por nicho (divide igualmente se o produto pertence a múltiplos nichos)
        alvos_nicho = nichos_item if nichos_item else [None]
        divisor = len(alvos_nicho)
        for idx_n, nid in enumerate(alvos_nicho):
            fat_parte = (receita_item // divisor) + (receita_item % divisor if idx_n == 0 else 0)
            custo_parte = (custo_item // divisor) + (custo_item % divisor if idx_n == 0 else 0)
            lucro_parte = fat_parte - custo_parte
            nb = nicho_agg.setdefault(
                nid,
                {"qtd": 0, "fat": 0, "custo": 0, "lucro": 0},
            )
            nb["qtd"] += vi.quantidade
            nb["fat"] += fat_parte
            nb["custo"] += custo_parte
            nb["lucro"] += lucro_parte

        if nid_filtro_int is not None and nid_filtro_int not in nichos_item:
            continue

        ab = abc_agg.setdefault(
            chave,
            {
                "tipo": "Kit" if chave[0] == "kit" else "Produto",
                "id": chave[1],
                "nome": nome,
                "sku": sku,
                "quantidade": 0,
                "faturamento_centavos": 0,
                "custo_centavos": 0,
                "lucro_centavos": 0,
            },
        )
        ab["quantidade"] += vi.quantidade
        ab["faturamento_centavos"] += receita_item
        ab["custo_centavos"] += custo_item
        ab["lucro_centavos"] += lucro_item

    curva_abc = sorted(abc_agg.values(), key=lambda x: x["faturamento_centavos"], reverse=True)
    soma_abc = sum(x["faturamento_centavos"] for x in curva_abc)
    acumulado = 0.0
    for idx_abc, item in enumerate(curva_abc):
        fat_i = item["faturamento_centavos"]
        pct = (fat_i / soma_abc) * 100 if soma_abc > 0 else 0.0
        antes = acumulado
        acumulado = min(100.0, acumulado + pct)
        item["pct_participacao"] = round(pct, 1)
        item["pct_acumulada"] = round(acumulado, 1)
        item["margem_pct"] = (
            round((item["lucro_centavos"] / fat_i) * 100, 1) if fat_i > 0 else 0.0
        )
        if idx_abc == 0 or antes < 80.0:
            item["classe"] = "A"
        elif antes < 95.0:
            item["classe"] = "B"
        else:
            item["classe"] = "C"

    soma_nichos_fat = sum(b["fat"] for b in nicho_agg.values())
    por_nicho = []
    for nid, b in nicho_agg.items():
        if nid_filtro_int is not None and nid != nid_filtro_int:
            continue
        nicho_obj = nichos_map.get(nid) if nid is not None else None
        fat_n = b["fat"]
        por_nicho.append(
            {
                "nicho_id": nid,
                "nome": nicho_obj.nome if nicho_obj else "Sem nicho",
                "cor": nicho_obj.cor if nicho_obj else "#6b7280",
                "qtd_unidades": b["qtd"],
                "faturamento_centavos": fat_n,
                "custo_centavos": b["custo"],
                "lucro_centavos": b["lucro"],
                "margem_pct": round((b["lucro"] / fat_n) * 100, 1) if fat_n > 0 else 0.0,
                "pct": round((fat_n / soma_nichos_fat) * 100, 1) if soma_nichos_fat > 0 else 0.0,
            }
        )
    por_nicho.sort(key=lambda x: x["faturamento_centavos"], reverse=True)

    # Estoque crítico e parado
    posicao = listar_posicao_estoque(session, nicho_id=nicho_filtro)
    estoque_critico = []
    estoque_parado = []
    for item in posicao:
        if item["estoque_status"] in ("zerado", "baixo"):
            alvo = max(item["estoque_minimo"] * 2, item["estoque_minimo"] + 2, 1)
            item_copy = dict(item)
            item_copy["sugestao_reposicao"] = max(1, alvo - max(0, item["estoque_atual"]))
            estoque_critico.append(item_copy)
        if item["estoque_atual"] > 0 and item["id"] not in produtos_vendidos_ids:
            estoque_parado.append(dict(item))

    # Compras recebidas no período por fornecedor
    q_comp = session.query(Compra).filter(Compra.status == "recebida")
    if data_inicio:
        q_comp = q_comp.filter(Compra.data >= f"{data_inicio}T00:00:00")
    if data_fim:
        q_comp = q_comp.filter(Compra.data <= f"{data_fim}T23:59:59")
    forns_map = {fn.id: fn.nome for fn in session.query(Fornecedor).all()}
    comp_agg: dict[str, dict[str, int]] = {}
    for c in q_comp.all():
        nome_fn = forns_map.get(c.fornecedor_id, "Compra avulsa / sem fornecedor")
        cb = comp_agg.setdefault(nome_fn, {"qtd": 0, "total": 0, "extras": 0})
        cb["qtd"] += 1
        cb["total"] += c.total_centavos
        cb["extras"] += c.frete_centavos + c.impostos_centavos + c.outros_custos_centavos
    compras_fornecedores = sorted(
        [
            {
                "fornecedor_nome": nome_fn,
                "qtd_pedidos": b["qtd"],
                "total_centavos": b["total"],
                "extras_centavos": b["extras"],
            }
            for nome_fn, b in comp_agg.items()
        ],
        key=lambda x: x["total_centavos"],
        reverse=True,
    )

    top_clientes = sorted(
        [
            {
                "cliente_id": cid,
                "nome": clientes_map[cid].nome if cid in clientes_map else f"Cliente #{cid}",
                "qtd_compras": b["qtd"],
                "total_centavos": b["fat"],
            }
            for cid, b in cli_agg.items()
        ],
        key=lambda x: x["total_centavos"],
        reverse=True,
    )[:15]

    aniversariantes = listar_clientes(session, mes_aniversario=mes_aniv)

    return {
        "resumo": resumo,
        "por_canal": por_canal,
        "por_pagamento": por_pagamento,
        "por_dia": por_dia,
        "curva_abc": curva_abc,
        "por_nicho": por_nicho,
        "estoque_critico": estoque_critico,
        "estoque_parado": estoque_parado,
        "compras_fornecedores": compras_fornecedores,
        "top_clientes": top_clientes,
        "aniversariantes": aniversariantes,
        "vendas_lista": vendas_lista,
        "mes_aniversario": mes_aniv,
    }


def _estilizar_aba(ws, cabecalhos: list[str], larguras: list[int] | None = None) -> None:
    ws.append(cabecalhos)
    fill = PatternFill(start_color="F5F4F0", end_color="F5F4F0", fill_type="solid")
    bold = Font(bold=True)
    for col_idx in range(1, len(cabecalhos) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = bold
        cell.fill = fill
    if larguras:
        for idx, largura in enumerate(larguras, start=1):
            col_letter = openpyxl.utils.get_column_letter(idx)
            ws.column_dimensions[col_letter].width = largura


def exportar_relatorio_xlsx(rel: dict[str, Any], nome_loja: str = "Loja Itamarandiba") -> bytes:
    """Exporta todas as visões do relatório gerencial em pasta de trabalho Excel (.xlsx)."""
    wb = openpyxl.Workbook()
    fmt_moeda = 'R$ #,##0.00'

    # 1. Resumo Executivo
    ws_res = wb.active
    ws_res.title = "Resumo Executivo"
    _estilizar_aba(ws_res, [f"{nome_loja} — Indicador", "Valor"], [38, 24])
    res = rel["resumo"]
    linhas_resumo = [
        ("Vendas concluídas", res["qtd_vendas"], None),
        ("Vendas canceladas", res["qtd_canceladas"], None),
        ("Faturamento líquido", _centavos_para_float(res["faturamento_centavos"]), fmt_moeda),
        ("Custo dos produtos (CMV)", _centavos_para_float(res["custo_centavos"]), fmt_moeda),
        ("Lucro bruto real", _centavos_para_float(res["lucro_centavos"]), fmt_moeda),
        ("Margem média (%)", res["margem_pct"], "0.0"),
        ("Ticket médio", _centavos_para_float(res["ticket_medio_centavos"]), fmt_moeda),
    ]
    for label, val, num_fmt in linhas_resumo:
        ws_res.append([label, val])
        if num_fmt:
            ws_res.cell(row=ws_res.max_row, column=2).number_format = num_fmt

    ws_res.append([])
    ws_res.append(["Vendas por Canal", "Qtd", "Faturamento", "Lucro Bruto", "% Participação"])
    for c in rel["por_canal"]:
        ws_res.append(
            [
                c["canal_label"],
                c["qtd"],
                _centavos_para_float(c["faturamento_centavos"]),
                _centavos_para_float(c["lucro_centavos"]),
                c["pct"],
            ]
        )
        ws_res.cell(row=ws_res.max_row, column=3).number_format = fmt_moeda
        ws_res.cell(row=ws_res.max_row, column=4).number_format = fmt_moeda

    # 2. Curva ABC
    ws_abc = wb.create_sheet("Curva ABC")
    _estilizar_aba(
        ws_abc,
        ["Classe", "Tipo", "SKU", "Item", "Qtd", "Faturamento", "Lucro Bruto", "Margem %", "% Acumulada"],
        [10, 12, 16, 34, 10, 16, 16, 12, 14],
    )
    for item in rel["curva_abc"]:
        ws_abc.append(
            [
                item["classe"],
                item["tipo"],
                item["sku"],
                item["nome"],
                item["quantidade"],
                _centavos_para_float(item["faturamento_centavos"]),
                _centavos_para_float(item["lucro_centavos"]),
                item["margem_pct"],
                item["pct_acumulada"],
            ]
        )
        ws_abc.cell(row=ws_abc.max_row, column=6).number_format = fmt_moeda
        ws_abc.cell(row=ws_abc.max_row, column=7).number_format = fmt_moeda

    # 3. Nichos
    ws_nichos = wb.create_sheet("Nichos")
    _estilizar_aba(
        ws_nichos,
        ["Nicho", "Unidades", "Faturamento", "Lucro Bruto", "Margem %", "% Participação"],
        [30, 12, 16, 16, 12, 15],
    )
    for n in rel["por_nicho"]:
        ws_nichos.append(
            [
                n["nome"],
                n["qtd_unidades"],
                _centavos_para_float(n["faturamento_centavos"]),
                _centavos_para_float(n["lucro_centavos"]),
                n["margem_pct"],
                n["pct"],
            ]
        )
        ws_nichos.cell(row=ws_nichos.max_row, column=3).number_format = fmt_moeda
        ws_nichos.cell(row=ws_nichos.max_row, column=4).number_format = fmt_moeda

    # 4. Estoque e Reposição
    ws_est = wb.create_sheet("Estoque e Reposição")
    _estilizar_aba(
        ws_est,
        ["Situação", "SKU", "Produto", "Atual", "Mínimo", "Sugestão Compra", "Valor em Custo"],
        [16, 16, 34, 10, 10, 16, 16],
    )
    for e in rel["estoque_critico"]:
        ws_est.append(
            [
                "Crítico/Baixo",
                e["sku"],
                e["nome"],
                e["estoque_atual"],
                e["estoque_minimo"],
                e["sugestao_reposicao"],
                _centavos_para_float(e["valor_custo_total_centavos"]),
            ]
        )
        ws_est.cell(row=ws_est.max_row, column=7).number_format = fmt_moeda
    for p in rel["estoque_parado"]:
        ws_est.append(
            [
                "Sem giro no período",
                p["sku"],
                p["nome"],
                p["estoque_atual"],
                p["estoque_minimo"],
                0,
                _centavos_para_float(p["valor_custo_total_centavos"]),
            ]
        )
        ws_est.cell(row=ws_est.max_row, column=7).number_format = fmt_moeda

    # 5. Vendas do Período
    ws_v = wb.create_sheet("Vendas do Período")
    _estilizar_aba(
        ws_v,
        ["# Venda", "Data/Hora", "Cliente", "Canal", "Pagamento", "Total", "Lucro Bruto"],
        [10, 18, 28, 16, 14, 16, 16],
    )
    for v in rel["vendas_lista"]:
        ws_v.append(
            [
                v["id"],
                v["data"],
                v["cliente_nome"],
                v["canal_label"],
                v["forma_label"],
                _centavos_para_float(v["total_centavos"]),
                _centavos_para_float(v["lucro_centavos"]),
            ]
        )
        ws_v.cell(row=ws_v.max_row, column=6).number_format = fmt_moeda
        ws_v.cell(row=ws_v.max_row, column=7).number_format = fmt_moeda

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_relatorio_csv(rel: dict[str, Any], secao: str = "vendas") -> bytes:
    """Exporta seção escolhida em CSV separado por ';' com UTF-8 BOM para Excel Brasil."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")

    if secao == "abc":
        writer.writerow(["Classe", "Tipo", "SKU", "Item", "Quantidade", "Faturamento", "Lucro", "Margem %", "% Acumulada"])
        for i in rel["curva_abc"]:
            writer.writerow(
                [
                    i["classe"],
                    i["tipo"],
                    i["sku"],
                    i["nome"],
                    i["quantidade"],
                    _formatar_brl_csv(i["faturamento_centavos"]),
                    _formatar_brl_csv(i["lucro_centavos"]),
                    f"{i['margem_pct']:.1f}".replace(".", ","),
                    f"{i['pct_acumulada']:.1f}".replace(".", ","),
                ]
            )
    elif secao == "nichos":
        writer.writerow(["Nicho", "Unidades", "Faturamento", "Lucro", "Margem %", "% Participacao"])
        for n in rel["por_nicho"]:
            writer.writerow(
                [
                    n["nome"],
                    n["qtd_unidades"],
                    _formatar_brl_csv(n["faturamento_centavos"]),
                    _formatar_brl_csv(n["lucro_centavos"]),
                    f"{n['margem_pct']:.1f}".replace(".", ","),
                    f"{n['pct']:.1f}".replace(".", ","),
                ]
            )
    elif secao == "estoque":
        writer.writerow(["Situacao", "SKU", "Produto", "Atual", "Minimo", "Sugestao Reposicao", "Valor Custo"])
        for e in rel["estoque_critico"]:
            writer.writerow(
                [
                    "Critico/Baixo",
                    e["sku"],
                    e["nome"],
                    e["estoque_atual"],
                    e["estoque_minimo"],
                    e["sugestao_reposicao"],
                    _formatar_brl_csv(e["valor_custo_total_centavos"]),
                ]
            )
        for p in rel["estoque_parado"]:
            writer.writerow(
                [
                    "Sem giro no periodo",
                    p["sku"],
                    p["nome"],
                    p["estoque_atual"],
                    p["estoque_minimo"],
                    0,
                    _formatar_brl_csv(p["valor_custo_total_centavos"]),
                ]
            )
    else:
        writer.writerow(["Venda", "Data", "Cliente", "Canal", "Pagamento", "Total", "Lucro Bruto"])
        for v in rel["vendas_lista"]:
            writer.writerow(
                [
                    v["id"],
                    v["data"],
                    v["cliente_nome"],
                    v["canal_label"],
                    v["forma_label"],
                    _formatar_brl_csv(v["total_centavos"]),
                    _formatar_brl_csv(v["lucro_centavos"]),
                ]
            )

    return buf.getvalue().encode("utf-8-sig")
