import sqlite3
from pathlib import Path
import pytest


EXPECTED_TABLES = {
    "nicho",
    "produto",
    "produto_nicho",
    "produto_imagem",
    "fornecedor",
    "compra",
    "compra_item",
    "movimento_estoque",
    "cliente",
    "venda",
    "venda_item",
    "kit",
    "kit_item",
    "usuario",
    "configuracao",
    "log_auditoria",
    "schema_version",
}

EXPECTED_NICHOS = [
    "Presentes Personalizados & Kits Prontos",
    "Religioso & Devocional",
    "Papelaria Fofa / Studygram & Concurseiros",
    "Lembrancinhas de Festas & Eventos",
    "Gamer, Geek & Setup de Mesa",
    "Pet (Mimos & Identificação)",
    "Casa Prática, Cozinha & Achadinhos Virais",
    "Beleza Express & Autocuidado",
    "Brindes Corporativos & Comércio Local (B2B)",
    "Agro / Profissões & Cultura Local",
]


def test_conversores_monetarios_centavos():
    from app.utils.money import centavos_para_brl, reais_para_centavos

    assert reais_para_centavos("19,90") == 1990
    assert reais_para_centavos("R$ 1.234,56") == 123456
    assert reais_para_centavos("25.5") == 2550
    assert reais_para_centavos(0) == 0
    assert reais_para_centavos("0,05") == 5
    assert centavos_para_brl(1990) == "R$ 19,90"
    assert centavos_para_brl(123456) == "R$ 1.234,56"
    assert centavos_para_brl(-500) == "-R$ 5,00"


def test_config_usa_diretorio_local_e_secret_key_persistida(tmp_env):
    from app.config import build_settings

    s1 = build_settings(tmp_env)
    assert Path(s1.data_dir) == Path(tmp_env["DATA_DIR"])
    assert Path(s1.backup_dir) == Path(tmp_env["BACKUP_DIR"])
    assert s1.db_path == Path(tmp_env["DATA_DIR"]) / "loja.db"
    assert s1.fotos_dir == Path(tmp_env["DATA_DIR"]) / "fotos"
    assert s1.host == "127.0.0.1"
    assert s1.secret_key

    s2 = build_settings(tmp_env)
    assert s2.secret_key == s1.secret_key


def test_init_db_cria_todas_tabelas_pragmas_e_seed_10_nichos(tmp_env):
    from app.config import build_settings
    from app.db import get_session, init_db
    from app.models import Nicho, Produto

    from sqlalchemy import text

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with sqlite3.connect(settings.db_path) as raw:
        journal = raw.execute("PRAGMA journal_mode;").fetchone()[0]
        tabelas = {
            row[0]
            for row in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        versoes = raw.execute("SELECT versao FROM schema_version;").fetchall()

    with engine.connect() as conn:
        fk_mode = conn.execute(text("PRAGMA foreign_keys;")).fetchone()[0]

    assert str(journal).lower() == "wal"
    assert fk_mode == 1
    assert EXPECTED_TABLES.issubset(tabelas)
    assert len(versoes) >= 1

    with get_session(engine) as session:
        nichos = session.query(Nicho).order_by(Nicho.id).all()
        assert [n.nome for n in nichos] == EXPECTED_NICHOS
        assert all(n.cor.startswith("#") and len(n.cor) == 7 for n in nichos)

    # Idempotente: rodar init_db novamente não duplica os 10 nichos
    init_db(settings)
    with get_session(engine) as session:
        assert session.query(Nicho).count() == 10

        # Foreign key enforcement via SQLAlchemy session
        p_invalido = Produto(
            sku="TST-999",
            nome="Teste FK",
            unidade="un",
            custo_centavos=500,
            preco_centavos=1200,
            fornecedor_id=999999,
        )
        session.add(p_invalido)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()
