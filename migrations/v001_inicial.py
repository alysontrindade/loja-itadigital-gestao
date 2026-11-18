from sqlalchemy import Engine

from app.models import Base


def aplicar(engine: Engine) -> None:
    """Cria a estrutura inicial das 16 tabelas de domínio e índices."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_produto_nome ON produto(nome);"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_venda_data ON venda(data);"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_movimento_produto ON movimento_estoque(produto_id, criado_em);"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_log_auditoria_data ON log_auditoria(criado_em);"
        )
