import re
from typing import Any, Mapping
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Cliente, Venda
from app.services.audit_service import registrar_auditoria
from app.utils.whatsapp import (
    formatar_telefone_exibicao,
    formatar_whatsapp_link,
    limpar_telefone,
)

ANIV_DDMM_RE = re.compile(r"^(\d{2})/(\d{2})(?:/(\d{4}))?$")
ANIV_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def extrair_mes_aniversario(aniversario: str | None) -> int | None:
    """Extrai o mês (1-12) de datas em formato DD/MM, DD/MM/AAAA ou AAAA-MM-DD."""
    texto = (aniversario or "").strip()
    if not texto:
        return None
    m_br = ANIV_DDMM_RE.match(texto)
    if m_br:
        mes = int(m_br.group(2))
        return mes if 1 <= mes <= 12 else None
    m_iso = ANIV_ISO_RE.match(texto)
    if m_iso:
        mes = int(m_iso.group(2))
        return mes if 1 <= mes <= 12 else None
    return None


def _validar_aniversario(aniversario: str | None) -> str:
    texto = (aniversario or "").strip()
    if not texto:
        return ""
    mes = extrair_mes_aniversario(texto)
    if mes is None:
        raise ValueError("Data de aniversário inválida. Use DD/MM ou AAAA-MM-DD.")
    m_br = ANIV_DDMM_RE.match(texto)
    if m_br:
        dia = int(m_br.group(1))
        if not 1 <= dia <= 31:
            raise ValueError("Dia de aniversário inválido.")
    m_iso = ANIV_ISO_RE.match(texto)
    if m_iso:
        dia = int(m_iso.group(3))
        if not 1 <= dia <= 31:
            raise ValueError("Dia de aniversário inválido.")
    return texto


def _validar_dados_cliente(dados: Mapping[str, Any]) -> dict[str, Any]:
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("O nome do cliente é obrigatório.")

    whatsapp_bruto = str(dados.get("whatsapp") or "").strip()
    whatsapp_norm = limpar_telefone(whatsapp_bruto) if whatsapp_bruto else None
    if whatsapp_bruto and not whatsapp_norm:
        raise ValueError("Número de WhatsApp inválido.")

    aniversario = _validar_aniversario(str(dados.get("aniversario") or ""))
    return {
        "nome": nome,
        "whatsapp": whatsapp_norm,
        "email": str(dados.get("email") or "").strip(),
        "cidade": str(dados.get("cidade") or "").strip(),
        "aniversario": aniversario,
        "observacoes": str(dados.get("observacoes") or "").strip(),
    }


def listar_cidades_clientes(session: Session) -> list[str]:
    rows = (
        session.query(Cliente.cidade)
        .filter(Cliente.cidade != "")
        .distinct()
        .order_by(Cliente.cidade)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def listar_clientes(
    session: Session,
    busca: str = "",
    cidade: str = "",
    mes_aniversario: str | int = "",
) -> list[dict]:
    """Lista clientes com filtro por nome/contato, cidade e mês de aniversário."""
    contagens_vendas = dict(
        session.query(Venda.cliente_id, func.count(Venda.id))
        .filter(Venda.cliente_id.is_not(None))
        .group_by(Venda.cliente_id)
        .all()
    )

    clientes = session.query(Cliente).order_by(Cliente.nome).all()
    termo = (busca or "").strip().lower()
    cidade_filtro = (cidade or "").strip().lower()

    mes_alvo: int | None = None
    if mes_aniversario not in ("", None):
        try:
            mes_num = int(mes_aniversario)
            if 1 <= mes_num <= 12:
                mes_alvo = mes_num
        except (TypeError, ValueError):
            mes_alvo = None

    resultado = []
    for c in clientes:
        if termo:
            alvo = " ".join([c.nome, c.whatsapp or "", c.email, c.cidade]).lower()
            if termo not in alvo:
                continue
        if cidade_filtro and cidade_filtro not in c.cidade.lower():
            continue
        if mes_alvo is not None and extrair_mes_aniversario(c.aniversario) != mes_alvo:
            continue
        resultado.append(
            {
                "id": c.id,
                "nome": c.nome,
                "whatsapp": c.whatsapp or "",
                "whatsapp_formatado": formatar_telefone_exibicao(c.whatsapp),
                "whatsapp_link": formatar_whatsapp_link(c.whatsapp),
                "email": c.email,
                "cidade": c.cidade,
                "aniversario": c.aniversario,
                "observacoes": c.observacoes,
                "criado_em": c.criado_em,
                "vendas_count": int(contagens_vendas.get(c.id, 0)),
            }
        )
    return resultado


def obter_cliente(session: Session, cliente_id: int) -> Cliente | None:
    return session.get(Cliente, cliente_id)


def criar_cliente(
    session: Session,
    dados: Mapping[str, Any],
    usuario_id: int | None = None,
) -> Cliente:
    limpos = _validar_dados_cliente(dados)
    if limpos["whatsapp"]:
        existente = (
            session.query(Cliente)
            .filter(Cliente.whatsapp == limpos["whatsapp"])
            .first()
        )
        if existente is not None:
            raise ValueError(f"Já existe um cliente com este WhatsApp ({existente.nome}).")

    cliente = Cliente(**limpos)
    session.add(cliente)
    session.flush()
    registrar_auditoria(
        session,
        acao="CRIAR_CLIENTE",
        entidade="cliente",
        entidade_id=cliente.id,
        detalhes=f"Cliente '{cliente.nome}' cadastrado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(cliente)
    return cliente


def atualizar_cliente(
    session: Session,
    cliente_id: int,
    dados: Mapping[str, Any],
    usuario_id: int | None = None,
) -> Cliente:
    cliente = session.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError("Cliente não encontrado.")

    limpos = _validar_dados_cliente(dados)
    if limpos["whatsapp"]:
        existente = (
            session.query(Cliente)
            .filter(Cliente.whatsapp == limpos["whatsapp"], Cliente.id != cliente_id)
            .first()
        )
        if existente is not None:
            raise ValueError(f"Outro cliente já usa este WhatsApp ({existente.nome}).")

    for chave, valor in limpos.items():
        setattr(cliente, chave, valor)

    registrar_auditoria(
        session,
        acao="EDITAR_CLIENTE",
        entidade="cliente",
        entidade_id=cliente.id,
        detalhes=f"Cliente '{cliente.nome}' atualizado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(cliente)
    return cliente
