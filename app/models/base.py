from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa SQLAlchemy 2 para todos os modelos do sistema."""


def utc_now_iso() -> str:
    """Retorna timestamp ISO 8601 UTC sem microssegundos para consistência em SQLite TEXT."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
