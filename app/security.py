import hmac
import secrets
from flask import abort, request, session


METODOS_MUTACAO = {"POST", "PUT", "PATCH", "DELETE"}


def ensure_csrf_token() -> str:
    """Garante um token CSRF por sessão para formulários e chamadas HTMX."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return str(token)


def validate_csrf_or_abort() -> None:
    """Valida token CSRF em requisições de mutação, retornando 403 se ausente/inválido."""
    if request.method not in METODOS_MUTACAO:
        return
    esperado = session.get("csrf_token")
    enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not esperado or not enviado:
        abort(403, description="Token CSRF ausente ou sessão expirada.")
    if not hmac.compare_digest(str(esperado), str(enviado)):
        abort(403, description="Token CSRF inválido.")
