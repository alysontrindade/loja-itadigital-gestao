from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile

from app.config import Settings

BACKUP_NAME_RE = re.compile(
    r"^backup_(\d{4}-\d{2}-\d{2})(?:_\d{6}(?:_\d+)?)?\.zip$"
)


def _local_now(when: datetime | None = None) -> datetime:
    if when is not None:
        return when
    return datetime.now()


def _next_zip_path(backup_dir: Path, prefix: str, moment: datetime) -> Path:
    base = backup_dir / f"{prefix}_{moment.strftime('%Y-%m-%d')}.zip"
    if prefix == "backup" and not base.exists():
        return base

    stamped = backup_dir / f"{prefix}_{moment.strftime('%Y-%m-%d_%H%M%S')}.zip"
    if not stamped.exists():
        return stamped

    idx = 1
    while True:
        candidate = backup_dir / f"{prefix}_{moment.strftime('%Y-%m-%d_%H%M%S')}_{idx}.zip"
        if not candidate.exists():
            return candidate
        idx += 1


def create_backup(
    settings: Settings,
    prefix: str = "backup",
    when: datetime | None = None,
) -> Path:
    """Cria backup ZIP consistente (SQLite online backup API + integrity_check + fotos)."""
    if not settings.db_path.exists():
        raise FileNotFoundError(f"Banco de dados não encontrado em {settings.db_path}")

    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    settings.fotos_dir.mkdir(parents=True, exist_ok=True)
    moment = _local_now(when)
    dest_zip = _next_zip_path(settings.backup_dir, prefix, moment)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        staged_db = tmp_dir / "loja.db"

        src_conn = sqlite3.connect(settings.db_path, timeout=15)
        dest_conn = sqlite3.connect(staged_db)
        try:
            src_conn.backup(dest_conn)
            row = dest_conn.execute("PRAGMA integrity_check;").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise RuntimeError(f"Falha de integridade no backup SQLite: {row}")
        finally:
            dest_conn.close()
            src_conn.close()

        fotos_contadas = 0
        manifest = {
            "criado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "integridade": "ok",
            "origem_db": settings.db_path.name,
        }

        staged_zip = tmp_dir / dest_zip.name
        with zipfile.ZipFile(staged_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(staged_db, arcname="loja.db")
            for arquivo in sorted(settings.fotos_dir.rglob("*")):
                if arquivo.is_file():
                    rel = arquivo.relative_to(settings.fotos_dir).as_posix()
                    zf.write(arquivo, arcname=f"fotos/{rel}")
                    fotos_contadas += 1
            manifest["fotos_total"] = fotos_contadas
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        shutil.copy2(staged_zip, dest_zip)

    return dest_zip


def _is_safe_member(name: str) -> bool:
    p = Path(name)
    return not p.is_absolute() and ".." not in p.parts


def validate_backup_zip(zip_path: Path) -> dict:
    """Valida estrutura e integridade SQLite de um arquivo ZIP de backup."""
    if not zip_path.exists():
        raise ValueError("Arquivo de backup não encontrado.")

    try:
        zf_ctx = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Arquivo ZIP inválido ou corrompido.") from exc

    with zf_ctx as zf:
        membros = zf.namelist()
        if any(not _is_safe_member(m) for m in membros):
            raise ValueError("Arquivo de backup contém caminhos inseguros.")
        if "loja.db" not in membros:
            raise ValueError("Backup inválido: arquivo 'loja.db' ausente.")

        with tempfile.TemporaryDirectory() as tmp_str:
            staged_db = Path(tmp_str) / "loja.db"
            staged_db.write_bytes(zf.read("loja.db"))

            conn = sqlite3.connect(staged_db)
            try:
                integrity = conn.execute("PRAGMA integrity_check;").fetchone()
                if not integrity or str(integrity[0]).lower() != "ok":
                    raise ValueError("Banco de dados dentro do backup está corrompido.")
                tabelas = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table';"
                    ).fetchall()
                }
                if "configuracao" not in tabelas or "nicho" not in tabelas:
                    raise ValueError("Backup não pertence ao esquema da Loja Itamarandiba.")
            except sqlite3.DatabaseError as exc:
                raise ValueError("Conteúdo de 'loja.db' inválido ou corrompido.") from exc
            finally:
                conn.close()

    return {
        "integrity": "ok",
        "files": membros,
        "size_bytes": zip_path.stat().st_size,
    }


def restore_backup(settings: Settings, zip_path: Path) -> Path:
    """Restaura banco e fotos a partir de um backup validado, gerando backup de segurança prévio."""
    validate_backup_zip(zip_path)

    safety_zip = create_backup(settings, prefix="pre_restore")

    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{settings.db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        with zipfile.ZipFile(zip_path, "r") as zf:
            (tmp_dir / "loja.db").write_bytes(zf.read("loja.db"))
            staged_fotos = tmp_dir / "fotos"
            staged_fotos.mkdir(parents=True, exist_ok=True)
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.filename.startswith("fotos/") and _is_safe_member(info.filename):
                    rel = Path(info.filename).relative_to("fotos")
                    destino = staged_fotos / rel
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(zf.read(info.filename))

        shutil.copy2(tmp_dir / "loja.db", settings.db_path)

        if settings.fotos_dir.exists():
            shutil.rmtree(settings.fotos_dir)
        shutil.copytree(tmp_dir / "fotos", settings.fotos_dir)

    return safety_zip


def list_backups(backup_dir: Path) -> list[dict]:
    """Lista backups existentes em ordem decrescente de modificação."""
    if not backup_dir.exists():
        return []
    arquivos = [
        p
        for p in backup_dir.glob("*.zip")
        if p.name.startswith("backup_") or p.name.startswith("pre_restore_")
    ]
    arquivos.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    resultado = []
    for p in arquivos:
        stat = p.stat()
        resultado.append(
            {
                "name": p.name,
                "path": p,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%d/%m/%Y %H:%M"
                ),
            }
        )
    return resultado


def prune_backups(
    backup_dir: Path,
    keep_daily: int = 30,
    keep_monthly: int = 12,
    today: date | None = None,
) -> list[Path]:
    """Aplica retenção de 30 backups diários + 12 backups mensais mais antigos."""
    if not backup_dir.exists():
        return []

    ref_today = today or date.today()
    daily_cutoff = ref_today - timedelta(days=max(keep_daily - 1, 0))

    candidatos: list[tuple[date, Path]] = []
    for p in backup_dir.glob("backup_*.zip"):
        match = BACKUP_NAME_RE.match(p.name)
        if not match:
            continue
        try:
            d = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        candidatos.append((d, p))

    manter: set[Path] = set()
    por_mes_antigo: dict[tuple[int, int], list[tuple[date, Path]]] = {}

    for d, p in candidatos:
        if d >= daily_cutoff:
            manter.add(p)
        else:
            por_mes_antigo.setdefault((d.year, d.month), []).append((d, p))

    meses_ordenados = sorted(por_mes_antigo.keys(), reverse=True)[:keep_monthly]
    for chave_mes in meses_ordenados:
        itens_mes = sorted(
            por_mes_antigo[chave_mes],
            key=lambda item: (item[0], item[1].name),
            reverse=True,
        )
        manter.add(itens_mes[0][1])

    removidos: list[Path] = []
    for _, p in candidatos:
        if p not in manter and p.exists():
            p.unlink()
            removidos.append(p)
    return removidos


def run_daily_backup_if_needed(
    settings: Settings,
    today: date | None = None,
) -> Path | None:
    """Executa o backup diário automático caso ainda não exista backup para o dia atual."""
    ref_today = today or date.today()
    prefixo_hoje = f"backup_{ref_today.isoformat()}"
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    if any(settings.backup_dir.glob(f"{prefixo_hoje}*.zip")):
        return None
    criado = create_backup(settings, prefix="backup")
    prune_backups(settings.backup_dir, today=ref_today)
    return criado


class BackupScheduler:
    """Thread em segundo plano para garantir backup diário automático."""

    def __init__(self, settings: Settings, check_interval_seconds: int = 3600) -> None:
        self.settings = settings
        self.check_interval_seconds = check_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            name="loja-backup-scheduler",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_daily_backup_if_needed(self.settings)
            except Exception:
                pass
            self._stop_event.wait(self.check_interval_seconds)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
