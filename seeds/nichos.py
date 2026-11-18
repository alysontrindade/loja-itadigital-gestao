from sqlalchemy.orm import Session

from app.models import Configuracao, Nicho

NICHOS_INICIAIS = [
    (
        "Presentes Personalizados & Kits Prontos",
        "#c2410c",
        "Kits prontos em 3 faixas de preço, canecas, chaveiros e embalagens afetivas.",
    ),
    (
        "Religioso & Devocional",
        "#7c5a2e",
        "Terços, escapulários, imagens sacras, bíblias e presentes devocionais.",
    ),
    (
        "Papelaria Fofa / Studygram & Concurseiros",
        "#be185d",
        "Cadernos inteligentes, marca-textos pastel, canetas fofas e kits de estudo.",
    ),
    (
        "Lembrancinhas de Festas & Eventos",
        "#b45309",
        "Mimos para aniversários, casamentos, batizados e datas comemorativas.",
    ),
    (
        "Gamer, Geek & Setup de Mesa",
        "#1d4ed8",
        "Mousepads RGB, suportes de headset, action figures e decoração de setup.",
    ),
    (
        "Pet (Mimos & Identificação)",
        "#0f766e",
        "Plaquetas gravadas, coleiras temáticas, brinquedos e comedouros.",
    ),
    (
        "Casa Prática, Cozinha & Achadinhos Virais",
        "#4d7c0f",
        "Organizadores, mini seladoras, garrafas térmicas e utilidades do dia a dia.",
    ),
    (
        "Beleza Express & Autocuidado",
        "#a21caf",
        "Skincare prático, nécessaires, escovas mágicas e acessórios de cuidado.",
    ),
    (
        "Brindes Corporativos & Comércio Local (B2B)",
        "#334155",
        "Squeezes, agendas, kits onboarding e presentes personalizados para empresas.",
    ),
    (
        "Agro / Profissões & Cultura Local",
        "#15803d",
        "Copos térmicos, canivetes, bonés, presentes temáticos de agro e profissões.",
    ),
]

CONFIG_PADRAO = {
    "nome_loja": "Loja Itamarandiba",
    "tema": "claro",
    "margem_alvo_pct": "45",
    "sessao_expira_minutos": "120",
    "backup_automatico": "1",
    "google_sheets_webapp_url": "",
}


def seed_nichos(session: Session) -> None:
    """Insere os 10 nichos aprovados de forma idempotente."""
    existentes = {row[0] for row in session.query(Nicho.nome).all()}
    for nome, cor, descricao in NICHOS_INICIAIS:
        if nome not in existentes:
            session.add(Nicho(nome=nome, cor=cor, descricao=descricao, ativo=1))


def seed_config_padrao(session: Session, session_timeout_minutes: int = 120) -> None:
    """Popula configurações iniciais sem sobrescrever preferências já salvas."""
    existentes = {row[0] for row in session.query(Configuracao.chave).all()}
    padroes = dict(CONFIG_PADRAO)
    padroes["sessao_expira_minutos"] = str(session_timeout_minutes)
    for chave, valor in padroes.items():
        if chave not in existentes:
            session.add(Configuracao(chave=chave, valor=valor))
