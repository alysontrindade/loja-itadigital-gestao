import json
from pathlib import Path
import re
import zipfile

from app import create_app
from app.db import get_session
from app.services import ideia_3d_service


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
    return app, client, _extract_csrf(r_ok.get_data(as_text=True))


def test_extrair_dimensoes_texto_mm():
    assert ideia_3d_service.extrair_dimensoes_texto_mm("Suporte Controle PS5 15x10cm") == [150.0, 150.0] or 150.0 in ideia_3d_service.extrair_dimensoes_texto_mm("Suporte Controle PS5 15x10cm")
    assert 180.0 in ideia_3d_service.extrair_dimensoes_texto_mm("Estatueta Decorativa 18 cm PLA")
    assert 200.0 in ideia_3d_service.extrair_dimensoes_texto_mm("Placa Pix 200mm Balcao")


def test_escala_comercial_facedown_e_exportacao_3mf(tmp_path: Path):
    # Gera STL pequeno (70 mm) e pede reescalonamento para padrão de placa (200 mm) com face-down 180°
    stl_orig = ideia_3d_service._gerar_stl_base_parametrico("placa pix teste", tmp_path, 70.0, True)
    res = ideia_3d_service.ajustar_escala_e_fatiar(
        stl_orig,
        dimensao_alvo_mm=200.0,
        eh_placa_face_down=True,
        pasta_destino=tmp_path,
    )
    assert float(res["fator_escala"]) > 2.5
    assert res["rotacionado_face_down"] is True
    assert res["gramas_estimadas"] >= 6
    assert res["preco_sugerido_centavos"] > 0

    path_3mf = Path(res["arquivo_stl_ajustado"]).with_suffix(".3mf")
    assert path_3mf.exists()
    with zipfile.ZipFile(path_3mf, "r") as zf:
        assert "3D/3dmodel.model" in zf.namelist()
        xml_txt = zf.read("3D/3dmodel.model").decode("utf-8")
        assert 'z="0.0000"' in xml_txt


def test_rotas_ideias_3d_e_sincronizacao(tmp_env, tmp_path, monkeypatch):
    app, client, csrf = _setup_e_login(tmp_env)

    # Evitar chamadas externas reais durante pytest
    monkeypatch.setattr(
        ideia_3d_service,
        "buscar_precos_e_dimensoes_marketplaces",
        lambda termo: {
            "links": [
                {"fonte": "Mercado Livre", "titulo": f"{termo} 15cm", "url": "https://produto.mercadolivre.com.br/MLB-123", "preco_brl": 49.90, "dimensoes_mm": [150.0]},
                {"fonte": "Shopee (Busca)", "titulo": f"Shopee {termo}", "url": "https://shopee.com.br/search?keyword=teste", "preco_brl": None, "dimensoes_mm": []},
            ],
            "preco_min_centavos": 4990,
            "preco_medio_centavos": 4990,
            "preco_max_centavos": 4990,
            "dimensao_alvo_mm": 150.0,
            "eh_placa_face_down": False,
            "origem_dimensao": "Mock ML",
            "url_makerworld_busca": "https://makerworld.com/pt/search/models?keyword=teste",
        },
    )
    monkeypatch.setattr(
        ideia_3d_service,
        "buscar_e_baixar_modelo_3d",
        lambda termo, pasta, dimensao_alvo_mm, eh_placa_face_down: {
            "modelo_url": "https://makerworld.com/pt/models/99999",
            "origem_modelo": "MakerWorld Mock",
            "arquivo_modelo": str(ideia_3d_service._gerar_stl_base_parametrico(termo, pasta, 75.0, False)),
            "baixado_direto": False,
        },
    )

    r_get = client.get("/ideias-3d")
    assert r_get.status_code == 200
    assert "Nova Ideia de Impressão" in r_get.get_data(as_text=True)

    r_post = client.post(
        "/ideias-3d/nova",
        data={"csrf_token": csrf, "termo_ideia": "suporte controle ps5", "observacoes": "Cor preta"},
        follow_redirects=True,
    )
    assert r_post.status_code == 200
    html = r_post.get_data(as_text=True)
    assert "suporte controle ps5" in html
    assert "PENDENTE" in html

    # Processa a ideia criada
    r_proc = client.post("/ideias-3d/1/processar", data={"csrf_token": csrf}, follow_redirects=True)
    assert r_proc.status_code == 200
    html_proc = r_proc.get_data(as_text=True)
    assert "CONCLUIDA" in html_proc
    assert "R$ 49,90" in html_proc
    assert "makerworld.com/pt/models/99999" in html_proc

    # Testa sincronizacao bidirecional com Google Sheets mockada
    monkeypatch.setattr(
        ideia_3d_service,
        "_http_get",
        lambda url, timeout=15: json.dumps({"ok": True, "ideias": [{"termo_ideia": "vaso robert plant", "observacoes": "branco"}]}),
    )

    class _DummyResp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b'{"ok": true}'

    monkeypatch.setattr(ideia_3d_service.urllib.request, "urlopen", lambda req, timeout=15: _DummyResp())

    with get_session(app.extensions["engine"]) as db:
        sync_res = ideia_3d_service.sincronizar_com_google_sheets(db, webapp_url="https://script.google.com/macros/s/demo/exec")
        db.commit()
        assert sync_res["ok"] is True
        assert sync_res["importadas"] == 1
        assert sync_res["enviadas"] == 2
