from sqlalchemy import Engine

from app.models import IdeiaImpressao


def aplicar(engine: Engine) -> None:
    """Cria a tabela ideia_impressao e índice por status/data."""
    IdeiaImpressao.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_ideia_impressao_status ON ideia_impressao(status, criado_em);"
        )
