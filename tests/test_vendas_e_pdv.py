import pytest

from app.config import build_settings
from app.db import get_session, init_db
from app.models import LogAuditoria, MovimentoEstoque, Produto


def _preparar_catalogo(db):
    from app.services.cliente_service import criar_cliente
    from app.services.kit_service import criar_kit
    from app.services.produto_service import criar_produto

    p1 = criar_produto(
        db,
        {
            "sku": "PDV-01",
            "codigo_barras": "7891000100011",
            "nome": "Caneca Cerâmica",
            "custo": "10,00",
            "preco": "30,00",
            "estoque_inicial": "10",
            "estoque_minimo": "2",
        },
        nicho_ids=[1],
    )
    p2 = criar_produto(
        db,
        {
            "sku": "PDV-02",
            "codigo_barras": "7891000100028",
            "nome": "Urso Pelúcia Mini",
            "custo": "15,00",
            "preco": "40,00",
            "estoque_inicial": "3",
            "estoque_minimo": "1",
        },
        nicho_ids=[1],
    )
    kit = criar_kit(
        db,
        {"nome": "Kit Amor", "nivel": "medio", "nicho_id": "1", "preco": "65,00"},
        itens=[
            {"produto_id": p1.id, "quantidade": 1},
            {"produto_id": p2.id, "quantidade": 1},
        ],
    )
    cli = criar_cliente(db, {"nome": "Fernanda", "whatsapp": "(38) 99900-1122"})
    return p1, p2, kit, cli


def test_venda_produto_e_kit_congela_custos_e_cancela_devolvendo_estoque(tmp_env):
    from app.services.venda_service import (
        buscar_itens_pdv,
        cancelar_venda,
        listar_vendas,
        obter_venda_detalhe,
        registrar_venda,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        p1, p2, kit, cli = _preparar_catalogo(db)

        busca_cod = buscar_itens_pdv(db, busca="7891000100011")
        assert len(busca_cod["produtos"]) == 1
        assert busca_cod["produtos"][0]["sku"] == "PDV-01"

        # Vende 2 Canecas avulsas (2x 30 = 60) + 1 Kit Amor (65), desconto 5,00 -> total 120,00
        # Baixa esperada: Caneca 10 -> 10 - 2 - 1 = 7; Urso 3 -> 3 - 1 = 2
        venda = registrar_venda(
            db,
            dados={
                "cliente_id": cli.id,
                "canal": "loja",
                "forma_pagamento": "pix",
                "desconto": "5,00",
                "frete": "0,00",
                "observacoes": "Embrulhar para presente",
            },
            itens=[
                {"tipo": "produto", "id": p1.id, "quantidade": 2},
                {"tipo": "kit", "id": kit.id, "quantidade": 1},
            ],
        )
        assert venda.subtotal_centavos == 12500
        assert venda.desconto_centavos == 500
        assert venda.total_centavos == 12000
        assert db.get(Produto, p1.id).estoque_atual == 7
        assert db.get(Produto, p2.id).estoque_atual == 2

        # Alterar custo do produto depois não muda o custo congelado da venda
        p1_db = db.get(Produto, p1.id)
        p1_db.custo_centavos = 9999
        db.commit()

        det = obter_venda_detalhe(db, venda.id)
        custos = [i["custo_unit_centavos"] for i in det["itens"]]
        assert 1000 in custos  # caneca congelada em R$ 10,00
        assert 2500 in custos  # kit congelado em R$ 10 + R$ 15 = R$ 25,00

        # Cancelar venda devolve todo o estoque (produto + componentes do kit)
        cancelada = cancelar_venda(db, venda.id, motivo="Desistência do cliente")
        assert cancelada.status == "cancelada"
        assert db.get(Produto, p1.id).estoque_atual == 10
        assert db.get(Produto, p2.id).estoque_atual == 3

        with pytest.raises(ValueError):
            cancelar_venda(db, venda.id)

        estornos = (
            db.query(MovimentoEstoque)
            .filter(MovimentoEstoque.origem == "cancelamento_venda", MovimentoEstoque.referencia_id == venda.id)
            .all()
        )
        assert len(estornos) == 3
        assert len(listar_vendas(db, {"canal": "loja", "status": "cancelada"})) == 1
        assert db.query(LogAuditoria).filter(LogAuditoria.entidade == "venda").count() >= 2

    engine.dispose()


def test_venda_atomica_faz_rollback_se_segundo_item_nao_tiver_estoque(tmp_env):
    from app.services.venda_service import registrar_venda

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        p1, p2, kit, cli = _preparar_catalogo(db)

        # Item 1 tem estoque (10), Item 2 (Kit pede Urso) pede 5 mas Urso só tem 3!
        with pytest.raises(ValueError):
            registrar_venda(
                db,
                dados={"canal": "whatsapp", "forma_pagamento": "pix"},
                itens=[
                    {"tipo": "produto", "id": p1.id, "quantidade": 2},
                    {"tipo": "kit", "id": kit.id, "quantidade": 5},
                ],
            )

        # Rollback completo: p1 não pode ter sido baixado parcialmente
        assert db.get(Produto, p1.id).estoque_atual == 10
        assert db.get(Produto, p2.id).estoque_atual == 3

    engine.dispose()
