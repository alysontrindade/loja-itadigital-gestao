from sqlalchemy.orm import Session

from app.models import LogAuditoria


def registrar_auditoria(
    session: Session,
    acao: str,
    entidade: str,
    entidade_id: str | int | None = None,
    detalhes: str = "",
    usuario_id: int | None = None,
) -> LogAuditoria:
    """Registra uma entrada no log imutável de auditoria."""
    registro = LogAuditoria(
        usuario_id=usuario_id,
        acao=acao,
        entidade=entidade,
        entidade_id=None if entidade_id is None else str(entidade_id),
        detalhes=detalhes,
    )
    session.add(registro)
    return registro
