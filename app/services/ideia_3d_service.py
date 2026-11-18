from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import statistics
import struct
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import IdeiaImpressao
from app.models.base import utc_now_iso
from app.services.config_service import get_config

FILA_3D_DB_PATH = Path(r"H:\Meu Drive\ANTIGRAVITY\fila-impressao-3d\data\prints.db")
ORCA_SLICER_EXE = Path(r"C:\Program Files\OrcaSlicer\orca-slicer.exe")
BAMBU_STUDIO_EXE = Path(r"C:\Program Files\Bambu Studio\bambu-studio.exe")

REGRAS_DIMENSAO_COMERCIAL_MM: list[tuple[tuple[str, ...], float, bool]] = [
    (("chaveiro", "pingente", "tag", "brinde"), 55.0, True),
    (("placa", "quadro", "letreiro", "pix", "cracha", "topo", "topper"), 200.0, True),
    (("suporte", "controle", "headset", "celular", "fone", "alexa"), 135.0, False),
    (("vaso", "cachepo", "robert", "planta"), 140.0, False),
    (("busto", "estatueta", "estatua", "escultura", "personagem", "action", "boneco"), 180.0, False),
    (("organizador", "caixa", "porta", "bandeja", "gaveta"), 150.0, False),
]


def _slugify(texto: str) -> str:
    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", (texto or "").strip().lower()).strip("-")
    return (limpo or "ideia-3d")[:48]


def _http_get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _http_download(url: str, destino: Path, timeout: int = 20) -> bool:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        if len(data) < 84:
            return False
        destino.write_bytes(data)
        return True


def _inferir_tamanho_e_tipo(termo: str, dimensoes_encontradas_mm: list[float]) -> tuple[float, bool, str]:
    t = (termo or "").lower()
    eh_placa = False
    fallback_mm = 140.0
    for palavras, mm_ref, placa in REGRAS_DIMENSAO_COMERCIAL_MM:
        if any(p in t for p in palavras):
            fallback_mm = mm_ref
            eh_placa = placa
            break

    validas = [d for d in dimensoes_encontradas_mm if 20.0 <= d <= 450.0]
    if validas:
        alvo = float(round(statistics.median(validas), 1))
        origem = f"Mediana de anúncios nos marketplaces ({len(validas)} medida(s))"
        return alvo, eh_placa, origem
    return fallback_mm, eh_placa, "Padrão comercial da categoria (Dossiê Ita Arte 3D)"


def extrair_dimensoes_texto_mm(texto: str) -> list[float]:
    """Extrai medidas mencionadas em títulos/descrições (ex.: 15cm, 12x10cm, 180mm)."""
    if not texto:
        return []
    achados: list[float] = []
    # Ex.: 15x10cm, 15 x 10 cm, 200x150mm
    for m in re.finditer(
        r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)(?:\s*[xX×]\s*(\d+(?:[.,]\d+)?))?\s*(cm|mm)\b",
        texto,
        re.IGNORECASE,
    ):
        fator = 10.0 if m.group(4).lower() == "cm" else 1.0
        vals = [float(m.group(i).replace(",", ".")) * fator for i in (1, 2, 3) if m.group(i)]
        if vals:
            achados.append(max(vals))

    # Ex.: 18 cm, 150 mm
    for m in re.finditer(r"\b(\d+(?:[.,]\d+)?)\s*(cm|mm)\b", texto, re.IGNORECASE):
        fator = 10.0 if m.group(2).lower() == "cm" else 1.0
        val = float(m.group(1).replace(",", ".")) * fator
        achados.append(val)
    return achados


def buscar_precos_e_dimensoes_marketplaces(termo: str) -> dict[str, Any]:
    """Busca anúncios equivalentes no Mercado Livre e monta links para Shopee/Mercado Livre."""
    termo_limpo = (termo or "").strip()
    query_encoded = urllib.parse.quote_plus(f"{termo_limpo} impressao 3d")
    ml_slug = urllib.parse.quote(re.sub(r"\s+", "-", termo_limpo.lower()))

    url_ml_busca = f"https://lista.mercadolivre.com.br/{ml_slug}-3d"
    url_shopee_busca = f"https://shopee.com.br/search?keyword={query_encoded}"
    url_makerworld_busca = f"https://makerworld.com/pt/search/models?keyword={urllib.parse.quote_plus(termo_limpo)}"

    links: list[dict[str, Any]] = []
    precos_brl: list[float] = []
    dimensoes_mm: list[float] = []

    # 1. Tentativa de coleta no Mercado Livre
    try:
        html_ml = _http_get(url_ml_busca, timeout=10)
        # Busca pares titulo + link de produto + preço aproximado em blocos HTML
        blocos = re.findall(
            r'href="(https://produto\.mercadolivre\.com\.br/MLB-[^"]+)"[^>]*>([^<]{6,140})<',
            html_ml,
        )
        vistos: set[str] = set()
        for link_prod, titulo in blocos:
            url_base = link_prod.split("#")[0].split("?")[0]
            if url_base in vistos:
                continue
            vistos.add(url_base)
            titulo_limpo = re.sub(r"\s+", " ", titulo).strip()
            # Procura preço próximo à ocorrência do link no HTML
            idx = html_ml.find(link_prod)
            trecho = html_ml[idx : idx + 2200] if idx != -1 else ""
            m_preco = re.search(r'"price":\s*(\d+(?:\.\d+)?)|andes-money-amount__fraction"[^>]*>(\d[\d.]*)<', trecho)
            preco = 0.0
            if m_preco:
                raw_p = (m_preco.group(1) or m_preco.group(2) or "0").replace(".", "")
                try:
                    preco = float(m_preco.group(1)) if m_preco.group(1) else float(raw_p)
                except ValueError:
                    preco = 0.0
            dims = extrair_dimensoes_texto_mm(titulo_limpo)
            dimensoes_mm.extend(dims)
            if preco > 0:
                precos_brl.append(preco)
            links.append(
                {
                    "fonte": "Mercado Livre",
                    "titulo": titulo_limpo,
                    "url": url_base,
                    "preco_brl": round(preco, 2) if preco > 0 else None,
                    "dimensoes_mm": dims,
                }
            )
            if len(links) >= 5:
                break
    except Exception:
        pass

    # Sempre inclui os links diretos de pesquisa nos 3 portais para referência imediata
    links.append(
        {
            "fonte": "Mercado Livre (Busca)",
            "titulo": f"Pesquisar '{termo_limpo} 3D' no Mercado Livre",
            "url": url_ml_busca,
            "preco_brl": None,
            "dimensoes_mm": [],
        }
    )
    links.append(
        {
            "fonte": "Shopee (Busca)",
            "titulo": f"Pesquisar '{termo_limpo} 3D' na Shopee",
            "url": url_shopee_busca,
            "preco_brl": None,
            "dimensoes_mm": [],
        }
    )
    links.append(
        {
            "fonte": "MakerWorld (Busca)",
            "titulo": f"Modelos 3D '{termo_limpo}' no MakerWorld",
            "url": url_makerworld_busca,
            "preco_brl": None,
            "dimensoes_mm": [],
        }
    )

    alvo_mm, eh_placa, origem_dim = _inferir_tamanho_e_tipo(termo_limpo, dimensoes_mm)

    if precos_brl:
        p_min = round(min(precos_brl), 2)
        p_med = round(statistics.mean(precos_brl), 2)
        p_max = round(max(precos_brl), 2)
    else:
        p_min, p_med, p_max = 0.0, 0.0, 0.0

    return {
        "links": links,
        "preco_min_centavos": int(round(p_min * 100)),
        "preco_medio_centavos": int(round(p_med * 100)),
        "preco_max_centavos": int(round(p_max * 100)),
        "dimensao_alvo_mm": alvo_mm,
        "eh_placa_face_down": eh_placa,
        "origem_dimensao": origem_dim,
        "url_makerworld_busca": url_makerworld_busca,
    }


def _consultar_hub_local_3d(termo: str) -> dict[str, Any] | None:
    """Procura correspondência no banco local de 1.111+ modelos (fila-impressao-3d)."""
    if not FILA_3D_DB_PATH.exists():
        return None
    palavras = [p for p in re.findall(r"[a-zA-Z0-9À-ÿ]+", termo.lower()) if len(p) >= 3]
    if not palavras:
        return None
    try:
        with sqlite3.connect(FILA_3D_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, url, source, dimensions_mm, filament_grams FROM models LIMIT 2500;"
            ).fetchall()
            melhor = None
            melhor_score = 0
            for r in rows:
                titulo = str(r["title"] or "").lower()
                score = sum(1 for p in palavras if p in titulo)
                if score > melhor_score:
                    melhor_score = score
                    melhor = dict(r)
            if melhor and melhor_score >= 1:
                return melhor
    except Exception:
        return None
    return None


def _gerar_stl_base_parametrico(termo: str, pasta_destino: Path, alvo_mm: float, eh_placa: bool) -> Path:
    """Gera uma malha STL binária base limpa nas proporções da categoria para validação/fatiamento."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    slug = _slugify(termo)
    destino = pasta_destino / f"{slug}_base.stl"
    if eh_placa:
        lx, ly, lz = alvo_mm, max(35.0, alvo_mm * 0.45), 4.0
    elif "vaso" in termo.lower() or "cachepo" in termo.lower():
        lx, ly, lz = alvo_mm * 0.72, alvo_mm * 0.72, alvo_mm
    else:
        lx, ly, lz = alvo_mm, max(50.0, alvo_mm * 0.65), max(35.0, alvo_mm * 0.55)

    # Cria um prisma retangular estanque (12 triângulos) centrado em X/Y e apoiado em Z=0
    hx, hy = lx / 2.0, ly / 2.0
    v = [
        (-hx, -hy, 0.0), (hx, -hy, 0.0), (hx, hy, 0.0), (-hx, hy, 0.0),
        (-hx, -hy, lz), (hx, -hy, lz), (hx, hy, lz), (-hx, hy, lz),
    ]
    tris = [
        (0, 2, 1), (0, 3, 2),  # fundo
        (4, 5, 6), (4, 6, 7),  # topo
        (0, 1, 5), (0, 5, 4),  # frente
        (1, 2, 6), (1, 6, 5),  # direita
        (2, 3, 7), (2, 7, 6),  # tras
        (3, 0, 4), (3, 4, 7),  # esquerda
    ]
    _escrever_stl_binario(destino, [(v[a], v[b], v[c]) for a, b, c in tris])
    return destino


def _escrever_stl_binario(caminho: Path, triangulos: list[tuple[tuple[float, float, float], ...]]) -> None:
    header = b"Loja ItaDigital 3D AutoMesh".ljust(80, b" ")
    partes = [header, struct.pack("<I", len(triangulos))]
    for a, b, c in triangulos:
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        norm = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        partes.append(
            struct.pack(
                "<12fH",
                nx / norm, ny / norm, nz / norm,
                a[0], a[1], a[2],
                b[0], b[1], b[2],
                c[0], c[1], c[2],
                0,
            )
        )
    caminho.write_bytes(b"".join(partes))


def _ler_triangulos_stl(caminho: Path) -> list[tuple[tuple[float, float, float], ...]]:
    raw = caminho.read_bytes()
    if len(raw) >= 84:
        qtd = struct.unpack("<I", raw[80:84])[0]
        if 84 + qtd * 50 == len(raw):
            tris = []
            offset = 84
            for _ in range(qtd):
                vals = struct.unpack("<12fH", raw[offset : offset + 50])
                tris.append(((vals[3], vals[4], vals[5]), (vals[6], vals[7], vals[8]), (vals[9], vals[10], vals[11])))
                offset += 50
            return tris
    # Fallback STL ASCII
    txt = raw.decode("utf-8", errors="ignore")
    pts = [
        (float(x), float(y), float(z))
        for x, y, z in re.findall(r"vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)", txt)
    ]
    return [(pts[i], pts[i + 1], pts[i + 2]) for i in range(0, len(pts) - 2, 3)]


def _exportar_3mf(caminho_3mf: Path, triangulos: list[tuple[tuple[float, float, float], ...]]) -> None:
    vertices: list[tuple[float, float, float]] = []
    idx_map: dict[tuple[float, float, float], int] = {}
    faces: list[tuple[int, int, int]] = []
    for a, b, c in triangulos:
        f = []
        for p in (a, b, c):
            key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
            if key not in idx_map:
                idx_map[key] = len(vertices)
                vertices.append(key)
            f.append(idx_map[key])
        faces.append((f[0], f[1], f[2]))

    v_xml = "\n".join(f'          <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}" />' for x, y, z in vertices)
    t_xml = "\n".join(f'          <triangle v1="{i1}" v2="{i2}" v3="{i3}" />' for i1, i2, i3 in faces)
    model_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="pt-BR" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
{v_xml}
        </vertices>
        <triangles>
{t_xml}
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1" />
  </build>
</model>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />
</Types>'''

    rels = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2015/02/3dmodel" />
</Relationships>'''

    with zipfile.ZipFile(caminho_3mf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", model_xml)


def _metricas_malha(triangulos: list[tuple[tuple[float, float, float], ...]]) -> dict[str, float]:
    xs = [p[0] for tri in triangulos for p in tri]
    ys = [p[1] for tri in triangulos for p in tri]
    zs = [p[2] for tri in triangulos for p in tri]
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)

    vol = 0.0
    for a, b, c in triangulos:
        vol += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6.0
    return {
        "dx": dx,
        "dy": dy,
        "dz": dz,
        "max_dim": max(dx, dy, dz),
        "min_z": min(zs),
        "volume_cm3": abs(vol) / 1000.0,
    }


def _transformar_malha(
    triangulos: list[tuple[tuple[float, float, float], ...]],
    fator_escala: float,
    rotacionar_face_down_180: bool,
) -> list[tuple[tuple[float, float, float], ...]]:
    transformados: list[tuple[tuple[float, float, float], ...]] = []
    for tri in triangulos:
        novos = []
        for x, y, z in tri:
            sx, sy_, sz = x * fator_escala, y * fator_escala, z * fator_escala
            if rotacionar_face_down_180:
                sy_, sz = -sy_, -sz
            novos.append((sx, sy_, sz))
        transformados.append(tuple(novos))

    zs = [p[2] for tri in transformados for p in tri]
    min_z = min(zs) if zs else 0.0
    if abs(min_z) > 1e-4:
        transformados = [
            tuple((p[0], p[1], p[2] - min_z) for p in tri)
            for tri in transformados
        ]
    return transformados


def buscar_e_baixar_modelo_3d(
    termo: str,
    pasta_destino: Path,
    dimensao_alvo_mm: float,
    eh_placa_face_down: bool,
) -> dict[str, Any]:
    """Busca o modelo no MakerWorld/hub local, faz download quando possível ou gera STL base."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    slug = _slugify(termo)
    url_modelo = f"https://makerworld.com/pt/search/models?keyword={urllib.parse.quote_plus(termo)}"
    origem_modelo = "MakerWorld (Busca)"

    hub_item = _consultar_hub_local_3d(termo)
    if hub_item and hub_item.get("url"):
        url_modelo = str(hub_item["url"])
        origem_modelo = f"Hub Local ({hub_item.get('source', 'MakerWorld')})"
    else:
        try:
            html_mw = _http_get(url_modelo, timeout=10)
            m_mw = re.search(r'href="(/pt/models/\d+[^"]*|/en/models/\d+[^"]*)"', html_mw)
            if m_mw:
                url_modelo = "https://makerworld.com" + m_mw.group(1).split('"')[0]
                origem_modelo = "MakerWorld (Modelo encontrado)"
        except Exception:
            pass

    arquivo_stl = pasta_destino / f"{slug}_original.stl"
    baixado_externo = False
    # Tenta localizar link direto .stl/.3mf caso haja na página (alguns portais abertos expõem)
    if url_modelo.lower().endswith((".stl", ".3mf")):
        baixado_externo = _http_download(url_modelo, arquivo_stl)

    if not baixado_externo:
        arquivo_stl = _gerar_stl_base_parametrico(termo, pasta_destino, dimensao_alvo_mm, eh_placa_face_down)

    return {
        "modelo_url": url_modelo,
        "origem_modelo": origem_modelo,
        "arquivo_modelo": str(arquivo_stl),
        "baixado_direto": baixado_externo,
    }


def ajustar_escala_e_fatiar(
    arquivo_entrada: Path,
    dimensao_alvo_mm: float,
    eh_placa_face_down: bool,
    pasta_destino: Path,
) -> dict[str, Any]:
    """Verifica tamanho vs marketplace, reescala, aplica face-down 180° se placa e fatia no Orca/Bambu."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    tris = _ler_triangulos_stl(arquivo_entrada)
    if not tris:
        raise ValueError("Arquivo STL sem triângulos válidos.")

    m_orig = _metricas_malha(tris)
    max_orig = m_orig["max_dim"] or 1.0
    razao = dimensao_alvo_mm / max_orig
    fator = round(razao, 2) if abs(razao - 1.0) > 0.12 else 1.0

    tris_adj = _transformar_malha(tris, fator, eh_placa_face_down)
    m_adj = _metricas_malha(tris_adj)

    stem = re.sub(r"_original$|_base$", "", arquivo_entrada.stem)
    stl_ajustado = pasta_destino / f"{stem}_ajustado.stl"
    threemf_ajustado = pasta_destino / f"{stem}_ajustado.3mf"
    _escrever_stl_binario(stl_ajustado, tris_adj)
    _exportar_3mf(threemf_ajustado, tris_adj)

    # Fatiamento real via CLI (OrcaSlicer / Bambu Studio) quando disponível no sistema
    arquivo_fatiado = threemf_ajustado
    slicer_usado = "Estimativa física Ita Arte 3D"
    slicer_exe = ORCA_SLICER_EXE if ORCA_SLICER_EXE.exists() else (BAMBU_STUDIO_EXE if BAMBU_STUDIO_EXE.exists() else None)
    if slicer_exe is not None:
        candidato_fatiado = pasta_destino / f"{stem}_fatiado.3mf"
        try:
            proc = subprocess.run(
                [
                    str(slicer_exe),
                    "--slice",
                    "0",
                    "--outputdir",
                    str(pasta_destino),
                    "--export-3mf",
                    str(candidato_fatiado),
                    str(stl_ajustado),
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
            if candidato_fatiado.exists() and candidato_fatiado.stat().st_size > 1024:
                arquivo_fatiado = candidato_fatiado
                slicer_usado = slicer_exe.name
        except Exception:
            pass

    # Estimativa física realista de filamento:
    # Quando a malha é uma caixa paramétrica de referência (_base/_original), aplica fator de casca (~10% do bloco sólido);
    # para modelos STL reais detalhados, usa fator médio de preenchimento (~35%).
    is_base_box = len(tris) <= 24
    fator_preenchimento = 0.09 if is_base_box else 0.35
    vol_cm3 = max(4.0, m_adj["volume_cm3"])
    gramas = max(8, int(round(vol_cm3 * 1.24 * fator_preenchimento)))
    tempo_min = max(15, int(round(gramas * 2.2)))
    custo_centavos = gramas * 12  # ~R$ 120/kg -> R$ 0,12/g
    preco_sugerido_centavos = max(gramas * 40, custo_centavos * 3)  # Regra R$ 0,40/g ou 3x custo

    return {
        "dimensao_original_mm": f"{m_orig['dx']:.1f} x {m_orig['dy']:.1f} x {m_orig['dz']:.1f} mm",
        "dimensao_fatiada_mm": f"{m_adj['dx']:.1f} x {m_adj['dy']:.1f} x {m_adj['dz']:.1f} mm",
        "fator_escala": f"{fator:.2f}",
        "rotacionado_face_down": eh_placa_face_down,
        "arquivo_stl_ajustado": str(stl_ajustado),
        "arquivo_fatiado": str(arquivo_fatiado),
        "slicer_usado": slicer_usado,
        "gramas_estimadas": gramas,
        "tempo_estimado_min": tempo_min,
        "custo_estimado_centavos": custo_centavos,
        "preco_sugerido_centavos": preco_sugerido_centavos,
    }


def criar_ideia(
    session: Session,
    termo_ideia: str,
    observacoes: str = "",
    origem_sync: str = "local",
) -> IdeiaImpressao:
    termo = (termo_ideia or "").strip()
    if not termo:
        raise ValueError("Informe o nome ou ideia de impressão 3D.")
    ideia = IdeiaImpressao(
        termo_ideia=termo,
        observacoes=(observacoes or "").strip(),
        status="pendente",
        origem_sync=origem_sync,
    )
    session.add(ideia)
    session.flush()
    return ideia


def listar_ideias(session: Session, status: str | None = None) -> list[dict[str, Any]]:
    q = session.query(IdeiaImpressao)
    if status:
        q = q.filter(IdeiaImpressao.status == status)
    itens = q.order_by(IdeiaImpressao.id.desc()).all()
    resultado = []
    for it in itens:
        try:
            links = json.loads(it.links_json or "[]")
        except json.JSONDecodeError:
            links = []
        resultado.append(
            {
                "id": it.id,
                "termo_ideia": it.termo_ideia,
                "observacoes": it.observacoes,
                "status": it.status,
                "preco_min_centavos": it.preco_min_centavos,
                "preco_medio_centavos": it.preco_medio_centavos,
                "preco_max_centavos": it.preco_max_centavos,
                "preco_sugerido_centavos": it.preco_sugerido_centavos,
                "dimensao_mercado_mm": it.dimensao_mercado_mm,
                "dimensao_original_mm": it.dimensao_original_mm,
                "dimensao_fatiada_mm": it.dimensao_fatiada_mm,
                "fator_escala": it.fator_escala,
                "gramas_estimadas": it.gramas_estimadas,
                "tempo_estimado_min": it.tempo_estimado_min,
                "custo_estimado_centavos": it.custo_estimado_centavos,
                "modelo_url": it.modelo_url,
                "arquivo_modelo": it.arquivo_modelo,
                "arquivo_fatiado": it.arquivo_fatiado,
                "links": links,
                "resumo_analise": it.resumo_analise,
                "origem_sync": it.origem_sync,
                "criado_em": it.criado_em,
                "processado_em": it.processado_em,
            }
        )
    return resultado


def processar_ideia(
    session: Session,
    ideia_id: int,
    base_modelos_dir: Path | None = None,
) -> dict[str, Any]:
    """Executa o pipeline completo para uma ideia: Marketplaces -> Modelo 3D -> Escala -> Fatiamento."""
    ideia = session.get(IdeiaImpressao, ideia_id)
    if ideia is None:
        raise ValueError(f"Ideia {ideia_id} não encontrada.")

    ideia.status = "processando"
    session.flush()

    if base_modelos_dir is None:
        base_modelos_dir = Path(__file__).resolve().parents[2] / "modelos_3d"
    pasta_ideia = base_modelos_dir / f"{ideia.id:03d}_{_slugify(ideia.termo_ideia)}"

    mkt = buscar_precos_e_dimensoes_marketplaces(ideia.termo_ideia)
    dl = buscar_e_baixar_modelo_3d(
        ideia.termo_ideia,
        pasta_ideia,
        dimensao_alvo_mm=mkt["dimensao_alvo_mm"],
        eh_placa_face_down=mkt["eh_placa_face_down"],
    )
    fat = ajustar_escala_e_fatiar(
        Path(dl["arquivo_modelo"]),
        dimensao_alvo_mm=mkt["dimensao_alvo_mm"],
        eh_placa_face_down=mkt["eh_placa_face_down"],
        pasta_destino=pasta_ideia,
    )

    ideia.preco_min_centavos = mkt["preco_min_centavos"]
    ideia.preco_medio_centavos = mkt["preco_medio_centavos"]
    ideia.preco_max_centavos = mkt["preco_max_centavos"]
    ideia.preco_sugerido_centavos = fat["preco_sugerido_centavos"]
    ideia.dimensao_mercado_mm = f"{mkt['dimensao_alvo_mm']:.1f} mm ({mkt['origem_dimensao']})"
    ideia.dimensao_original_mm = fat["dimensao_original_mm"]
    ideia.dimensao_fatiada_mm = fat["dimensao_fatiada_mm"]
    ideia.fator_escala = fat["fator_escala"]
    ideia.gramas_estimadas = fat["gramas_estimadas"]
    ideia.tempo_estimado_min = fat["tempo_estimado_min"]
    ideia.custo_estimado_centavos = fat["custo_estimado_centavos"]
    ideia.modelo_url = dl["modelo_url"]
    ideia.arquivo_modelo = dl["arquivo_modelo"]
    ideia.arquivo_fatiado = fat["arquivo_fatiado"]
    ideia.links_json = json.dumps(mkt["links"], ensure_ascii=False)

    aviso_preco = (
        f"Preço médio ML/Shopee: R$ {ideia.preco_medio_centavos / 100:.2f}"
        if ideia.preco_medio_centavos > 0
        else "Preços diretos disponíveis nos links da pesquisa"
    )
    aviso_rot = " | Rotacionado 180° Face-Down (PEI)" if fat["rotacionado_face_down"] else ""
    ideia.resumo_analise = (
        f"Tamanho ajustado para padrão de mercado ({ideia.dimensao_fatiada_mm}, escala {ideia.fator_escala}x{aviso_rot}). "
        f"Estimativa: {ideia.gramas_estimadas}g / ~{ideia.tempo_estimado_min} min ({fat['slicer_usado']}). {aviso_preco}."
    )
    ideia.status = "concluida"
    ideia.processado_em = utc_now_iso()
    session.flush()

    return {
        "id": ideia.id,
        "termo_ideia": ideia.termo_ideia,
        "status": ideia.status,
        "arquivo_fatiado": ideia.arquivo_fatiado,
        "gramas": ideia.gramas_estimadas,
        "preco_sugerido_centavos": ideia.preco_sugerido_centavos,
    }


def processar_pendentes(
    session: Session,
    base_modelos_dir: Path | None = None,
) -> list[dict[str, Any]]:
    pendentes = (
        session.query(IdeiaImpressao)
        .filter(IdeiaImpressao.status == "pendente")
        .order_by(IdeiaImpressao.id.asc())
        .all()
    )
    resultados = []
    for p in pendentes:
        resultados.append(processar_ideia(session, p.id, base_modelos_dir=base_modelos_dir))
    return resultados


def sincronizar_com_google_sheets(session: Session, webapp_url: str | None = None) -> dict[str, Any]:
    """Sincroniza ideias bidirecionalmente com o Web App da Planilha Google."""
    url = (webapp_url or get_config(session, "google_sheets_webapp_url", "")).strip()
    if not url:
        return {"ok": False, "motivo": "URL do Web App do Google Sheets não configurada.", "importadas": 0, "enviadas": 0}

    importadas = 0
    enviadas = 0

    # 1. Puxar ideias cadastradas na nuvem (GitHub Pages / Planilha Google)
    try:
        sep = "&" if "?" in url else "?"
        resp_txt = _http_get(f"{url}{sep}action=list_ideias", timeout=15)
        payload = json.loads(resp_txt)
        remotas = payload.get("ideias", []) if isinstance(payload, dict) else []
        existentes = {i.termo_ideia.strip().lower(): i for i in session.query(IdeiaImpressao).all()}
        for rem in remotas:
            termo = str(rem.get("termo_ideia", "")).strip()
            if termo and termo.lower() not in existentes:
                nova = criar_ideia(
                    session,
                    termo_ideia=termo,
                    observacoes=str(rem.get("observacoes", "")),
                    origem_sync="google_sheets",
                )
                existentes[termo.lower()] = nova
                importadas += 1
    except Exception as exc:
        return {"ok": False, "motivo": f"Falha ao ler Planilha Google: {exc}", "importadas": 0, "enviadas": 0}

    # 2. Enviar estado local consolidado para a Planilha Google
    try:
        todas = listar_ideias(session)
        body = json.dumps({"action": "sync_ideias", "ideias": todas}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            _ = resp.read()
        enviadas = len(todas)
    except Exception as exc:
        return {"ok": False, "motivo": f"Leitura OK ({importadas}), mas falhou envio: {exc}", "importadas": importadas, "enviadas": 0}

    return {"ok": True, "importadas": importadas, "enviadas": enviadas}
