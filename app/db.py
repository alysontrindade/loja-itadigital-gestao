from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import SchemaVersion
from migrations import MIGRACOES
from seeds.nichos import seed_config_padrao, seed_nichos


def create_db_engine(db_path: Path) -> Engine:
    """Cria engine SQLAlchemy para SQLite com WAL, chaves estrangeiras e busy_timeout."""
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        future=True,
        connect_args={"timeout": 15, "check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configurar_pragmas_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

    return engine


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Fornece sessão SQLAlchemy com fechamento garantido."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _versoes_aplicadas(engine: Engine) -> set[int]:
    with engine.connect() as conn:
        existe = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version';"
            )
        ).fetchone()
        if not existe:
            return set()
        rows = conn.execute(text("SELECT versao FROM schema_version;")).fetchall()
        return {int(row[0]) for row in rows}


def init_db(settings: Settings) -> Engine:
    """Inicializa o banco SQLite, aplica migrações pendentes e garante os seeds iniciais."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(settings.db_path)

    aplicadas = _versoes_aplicadas(engine)
    for versao, descricao, funcao in MIGRACOES:
        if versao not in aplicadas:
            funcao(engine)
            with get_session(engine) as session:
                session.add(SchemaVersion(versao=versao, descricao=descricao))
                session.commit()

    with get_session(engine) as session:
        seed_nichos(session)
        seed_config_padrao(
            session, session_timeout_minutes=settings.session_timeout_minutes
        )
        session.commit()

    return engine
