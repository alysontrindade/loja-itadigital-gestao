from typing import Mapping
from flask import current_app, request, session


def get_engine():
    return current_app.extensions["engine"]


def get_settings():
    return current_app.config["LOJA_SETTINGS"]


def current_user_id() -> int | None:
    uid = session.get("user_id")
    return int(uid) if uid is not None else None


def gerenciar_filtros_sessao(
    chave_sessao: str,
    campos: tuple[str, ...],
    padroes: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Lembra a última seleção de filtros na sessão e permite limpar com ?limpar=1."""
    base = {c: "" for c in campos}
    if padroes:
        base.update(padroes)

    if request.args.get("limpar") == "1":
        session.pop(chave_sessao, None)
        return base

    if any(c in request.args for c in campos):
        atual = dict(base)
        for c in campos:
            if c in request.args:
                atual[c] = request.args.get(c, "").strip()
        session[chave_sessao] = atual
        return atual

    salvos = session.get(chave_sessao)
    if isinstance(salvos, dict):
        combinado = dict(base)
        for c in campos:
            if c in salvos:
                combinado[c] = str(salvos[c])
        return combinado

    return base
