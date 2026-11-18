from pathlib import Path
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from app.db import get_session, init_db
from app.models import (
    Cliente,
    Fornecedor,
    Kit,
    LogAuditoria,
    Nicho,
    Produto,
    Venda,
)
from app.services.audit_service import registrar_auditoria
from app.services.auth_service import change_password
from app.services.backup_service import (
    create_backup,
    list_backups,
    prune_backups,
    restore_backup,
)
from app.services.config_service import TEMAS_VALIDOS, get_all_config, set_config
from app.services.estoque_service import listar_posicao_estoque
from app.services.venda_service import resumo_vendas_hoje

bp = Blueprint("main", __name__)


def _engine():
    return current_app.extensions["engine"]


def _settings():
    return current_app.config["LOJA_SETTINGS"]


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/")
def inicio():
    with get_session(_engine()) as db:
        nichos = db.query(Nicho).filter(Nicho.ativo == 1).order_by(Nicho.id).all()
        vendas_hoje = resumo_vendas_hoje(db)
        estoque_zerado = listar_posicao_estoque(db, status="zerado")
        estoque_baixo = listar_posicao_estoque(db, status="baixo")
        estoque_critico_itens = (estoque_zerado + estoque_baixo)[:6]
        resumo = {
            "total_nichos": len(nichos),
            "total_produtos": db.query(Produto).filter(Produto.ativo == 1).count(),
            "total_kits": db.query(Kit).filter(Kit.ativo == 1).count(),
            "total_fornecedores": db.query(Fornecedor).filter(Fornecedor.ativo == 1).count(),
            "total_clientes": db.query(Cliente).count(),
            "total_vendas": db.query(Venda).filter(Venda.status == "concluida").count(),
        }
    return render_template(
        "inicio.html",
        nichos=nichos,
        resumo=resumo,
        vendas_hoje=vendas_hoje,
        estoque_critico_itens=estoque_critico_itens,
    )


@bp.route("/configuracoes")
def configuracoes():
    settings = _settings()
    backups = list_backups(settings.backup_dir)
    with get_session(_engine()) as db:
        cfg = get_all_config(db)
        logs = (
            db.query(LogAuditoria)
            .order_by(LogAuditoria.id.desc())
            .limit(12)
            .all()
        )
    return render_template(
        "config/index.html",
        cfg=cfg,
        backups=backups,
        logs=logs,
        data_dir=str(settings.data_dir),
        backup_dir=str(settings.backup_dir),
    )


@bp.route("/configuracoes/aparencia", methods=["POST"])
def salvar_configuracoes():
    tema = request.form.get("tema", "claro").strip()
    if tema not in TEMAS_VALIDOS:
        tema = "claro"
    nome_loja = request.form.get("nome_loja", "").strip() or "Loja Itamarandiba"

    try:
        margem = max(0, min(95, int(request.form.get("margem_alvo_pct", "45"))))
    except ValueError:
        margem = 45

    try:
        expira = max(5, min(1440, int(request.form.get("sessao_expira_minutos", "120"))))
    except ValueError:
        expira = 120

    with get_session(_engine()) as db:
        set_config(db, "tema", tema)
        set_config(db, "nome_loja", nome_loja)
        set_config(db, "margem_alvo_pct", str(margem))
        set_config(db, "sessao_expira_minutos", str(expira))
        registrar_auditoria(
            db,
            acao="ATUALIZAR_CONFIGURACAO",
            entidade="configuracao",
            detalhes=f"Tema={tema}; MargemAlvo={margem}%; Sessao={expira}min.",
            usuario_id=session.get("user_id"),
        )
        db.commit()

    flash("Configurações e tema salvos com sucesso.", "ok")
    return redirect(url_for("main.configuracoes"))


@bp.route("/configuracoes/tema-rapido", methods=["POST"])
def alternar_tema_rapido():
    ordem = ["claro", "escuro", "contraste"]
    with get_session(_engine()) as db:
        atual = get_all_config(db).get("tema", "claro")
        proximo = ordem[(ordem.index(atual) + 1) % len(ordem)] if atual in ordem else "escuro"
        set_config(db, "tema", proximo)
        registrar_auditoria(
            db,
            acao="ALTERNAR_TEMA",
            entidade="configuracao",
            detalhes=f"Tema alterado para {proximo}.",
            usuario_id=session.get("user_id"),
        )
        db.commit()
    destino = request.form.get("next") or request.referrer or url_for("main.inicio")
    if not str(destino).startswith("/"):
        destino = url_for("main.inicio")
    return redirect(destino)


@bp.route("/configuracoes/senha", methods=["POST"])
def alterar_senha():
    uid = session.get("user_id")
    atual = request.form.get("senha_atual", "")
    nova = request.form.get("nova_senha", "")
    confirmar = request.form.get("confirmar_nova_senha", "")
    if nova != confirmar:
        flash("A nova senha e a confirmação não coincidem.", "danger")
        return redirect(url_for("main.configuracoes"))

    with get_session(_engine()) as db:
        ok, msg = change_password(db, int(uid), atual, nova)
    flash(msg, "ok" if ok else "danger")
    return redirect(url_for("main.configuracoes"))


@bp.route("/configuracoes/backup", methods=["POST"])
def executar_backup_manual():
    settings = _settings()
    try:
        criado = create_backup(settings, prefix="backup")
        prune_backups(settings.backup_dir)
        with get_session(_engine()) as db:
            registrar_auditoria(
                db,
                acao="BACKUP_MANUAL",
                entidade="backup",
                entidade_id=criado.name,
                detalhes=f"Backup salvo em {criado.name}.",
                usuario_id=session.get("user_id"),
            )
            db.commit()
        flash(f"Backup gerado e verificado: {criado.name}", "ok")
    except Exception as exc:
        flash(f"Erro ao gerar backup: {exc}", "danger")
    return redirect(url_for("main.configuracoes"))


@bp.route("/configuracoes/backup/restaurar", methods=["POST"])
def restaurar_backup_rota():
    settings = _settings()
    nome = request.form.get("arquivo", "").strip()
    if not nome or Path(nome).name != nome or not nome.endswith(".zip"):
        flash("Nome de arquivo de backup inválido.", "danger")
        return redirect(url_for("main.configuracoes"))

    alvo = (settings.backup_dir / nome).resolve()
    if alvo.parent != settings.backup_dir.resolve() or not alvo.exists():
        flash("Arquivo de backup não encontrado.", "danger")
        return redirect(url_for("main.configuracoes"))

    try:
        _engine().dispose()
        seguranca = restore_backup(settings, alvo)
        current_app.extensions["engine"] = init_db(settings)
        with get_session(_engine()) as db:
            registrar_auditoria(
                db,
                acao="RESTAURAR_BACKUP",
                entidade="backup",
                entidade_id=nome,
                detalhes=f"Restaurado '{nome}'. Cópia de segurança: '{seguranca.name}'.",
                usuario_id=session.get("user_id"),
            )
            db.commit()
        flash(
            f"Backup '{nome}' restaurado com sucesso (cópia prévia salva: {seguranca.name}).",
            "ok",
        )
    except Exception as exc:
        current_app.extensions["engine"] = init_db(settings)
        flash(f"Falha ao restaurar backup: {exc}", "danger")

    return redirect(url_for("main.configuracoes"))


def _validar_nome_imagem(arquivo: str) -> str:
    if not arquivo or Path(arquivo).name != arquivo or ".." in arquivo:
        abort(404)
    if not arquivo.lower().endswith((".webp", ".jpg", ".jpeg", ".png")):
        abort(404)
    return arquivo


@bp.route("/midia/fotos/<path:arquivo>")
def foto_produto(arquivo: str):
    nome = _validar_nome_imagem(arquivo)
    return send_from_directory(_settings().fotos_dir, nome)


@bp.route("/midia/fotos/thumb/<path:arquivo>")
def foto_thumb(arquivo: str):
    nome = _validar_nome_imagem(arquivo)
    return send_from_directory(_settings().fotos_dir / "thumbs", nome)
