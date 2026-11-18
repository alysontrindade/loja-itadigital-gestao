from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def reais_para_centavos(valor: int | float | Decimal | str | None) -> int:
    """Converte um valor monetário em reais (str pt-BR/en-US, float, Decimal ou int) para centavos inteiros."""
    if valor is None or valor == "":
        return 0
    if isinstance(valor, bool):
        raise ValueError("Valor monetário booleano inválido")
    if isinstance(valor, int):
        return valor * 100
    if isinstance(valor, Decimal):
        return int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if isinstance(valor, float):
        return int((Decimal(str(valor)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace(" ", "").replace("\xa0", "")
    if not texto:
        return 0

    if "," in texto and "." in texto:
        # Formato pt-BR: 1.234,56 -> remove separador de milhar e troca vírgula
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        dec = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"Valor monetário inválido: {valor!r}") from exc

    return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def centavos_para_brl(centavos: int | None) -> str:
    """Formata um inteiro em centavos para string BRL (ex.: 123456 -> 'R$ 1.234,56')."""
    if centavos is None:
        centavos = 0
    negativo = centavos < 0
    absoluto = abs(int(centavos))
    reais = absoluto // 100
    resto = absoluto % 100
    reais_fmt = f"{reais:,}".replace(",", ".")
    prefixo = "-R$ " if negativo else "R$ "
    return f"{prefixo}{reais_fmt},{resto:02d}"
