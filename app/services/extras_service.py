import csv
import io
from typing import Any
import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Fornecedor, Nicho, Produto
from app.services.audit_service import registrar_auditoria
from app.services.produto_service import criar_produto

COLUNAS_MODELO = [
    "nome",
    "sku",
    "codigo_barras",
    "custo",
    "preco",
    "estoque_inicial",
    "estoque_minimo",
    "unidade",
    "nicho",
    "fornecedor",
    "descricao",
]


def gerar_barras_svg(codigo: str, altura: int = 38) -> str:
    """Gera código de barras SVG local determinístico sem dependência externa."""
    texto = (codigo or "").strip() or "000000"
    padrao_barras: list[int] = [2, 1, 1, 2, 1, 2]  # guarda inicial
    for ch in texto:
        val = ord(ch)
        padrao_barras.extend([
            1 + (val % 2),
            1 + ((val >> 1) % 2),
            1 + ((val >> 2) % 2),
            1 + ((val >> 3) % 2),
            1 + ((val >> 4) % 2),
            1,
        ])
    padrao_barras.extend([2, 1, 1, 2, 1, 2])  # guarda final

    rects = []
    x = 4
    desenhar = True
    for largura in padrao_barras:
        w = largura * 1.5
        if desenhar:
            rects.append(f'<rect x="{x:.1f}" y="2" width="{w:.1f}" height="{altura}" fill="#111827"/>')
        x += w
        desenhar = not desenhar

    largura_total = x + 4
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura_total:.0f} {altura + 4}" '
        f'width="100%" height="{altura}" role="img" aria-label="Código {texto}">'
        + "".join(rects)
        + "</svg>"
    )


def _para_float(valor: Any, padrao: float = 0.0) -> float:
    if valor in (None, ""):
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)
    limpo = str(valor).strip().replace("R$", "").replace("US$", "").replace(" ", "")
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return padrao


def calcular_custo_importacao(
    valor_lote: Any,
    moeda: str = "USD",
    cotacao_usd: Any = 5.50,
    frete_brl: Any = 0.0,
    imposto_pct: Any = 0.0,
    outros_brl: Any = 0.0,
    quantidade: Any = 1,
    margem_alvo_pct: Any = 45.0,
    taxa_venda_pct: Any = 0.0,
) -> dict[str, Any]:
    """Calcula custo unitário real em R$ e preço sugerido considerando margem e taxas."""
    qtd = max(1, int(_para_float(quantidade, 1)))
    val_lote = max(0.0, _para_float(valor_lote, 0.0))
    cotacao = max(0.01, _para_float(cotacao_usd, 5.50))
    frete = max(0.0, _para_float(frete_brl, 0.0))
    imp_pct = max(0.0, _para_float(imposto_pct, 0.0))
    outros = max(0.0, _para_float(outros_brl, 0.0))
    margem_alvo = max(0.0, min(90.0, _para_float(margem_alvo_pct, 45.0)))
    taxa_venda = max(0.0, min(50.0, _para_float(taxa_venda_pct, 0.0)))

    moeda_norm = (moeda or "USD").strip().upper()
    base_brl = val_lote * cotacao if moeda_norm == "USD" else val_lote
    imposto_brl = base_brl * (imp_pct / 100.0)
    total_lote_brl = base_brl + imposto_brl + frete + outros
    custo_unit_brl = total_lote_brl / qtd
    custo_unit_centavos = int(round(custo_unit_brl * 100))

    soma_pct = margem_alvo + taxa_venda
    aviso = ""
    if soma_pct >= 95.0:
        divisor = 0.05
        aviso = "A soma de margem alvo + taxa de venda está muito alta (>= 95%); preço limitado."
    else:
        divisor = 1.0 - (soma_pct / 100.0)

    preco_sugerido_centavos = int(round(custo_unit_centavos / divisor)) if custo_unit_centavos > 0 else 0
    taxa_unit_centavos = int(round(preco_sugerido_centavos * (taxa_venda / 100.0)))
    lucro_unit_centavos = preco_sugerido_centavos - taxa_unit_centavos - custo_unit_centavos
    margem_real_pct = (
        round((lucro_unit_centavos / preco_sugerido_centavos) * 100, 1)
        if preco_sugerido_centavos > 0
        else 0.0
    )

    return {
        "quantidade": qtd,
        "moeda": moeda_norm,
        "base_brl_centavos": int(round(base_brl * 100)),
        "imposto_brl_centavos": int(round(imposto_brl * 100)),
        "total_lote_centavos": int(round(total_lote_brl * 100)),
        "custo_unit_centavos": custo_unit_centavos,
        "preco_sugerido_centavos": preco_sugerido_centavos,
        "taxa_unit_centavos": taxa_unit_centavos,
        "lucro_unit_centavos": lucro_unit_centavos,
        "lucro_lote_centavos": lucro_unit_centavos * qtd,
        "margem_real_pct": margem_real_pct,
        "aviso": aviso,
    }


def gerar_modelo_importacao_xlsx() -> bytes:
    """Gera planilha modelo .xlsx com cabeçalho padrão e linha de exemplo."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(COLUNAS_MODELO)

    fill = PatternFill(start_color="F5F4F0", end_color="F5F4F0", fill_type="solid")
    bold = Font(bold=True)
    for col_idx in range(1, len(COLUNAS_MODELO) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = bold
        cell.fill = fill
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 18

    ws.append([
        "Caneca Exemplo Presente",
        "EX-CAN-01",
        "7890000000019",
        "12,50",
        "32,90",
        10,
        3,
        "un",
        "Presentes Personalizados",
        "",
        "Linha exemplo - substitua pelos seus produtos",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ler_linhas_planilha(conteudo_bytes: bytes, nome_arquivo: str) -> list[dict[str, str]]:
    ext = (nome_arquivo or "").lower().rsplit(".", 1)[-1]
    linhas: list[dict[str, str]] = []

    if ext == "xlsx":
        wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h or "").strip().lower() for h in rows[0]]
        for row in rows[1:]:
            if not any(v not in (None, "") for v in row):
                continue
            item = {
                headers[idx]: ("" if idx >= len(row) or row[idx] is None else str(row[idx]).strip())
                for idx in range(len(headers))
                if headers[idx]
            }
            linhas.append(item)
        return linhas

    if ext == "csv":
        try:
            texto = conteudo_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = conteudo_bytes.decode("latin-1")
        primeira = texto.splitlines()[0] if texto.splitlines() else ""
        delim = ";" if primeira.count(";") >= primeira.count(",") else ","
        reader = csv.DictReader(io.StringIO(texto), delimiter=delim)
        for row in reader:
            item = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items() if k}
            if any(item.values()):
                linhas.append(item)
        return linhas

    raise ValueError("Formato inválido. Envie um arquivo .xlsx ou .csv.")


def importar_produtos_planilha(
    session: Session,
    conteudo_bytes: bytes,
    nome_arquivo: str,
    usuario_id: int | None = None,
) -> dict[str, Any]:
    """Importa produtos em lote a partir de .xlsx ou .csv preservando auditoria e evitando duplicados."""
    linhas = _ler_linhas_planilha(conteudo_bytes, nome_arquivo)
    if not linhas:
        raise ValueError("A planilha enviada está vazia.")

    nichos_por_nome = {n.nome.strip().lower(): n.id for n in session.query(Nicho).all()}
    forns_por_nome = {f.nome.strip().lower(): f.id for f in session.query(Fornecedor).all()}

    criados = 0
    duplicados = 0
    erros: list[str] = []

    for idx, linha in enumerate(linhas, start=2):
        nome = (linha.get("nome") or "").strip()
        sku = (linha.get("sku") or "").strip().upper()
        barras = (linha.get("codigo_barras") or "").strip()

        if not nome or not sku:
            erros.append(f"Linha {idx}: 'nome' e 'sku' são obrigatórios.")
            continue

        existe_sku = session.query(Produto).filter(func.upper(Produto.sku) == sku).first()
        existe_barras = (
            session.query(Produto).filter(Produto.codigo_barras == barras).first()
            if barras
            else None
        )
        if existe_sku is not None or existe_barras is not None:
            duplicados += 1
            continue

        nicho_nome = (linha.get("nicho") or "").strip().lower()
        nicho_ids = [nichos_por_nome[nicho_nome]] if nicho_nome in nichos_por_nome else []

        forn_nome = (linha.get("fornecedor") or "").strip().lower()
        forn_id = forns_por_nome.get(forn_nome)

        try:
            criar_produto(
                session,
                {
                    "nome": nome,
                    "sku": sku,
                    "codigo_barras": barras,
                    "custo": linha.get("custo") or "0,00",
                    "preco": linha.get("preco") or "0,00",
                    "estoque_inicial": linha.get("estoque_inicial") or "0",
                    "estoque_minimo": linha.get("estoque_minimo") or "0",
                    "unidade": linha.get("unidade") or "un",
                    "fornecedor_id": forn_id,
                    "descricao": linha.get("descricao") or "",
                },
                nicho_ids=nicho_ids,
                usuario_id=usuario_id,
            )
            criados += 1
        except ValueError as exc:
            erros.append(f"Linha {idx} ({sku}): {exc}")

    registrar_auditoria(
        session,
        acao="IMPORTAR_LOTE_PRODUTOS",
        entidade="produto",
        detalhes=f"Arquivo '{nome_arquivo}': {criados} criado(s), {duplicados} duplicado(s), {len(erros)} erro(s).",
        usuario_id=usuario_id,
    )
    session.commit()

    return {
        "criados": criados,
        "duplicados": duplicados,
        "erros": erros,
        "total_lido": len(linhas),
    }
