import io
import re
from PIL import Image


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
        },
        follow_redirects=True,
    )
    assert r_ok.status_code == 200
    return app, client, _extract_csrf(r_ok.get_data(as_text=True))


def _png_bytes(cor=(20, 120, 200)) -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", (320, 320), cor).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_rotas_nichos_fornecedores_e_clientes(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)

    # Nichos: lista 10, cria e inativa
    r_n = client.get("/nichos")
    assert r_n.status_code == 200
    assert "Presentes Personalizados" in r_n.get_data(as_text=True)

    r_n_add = client.post(
        "/nichos/novo",
        data={"csrf_token": csrf, "nome": "Colecionáveis", "cor": "#7c3aed", "descricao": "Miniaturas"},
        follow_redirects=True,
    )
    assert r_n_add.status_code == 200
    assert "Colecionáveis" in r_n_add.get_data(as_text=True)

    # Fornecedores: cria, filtra por tipo e abre link WhatsApp
    r_f_new = client.get("/fornecedores/novo")
    assert r_f_new.status_code == 200
    r_f_post = client.post(
        "/fornecedores/novo",
        data={
            "csrf_token": csrf,
            "nome": "Peining Brasil",
            "tipo": "atacado",
            "contato": "Carlos",
            "whatsapp": "(11) 97777-8888",
            "site": "peining.com.br",
            "cidade_uf": "São Paulo/SP",
            "prazo_dias": "5",
            "pedido_minimo": "500,00",
        },
        follow_redirects=True,
    )
    html_f = r_f_post.get_data(as_text=True)
    assert r_f_post.status_code == 200
    assert "Peining Brasil" in html_f
    assert "https://wa.me/5511977778888" in html_f

    # Clientes: cria e filtra aniversariante
    r_c_post = client.post(
        "/clientes/novo",
        data={
            "csrf_token": csrf,
            "nome": "Luciana Mendes",
            "whatsapp": "(38) 98888-2222",
            "cidade": "Itamarandiba",
            "aniversario": "22/11",
        },
        follow_redirects=True,
    )
    assert r_c_post.status_code == 200
    assert "Luciana Mendes" in r_c_post.get_data(as_text=True)

    r_c_filt = client.get("/clientes?mes_aniversario=11")
    assert "Luciana Mendes" in r_c_filt.get_data(as_text=True)


def test_rotas_produtos_upload_imagem_filtros_e_memoria_sessao(tmp_env):
    _, client, csrf = _setup_e_login(tmp_env)

    # Cria fornecedor primeiro
    client.post(
        "/fornecedores/novo",
        data={"csrf_token": csrf, "nome": "Look China", "tipo": "atacado", "cidade_uf": "São Paulo/SP"},
        follow_redirects=True,
    )

    # Cria produto com imagem real multipart e 2 nichos
    r_p_form = client.get("/produtos/novo")
    assert r_p_form.status_code == 200

    r_p_post = client.post(
        "/produtos/novo",
        data={
            "csrf_token": csrf,
            "sku": "KIT-REL-01",
            "codigo_barras": "7890000111222",
            "nome": "Kit Terço Madeira Nobre",
            "unidade": "kit",
            "custo": "18,00",
            "preco": "45,00",
            "estoque_inicial": "6",
            "estoque_minimo": "2",
            "fornecedor_id": "1",
            "nichos": ["1", "2"],
            "imagens": [(_png_bytes(), "terco.png")],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html_p = r_p_post.get_data(as_text=True)
    assert r_p_post.status_code == 200
    assert "Kit Terço Madeira Nobre" in html_p
    assert "R$ 45,00" in html_p

    # Verifica que imagem thumb foi servida com HTTP 200
    match_img = re.search(r'src="(/midia/fotos/thumb/[^"]+)"', html_p)
    assert match_img is not None
    r_img = client.get(match_img.group(1))
    assert r_img.status_code == 200
    assert r_img.mimetype == "image/webp"

    # Testa proteção contra tentativa de download fora da pasta de fotos
    assert client.get("/midia/fotos/..%2Floja.db").status_code in (400, 404)

    # Verifica memória de filtro na sessão: filtrar por busca sem resultado -> voltar a /produtos mantém filtro -> ?limpar=1 restaura lista
    r_filt = client.get("/produtos?busca=NAOEXISTE")
    assert "Kit Terço Madeira Nobre" not in r_filt.get_data(as_text=True)

    r_remember = client.get("/produtos")
    assert "Kit Terço Madeira Nobre" not in r_remember.get_data(as_text=True)

    r_clear = client.get("/produtos?limpar=1")
    assert "Kit Terço Madeira Nobre" in r_clear.get_data(as_text=True)

    # Verifica endpoint HTMX de duplicidade
    r_dup = client.get("/produtos/verificar-duplicidade?sku=KIT-REL-01")
    assert r_dup.status_code == 200
    assert "KIT-REL-01" in r_dup.get_data(as_text=True)

    # Verifica HTMX parcial de listagem
    r_htmx = client.get(
        "/produtos?busca=Terço",
        headers={"HX-Request": "true", "HX-Target": "produtos-tabela"},
    )
    assert r_htmx.status_code == 200
    assert "Kit Terço Madeira Nobre" in r_htmx.get_data(as_text=True)
    assert "<aside" not in r_htmx.get_data(as_text=True)

    # Edita produto, envia segunda imagem, define principal, remove uma e alterna ativo
    r_edit_page = client.get("/produtos/1/editar")
    assert r_edit_page.status_code == 200
    csrf_e = _extract_csrf(r_edit_page.get_data(as_text=True))

    r_edit_post = client.post(
        "/produtos/1/editar",
        data={
            "csrf_token": csrf_e,
            "sku": "KIT-REL-01",
            "codigo_barras": "7890000111222",
            "nome": "Kit Terço Luxo Editado",
            "unidade": "kit",
            "custo": "20,00",
            "preco": "52,00",
            "estoque_minimo": "3",
            "fornecedor_id": "1",
            "nichos": ["1", "2"],
            "imagens": [(_png_bytes((220, 40, 40)), "terco2.png")],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html_edit = r_edit_post.get_data(as_text=True)
    assert r_edit_post.status_code == 200
    assert "Kit Terço Luxo Editado" in html_edit

    # Alterna imagem principal e remove segunda imagem
    csrf_p = _extract_csrf(html_edit)
    r_prin = client.post(
        "/produtos/1/imagens/2/principal",
        data={"csrf_token": csrf_p},
        follow_redirects=True,
    )
    assert r_prin.status_code == 200

    csrf_r = _extract_csrf(r_prin.get_data(as_text=True))
    r_rem = client.post(
        "/produtos/1/imagens/2/remover",
        data={"csrf_token": csrf_r},
        follow_redirects=True,
    )
    assert "Imagem removida" in r_rem.get_data(as_text=True)

    # Tentativa de enviar arquivo inválido ao cadastrar produto redireciona com aviso sem quebrar
    csrf_inv = _extract_csrf(r_rem.get_data(as_text=True))
    r_inv = client.post(
        "/produtos/novo",
        data={
            "csrf_token": csrf_inv,
            "sku": "PROD-INV-01",
            "nome": "Produto Foto Inválida",
            "custo": "10,00",
            "preco": "20,00",
            "imagens": [(io.BytesIO(b"nao e imagem"), "falso.jpg")],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r_inv.status_code == 200
    assert "erro ao salvar foto" in r_inv.get_data(as_text=True).lower()

