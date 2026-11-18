from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import math
import secrets
from sqlalchemy.orm import Session

from app.models import Usuario
from app.services.audit_service import registrar_auditoria

MAX_TENTATIVAS_FALHAS = 5
MINUTOS_BLOQUEIO = 15
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    locked: bool = False
    message: str = ""
    user: Usuario | None = None


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def hash_password(senha: str) -> str:
    """Gera hash seguro com scrypt e salt aleatório por senha."""
    if not senha or len(senha) < 6:
        raise ValueError("A senha deve ter pelo menos 6 caracteres.")
    salt = secrets.token_bytes(16)
    derivada = hashlib.scrypt(
        senha.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derivada.hex()}"


def verify_password(senha: str, senha_hash: str) -> bool:
    """Verifica senha contra hash scrypt armazenado em tempo constante."""
    if not senha or not senha_hash:
        return False
    partes = senha_hash.split("$")
    if len(partes) != 6 or partes[0] != "scrypt":
        return False
    try:
        n = int(partes[1])
        r = int(partes[2])
        p = int(partes[3])
        salt = bytes.fromhex(partes[4])
        esperado = bytes.fromhex(partes[5])
    except ValueError:
        return False

    calculado = hashlib.scrypt(
        senha.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(esperado),
    )
    return hmac.compare_digest(calculado, esperado)


def has_admin_user(session: Session) -> bool:
    return session.query(Usuario.id).first() is not None


def create_admin_user(session: Session, nome: str, login: str, senha: str) -> Usuario:
    """Cria o usuário administrador no primeiro acesso."""
    if has_admin_user(session):
        raise ValueError("Já existe um usuário administrador cadastrado.")
    nome_limpo = (nome or "").strip()
    login_limpo = (login or "").strip().lower()
    if not nome_limpo or not login_limpo:
        raise ValueError("Nome e login são obrigatórios.")

    usuario = Usuario(
        nome=nome_limpo,
        login=login_limpo,
        senha_hash=hash_password(senha),
        tentativas_falhas=0,
        bloqueado_ate=None,
    )
    session.add(usuario)
    session.flush()
    registrar_auditoria(
        session,
        acao="CRIAR_USUARIO_INICIAL",
        entidade="usuario",
        entidade_id=usuario.id,
        detalhes=f"Administrador '{login_limpo}' configurado no primeiro acesso.",
        usuario_id=usuario.id,
    )
    session.commit()
    session.refresh(usuario)
    return usuario


def authenticate(
    session: Session,
    login: str,
    senha: str,
    now: datetime | None = None,
) -> AuthResult:
    """Autentica usuário aplicando bloqueio temporário após 5 falhas consecutivas."""
    agora = _utc_now(now).replace(microsecond=0)
    login_limpo = (login or "").strip().lower()
    usuario = session.query(Usuario).filter(Usuario.login == login_limpo).first()

    if usuario is None:
        registrar_auditoria(
            session,
            acao="LOGIN_FALHA",
            entidade="usuario",
            detalhes=f"Tentativa com login inexistente: '{login_limpo}'.",
        )
        session.commit()
        return AuthResult(ok=False, message="Usuário ou senha inválidos.")

    if usuario.bloqueado_ate:
        bloqueado_dt = datetime.fromisoformat(usuario.bloqueado_ate)
        if bloqueado_dt.tzinfo is None:
            bloqueado_dt = bloqueado_dt.replace(tzinfo=timezone.utc)
        if agora < bloqueado_dt:
            restante_min = max(1, math.ceil((bloqueado_dt - agora).total_seconds() / 60))
            registrar_auditoria(
                session,
                acao="LOGIN_BLOQUEADO",
                entidade="usuario",
                entidade_id=usuario.id,
                detalhes=f"Tentativa durante bloqueio ({restante_min} min restantes).",
                usuario_id=usuario.id,
            )
            session.commit()
            return AuthResult(
                ok=False,
                locked=True,
                message=f"Acesso temporariamente bloqueado. Tente novamente em {restante_min} minuto(s).",
            )
        usuario.bloqueado_ate = None
        usuario.tentativas_falhas = 0

    if not verify_password(senha, usuario.senha_hash):
        usuario.tentativas_falhas += 1
        if usuario.tentativas_falhas >= MAX_TENTATIVAS_FALHAS:
            limite = agora + timedelta(minutes=MINUTOS_BLOQUEIO)
            usuario.bloqueado_ate = limite.isoformat()
            registrar_auditoria(
                session,
                acao="CONTA_BLOQUEADA",
                entidade="usuario",
                entidade_id=usuario.id,
                detalhes=f"Conta bloqueada por {MINUTOS_BLOQUEIO} minutos após {MAX_TENTATIVAS_FALHAS} falhas.",
                usuario_id=usuario.id,
            )
            session.commit()
            return AuthResult(
                ok=False,
                locked=True,
                message=f"Muitas tentativas inválidas. Acesso bloqueado por {MINUTOS_BLOQUEIO} minutos.",
            )

        restantes = MAX_TENTATIVAS_FALHAS - usuario.tentativas_falhas
        registrar_auditoria(
            session,
            acao="LOGIN_FALHA",
            entidade="usuario",
            entidade_id=usuario.id,
            detalhes=f"Senha inválida ({usuario.tentativas_falhas}/{MAX_TENTATIVAS_FALHAS}).",
            usuario_id=usuario.id,
        )
        session.commit()
        return AuthResult(
            ok=False,
            message=f"Usuário ou senha inválidos. Restam {restantes} tentativa(s) antes do bloqueio.",
        )

    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    usuario.ultimo_acesso = agora.isoformat()
    registrar_auditoria(
        session,
        acao="LOGIN_SUCESSO",
        entidade="usuario",
        entidade_id=usuario.id,
        detalhes="Login efetuado com sucesso.",
        usuario_id=usuario.id,
    )
    session.commit()
    session.refresh(usuario)
    return AuthResult(ok=True, message="Login realizado.", user=usuario)


def change_password(
    session: Session,
    usuario_id: int,
    senha_atual: str,
    nova_senha: str,
) -> tuple[bool, str]:
    """Altera a senha do usuário validando a senha atual."""
    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        return False, "Usuário não encontrado."
    if not verify_password(senha_atual, usuario.senha_hash):
        return False, "Senha atual incorreta."
    try:
        usuario.senha_hash = hash_password(nova_senha)
    except ValueError as exc:
        return False, str(exc)

    registrar_auditoria(
        session,
        acao="SENHA_ALTERADA",
        entidade="usuario",
        entidade_id=usuario.id,
        detalhes="Senha alterada nas configurações.",
        usuario_id=usuario.id,
    )
    session.commit()
    return True, "Senha atualizada com sucesso."
