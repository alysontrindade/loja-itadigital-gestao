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


def test_extras_service_importacao_codigo_barras_e_lote_xlsx(tmp_env):
    from app import create_app
    from app.db import get_session
    from app.models import Produto
    from app.services.extras_service import (
        calcular_custo_importacao,
        gerar_barras_svg,
        gerar_modelo_importacao_xlsx,
        importar_produtos_planilha,
    )

    # 1. Cálculo de importação
    calc = calcular_custo_importacao(
        valor_lote=100.0,
        moeda="USD",
        cotacao_usd=5.50,
        frete_brl=50.0,
        imposto_pct=20.0,
        outros_brl=20.0,
        quantidade=10,
        margem_alvo_pct=45.0,
        taxa_venda_pct=15.0,
    )
    # 100 * 5.50 = 550; +20% imposto = 110 -> 660 + 50 + 20 = 730 BRL / 10 = R$ 73,00/un (7300 centavos)
    assert calc["custo_unit_centavos"] == 7300
    assert calc["preco_sugerido_centavos"] > calc["custo_unit_centavos"]
    assert calc["lucro_unit_centavos"] > 0

    # 2. SVG de barras
    svg = gerar_barras_svg("7891000200301")
    assert "<svg" in svg and "<rect" in svg

    # 3. Modelo + Importação XLSX em lote
    modelo_bytes = gerar_modelo_importacao_xlsx()
    wb = openpyxl.load_workbook(io.BytesIO(modelo_bytes))
    ws = wb.active
    # Limpa linha de exemplo se houver e adiciona linhas de teste
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    ws.append(["Luminária Lua 3D", "LUM-LUA-01", "7891111222333", "28,50", "69,90", 5, 2, "un", "Decoração", "", "Luz LED"])
    ws.append(["Chaveiro Geek", "CHAV-GK-01", "", "4,00", "14,90", 12, 3, "un", "", "", ""])
    ws.append(["", "SEM-NOME", "", "10,00", "20,00", 1, 1, "un", "", "", ""])  # erro sem nome

    buf = io.BytesIO()
    wb.save(buf)

    app = create_app(tmp_env)
    with app.app_context():
        with get_session(app.extensions["engine"]) as db:
            res = importar_produtos_planilha(db, buf.getvalue(), "lote.xlsx")
            assert res["criados"] == 2
            assert len(res["erros"]) == 1

            # Reimportar mesmo arquivo deve ignorar os 2 SKUs duplicados
            res2 = importar_produtos_planilha(db, buf.getvalue(), "lote.xlsx")
            assert res2["criados"] == 0
            assert res2["duplicados"] == 2
            assert db.query(Produto).filter(Produto.sku == "LUM-LUA-01").first().estoque_atual == 5


def test_rotas_extras_etiquetas_whatsapp_importacao_e_importar(tmp_env):
    app, client, csrf = _setup_e_login(tmp_env)

    from app.db import get_session
    from app.services.cliente_service import criar_cliente
    from app.services.fornecedor_service import criar_fornecedor
    from app.services.produto_service import criar_produto

    with app.app_context():
        with get_session(app.extensions["engine"]) as db:
            forn = criar_fornecedor(db, {"nome": "Fornecedor Teste", "tipo": "local", "whatsapp": "(38) 99988-7766"})
            criar_cliente(db, {"nome": "Joana Prado", "whatsapp": "(38) 98877-6655", "aniversario": "10/11"})
            p = criar_produto(
                db,
                {
                    "nome": "Garrafa Térmica Inox",
                    "sku": "GAR-INOX-01",
                    "codigo_barras": "7890001112223",
                    "fornecedor_id": forn.id,
                    "custo": "22,00",
                    "preco": "59,90",
                    "estoque_inicial": 1,
                    "estoque_minimo": 3,
                },
                nicho_ids=[1],
            )
            prod_id = p.id

    assert client.get("/extras").status_code == 200

    # Etiquetas
    r_etq = client.get(f"/extras/etiquetas?produto_id={prod_id}&qtd=2")
    html_etq = r_etq.get_data(as_text=True)
    assert r_etq.status_code == 200
    assert "Garrafa Térmica Inox" in html_etq
    assert "59,90" in html_etq
    assert "<svg" in html_etq

    # WhatsApp
    r_wpp = client.get("/extras/whatsapp?mes_aniversario=11")
    html_wpp = r_wpp.get_data(as_text=True)
    assert r_wpp.status_code == 200
    assert "https://wa.me/5538988776655" in html_wpp
    assert "https://wa.me/5538999887766" in html_wpp

    # Calculadora de importação
    r_imp = client.post(
        "/extras/importacao",
        data={
            "csrf_token": csrf,
            "valor_lote": "200,00",
            "moeda": "USD",
            "cotacao_usd": "5,60",
            "frete_brl": "80,00",
            "imposto_pct": "20",
            "outros_brl": "0",
            "quantidade": "20",
            "margem_alvo_pct": "45",
            "taxa_venda_pct": "12",
        },
    )
    assert r_imp.status_code == 200
    assert "Preço sugerido" in r_imp.get_data(as_text=True)

    # Download modelo + Upload CSV
    r_mod = client.get("/extras/importar/modelo")
    assert r_mod.status_code == 200
    assert "spreadsheetml" in r_mod.headers.get("Content-Type", "")

    csv_conteudo = (
        "nome;sku;codigo_barras;custo;preco;estoque_inicial;estoque_minimo;unidade;nicho;fornecedor;descricao\n"
        "Agenda 2027 Floral;AGD-2027;7895556667778;14,00;34,90;6;2;un;Papelaria;;Capa dura\n"
    ).encode("utf-8-sig")
    r_up = client.post(
        "/extras/importar",
        data={"csrf_token": csrf, "arquivo": (io.BytesIO(csv_conteudo), "produtos.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r_up.status_code == 200
    assert "1 produto(s) importado(s)" in r_up.get_data(as_text=True)
