import io
from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage

from app.config import build_settings
from app.db import get_session, init_db
from app.models import LogAuditoria, MovimentoEstoque, Produto


def _gerar_imagem_bytes(largura=800, altura=600, formato="PNG", cor=(200, 90, 40)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (largura, altura), cor)
    img.save(buf, format=formato)
    buf.seek(0)
    return buf.getvalue()


def _make_upload(conteudo: bytes, filename: str, content_type: str = "image/png") -> FileStorage:
    return FileStorage(
        stream=io.BytesIO(conteudo),
        filename=filename,
        content_type=content_type,
    )


def test_imagem_service_valida_redimensiona_gera_miniatura_e_remove(tmp_env):
    from app.services.imagem_service import remover_arquivos_imagem, salvar_imagem_produto

    settings = build_settings(tmp_env)

    # Arquivo falso disfarçado de JPG deve ser rejeitado
    falso = _make_upload(b"<svg><script>alert(1)</script></svg>", "../../evil.jpg", "image/jpeg")
    with pytest.raises(ValueError):
        salvar_imagem_produto(settings, falso)

    # Imagem grande é redimensionada com segurança + miniatura + nome UUID
    grande = _make_upload(_gerar_imagem_bytes(2400, 1600, "JPEG"), "foto da caneca!.jpg", "image/jpeg")
    arquivo = salvar_imagem_produto(settings, grande)

    assert "/" not in arquivo and "\\" not in arquivo
    assert arquivo.endswith(".webp")
    caminho_main = settings.fotos_dir / arquivo
    caminho_thumb = settings.fotos_dir / "thumbs" / arquivo
    assert caminho_main.exists()
    assert caminho_thumb.exists()

    with Image.open(caminho_main) as img_m:
        assert max(img_m.size) <= 1200
        assert img_m.size == (1200, 800)

    with Image.open(caminho_thumb) as img_t:
        assert max(img_t.size) <= 240

    remover_arquivos_imagem(settings, arquivo)
    assert not caminho_main.exists()
    assert not caminho_thumb.exists()


def test_produto_crud_margem_estoque_inicial_duplicidade_e_imagens(tmp_env):
    from app.services.fornecedor_service import criar_fornecedor
    from app.services.produto_service import (
        adicionar_imagens_produto,
        alternar_ativo_produto,
        atualizar_produto,
        calcular_margem,
        criar_produto,
        definir_imagem_principal,
        listar_produtos,
        remover_imagem_produto,
        verificar_duplicidades_produto,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    m = calcular_margem(1200, 3000)
    assert m["lucro_centavos"] == 1800
    assert m["margem_pct"] == 60.0

    with get_session(engine) as db:
        forn = criar_fornecedor(db, {"nome": "Fornecedor Teste", "tipo": "atacado"})

        p = criar_produto(
            db,
            {
                "sku": "CAN-001",
                "codigo_barras": "7891234567890",
                "nome": "Caneca Cerâmica Mágica",
                "unidade": "un",
                "custo": "12,50",
                "preco": "29,90",
                "estoque_inicial": "8",
                "estoque_minimo": "3",
                "fornecedor_id": forn.id,
            },
            nicho_ids=[1, 5],
        )
        assert p.custo_centavos == 1250
        assert p.preco_centavos == 2990
        assert p.estoque_atual == 8

        mov = db.query(MovimentoEstoque).filter(MovimentoEstoque.produto_id == p.id).first()
        assert mov is not None
        assert mov.quantidade == 8
        assert mov.origem == "saldo_inicial"

        # Atualizar produto não permite alterar estoque_atual arbitrariamente
        atualizar_produto(
            db,
            p.id,
            {
                "sku": "CAN-001",
                "codigo_barras": "7891234567890",
                "nome": "Caneca Cerâmica Térmica",
                "unidade": "un",
                "custo": "15,00",
                "preco": "35,00",
                "estoque_atual": 999,
                "estoque_minimo": "4",
                "fornecedor_id": forn.id,
            },
            nicho_ids=[1],
        )
        p_atual = db.get(Produto, p.id)
        assert p_atual.nome == "Caneca Cerâmica Térmica"
        assert p_atual.estoque_atual == 8  # preservado!

        # Aviso de duplicidade
        avisos = verificar_duplicidades_produto(
            db, nome="Caneca Cerâmica Térmica Nova", sku="CAN-001", codigo_barras="7891234567890"
        )
        assert len(avisos) >= 2

        # Upload, seleção de principal e remoção promovendo outra foto
        imgs = adicionar_imagens_produto(
            db,
            settings,
            p.id,
            [
                _make_upload(_gerar_imagem_bytes(600, 600, "PNG", (10, 20, 30)), "f1.png"),
                _make_upload(_gerar_imagem_bytes(600, 600, "PNG", (40, 50, 60)), "f2.png"),
            ],
        )
        assert len(imgs) == 2
        assert imgs[0].principal == 1
        assert imgs[1].principal == 0

        definir_imagem_principal(db, p.id, imgs[1].id)
        db.refresh(imgs[0])
        db.refresh(imgs[1])
        assert imgs[1].principal == 1
        assert imgs[0].principal == 0

        remover_imagem_produto(db, settings, p.id, imgs[1].id)
        restantes = listar_produtos(db, {"busca": "CAN-001"})[0]
        assert restantes["imagem_principal"] == imgs[0].arquivo

        alternar_ativo_produto(db, p.id)
        assert len(listar_produtos(db, {"ativo": "1"})) == 0
        assert len(listar_produtos(db, {"ativo": "0"})) == 1
        assert db.query(LogAuditoria).filter(LogAuditoria.entidade == "produto").count() >= 4

    engine.dispose()


def test_produto_filtros_multicriterio(tmp_env):
    from app.services.fornecedor_service import criar_fornecedor
    from app.services.produto_service import criar_produto, listar_produtos

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        f1 = criar_fornecedor(db, {"nome": "Atacado A", "tipo": "atacado"})
        f2 = criar_fornecedor(db, {"nome": "Atacado B", "tipo": "china"})

        # Produto 1: estoque ok, margem alta (60%), nicho 1, f1, R$ 50
        criar_produto(
            db,
            {
                "sku": "P-OK",
                "codigo_barras": "1111111111111",
                "nome": "Kit Presente Luxo",
                "custo": "20,00",
                "preco": "50,00",
                "estoque_inicial": "12",
                "estoque_minimo": "3",
                "fornecedor_id": f1.id,
            },
            nicho_ids=[1],
        )
        # Produto 2: estoque baixo (2 <= 5), margem baixa (20%), nicho 3, f2, R$ 25
        criar_produto(
            db,
            {
                "sku": "P-BAIXO",
                "codigo_barras": "2222222222222",
                "nome": "Caderno Study Pastel",
                "custo": "20,00",
                "preco": "25,00",
                "estoque_inicial": "2",
                "estoque_minimo": "5",
                "fornecedor_id": f2.id,
            },
            nicho_ids=[3],
        )
        # Produto 3: estoque zerado (0), margem média (50%), nicho 5, f1, R$ 100
        criar_produto(
            db,
            {
                "sku": "P-ZERO",
                "codigo_barras": "3333333333333",
                "nome": "Mousepad RGB Grande",
                "custo": "50,00",
                "preco": "100,00",
                "estoque_inicial": "0",
                "estoque_minimo": "2",
                "fornecedor_id": f1.id,
            },
            nicho_ids=[5],
        )

        assert [p["sku"] for p in listar_produtos(db, {"busca": "2222222222222"})] == ["P-BAIXO"]
        assert [p["sku"] for p in listar_produtos(db, {"nicho_id": "3"})] == ["P-BAIXO"]
        assert len(listar_produtos(db, {"fornecedor_id": str(f1.id)})) == 2
        assert [p["sku"] for p in listar_produtos(db, {"preco_min": "80,00"})] == ["P-ZERO"]
        assert [p["sku"] for p in listar_produtos(db, {"preco_max": "30,00"})] == ["P-BAIXO"]
        assert [p["sku"] for p in listar_produtos(db, {"margem_max": "25"})] == ["P-BAIXO"]
        assert [p["sku"] for p in listar_produtos(db, {"margem_min": "55"})] == ["P-OK"]
        assert [p["sku"] for p in listar_produtos(db, {"estoque_status": "ok"})] == ["P-OK"]
        assert [p["sku"] for p in listar_produtos(db, {"estoque_status": "baixo"})] == ["P-BAIXO"]
        assert [p["sku"] for p in listar_produtos(db, {"estoque_status": "zerado"})] == ["P-ZERO"]

    engine.dispose()
