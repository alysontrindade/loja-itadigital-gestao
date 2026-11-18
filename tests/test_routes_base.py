import re
import time


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None, "csrf_token não encontrado no formulário HTML"
    return match.group(1)


def test_fluxo_primeiro_acesso_login_csrf_e_expiracao(tmp_env):
    from app import create_app

    tmp_env["SESSION_TIMEOUT_MINUTES"] = 1
    app = create_app(tmp_env)
    client = app.test_client()

    # Health endpoint responde sem auth
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"

    # Sem usuário cadastrado, / redireciona para /primeiro-acesso
    r_root = client.get("/", follow_redirects=False)
    assert r_root.status_code == 302
    assert "/primeiro-acesso" in r_root.headers["Location"]

    # POST sem CSRF deve falhar com 403
    r_no_csrf = client.post(
        "/primeiro-acesso",
        data={"nome": "Alyson", "login": "admin", "senha": "SenhaForte123", "confirmar_senha": "SenhaForte123"},
    )
    assert r_no_csrf.status_code == 403

    # Setup com CSRF válido cria usuário, autentica e abre Início
    r_setup_page = client.get("/primeiro-acesso")
    assert r_setup_page.status_code == 200
    csrf = _extract_csrf(r_setup_page.get_data(as_text=True))

    r_setup_post = client.post(
        "/primeiro-acesso",
        data={
            "csrf_token": csrf,
            "nome": "Alyson",
            "login": "admin",
            "senha": "SenhaForte123",
            "confirmar_senha": "SenhaForte123",
            "nome_loja": "Presentes & Variedades Itamarandiba",
        },
        follow_redirects=True,
    )
    assert r_setup_post.status_code == 200
    body = r_setup_post.get_data(as_text=True)
    assert "Presentes &amp; Variedades Itamarandiba" in body or "Presentes & Variedades Itamarandiba" in body
    assert "PDV / Caixa" in body
    assert "Configurações" in body

    # Logout encerra sessão e exige /login
    csrf_home = _extract_csrf(body)
    r_logout = client.post("/logout", data={"csrf_token": csrf_home}, follow_redirects=False)
    assert r_logout.status_code == 302
    assert "/login" in r_logout.headers["Location"]

    # Login com senha errada retorna 401
    r_login_page = client.get("/login")
    csrf_login = _extract_csrf(r_login_page.get_data(as_text=True))
    r_bad = client.post(
        "/login",
        data={"csrf_token": csrf_login, "login": "admin", "senha": "errada"},
    )
    assert r_bad.status_code == 401

    # Login correto funciona
    csrf_login2 = _extract_csrf(r_bad.get_data(as_text=True))
    r_ok = client.post(
        "/login",
        data={"csrf_token": csrf_login2, "login": "admin", "senha": "SenhaForte123"},
        follow_redirects=True,
    )
    assert r_ok.status_code == 200

    # Sessão expirada por inatividade redireciona para /login
    with client.session_transaction() as sess:
        sess["last_activity"] = int(time.time()) - 120
    r_expired = client.get("/", follow_redirects=False)
    assert r_expired.status_code == 302
    assert "/login" in r_expired.headers["Location"]


def test_configuracoes_tema_backup_manual_e_menus_em_construcao(tmp_env):
    from app import create_app

    app = create_app(tmp_env)
    client = app.test_client()

    # Cria admin
    r_setup = client.get("/primeiro-acesso")
    csrf = _extract_csrf(r_setup.get_data(as_text=True))
    client.post(
        "/primeiro-acesso",
        data={
            "csrf_token": csrf,
            "nome": "Alyson",
            "login": "admin",
            "senha": "SenhaForte123",
            "confirmar_senha": "SenhaForte123",
        },
        follow_redirects=True,
    )

    # Alternar tema para escuro em Configurações
    r_cfg = client.get("/configuracoes")
    assert r_cfg.status_code == 200
    csrf_cfg = _extract_csrf(r_cfg.get_data(as_text=True))

    r_tema = client.post(
        "/configuracoes/aparencia",
        data={
            "csrf_token": csrf_cfg,
            "tema": "escuro",
            "nome_loja": "Loja Itamarandiba",
            "margem_alvo_pct": "50",
            "sessao_expira_minutos": "120",
        },
        follow_redirects=True,
    )
    assert r_tema.status_code == 200
    html_tema = r_tema.get_data(as_text=True)
    assert 'data-tema="escuro"' in html_tema

    # Dispara backup manual
    csrf_bkp = _extract_csrf(html_tema)
    r_bkp = client.post(
        "/configuracoes/backup",
        data={"csrf_token": csrf_bkp},
        follow_redirects=True,
    )
    assert r_bkp.status_code == 200
    assert "backup_" in r_bkp.get_data(as_text=True)

    # Rotas futuras respondem 200 com layout intacto
    for rota in ["/pdv", "/produtos", "/nichos", "/kits", "/fornecedores", "/compras", "/estoque", "/clientes", "/relatorios"]:
        r = client.get(rota)
        assert r.status_code == 200


def test_tema_rapido_alteracao_senha_e_restauracao_via_http(tmp_env):
    from pathlib import Path
    from app import create_app

    app = create_app(tmp_env)
    client = app.test_client()

    r_setup = client.get("/primeiro-acesso")
    csrf = _extract_csrf(r_setup.get_data(as_text=True))
    client.post(
        "/primeiro-acesso",
        data={
            "csrf_token": csrf,
            "nome": "Alyson",
            "login": "admin",
            "senha": "SenhaForte123",
            "confirmar_senha": "SenhaForte123",
            "nome_loja": "Estado Original",
        },
        follow_redirects=True,
    )

    # Alternância rápida de tema: claro -> escuro -> contraste -> claro
    r_cfg = client.get("/configuracoes")
    csrf_cfg = _extract_csrf(r_cfg.get_data(as_text=True))
    r_q1 = client.post("/configuracoes/tema-rapido", data={"csrf_token": csrf_cfg, "next": "/"}, follow_redirects=True)
    assert 'data-tema="escuro"' in r_q1.get_data(as_text=True)

    # Cria backup com Estado Original + tema escuro
    csrf_2 = _extract_csrf(r_q1.get_data(as_text=True))
    r_bkp = client.post("/configuracoes/backup", data={"csrf_token": csrf_2}, follow_redirects=True)
    bkp_files = list(Path(tmp_env["BACKUP_DIR"]).glob("backup_*.zip"))
    assert len(bkp_files) == 1
    bkp_name = bkp_files[0].name

    # Altera tema para contraste e nome da loja
    csrf_3 = _extract_csrf(r_bkp.get_data(as_text=True))
    r_alt = client.post(
        "/configuracoes/aparencia",
        data={
            "csrf_token": csrf_3,
            "tema": "contraste",
            "nome_loja": "Estado Modificado",
            "margem_alvo_pct": "55",
            "sessao_expira_minutos": "120",
        },
        follow_redirects=True,
    )
    assert 'data-tema="contraste"' in r_alt.get_data(as_text=True)
    assert "Estado Modificado" in r_alt.get_data(as_text=True)

    # Tentativa de path traversal na restauração é rejeitada sem quebrar
    csrf_4 = _extract_csrf(r_alt.get_data(as_text=True))
    r_bad_restore = client.post(
        "/configuracoes/backup/restaurar",
        data={"csrf_token": csrf_4, "arquivo": "../evil.zip"},
        follow_redirects=True,
    )
    assert "inválido" in r_bad_restore.get_data(as_text=True).lower()

    # Restaura backup válido via HTTP -> volta nome e tema anteriores
    csrf_5 = _extract_csrf(r_bad_restore.get_data(as_text=True))
    r_restore = client.post(
        "/configuracoes/backup/restaurar",
        data={"csrf_token": csrf_5, "arquivo": bkp_name},
        follow_redirects=True,
    )
    html_restored = r_restore.get_data(as_text=True)
    assert 'data-tema="escuro"' in html_restored
    assert "Estado Original" in html_restored

    # Altera senha e valida novo login
    csrf_6 = _extract_csrf(html_restored)
    r_pw = client.post(
        "/configuracoes/senha",
        data={
            "csrf_token": csrf_6,
            "senha_atual": "SenhaForte123",
            "nova_senha": "NovaSenha456",
            "confirmar_nova_senha": "NovaSenha456",
        },
        follow_redirects=True,
    )
    assert "sucesso" in r_pw.get_data(as_text=True).lower()

    csrf_7 = _extract_csrf(r_pw.get_data(as_text=True))
    client.post("/logout", data={"csrf_token": csrf_7}, follow_redirects=False)
    r_login_page = client.get("/login")
    csrf_login = _extract_csrf(r_login_page.get_data(as_text=True))
    r_new_login = client.post(
        "/login",
        data={"csrf_token": csrf_login, "login": "admin", "senha": "NovaSenha456"},
        follow_redirects=True,
    )
    assert r_new_login.status_code == 200
    assert "Estado Original" in r_new_login.get_data(as_text=True)

