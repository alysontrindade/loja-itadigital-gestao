import pytest

from app.config import build_settings
from app.db import get_session, init_db
from app.models import LogAuditoria, Produto, ProdutoNicho


def test_whatsapp_limpeza_e_link():
    from app.utils.whatsapp import formatar_whatsapp_link, limpar_telefone

    assert limpar_telefone("(38) 99999-1234") == "5538999991234"
    assert limpar_telefone("55 38 99999-1234") == "5538999991234"
    assert limpar_telefone("") == ""

    link = formatar_whatsapp_link("(38) 99999-1234", "Olá, tudo bem?")
    assert link.startswith("https://wa.me/5538999991234?text=")
    assert "Ol%C3%A1" in link
    assert formatar_whatsapp_link("") == ""


def test_nicho_crud_filtros_e_contagem(tmp_env):
    from app.services.nicho_service import (
        alternar_ativo_nicho,
        atualizar_nicho,
        criar_nicho,
        listar_nichos,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        iniciais = listar_nichos(db, ativo="1")
        assert len(iniciais) == 10

        novo = criar_nicho(db, nome="Sazonais & Natal", cor="#b91c1c", descricao="Datas festivas")
        assert novo.id is not None

        # Nome duplicado é rejeitado
        with pytest.raises(ValueError):
            criar_nicho(db, nome="sazonais & natal", cor="#000000")

        atualizar_nicho(db, novo.id, nome="Sazonais & Festas", cor="#991b1b", descricao="Atualizado")
        lista_com_novo = listar_nichos(db, busca="Sazonais")
        assert len(lista_com_novo) == 1
        assert lista_com_novo[0]["nome"] == "Sazonais & Festas"
        assert lista_com_novo[0]["cor"] == "#991b1b"

        # Vincula produto para testar contagem por nicho
        prod = Produto(sku="NAT-01", nome="Guirlanda", custo_centavos=1000, preco_centavos=2500)
        db.add(prod)
        db.flush()
        db.add(ProdutoNicho(produto_id=prod.id, nicho_id=novo.id))
        db.commit()

        contado = listar_nichos(db, busca="Sazonais")[0]
        assert contado["produtos_count"] == 1

        alternar_ativo_nicho(db, novo.id)
        assert len(listar_nichos(db, ativo="1", busca="Sazonais")) == 0
        assert len(listar_nichos(db, ativo="0", busca="Sazonais")) == 1
        assert len(listar_nichos(db, ativo="todos", busca="Sazonais")) == 1

    engine.dispose()


def test_fornecedor_crud_e_filtros(tmp_env):
    from app.services.fornecedor_service import (
        alternar_ativo_fornecedor,
        atualizar_fornecedor,
        criar_fornecedor,
        listar_fornecedores,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        f1 = criar_fornecedor(
            db,
            {
                "nome": "Marlon Distribuidora",
                "tipo": "atacado",
                "contato": "Marlon",
                "whatsapp": "(11) 98888-1111",
                "site": "marlondistribuidora.com.br",
                "cidade_uf": "São Paulo/SP",
                "prazo_dias": "7",
                "pedido_minimo": "300,00",
                "observacoes": "Variedades e presentes",
            },
        )
        assert f1.pedido_minimo_centavos == 30000
        assert f1.site == "https://marlondistribuidora.com.br"

        f2 = criar_fornecedor(
            db,
            {
                "nome": "Yiwu Direct Hub",
                "tipo": "china",
                "cidade_uf": "Yiwu/CN",
                "prazo_dias": "35",
                "pedido_minimo": "1500,00",
            },
        )
        assert f2.tipo == "china"

        assert len(listar_fornecedores(db, tipo="china")) == 1
        assert len(listar_fornecedores(db, cidade="Paulo")) == 1
        assert listar_fornecedores(db, busca="Marlon")[0]["whatsapp_link"].startswith(
            "https://wa.me/5511988881111"
        )

        atualizar_fornecedor(
            db,
            f1.id,
            {
                "nome": "Marlon Atacado SP",
                "tipo": "atacado",
                "cidade_uf": "São Paulo/SP",
                "prazo_dias": "5",
                "pedido_minimo": "250,00",
            },
        )
        assert listar_fornecedores(db, busca="Atacado SP")[0]["prazo_dias"] == 5

        alternar_ativo_fornecedor(db, f2.id)
        assert len(listar_fornecedores(db, ativo="1")) == 1
        assert len(listar_fornecedores(db, ativo="0")) == 1

    engine.dispose()


def test_cliente_crud_aniversario_e_whatsapp_opcional(tmp_env):
    from app.services.cliente_service import (
        atualizar_cliente,
        criar_cliente,
        listar_clientes,
    )

    settings = build_settings(tmp_env)
    engine = init_db(settings)

    with get_session(engine) as db:
        c1 = criar_cliente(
            db,
            {
                "nome": "Maria Souza",
                "whatsapp": "(38) 99123-4567",
                "cidade": "Itamarandiba",
                "aniversario": "15/11",
            },
        )
        c2 = criar_cliente(
            db,
            {
                "nome": "João Sem Zap",
                "whatsapp": "",
                "cidade": "Itamarandiba",
                "aniversario": "1990-05-20",
            },
        )
        c3 = criar_cliente(
            db,
            {
                "nome": "Ana Sem Zap",
                "whatsapp": "",
                "cidade": "Capelinha",
                "aniversario": "",
            },
        )
        assert c2.whatsapp is None
        assert c3.whatsapp is None

        # WhatsApp duplicado é bloqueado com erro claro
        with pytest.raises(ValueError):
            criar_cliente(db, {"nome": "Outro", "whatsapp": "38991234567"})

        assert len(listar_clientes(db, cidade="Itamarandiba")) == 2
        aniv_nov = listar_clientes(db, mes_aniversario="11")
        assert [c["nome"] for c in aniv_nov] == ["Maria Souza"]
        aniv_mai = listar_clientes(db, mes_aniversario="5")
        assert [c["nome"] for c in aniv_mai] == ["João Sem Zap"]

        atualizar_cliente(
            db,
            c1.id,
            {
                "nome": "Maria Clara Souza",
                "whatsapp": "(38) 99123-4567",
                "cidade": "Itamarandiba",
                "aniversario": "15/11",
            },
        )
        assert listar_clientes(db, busca="Clara")[0]["whatsapp_link"].startswith(
            "https://wa.me/5538991234567"
        )
        assert db.query(LogAuditoria).filter(LogAuditoria.entidade == "cliente").count() >= 4

    engine.dispose()
