import re
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Nicho, ProdutoNicho
from app.services.audit_service import registrar_auditoria

HEX_COR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validar_cor(cor: str | None) -> str:
    valor = (cor or "#c2410c").strip()
    if not HEX_COR_RE.match(valor):
        raise ValueError("Cor do nicho deve estar no formato hexadecimal #RRGGBB.")
    return valor.lower()


def listar_nichos(session: Session, ativo: str = "1", busca: str = "") -> list[dict]:
    """Lista nichos com filtros de status e busca textual e contagem real de produtos."""
    contagens = dict(
        session.query(ProdutoNicho.nicho_id, func.count(ProdutoNicho.produto_id))
        .group_by(ProdutoNicho.nicho_id)
        .all()
    )

    query = session.query(Nicho)
    if ativo == "1":
        query = query.filter(Nicho.ativo == 1)
    elif ativo == "0":
        query = query.filter(Nicho.ativo == 0)

    termo = (busca or "").strip().lower()
    nichos = query.order_by(Nicho.id).all()

    resultado = []
    for n in nichos:
        if termo and termo not in n.nome.lower() and termo not in n.descricao.lower():
            continue
        resultado.append(
            {
                "id": n.id,
                "nome": n.nome,
                "descricao": n.descricao,
                "cor": n.cor,
                "ativo": bool(n.ativo),
                "criado_em": n.criado_em,
                "produtos_count": int(contagens.get(n.id, 0)),
            }
        )
    return resultado


def obter_nicho(session: Session, nicho_id: int) -> Nicho | None:
    return session.get(Nicho, nicho_id)


def criar_nicho(
    session: Session,
    nome: str,
    cor: str = "#c2410c",
    descricao: str = "",
    usuario_id: int | None = None,
) -> Nicho:
    """Cria novo nicho garantindo unicidade de nome (sem distinguir maiúsculas/minúsculas)."""
    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        raise ValueError("O nome do nicho é obrigatório.")
    cor_limpa = _validar_cor(cor)

    duplicado = (
        session.query(Nicho)
        .filter(func.lower(Nicho.nome) == nome_limpo.lower())
        .first()
    )
    if duplicado is not None:
        raise ValueError(f"Já existe um nicho chamado '{duplicado.nome}'.")

    nicho = Nicho(
        nome=nome_limpo,
        cor=cor_limpa,
        descricao=(descricao or "").strip(),
        ativo=1,
    )
    session.add(nicho)
    session.flush()
    registrar_auditoria(
        session,
        acao="CRIAR_NICHO",
        entidade="nicho",
        entidade_id=nicho.id,
        detalhes=f"Nicho '{nome_limpo}' criado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(nicho)
    return nicho


def atualizar_nicho(
    session: Session,
    nicho_id: int,
    nome: str,
    cor: str = "#c2410c",
    descricao: str = "",
    ativo: bool | None = None,
    usuario_id: int | None = None,
) -> Nicho:
    """Atualiza dados de um nicho existente."""
    nicho = session.get(Nicho, nicho_id)
    if nicho is None:
        raise ValueError("Nicho não encontrado.")

    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        raise ValueError("O nome do nicho é obrigatório.")
    cor_limpa = _validar_cor(cor)

    duplicado = (
        session.query(Nicho)
        .filter(func.lower(Nicho.nome) == nome_limpo.lower(), Nicho.id != nicho_id)
        .first()
    )
    if duplicado is not None:
        raise ValueError(f"Já existe outro nicho chamado '{duplicado.nome}'.")

    nicho.nome = nome_limpo
    nicho.cor = cor_limpa
    nicho.descricao = (descricao or "").strip()
    if ativo is not None:
        nicho.ativo = 1 if ativo else 0

    registrar_auditoria(
        session,
        acao="EDITAR_NICHO",
        entidade="nicho",
        entidade_id=nicho.id,
        detalhes=f"Nicho '{nome_limpo}' atualizado.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(nicho)
    return nicho


def alternar_ativo_nicho(
    session: Session,
    nicho_id: int,
    usuario_id: int | None = None,
) -> Nicho:
    """Inativa ou reativa um nicho sem remover histórico."""
    nicho = session.get(Nicho, nicho_id)
    if nicho is None:
        raise ValueError("Nicho não encontrado.")
    nicho.ativo = 0 if nicho.ativo else 1
    acao = "REATIVAR_NICHO" if nicho.ativo else "INATIVAR_NICHO"
    registrar_auditoria(
        session,
        acao=acao,
        entidade="nicho",
        entidade_id=nicho.id,
        detalhes=f"Nicho '{nicho.nome}' marcado como {'ativo' if nicho.ativo else 'inativo'}.",
        usuario_id=usuario_id,
    )
    session.commit()
    session.refresh(nicho)
    return nicho
