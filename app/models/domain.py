from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now_iso


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    versao: Mapped[int] = mapped_column(Integer, primary_key=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    aplicado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)


class Nicho(Base):
    __tablename__ = "nicho"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cor: Mapped[str] = mapped_column(Text, nullable=False, default="#c2410c")
    ativo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)


class Fornecedor(Base):
    __tablename__ = "fornecedor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False, default="atacado")
    contato: Mapped[str] = mapped_column(Text, nullable=False, default="")
    whatsapp: Mapped[str] = mapped_column(Text, nullable=False, default="")
    site: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cidade_uf: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prazo_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pedido_minimo_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ativo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Produto(Base):
    __tablename__ = "produto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    codigo_barras: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="")
    unidade: Mapped[str] = mapped_column(Text, nullable=False, default="un")
    custo_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preco_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estoque_atual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estoque_minimo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fornecedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fornecedor.id", ondelete="SET NULL"), nullable=True
    )
    ativo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    atualizado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)

    fornecedor: Mapped["Fornecedor | None"] = relationship("Fornecedor")
    imagens: Mapped[list["ProdutoImagem"]] = relationship(
        "ProdutoImagem", back_populates="produto", cascade="all, delete-orphan"
    )


class ProdutoNicho(Base):
    __tablename__ = "produto_nicho"

    produto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("produto.id", ondelete="CASCADE"), primary_key=True
    )
    nicho_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nicho.id", ondelete="CASCADE"), primary_key=True
    )


class ProdutoImagem(Base):
    __tablename__ = "produto_imagem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("produto.id", ondelete="CASCADE"), nullable=False
    )
    arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    principal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    produto: Mapped["Produto"] = relationship("Produto", back_populates="imagens")


class Compra(Base):
    __tablename__ = "compra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fornecedor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fornecedor.id", ondelete="SET NULL"), nullable=True
    )
    data: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="aberta")
    frete_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impostos_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outros_custos_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    itens: Mapped[list["CompraItem"]] = relationship(
        "CompraItem", back_populates="compra", cascade="all, delete-orphan"
    )


class CompraItem(Base):
    __tablename__ = "compra_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compra_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compra.id", ondelete="CASCADE"), nullable=False
    )
    produto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("produto.id"), nullable=False
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    custo_unit_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    custo_final_unit_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    compra: Mapped["Compra"] = relationship("Compra", back_populates="itens")


class MovimentoEstoque(Base):
    __tablename__ = "movimento_estoque"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("produto.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(Text, nullable=False)
    referencia_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cidade: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aniversario: Mapped[str] = mapped_column(Text, nullable=False, default="")
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)


class Kit(Base):
    __tablename__ = "kit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nivel: Mapped[str] = mapped_column(Text, nullable=False, default="medio")
    nicho_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("nicho.id", ondelete="SET NULL"), nullable=True
    )
    preco_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    descricao: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ativo: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    itens: Mapped[list["KitItem"]] = relationship(
        "KitItem", back_populates="kit", cascade="all, delete-orphan"
    )


class KitItem(Base):
    __tablename__ = "kit_item"

    kit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kit.id", ondelete="CASCADE"), primary_key=True
    )
    produto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("produto.id"), primary_key=True
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    kit: Mapped["Kit"] = relationship("Kit", back_populates="itens")


class Venda(Base):
    __tablename__ = "venda"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cliente.id", ondelete="SET NULL"), nullable=True
    )
    data: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    canal: Mapped[str] = mapped_column(Text, nullable=False, default="loja")
    forma_pagamento: Mapped[str] = mapped_column(Text, nullable=False, default="pix")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="concluida")
    subtotal_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    desconto_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frete_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    itens: Mapped[list["VendaItem"]] = relationship(
        "VendaItem", back_populates="venda", cascade="all, delete-orphan"
    )


class VendaItem(Base):
    __tablename__ = "venda_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venda_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venda.id", ondelete="CASCADE"), nullable=False
    )
    produto_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("produto.id"), nullable=True
    )
    kit_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("kit.id"), nullable=True
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unit_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    custo_unit_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    desconto_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    venda: Mapped["Venda"] = relationship("Venda", back_populates="itens")


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    login: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bloqueado_ate: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultimo_acesso: Mapped[str | None] = mapped_column(Text, nullable=True)


class Configuracao(Base):
    __tablename__ = "configuracao"

    chave: Mapped[str] = mapped_column(Text, primary_key=True)
    valor: Mapped[str] = mapped_column(Text, nullable=False)


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True
    )
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    entidade: Mapped[str] = mapped_column(Text, nullable=False)
    entidade_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    detalhes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)


class IdeiaImpressao(Base):
    __tablename__ = "ideia_impressao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    termo_ideia: Mapped[str] = mapped_column(Text, nullable=False)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pendente")
    preco_min_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preco_medio_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preco_max_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preco_sugerido_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dimensao_mercado_mm: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dimensao_original_mm: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dimensao_fatiada_mm: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fator_escala: Mapped[str] = mapped_column(Text, nullable=False, default="1.00")
    gramas_estimadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tempo_estimado_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custo_estimado_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modelo_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    arquivo_modelo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    arquivo_fatiado: Mapped[str] = mapped_column(Text, nullable=False, default="")
    links_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    resumo_analise: Mapped[str] = mapped_column(Text, nullable=False, default="")
    origem_sync: Mapped[str] = mapped_column(Text, nullable=False, default="local")
    criado_em: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
    processado_em: Mapped[str | None] = mapped_column(Text, nullable=True)
