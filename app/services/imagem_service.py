import io
from pathlib import Path
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from app.config import Settings

MAX_BYTES_IMAGEM = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_PIXELS_SAFE = 40_000_000
FORMATOS_PERMITIDOS = {"JPEG", "PNG", "WEBP"}
MAX_LADO_PRINCIPAL = 1200
MAX_LADO_MINIATURA = 240


def _thumbs_dir(settings: Settings) -> Path:
    thumbs = settings.fotos_dir / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    return thumbs


def salvar_imagem_produto(settings: Settings, arquivo: FileStorage) -> str:
    """Valida via Pillow, redimensiona e gera miniatura WebP segura com nome UUID."""
    if arquivo is None or not arquivo.filename:
        raise ValueError("Nenhum arquivo de imagem selecionado.")

    dados = arquivo.stream.read(MAX_BYTES_IMAGEM + 1)
    if not dados:
        raise ValueError("Arquivo de imagem vazio.")
    if len(dados) > MAX_BYTES_IMAGEM:
        raise ValueError("A imagem excede o limite máximo de 10 MB.")

    anterior_max = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS_SAFE
    try:
        try:
            with Image.open(io.BytesIO(dados)) as probe:
                formato = (probe.format or "").upper()
                if formato not in FORMATOS_PERMITIDOS:
                    raise ValueError(
                        "Formato de imagem não permitido. Envie apenas JPG, PNG ou WEBP."
                    )
                probe.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Arquivo inválido ou imagem corrompida.") from exc

        with Image.open(io.BytesIO(dados)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                convertida = img.convert("RGBA")
            else:
                convertida = img.convert("RGB")

            settings.fotos_dir.mkdir(parents=True, exist_ok=True)
            thumbs_dir = _thumbs_dir(settings)
            nome_seguro = f"{uuid.uuid4().hex}.webp"

            principal = convertida.copy()
            principal.thumbnail((MAX_LADO_PRINCIPAL, MAX_LADO_PRINCIPAL), Image.Resampling.LANCZOS)
            principal.save(settings.fotos_dir / nome_seguro, format="WEBP", quality=82, method=4)

            miniatura = convertida.copy()
            miniatura.thumbnail((MAX_LADO_MINIATURA, MAX_LADO_MINIATURA), Image.Resampling.LANCZOS)
            miniatura.save(thumbs_dir / nome_seguro, format="WEBP", quality=78, method=4)

            return nome_seguro
    finally:
        Image.MAX_IMAGE_PIXELS = anterior_max


def remover_arquivos_imagem(settings: Settings, nome_arquivo: str) -> None:
    """Remove foto principal e miniatura com proteção contra traversal."""
    if not nome_arquivo or Path(nome_arquivo).name != nome_arquivo:
        return
    base_fotos = settings.fotos_dir.resolve()
    base_thumbs = _thumbs_dir(settings).resolve()

    for pasta in (base_fotos, base_thumbs):
        alvo = (pasta / nome_arquivo).resolve()
        if alvo.parent == pasta and alvo.is_file():
            alvo.unlink()
