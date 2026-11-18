from typing import Any, Mapping
from sqlalchemy import func
from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage

from app.config import Settings
from app.models import (
    Fornecedor,
    MovimentoEstoque,
    Nicho,
    Produto,
    ProdutoImagem,
    ProdutoNicho,
)
from app.models.base import utc_now_iso
from app.services.audit_service import registrar_auditoria
from app.services.imagem_service import remover_arquivos_imagem, salvar_imagem_produto
from app.utils.money import reais_para_centavos


def calcular_margem(custo_centavos: int, preco_centavos: int) -> dict[str, Any]:
    """Calcula lucro em centavos, margem sobre preço (%) e markup (%) sem ponto flutuante monetário."""
    lucro = int(preco_centavos) - int(custo_centavos)
    margem = round((lucro / preco_centavos) * 100, 1) if preco_centavos > 0 else 0.0
    markup = round((lucro / custo_centavos) * 100, 1) if custo_centavos > 0 else 0.0
    return {
        "lucro_centavos": lucro,
        "margem_pct": margem,
        "markup_pct": markup,
    }


def sugerir_sku(session: Session) -> str:
    """Sugere próximo SKU sequencial limpo para cadastro rápido."""
    ultimo_id = session.query(func.max(Produto.id)).scalar() or 0
    return f"PROD-{int(ultimo_id) + 1:04d}"


def _ler_int(valor: Any, campo: str, default: int = 0) -> int:
    if valor is None or str(valor).strip() == "":
        return default
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido para {campo}.") from exc
    if n < 0:
        raise ValueError(f"{campo} não pode ser negativo.")
    return n


def _ler_centavos(dados: Mapping[str, Any], chave_centavos: str, chave_reais: str) -> int:
    if chave_centavos in dados and dados[chave_centavos] not in (None, ""):
        return _ler_int(dados[chave_centavos], chave_reais)
    centavos = reais_para_centavos(dados.get(chave_reais, 0))
    if centavos < 0:
        raise ValueError(f"{chave_reais} não pode ser negativo.")
    return centavos


def _validar_nichos(session: Session, nicho_ids: list[int] | None) -> list[int]:
    if not nicho_ids:
        return []
    limpos: list[int] = []
    for item in nicho_ids:
        try:
            nid = int(item)
        except (TypeError, ValueError):
            continue
        if nid not in limpos:
            limpos.append(nid)
    if not limpos:
        return []
    existentes = {
        row[0] for row in session.query(Nicho.id).filter(Nicho.id.in_(limpos)).all()
    }
    return [nid for nid in limpos if nid in existentes]


def verificar_duplicidades_produto(
    session: Session,
    nome: str = "",
    sku: str = "",
    codigo_barras: str = "",
    excluir_id: int | None = None,
) -> list[str]:
    """Retorna avisos em português quando encontra SKU, código de barras ou nome semelhante."""
    avisos: list[str] = []
    sku_limpo = (sku or "").strip().upper()
    barras_limpo = (codigo_barras or "").strip()
    nome_limpo = (nome or "").strip()

    if sku_limpo:
        q = session.query(Produto).filter(func.upper(Produto.sku) == sku_limpo)
        if excluir_id is not None:
            q = q.filter(Produto.id != excluir_id)
        if p := q.first():
            avisos.append(f"SKU '{sku_limpo}' já pertence a '{p.nome}'.")

    if barras_limpo:
        q = session.query(Produto).filter(Produto.codigo_barras == barras_limpo)
        if excluir_id is not None:
            q = q.filter(Produto.id != excluir_id)
        if p := q.first():
            avisos.append(f"Código de barras '{barras_limpo}' já pertence a '{p.nome}'.")

    if len(nome_limpo) >= 3:
        termos = [t for t in nome_limpo.lower().split() if len(t) >= 3][:3]
        if termos:
            q = session.query(Produto).filter(Produto.ativo == 1)
            if excluir_id is not None:
                q = q.filter(Produto.id != excluir_id)
            similares = []
            for p in q.all():
                nl = p.nome.lower()
                if nome_limpo.lower() in nl or nl in nome_limpo.lower() or all(t in nl for t in termos):
                    similares.append(p.nome)
            if similares:
                amostra = ", ".join(similares[:3])
                avisos.append(f"Produto(s) parecido(s) já cadastrado(s): {amostra}.")

    return avisos


def _preparar_campos_produto(
    session: Session,
    dados: Mapping[str, Any],
    excluir_id: int | None = None,
) -> dict[str, Any]:
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("O nome do produto é obrigatório.")

    sku = str(dados.get("sku") or "").strip().upper()
    if not sku:
        raise ValueError("O SKU do produto é obrigatório.")

    q_sku = session.query(Produto).filter(func.upper(Produto.sku) == sku)
    if excluir_id is not None:
        q_sku = q_sku.filter(Produto.id != excluir_id)
    if q_sku.first() is not None:
        raise ValueError(f"Já existe um produto cadastrado com o SKU '{sku}'.")

    barras_raw = str(dados.get("codigo_barras") or "").strip()
    codigo_barras = barras_raw if barras_raw else None
    if codigo_barras:
        q_barras = session.query(Produto).filter(Produto.codigo_barras == codigo_barras)
        if excluir_id is not None:
            q_barras = q_barras.filter(Produto.id != excluir_id)
        if q_barras.first() is not None:
            raise ValueError(
                f"Já existe um produto cadastrado com o código de barras '{codigo_barras}'."
            )

    fornecedor_raw = dados.get("fornecedor_id")
    fornecedor_id: int | None = None
    if fornecedor_raw not in (None, "", "0"):
        fornecedor_id = _ler_int(fornecedor_raw, "Fornecedor")
        if session.get(Fornecedor, fornecedor_id) is None:
            raise ValueError("Fornecedor selecionado não existe.")

    return {
        "sku": sku,
        "codigo_barras": codigo_barras,
        "nome": nome,
        "descricao": str(dados.get("descricao") or "").strip(),
        "unidade": str(dados.get("unidade") or "un").strip() or "un",
        "custo_centavos": _ler_centavos(dados, "custo_centavos", "custo"),
        "preco_centavos": _ler_centavos(dados, "preco_centavos", "preco"),
        "estoque_minimo": _ler_int(dados.get("estoque_minimo"), "Estoque mínimo", 0),
        "fornecedor_id": fornecedor_id,
    }


def criar_produto(
    session: Session,
    dados: Mapping[str, Any],
    nicho_ids: list[int] | None = None,
    usuario_id: int | None = None,
) -> Produto:
    """Cria produto, vincula nichos e registra movimento caso haja saldo inicial."""
    campos = _preparar_campos_produto(session, dados)
    estoque_inicial = _ler_int(dados.get("estoque_inicial"), "Estoque inicial", 0)
    nichos_validos = _validar_nichos(session, nicho_ids)

    produto = Produto(
        **campos,
        estoque_atual=estoque_inicial,
        ativo=1,
    )
    session.add(produto)
    session.flush()

    for nid in nichos_validos:
        session.add(ProdutoNicho(produto_id=produto.id, nicho_id=nid))

    if estoque_inicial > 0:
        session.add(
            MovimentoEstoque(
                produto_id=produto.id,
                tipo="entrada",
                quantidade=estoque_inicial,
                origem="saldo_inicial",
                referencia_id=produto.id,
                motivo="Saldo inicial informado no cadastro do produto.",
            )
        )

    registrar_auditoria(
        session,
        acao="CRIAR_PRODUTO",
        entidade="produto",
        entidade_id=produto.id,
        detalhes=f"Produto '{produto.nome}' (SKU {produto.sku}) criado; estoque inicial={estoque_inicial}.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(produto)
    return produto


def atualizar_produto(
    session: Session,
    produto_id: int,
    dados: Mapping[str, Any],
    nicho_ids: list[int] | None = None,
    usuario_id: int | None = None,
) -> Produto:
    """Atualiza dados comerciais e nichos do produto preservando estoque_atual intacto."""
    produto = session.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado.")

    campos = _preparar_campos_produto(session, dados, excluir_id=produto_id)
    for chave, valor in campos.items():
        setattr(produto, chave, valor)
    produto.atualizado_em = utc_now_iso()

    if nicho_ids is not None:
        session.query(ProdutoNicho).filter(ProdutoNicho.produto_id == produto_id).delete()
        for nid in _validar_nichos(session, nicho_ids):
            session.add(ProdutoNicho(produto_id=produto_id, nicho_id=nid))

    registrar_auditoria(
        session,
        acao="EDITAR_PRODUTO",
        entidade="produto",
        entidade_id=produto.id,
        detalhes=f"Produto '{produto.nome}' (SKU {produto.sku}) atualizado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(produto)
    return produto


def alternar_ativo_produto(
    session: Session,
    produto_id: int,
    usuario_id: int | None = None,
) -> Produto:
    produto = session.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado.")
    produto.ativo = 0 if produto.ativo else 1
    produto.atualizado_em = utc_now_iso()
    acao = "REATIVAR_PRODUTO" if produto.ativo else "INATIVAR_PRODUTO"
    registrar_auditoria(
        session,
        acao=acao,
        entidade="produto",
        entidade_id=produto.id,
        detalhes=f"Produto '{produto.nome}' marcado como {'ativo' if produto.ativo else 'inativo'}.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(produto)
    return produto


def adicionar_imagens_produto(
    session: Session,
    settings: Settings,
    produto_id: int,
    arquivos: list[FileStorage],
    usuario_id: int | None = None,
) -> list[ProdutoImagem]:
    """Processa e vincula novas fotos enviadas para o produto."""
    produto = session.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado.")

    existentes = (
        session.query(ProdutoImagem)
        .filter(ProdutoImagem.produto_id == produto_id)
        .order_by(ProdutoImagem.ordem, ProdutoImagem.id)
        .all()
    )
    tem_principal = any(img.principal == 1 for img in existentes)
    proxima_ordem = max((img.ordem for img in existentes), default=0) + 1

    criadas: list[ProdutoImagem] = []
    for arquivo in arquivos:
        if arquivo is None or not arquivo.filename:
            continue
        nome_salvo = salvar_imagem_produto(settings, arquivo)
        eh_principal = 1 if (not tem_principal and len(criadas) == 0) else 0
        registro = ProdutoImagem(
            produto_id=produto_id,
            arquivo=nome_salvo,
            principal=eh_principal,
            ordem=proxima_ordem,
        )
        proxima_ordem += 1
        session.add(registro)
        criadas.append(registro)

    if criadas:
        registrar_auditoria(
            session,
            acao="ADICIONAR_IMAGEM_PRODUTO",
            entidade="produto",
            entidade_id=produto_id,
            detalhes=f"{len(criadas)} imagem(ns) adicionada(s) ao produto '{produto.nome}'.",
            usuario_id=usuario_id,
        )
        session.commit()
        for img in criadas:
            session.refresh(img)

    return criadas


def definir_imagem_principal(
    session: Session,
    produto_id: int,
    imagem_id: int,
    usuario_id: int | None = None,
) -> None:
    alvo = (
        session.query(ProdutoImagem)
        .filter(ProdutoImagem.id == imagem_id, ProdutoImagem.produto_id == produto_id)
        .first()
    )
    if alvo is None:
        raise ValueError("Imagem não encontrada para este produto.")

    session.query(ProdutoImagem).filter(ProdutoImagem.produto_id == produto_id).update(
        {"principal": 0}
    )
    alvo.principal = 1
    registrar_auditoria(
        session,
        acao="DEFINIR_IMAGEM_PRINCIPAL",
        entidade="produto",
        entidade_id=produto_id,
        detalhes=f"Imagem #{imagem_id} definida como principal.",
        usuario_id=usuario_id,
    )
    session.commit()


def remover_imagem_produto(
    session: Session,
    settings: Settings,
    produto_id: int,
    imagem_id: int,
    usuario_id: int | None = None,
) -> None:
    alvo = (
        session.query(ProdutoImagem)
        .filter(ProdutoImagem.id == imagem_id, ProdutoImagem.produto_id == produto_id)
        .first()
    )
    if alvo is None:
        raise ValueError("Imagem não encontrada para este produto.")

    era_principal = bool(alvo.principal)
    nome_arquivo = alvo.arquivo
    session.delete(alvo)
    session.flush()

    if era_principal:
        proxima = (
            session.query(ProdutoImagem)
            .filter(ProdutoImagem.produto_id == produto_id)
            .order_by(ProdutoImagem.ordem, ProdutoImagem.id)
            .first()
        )
        if proxima is not None:
            proxima.principal = 1

    registrar_auditoria(
        session,
        acao="REMOVER_IMAGEM_PRODUTO",
        entidade="produto",
        entidade_id=produto_id,
        detalhes=f"Imagem '{nome_arquivo}' removida.",
        usuario_id=usuario_id,
    )
    session.commit()
    remover_arquivos_imagem(settings, nome_arquivo)


def obter_produto_detalhe(session: Session, produto_id: int) -> dict | None:
    produto = session.get(Produto, produto_id)
    if produto is None:
        return None
    nicho_ids = [
        row[0]
        for row in session.query(ProdutoNicho.nicho_id)
        .filter(ProdutoNicho.produto_id == produto_id)
        .all()
    ]
    imagens = (
        session.query(ProdutoImagem)
        .filter(ProdutoImagem.produto_id == produto_id)
        .order_by(ProdutoImagem.principal.desc(), ProdutoImagem.ordem, ProdutoImagem.id)
        .all()
    )
    margem = calcular_margem(produto.custo_centavos, produto.preco_centavos)
    return {
        "produto": produto,
        "nicho_ids": nicho_ids,
        "imagens": imagens,
        **margem,
    }


def _status_estoque(estoque_atual: int, estoque_minimo: int) -> str:
    if estoque_atual <= 0:
        return "zerado"
    if estoque_atual <= estoque_minimo:
        return "baixo"
    return "ok"


def _parse_float_opcional(valor: Any) -> float | None:
    texto = str(valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _parse_centavos_opcional(valor: Any) -> int | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return reais_para_centavos(texto)
    except ValueError:
        return None


def listar_produtos(
    session: Session,
    filtros: Mapping[str, Any] | None = None,
    margem_alvo_pct: float = 45.0,
) -> list[dict]:
    """Lista produtos aplicando todos os filtros combinados do catálogo."""
    f = dict(filtros or {})
    ativo = str(f.get("ativo", "1") or "1")
    busca = str(f.get("busca", "") or "").strip().lower()
    nicho_id = str(f.get("nicho_id", "") or "").strip()
    fornecedor_id = str(f.get("fornecedor_id", "") or "").strip()
    preco_min = _parse_centavos_opcional(f.get("preco_min"))
    preco_max = _parse_centavos_opcional(f.get("preco_max"))
    margem_min = _parse_float_opcional(f.get("margem_min"))
    margem_max = _parse_float_opcional(f.get("margem_max"))
    abaixo_alvo = str(f.get("margem_abaixo_alvo", "") or "") == "1"
    estoque_status = str(f.get("estoque_status", "") or "").strip()
    ordenar = str(f.get("ordenar", "nome") or "nome")

    query = session.query(Produto)
    if ativo == "1":
        query = query.filter(Produto.ativo == 1)
    elif ativo == "0":
        query = query.filter(Produto.ativo == 0)

    if fornecedor_id.isdigit():
        query = query.filter(Produto.fornecedor_id == int(fornecedor_id))

    if nicho_id.isdigit():
        nid = int(nicho_id)
        subq = session.query(ProdutoNicho.produto_id).filter(ProdutoNicho.nicho_id == nid)
        query = query.filter(Produto.id.in_(subq))

    produtos = query.all()

    nichos_por_id = {n.id: n for n in session.query(Nicho).all()}
    fornecedores_por_id = {x.id: x.nome for x in session.query(Fornecedor).all()}

    mapa_nichos: dict[int, list[dict]] = {}
    for pn in session.query(ProdutoNicho).all():
        n = nichos_por_id.get(pn.nicho_id)
        if n:
            mapa_nichos.setdefault(pn.produto_id, []).append(
                {"id": n.id, "nome": n.nome, "cor": n.cor}
            )

    mapa_imagens: dict[int, str] = {}
    for img in (
        session.query(ProdutoImagem)
        .order_by(ProdutoImagem.principal.desc(), ProdutoImagem.ordem, ProdutoImagem.id)
        .all()
    ):
        if img.produto_id not in mapa_imagens:
            mapa_imagens[img.produto_id] = img.arquivo

    itens: list[dict] = []
    for p in produtos:
        if busca:
            alvo = " ".join([p.nome, p.sku, p.codigo_barras or ""]).lower()
            if busca not in alvo:
                continue
        if preco_min is not None and p.preco_centavos < preco_min:
            continue
        if preco_max is not None and p.preco_centavos > preco_max:
            continue

        calc = calcular_margem(p.custo_centavos, p.preco_centavos)
        if margem_min is not None and calc["margem_pct"] < margem_min:
            continue
        if margem_max is not None and calc["margem_pct"] > margem_max:
            continue
        if abaixo_alvo and calc["margem_pct"] >= margem_alvo_pct:
            continue

        est_status = _status_estoque(p.estoque_atual, p.estoque_minimo)
        if estoque_status and est_status != estoque_status:
            continue

        itens.append(
            {
                "id": p.id,
                "sku": p.sku,
                "codigo_barras": p.codigo_barras or "",
                "nome": p.nome,
                "unidade": p.unidade,
                "custo_centavos": p.custo_centavos,
                "preco_centavos": p.preco_centavos,
                "lucro_centavos": calc["lucro_centavos"],
                "margem_pct": calc["margem_pct"],
                "margem_baixa": calc["margem_pct"] < margem_alvo_pct,
                "estoque_atual": p.estoque_atual,
                "estoque_minimo": p.estoque_minimo,
                "estoque_status": est_status,
                "fornecedor_id": p.fornecedor_id,
                "fornecedor_nome": fornecedores_por_id.get(p.fornecedor_id, "—"),
                "nichos": sorted(mapa_nichos.get(p.id, []), key=lambda x: x["nome"]),
                "imagem_principal": mapa_imagens.get(p.id),
                "ativo": bool(p.ativo),
                "criado_em": p.criado_em,
            }
        )

    if ordenar == "preco_asc":
        itens.sort(key=lambda x: (x["preco_centavos"], x["nome"].lower()))
    elif ordenar == "preco_desc":
        itens.sort(key=lambda x: (-x["preco_centavos"], x["nome"].lower()))
    elif ordenar == "estoque_asc":
        itens.sort(key=lambda x: (x["estoque_atual"], x["nome"].lower()))
    elif ordenar == "recentes":
        itens.sort(key=lambda x: x["id"], reverse=True)
    else:
        itens.sort(key=lambda x: x["nome"].lower())

    return itens
