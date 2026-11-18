import io
import re
import openpyxl


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


def _popular_dados_relatorio(app):
    from app.db import get_session
    from app.services.cliente_service import criar_cliente
    from app.services.compra_service import criar_compra
    from app.services.fornecedor_service import criar_fornecedor
    from app.services.kit_service import criar_kit
    from app.services.produto_service import criar_produto
    from app.services.venda_service import cancelar_venda, registrar_venda

    with app.app_context():
        engine = app.extensions["engine"]
        with get_session(engine) as db:
            forn = criar_fornecedor(db, {"nome": "Atacado Central", "tipo": "atacado"})
            cli = criar_cliente(
                db,
                {"nome": "Fernanda Silva", "whatsapp": "(38) 99900-1122", "aniversario": "15/11"},
            )
            # p1: alto giro (Nicho 1)
            p1 = criar_produto(
                db,
                {
                    "nome": "Caneca Personalizada Premium",
                    "sku": "CAN-PREM-01",
                    "fornecedor_id": forn.id,
                    "custo": "10,00",
                    "preco": "40,00",
                    "estoque_inicial": 20,
                    "estoque_minimo": 5,
                },
                nicho_ids=[1],
            )
            # p2: giro médio + estoque baixo após venda (Nicho 2)
            p2 = criar_produto(
                db,
                {
                    "nome": "Fone Bluetooth Mini",
                    "sku": "FONE-BT-01",
                    "fornecedor_id": forn.id,
                    "custo": "25,00",
                    "preco": "60,00",
                    "estoque_inicial": 4,
                    "estoque_minimo": 3,
                },
                nicho_ids=[2],
            )
            # p3: parado (estoque > 0 e sem vendas)
            p3 = criar_produto(
                db,
                {
                    "nome": "Porta Retrato Clássico",
                    "sku": "PR-CLAS-01",
                    "fornecedor_id": forn.id,
                    "custo": "8,00",
                    "preco": "22,00",
                    "estoque_inicial": 6,
                    "estoque_minimo": 2,
                },
                nicho_ids=[1],
            )
            kit = criar_kit(
                db,
                {"nome": "Kit Presente Duo", "nivel": "medio", "nicho_id": 1, "preco": "90,00"},
                [{"produto_id": p1.id, "quantidade": 1}, {"produto_id": p2.id, "quantidade": 1}],
            )
            # Compra recebida para compor relatório de compras
            criar_compra(
                db,
                fornecedor_id=forn.id,
                itens=[{"produto_id": p3.id, "quantidade": 2, "custo_unit": "8,00"}],
                frete="4,00",
                receber_agora=True,
            )
            # Venda 1: 3x p1 = 120,00 (custo 30,00, lucro 90,00) - Loja / Pix
            registrar_venda(
                db,
                {"cliente_id": cli.id, "canal": "loja", "forma_pagamento": "pix"},
                [{"tipo": "produto", "id": p1.id, "quantidade": 3}],
            )
            # Venda 2: 1x p2 (60,00) + 1x kit (90,00) - 10,00 desc = 140,00 (custo 25 + 35 = 60,00, lucro 80,00) - WhatsApp / Cartão
            registrar_venda(
                db,
                {"canal": "whatsapp", "forma_pagamento": "credito", "desconto": "10,00"},
                [
                    {"tipo": "produto", "id": p2.id, "quantidade": 1},
                    {"tipo": "kit", "id": kit.id, "quantidade": 1},
                ],
            )
            # Venda 3: cancelada (NÃO pode entrar no faturamento)
            v_canc = registrar_venda(
                db,
                {"canal": "loja", "forma_pagamento": "dinheiro"},
                [{"tipo": "produto", "id": p1.id, "quantidade": 1}],
            )
            cancelar_venda(db, v_canc.id, motivo="Teste cancelamento")


def test_relatorio_service_calculos_abc_nichos_estoque_e_exportacao(tmp_env):
    from app import create_app
    from app.db import get_session
    from app.services.relatorio_service import (
        exportar_relatorio_csv,
        exportar_relatorio_xlsx,
        gerar_relatorio_completo,
    )

    app = create_app(tmp_env)
    _popular_dados_relatorio(app)

    with app.app_context():
        with get_session(app.extensions["engine"]) as db:
            rel = gerar_relatorio_completo(db, filtros={"mes_aniversario": "11"})

    resumo = rel["resumo"]
    # Venda 1 (120,00) + Venda 2 (140,00) = 260,00 (26000 centavos); Venda 3 cancelada fora
    assert resumo["qtd_vendas"] == 2
    assert resumo["qtd_canceladas"] == 1
    assert resumo["faturamento_centavos"] == 26000
    assert resumo["custo_centavos"] == 9000
    assert resumo["lucro_centavos"] == 17000
    assert resumo["ticket_medio_centavos"] == 13000

    # Canais
    canais = {c["canal"]: c for c in rel["por_canal"]}
    assert canais["loja"]["faturamento_centavos"] == 12000
    assert canais["whatsapp"]["faturamento_centavos"] == 14000

    # Curva ABC: tem 3 itens vendidos (Caneca, Kit, Fone) ordenados por faturamento
    abc = rel["curva_abc"]
    assert len(abc) == 3
    assert abc[0]["classe"] == "A"
    assert abc[0]["nome"] == "Caneca Personalizada Premium"

    # Estoque crítico (p2 ficou com 4 - 1 - 1 = 2 <= min 3) e parado (p3 sem vendas)
    criticos_skus = {p["sku"] for p in rel["estoque_critico"]}
    parados_skus = {p["sku"] for p in rel["estoque_parado"]}
    assert "FONE-BT-01" in criticos_skus
    assert "PR-CLAS-01" in parados_skus

    # Aniversariantes de novembro
    assert any(a["nome"] == "Fernanda Silva" for a in rel["aniversariantes"])

    # Exportação XLSX
    xlsx_bytes = exportar_relatorio_xlsx(rel, nome_loja="Loja Itamarandiba")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert "Resumo Executivo" in wb.sheetnames
    assert "Curva ABC" in wb.sheetnames
    assert "Nichos" in wb.sheetnames
    assert "Estoque e Reposição" in wb.sheetnames

    # Exportação CSV (UTF-8 BOM + ponto e vírgula)
    csv_bytes = exportar_relatorio_csv(rel, secao="abc")
    csv_txt = csv_bytes.decode("utf-8-sig")
    assert "Caneca Personalizada Premium" in csv_txt
    assert ";" in csv_txt


def test_rotas_relatorios_filtros_e_downloads(tmp_env):
    app, client, _ = _setup_e_login(tmp_env)
    _popular_dados_relatorio(app)

    r_ok = client.get("/relatorios")
    html = r_ok.get_data(as_text=True)
    assert r_ok.status_code == 200
    assert "260,00" in html
    assert "170,00" in html
    assert "Caneca Personalizada Premium" in html
    assert "Porta Retrato Clássico" in html

    # Filtro por canal whatsapp exibe apenas R$ 140,00
    r_filt = client.get("/relatorios?canal=whatsapp")
    html_filt = r_filt.get_data(as_text=True)
    assert r_filt.status_code == 200
    assert "140,00" in html_filt

    # Limpar filtros restaura total
    r_limpar = client.get("/relatorios?limpar=1")
    assert r_limpar.status_code == 200
    assert "260,00" in r_limpar.get_data(as_text=True)

    # Download XLSX
    r_xlsx = client.get("/relatorios/exportar/xlsx")
    assert r_xlsx.status_code == 200
    assert "spreadsheetml" in r_xlsx.headers.get("Content-Type", "")
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.data))
    assert "Curva ABC" in wb.sheetnames

    # Download CSV
    r_csv = client.get("/relatorios/exportar/csv?secao=vendas")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers.get("Content-Type", "")
    assert "WhatsApp" in r_csv.data.decode("utf-8-sig")
