from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from app.fila3d import analyzer
from app.fila3d.analyzer import (
    CATEGORIES,
    COLOR_PALETTE,
    FILAMENT_TYPES,
    MULTICOLOR_LABEL,
    SIZE_TIERS,
    STATUSES,
    analyze_model_input,
    classify_size_tier,
    extract_urls,
    normalize_url,
)
from app.fila3d.database import (
    batch_update_enriched_models,
    count_models_missing_images,
    delete_model,
    get_model,
    init_db,
    list_models,
    list_models_missing_images,
    update_model,
    upsert_model,
)
from app.fila3d.hub_db import (
    JOB_PRIORITIES,
    JOB_STATUSES,
    JOB_TARGETS,
    PAYMENT_STATUSES,
    POST_FORMATS,
    POST_STATUSES,
    PRINTER_STATUSES,
    SALE_CHANNELS,
    create_catalog_item,
    create_job,
    create_media_post,
    create_printer,
    create_rubric,
    create_sale,
    create_slicing_profile,
    create_spool,
    create_subcategory,
    delete_catalog_item,
    delete_job,
    delete_media_post,
    delete_printer,
    delete_rubric,
    delete_sale,
    delete_slicing_profile,
    delete_spool,
    delete_subcategory,
    ensure_model_subcategory,
    ensure_subcategory_entry,
    generate_instagram_caption,
    get_hub_summary,
    import_ita_arte_catalog,
    init_hub_db,
    list_catalog_items,
    list_jobs,
    list_media_posts,
    list_printers,
    list_rubrics,
    list_sales,
    list_slicing_profiles,
    list_spools,
    list_subcategories,
    reclassify_all_items,
    seed_default_business_data,
    update_catalog_item,
    update_job,
    update_media_post,
    update_printer,
    update_rubric,
    update_slicing_profile,
    update_spool,
    update_subcategory,
)
from app.routes.helpers import get_settings

bp = Blueprint("fila3d", __name__)

_LEGACY_DIR = Path(r"H:\Meu Drive\ANTIGRAVITY\fila-impressao-3d")
_LEGACY_DB = _LEGACY_DIR / "data" / "prints.db"
_LEGACY_MEDIA = _LEGACY_DIR / "data" / "media"
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_INITIALIZED_DBS: set[str] = set()


def _get_fila3d_paths() -> tuple[Path, Path, bool]:
    """Resolve db_path e media_dir dentro do data_dir configurado, semeando na 1a execução."""
    settings = get_settings()
    db_path = settings.data_dir / "prints.db"
    media_path = settings.data_dir / "fila3d_media"
    media_path.mkdir(parents=True, exist_ok=True)

    key = str(db_path.resolve())
    if key not in _INITIALIZED_DBS:
        if not settings.testing:
            if not db_path.exists() and _LEGACY_DB.exists():
                db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_LEGACY_DB, db_path)
            if _LEGACY_MEDIA.exists():
                shutil.copytree(_LEGACY_MEDIA, media_path, dirs_exist_ok=True)
        init_db(db_path)
        init_hub_db(db_path)
        if not settings.testing:
            seed_default_business_data(db_path, media_path)
        _INITIALIZED_DBS.add(key)

    return db_path, media_path, bool(settings.testing)


def _err(detail: str, status: int = 400):
    return jsonify({"detail": detail}), status


def _opt_int(name: str) -> int | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _opt_float(name: str) -> float | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _opt_bool(name: str, default: bool = False) -> bool:
    raw = request.args.get(name, "")
    if not raw:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def _json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _render_public_catalog_html(
    items: list[dict[str, Any]],
    media_path: Path,
    category_filter: str = "",
    subcategory_filter: str = "",
) -> str:
    has_logo = (media_path / "catalog" / "logo-ita-arte-3d.jpg").exists()
    logo_html = (
        '<img src="/media/catalog/logo-ita-arte-3d.jpg" alt="Ita Arte 3D" class="pub-logo" />'
        if has_logo
        else '<div class="pub-mark">IA3D</div>'
    )
    active_items = [i for i in items if i.get("active", True)]
    if category_filter and subcategory_filter:
        active_items = [
            i
            for i in active_items
            if any(
                c.get("category") == category_filter and c.get("subcategory", "") == subcategory_filter
                for c in (
                    i.get("classifications")
                    or [{"category": i.get("category", ""), "subcategory": i.get("subcategory", "")}]
                )
            )
        ]
    elif category_filter:
        active_items = [
            i for i in active_items if category_filter in (i.get("categories") or [i.get("category", "")])
        ]
    elif subcategory_filter:
        active_items = [
            i
            for i in active_items
            if subcategory_filter in (i.get("subcategories") or ([i["subcategory"]] if i.get("subcategory") else []))
        ]

    cards = []
    for item in active_items:
        price = f"R$ {item['sale_price_brl']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        img = (
            f'<img src="{escape(item["image_url"])}" alt="{escape(item["name"])}" loading="lazy" />'
            if item.get("image_url")
            else '<div class="pub-no-img">Ita Arte 3D</div>'
        )
        stock_tag = (
            f'<span class="pub-badge ready">Pronta entrega ({item["stock_qty"]})</span>'
            if item.get("stock_qty", 0) > 0
            else '<span class="pub-badge order">Sob encomenda</span>'
        )
        dims = f'<div class="pub-dims">{escape(item["dimensions_cm"])}</div>' if item.get("dimensions_cm") else ""
        code = f'<span class="pub-code">{escape(item["code"])}</span>' if item.get("code") else ""
        pairs = item.get("classifications") or [
            {"category": item["category"], "subcategory": item.get("subcategory", "")}
        ]
        class_labels = " • ".join(
            f"{c['category']} › {c['subcategory']}" if c.get("subcategory") else c["category"] for c in pairs
        )
        cards.append(
            f"""
            <article class="pub-card">
              <div class="pub-thumb">{img}</div>
              <div class="pub-body">
                <div class="pub-meta">{code}<span class="pub-cat">{escape(class_labels)}</span></div>
                <h3>{escape(item['name'])}</h3>
                {dims}
                <div class="pub-footer">
                  <strong class="pub-price">{price}</strong>
                  {stock_tag}
                </div>
              </div>
            </article>
            """
        )

    cards_html = "".join(cards) or '<p class="pub-empty">Nenhum produto ativo neste filtro.</p>'
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ita Arte 3D — Catálogo de Produtos</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: -apple-system, "Segoe UI", Arial, sans-serif; background:#09090b; color:#fafafa; }}
    .pub-wrap {{ max-width:1120px; margin:0 auto; padding:28px 20px 60px; }}
    .pub-head {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:16px; border-bottom:1px solid rgba(255,255,255,.1); padding-bottom:20px; margin-bottom:24px; }}
    .pub-brand {{ display:flex; align-items:center; gap:14px; }}
    .pub-logo {{ width:56px; height:56px; border-radius:12px; object-fit:cover; border:1px solid rgba(255,255,255,.12); }}
    .pub-mark {{ width:56px; height:56px; border-radius:12px; background:#0070f3; display:grid; place-items:center; font-weight:700; }}
    h1 {{ margin:0; font-size:22px; }}
    .pub-sub {{ margin:3px 0 0; color:#a1a1aa; font-size:13px; }}
    .pub-actions {{ display:flex; gap:8px; }}
    .pub-btn {{ border:1px solid rgba(255,255,255,.15); background:#18181b; color:#fafafa; padding:8px 14px; border-radius:8px; cursor:pointer; font-size:13px; text-decoration:none; }}
    .pub-btn.primary {{ background:#0070f3; border-color:#0070f3; }}
    .pub-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:16px; }}
    .pub-card {{ background:#111114; border:1px solid rgba(255,255,255,.1); border-radius:12px; overflow:hidden; display:flex; flex-direction:column; break-inside:avoid; }}
    .pub-thumb {{ aspect-ratio:4/3; background:#18181b; display:grid; place-items:center; overflow:hidden; }}
    .pub-thumb img {{ width:100%; height:100%; object-fit:cover; }}
    .pub-no-img {{ color:#71717a; font-size:13px; }}
    .pub-body {{ padding:14px; display:flex; flex-direction:column; gap:8px; flex:1; }}
    .pub-meta {{ display:flex; align-items:center; gap:6px; font-size:11px; color:#a1a1aa; }}
    .pub-code {{ font-family: ui-monospace, monospace; background:rgba(255,255,255,.08); padding:2px 6px; border-radius:4px; color:#fafafa; }}
    .pub-card h3 {{ margin:0; font-size:15px; line-height:1.35; }}
    .pub-dims {{ font-size:12px; color:#a1a1aa; }}
    .pub-footer {{ margin-top:auto; padding-top:8px; border-top:1px solid rgba(255,255,255,.08); display:flex; align-items:center; justify-content:space-between; gap:8px; }}
    .pub-price {{ font-size:17px; color:#38bdf8; font-variant-numeric:tabular-nums; }}
    .pub-badge {{ font-size:11px; padding:3px 8px; border-radius:999px; }}
    .pub-badge.ready {{ background:rgba(22,163,74,.2); color:#4ade80; }}
    .pub-badge.order {{ background:rgba(255,255,255,.08); color:#d4d4d8; }}
    @media print {{
      body {{ background:#ffffff; color:#111111; }}
      .pub-actions {{ display:none; }}
      .pub-card {{ background:#ffffff; border-color:#d4d4d8; }}
      .pub-price {{ color:#0369a1; }}
    }}
  </style>
</head>
<body>
  <div class="pub-wrap">
    <header class="pub-head">
      <div class="pub-brand">
        {logo_html}
        <div>
          <h1>Ita Arte 3D — Catálogo de Produtos</h1>
          <p class="pub-sub">Impressão 3D personalizada • Peças exclusivas sob medida</p>
        </div>
      </div>
      <div class="pub-actions">
        <a class="pub-btn" href="/fila-3d">Abrir Painel Interno</a>
        <button class="pub-btn primary" onclick="window.print()">Imprimir / Salvar PDF</button>
      </div>
    </header>
    <div class="pub-grid">{cards_html}</div>
  </div>
</body>
</html>"""


# ---- Páginas e Mídia ---- #


@bp.route("/fila-3d")
def hub():
    _get_fila3d_paths()
    return render_template("fila3d/hub.html")


@bp.route("/catalogo-publico")
def public_catalog():
    db_path, media_path, _ = _get_fila3d_paths()
    category = request.args.get("category", "")
    subcategory = request.args.get("subcategory", "")
    items = list_catalog_items(db_path)["items"]
    return _render_public_catalog_html(items, media_path, category_filter=category, subcategory_filter=subcategory)


@bp.route("/media/<path:filename>")
def serve_media(filename: str):
    _, media_path, _ = _get_fila3d_paths()
    return send_from_directory(media_path, filename)


# ---- Summary & Metadata ---- #


@bp.route("/api/hub/summary")
def api_hub_summary():
    db_path, _, _ = _get_fila3d_paths()
    return jsonify(get_hub_summary(db_path))


@bp.route("/api/catalog-meta")
def api_catalog_meta():
    _get_fila3d_paths()
    return jsonify(
        {
            "categories": CATEGORIES,
            "size_tiers": SIZE_TIERS,
            "filaments": FILAMENT_TYPES,
            "colors": COLOR_PALETTE,
            "multicolor_label": MULTICOLOR_LABEL,
            "statuses": STATUSES,
            "printer_statuses": PRINTER_STATUSES,
            "job_statuses": JOB_STATUSES,
            "job_priorities": JOB_PRIORITIES,
            "job_targets": JOB_TARGETS,
            "post_formats": POST_FORMATS,
            "post_statuses": POST_STATUSES,
            "sale_channels": SALE_CHANNELS,
            "payment_statuses": PAYMENT_STATUSES,
        }
    )


# ---- 1. Models ---- #


@bp.route("/api/import/batch", methods=["POST"])
def api_import_batch():
    db_path, _, is_testing = _get_fila3d_paths()
    payload = _json_body()
    raw_text = str(payload.get("raw_text") or "")
    urls = payload.get("urls") or []
    items = payload.get("items") or []

    by_url: dict[str, dict[str, Any]] = {}
    for url in extract_urls(raw_text):
        by_url[url] = {"url": url}
    for raw_u in urls:
        for url in extract_urls(str(raw_u)):
            by_url.setdefault(url, {"url": url})
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_u = str(item.get("url") or "").strip()
        if not raw_u:
            continue
        norm = normalize_url(raw_u)
        by_url[norm] = {**item, "url": norm}

    if not by_url:
        return _err("Nenhum link HTTP/HTTPS válido encontrado para importar.", 400)

    fetch_remote = not is_testing
    item_payloads = list(by_url.values())
    if fetch_remote and len(item_payloads) > 1:
        with ThreadPoolExecutor(max_workers=2) as pool:
            analyzed_items = list(pool.map(lambda p: analyze_model_input(p, fetch_remote=True), item_payloads))
    else:
        analyzed_items = [analyze_model_input(p, fetch_remote=fetch_remote) for p in item_payloads]

    saved = [upsert_model(db_path, analyzed) for analyzed in analyzed_items]
    for item in saved:
        for pair in (
            item.get("classifications")
            or [{"category": item.get("category"), "subcategory": item.get("subcategory")}]
        ):
            if pair.get("category") and pair.get("subcategory"):
                ensure_model_subcategory(db_path, pair["category"], pair["subcategory"])
    return jsonify({"count": len(saved), "items": saved})


@bp.route("/api/models")
def api_get_models():
    db_path, _, _ = _get_fila3d_paths()
    limit = _opt_int("limit")
    if limit is not None:
        limit = max(1, min(500, limit))
    offset = max(0, _opt_int("offset") or 0)
    return jsonify(
        list_models(
            db_path,
            {
                "q": request.args.get("q", ""),
                "status": request.args.get("status", ""),
                "category": request.args.get("category", ""),
                "subcategory": request.args.get("subcategory", ""),
                "source": request.args.get("source", ""),
                "collected_from": request.args.get("collected_from", ""),
                "collected_to": request.args.get("collected_to", ""),
                "size_tier": request.args.get("size_tier", ""),
                "max_dimension_mm": _opt_float("max_dimension_mm"),
                "min_grams": _opt_float("min_grams"),
                "max_grams": _opt_float("max_grams"),
                "filament": request.args.get("filament", ""),
                "color": request.args.get("color", ""),
                "include_multicolor": _opt_bool("include_multicolor", False),
                "exclude_archived": _opt_bool("exclude_archived", False),
                "sort": request.args.get("sort", "collected_desc"),
                "limit": limit,
                "offset": offset,
            },
        )
    )


@bp.route("/api/models/enrich-missing", methods=["POST"])
def api_enrich_missing():
    db_path, _, is_testing = _get_fila3d_paths()
    limit = max(1, min(500, _opt_int("limit") or 50))
    offset = max(0, _opt_int("offset") or 0)
    candidates = list_models_missing_images(db_path, limit=limit, offset=offset)
    total_before = count_models_missing_images(db_path)
    if not candidates or is_testing:
        return jsonify(
            {
                "requested": len(candidates) if not is_testing else 0,
                "enriched": 0,
                "total_missing": total_before,
                "next_offset": offset,
                "has_more_missing": False,
            }
        )

    def _fetch_one(model_item: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
        meta = (
            analyzer.fetch_makerworld_api(model_item["external_id"], timeout=8.0)
            if model_item.get("source") == "MakerWorld" and model_item.get("external_id")
            else analyzer.fetch_remote_metadata(model_item["url"], timeout=8.0)
        )
        if not meta:
            return None
        if meta.get("filament_grams") and not model_item.get("filament_grams"):
            meta["size_tier"] = classify_size_tier(
                meta.get("max_dimension_mm") or model_item.get("max_dimension_mm"),
                meta.get("filament_grams"),
                model_item.get("title", ""),
            )
        return (model_item["id"], meta)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [res for res in pool.map(_fetch_one, candidates) if res is not None]

    batch_update_enriched_models(db_path, results)
    enriched_images = sum(1 for _, m in results if m.get("image_url"))
    failed_images = max(0, len(candidates) - enriched_images)
    next_offset = offset + failed_images
    total_after = count_models_missing_images(db_path)
    return jsonify(
        {
            "requested": len(candidates),
            "enriched": enriched_images,
            "total_missing": total_after,
            "next_offset": next_offset,
            "has_more_missing": next_offset < total_after,
        }
    )


@bp.route("/api/models/<int:model_id>/enrich", methods=["POST"])
def api_enrich_single_model(model_id: int):
    db_path, _, _ = _get_fila3d_paths()
    existing = get_model(db_path, model_id)
    if not existing:
        return _err("Modelo não encontrado.", 404)
    meta = (
        analyzer.fetch_makerworld_api(existing["external_id"], timeout=8.0)
        if existing["source"] == "MakerWorld" and existing["external_id"]
        else analyzer.fetch_remote_metadata(existing["url"], timeout=8.0)
    )
    if not meta:
        return _err("Não foi possível obter metadados/foto do MakerWorld para este modelo.", 502)
    updates: dict[str, Any] = {}
    for k in (
        "image_url",
        "description",
        "tags",
        "dimensions_mm",
        "max_dimension_mm",
        "filament_grams",
        "print_time_min",
        "recommended_filaments",
        "recommended_colors",
    ):
        if meta.get(k):
            updates[k] = meta[k]
    updated = update_model(db_path, model_id, updates)
    return jsonify(updated)


@bp.route("/api/models/<int:model_id>", methods=["PATCH", "DELETE"])
def api_model_item(model_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_model(db_path, model_id):
            return _err("Modelo não encontrado.", 404)
        return jsonify({"deleted": True, "id": model_id})

    updated = update_model(db_path, model_id, _json_body())
    if not updated:
        return _err("Modelo não encontrado.", 404)
    for pair in (
        updated.get("classifications")
        or [{"category": updated.get("category"), "subcategory": updated.get("subcategory")}]
    ):
        if pair.get("category") and pair.get("subcategory"):
            ensure_model_subcategory(db_path, pair["category"], pair["subcategory"])
    return jsonify(updated)


@bp.route("/api/seed-demo", methods=["POST"])
def api_seed_demo():
    db_path, _, _ = _get_fila3d_paths()
    demo_items = [
        {
            "url": "https://makerworld.com/en/models/120001-articulated-crystal-dragon",
            "title": "Articulated Crystal Dragon (Exemplo)",
            "filament_grams": 118,
            "dimensions_mm": "210 x 145 x 55 mm",
            "print_time_min": 215,
            "tags": ["dragon", "articulated", "ams", "flexi"],
        },
        {
            "url": "https://makerworld.com/en/models/120002-gridfinity-screw-organizer",
            "title": "Gridfinity Modular Screw Organizer (Exemplo)",
            "filament_grams": 74,
            "dimensions_mm": "126 x 84 x 42 mm",
            "print_time_min": 110,
            "tags": ["gridfinity", "organizer", "storage"],
        },
        {
            "url": "https://makerworld.com/en/models/120003-heavy-duty-headset-clamp",
            "title": "Heavy Duty Desk Headset Clamp (Exemplo)",
            "filament_grams": 48,
            "dimensions_mm": "78 x 45 x 62 mm",
            "print_time_min": 75,
            "tags": ["headset", "clamp", "desk"],
        },
    ]
    saved = [upsert_model(db_path, analyze_model_input(item, fetch_remote=False)) for item in demo_items]
    return jsonify({"count": len(saved), "items": saved})


# ---- 2. Printers ---- #


@bp.route("/api/printers", methods=["GET", "POST"])
def api_printers():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(list_printers(db_path))
    data = _json_body()
    if not str(data.get("name") or "").strip():
        return _err("Informe o apelido da impressora.", 400)
    return jsonify(create_printer(db_path, data))


@bp.route("/api/printers/<int:printer_id>", methods=["PATCH", "DELETE"])
def api_printer_item(printer_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_printer(db_path, printer_id):
            return _err("Impressora não encontrada.", 404)
        return jsonify({"deleted": True, "id": printer_id})
    updated = update_printer(db_path, printer_id, _json_body())
    if not updated:
        return _err("Impressora não encontrada.", 404)
    return jsonify(updated)


# ---- 3. Filament Spools ---- #


@bp.route("/api/spools", methods=["GET", "POST"])
def api_spools():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(
            list_spools(
                db_path,
                material=request.args.get("material", ""),
                low_only=_opt_bool("low_only", False),
            )
        )
    data = _json_body()
    if not str(data.get("color_name") or "").strip():
        return _err("Informe a cor do carretel.", 400)
    return jsonify(create_spool(db_path, data))


@bp.route("/api/spools/<int:spool_id>", methods=["PATCH", "DELETE"])
def api_spool_item(spool_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_spool(db_path, spool_id):
            return _err("Carretel não encontrado.", 404)
        return jsonify({"deleted": True, "id": spool_id})
    updated = update_spool(db_path, spool_id, _json_body())
    if not updated:
        return _err("Carretel não encontrado.", 404)
    return jsonify(updated)


# ---- 4. Print Queue ---- #


@bp.route("/api/queue", methods=["GET", "POST"])
def api_queue():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(
            list_jobs(
                db_path,
                status=request.args.get("status", ""),
                printer_id=_opt_int("printer_id"),
                unassigned_printer=_opt_bool("unassigned_printer", False),
                rubric_id=_opt_int("rubric_id"),
                rubric_name=request.args.get("rubric_name", ""),
                target_type=request.args.get("target_type", ""),
                priority=request.args.get("priority", ""),
                spool_id=_opt_int("spool_id"),
                slicing_profile_id=_opt_int("slicing_profile_id"),
                layer_height_mm=_opt_float("layer_height_mm"),
                q=request.args.get("q", ""),
                exclude_archived=_opt_bool("exclude_archived", False),
            )
        )
    data = _json_body()
    if not str(data.get("title") or "").strip():
        return _err("Informe o título da peça/trabalho.", 400)
    return jsonify(create_job(db_path, data))


@bp.route("/api/queue/<int:job_id>", methods=["PATCH", "DELETE"])
def api_queue_item(job_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_job(db_path, job_id):
            return _err("Trabalho na fila não encontrado.", 404)
        return jsonify({"deleted": True, "id": job_id})
    updated = update_job(db_path, job_id, _json_body())
    if not updated:
        return _err("Trabalho na fila não encontrado.", 404)
    return jsonify(updated)


# ---- 4b. Rubrics, Slicing Profiles & Subcategories ---- #


@bp.route("/api/rubrics", methods=["GET", "POST"])
def api_rubrics():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(list_rubrics(db_path))
    try:
        return jsonify(create_rubric(db_path, _json_body()))
    except ValueError as exc:
        return _err(str(exc), 400)


@bp.route("/api/rubrics/<int:rubric_id>", methods=["PATCH", "DELETE"])
def api_rubric_item(rubric_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_rubric(db_path, rubric_id):
            return _err("Rubrica não encontrada.", 404)
        return jsonify({"deleted": True, "id": rubric_id})
    try:
        updated = update_rubric(db_path, rubric_id, _json_body())
    except ValueError as exc:
        return _err(str(exc), 400)
    if not updated:
        return _err("Rubrica não encontrada.", 404)
    return jsonify(updated)


@bp.route("/api/slicing-profiles", methods=["GET", "POST"])
def api_slicing_profiles():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(list_slicing_profiles(db_path))
    return jsonify(create_slicing_profile(db_path, _json_body()))


@bp.route("/api/slicing-profiles/<int:profile_id>", methods=["PATCH", "DELETE"])
def api_slicing_profile_item(profile_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_slicing_profile(db_path, profile_id):
            return _err("Perfil de fatiamento não encontrado.", 404)
        return jsonify({"deleted": True, "id": profile_id})
    try:
        updated = update_slicing_profile(db_path, profile_id, _json_body())
    except ValueError as exc:
        return _err(str(exc), 400)
    if not updated:
        return _err("Perfil de fatiamento não encontrado.", 404)
    return jsonify(updated)


@bp.route("/api/subcategories", methods=["GET", "POST"])
def api_subcategories():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(
            list_subcategories(
                db_path,
                scope=request.args.get("scope", ""),
                category=request.args.get("category", ""),
            )
        )
    try:
        return jsonify(create_subcategory(db_path, _json_body()))
    except ValueError as exc:
        return _err(str(exc), 400)


@bp.route("/api/subcategories/<int:sub_id>", methods=["PATCH", "DELETE"])
def api_subcategory_item(sub_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_subcategory(db_path, sub_id, reassign_to=request.args.get("reassign_to", "")):
            return _err("Subcategoria não encontrada.", 404)
        return jsonify({"deleted": True, "id": sub_id})
    try:
        updated = update_subcategory(db_path, sub_id, _json_body())
    except ValueError as exc:
        return _err(str(exc), 400)
    if not updated:
        return _err("Subcategoria não encontrada.", 404)
    return jsonify(updated)


@bp.route("/api/subcategories/reclassify", methods=["POST"])
def api_subcategories_reclassify():
    db_path, _, _ = _get_fila3d_paths()
    return jsonify({"ok": True, **reclassify_all_items(db_path)})


# ---- 5. Sales Catalog & Orders ---- #


@bp.route("/api/catalog", methods=["GET", "POST"])
def api_catalog():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(
            list_catalog_items(
                db_path,
                category=request.args.get("category", ""),
                subcategory=request.args.get("subcategory", ""),
                q=request.args.get("q", ""),
                in_stock_only=_opt_bool("in_stock_only", False),
            )
        )
    data = _json_body()
    if not str(data.get("name") or "").strip():
        return _err("Informe o nome do produto.", 400)
    saved = create_catalog_item(db_path, data)
    for pair in saved.get("classifications") or []:
        if pair.get("category") and pair.get("subcategory"):
            ensure_subcategory_entry(db_path, "sales_catalog", pair["category"], pair["subcategory"])
    return jsonify(saved)


@bp.route("/api/catalog/import-ita-arte", methods=["POST"])
def api_catalog_import_ita_arte():
    db_path, media_path, _ = _get_fila3d_paths()
    count = import_ita_arte_catalog(db_path, media_path)
    return jsonify({"imported": count})


@bp.route("/api/catalog/<int:item_id>", methods=["PATCH", "DELETE"])
def api_catalog_item(item_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_catalog_item(db_path, item_id):
            return _err("Produto não encontrado.", 404)
        return jsonify({"deleted": True, "id": item_id})
    updated = update_catalog_item(db_path, item_id, _json_body())
    if not updated:
        return _err("Produto não encontrado no catálogo.", 404)
    for pair in updated.get("classifications") or []:
        if pair.get("category") and pair.get("subcategory"):
            ensure_subcategory_entry(db_path, "sales_catalog", pair["category"], pair["subcategory"])
    return jsonify(updated)


@bp.route("/api/sales", methods=["GET", "POST"])
def api_sales():
    db_path, _, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(list_sales(db_path))
    return jsonify(create_sale(db_path, _json_body()))


@bp.route("/api/sales/<int:sale_id>", methods=["DELETE"])
def api_sale_item(sale_id: int):
    db_path, _, _ = _get_fila3d_paths()
    if not delete_sale(db_path, sale_id):
        return _err("Venda não encontrada.", 404)
    return jsonify({"deleted": True, "id": sale_id})


# ---- 6. Media & Instagram Studio ---- #


@bp.route("/api/media", methods=["GET", "POST"])
def api_media():
    db_path, media_path, _ = _get_fila3d_paths()
    if request.method == "GET":
        return jsonify(
            list_media_posts(
                db_path,
                status=request.args.get("status", ""),
                post_format=request.args.get("post_format", ""),
            )
        )

    if request.form or request.files or (request.content_type and "multipart/form-data" in request.content_type):
        form = request.form
        file = request.files.get("file")
        image_url = (form.get("image_url") or "").strip()
        title = form.get("title") or ""
        model_id = int(form["model_id"]) if (form.get("model_id") or "").strip().isdigit() else None
        print_job_id = int(form["print_job_id"]) if (form.get("print_job_id") or "").strip().isdigit() else None
        catalog_item_id = int(form["catalog_item_id"]) if (form.get("catalog_item_id") or "").strip().isdigit() else None
        post_format = form.get("post_format") or "Feed"
        status = form.get("status") or "Banco de Fotos"
        caption = form.get("caption") or ""
        hashtags = form.get("hashtags") or ""
        scheduled_date = form.get("scheduled_date") or ""
        notes = form.get("notes") or ""
    else:
        body = _json_body()
        file = None
        image_url = str(body.get("image_url") or "").strip()
        title = str(body.get("title") or "")
        model_id = body.get("model_id")
        print_job_id = body.get("print_job_id")
        catalog_item_id = body.get("catalog_item_id")
        post_format = str(body.get("post_format") or "Feed")
        status = str(body.get("status") or "Banco de Fotos")
        caption = str(body.get("caption") or "")
        hashtags = str(body.get("hashtags") or "")
        scheduled_date = str(body.get("scheduled_date") or "")
        notes = str(body.get("notes") or "")

    if image_url:
        if not (image_url.startswith("http://") or image_url.startswith("https://") or image_url.startswith("/media/")):
            return _err("Link de imagem inválido. Use URL http://, https:// ou /media/...", 400)
        safe_filename = ""
        final_url = image_url
        fallback_title = Path(image_url.split("?")[0]).stem.replace("_", " ").replace("-", " ").title() or "Foto de Impressão"
    elif file is not None and (file.filename or ""):
        orig_name = file.filename or "foto.png"
        ext = Path(orig_name).suffix.lower() or ".png"
        if ext not in _ALLOWED_IMAGE_EXTS:
            return _err("Formato de imagem não suportado. Use PNG, JPG, WEBP ou GIF.", 400)
        stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(orig_name).stem).strip("_") or "peca"
        safe_filename = f"posts/{uuid4().hex[:10]}_{stem}{ext}"
        dest = media_path / safe_filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        file.save(dest)
        final_url = f"/media/{safe_filename}"
        fallback_title = stem.replace("_", " ").title()
    else:
        return _err("Informe o link da imagem (URL) ou selecione um arquivo.", 400)

    return jsonify(
        create_media_post(
            db_path,
            {
                "filename": safe_filename,
                "file_url": final_url,
                "title": title or fallback_title,
                "model_id": model_id,
                "print_job_id": print_job_id,
                "catalog_item_id": catalog_item_id,
                "post_format": post_format,
                "status": status,
                "caption": caption,
                "hashtags": hashtags,
                "scheduled_date": scheduled_date,
                "notes": notes,
            },
        )
    )


@bp.route("/api/media/generate-caption", methods=["POST"])
def api_generate_caption():
    _get_fila3d_paths()
    payload = _json_body()
    price = payload.get("price_brl")
    return jsonify(
        generate_instagram_caption(
            title=str(payload.get("title") or ""),
            category=str(payload.get("category") or ""),
            price_brl=float(price) if price not in (None, "") else None,
            notes=str(payload.get("notes") or ""),
        )
    )


@bp.route("/api/media/<int:media_id>", methods=["PATCH", "DELETE"])
def api_media_item(media_id: int):
    db_path, media_path, _ = _get_fila3d_paths()
    if request.method == "DELETE":
        if not delete_media_post(db_path, media_id, media_path):
            return _err("Mídia não encontrada.", 404)
        return jsonify({"deleted": True, "id": media_id})
    updated = update_media_post(db_path, media_id, _json_body())
    if not updated:
        return _err("Mídia não encontrada.", 404)
    return jsonify(updated)
