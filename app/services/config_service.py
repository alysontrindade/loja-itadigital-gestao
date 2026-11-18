from sqlalchemy.orm import Session

from app.models import Configuracao
from seeds.nichos import CONFIG_PADRAO

TEMAS_VALIDOS = {"claro", "escuro", "contraste"}


def get_all_config(session: Session) -> dict[str, str]:
    """Retorna todas as configurações mescladas com os padrões seguros."""
    dados = dict(CONFIG_PADRAO)
    for item in session.query(Configuracao).all():
        dados[item.chave] = item.valor
    if dados.get("tema") not in TEMAS_VALIDOS:
        dados["tema"] = "claro"
    return dados


def get_config(session: Session, chave: str, default: str = "") -> str:
    row = session.get(Configuracao, chave)
    if row is not None:
        return row.valor
    return CONFIG_PADRAO.get(chave, default)


def set_config(session: Session, chave: str, valor: str) -> None:
    session.merge(Configuracao(chave=chave, valor=str(valor)))
