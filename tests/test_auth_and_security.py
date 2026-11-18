from datetime import datetime, timedelta, timezone
from app.config import build_settings
from app.db import get_session, init_db
from app.models import LogAuditoria, Usuario


def test_hash_scrypt_e_verificacao():
    from app.services.auth_service import hash_password, verify_password

    h1 = hash_password("Segredo@123")
    h2 = hash_password("Segredo@123")

    assert h1.startswith("scrypt$")
    assert h1 != h2  # salt aleatório por hash
    assert verify_password("Segredo@123", h1) is True
    assert verify_password("SenhaErrada", h1) is False
    assert verify_password("Segredo@123", "formato-invalido") is False


def test_primeiro_acesso_criacao_admin_e_bloqueio_5_tentativas(tmp_env):
    from app.services.auth_service import (
        authenticate,
        create_admin_user,
        has_admin_user,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as session:
        assert has_admin_user(session) is False
        admin = create_admin_user(
            session,
            nome="Alyson",
            login="admin",
            senha="MinhaSenhaForte123",
        )
        assert admin.id is not None
        assert has_admin_user(session) is True

        base_now = datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc)

        # 4 tentativas erradas ainda não bloqueiam
        for i in range(4):
            res = authenticate(session, "admin", "errada", now=base_now + timedelta(seconds=i))
            assert res.ok is False
            assert res.locked is False

        # 5a tentativa errada bloqueia por 15 minutos
        res5 = authenticate(session, "admin", "errada", now=base_now + timedelta(seconds=10))
        assert res5.ok is False
        assert res5.locked is True
        assert "15" in res5.message or "bloqueado" in res5.message.lower()

        # Mesmo com senha correta durante o bloqueio, continua bloqueado
        res_durante = authenticate(
            session,
            "admin",
            "MinhaSenhaForte123",
            now=base_now + timedelta(minutes=5),
        )
        assert res_durante.ok is False
        assert res_durante.locked is True

        # Após 15 minutos, autenticação válida libera e zera contador
        res_depois = authenticate(
            session,
            "admin",
            "MinhaSenhaForte123",
            now=base_now + timedelta(minutes=16),
        )
        assert res_depois.ok is True
        assert res_depois.user is not None

        user_db = session.get(Usuario, admin.id)
        assert user_db.tentativas_falhas == 0
        assert user_db.bloqueado_ate is None

        logs = session.query(LogAuditoria).all()
        acoes = {log.acao for log in logs}
        assert "CRIAR_USUARIO_INICIAL" in acoes
        assert "CONTA_BLOQUEADA" in acoes
        assert "LOGIN_SUCESSO" in acoes
