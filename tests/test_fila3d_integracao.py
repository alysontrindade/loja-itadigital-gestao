import re

from app import create_app


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _setup_e_login(tmp_env):
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
    csrf_hub = _extract_csrf(r_ok.get_data(as_text=True))
    return app, client, csrf_hub


def test_fila3d_hub_e_catalogo_publico(tmp_env):
    _, client, _ = _setup_e_login(tmp_env)

    res_hub = client.get("/fila-3d")
    assert res_hub.status_code == 200
    html = res_hub.get_data(as_text=True)
    assert "Ita Arte 3D" in html
    assert "Fila de Impressão" in html
    assert "meta name=\"csrf-token\"" in html

    res_pub = client.get("/catalogo-publico")
    assert res_pub.status_code == 200
    assert "Ita Arte 3D — Catálogo de Produtos" in res_pub.get_data(as_text=True)

    res_meta = client.get("/api/catalog-meta")
    assert res_meta.status_code == 200
    meta = res_meta.get_json()
    assert "PLA" in meta["filaments"]
    assert "categories" in meta

    res_sum = client.get("/api/hub/summary")
    assert res_sum.status_code == 200
    assert "models_total" in res_sum.get_json()


def test_fila3d_fluxo_completo_modelos_fila_estoque_vendas_midia(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)
    headers = {"X-CSRF-Token": csrf}

    # 1. Importação de modelos em lote
    r_imp = client.post(
        "/api/import/batch",
        json={"raw_text": "https://makerworld.com/en/models/555111-organizador-mesa-test"},
        headers=headers,
    )
    assert r_imp.status_code == 200
    imp_data = r_imp.get_json()
    assert imp_data["count"] == 1
    model_id = imp_data["items"][0]["id"]

    r_models = client.get("/api/models?q=organizador")
    assert r_models.status_code == 200
    assert r_models.get_json()["total"] == 1

    # 2. Cadastrar impressora e carretel
    r_pr = client.post(
        "/api/printers",
        json={"name": "Bambu Lab A1 Teste", "brand_model": "Bambu Lab A1", "ams_slots": 4},
        headers=headers,
    )
    assert r_pr.status_code == 200
    printer_id = r_pr.get_json()["id"]

    r_sp = client.post(
        "/api/spools",
        json={"brand": "Voolt3D", "material": "PLA", "color_name": "Preto Fosco", "initial_grams": 1000},
        headers=headers,
    )
    assert r_sp.status_code == 200
    spool_id = r_sp.get_json()["id"]

    # 3. Adicionar na fila e concluir com baixa de filamento
    r_job = client.post(
        "/api/queue",
        json={
            "model_id": model_id,
            "printer_id": printer_id,
            "spool_id": spool_id,
            "title": "Organizador de Mesa",
            "estimated_grams": 100,
            "rubric_name": "Encomenda Teste",
        },
        headers=headers,
    )
    assert r_job.status_code == 200
    job_id = r_job.get_json()["id"]

    r_done = client.patch(
        f"/api/queue/{job_id}",
        json={"status": "Concluída", "actual_grams_used": 120},
        headers=headers,
    )
    assert r_done.status_code == 200
    assert r_done.get_json()["status"] == "Concluída"

    r_sp_after = client.get("/api/spools")
    assert r_sp_after.get_json()["items"][0]["remaining_grams"] == 880.0

    # 4. Catálogo & Venda com criação automática de fila quando falta estoque
    r_cat = client.post(
        "/api/catalog",
        json={
            "code": "#99",
            "model_id": model_id,
            "name": "Organizador Pro",
            "category": "Organizadores & Utilitários",
            "filament_grams": 80,
            "pricing_mode": "rate_per_gram",
            "rate_per_gram_brl": 0.5,
            "stock_qty": 0,
        },
        headers=headers,
    )
    assert r_cat.status_code == 200
    cat_item = r_cat.get_json()
    assert cat_item["sale_price_brl"] == 40.0

    r_sale = client.post(
        "/api/sales",
        json={
            "catalog_item_id": cat_item["id"],
            "customer_name": "João",
            "channel": "WhatsApp",
            "quantity": 2,
            "unit_price_brl": 40.0,
            "payment_status": "Pago",
            "auto_queue_missing": True,
        },
        headers=headers,
    )
    assert r_sale.status_code == 200
    sale_res = r_sale.get_json()
    assert sale_res["queued_job"] is not None
    assert sale_res["queued_job"]["quantity"] == 2

    # 5. Mídia & Geração de Legenda Instagram
    r_cap = client.post(
        "/api/media/generate-caption",
        json={"title": "Organizador Pro", "category": "Organizadores", "price_brl": 40.0},
        headers=headers,
    )
    assert r_cap.status_code == 200
    cap_data = r_cap.get_json()
    assert "Ita Arte 3D" in cap_data["caption"]
    assert "#ItaArte3D" in cap_data["hashtags"]

    # 6. Rubricas, Perfis de Fatiamento, Subcategorias, Postagem URL e Arquivamento
    r_rub = client.post("/api/rubrics", json={"name": "Cliente VIP", "color_hex": "#38bdf8"}, headers=headers)
    assert r_rub.status_code == 200
    rub_id = r_rub.get_json()["id"]
    assert client.get("/api/rubrics").status_code == 200
    assert client.patch(f"/api/rubrics/{rub_id}", json={"notes": "Urgente"}, headers=headers).status_code == 200
    assert client.delete(f"/api/rubrics/{rub_id}", headers=headers).status_code == 200

    r_sl = client.post(
        "/api/slicing-profiles",
        json={"name": "0.16 mm Teste", "layer_height_mm": 0.16, "notes": "3 paredes"},
        headers=headers,
    )
    assert r_sl.status_code == 200
    sl_id = r_sl.get_json()["id"]
    assert client.patch(f"/api/slicing-profiles/{sl_id}", json={"notes": "4 paredes"}, headers=headers).status_code == 200
    assert client.delete(f"/api/slicing-profiles/{sl_id}", headers=headers).status_code == 200

    r_sub = client.post(
        "/api/subcategories",
        json={"scope": "sales_catalog", "category": "Organizadores & Utilitários", "name": "Gavetas"},
        headers=headers,
    )
    assert r_sub.status_code == 200
    sub_id = r_sub.get_json()["id"]
    assert client.post("/api/subcategories/reclassify", headers=headers).status_code == 200
    assert client.delete(f"/api/subcategories/{sub_id}", headers=headers).status_code == 200

    r_med = client.post(
        "/api/media",
        data={"image_url": "https://example.com/foto.jpg", "title": "Foto Teste", "post_format": "Feed"},
        headers=headers,
    )
    assert r_med.status_code == 200
    med_id = r_med.get_json()["id"]
    assert client.patch(f"/api/media/{med_id}", json={"status": "Postado"}, headers=headers).status_code == 200
    assert client.delete(f"/api/media/{med_id}", headers=headers).status_code == 200

    # Arquivar e restaurar modelo
    r_arch = client.patch(f"/api/models/{model_id}", json={"status": "Arquivado"}, headers=headers)
    assert r_arch.status_code == 200 and r_arch.get_json()["status"] == "Arquivado"
    assert client.get("/api/models?exclude_archived=true").get_json()["total"] == 0
    r_rest = client.patch(f"/api/models/{model_id}", json={"status": "Na Fila"}, headers=headers)
    assert r_rest.status_code == 200 and r_rest.get_json()["status"] == "Na Fila"
    assert client.delete(f"/api/models/{model_id}", headers=headers).status_code == 200
