from dataclasses import dataclass
import os
from pathlib import Path
import secrets
from typing import Any, Mapping


PROJECT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    """Configuração de execução da aplicação local."""

    project_dir: Path
    data_dir: Path
    backup_dir: Path
    db_path: Path
    fotos_dir: Path
    host: str
    port: int
    secret_key: str
    session_timeout_minutes: int
    testing: bool = False


def _default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "LojaItamarandiba"
    return Path.home() / "AppData" / "Local" / "LojaItamarandiba"


def _load_or_create_secret_key(data_dir: Path) -> str:
    secret_file = data_dir / ".secret_key"
    if secret_file.exists():
        valor = secret_file.read_text(encoding="utf-8").strip()
        if len(valor) >= 32:
            return valor
    novo = secrets.token_hex(32)
    secret_file.write_text(novo, encoding="utf-8")
    return novo


def build_settings(overrides: Mapping[str, Any] | None = None) -> Settings:
    """Constrói Settings garantindo criação dos diretórios locais e chave secreta persistente."""
    cfg = dict(overrides or {})

    data_dir = Path(cfg.get("DATA_DIR") or os.environ.get("LOJA_DATA_DIR") or _default_data_dir())
    backup_dir = Path(cfg.get("BACKUP_DIR") or os.environ.get("LOJA_BACKUP_DIR") or (PROJECT_DIR / "backups"))
    fotos_dir = data_dir / "fotos"
    db_path = data_dir / "loja.db"

    data_dir.mkdir(parents=True, exist_ok=True)
    fotos_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    secret_key = str(cfg.get("SECRET_KEY") or os.environ.get("LOJA_SECRET_KEY") or _load_or_create_secret_key(data_dir))
    port = int(cfg.get("PORT") or os.environ.get("LOJA_PORT") or 8000)
    session_timeout = int(
        cfg.get("SESSION_TIMEOUT_MINUTES")
        or os.environ.get("LOJA_SESSION_TIMEOUT_MINUTES")
        or 120
    )

    return Settings(
        project_dir=PROJECT_DIR,
        data_dir=data_dir,
        backup_dir=backup_dir,
        db_path=db_path,
        fotos_dir=fotos_dir,
        host="127.0.0.1",
        port=port,
        secret_key=secret_key,
        session_timeout_minutes=session_timeout,
        testing=bool(cfg.get("TESTING", False)),
    )
