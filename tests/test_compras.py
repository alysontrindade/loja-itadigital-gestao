import pytest

from app.config import build_settings
from app.db import get_session, init_db
from app.models import LogAuditoria, MovimentoEstoque, Produto


def test_compra_criacao_rateio_recebimento_e_protecao_duplicado(tmp_env):
    from app.services.compra_service import (
        cancelar_compra,
        criar_compra,
        listar_compras,
        obter_compra_detalhe,
        receber_compra,
    )
    from app.services.fornecedor_service import criar_fornecedor
    from app.services.produto_service import criar_produto

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        forn = criar_fornecedor(db, {"nome": "Distribuidora Minas", "tipo": "atacado"})
        p1 = criar_produto(
            db,
            {"sku": "CMP-A", "nome": "Item A", "custo": "10,00", "preco": "25,00", "estoque_inicial": "0"},
        )
        p2 = criar_produto(
            db,
            {"sku": "CMP-B", "nome": "Item B", "custo": "20,00", "preco": "45,00", "estoque_inicial": "2"},
        )

        # Pedido aberto: 10x R$10 (R$100) + 5x R$20 (R$100) + frete R$30 + impostos R$10 = R$240
        # Rateio proporcional exato: R$20 para A (+R$2/un -> R$12) e R$20 para B (+R$4/un -> R$24)
        compra = criar_compra(
            db,
            fornecedor_id=forn.id,
            itens=[
                {"produto_id": p1.id, "quantidade": 10, "custo_unit": "10,00"},
                {"produto_id": p2.id, "quantidade": 5, "custo_unit": "20,00"},
            ],
            frete="30,00",
            impostos="10,00",
            outros_custos="0,00",
            observacoes="Pedido teste",
        )
        assert compra.status == "aberta"
        assert compra.total_centavos == 24000

        # Antes de receber, estoque permanece inalterado
        assert db.get(Produto, p1.id).estoque_atual == 0
        assert db.get(Produto, p2.id).estoque_atual == 2

        det = obter_compra_detalhe(db, compra.id)
        custos_finais = {i["produto_id"]: i["custo_final_unit_centavos"] for i in det["itens"]}
        assert custos_finais[p1.id] == 1200
        assert custos_finais[p2.id] == 2400

        # Receber compra -> entra no estoque + atualiza custo do produto
        recebida = receber_compra(db, compra.id, atualizar_custo_produto=True)
        assert recebida.status == "recebida"
        assert db.get(Produto, p1.id).estoque_atual == 10
        assert db.get(Produto, p2.id).estoque_atual == 7
        assert db.get(Produto, p1.id).custo_centavos == 1200
        assert db.get(Produto, p2.id).custo_centavos == 2400

        movs = (
            db.query(MovimentoEstoque)
            .filter(MovimentoEstoque.origem == "compra", MovimentoEstoque.referencia_id == compra.id)
            .all()
        )
        assert len(movs) == 2

        # Não pode receber duas vezes nem cancelar pedido já recebido
        with pytest.raises(ValueError):
            receber_compra(db, compra.id)
        with pytest.raises(ValueError):
            cancelar_compra(db, compra.id)

        # Pedido aberto pode ser cancelado sem tocar estoque
        c2 = criar_compra(
            db,
            fornecedor_id=forn.id,
            itens=[{"produto_id": p1.id, "quantidade": 3, "custo_unit": "12,00"}],
        )
        cancelar_compra(db, c2.id)
        assert db.get(Produto, p1.id).estoque_atual == 10
        assert len(listar_compras(db, {"status": "cancelada"})) == 1
        assert db.query(LogAuditoria).filter(LogAuditoria.entidade == "compra").count() >= 4

    engine.dispose()


def test_rateio_centavos_impares_nao_perde_centavo():
    from app.services.compra_service import calcular_rateio_custos

    # 3 itens iguais (total 3000) com frete R$ 1,00 (100 centavos) -> não pode perder centavo no rateio
    resultado = calcular_rateio_custos(
        [
            {"produto_id": 1, "quantidade": 1, "custo_unit_centavos": 1000},
            {"produto_id": 2, "quantidade": 1, "custo_unit_centavos": 1000},
            {"produto_id": 3, "quantidade": 1, "custo_unit_centavos": 1000},
        ],
        extras_centavos=100,
    )
    soma_final = sum(r["subtotal_com_rateio_centavos"] for r in resultado)
    assert soma_final == 3100
