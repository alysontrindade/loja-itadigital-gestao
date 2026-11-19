from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
import json
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import urllib.error
import urllib.request


def _urllib_get(url: str, timeout: float = 8.0, headers: dict[str, str] | None = None) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            body = resp.read().decode("utf-8", errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return int(status), body, resp_headers
    except urllib.error.HTTPError as err:
        resp_headers = {k.lower(): v for k, v in (err.headers.items() if err.headers else [])}
        return int(err.code), "", resp_headers
    except Exception:
        return 0, "", {}

MULTICOLOR_LABEL = "Multicolor / Todas as Cores"

STATUSES = ["Na Fila", "Imprimindo", "Impresso", "Arquivado"]

CATEGORIES = [
    "Chaveiros & Personalizados",
    "Organização & Casa",
    "Ferramentas & Oficina",
    "Decoração & Arte",
    "Miniaturas & Colecionáveis",
    "Geek & Games",
    "Suportes & Eletrônicos",
    "Acessórios 3D",
    "Brinquedos & Articulados",
    "Cozinha & Utilidades",
    "Outros",
]

DEFAULT_MODEL_SUBCATEGORIES: dict[str, list[str]] = {
    "Chaveiros & Personalizados": [
        "Chaveiros 3D",
        "Times & Futebol",
        "Nomes & Brindes",
        "Placas, Pix & Topos",
        "Brincos & Acessórios",
        "Personalizados Gerais",
    ],
    "Organização & Casa": [
        "Gridfinity",
        "Cabos & Fios",
        "Caixas & Nichos",
        "Bandejas & Relógios",
        "Porta-Objetos & Ganchos",
        "Utilidades Domésticas",
    ],
    "Decoração & Arte": [
        "Esculturas & Bustos",
        "Religioso",
        "Vasos & Cachepôs",
        "Placas & Quadros",
        "Pássaros & Natureza",
        "Decoração Geral",
    ],
    "Suportes & Eletrônicos": [
        "Celular & Tablet",
        "Setup & Mesa",
        "Controles & Consoles",
        "Expositores & Colecionáveis",
        "Casa, Banheiro & Parede",
        "Suportes Gerais",
    ],
    "Ferramentas & Oficina": [
        "Gabaritos & Medição",
        "Parede & Skadis",
        "Mosquetões & Clipes",
        "Pintura & Modelismo",
        "Parafusos & Caixas",
        "Oficina Geral",
    ],
    "Brinquedos & Articulados": [
        "Dragões & Criaturas",
        "Fidget & Articulados",
        "Quebra-Cabeças & Educativos",
        "Brinquedos & Jogos",
    ],
    "Acessórios 3D": [
        "Calibração & Testes",
        "Bambu Lab, Elegoo & Upgrades",
        "Raspadores & Limpeza",
        "Chaveiros & Pingentes 3D",
        "Peças & Acessórios Gerais",
    ],
    "Geek & Games": [
        "Funko Pop & Colecionáveis",
        "Animes, Heróis & Filmes",
        "Esportes & Clubes",
        "Geek Geral",
    ],
    "Cozinha & Utilidades": [
        "Canecas, Abridores & Bar",
        "Preparo & Cozinha",
        "Irrigação & Casa",
        "Utilidades de Cozinha",
    ],
    "Miniaturas & Colecionáveis": [
        "Religioso & Esculturas",
        "Expositores & Diecast",
        "Colecionáveis Gerais",
    ],
    "Outros": [
        "Jardim, Horta & Hidropônico",
        "Pets & Identificação",
        "Calçados & Moda",
        "Cozinha, Alimentos & Banheiro",
        "Brinquedos, Jogos & Esportes",
        "Personagens, Anime & Geek",
        "Esculturas, Religioso & Profissões",
        "Automotivo, PVC & Ferragens",
        "Casa, Cofres & Prateleiras",
        "Sazonal (Natal & Páscoa)",
        "Pintura, Papelaria & Testes 3D",
        "Modelos Gerais",
    ],
}

SIZE_TIERS = [
    {"name": "Pequeno", "label": "≤ 80 mm"},
    {"name": "Médio", "label": "81–160 mm"},
    {"name": "Grande", "label": "161–240 mm"},
    {"name": "Extra Grande", "label": "> 240 mm"},
]

FILAMENT_TYPES = [
    "PLA",
    "PLA+",
    "PLA Matte",
    "PLA Silk",
    "PETG",
    "TPU",
    "ABS/ASA",
    "PLA-CF",
]

COLOR_PALETTE = [
    {"name": MULTICOLOR_LABEL, "type": "multicolor", "hex": "multicolor"},
    {"name": "Preto", "type": "solid", "hex": "#171717"},
    {"name": "Branco", "type": "solid", "hex": "#f5f5f4"},
    {"name": "Cinza / Grafite", "type": "solid", "hex": "#6b7280"},
    {"name": "Prata / Metálico", "type": "solid", "hex": "#9ca3af"},
    {"name": "Azul", "type": "solid", "hex": "#2563eb"},
    {"name": "Vermelho", "type": "solid", "hex": "#dc2626"},
    {"name": "Verde", "type": "solid", "hex": "#16a34a"},
    {"name": "Amarelo / Dourado", "type": "solid", "hex": "#eab308"},
    {"name": "Laranja", "type": "solid", "hex": "#ea580c"},
    {"name": "Roxo", "type": "solid", "hex": "#7e22ce"},
    {"name": "Rosa", "type": "solid", "hex": "#db2777"},
    {"name": "Marrom / Madeira", "type": "solid", "hex": "#854d0e"},
    {"name": "Transparente", "type": "solid", "hex": "#bae6fd"},
]

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref"}
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_DIMS_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*mm\b",
    re.IGNORECASE,
)
_KG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\b", re.IGNORECASE)
_GRAMS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*g(?:ramas|rams)?\b", re.IGNORECASE)
_TIME_HM_RE = re.compile(r"(\d+)\s*h(?:rs?|oras?)?\s*(?:(\d+)\s*m(?:in)?)?", re.IGNORECASE)

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Chaveiros & Personalizados", ("keychain", "chaveiro", "keyring", "tag", "nameplate", "placa", "pix", "qrcode", "qr code", "badge", "cracha", "pingente", "magnet", "ima", "personalizado")),
    ("Acessórios 3D", ("bambu", "a1", "p1s", "x1c", "ams", "poop", "spool", "filament", "filamento", "nozzle", "bico", "extruder", "ptfe")),
    ("Brinquedos & Articulados", ("articulated", "articulado", "flexi", "dragon", "dragão", "axolotl", "fidget", "toy", "brinquedo", "spinner", "octopus", "dino")),
    ("Ferramentas & Oficina", ("wrench", "chave", "tool", "ferramenta", "bit", "screwdriver", "caliper", "paquimetro", "clamp", "oficina", "bracket", "suporte parede", "screw", "parafuso")),
    ("Organização & Casa", ("gridfinity", "organizer", "organizador", "skadis", "pegboard", "box", "caixa", "tray", "bandeja", "drawer", "gaveta", "bin", "storage")),
    ("Suportes & Eletrônicos", ("controller", "controle", "ps5", "xbox", "switch", "headphone", "headset", "phone", "celular", "tablet", "laptop", "stand", "dock", "raspberry", "esp32", "cable", "cabo")),
    ("Cozinha & Utilidades", ("kitchen", "cozinha", "coaster", "porta copo", "funnel", "funil", "clip", "bag clip", "caneca", "sponge", "esponja", "coffee", "café")),
    ("Geek & Games", ("pokemon", "mario", "zelda", "minecraft", "naruto", "anime", "star wars", "batman", "marvel", "rpg", "dice", "dado", "cosplay", "mask")),
    ("Miniaturas & Colecionáveis", ("miniature", "miniatura", "figurine", "statue", "estatueta", "bust", "busto", "chibi", "diorama", "warhammer", "dnd")),
    ("Decoração & Arte", ("vase", "vaso", "lamp", "luminaria", "abajur", "planter", "cachepot", "decor", "decoracao", "wall art", "quadro", "sculpture", "escultura", "hueforge", "lithophane")),
]


class _MetaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self._in_title = False
        self._title_parts: list[str] = []
        self._in_next_data = False
        self._next_data_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        t = tag.lower()
        if t == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if key and attr_map.get("content"):
                self.meta[key] = attr_map["content"]
        elif t == "title":
            self._in_title = True
        elif t == "script" and attr_map.get("id") == "__NEXT_DATA__":
            self._in_next_data = True

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title":
            self._in_title = False
        elif t == "script" and self._in_next_data:
            self._in_next_data = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_next_data:
            self._next_data_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self._title_parts).strip()

    @property
    def next_data(self) -> dict[str, Any] | None:
        raw = "".join(self._next_data_parts).strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None


def _clean_title_suffix(title: str) -> str:
    return re.sub(r"\s*[-|]\s*(MakerWorld|Printables|Thingiverse|Cults3D|Thangs).*$", "", title, flags=re.IGNORECASE).strip()


def normalize_url(url: str) -> str:
    cleaned = url.strip().rstrip(".,;:!?)]}>\"'")
    parsed = urlparse(cleaned)
    query_pairs = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", urlencode(query_pairs), ""))


def extract_urls(raw_text: str) -> list[str]:
    if not raw_text:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for match in _URL_RE.findall(raw_text):
        norm = normalize_url(match)
        parsed = urlparse(norm)
        if parsed.scheme in {"http", "https"} and parsed.netloc and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def parse_url_info(url: str) -> dict[str, str]:
    norm = normalize_url(url)
    parsed = urlparse(norm)
    host = parsed.netloc.lower()

    if "makerworld.com" in host:
        source = "MakerWorld"
    elif "printables.com" in host:
        source = "Printables"
    elif "thingiverse.com" in host:
        source = "Thingiverse"
    elif "cults3d.com" in host:
        source = "Cults3D"
    elif "thangs.com" in host:
        source = "Thangs"
    else:
        source = "Outro"

    segments = [s for s in parsed.path.split("/") if s]
    last_seg = segments[-1] if segments else ""
    id_match = re.search(r"(\d{3,})", last_seg) or re.search(r"(\d{3,})", parsed.path)
    external_id = id_match.group(1) if id_match else ""

    slug = re.sub(r"^\d+[-_]?", "", last_seg)
    slug_words = re.sub(r"[-_]+", " ", slug).strip()
    title = slug_words.title() if slug_words else f"Modelo {source} {external_id}".strip()

    return {
        "url": norm,
        "source": source,
        "external_id": external_id,
        "title": title,
    }


def _extract_specs_from_text(text: str) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    if not text:
        return specs

    dim_match = _DIMS_RE.search(text)
    if dim_match:
        vals = [float(g.replace(",", ".")) for g in dim_match.groups()]
        specs["dimensions_mm"] = f"{dim_match.group(1)} x {dim_match.group(2)} x {dim_match.group(3)} mm"
        specs["max_dimension_mm"] = max(vals)

    kg_match = _KG_RE.search(text)
    if kg_match:
        specs["filament_grams"] = round(float(kg_match.group(1).replace(",", ".")) * 1000.0, 1)
    else:
        g_match = _GRAMS_RE.search(text)
        if g_match:
            specs["filament_grams"] = round(float(g_match.group(1).replace(",", ".")), 1)

    time_match = _TIME_HM_RE.search(text)
    if time_match:
        hours = int(time_match.group(1))
        mins = int(time_match.group(2) or 0)
        if hours > 0 or mins > 0:
            specs["print_time_min"] = hours * 60 + mins

    return specs


def parse_html_metadata(html: str, url: str) -> dict[str, Any]:
    parser = _MetaHTMLParser()
    parser.feed(html)

    out: dict[str, Any] = {}
    design = ((parser.next_data or {}).get("props") or {}).get("pageProps", {}).get("design")
    if isinstance(design, dict):
        if design.get("title"):
            out["title"] = _clean_title_suffix(str(design["title"]))
        if design.get("cover"):
            out["image_url"] = str(design["cover"])
        if design.get("summary"):
            out["description"] = str(design["summary"])
        if isinstance(design.get("tags"), list):
            out["tags"] = [str(t) for t in design["tags"] if t]

    if "title" not in out:
        raw_title = parser.meta.get("og:title") or parser.title
        if raw_title:
            out["title"] = _clean_title_suffix(raw_title)

    if "image_url" not in out and parser.meta.get("og:image"):
        out["image_url"] = parser.meta["og:image"]

    if "description" not in out:
        desc = parser.meta.get("og:description") or parser.meta.get("description") or ""
        if desc:
            out["description"] = desc

    combined_text = " ".join(filter(None, [out.get("description", ""), parser.meta.get("og:description", "")]))
    out.update(_extract_specs_from_text(combined_text))
    return out


def _nearest_palette_color(hex_str: str) -> str | None:
    cleaned = (hex_str or "").strip().lstrip("#")
    if len(cleaned) != 6:
        return None
    try:
        r1, g1, b1 = int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16)
    except ValueError:
        return None
    best_name: str | None = None
    best_dist = float("inf")
    for c in COLOR_PALETTE:
        ch = c.get("hex", "")
        if not ch.startswith("#") or len(ch) != 7:
            continue
        r2, g2, b2 = int(ch[1:3], 16), int(ch[3:5], 16), int(ch[5:7], 16)
        dist = (r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = c["name"]
    return best_name


def parse_makerworld_api_payload(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(data, dict) or not data.get("id"):
        return out

    title = data.get("titleTranslated") or data.get("title") or ""
    if title:
        out["title"] = _clean_title_suffix(str(title))

    ext = data.get("designExtension") if isinstance(data.get("designExtension"), dict) else {}
    instances = data.get("instances") if isinstance(data.get("instances"), list) else []
    default_id = data.get("defaultInstanceId")
    inst = next((i for i in instances if isinstance(i, dict) and (i.get("id") == default_id or i.get("isDefault"))), None)
    if inst is None and instances and isinstance(instances[0], dict):
        inst = instances[0]

    cover = data.get("coverUrl") or data.get("cover") or data.get("coverLandscape") or data.get("coverPortrait")
    if not cover and isinstance(ext.get("design_pictures"), list) and ext["design_pictures"]:
        pic0 = ext["design_pictures"][0]
        if isinstance(pic0, dict):
            cover = pic0.get("url")
    if not cover and isinstance(ext.get("real_pictures"), list) and ext["real_pictures"]:
        pic0 = ext["real_pictures"][0]
        if isinstance(pic0, dict):
            cover = pic0.get("url")
    if not cover and inst:
        cover = inst.get("cover")
    if cover:
        out["image_url"] = str(cover).strip()

    desc = data.get("summaryTranslated") or data.get("summary") or ""
    if desc:
        out["description"] = re.sub(r"<[^>]+>", " ", str(desc)).strip()

    raw_tags = data.get("tagsTranslated") or data.get("tags") or []
    if isinstance(raw_tags, list) and raw_tags:
        out["tags"] = [str(t).strip() for t in raw_tags if str(t).strip()]

    specs_source = " ".join(filter(None, [out.get("description", ""), str((inst or {}).get("summary") or "")]))
    out.update(_extract_specs_from_text(specs_source))

    if inst:
        if inst.get("weight"):
            try:
                out["filament_grams"] = round(float(inst["weight"]), 1)
            except (TypeError, ValueError):
                pass
        if inst.get("prediction"):
            try:
                mins = int(round(float(inst["prediction"]) / 60.0))
                if mins > 0:
                    out["print_time_min"] = mins
            except (TypeError, ValueError):
                pass

        fils = inst.get("instanceFilaments") if isinstance(inst.get("instanceFilaments"), list) else []
        if fils:
            mapped_fils: list[str] = []
            mapped_colors: list[str] = []
            for f in fils:
                if not isinstance(f, dict):
                    continue
                ftype = str(f.get("type") or "").strip().upper()
                for cand in FILAMENT_TYPES:
                    if cand.upper() == ftype and cand not in mapped_fils:
                        mapped_fils.append(cand)
                cname = _nearest_palette_color(str(f.get("color") or ""))
                if cname and cname not in mapped_colors:
                    mapped_colors.append(cname)
            if mapped_fils:
                out["recommended_filaments"] = mapped_fils
            if len(fils) > 1 and MULTICOLOR_LABEL not in mapped_colors:
                mapped_colors.insert(0, MULTICOLOR_LABEL)
            if mapped_colors:
                out["recommended_colors"] = mapped_colors

    return out


def fetch_makerworld_api(external_id: str, timeout: float = 8.0) -> dict[str, Any]:
    if not external_id:
        return {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://makerworld.com/",
        "Accept": "application/json",
    }
    url = f"https://makerworld.com/api/v1/design-service/design/{external_id}"
    for attempt in range(2):
        try:
            status_code, body, resp_headers = _urllib_get(url, timeout=timeout, headers=headers)
            if status_code == 200 and body:
                return parse_makerworld_api_payload(json.loads(body))
            if status_code == 429 and attempt == 0:
                wait_s = min(float(resp_headers.get("retry-after") or 2.0), 4.0)
                time.sleep(max(0.5, wait_s))
                continue
            break
        except Exception:
            break
    return {}


def fetch_remote_metadata(url: str, timeout: float = 6.0) -> dict[str, Any]:
    info = parse_url_info(url)
    if info["source"] == "MakerWorld" and info["external_id"]:
        api_meta = fetch_makerworld_api(info["external_id"], timeout=timeout)
        if api_meta:
            return api_meta
    try:
        status_code, body, _ = _urllib_get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        )
        if status_code == 200 and body:
            return parse_html_metadata(body, url)
    except Exception:
        pass
    return {}


_MODEL_SUBCATEGORY_RULES: dict[str, tuple[list[tuple[str, tuple[str, ...]]], str]] = {
    "Chaveiros & Personalizados": (
        [
            ("Times & Futebol", ("cruzeiro", "atlético", "atletico", "corinthians", "flamengo", "palmeiras", "futebol", "time", "copa", "brasil", "brasão", "escudo", "soccer")),
            ("Placas, Pix & Topos", ("pix", "qr", "placa", "topo", "bolo", "cake", "letreiro", "nomeplate", "sinalização", "porta de", "número", "numero")),
            ("Brincos & Acessórios", ("brinco", "earring", "iphone", "capa", "case", "colar", "pulseira", "anel", "sacola", "bolsa", "acessório")),
            ("Nomes & Brindes", ("personalizável", "personalizado", "custom", "nome", "mãe", "mae", "pai", "inicial", "letra", "brinde", "dia dos", "dia das")),
            ("Chaveiros 3D", ("chaveiro", "keychain", "keyring", "tag", "etiqueta", "hotel", "motel", "mosquetão", "argola", "berloque", "pingente")),
        ],
        "Personalizados Gerais",
    ),
    "Organização & Casa": (
        [
            ("Gridfinity", ("gridfinity",)),
            ("Cabos & Fios", ("cabo", "cabos", "fio", "fios", "cable", "cord", "carregador", "usb", "tomada", "fita")),
            ("Bandejas & Relógios", ("bandeja", "tray", "relógio", "relogio", "watch", "joia", "joias", "maquiagem", "cosmético", "óculos")),
            ("Caixas & Nichos", ("caixa", "box", "pote", "recipiente", "tampa", "gaveta", "drawer", "divisória", "estojo", "pílula", "pilula", "comprimido", "viagem", "frasco", "origami", "presente", "colmeia", "modular")),
            ("Porta-Objetos & Ganchos", ("gancho", "hook", "cabide", "hanger", "trava de porta", "batente", "para-porta", "calçado", "sapato", "porta-", "porta ", "skadis", "ikea", "mudas")),
        ],
        "Utilidades Domésticas",
    ),
    "Decoração & Arte": (
        [
            ("Vasos & Cachepôs", ("vaso", "vasos", "vase", "planta", "plantas", "suculenta", "cachepot", "cachepô", "cultivo", "irrigável", "irrigavel", "semente", "prato para vaso")),
            ("Pássaros & Natureza", ("comedouro", "pássaro", "passaro", "bird", "esquilo", "jardim", "ninho")),
            ("Religioso", ("presépio", "presepio", "nossa senhora", "aparecida", "jesus", "cruz", "santa", "santo", "anjo", "natal", "páscoa", "pascoa")),
            ("Esculturas & Bustos", ("escultura", "estátua", "estatua", "busto", "statue", "coração", "coracao", "ilusão", "difusor", "amor")),
            ("Placas & Quadros", ("quadro", "quadros", "arte de parede", "arte de porta", "placa", "placas", "iniciais", "hueforge", "lithophane")),
        ],
        "Decoração Geral",
    ),
    "Suportes & Eletrônicos": (
        [
            ("Celular & Tablet", ("celular", "smartphone", "telefone", "phone", "tablet", "ipad", "iphone", "kindle", "apple watch", "galaxy watch", "watch", "magsafe", "carro", "automotivo", "painel", "saída de ar", "gravidade")),
            ("Controles & Consoles", ("controle", "controller", "joystick", "arcade", "ps5", "ps4", "xbox", "switch", "nintendo", "console", "remoto")),
            ("Setup & Mesa", ("monitor", "notebook", "laptop", "mesa", "echo", "dot", "alexa", "headphone", "headset", "fone", "teclado", "mouse", "cabo", "webcam", "roteador", "usb", "sd", "esp32", "raspberry", "gopro", "câmera", "estúdio")),
            ("Expositores & Colecionáveis", ("funko", "minifigura", "lego", "1:64", "diecast", "expositor", "display", "miniatura", "óculos", "oculos", "varinha", "sabre", "relógio", "relogio")),
            ("Casa, Banheiro & Parede", ("parede", "wall", "papel higiênico", "higienico", "toalha", "escova", "pasta", "chuveiro", "sabonete", "secador", "barbear", "cozinha", "tampa", "talheres", "gridfinity", "caneca", "copo", "doces", "bolo", "lixo", "cerveja", "sacola", "barril", "mochila", "gancho", "garrafa", "morango", "tinta", "cachorro", "fezes", "cadarço")),
        ],
        "Suportes Gerais",
    ),
    "Ferramentas & Oficina": (
        [
            ("Mosquetões & Clipes", ("mosquetão", "mosquetao", "karabiner", "carabiner", "clip", "presilha")),
            ("Pintura & Modelismo", ("pintura", "paint", "chuck", "mandril", "espátula", "espatula", "paleta", "pincel", "aerógrafo")),
            ("Parede & Skadis", ("parede", "wall", "skadis", "pegboard", "vassoura", "gancho", "prateleira")),
            ("Parafusos & Caixas", ("parafuso", "screw", "porca", "bolt", "caixa", "segredo", "fechadura", "chave", "chaves")),
            ("Gabaritos & Medição", ("gabarito", "medição", "medicao", "régua", "regua", "paquímetro", "caliper", "ferramenta", "tool", "chaveiro", "broca", "calço")),
        ],
        "Oficina Geral",
    ),
    "Brinquedos & Articulados": (
        [
            ("Quebra-Cabeças & Educativos", ("quebra-cabeça", "quebra cabeça", "puzzle", "alfabeto", "números", "crianças", "infantil", "corpo humano", "patrulha", "montessori")),
            ("Fidget & Articulados", ("fidget", "spinner", "giratório", "clicker", "ovo", "páscoa", "surpresa", "flexível", "flexivel", "articulado", "flexi")),
            ("Dragões & Criaturas", ("dragão", "dragao", "dragon", "polvo", "sapo", "coelhinho", "coelho", "capivara", "banguela", "dino", "axolotl", "gato", "stitch", "rena", "crochê", "tricô", "trico", "tricotado")),
        ],
        "Brinquedos & Jogos",
    ),
    "Acessórios 3D": (
        [
            ("Calibração & Testes", ("torre", "temperatura", "calibração", "calibracao", "fluxo", "teste", "benchy", "retração", "nivelamento", "tolerância", "camada", "pla", "petg", "abs", "nylon")),
            ("Raspadores & Limpeza", ("raspador", "scraper", "limpador", "lixeira", "poop", "purge", "escova", "bico", "nozzle")),
            ("Chaveiros & Pingentes 3D", ("chaveiro", "keychain", "stitch", "cruzeiro", "atlético", "cachorro", "placas")),
            ("Bambu Lab, Elegoo & Upgrades", ("bambu", "ams", "elegoo", "neptune", "ender", "creality", "kobra", "ptfe", "extrusor", "hotend", "spool", "carretel", "filamento", "guia", "suporte")),
        ],
        "Peças & Acessórios Gerais",
    ),
    "Geek & Games": (
        [
            ("Funko Pop & Colecionáveis", ("funko", "pop", "bitty", "expositor", "prateleira", "colmeia")),
            ("Esportes & Clubes", ("cruzeiro", "raposão", "raposao", "atlético", "corinthians", "futebol", "bola", "clube", "time", "mesa mini")),
            ("Animes, Heróis & Filmes", ("naruto", "itachi", "minato", "pokemon", "pokémon", "homem-aranha", "spider", "disney", "princesa", "mulan", "cinderela", "ariel", "moana", "stitch", "harry potter", "varinha", "venom", "hulk", "mario", "dummy", "star wars", "batman", "marvel", "zelda")),
        ],
        "Geek Geral",
    ),
    "Cozinha & Utilidades": (
        [
            ("Canecas, Abridores & Bar", ("caneca", "chopp", "cervejeiro", "abridor", "porta garrafa", "latão", "bar")),
            ("Irrigação & Casa", ("gotejador", "gotejadores", "irrigação", "irrigacao", "regua", "garrafa pet", "garrafas pet", "foguete")),
            ("Preparo & Cozinha", ("espetinho", "espetinhos", "hambúrguer", "churrasco", "clipe", "selador", "café", "dispensador", "sabonete", "cozinha", "parede", "cook", "chef")),
        ],
        "Utilidades de Cozinha",
    ),
    "Miniaturas & Colecionáveis": (
        [
            ("Religioso & Esculturas", ("nossa senhora", "aparecida", "santa", "santo", "religioso", "estátua", "busto")),
            ("Expositores & Diecast", ("expositor", "expositores", "diecast", "1:64", "miniatura", "loft", "modular")),
        ],
        "Colecionáveis Gerais",
    ),
    "Outros": (
        [
            ("Jardim, Horta & Hidropônico", ("hidropônico", "hidroponic", "germinador", "germinação", "semente", "sprout", "cultivo", "irrigação", "gotejamento", "muda", "mudas", "aspersor", "cortador de grama", "jardim", "planta", "abacate", "vasinho")),
            ("Pets & Identificação", ("cachorro", "pet", "gato", "osso", "pata", "poo-ch", "fezes", "medalhinha", "coleira")),
            ("Calçados & Moda", ("sandália", "sandalia", "sandálias", "chinelo", "chinelos", "sapato", "sapatos", "sapatilha", "crocs", "sapateira", "pulseira", "grampo", "cabelo", "tênis", "calçado", "calçados")),
            ("Sazonal (Natal & Páscoa)", ("natal", "páscoa", "pascoa", "ovo", "ovos", "coelho", "reno", "papai noel", "natalino")),
            ("Esculturas, Religioso & Profissões", ("presépio", "natividade", "jesus", "arcanjo", "miguel", "santa", "santo", "filósofo", "caduceu", "médico", "themis", "justiça", "advocacia", "juiz", "martelo", "águia", "aguia", "estátua", "estatuas", "estatua")),
            ("Pintura, Papelaria & Testes 3D", ("tinta", "tintas", "paleta", "pincel", "estêncil", "estencéis", "régua", "escolar", "desenho", "colorir", "caderno", "encadernação", "furador", "crachá", "teste", "torre de teste", "lixeira", "kobra", "citadel", "vallejo", "protoboard")),
            ("Personagens, Anime & Geek", ("pikachu", "pokémon", "pokemon", "blastoise", "itachi", "uchiha", "raphtalia", "banguela", "fúria da noite", "hello kitty", "dummy", "semibot", "beyblade", "princesa", "urso", "naruto", "dragon", "corinthians", "atlético", "atletico", "galo", "messi", "copa do mundo", "futebol", "transformers", "arcade", "fliperama", "joystick", "glock")),
            ("Automotivo, PVC & Ferragens", ("nissan", "skyline", "vw", "honda", "carro", "pvc", "conector", "cano", "extrusão", "rolamento", "pés reguláveis", "pinça", "pneus", "prisioneiro", "porca", "serra", "abraçadeira", "guindaste", "carregadeira")),
            ("Brinquedos, Jogos & Esportes", ("bola", "basquete", "ping pong", "pião", "hélice", "helicóptero", "lançador", "launcher", "estilingue", "balão", "balões", "drone", "brinquedo", "jogo", "apito", "abacaxi", "fidget", "pistola", "boneca", "areia")),
            ("Cozinha, Alimentos & Banheiro", ("descascador", "cortador de abacate", "laranja", "legumes", "cerveja", "chopp", "hambúrguer", "espumador", "napkin", "restaurante", "sabonete", "saboneteira", "copo", "escova de dentes", "papel higiênico", "dispenser", "dispensador", "chuveiro", "presilha para saco", "sorvete")),
            ("Casa, Cofres & Prateleiras", ("cofrinho", "cofre", "banco de moedas", "prateleira", "colmeia", "calço", "porta", "janela", "difusor", "aroma", "números e letras", "frase", "parede", "pix", "qrcode", "armário", "armazenamento", "presente", "prendedor")),
        ],
        "Modelos Gerais",
    ),
}


def _kw_match(kw: str, haystack: str) -> bool:
    if kw == "time":
        return bool(re.search(r"\btime(?:s)?\s+(?:de\s+)?futebol\b|\b(?:seu|meu)\s+time\b", haystack))
    if kw == "ams":
        return bool(re.search(r"(?<!sem\s)(?<!não\s)(?<!nao\s)(?<!no\s)\bams\b", haystack))
    if " " not in kw and len(kw) <= 5 and kw.replace("-", "").isalnum():
        suffix = "" if kw in {"pla", "abs", "usb", "vw", "pix", "petg", "pop"} else "s?"
        return bool(re.search(rf"\b{re.escape(kw)}{suffix}\b", haystack))
    return kw in haystack


def classify_category(title: str, tags: list[str] | None = None, description: str = "") -> str:
    haystack = " ".join([title or "", " ".join(tags or []), description or ""]).lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in haystack for kw in keywords):
            return category
    return "Outros"


_CROSS_SUBCATEGORY_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("Chaveiros & Personalizados", "Chaveiros 3D", ("chaveiro", "chaveiros", "keychain", "keyring")),
    ("Chaveiros & Personalizados", "Times & Futebol", ("cruzeiro", "atlético", "atletico", "corinthians", "flamengo", "palmeiras", "futebol", "copa do mundo", "brasão")),
    ("Chaveiros & Personalizados", "Placas, Pix & Topos", ("pix", "qrcode", "qr code", "topo de bolo")),
    ("Geek & Games", "Esportes & Clubes", ("cruzeiro", "raposão", "atlético", "atletico", "corinthians", "flamengo", "palmeiras", "futebol", "copa do mundo")),
    ("Geek & Games", "Funko Pop & Colecionáveis", ("funko", "bitty pop")),
    ("Geek & Games", "Animes, Heróis & Filmes", ("naruto", "itachi", "pikachu", "pokémon", "pokemon", "blastoise", "homem-aranha", "spider-man", "spiderman", "harry potter", "stitch", "disney", "dummy 13", "star wars", "batman", "marvel", "zelda", "super mario")),
    ("Brinquedos & Articulados", "Dragões & Criaturas", ("dragão", "dragon", "tricô", "tricotado", "crochê", "banguela", "capivara", "polvo articulado")),
    ("Brinquedos & Articulados", "Fidget & Articulados", ("fidget", "articulado", "articulated", "flexi", "spinner")),
    ("Cozinha & Utilidades", "Canecas, Abridores & Bar", ("abridor", "caneca", "chopp", "porta garrafa", "cervejeiro", "cerveja")),
    ("Cozinha & Utilidades", "Irrigação & Casa", ("hidropônico", "hidroponic", "gotejador", "gotejamento", "irrigação")),
    ("Cozinha & Utilidades", "Preparo & Cozinha", ("descascador", "hambúrguer", "espetinho", "churrasco", "cantinho do café")),
    ("Decoração & Arte", "Religioso", ("nossa senhora", "aparecida", "presépio", "presepio", "natividade", "mini jesus", "arcanjo")),
    ("Decoração & Arte", "Esculturas & Bustos", ("escultura", "estátua", "estatua", "busto", "filósofo", "águia", "themis")),
    ("Decoração & Arte", "Vasos & Cachepôs", ("vaso", "vasinho", "cachepot", "cachepô", "autoirrigável", "auto-irrigável")),
    ("Decoração & Arte", "Pássaros & Natureza", ("comedouro", "pássaro", "esquilo")),
    ("Organização & Casa", "Gridfinity", ("gridfinity",)),
    ("Ferramentas & Oficina", "Parede & Skadis", ("skadis", "pegboard")),
    ("Ferramentas & Oficina", "Mosquetões & Clipes", ("mosquetão", "karabiner", "carabiner")),
    ("Ferramentas & Oficina", "Pintura & Modelismo", ("maleta de tintas", "paleta", "pincel", "citadel", "vallejo", "tinta acrílica")),
    ("Acessórios 3D", "Bambu Lab, Elegoo & Upgrades", ("bambu", "ams", "elegoo", "neptune", "ender", "kobra", "ptfe", "filamento")),
    ("Acessórios 3D", "Calibração & Testes", ("torre de temperatura", "calibração", "benchy", "torre de teste")),
    ("Suportes & Eletrônicos", "Expositores & Colecionáveis", ("expositor", "funko", "1:64", "diecast", "minifigura")),
    ("Suportes & Eletrônicos", "Celular & Tablet", ("suporte de celular", "suporte para celular", "smartphone", "magsafe", "iphone", "kindle", "apple watch", "galaxy watch")),
    ("Suportes & Eletrônicos", "Controles & Consoles", ("ps5", "xbox", "nintendo switch", "joystick")),
    ("Outros", "Jardim, Horta & Hidropônico", ("hidropônico", "germinador", "germinação", "semente", "sprout", "mudas", "irrigação", "gotejador")),
    ("Outros", "Pets & Identificação", ("cachorro", "pet", "poo-ch", "fezes de cachorro", "osso de cachorro", "pata de cachorro")),
    ("Outros", "Calçados & Moda", ("sandália", "sandálias", "chinelo", "chinelos", "crocs", "sapatilha", "sapateira")),
    ("Outros", "Sazonal (Natal & Páscoa)", ("natal", "natalino", "páscoa", "pascoa", "ovo surpresa", "presépio")),
]


def normalize_classifications(
    classifications: list[dict[str, Any]] | None = None,
    category: str = "",
    subcategory: str = "",
    categories: list[str] | None = None,
    subcategories: list[str] | None = None,
    default_category: str = "Outros",
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(cat_val: Any, sub_val: Any) -> None:
        cat = str(cat_val or "").strip()
        sub = str(sub_val or "").strip()
        if not cat:
            return
        key = (cat, sub)
        if key not in seen:
            seen.add(key)
            out.append({"category": cat, "subcategory": sub})

    if classifications is not None:
        for entry in classifications:
            if isinstance(entry, dict):
                _add(entry.get("category"), entry.get("subcategory"))
    else:
        _add(category, subcategory)
        if categories:
            for idx, c in enumerate(categories):
                sub_cand = subcategories[idx] if (subcategories and idx < len(subcategories)) else ""
                _add(c, sub_cand)

    if not out and default_category:
        _add(category or default_category, subcategory)
    return out


def classify_model_subcategory(
    title: str,
    category: str,
    tags: list[str] | None = None,
    description: str = "",
) -> str:
    haystack = " ".join([title or "", " ".join(tags or []), description or ""]).lower()
    cat_entry = _MODEL_SUBCATEGORY_RULES.get(category)
    if cat_entry:
        rules, fallback = cat_entry
        for sub_name, keywords in rules:
            if any(_kw_match(kw, haystack) for kw in keywords):
                return sub_name
        return fallback
    return "Geral"


def classify_model_classifications(
    title: str,
    primary_category: str = "",
    tags: list[str] | None = None,
    description: str = "",
    explicit_subcategory: str = "",
) -> list[dict[str, str]]:
    primary_cat = str(primary_category or "").strip() or classify_category(title, tags, description)
    haystack_full = " ".join([title or "", " ".join(tags or []), description or ""]).lower()
    haystack_tight = " ".join([title or "", " ".join(tags or [])]).lower()

    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(cat_name: str, sub_name: str) -> None:
        c = str(cat_name or "").strip()
        s = str(sub_name or "").strip()
        if c and (c, s) not in seen:
            seen.add((c, s))
            results.append({"category": c, "subcategory": s})

    if explicit_subcategory:
        _add(primary_cat, explicit_subcategory)

    # 1. All matching subcategories within primary_cat (e.g. Chaveiros 3D + Times & Futebol)
    cat_entry = _MODEL_SUBCATEGORY_RULES.get(primary_cat)
    if cat_entry:
        rules, fallback = cat_entry
        matched_in_primary = False
        for sub_name, keywords in rules:
            if any(_kw_match(kw, haystack_full) for kw in keywords):
                _add(primary_cat, sub_name)
                matched_in_primary = True
        if not matched_in_primary and not explicit_subcategory:
            _add(primary_cat, fallback)
    elif not results:
        _add(primary_cat, "Geral")

    # 2. High-precision cross-category & cross-subcategory matches from title + tags
    for cross_cat, cross_sub, keywords in _CROSS_SUBCATEGORY_RULES:
        if any(_kw_match(kw, haystack_tight) for kw in keywords):
            _add(cross_cat, cross_sub)

    return results


def classify_size_tier(
    max_dimension_mm: float | None,
    filament_grams: float | None = None,
    title: str = "",
) -> str:
    if max_dimension_mm is not None:
        if max_dimension_mm <= 80:
            return "Pequeno"
        if max_dimension_mm <= 160:
            return "Médio"
        if max_dimension_mm <= 240:
            return "Grande"
        return "Extra Grande"

    if filament_grams is not None:
        if filament_grams <= 40:
            return "Pequeno"
        if filament_grams <= 160:
            return "Médio"
        if filament_grams <= 400:
            return "Grande"
        return "Extra Grande"

    lower = (title or "").lower()
    if any(k in lower for k in ("mini", "keychain", "chaveiro", "coin", "cap", "clip")):
        return "Pequeno"
    if any(k in lower for k in ("full", "giant", "gigante", "armor", "helmet", "capacete", "modular")):
        return "Grande"
    return "Médio"


def recommend_filaments_and_colors(
    title: str,
    category: str,
    tags: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    haystack = " ".join([title or "", " ".join(tags or []), description or ""]).lower()

    if any(k in haystack for k in ("tpu", "flexible", "flexível", "bumper", "gasket", "junta", "tire", "pneu", "shoe")):
        filaments = ["TPU", "PETG"]
        reason = "TPU recomendado pela flexibilidade e absorção de impacto; PETG como alternativa semirrígida."
        colors = ["Preto", "Laranja", MULTICOLOR_LABEL]
    elif any(k in haystack for k in ("outdoor", "externo", "car", "carro", "automotive", "sun", "sol", "hot")):
        filaments = ["ABS/ASA", "PETG"]
        reason = "ABS/ASA indicado pela resistência UV e térmica; PETG é alternativa mais fácil de imprimir."
        colors = ["Preto", "Cinza / Grafite"]
    elif category in {"Ferramentas & Oficina", "Suportes & Eletrônicos", "Acessórios 3D"} or any(
        k in haystack for k in ("mount", "bracket", "suporte", "shelf", "prateleira", "heavy", "hook", "gancho", "clamp")
    ):
        filaments = ["PETG", "PLA+", "PLA-CF"]
        reason = "PETG ou PLA+ recomendados pela resistência mecânica, encaixe firme e tolerância ao calor."
        colors = ["Preto", "Cinza / Grafite", "Laranja"]
        if category == "Organização & Casa" or "organizer" in haystack or "skadis" in haystack:
            colors.append(MULTICOLOR_LABEL)
    elif category == "Cozinha & Utilidades":
        filaments = ["PETG", "PLA+"]
        reason = "PETG recomendado pela maior resistência à umidade, lavagem e temperatura moderada."
        colors = ["Branco", "Cinza / Grafite", MULTICOLOR_LABEL]
    elif category == "Brinquedos & Articulados":
        filaments = ["PLA Silk", "PLA", "PLA+"]
        reason = "PLA Silk e PLA oferecem excelente definição de juntas articuladas e brilho visual."
        colors = [MULTICOLOR_LABEL, "Roxo", "Azul", "Verde"]
    elif category == "Decoração & Arte":
        filaments = ["PLA Matte", "PLA Silk", "PLA"]
        reason = "PLA Matte reduz marcas de camada em peças decorativas; PLA Silk destaca relevos e curvas."
        colors = [MULTICOLOR_LABEL, "Branco", "Preto", "Marrom / Madeira"]
    elif category in {"Miniaturas & Colecionáveis", "Geek & Games"}:
        filaments = ["PLA Matte", "PLA+", "PLA Silk"]
        reason = "PLA Matte/PLA+ preserva detalhes finos e facilita pintura ou acabamento."
        colors = [MULTICOLOR_LABEL, "Cinza / Grafite", "Prata / Metálico", "Amarelo / Dourado"]
    elif category == "Chaveiros & Personalizados":
        filaments = ["PLA+", "PLA", "PLA Silk"]
        reason = "PLA+ e PLA garantem detalhes nítidos em chaveiros/placas e ótima troca de cor em AMS."
        colors = [MULTICOLOR_LABEL, "Preto", "Branco", "Amarelo / Dourado", "Azul", "Vermelho"]
    elif category == "Organização & Casa":
        filaments = ["PLA+", "PETG", "PLA Matte"]
        reason = "PLA+ e PETG garantem boa rigidez para caixas, bandejas e organizadores do dia a dia."
        colors = [MULTICOLOR_LABEL, "Branco", "Preto", "Cinza / Grafite"]
    else:
        filaments = ["PLA", "PLA+", "PETG"]
        reason = "PLA/PLA+ atendem bem uso geral com alta precisão dimensional e fácil impressão."
        colors = [MULTICOLOR_LABEL, "Preto", "Branco"]

    return {
        "recommended_filaments": filaments,
        "filament_reason": reason,
        "recommended_colors": list(dict.fromkeys(colors)),
    }


def _parse_max_dim(dimensions_mm: str) -> float | None:
    if not dimensions_mm:
        return None
    m = _DIMS_RE.search(dimensions_mm)
    if not m:
        nums = re.findall(r"\d+(?:[.,]\d+)?", dimensions_mm)
        return max((float(n.replace(",", ".")) for n in nums), default=None)
    return max(float(g.replace(",", ".")) for g in m.groups())


def analyze_model_input(
    payload: dict[str, Any],
    collected_at: str | None = None,
    fetch_remote: bool = False,
) -> dict[str, Any]:
    raw_url = str(payload.get("url") or "").strip()
    url_info = parse_url_info(raw_url)
    norm_url = url_info["url"]

    remote_meta = fetch_remote_metadata(norm_url) if fetch_remote and norm_url else {}

    title = str(payload.get("title") or remote_meta.get("title") or url_info["title"]).strip()
    description = str(payload.get("description") or remote_meta.get("description") or "").strip()
    image_url = str(payload.get("image_url") or remote_meta.get("image_url") or "").strip()
    tags_raw = payload.get("tags") or remote_meta.get("tags") or []
    tags = [str(t).strip() for t in tags_raw if str(t).strip()]

    dimensions_mm = str(payload.get("dimensions_mm") or remote_meta.get("dimensions_mm") or "").strip()
    max_dim = payload.get("max_dimension_mm")
    if max_dim is None:
        max_dim = remote_meta.get("max_dimension_mm") or _parse_max_dim(dimensions_mm)
    else:
        max_dim = float(max_dim)

    filament_grams = payload.get("filament_grams")
    if filament_grams is None:
        filament_grams = remote_meta.get("filament_grams")
    elif filament_grams != "":
        filament_grams = float(filament_grams)
    else:
        filament_grams = None

    print_time_min = payload.get("print_time_min")
    if print_time_min is None:
        print_time_min = remote_meta.get("print_time_min")
    elif print_time_min != "":
        print_time_min = int(round(float(print_time_min)))
    else:
        print_time_min = None

    category = payload.get("category") or classify_category(title, tags, description)
    explicit_sub = str(payload.get("subcategory") or "").strip()
    if payload.get("classifications") is not None:
        classifications = normalize_classifications(
            payload.get("classifications"),
            category=category,
            subcategory=explicit_sub,
        )
    else:
        classifications = classify_model_classifications(
            title,
            category,
            tags,
            description,
            explicit_subcategory=explicit_sub,
        )
    primary_pair = classifications[0] if classifications else {"category": category, "subcategory": explicit_sub}
    category = primary_pair["category"]
    subcategory = primary_pair["subcategory"]
    categories_list = list(dict.fromkeys(c["category"] for c in classifications if c["category"]))
    subcategories_list = list(dict.fromkeys(c["subcategory"] for c in classifications if c["subcategory"]))
    size_tier = payload.get("size_tier") or classify_size_tier(max_dim, filament_grams, title)

    recs = recommend_filaments_and_colors(title, category, tags, description)
    recommended_filaments = (
        payload.get("recommended_filaments")
        or remote_meta.get("recommended_filaments")
        or recs["recommended_filaments"]
    )
    recommended_colors = (
        payload.get("recommended_colors")
        or remote_meta.get("recommended_colors")
        or recs["recommended_colors"]
    )
    filament_reason = payload.get("filament_reason") or recs["filament_reason"]

    stamp = collected_at or payload.get("collected_at") or datetime.now().astimezone().isoformat(timespec="seconds")

    return {
        "url": norm_url,
        "source": url_info["source"],
        "external_id": url_info["external_id"],
        "title": title,
        "description": description,
        "image_url": image_url,
        "category": category,
        "subcategory": subcategory,
        "categories": categories_list,
        "subcategories": subcategories_list,
        "classifications": classifications,
        "tags": tags,
        "size_tier": size_tier,
        "dimensions_mm": dimensions_mm,
        "max_dimension_mm": max_dim,
        "filament_grams": filament_grams,
        "print_time_min": print_time_min,
        "recommended_filaments": list(recommended_filaments),
        "filament_reason": filament_reason,
        "recommended_colors": list(recommended_colors),
        "status": payload.get("status") or "Na Fila",
        "notes": str(payload.get("notes") or "").strip(),
        "collected_at": stamp,
    }
