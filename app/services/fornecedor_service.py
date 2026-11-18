from typing import Any, Mapping
from urllib.parse import urlparse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Fornecedor, Produto
from app.services.audit_service import registrar_auditoria
from app.utils.money import reais_para_centavos
from app.utils.whatsapp import formatar_telefone_exibicao, formatar_whatsapp_link, limpar_telefone

TIPOS_FORNECEDOR = {
    "local": "Local / Regional",
    "atacado": "Atacado Nacional",
    "china": "Importação / China",
    "marketplace": "Marketplace",
}


def _normalizar_site(url: str | None) -> str:
    valor = (url or "").strip()
    if not valor:
        return ""
    if "://" not in valor:
        valor = f"https://{valor}"
    parsed = urlparse(valor)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("URL do site do fornecedor inválida.")
    return valor


def _ler_int_nao_negativo(valor: Any, campo: str) -> int:
    if valor is None or valor == "":
        return 0
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido para {campo}.") from exc
    if numero < 0:
        raise ValueError(f"{campo} não pode ser negativo.")
    return numero


def _validar_dados_fornecedor(dados: Mapping[str, Any]) -> dict[str, Any]:
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("O nome do fornecedor é obrigatório.")

    tipo = str(dados.get("tipo") or "atacado").strip().lower()
    if tipo not in TIPOS_FORNECEDOR:
        raise ValueError("Tipo de fornecedor inválido.")

    whatsapp_bruto = str(dados.get("whatsapp") or "").strip()
    whatsapp_norm = limpar_telefone(whatsapp_bruto) if whatsapp_bruto else ""
    site_norm = _normalizar_site(str(dados.get("site") or ""))
    prazo_dias = _ler_int_nao_negativo(dados.get("prazo_dias"), "Prazo em dias")

    if "pedido_minimo_centavos" in dados and dados["pedido_minimo_centavos"] is not None:
        pedido_minimo_centavos = _ler_int_nao_negativo(
            dados["pedido_minimo_centavos"], "Pedido mínimo"
        )
    else:
        pedido_minimo_centavos = reais_para_centavos(dados.get("pedido_minimo", 0))
        if pedido_minimo_centavos < 0:
            raise ValueError("Pedido mínimo não pode ser negativo.")

    return {
        "nome": nome,
        "tipo": tipo,
        "contato": str(dados.get("contato") or "").strip(),
        "whatsapp": whatsapp_norm,
        "site": site_norm,
        "cidade_uf": str(dados.get("cidade_uf") or "").strip(),
        "prazo_dias": prazo_dias,
        "pedido_minimo_centavos": pedido_minimo_centavos,
        "observacoes": str(dados.get("observacoes") or "").strip(),
    }


def listar_cidades_fornecedores(session: Session) -> list[str]:
    rows = (
        session.query(Fornecedor.cidade_uf)
        .filter(Fornecedor.cidade_uf != "")
        .distinct()
        .order_by(Fornecedor.cidade_uf)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def listar_fornecedores(
    session: Session,
    busca: str = "",
    tipo: str = "",
    cidade: str = "",
    ativo: str = "1",
) -> list[dict]:
    """Lista fornecedores com filtros combinados e contagem de produtos vinculados."""
    contagens = dict(
        session.query(Produto.fornecedor_id, func.count(Produto.id))
        .filter(Produto.fornecedor_id.is_not(None))
        .group_by(Produto.fornecedor_id)
        .all()
    )

    query = session.query(Fornecedor)
    if ativo == "1":
        query = query.filter(Fornecedor.ativo == 1)
    elif ativo == "0":
        query = query.filter(Fornecedor.ativo == 0)

    if tipo and tipo in TIPOS_FORNECEDOR:
        query = query.filter(Fornecedor.tipo == tipo)

    fornecedores = query.order_by(Fornecedor.nome).all()
    termo = (busca or "").strip().lower()
    cidade_filtro = (cidade or "").strip().lower()

    resultado = []
    for f in fornecedores:
        if termo:
            alvo = " ".join([f.nome, f.contato, f.whatsapp, f.site, f.cidade_uf]).lower()
            if termo not in alvo:
                continue
        if cidade_filtro and cidade_filtro not in f.cidade_uf.lower():
            continue
        resultado.append(
            {
                "id": f.id,
                "nome": f.nome,
                "tipo": f.tipo,
                "tipo_label": TIPOS_FORNECEDOR.get(f.tipo, f.tipo),
                "contato": f.contato,
                "whatsapp": f.whatsapp,
                "whatsapp_formatado": formatar_telefone_exibicao(f.whatsapp),
                "whatsapp_link": formatar_whatsapp_link(f.whatsapp),
                "site": f.site,
                "cidade_uf": f.cidade_uf,
                "prazo_dias": f.prazo_dias,
                "pedido_minimo_centavos": f.pedido_minimo_centavos,
                "observacoes": f.observacoes,
                "ativo": bool(f.ativo),
                "produtos_count": int(contagens.get(f.id, 0)),
            }
        )
    return resultado


def obter_fornecedor(session: Session, fornecedor_id: int) -> Fornecedor | None:
    return session.get(Fornecedor, fornecedor_id)


def criar_fornecedor(
    session: Session,
    dados: Mapping[str, Any],
    usuario_id: int | None = None,
) -> Fornecedor:
    limpos = _validar_dados_fornecedor(dados)
    fornecedor = Fornecedor(**limpos, ativo=1)
    session.add(fornecedor)
    session.flush()
    registrar_auditoria(
        session,
        acao="CRIAR_FORNECEDOR",
        entidade="fornecedor",
        entidade_id=fornecedor.id,
        detalhes=f"Fornecedor '{fornecedor.nome}' ({fornecedor.tipo}) cadastrado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(fornecedor)
    return fornecedor


def atualizar_fornecedor(
    session: Session,
    fornecedor_id: int,
    dados: Mapping[str, Any],
    usuario_id: int | None = None,
) -> Fornecedor:
    fornecedor = session.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        raise ValueError("Fornecedor não encontrado.")

    limpos = _validar_dados_fornecedor(dados)
    for chave, valor in limpos.items():
        setattr(fornecedor, chave, valor)

    registrar_auditoria(
        session,
        acao="EDITAR_FORNECEDOR",
        entidade="fornecedor",
        entidade_id=fornecedor.id,
        detalhes=f"Fornecedor '{fornecedor.nome}' atualizado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(fornecedor)
    return fornecedor


def alternar_ativo_fornecedor(
    session: Session,
    fornecedor_id: int,
    usuario_id: int | None = None,
) -> Fornecedor:
    fornecedor = session.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        raise ValueError("Fornecedor não encontrado.")
    fornecedor.ativo = 0 if fornecedor.ativo else 1
    acao = "REATIVAR_FORNECEDOR" if fornecedor.ativo else "INATIVAR_FORNECEDOR"
    registrar_auditoria(
        session,
        acao=acao,
        entidade="fornecedor",
        entidade_id=fornecedor.id,
        detalhes=f"Fornecedor '{fornecedor.nome}' marcado como {'ativo' if fornecedor.ativo else 'inativo'}.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(fornecedor)
    return fornecedor
