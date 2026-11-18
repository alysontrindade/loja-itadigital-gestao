import pytest

from app.config import build_settings
from app.db import get_session, init_db
from app.models import LogAuditoria, MovimentoEstoque, Produto


def _criar_produtos_base(db):
    from app.services.produto_service import criar_produto

    p1 = criar_produto(
        db,
        {
            "sku": "EST-01",
            "nome": "Caneca Personalizada",
            "custo": "10,00",
            "preco": "30,00",
            "estoque_inicial": "10",
            "estoque_minimo": "3",
        },
        nicho_ids=[1],
    )
    p2 = criar_produto(
        db,
        {
            "sku": "EST-02",
            "nome": "Caixa Presente Cartonada",
            "custo": "5,00",
            "preco": "15,00",
            "estoque_inicial": "4",
            "estoque_minimo": "5",
        },
        nicho_ids=[1],
    )
    return p1, p2


def test_estoque_movimento_ajuste_perda_e_protecao_negativo(tmp_env):
    from app.services.estoque_service import (
        ajustar_estoque_manual,
        contar_estoque_critico,
        listar_movimentos,
        listar_posicao_estoque,
        registrar_movimento,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        p1, p2 = _criar_produtos_base(db)

        # Ajuste requer motivo obrigatório
        with pytest.raises(ValueError):
            ajustar_estoque_manual(db, p1.id, tipo="perda", quantidade=2, motivo="   ")

        # Saída acima do estoque disponível bloqueia
        with pytest.raises(ValueError):
            registrar_movimento(
                db,
                produto_id=p1.id,
                tipo="saida",
                quantidade=99,
                origem="venda",
                motivo="Teste acima do saldo",
            )

        # Perda de 2 unidades em p1 -> estoque passa de 10 para 8
        mov = ajustar_estoque_manual(
            db, p1.id, tipo="perda", quantidade=2, motivo="Caneca trincada no depósito"
        )
        assert mov.tipo == "perda"
        assert db.get(Produto, p1.id).estoque_atual == 8

        # Ajuste positivo de 4 unidades em p2 -> 4 -> 8 (sai de baixo para ok)
        ajustar_estoque_manual(
            db, p2.id, tipo="ajuste_positivo", quantidade=4, motivo="Contagem inventário"
        )
        assert db.get(Produto, p2.id).estoque_atual == 8
        assert contar_estoque_critico(db) == 0

        # Perda total de p2 -> zera estoque e conta como crítico
        ajustar_estoque_manual(
            db, p2.id, tipo="ajuste_negativo", quantidade=8, motivo="Avaria"
        )
        assert contar_estoque_critico(db) == 1

        movs = listar_movimentos(db, produto_id=p1.id)
        assert len(movs) == 2  # saldo_inicial + perda
        assert movs[0]["motivo"] == "Caneca trincada no depósito"

        pos_zerado = listar_posicao_estoque(db, status="zerado")
        assert [x["sku"] for x in pos_zerado] == ["EST-02"]
        assert db.query(LogAuditoria).filter(LogAuditoria.entidade == "estoque").count() >= 3

    engine.dispose()


def test_kit_crud_custo_margem_e_disponibilidade(tmp_env):
    from app.services.kit_service import (
        alternar_ativo_kit,
        atualizar_kit,
        criar_kit,
        listar_kits,
        obter_kit_detalhe,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        p1, p2 = _criar_produtos_base(db)

        # Kit usa 2 Canecas (estoque 10 -> monta até 5) + 1 Caixa (estoque 4 -> monta até 4)
        # Portanto disponibilidade máxima do kit = min(5, 4) = 4
        # Custo total = 2*10 + 1*5 = 25,00 (2500); soma avulsa = 2*30 + 15 = 75,00; preço kit = 60,00 (6000)
        kit = criar_kit(
            db,
            {
                "nome": "Kit Café Especial",
                "nivel": "premium",
                "nicho_id": "1",
                "preco": "60,00",
                "descricao": "2 canecas + caixa presente",
            },
            itens=[
                {"produto_id": p1.id, "quantidade": 2},
                {"produto_id": p2.id, "quantidade": 1},
            ],
        )
        assert kit.preco_centavos == 6000

        det = obter_kit_detalhe(db, kit.id)
        assert det["custo_total_centavos"] == 2500
        assert det["soma_avulsa_centavos"] == 7500
        assert det["economia_centavos"] == 1500
        assert det["estoque_disponivel"] == 4
        assert det["lucro_centavos"] == 3500

        # Atualizar para 1 caneca + 1 caixa com preço 40,00
        atualizar_kit(
            db,
            kit.id,
            {
                "nome": "Kit Café Essencial",
                "nivel": "basico",
                "nicho_id": "1",
                "preco": "40,00",
            },
            itens=[
                {"produto_id": p1.id, "quantidade": 1},
                {"produto_id": p2.id, "quantidade": 1},
            ],
        )
        lista = listar_kits(db, {"nivel": "basico"})
        assert len(lista) == 1
        assert lista[0]["nome"] == "Kit Café Essencial"
        assert lista[0]["custo_total_centavos"] == 1500

        alternar_ativo_kit(db, kit.id)
        assert len(listar_kits(db, {"ativo": "1"})) == 0
        assert len(listar_kits(db, {"ativo": "0"})) == 1

    engine.dispose()
