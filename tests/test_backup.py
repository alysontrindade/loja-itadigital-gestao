from datetime import date, datetime, timedelta, timezone
import sqlite3
import zipfile
from pathlib import Path
import pytest

from app.config import build_settings
from app.db import get_session, init_db
from app.models import Configuracao


def test_backup_criacao_integridade_e_restauracao_com_seguranca(tmp_env):
    from app.services.backup_service import (
        create_backup,
        list_backups,
        restore_backup,
        validate_backup_zip,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as session:
        session.merge(Configuracao(chave="nome_loja", valor="Loja Teste Original"))
        session.commit()

    foto_arquivo = settings.fotos_dir / "produto_teste.jpg"
    foto_arquivo.parent.mkdir(parents=True, exist_ok=True)
    foto_arquivo.write_bytes(b"FAKEJPEGDATA123")

    backup_zip = create_backup(settings)
    assert backup_zip.exists()
    assert backup_zip.parent == settings.backup_dir
    assert len(list_backups(settings.backup_dir)) == 1

    meta = validate_backup_zip(backup_zip)
    assert meta["integrity"] == "ok"
    assert "loja.db" in meta["files"]

    # Altera dados e foto após o backup
    with get_session(engine) as session:
        session.merge(Configuracao(chave="nome_loja", valor="Loja Alterada Depois"))
        session.commit()
    foto_arquivo.write_bytes(b"SOBRESCRITA")

    engine.dispose()

    # Restaura o backup anterior e verifica que foi criado backup de segurança pré-restauração
    safety_zip = restore_backup(settings, backup_zip)
    assert safety_zip.exists()
    assert "pre_restore_" in safety_zip.name

    assert foto_arquivo.read_bytes() == b"FAKEJPEGDATA123"
    with sqlite3.connect(settings.db_path) as raw:
        row = raw.execute(
            "SELECT valor FROM configuracao WHERE chave = 'nome_loja';"
        ).fetchone()
    assert row is not None
    assert row[0] == "Loja Teste Original"


def test_backup_rejeita_zip_invalido_ou_corrompido(tmp_env, tmp_path):
    from app.services.backup_service import validate_backup_zip

    invalido = tmp_path / "corrompido.zip"
    with zipfile.ZipFile(invalido, "w") as zf:
        zf.writestr("loja.db", b"nao e um banco sqlite valido")

    with pytest.raises(ValueError):
        validate_backup_zip(invalido)


def test_backup_retencao_30_diarios_e_12_mensais(tmp_env):
    from app.services.backup_service import prune_backups

    backup_dir = Path(tmp_env["BACKUP_DIR"])
    hoje = date(2026, 11, 13)

    # Cria 45 backups diários consecutivos
    criados = []
    for i in range(45):
        d = hoje - timedelta(days=i)
        p = backup_dir / f"backup_{d.isoformat()}.zip"
        p.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        criados.append(p)

    # Cria mais 15 backups mensais antigos (um por mês anterior)
    for m in range(2, 17):
        ano = 2026 - ((m + 1) // 12)
        mes = ((11 - m - 1) % 12) + 1
        d = date(ano, mes, 10)
        p = backup_dir / f"backup_{d.isoformat()}.zip"
        p.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        criados.append(p)

    removidos = prune_backups(backup_dir, keep_daily=30, keep_monthly=12, today=hoje)
    restantes = sorted(p.name for p in backup_dir.glob("backup_*.zip"))

    assert len(removidos) > 0
    # Últimos 30 dias mantidos
    for i in range(30):
        d = hoje - timedelta(days=i)
        assert f"backup_{d.isoformat()}.zip" in restantes
    # Total razoável (30 diários + até 12 mensais fora da janela diária)
    assert len(restantes) <= 42


def test_backup_diario_executa_apenas_uma_vez_por_dia(tmp_env):
    from app.services.backup_service import run_daily_backup_if_needed

    settings = build_settings(tmp_env)
    engine = init_db(settings)
    engine.dispose()

    hoje = date(2026, 11, 13)
    primeiro = run_daily_backup_if_needed(settings, today=hoje)
    segundo = run_daily_backup_if_needed(settings, today=hoje)

    assert primeiro is not None
    assert primeiro.exists()
    assert segundo is None

