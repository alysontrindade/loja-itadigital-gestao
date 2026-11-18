import json
import re


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None, "csrf_token não encontrado no HTML"
    return match.group(1)


def _setup_e_login(tmp_env):
    from app import create_app

    app = create_app(tmp_env)
    client = app.test_client()
    r = client.get("/primeiro-acesso")
    csrf = _extract_csrf(r.get_data(as_text=True))
    r_ok = client.post(
        "/primeiro-acesso",
        data={
            "csrf_token": csrf,
            "nome": "Alyson",
            "login": "admin",
            "senha": "SenhaForte123",
            "confirmar_senha": "SenhaForte123",
            "nome_loja": "Loja Itamarandiba",
        },
        follow_redirects=True,
    )
    assert r_ok.status_code == 200
    return app, client, _extract_csrf(r_ok.get_data(as_text=True))


def _criar_base_dados_operacao(client, csrf: str):
    """Cria fornecedor, cliente e 2 produtos iniciais via serviços para exercitar todas as rotas."""
    from flask import current_app
    from app.db import get_session
    from app.services.fornecedor_service import criar_fornecedor
    from app.services.cliente_service import criar_cliente
    from app.services.produto_service import criar_produto

    with client.application.app_context():
        engine = current_app.extensions["engine"]
        with get_session(engine) as db:
            forn = criar_fornecedor(
                db,
                {
                    "nome": "Distribuidora Minas Gerais",
                    "tipo": "atacado",
                    "whatsapp": "(38) 99911-2233",
                },
            )
            cli = criar_cliente(
                db,
                {
                    "nome": "Mariana Costa",
                    "whatsapp": "(38) 98844-5566",
                    "cidade": "Itamarandiba",
                },
            )
            p1 = criar_produto(
                db,
                {
                    "nome": "Caneca Cerâmica Floral",
                    "sku": "CAN-FLOR-01",
                    "codigo_barras": "7891000200301",
                    "fornecedor_id": forn.id,
                    "custo": "12,00",
                    "preco": "29,90",
                    "estoque_inicial": 10,
                    "estoque_minimo": 3,
                },
                nicho_ids=[1],
            )
            p2 = criar_produto(
                db,
                {
                    "nome": "Caixa Presente Kraft",
                    "sku": "CX-KRAFT-01",
                    "codigo_barras": "7891000200302",
                    "fornecedor_id": forn.id,
                    "custo": "3,50",
                    "preco": "9,90",
                    "estoque_inicial": 8,
                    "estoque_minimo": 2,
                },
                nicho_ids=[1],
            )
            return forn.id, cli.id, p1.id, p2.id


def test_rotas_kits_e_composicao(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)
    _, _, p1_id, p2_id = _criar_base_dados_operacao(client, csrf)

    r_list = client.get("/kits")
    assert r_list.status_code == 200

    r_novo = client.get("/kits/novo")
    assert r_novo.status_code == 200

    r_create = client.post(
        "/kits/novo",
        data={
            "csrf_token": csrf,
            "nome": "Kit Café com Carinho",
            "nivel": "medio",
            "nicho_id": "1",
            "preco": "35,00",
            "descricao": "Caneca embrulhada para presente",
            "produto_id": [str(p1_id), str(p2_id)],
            "quantidade": ["1", "1"],
        },
        follow_redirects=True,
    )
    html_create = r_create.get_data(as_text=True)
    assert r_create.status_code == 200
    assert "Kit Café com Carinho" in html_create
    assert "Presente / Padrão" in html_create

    match_edit = re.search(r'/kits/(\d+)/editar', html_create)
    assert match_edit is not None
    kit_id = int(match_edit.group(1))

    r_edit_get = client.get(f"/kits/{kit_id}/editar")
    assert r_edit_get.status_code == 200

    r_edit_post = client.post(
        f"/kits/{kit_id}/editar",
        data={
            "csrf_token": csrf,
            "nome": "Kit Café Especial",
            "nivel": "premium",
            "nicho_id": "1",
            "preco": "39,90",
            "descricao": "Versão premium",
            "produto_id": [str(p1_id), str(p2_id)],
            "quantidade": ["1", "1"],
        },
        follow_redirects=True,
    )
    assert r_edit_post.status_code == 200
    assert "Kit Café Especial" in r_edit_post.get_data(as_text=True)

    r_toggle = client.post(
        f"/kits/{kit_id}/alternar",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert r_toggle.status_code == 200
    assert "inativado" in r_toggle.get_data(as_text=True)


def test_rotas_compras_rateio_recebimento_e_cancelamento(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)
    forn_id, _, p1_id, p2_id = _criar_base_dados_operacao(client, csrf)

    assert client.get("/compras").status_code == 200
    assert client.get("/compras/novo").status_code == 200

    # Compra 1 em aberto com frete de R$ 20,00 rateado entre 5x p1 (R$ 10,00) e 5x p2 (R$ 2,00)
    r_c1 = client.post(
        "/compras/novo",
        data={
            "csrf_token": csrf,
            "fornecedor_id": str(forn_id),
            "frete": "20,00",
            "impostos": "0,00",
            "outros_custos": "0,00",
            "observacoes": "Pedido semanal #01",
            "produto_id": [str(p1_id), str(p2_id)],
            "quantidade": ["5", "5"],
            "custo_unit": ["10,00", "2,00"],
        },
        follow_redirects=True,
    )
    html_c1 = r_c1.get_data(as_text=True)
    assert r_c1.status_code == 200
    assert "Em aberto" in html_c1
    assert "Distribuidora Minas Gerais" in html_c1

    match_rec = re.search(r'/compras/(\d+)/receber', html_c1)
    assert match_rec is not None
    compra1_id = int(match_rec.group(1))

    # Recebe compra e verifica entrada no estoque (p1: 10 + 5 = 15, p2: 8 + 5 = 13)
    r_rec = client.post(
        f"/compras/{compra1_id}/receber",
        data={"csrf_token": csrf, "atualizar_custo_produto": "1"},
        follow_redirects=True,
    )
    html_rec = r_rec.get_data(as_text=True)
    assert r_rec.status_code == 200
    assert "Recebida" in html_rec

    r_est = client.get("/estoque?busca=CAN-FLOR-01")
    assert r_est.status_code == 200
    assert "15" in r_est.get_data(as_text=True)

    # Compra 2 em aberto seguida de cancelamento
    r_c2 = client.post(
        "/compras/novo",
        data={
            "csrf_token": csrf,
            "fornecedor_id": str(forn_id),
            "frete": "0,00",
            "produto_id": [str(p1_id)],
            "quantidade": ["2"],
            "custo_unit": ["12,00"],
        },
        follow_redirects=True,
    )
    match_c2 = re.search(r'/compras/(\d+)/cancelar', r_c2.get_data(as_text=True))
    assert match_c2 is not None
    compra2_id = int(match_c2.group(1))

    r_canc = client.post(
        f"/compras/{compra2_id}/cancelar",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert r_canc.status_code == 200
    assert "Cancelada" in r_canc.get_data(as_text=True)


def test_rotas_estoque_ajuste_perda_e_movimentos(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)
    _, _, p1_id, _ = _criar_base_dados_operacao(client, csrf)

    assert client.get("/estoque").status_code == 200
    assert client.get("/estoque/movimentos").status_code == 200

    # Ajuste sem motivo falha com 400 e mensagem clara
    r_sem_motivo = client.post(
        "/estoque/ajustar",
        data={
            "csrf_token": csrf,
            "produto_id": str(p1_id),
            "tipo": "perda",
            "quantidade": "1",
            "motivo": "",
        },
    )
    assert r_sem_motivo.status_code == 400
    assert "motivo" in r_sem_motivo.get_data(as_text=True).lower()

    # Perda acima do saldo disponível é bloqueada
    r_neg = client.post(
        "/estoque/ajustar",
        data={
            "csrf_token": csrf,
            "produto_id": str(p1_id),
            "tipo": "perda",
            "quantidade": "99",
            "motivo": "Teste negativo",
        },
    )
    assert r_neg.status_code == 400
    assert "insuficiente" in r_neg.get_data(as_text=True).lower()

    # Perda válida de 1 unidade reduz estoque de 10 para 9 e entra no histórico
    r_ok = client.post(
        "/estoque/ajustar",
        data={
            "csrf_token": csrf,
            "produto_id": str(p1_id),
            "tipo": "perda",
            "quantidade": "1",
            "motivo": "Quebra na prateleira",
        },
        follow_redirects=True,
    )
    assert r_ok.status_code == 200

    r_mov = client.get(f"/estoque/movimentos?produto_id={p1_id}")
    assert r_mov.status_code == 200
    assert "Quebra na prateleira" in r_mov.get_data(as_text=True)


def test_rotas_pdv_busca_finalizacao_recibo_e_cancelamento_venda(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)
    _, cli_id, p1_id, p2_id = _criar_base_dados_operacao(client, csrf)

    # Cria 1 kit ativo com 1x p1 + 1x p2
    client.post(
        "/kits/novo",
        data={
            "csrf_token": csrf,
            "nome": "Combo Presente Dia",
            "nivel": "medio",
            "nicho_id": "1",
            "preco": "36,00",
            "produto_id": [str(p1_id), str(p2_id)],
            "quantidade": ["1", "1"],
        },
        follow_redirects=True,
    )

    r_pdv = client.get("/pdv")
    html_pdv = r_pdv.get_data(as_text=True)
    assert r_pdv.status_code == 200
    assert "Caneca Cerâmica Floral" in html_pdv
    assert "Combo Presente Dia" in html_pdv

    # Busca por código de barras (HTMX parcial e JSON)
    r_busca_html = client.get("/pdv/buscar?busca=7891000200301")
    assert r_busca_html.status_code == 200
    assert "Caneca Cerâmica Floral" in r_busca_html.get_data(as_text=True)

    r_busca_json = client.get("/pdv/buscar?busca=7891000200301&formato=json")
    assert r_busca_json.status_code == 200
    payload = r_busca_json.get_json()
    assert len(payload["produtos"]) == 1
    assert payload["produtos"][0]["match_exato_barras"] is True

    # Descobre kit_id via payload de busca
    payload_todos = client.get("/pdv/buscar?busca=Combo&formato=json").get_json()
    kit_id = payload_todos["kits"][0]["id"]

    # Finaliza venda no PDV com 2x p1 avulso + 1x kit (total esperado: 2*29,90 + 36,00 - 5,80 desc = 90,00)
    itens_json = json.dumps(
        [
            {"tipo": "produto", "id": p1_id, "quantidade": 2},
            {"tipo": "kit", "id": kit_id, "quantidade": 1},
        ]
    )
    r_fin = client.post(
        "/pdv/finalizar",
        data={
            "csrf_token": csrf,
            "cliente_id": str(cli_id),
            "canal": "whatsapp",
            "forma_pagamento": "pix",
            "desconto": "5,80",
            "frete": "0,00",
            "observacoes": "Embrulhar para presente",
            "itens_json": itens_json,
        },
        follow_redirects=True,
    )
    html_recibo = r_fin.get_data(as_text=True)
    assert r_fin.status_code == 200
    assert "Mariana Costa" in html_recibo
    assert "90,00" in html_recibo
    assert "Combo Presente Dia" in html_recibo

    # Verifica baixa de estoque: p1 (10 - 2 - 1 = 7), p2 (8 - 1 = 7)
    from flask import current_app
    from app.db import get_session
    from app.models import Produto

    with client.application.app_context():
        with get_session(current_app.extensions["engine"]) as db:
            assert db.get(Produto, p1_id).estoque_atual == 7
            assert db.get(Produto, p2_id).estoque_atual == 7

    # Lista e filtra vendas
    r_vendas = client.get("/vendas?canal=whatsapp")
    assert r_vendas.status_code == 200
    assert "Mariana Costa" in r_vendas.get_data(as_text=True)

    # Cancela venda pelo comprovante e valida devolução do estoque
    match_canc = re.search(r'/vendas/(\d+)/cancelar', html_recibo)
    assert match_canc is not None
    venda_id = int(match_canc.group(1))

    r_canc = client.post(
        f"/vendas/{venda_id}/cancelar",
        data={"csrf_token": csrf, "motivo": "Cliente desistiu"},
        follow_redirects=True,
    )
    assert r_canc.status_code == 200
    assert "Cancelada" in r_canc.get_data(as_text=True)

    with client.application.app_context():
        with get_session(current_app.extensions["engine"]) as db:
            assert db.get(Produto, p1_id).estoque_atual == 10
            assert db.get(Produto, p2_id).estoque_atual == 8
