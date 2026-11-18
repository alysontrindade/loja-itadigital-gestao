import re
from urllib.parse import quote


def limpar_telefone(valor: str | None) -> str:
    """Extrai dígitos do telefone e normaliza DDD brasileiro com DDI 55 quando aplicável."""
    if not valor:
        return ""
    digitos = re.sub(r"\D+", "", str(valor))
    if not digitos:
        return ""
    if len(digitos) in (10, 11) and not digitos.startswith("55"):
        digitos = f"55{digitos}"
    return digitos


def formatar_telefone_exibicao(valor: str | None) -> str:
    """Formata telefone brasileiro para exibição legível."""
    digitos = limpar_telefone(valor)
    if not digitos:
        return ""
    local = digitos[2:] if digitos.startswith("55") and len(digitos) in (12, 13) else digitos
    if len(local) == 11:
        return f"({local[:2]}) {local[2:7]}-{local[7:]}"
    if len(local) == 10:
        return f"({local[:2]}) {local[2:6]}-{local[6:]}"
    return digitos


def formatar_whatsapp_link(telefone: str | None, mensagem: str = "") -> str:
    """Gera link pronto https://wa.me/<numero> com mensagem opcional codificada."""
    numero = limpar_telefone(telefone)
    if not numero:
        return ""
    base = f"https://wa.me/{numero}"
    texto = (mensagem or "").strip()
    if texto:
        return f"{base}?text={quote(texto)}"
    return base
