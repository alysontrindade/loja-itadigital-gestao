from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from urllib.parse import unquote

from app.fila3d.analyzer import (
    DEFAULT_MODEL_SUBCATEGORIES,
    classify_model_classifications,
    classify_model_subcategory,
    normalize_classifications,
)
from app.fila3d.database import _connect, load_classifications_map, sync_item_classifications

PRINTER_STATUSES = ["Disponível", "Imprimindo", "Pausada", "Manutenção"]
JOB_STATUSES = ["Pendente", "Em Impressão", "Concluída", "Falhou", "Cancelada", "Arquivado"]
JOB_PRIORITIES = ["Baixa", "Normal", "Alta", "Urgente"]
JOB_TARGETS = ["Encomenda", "Estoque", "Teste / Pessoal"]
POST_FORMATS = ["Feed", "Carrossel", "Reels", "Stories"]
POST_STATUSES = ["Banco de Fotos", "Legenda Pronta", "Agendado", "Postado"]
SALE_CHANNELS = ["Instagram", "WhatsApp", "Shopee / ML", "Presencial", "Outro"]
PAYMENT_STATUSES = ["Pendente", "Sinal 50%", "Pago"]
SUBCATEGORY_SCOPES = ("sales_catalog", "models")

DEFAULT_SUBCATEGORIES: dict[str, dict[str, list[str]]] = {
    "sales_catalog": {
        "Direito & Advocacia": [
            "Porta-Cartões & Organizadores",
            "Estátuas Têmis & Balança",
            "Malhetes & Carimbos",
            "Acessórios de Mesa",
        ],
        "Medicina": ["Símbolos & Estátuas", "Consultório & Mesa"],
        "Decoração": ["Esculturas & Bustos", "Vasos & Luminárias"],
    },
    "models": DEFAULT_MODEL_SUBCATEGORIES,
}

DEFAULT_ITA_ARTE_DIR = Path(r"H:\Meu Drive\ANTIGRAVITY\catalogo-ita-arte-3d")

DEFAULT_SLICING_PROFILES: list[tuple[str, float, str, int]] = [
    ("0.08 mm — Extra Fino", 0.08, "Altíssima definição para miniaturas, rostos e detalhes finos.", 0),
    ("0.12 mm — Fino", 0.12, "Ótimo acabamento superficial com bom equilíbrio de tempo.", 0),
    ("0.16 mm — Ótimo", 0.16, "Camadas discretas para peças decorativas e bustos.", 0),
    ("0.20 mm — Padrão", 0.20, "Perfil padrão equilibrado (velocidade × resistência).", 1),
    ("0.24 mm — Rascunho", 0.24, "Mais rápido para peças funcionais e suportes.", 0),
    ("0.28 mm — Extra Rascunho", 0.28, "Impressão rápida para organizadores e protótipos.", 0),
    ("0.32 mm — Rápido / Estrutural", 0.32, "Camada alta para peças grandes e alta vazão.", 0),
]

DEFAULT_RUBRICS: list[tuple[str, str, str]] = [
    ("Encomendas Gerais", "#22d3ee", "Pedidos sob encomenda para clientes."),
    ("Estoque Pronta Entrega", "#34d399", "Reposição de catálogo e estoque físico."),
    ("Testes & Calibração", "#a78bfa", "Protótipos, torres e calibração de filamento."),
]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def init_hub_db(db_path: Path | str) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS printers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand_model TEXT NOT NULL DEFAULT 'Bambu Lab A1',
                build_volume_mm TEXT NOT NULL DEFAULT '256 x 256 x 256 mm',
                max_dim_mm REAL NOT NULL DEFAULT 256.0,
                nozzle_mm REAL NOT NULL DEFAULT 0.4,
                has_ams INTEGER NOT NULL DEFAULT 1,
                ams_slots INTEGER NOT NULL DEFAULT 4,
                ams_mapping_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'Disponível',
                hourly_cost_brl REAL NOT NULL DEFAULT 2.5,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS filament_spools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL DEFAULT '',
                material TEXT NOT NULL DEFAULT 'PLA+',
                color_name TEXT NOT NULL,
                color_hex TEXT NOT NULL DEFAULT '#171717',
                initial_grams REAL NOT NULL DEFAULT 1000.0,
                remaining_grams REAL NOT NULL DEFAULT 1000.0,
                min_alert_grams REAL NOT NULL DEFAULT 150.0,
                cost_per_kg_brl REAL NOT NULL DEFAULT 120.0,
                location TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sales_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL DEFAULT '',
                model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Outros',
                subcategory TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                dimensions_cm TEXT NOT NULL DEFAULT '',
                filament_grams REAL NOT NULL DEFAULT 0.0,
                filament_cost_per_kg_brl REAL NOT NULL DEFAULT 120.0,
                energy_and_wear_brl REAL NOT NULL DEFAULT 0.0,
                extras_cost_brl REAL NOT NULL DEFAULT 0.0,
                pricing_mode TEXT NOT NULL DEFAULT 'rate_per_gram',
                rate_per_gram_brl REAL NOT NULL DEFAULT 0.40,
                margin_percent REAL NOT NULL DEFAULT 150.0,
                sale_price_brl REAL NOT NULL DEFAULT 0.0,
                stock_qty INTEGER NOT NULL DEFAULT 0,
                min_stock_alert INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
                printer_id INTEGER REFERENCES printers(id) ON DELETE SET NULL,
                spool_id INTEGER REFERENCES filament_spools(id) ON DELETE SET NULL,
                catalog_item_id INTEGER REFERENCES sales_catalog(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT 'Encomenda',
                customer_name TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 1,
                estimated_grams REAL NOT NULL DEFAULT 0.0,
                actual_grams_used REAL,
                estimated_time_min INTEGER,
                priority TEXT NOT NULL DEFAULT 'Normal',
                color_choice TEXT NOT NULL DEFAULT '',
                material_choice TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pendente',
                failure_reason TEXT NOT NULL DEFAULT '',
                filament_deducted INTEGER NOT NULL DEFAULT 0,
                stock_added INTEGER NOT NULL DEFAULT 0,
                scheduled_for TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                finished_at TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sales_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_item_id INTEGER REFERENCES sales_catalog(id) ON DELETE SET NULL,
                item_name TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                channel TEXT NOT NULL DEFAULT 'Instagram',
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price_brl REAL NOT NULL DEFAULT 0.0,
                total_price_brl REAL NOT NULL DEFAULT 0.0,
                payment_status TEXT NOT NULL DEFAULT 'Pendente',
                fulfillment_status TEXT NOT NULL DEFAULT 'Pronta Entrega',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS media_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
                print_job_id INTEGER REFERENCES print_jobs(id) ON DELETE SET NULL,
                catalog_item_id INTEGER REFERENCES sales_catalog(id) ON DELETE SET NULL,
                post_format TEXT NOT NULL DEFAULT 'Feed',
                status TEXT NOT NULL DEFAULT 'Banco de Fotos',
                caption TEXT NOT NULL DEFAULT '',
                hashtags TEXT NOT NULL DEFAULT '',
                scheduled_date TEXT NOT NULL DEFAULT '',
                posted_at TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS catalog_subcategories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL DEFAULT 'sales_catalog',
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope, category, name)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON print_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_printer ON print_jobs(printer_id);
            CREATE INDEX IF NOT EXISTS idx_catalog_cat ON sales_catalog(category);
            CREATE INDEX IF NOT EXISTS idx_media_status ON media_posts(status);
            CREATE INDEX IF NOT EXISTS idx_subcats_scope_cat ON catalog_subcategories(scope, category);
            """
        )
        cat_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sales_catalog)").fetchall()}
        if "subcategory" not in cat_cols:
            conn.execute("ALTER TABLE sales_catalog ADD COLUMN subcategory TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_subcat ON sales_catalog(subcategory)")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS print_rubrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color_hex TEXT NOT NULL DEFAULT '#22d3ee',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS slicing_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                layer_height_mm REAL NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS item_classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                UNIQUE(scope, item_id, category, subcategory)
            );
            CREATE INDEX IF NOT EXISTS idx_item_class_scope_item ON item_classifications(scope, item_id);
            CREATE INDEX IF NOT EXISTS idx_item_class_scope_cat_sub ON item_classifications(scope, category, subcategory);
            """
        )
        job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(print_jobs)").fetchall()}
        if "rubric_id" not in job_cols:
            conn.execute("ALTER TABLE print_jobs ADD COLUMN rubric_id INTEGER REFERENCES print_rubrics(id) ON DELETE SET NULL")
        if "rubric_name" not in job_cols:
            conn.execute("ALTER TABLE print_jobs ADD COLUMN rubric_name TEXT NOT NULL DEFAULT ''")
        if "slicing_profile_id" not in job_cols:
            conn.execute("ALTER TABLE print_jobs ADD COLUMN slicing_profile_id INTEGER REFERENCES slicing_profiles(id) ON DELETE SET NULL")
        if "layer_height_mm" not in job_cols:
            conn.execute("ALTER TABLE print_jobs ADD COLUMN layer_height_mm REAL")
        if "slicing_notes" not in job_cols:
            conn.execute("ALTER TABLE print_jobs ADD COLUMN slicing_notes TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_rubric ON print_jobs(rubric_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_slicing ON print_jobs(slicing_profile_id)")

        now = _now_iso()
        if conn.execute("SELECT COUNT(*) FROM slicing_profiles").fetchone()[0] == 0:
            for pname, height, pnotes, is_def in DEFAULT_SLICING_PROFILES:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO slicing_profiles (name, layer_height_mm, notes, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (pname, height, pnotes, is_def, now, now),
                )
        if conn.execute("SELECT COUNT(*) FROM print_rubrics").fetchone()[0] == 0:
            for rname, rcolor, rnotes in DEFAULT_RUBRICS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO print_rubrics (name, color_hex, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (rname, rcolor, rnotes, now, now),
                )
        conn.execute(
            """
            INSERT OR IGNORE INTO item_classifications (scope, item_id, category, subcategory, sort_order)
            SELECT 'sales_catalog', id, category, COALESCE(subcategory, ''), 0
            FROM sales_catalog s
            WHERE category != ''
              AND NOT EXISTS (
                  SELECT 1 FROM item_classifications ic WHERE ic.scope = 'sales_catalog' AND ic.item_id = s.id
              )
            """
        )
        conn.commit()


def _printer_row(row: sqlite3.Row, active_count: int = 0, queued_count: int = 0) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "brand_model": row["brand_model"],
        "build_volume_mm": row["build_volume_mm"],
        "max_dim_mm": row["max_dim_mm"],
        "nozzle_mm": row["nozzle_mm"],
        "has_ams": bool(row["has_ams"]),
        "ams_slots": row["ams_slots"],
        "ams_mapping": json.loads(row["ams_mapping_json"] or "[]"),
        "status": row["status"],
        "hourly_cost_brl": row["hourly_cost_brl"],
        "notes": row["notes"],
        "active_jobs_count": active_count,
        "queued_jobs_count": queued_count,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _spool_row(row: sqlite3.Row) -> dict[str, Any]:
    rem = float(row["remaining_grams"] or 0.0)
    alert = float(row["min_alert_grams"] or 0.0)
    init_g = max(float(row["initial_grams"] or 1000.0), 1.0)
    return {
        "id": row["id"],
        "brand": row["brand"],
        "material": row["material"],
        "color_name": row["color_name"],
        "color_hex": row["color_hex"],
        "initial_grams": float(row["initial_grams"] or 0.0),
        "remaining_grams": round(rem, 1),
        "min_alert_grams": alert,
        "cost_per_kg_brl": float(row["cost_per_kg_brl"] or 0.0),
        "estimated_value_brl": round((rem / 1000.0) * float(row["cost_per_kg_brl"] or 0.0), 2),
        "percent_remaining": round(max(0.0, min(100.0, (rem / init_g) * 100.0)), 1),
        "is_low_stock": rem <= alert,
        "location": row["location"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def compute_sale_price(data: dict[str, Any]) -> dict[str, float]:
    grams = float(data.get("filament_grams") or 0.0)
    kg_cost = float(data.get("filament_cost_per_kg_brl") or 120.0)
    energy = float(data.get("energy_and_wear_brl") or 0.0)
    extras = float(data.get("extras_cost_brl") or 0.0)
    unit_cost = round((grams / 1000.0) * kg_cost + energy + extras, 2)

    mode = str(data.get("pricing_mode") or "rate_per_gram")
    rate = float(data.get("rate_per_gram_brl") if data.get("rate_per_gram_brl") is not None else 0.40)
    margin = float(data.get("margin_percent") if data.get("margin_percent") is not None else 150.0)

    if mode == "manual" and data.get("sale_price_brl") is not None:
        sale_price = round(float(data["sale_price_brl"]), 2)
    elif mode == "cost_markup":
        sale_price = round(unit_cost * (1.0 + margin / 100.0), 2)
    else:
        sale_price = round(grams * rate + extras, 2)

    profit = round(sale_price - unit_cost, 2)
    return {
        "unit_cost_brl": unit_cost,
        "sale_price_brl": sale_price,
        "estimated_profit_brl": profit,
    }


def _catalog_row(row: sqlite3.Row, classifications: list[dict[str, str]] | None = None) -> dict[str, Any]:
    raw = dict(row)
    costs = compute_sale_price(raw)
    qty = int(row["stock_qty"] or 0)
    alert = int(row["min_stock_alert"] or 0)
    primary_cat = row["category"]
    primary_sub = row["subcategory"] if "subcategory" in row.keys() else ""
    cls_list = normalize_classifications(
        classifications if classifications is not None and len(classifications) > 0 else None,
        category=primary_cat,
        subcategory=primary_sub,
        default_category="",
    )
    cats = list(dict.fromkeys(c["category"] for c in cls_list if c["category"]))
    subs = list(dict.fromkeys(c["subcategory"] for c in cls_list if c["subcategory"]))
    return {
        "id": row["id"],
        "code": row["code"],
        "model_id": row["model_id"],
        "name": row["name"],
        "category": cls_list[0]["category"] if cls_list else primary_cat,
        "subcategory": cls_list[0]["subcategory"] if cls_list else primary_sub,
        "categories": cats,
        "subcategories": subs,
        "classifications": cls_list,
        "source_url": row["source_url"],
        "image_url": row["image_url"],
        "dimensions_cm": row["dimensions_cm"],
        "filament_grams": float(row["filament_grams"] or 0.0),
        "filament_cost_per_kg_brl": float(row["filament_cost_per_kg_brl"] or 0.0),
        "energy_and_wear_brl": float(row["energy_and_wear_brl"] or 0.0),
        "extras_cost_brl": float(row["extras_cost_brl"] or 0.0),
        "pricing_mode": row["pricing_mode"],
        "rate_per_gram_brl": float(row["rate_per_gram_brl"] or 0.40),
        "margin_percent": float(row["margin_percent"] or 150.0),
        "sale_price_brl": float(row["sale_price_brl"] or costs["sale_price_brl"]),
        "unit_cost_brl": costs["unit_cost_brl"],
        "estimated_profit_brl": round(float(row["sale_price_brl"] or costs["sale_price_brl"]) - costs["unit_cost_brl"], 2),
        "stock_qty": qty,
        "min_stock_alert": alert,
        "is_low_stock": qty <= alert,
        "active": bool(row["active"]),
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _job_row(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    rubric_name = (
        row["rubric_name_resolved"]
        if "rubric_name_resolved" in keys and row["rubric_name_resolved"]
        else (row["rubric_name"] if "rubric_name" in keys and row["rubric_name"] else "")
    )
    rubric_color = row["rubric_color"] if "rubric_color" in keys and row["rubric_color"] else "#22d3ee"
    slicing_profile_name = row["slicing_profile_name"] if "slicing_profile_name" in keys and row["slicing_profile_name"] else ""
    layer_height = row["layer_height_resolved"] if "layer_height_resolved" in keys else (row["layer_height_mm"] if "layer_height_mm" in keys else None)
    spool_rem = row["spool_remaining_grams"] if "spool_remaining_grams" in keys else None
    est_g = float(row["estimated_grams"] or 0.0)
    filament_ok = True if spool_rem is None else (float(spool_rem) >= est_g)
    return {
        "id": row["id"],
        "model_id": row["model_id"],
        "printer_id": row["printer_id"],
        "spool_id": row["spool_id"],
        "catalog_item_id": row["catalog_item_id"],
        "rubric_id": row["rubric_id"] if "rubric_id" in keys else None,
        "rubric_name": rubric_name,
        "rubric_color": rubric_color,
        "slicing_profile_id": row["slicing_profile_id"] if "slicing_profile_id" in keys else None,
        "slicing_profile_name": slicing_profile_name,
        "layer_height_mm": float(layer_height) if layer_height is not None else None,
        "slicing_notes": row["slicing_notes"] if "slicing_notes" in keys and row["slicing_notes"] else "",
        "printer_name": row["printer_name"] if "printer_name" in keys and row["printer_name"] else "",
        "spool_label": row["spool_label"] if "spool_label" in keys and row["spool_label"] else "",
        "spool_remaining_grams": float(spool_rem) if spool_rem is not None else None,
        "filament_ok": filament_ok,
        "catalog_name": row["catalog_name"] if "catalog_name" in keys and row["catalog_name"] else "",
        "model_title": row["model_title"] if "model_title" in keys and row["model_title"] else "",
        "title": row["title"],
        "target_type": row["target_type"],
        "customer_name": row["customer_name"],
        "quantity": int(row["quantity"] or 1),
        "estimated_grams": est_g,
        "actual_grams_used": row["actual_grams_used"],
        "estimated_time_min": row["estimated_time_min"],
        "priority": row["priority"],
        "color_choice": row["color_choice"],
        "material_choice": row["material_choice"],
        "status": row["status"],
        "failure_reason": row["failure_reason"],
        "filament_deducted": bool(row["filament_deducted"]),
        "stock_added": bool(row["stock_added"]),
        "scheduled_for": row["scheduled_for"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _sale_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "catalog_item_id": row["catalog_item_id"],
        "item_name": row["item_name"],
        "customer_name": row["customer_name"],
        "channel": row["channel"],
        "quantity": int(row["quantity"] or 1),
        "unit_price_brl": float(row["unit_price_brl"] or 0.0),
        "total_price_brl": float(row["total_price_brl"] or 0.0),
        "payment_status": row["payment_status"],
        "fulfillment_status": row["fulfillment_status"],
        "notes": row["notes"],
        "created_at": row["created_at"],
    }


def _media_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "file_url": row["file_url"],
        "title": row["title"],
        "model_id": row["model_id"],
        "print_job_id": row["print_job_id"],
        "catalog_item_id": row["catalog_item_id"],
        "post_format": row["post_format"],
        "status": row["status"],
        "caption": row["caption"],
        "hashtags": row["hashtags"],
        "scheduled_date": row["scheduled_date"],
        "posted_at": row["posted_at"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ---------------- Printers ---------------- #

def list_printers(db_path: Path | str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM printers ORDER BY id ASC").fetchall()
        counts = conn.execute(
            """
            SELECT printer_id,
                   SUM(CASE WHEN status = 'Em Impressão' THEN 1 ELSE 0 END) AS active_cnt,
                   SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END) AS queued_cnt
            FROM print_jobs
            WHERE printer_id IS NOT NULL
            GROUP BY printer_id
            """
        ).fetchall()
    by_pid = {r["printer_id"]: (int(r["active_cnt"] or 0), int(r["queued_cnt"] or 0)) for r in counts}
    items = [_printer_row(r, *by_pid.get(r["id"], (0, 0))) for r in rows]
    return {"items": items, "total": len(items)}


def create_printer(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    ams_slots = int(data.get("ams_slots") if data.get("ams_slots") is not None else (4 if data.get("has_ams", True) else 0))
    ams_mapping = data.get("ams_mapping") or [{"slot": i + 1, "label": f"Slot {i + 1}", "color": ""} for i in range(ams_slots)]
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO printers (
                name, brand_model, build_volume_mm, max_dim_mm, nozzle_mm,
                has_ams, ams_slots, ams_mapping_json, status, hourly_cost_brl,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(data["name"]).strip(),
                str(data.get("brand_model") or "Bambu Lab A1").strip(),
                str(data.get("build_volume_mm") or "256 x 256 x 256 mm").strip(),
                float(data.get("max_dim_mm") or 256.0),
                float(data.get("nozzle_mm") or 0.4),
                1 if data.get("has_ams", True) else 0,
                ams_slots,
                json.dumps(ams_mapping, ensure_ascii=False),
                str(data.get("status") or "Disponível"),
                float(data.get("hourly_cost_brl") or 2.5),
                str(data.get("notes") or ""),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM printers WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _printer_row(row)


def update_printer(db_path: Path | str, printer_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM printers WHERE id = ?", (printer_id,)).fetchone()
        if not row:
            return None
        cur_data = _printer_row(row)
        merged = {**cur_data, **updates}
        ams_slots = int(merged.get("ams_slots") or 0)
        conn.execute(
            """
            UPDATE printers SET
                name = ?, brand_model = ?, build_volume_mm = ?, max_dim_mm = ?,
                nozzle_mm = ?, has_ams = ?, ams_slots = ?, ams_mapping_json = ?,
                status = ?, hourly_cost_brl = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["name"],
                merged["brand_model"],
                merged["build_volume_mm"],
                float(merged["max_dim_mm"]),
                float(merged["nozzle_mm"]),
                1 if merged["has_ams"] else 0,
                ams_slots,
                json.dumps(merged.get("ams_mapping") or [], ensure_ascii=False),
                merged["status"],
                float(merged["hourly_cost_brl"]),
                merged.get("notes") or "",
                _now_iso(),
                printer_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM printers WHERE id = ?", (printer_id,)).fetchone()
    return _printer_row(updated)


def delete_printer(db_path: Path | str, printer_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM printers WHERE id = ?", (printer_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------- Filament Spools ---------------- #

def list_spools(db_path: Path | str, material: str = "", low_only: bool = False) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM filament_spools ORDER BY remaining_grams ASC, id DESC").fetchall()
    items = [_spool_row(r) for r in rows]
    if material:
        items = [i for i in items if i["material"] == material]
    if low_only:
        items = [i for i in items if i["is_low_stock"]]
    total_grams = round(sum(i["remaining_grams"] for i in items), 1)
    total_value = round(sum(i["estimated_value_brl"] for i in items), 2)
    low_count = sum(1 for i in items if i["is_low_stock"])
    return {
        "items": items,
        "total": len(items),
        "total_remaining_grams": total_grams,
        "total_value_brl": total_value,
        "low_stock_count": low_count,
    }


def create_spool(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    initial = float(data.get("initial_grams") or 1000.0)
    remaining = float(data["remaining_grams"]) if data.get("remaining_grams") is not None else initial
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO filament_spools (
                brand, material, color_name, color_hex, initial_grams, remaining_grams,
                min_alert_grams, cost_per_kg_brl, location, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(data.get("brand") or "").strip(),
                str(data.get("material") or "PLA+").strip(),
                str(data["color_name"]).strip(),
                str(data.get("color_hex") or "#171717").strip(),
                initial,
                max(0.0, remaining),
                float(data.get("min_alert_grams") if data.get("min_alert_grams") is not None else 150.0),
                float(data.get("cost_per_kg_brl") if data.get("cost_per_kg_brl") is not None else 120.0),
                str(data.get("location") or "").strip(),
                str(data.get("notes") or "").strip(),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM filament_spools WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _spool_row(row)


def update_spool(db_path: Path | str, spool_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM filament_spools WHERE id = ?", (spool_id,)).fetchone()
        if not row:
            return None
        merged = {**_spool_row(row), **updates}
        conn.execute(
            """
            UPDATE filament_spools SET
                brand = ?, material = ?, color_name = ?, color_hex = ?,
                initial_grams = ?, remaining_grams = ?, min_alert_grams = ?,
                cost_per_kg_brl = ?, location = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["brand"],
                merged["material"],
                merged["color_name"],
                merged["color_hex"],
                float(merged["initial_grams"]),
                max(0.0, float(merged["remaining_grams"])),
                float(merged["min_alert_grams"]),
                float(merged["cost_per_kg_brl"]),
                merged.get("location") or "",
                merged.get("notes") or "",
                _now_iso(),
                spool_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM filament_spools WHERE id = ?", (spool_id,)).fetchone()
    return _spool_row(updated)


def delete_spool(db_path: Path | str, spool_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM filament_spools WHERE id = ?", (spool_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------- Rubrics & Slicing Profiles ---------------- #


def list_rubrics(db_path: Path | str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT r.*, COUNT(j.id) AS jobs_count
            FROM print_rubrics r
            LEFT JOIN print_jobs j ON j.rubric_id = r.id AND j.status != 'Arquivado'
            GROUP BY r.id
            ORDER BY r.name COLLATE NOCASE ASC
            """
        ).fetchall()
    items = [
        {
            "id": r["id"],
            "name": r["name"],
            "color_hex": r["color_hex"] or "#22d3ee",
            "notes": r["notes"] or "",
            "jobs_count": int(r["jobs_count"] or 0),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


def create_rubric(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("Nome da rubrica é obrigatório.")
    now = _now_iso()
    color_hex = str(data.get("color_hex") or "#22d3ee").strip() or "#22d3ee"
    notes = str(data.get("notes") or "").strip()
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM print_rubrics WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        if existing:
            return {
                "id": existing["id"],
                "name": existing["name"],
                "color_hex": existing["color_hex"],
                "notes": existing["notes"],
                "jobs_count": 0,
                "created_at": existing["created_at"],
                "updated_at": existing["updated_at"],
            }
        cur = conn.execute(
            """
            INSERT INTO print_rubrics (name, color_hex, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, color_hex, notes, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM print_rubrics WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {
        "id": row["id"],
        "name": row["name"],
        "color_hex": row["color_hex"],
        "notes": row["notes"],
        "jobs_count": 0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_rubric(db_path: Path | str, rubric_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    now = _now_iso()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM print_rubrics WHERE id = ?", (rubric_id,)).fetchone()
        if not row:
            return None
        new_name = str(updates.get("name") if updates.get("name") is not None else row["name"]).strip()
        if not new_name:
            raise ValueError("Nome da rubrica é obrigatório.")
        new_color = str(updates.get("color_hex") if updates.get("color_hex") is not None else row["color_hex"]).strip() or "#22d3ee"
        new_notes = str(updates.get("notes") if updates.get("notes") is not None else row["notes"]).strip()
        conn.execute(
            "UPDATE print_rubrics SET name = ?, color_hex = ?, notes = ?, updated_at = ? WHERE id = ?",
            (new_name, new_color, new_notes, now, rubric_id),
        )
        conn.execute(
            "UPDATE print_jobs SET rubric_name = ?, updated_at = ? WHERE rubric_id = ?",
            (new_name, now, rubric_id),
        )
        conn.commit()
        updated = conn.execute(
            """
            SELECT r.*, COUNT(j.id) AS jobs_count
            FROM print_rubrics r
            LEFT JOIN print_jobs j ON j.rubric_id = r.id AND j.status != 'Arquivado'
            WHERE r.id = ?
            GROUP BY r.id
            """,
            (rubric_id,),
        ).fetchone()
    return {
        "id": updated["id"],
        "name": updated["name"],
        "color_hex": updated["color_hex"],
        "notes": updated["notes"],
        "jobs_count": int(updated["jobs_count"] or 0),
        "created_at": updated["created_at"],
        "updated_at": updated["updated_at"],
    }


def delete_rubric(db_path: Path | str, rubric_id: int) -> bool:
    with _connect(db_path) as conn:
        conn.execute("UPDATE print_jobs SET rubric_id = NULL WHERE rubric_id = ?", (rubric_id,))
        cur = conn.execute("DELETE FROM print_rubrics WHERE id = ?", (rubric_id,))
        conn.commit()
        return cur.rowcount > 0


def list_slicing_profiles(db_path: Path | str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM slicing_profiles ORDER BY layer_height_mm ASC, name ASC"
        ).fetchall()
    items = [
        {
            "id": r["id"],
            "name": r["name"],
            "layer_height_mm": float(r["layer_height_mm"]),
            "notes": r["notes"] or "",
            "is_default": bool(r["is_default"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


def create_slicing_profile(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    layer = float(data.get("layer_height_mm") or 0.20)
    if not name:
        name = f"{layer:.2f} mm — Personalizado"
    now = _now_iso()
    notes = str(data.get("notes") or "").strip()
    is_default = 1 if data.get("is_default") else 0
    with _connect(db_path) as conn:
        if is_default:
            conn.execute("UPDATE slicing_profiles SET is_default = 0")
        cur = conn.execute(
            """
            INSERT INTO slicing_profiles (name, layer_height_mm, notes, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, layer, notes, is_default, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM slicing_profiles WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {
        "id": row["id"],
        "name": row["name"],
        "layer_height_mm": float(row["layer_height_mm"]),
        "notes": row["notes"] or "",
        "is_default": bool(row["is_default"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_slicing_profile(db_path: Path | str, profile_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    now = _now_iso()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM slicing_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return None
        new_name = str(updates.get("name") if updates.get("name") is not None else row["name"]).strip()
        if not new_name:
            raise ValueError("Nome do perfil de fatiamento é obrigatório.")
        new_layer = float(updates["layer_height_mm"]) if updates.get("layer_height_mm") is not None else float(row["layer_height_mm"])
        new_notes = str(updates.get("notes") if updates.get("notes") is not None else row["notes"]).strip()
        is_def = bool(updates["is_default"]) if updates.get("is_default") is not None else bool(row["is_default"])
        if is_def:
            conn.execute("UPDATE slicing_profiles SET is_default = 0")
        conn.execute(
            """
            UPDATE slicing_profiles
            SET name = ?, layer_height_mm = ?, notes = ?, is_default = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_name, new_layer, new_notes, 1 if is_def else 0, now, profile_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM slicing_profiles WHERE id = ?", (profile_id,)).fetchone()
    return {
        "id": updated["id"],
        "name": updated["name"],
        "layer_height_mm": float(updated["layer_height_mm"]),
        "notes": updated["notes"] or "",
        "is_default": bool(updated["is_default"]),
        "created_at": updated["created_at"],
        "updated_at": updated["updated_at"],
    }


def delete_slicing_profile(db_path: Path | str, profile_id: int) -> bool:
    with _connect(db_path) as conn:
        conn.execute("UPDATE print_jobs SET slicing_profile_id = NULL WHERE slicing_profile_id = ?", (profile_id,))
        cur = conn.execute("DELETE FROM slicing_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------- Print Queue ---------------- #

_JOB_SELECT = """
SELECT j.*,
       p.name AS printer_name,
       CASE WHEN sp.id IS NOT NULL THEN (sp.material || ' ' || sp.color_name || CASE WHEN sp.brand != '' THEN ' (' || sp.brand || ')' ELSE '' END) ELSE '' END AS spool_label,
       sp.remaining_grams AS spool_remaining_grams,
       COALESCE(sc.name, '') AS catalog_name,
       COALESCE(m.title, '') AS model_title,
       COALESCE(r.name, j.rubric_name, '') AS rubric_name_resolved,
       COALESCE(r.color_hex, '#22d3ee') AS rubric_color,
       COALESCE(sl.name, '') AS slicing_profile_name,
       COALESCE(j.layer_height_mm, sl.layer_height_mm) AS layer_height_resolved
FROM print_jobs j
LEFT JOIN printers p ON p.id = j.printer_id
LEFT JOIN filament_spools sp ON sp.id = j.spool_id
LEFT JOIN sales_catalog sc ON sc.id = j.catalog_item_id
LEFT JOIN models m ON m.id = j.model_id
LEFT JOIN print_rubrics r ON r.id = j.rubric_id
LEFT JOIN slicing_profiles sl ON sl.id = j.slicing_profile_id
"""


def _resolve_job_rubric_and_slicing(
    conn: sqlite3.Connection,
    data: dict[str, Any],
    now: str,
) -> tuple[int | None, str, int | None, float | None]:
    rubric_id = data.get("rubric_id")
    rubric_name = str(data.get("rubric_name") or "").strip()
    if rubric_id is not None:
        r_row = conn.execute("SELECT id, name FROM print_rubrics WHERE id = ?", (int(rubric_id),)).fetchone()
        if r_row:
            rubric_id = int(r_row["id"])
            rubric_name = str(r_row["name"])
        else:
            rubric_id = None
    elif rubric_name:
        r_row = conn.execute("SELECT id, name FROM print_rubrics WHERE LOWER(name) = LOWER(?)", (rubric_name,)).fetchone()
        if r_row:
            rubric_id = int(r_row["id"])
            rubric_name = str(r_row["name"])
        else:
            cur = conn.execute(
                "INSERT INTO print_rubrics (name, color_hex, notes, created_at, updated_at) VALUES (?, '#22d3ee', '', ?, ?)",
                (rubric_name, now, now),
            )
            rubric_id = int(cur.lastrowid)

    slicing_profile_id = data.get("slicing_profile_id")
    layer_height_mm = data.get("layer_height_mm")
    if slicing_profile_id is not None:
        s_row = conn.execute("SELECT id, layer_height_mm FROM slicing_profiles WHERE id = ?", (int(slicing_profile_id),)).fetchone()
        if s_row:
            slicing_profile_id = int(s_row["id"])
            if layer_height_mm is None:
                layer_height_mm = float(s_row["layer_height_mm"])
        else:
            slicing_profile_id = None

    return (
        int(rubric_id) if rubric_id is not None else None,
        rubric_name,
        int(slicing_profile_id) if slicing_profile_id is not None else None,
        float(layer_height_mm) if layer_height_mm is not None else None,
    )


def list_jobs(
    db_path: Path | str,
    status: str = "",
    printer_id: int | None = None,
    unassigned_printer: bool = False,
    rubric_id: int | None = None,
    rubric_name: str = "",
    target_type: str = "",
    priority: str = "",
    spool_id: int | None = None,
    slicing_profile_id: int | None = None,
    layer_height_mm: float | None = None,
    q: str = "",
    exclude_archived: bool = False,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("j.status = ?")
        params.append(status)
    elif exclude_archived:
        clauses.append("j.status != 'Arquivado'")
    if unassigned_printer:
        clauses.append("j.printer_id IS NULL")
    elif printer_id is not None:
        clauses.append("j.printer_id = ?")
        params.append(printer_id)
    if rubric_id is not None:
        clauses.append("j.rubric_id = ?")
        params.append(rubric_id)
    elif rubric_name:
        clauses.append("LOWER(COALESCE(r.name, j.rubric_name, '')) = LOWER(?)")
        params.append(rubric_name.strip())
    if target_type:
        clauses.append("j.target_type = ?")
        params.append(target_type)
    if priority:
        clauses.append("j.priority = ?")
        params.append(priority)
    if spool_id is not None:
        clauses.append("j.spool_id = ?")
        params.append(spool_id)
    if slicing_profile_id is not None:
        clauses.append("j.slicing_profile_id = ?")
        params.append(slicing_profile_id)
    if layer_height_mm is not None:
        clauses.append("ABS(COALESCE(j.layer_height_mm, sl.layer_height_mm, -1) - ?) < 0.005")
        params.append(float(layer_height_mm))
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(j.title LIKE ? OR j.customer_name LIKE ? OR COALESCE(r.name, j.rubric_name, '') LIKE ? OR COALESCE(j.slicing_notes, '') LIKE ? OR COALESCE(j.notes, '') LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order_sql = """
    ORDER BY
        CASE j.status WHEN 'Em Impressão' THEN 0 WHEN 'Pendente' THEN 1 WHEN 'Concluída' THEN 2 WHEN 'Falhou' THEN 3 ELSE 4 END ASC,
        CASE j.priority WHEN 'Urgente' THEN 0 WHEN 'Alta' THEN 1 WHEN 'Normal' THEN 2 ELSE 3 END ASC,
        j.id DESC
    """
    with _connect(db_path) as conn:
        rows = conn.execute(f"{_JOB_SELECT} {where_sql} {order_sql}", params).fetchall()
    items = [_job_row(r) for r in rows]
    return {
        "items": items,
        "total": len(items),
        "pending_count": sum(1 for i in items if i["status"] == "Pendente"),
        "active_count": sum(1 for i in items if i["status"] == "Em Impressão"),
        "done_count": sum(1 for i in items if i["status"] == "Concluída"),
        "total_estimated_grams": round(sum(i["estimated_grams"] for i in items if i["status"] in {"Pendente", "Em Impressão"}), 1),
    }


def _get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(f"{_JOB_SELECT} WHERE j.id = ?", (job_id,)).fetchone()
    return _job_row(row) if row else None


def _sync_printer_idle_state(conn: sqlite3.Connection, printer_id: int | None, now: str) -> None:
    if not printer_id:
        return
    active = conn.execute(
        "SELECT COUNT(*) AS cnt FROM print_jobs WHERE printer_id = ? AND status = 'Em Impressão'",
        (printer_id,),
    ).fetchone()["cnt"]
    if active > 0:
        conn.execute("UPDATE printers SET status = 'Imprimindo', updated_at = ? WHERE id = ?", (now, printer_id))
    else:
        conn.execute(
            "UPDATE printers SET status = 'Disponível', updated_at = ? WHERE id = ? AND status = 'Imprimindo'",
            (now, printer_id),
        )


def create_job(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    status = str(data.get("status") or "Pendente")
    started_at = now if status == "Em Impressão" else ""
    with _connect(db_path) as conn:
        rubric_id, rubric_name, slicing_id, layer_height = _resolve_job_rubric_and_slicing(conn, data, now)
        cur = conn.execute(
            """
            INSERT INTO print_jobs (
                model_id, printer_id, spool_id, catalog_item_id, rubric_id, rubric_name,
                slicing_profile_id, layer_height_mm, slicing_notes,
                title, target_type, customer_name, quantity, estimated_grams, actual_grams_used,
                estimated_time_min, priority, color_choice, material_choice,
                status, failure_reason, scheduled_for, started_at, finished_at,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("model_id"),
                data.get("printer_id"),
                data.get("spool_id"),
                data.get("catalog_item_id"),
                rubric_id,
                rubric_name,
                slicing_id,
                layer_height,
                str(data.get("slicing_notes") or "").strip(),
                str(data["title"]).strip(),
                str(data.get("target_type") or "Encomenda"),
                str(data.get("customer_name") or "").strip(),
                max(1, int(data.get("quantity") or 1)),
                float(data.get("estimated_grams") or 0.0),
                data.get("actual_grams_used"),
                data.get("estimated_time_min"),
                str(data.get("priority") or "Normal"),
                str(data.get("color_choice") or "").strip(),
                str(data.get("material_choice") or "").strip(),
                status,
                str(data.get("failure_reason") or "").strip(),
                str(data.get("scheduled_for") or "").strip(),
                started_at,
                "",
                str(data.get("notes") or "").strip(),
                now,
                now,
            ),
        )
        job_id = cur.lastrowid
        if status == "Em Impressão":
            _sync_printer_idle_state(conn, data.get("printer_id"), now)
        conn.commit()
        return _get_job(conn, job_id)  # type: ignore[return-value]


def update_job(db_path: Path | str, job_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    now = _now_iso()
    with _connect(db_path) as conn:
        existing = _get_job(conn, job_id)
        if not existing:
            return None

        merged = {**existing, **updates}
        if "rubric_id" in updates or "rubric_name" in updates or "slicing_profile_id" in updates or "layer_height_mm" in updates:
            # If user passed a new slicing_profile_id without explicit layer_height_mm in updates, recompute layer height from profile
            resolve_input = dict(merged)
            if "slicing_profile_id" in updates and "layer_height_mm" not in updates:
                resolve_input["layer_height_mm"] = None
            if "rubric_name" in updates and "rubric_id" not in updates:
                resolve_input["rubric_id"] = None
            rubric_id, rubric_name, slicing_id, layer_height = _resolve_job_rubric_and_slicing(conn, resolve_input, now)
        else:
            rubric_id = merged.get("rubric_id")
            rubric_name = merged.get("rubric_name") or ""
            slicing_id = merged.get("slicing_profile_id")
            layer_height = merged.get("layer_height_mm")
        new_status = str(merged["status"])
        old_printer_id = existing["printer_id"]
        new_printer_id = merged.get("printer_id")
        spool_id = merged.get("spool_id")
        filament_deducted = bool(existing["filament_deducted"])
        stock_added = bool(existing["stock_added"])

        started_at = existing["started_at"]
        finished_at = existing["finished_at"]

        if new_status == "Em Impressão" and not started_at:
            started_at = now
        if new_status in {"Concluída", "Falhou", "Cancelada"} and not finished_at:
            finished_at = now

        # Atomic filament deduction on completion or failure (idempotent via filament_deducted)
        if new_status == "Concluída" and not filament_deducted and spool_id:
            grams_to_deduct = (
                float(merged["actual_grams_used"])
                if merged.get("actual_grams_used") is not None
                else float(merged.get("estimated_grams") or 0.0)
            )
            if grams_to_deduct > 0:
                conn.execute(
                    "UPDATE filament_spools SET remaining_grams = MAX(0.0, remaining_grams - ?), updated_at = ? WHERE id = ?",
                    (grams_to_deduct, now, spool_id),
                )
            filament_deducted = True

        elif new_status == "Falhou" and not filament_deducted and spool_id:
            wasted = float(merged.get("actual_grams_used") or 0.0)
            if wasted > 0:
                conn.execute(
                    "UPDATE filament_spools SET remaining_grams = MAX(0.0, remaining_grams - ?), updated_at = ? WHERE id = ?",
                    (wasted, now, spool_id),
                )
                filament_deducted = True

        # Atomic finished-goods inventory increment only on Estoque job completion
        if new_status == "Concluída" and merged.get("target_type") == "Estoque" and merged.get("catalog_item_id") and not stock_added:
            qty = max(1, int(merged.get("quantity") or 1))
            conn.execute(
                "UPDATE sales_catalog SET stock_qty = stock_qty + ?, updated_at = ? WHERE id = ?",
                (qty, now, merged["catalog_item_id"]),
            )
            stock_added = True

        conn.execute(
            """
            UPDATE print_jobs SET
                printer_id = ?, spool_id = ?, catalog_item_id = ?,
                rubric_id = ?, rubric_name = ?, slicing_profile_id = ?, layer_height_mm = ?, slicing_notes = ?,
                title = ?, target_type = ?, customer_name = ?, quantity = ?, estimated_grams = ?,
                actual_grams_used = ?, estimated_time_min = ?, priority = ?,
                color_choice = ?, material_choice = ?, status = ?, failure_reason = ?,
                filament_deducted = ?, stock_added = ?, scheduled_for = ?,
                started_at = ?, finished_at = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_printer_id,
                spool_id,
                merged.get("catalog_item_id"),
                rubric_id,
                rubric_name,
                slicing_id,
                layer_height,
                merged.get("slicing_notes") or "",
                merged["title"],
                merged["target_type"],
                merged.get("customer_name") or "",
                max(1, int(merged.get("quantity") or 1)),
                float(merged.get("estimated_grams") or 0.0),
                merged.get("actual_grams_used"),
                merged.get("estimated_time_min"),
                merged["priority"],
                merged.get("color_choice") or "",
                merged.get("material_choice") or "",
                new_status,
                merged.get("failure_reason") or "",
                1 if filament_deducted else 0,
                1 if stock_added else 0,
                merged.get("scheduled_for") or "",
                started_at,
                finished_at,
                merged.get("notes") or "",
                now,
                job_id,
            ),
        )

        if old_printer_id and old_printer_id != new_printer_id:
            _sync_printer_idle_state(conn, old_printer_id, now)
        _sync_printer_idle_state(conn, new_printer_id, now)
        conn.commit()
        return _get_job(conn, job_id)


def delete_job(db_path: Path | str, job_id: int) -> bool:
    now = _now_iso()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT printer_id FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return False
        pid = row["printer_id"]
        cur = conn.execute("DELETE FROM print_jobs WHERE id = ?", (job_id,))
        _sync_printer_idle_state(conn, pid, now)
        conn.commit()
        return cur.rowcount > 0


# ---------------- Sales Catalog & Orders ---------------- #

def _classify_sales_catalog_subcategory(name: str, category: str) -> str:
    low = f"{name} {category}".lower()
    if "porta-cart" in low or "organizador" in low:
        return "Porta-Cartões & Organizadores"
    if "malhete" in low or "carimbo" in low:
        return "Malhetes & Carimbos"
    if "têmis" in low or "temis" in low or "balança" in low or "justiça" in low:
        return "Estátuas Têmis & Balança"
    if "estojo" in low or "caneta" in low:
        return "Acessórios de Mesa"
    if "caduceu" in low or "medicina" in low:
        return "Símbolos & Estátuas"
    if "escultura" in low or "estátua" in low or "filósofo" in low or "águia" in low:
        return "Esculturas & Bustos"
    return ""


def _classify_sales_catalog_classifications(
    name: str,
    category: str,
    explicit_subcategory: str = "",
) -> list[dict[str, str]]:
    primary_cat = str(category or "Outros").strip()
    primary_sub = str(explicit_subcategory or "").strip() or _classify_sales_catalog_subcategory(name, primary_cat)
    low = f"{name} {primary_cat}".lower()
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(cat_name: str, sub_name: str) -> None:
        c = str(cat_name or "").strip()
        s = str(sub_name or "").strip()
        if c and (c, s) not in seen:
            seen.add((c, s))
            results.append({"category": c, "subcategory": s})

    _add(primary_cat, primary_sub)
    if "porta-cart" in low or "organizador" in low:
        _add("Direito & Advocacia", "Porta-Cartões & Organizadores")
    if "organizador" in low or "estojo" in low or "caneta" in low or "mesa" in low:
        _add("Direito & Advocacia", "Acessórios de Mesa")
    if "malhete" in low or "carimbo" in low:
        _add("Direito & Advocacia", "Malhetes & Carimbos")
    if "têmis" in low or "temis" in low or "balança" in low or "justiça" in low:
        _add("Direito & Advocacia", "Estátuas Têmis & Balança")
    if "caduceu" in low or "medicina" in low:
        _add("Medicina", "Símbolos & Estátuas")
        _add("Medicina", "Consultório & Mesa")
    if any(k in low for k in ("escultura", "estátua", "estatua", "têmis", "temis", "balança", "caduceu", "filósofo", "águia")):
        _add("Decoração", "Esculturas & Bustos")
    if any(k in low for k in ("filósofo", "águia")):
        _add("Direito & Advocacia", "Acessórios de Mesa")
    return results


def _subcat_row(row: sqlite3.Row, count_map: dict[tuple[str, str, str], int] | None = None) -> dict[str, Any]:
    key = (row["scope"], row["category"], row["name"])
    return {
        "id": row["id"],
        "scope": row["scope"],
        "category": row["category"],
        "name": row["name"],
        "sort_order": int(row["sort_order"] or 0),
        "items_count": (count_map or {}).get(key, 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _subcat_counts(conn: sqlite3.Connection) -> dict[tuple[str, str, str], int]:
    counts: dict[tuple[str, str, str], int] = {}
    try:
        for r in conn.execute(
            """
            SELECT scope, category, subcategory, COUNT(DISTINCT item_id) AS c
            FROM item_classifications
            WHERE subcategory != ''
            GROUP BY scope, category, subcategory
            """
        ).fetchall():
            counts[(r["scope"], r["category"], r["subcategory"])] = int(r["c"])
    except sqlite3.OperationalError:
        pass
    if not counts:
        for r in conn.execute(
            "SELECT category, subcategory, COUNT(*) AS c FROM sales_catalog WHERE subcategory != '' GROUP BY category, subcategory"
        ).fetchall():
            counts[("sales_catalog", r["category"], r["subcategory"])] = int(r["c"])
        try:
            for r in conn.execute(
                "SELECT category, subcategory, COUNT(*) AS c FROM models WHERE subcategory != '' GROUP BY category, subcategory"
            ).fetchall():
                counts[("models", r["category"], r["subcategory"])] = int(r["c"])
        except sqlite3.OperationalError:
            pass
    return counts


def list_subcategories(db_path: Path | str, scope: str = "", category: str = "") -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM catalog_subcategories ORDER BY scope ASC, category ASC, sort_order ASC, name ASC"
        ).fetchall()
        counts = _subcat_counts(conn)
        cat_rows = conn.execute("SELECT DISTINCT category FROM sales_catalog WHERE category != ''").fetchall()
        try:
            model_cat_rows = conn.execute("SELECT DISTINCT category FROM models WHERE category != ''").fetchall()
        except sqlite3.OperationalError:
            model_cat_rows = []
        try:
            ic_cat_rows = conn.execute(
                "SELECT DISTINCT scope, category FROM item_classifications WHERE category != ''"
            ).fetchall()
        except sqlite3.OperationalError:
            ic_cat_rows = []

    items = [_subcat_row(r, counts) for r in rows]
    if scope:
        items = [i for i in items if i["scope"] == scope]
    if category:
        items = [i for i in items if i["category"] == category]

    cats = sorted(
        {i["category"] for i in items}
        | ({r["category"] for r in cat_rows} if scope in {"", "sales_catalog"} else set())
        | ({r["category"] for r in model_cat_rows} if scope in {"", "models"} else set())
        | {r["category"] for r in ic_cat_rows if not scope or r["scope"] == scope}
    )
    return {"items": items, "total": len(items), "categories": cats}


def create_subcategory(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    scope = str(data.get("scope") or "sales_catalog").strip()
    if scope not in SUBCATEGORY_SCOPES:
        raise ValueError("Escopo inválido. Use 'sales_catalog' ou 'models'.")
    category = str(data.get("category") or "").strip()
    name = str(data.get("name") or "").strip()
    if not category or not name:
        raise ValueError("Informe a categoria pai e o nome da subcategoria.")
    sort_order = int(data.get("sort_order") or 0)
    now = _now_iso()
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM catalog_subcategories WHERE scope = ? AND category = ? AND lower(name) = lower(?)",
            (scope, category, name),
        ).fetchone()
        if existing:
            raise ValueError("Já existe uma subcategoria com este nome nesta categoria.")
        cur = conn.execute(
            """
            INSERT INTO catalog_subcategories (scope, category, name, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (scope, category, name, sort_order, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM catalog_subcategories WHERE id = ?", (cur.lastrowid,)).fetchone()
        counts = _subcat_counts(conn)
    return _subcat_row(row, counts)


def update_subcategory(db_path: Path | str, sub_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    now = _now_iso()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM catalog_subcategories WHERE id = ?", (sub_id,)).fetchone()
        if not row:
            return None
        old_scope = row["scope"]
        old_cat = row["category"]
        old_name = row["name"]
        new_cat = str(updates.get("category") if updates.get("category") is not None else old_cat).strip()
        new_name = str(updates.get("name") if updates.get("name") is not None else old_name).strip()
        if not new_cat or not new_name:
            raise ValueError("Categoria e nome da subcategoria não podem ficar vazios.")
        new_order = int(updates["sort_order"]) if updates.get("sort_order") is not None else int(row["sort_order"] or 0)

        dup = conn.execute(
            "SELECT id FROM catalog_subcategories WHERE scope = ? AND category = ? AND lower(name) = lower(?) AND id != ?",
            (old_scope, new_cat, new_name, sub_id),
        ).fetchone()
        if dup:
            raise ValueError("Já existe outra subcategoria com esse nome nesta categoria.")

        conn.execute(
            "UPDATE catalog_subcategories SET category = ?, name = ?, sort_order = ?, updated_at = ? WHERE id = ?",
            (new_cat, new_name, new_order, now, sub_id),
        )
        if old_cat != new_cat or old_name != new_name:
            target_table = "sales_catalog" if old_scope == "sales_catalog" else "models"
            # Update item_classifications safely (avoiding UNIQUE conflict if an item already had target pair)
            existing_ic = conn.execute(
                "SELECT id, item_id FROM item_classifications WHERE scope = ? AND category = ? AND subcategory = ?",
                (old_scope, old_cat, old_name),
            ).fetchall()
            for ic in existing_ic:
                conflict = conn.execute(
                    "SELECT id FROM item_classifications WHERE scope = ? AND item_id = ? AND category = ? AND subcategory = ?",
                    (old_scope, ic["item_id"], new_cat, new_name),
                ).fetchone()
                if conflict:
                    conn.execute("DELETE FROM item_classifications WHERE id = ?", (ic["id"],))
                else:
                    conn.execute(
                        "UPDATE item_classifications SET category = ?, subcategory = ? WHERE id = ?",
                        (new_cat, new_name, ic["id"]),
                    )
            conn.execute(
                f"UPDATE {target_table} SET category = ?, subcategory = ?, updated_at = ? WHERE category = ? AND subcategory = ?",
                (new_cat, new_name, now, old_cat, old_name),
            )
        conn.commit()
        updated = conn.execute("SELECT * FROM catalog_subcategories WHERE id = ?", (sub_id,)).fetchone()
        counts = _subcat_counts(conn)
    return _subcat_row(updated, counts)


def delete_subcategory(db_path: Path | str, sub_id: int, reassign_to: str = "") -> bool:
    now = _now_iso()
    next_sub = reassign_to.strip()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM catalog_subcategories WHERE id = ?", (sub_id,)).fetchone()
        if not row:
            return False
        scope = row["scope"]
        old_cat = row["category"]
        old_name = row["name"]
        target_table = "sales_catalog" if scope == "sales_catalog" else "models"

        ic_matches = conn.execute(
            "SELECT id, item_id FROM item_classifications WHERE scope = ? AND category = ? AND subcategory = ?",
            (scope, old_cat, old_name),
        ).fetchall()
        for ic in ic_matches:
            if next_sub:
                conflict = conn.execute(
                    "SELECT id FROM item_classifications WHERE scope = ? AND item_id = ? AND category = ? AND subcategory = ?",
                    (scope, ic["item_id"], old_cat, next_sub),
                ).fetchone()
                if conflict:
                    conn.execute("DELETE FROM item_classifications WHERE id = ?", (ic["id"],))
                else:
                    conn.execute(
                        "UPDATE item_classifications SET subcategory = ? WHERE id = ?",
                        (next_sub, ic["id"]),
                    )
            else:
                conn.execute("DELETE FROM item_classifications WHERE id = ?", (ic["id"],))

        primary_rows = conn.execute(
            f"SELECT id FROM {target_table} WHERE category = ? AND subcategory = ?",
            (old_cat, old_name),
        ).fetchall()
        for pr in primary_rows:
            if next_sub:
                conn.execute(
                    f"UPDATE {target_table} SET subcategory = ?, updated_at = ? WHERE id = ?",
                    (next_sub, now, pr["id"]),
                )
            else:
                nxt = conn.execute(
                    "SELECT category, subcategory FROM item_classifications WHERE scope = ? AND item_id = ? ORDER BY sort_order ASC, id ASC LIMIT 1",
                    (scope, pr["id"]),
                ).fetchone()
                if nxt:
                    conn.execute(
                        f"UPDATE {target_table} SET category = ?, subcategory = ?, updated_at = ? WHERE id = ?",
                        (nxt["category"], nxt["subcategory"], now, pr["id"]),
                    )
                else:
                    conn.execute(
                        f"UPDATE {target_table} SET subcategory = '', updated_at = ? WHERE id = ?",
                        (now, pr["id"]),
                    )

        conn.execute("DELETE FROM catalog_subcategories WHERE id = ?", (sub_id,))
        conn.commit()
    return True


def ensure_subcategory_entry(db_path: Path | str, scope: str, category: str, subcategory: str) -> None:
    cat = str(category or "").strip()
    sub = str(subcategory or "").strip()
    if scope not in SUBCATEGORY_SCOPES or not cat or not sub:
        return
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO catalog_subcategories (scope, category, name, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (scope, cat, sub, now, now),
        )
        conn.commit()


def ensure_model_subcategory(db_path: Path | str, category: str, subcategory: str) -> None:
    ensure_subcategory_entry(db_path, "models", category, subcategory)


def _sync_default_registry(conn: sqlite3.Connection, now: str) -> None:
    for scope, cat_map in DEFAULT_SUBCATEGORIES.items():
        for cat_name, sub_names in cat_map.items():
            existing_for_cat = conn.execute(
                "SELECT COUNT(*) FROM catalog_subcategories WHERE scope = ? AND category = ?",
                (scope, cat_name),
            ).fetchone()[0]
            if existing_for_cat == 0:
                for idx, sub_name in enumerate(sub_names):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO catalog_subcategories (scope, category, name, sort_order, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (scope, cat_name, sub_name, idx, now, now),
                    )


def _apply_multi_classifications_db(
    conn: sqlite3.Connection,
    now: str,
    *,
    force_all: bool = False,
) -> dict[str, int]:
    catalog_updated = 0
    models_updated = 0

    cat_rows = conn.execute("SELECT id, name, category, subcategory FROM sales_catalog").fetchall()
    for r in cat_rows:
        existing_ic = conn.execute(
            "SELECT COUNT(*) FROM item_classifications WHERE scope = 'sales_catalog' AND item_id = ?",
            (r["id"],),
        ).fetchone()[0]
        if not force_all and r["subcategory"] != "" and existing_ic > 0:
            continue
        cls_list = _classify_sales_catalog_classifications(
            r["name"], r["category"], explicit_subcategory=r["subcategory"] if not force_all else ""
        )
        if not cls_list:
            continue
        primary = cls_list[0]
        conn.execute(
            "UPDATE sales_catalog SET category = ?, subcategory = ? WHERE id = ?",
            (primary["category"], primary["subcategory"], r["id"]),
        )
        sync_item_classifications(conn, "sales_catalog", r["id"], cls_list)
        for pair in cls_list:
            if pair["subcategory"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO catalog_subcategories (scope, category, name, sort_order, created_at, updated_at)
                    VALUES ('sales_catalog', ?, ?, 0, ?, ?)
                    """,
                    (pair["category"], pair["subcategory"], now, now),
                )
        catalog_updated += 1

    try:
        model_rows = conn.execute("SELECT id, title, category, subcategory, tags_json, description FROM models").fetchall()
    except sqlite3.OperationalError:
        model_rows = []
    for m in model_rows:
        existing_ic = conn.execute(
            "SELECT COUNT(*) FROM item_classifications WHERE scope = 'models' AND item_id = ?",
            (m["id"],),
        ).fetchone()[0]
        if not force_all and m["subcategory"] != "" and existing_ic > 0:
            continue
        tags = json.loads(m["tags_json"] or "[]")
        cls_list = classify_model_classifications(
            m["title"],
            m["category"],
            tags,
            m["description"],
            explicit_subcategory=m["subcategory"] if not force_all else "",
        )
        if not cls_list:
            continue
        primary = cls_list[0]
        conn.execute(
            "UPDATE models SET category = ?, subcategory = ?, updated_at = ? WHERE id = ?",
            (primary["category"], primary["subcategory"], now, m["id"]),
        )
        sync_item_classifications(conn, "models", m["id"], cls_list)
        for pair in cls_list:
            if pair["subcategory"]:
                order_list = DEFAULT_MODEL_SUBCATEGORIES.get(pair["category"], [])
                sort_idx = order_list.index(pair["subcategory"]) if pair["subcategory"] in order_list else 99
                conn.execute(
                    """
                    INSERT OR IGNORE INTO catalog_subcategories (scope, category, name, sort_order, created_at, updated_at)
                    VALUES ('models', ?, ?, ?, ?, ?)
                    """,
                    (pair["category"], pair["subcategory"], sort_idx, now, now),
                )
        models_updated += 1

    return {"catalog_updated": catalog_updated, "models_updated": models_updated}


def seed_default_subcategories(db_path: Path | str) -> None:
    now = _now_iso()
    with _connect(db_path) as conn:
        _sync_default_registry(conn, now)
        _apply_multi_classifications_db(conn, now, force_all=False)
        conn.commit()


def reclassify_all_items(db_path: Path | str) -> dict[str, int]:
    now = _now_iso()
    with _connect(db_path) as conn:
        _sync_default_registry(conn, now)
        res = _apply_multi_classifications_db(conn, now, force_all=True)
        conn.commit()
    return res


def list_catalog_items(
    db_path: Path | str,
    category: str = "",
    subcategory: str = "",
    q: str = "",
    in_stock_only: bool = False,
) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM sales_catalog ORDER BY id DESC").fetchall()
        cls_map = load_classifications_map(conn, "sales_catalog")
    items = [_catalog_row(r, cls_map.get(r["id"])) for r in rows]
    if category and subcategory:
        items = [
            i for i in items
            if any(c["category"] == category and c["subcategory"] == subcategory for c in (i.get("classifications") or []))
        ]
    elif category:
        items = [i for i in items if category in i.get("categories", [i["category"]])]
    elif subcategory:
        items = [i for i in items if subcategory in i.get("subcategories", [i.get("subcategory", "")])]
    if q:
        ql = q.strip().lower()
        items = [
            i
            for i in items
            if ql
            in (
                f"{i['code']} {i['name']} {i['category']} {i.get('subcategory', '')} "
                f"{' '.join(i.get('categories', []))} {' '.join(i.get('subcategories', []))} {i['notes']}"
            ).lower()
        ]
    if in_stock_only:
        items = [i for i in items if i["stock_qty"] > 0]
    total_units = sum(i["stock_qty"] for i in items)
    total_stock_value = round(sum(i["stock_qty"] * i["sale_price_brl"] for i in items), 2)
    return {
        "items": items,
        "total": len(items),
        "total_ready_units": total_units,
        "total_stock_value_brl": total_stock_value,
    }


def create_catalog_item(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    costs = compute_sale_price(data)
    cls_list = normalize_classifications(
        data.get("classifications"),
        category=str(data.get("category") or "Outros"),
        subcategory=str(data.get("subcategory") or ""),
        categories=data.get("categories"),
        subcategories=data.get("subcategories"),
        default_category="Outros",
    )
    primary_cat = cls_list[0]["category"]
    primary_sub = cls_list[0]["subcategory"]
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO sales_catalog (
                code, model_id, name, category, subcategory, source_url, image_url, dimensions_cm,
                filament_grams, filament_cost_per_kg_brl, energy_and_wear_brl,
                extras_cost_brl, pricing_mode, rate_per_gram_brl, margin_percent,
                sale_price_brl, stock_qty, min_stock_alert, active, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(data.get("code") or "").strip(),
                data.get("model_id"),
                str(data["name"]).strip(),
                primary_cat,
                primary_sub,
                str(data.get("source_url") or "").strip(),
                str(data.get("image_url") or "").strip(),
                str(data.get("dimensions_cm") or "").strip(),
                float(data.get("filament_grams") or 0.0),
                float(data.get("filament_cost_per_kg_brl") if data.get("filament_cost_per_kg_brl") is not None else 120.0),
                float(data.get("energy_and_wear_brl") or 0.0),
                float(data.get("extras_cost_brl") or 0.0),
                str(data.get("pricing_mode") or "rate_per_gram"),
                float(data.get("rate_per_gram_brl") if data.get("rate_per_gram_brl") is not None else 0.40),
                float(data.get("margin_percent") if data.get("margin_percent") is not None else 150.0),
                costs["sale_price_brl"],
                max(0, int(data.get("stock_qty") or 0)),
                max(0, int(data.get("min_stock_alert") if data.get("min_stock_alert") is not None else 1)),
                1 if data.get("active", True) else 0,
                str(data.get("notes") or "").strip(),
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        sync_item_classifications(conn, "sales_catalog", new_id, cls_list)
        conn.commit()
        row = conn.execute("SELECT * FROM sales_catalog WHERE id = ?", (new_id,)).fetchone()
        cls_map = load_classifications_map(conn, "sales_catalog", item_id=new_id)
    return _catalog_row(row, cls_map.get(new_id))


def update_catalog_item(db_path: Path | str, item_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sales_catalog WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        existing_cls = load_classifications_map(conn, "sales_catalog", item_id=item_id).get(item_id)
        existing_dict = _catalog_row(row, existing_cls)
        merged = {**existing_dict, **updates}

        if "classifications" in updates and updates["classifications"] is not None:
            cls_list = normalize_classifications(
                updates["classifications"],
                default_category=merged.get("category") or "Outros",
            )
        elif "category" in updates or "subcategory" in updates:
            next_cat = str(merged.get("category") or "Outros").strip()
            next_sub = str(merged.get("subcategory") or "").strip()
            rest = list(existing_dict.get("classifications") or [])
            cls_list = normalize_classifications(
                [{"category": next_cat, "subcategory": next_sub}, *rest[1:]],
                default_category=next_cat,
            )
        else:
            cls_list = existing_dict["classifications"]

        merged["category"] = cls_list[0]["category"]
        merged["subcategory"] = cls_list[0]["subcategory"]

        costs = compute_sale_price(merged)
        sale_price = float(merged["sale_price_brl"]) if updates.get("pricing_mode") == "manual" or ("sale_price_brl" in updates and "pricing_mode" not in updates and merged["pricing_mode"] == "manual") else costs["sale_price_brl"]
        if "sale_price_brl" in updates and merged["pricing_mode"] == "manual":
            sale_price = round(float(updates["sale_price_brl"]), 2)
        conn.execute(
            """
            UPDATE sales_catalog SET
                code = ?, model_id = ?, name = ?, category = ?, subcategory = ?, source_url = ?,
                image_url = ?, dimensions_cm = ?, filament_grams = ?,
                filament_cost_per_kg_brl = ?, energy_and_wear_brl = ?,
                extras_cost_brl = ?, pricing_mode = ?, rate_per_gram_brl = ?,
                margin_percent = ?, sale_price_brl = ?, stock_qty = ?,
                min_stock_alert = ?, active = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged.get("code") or "",
                merged.get("model_id"),
                merged["name"],
                merged["category"],
                merged["subcategory"],
                merged.get("source_url") or "",
                merged.get("image_url") or "",
                merged.get("dimensions_cm") or "",
                float(merged.get("filament_grams") or 0.0),
                float(merged.get("filament_cost_per_kg_brl") or 120.0),
                float(merged.get("energy_and_wear_brl") or 0.0),
                float(merged.get("extras_cost_brl") or 0.0),
                merged["pricing_mode"],
                float(merged.get("rate_per_gram_brl") or 0.40),
                float(merged.get("margin_percent") or 150.0),
                sale_price,
                max(0, int(merged.get("stock_qty") or 0)),
                max(0, int(merged.get("min_stock_alert") or 0)),
                1 if merged.get("active", True) else 0,
                merged.get("notes") or "",
                _now_iso(),
                item_id,
            ),
        )
        sync_item_classifications(conn, "sales_catalog", item_id, cls_list)
        conn.commit()
        updated = conn.execute("SELECT * FROM sales_catalog WHERE id = ?", (item_id,)).fetchone()
        cls_map = load_classifications_map(conn, "sales_catalog", item_id=item_id)
    return _catalog_row(updated, cls_map.get(item_id))


def delete_catalog_item(db_path: Path | str, item_id: int) -> bool:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM item_classifications WHERE scope = 'sales_catalog' AND item_id = ?", (item_id,))
        cur = conn.execute("DELETE FROM sales_catalog WHERE id = ?", (item_id,))
        conn.commit()
        return cur.rowcount > 0


def list_sales(db_path: Path | str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM sales_orders ORDER BY id DESC").fetchall()
    items = [_sale_row(r) for r in rows]
    total_rev = round(sum(i["total_price_brl"] for i in items), 2)
    paid_rev = round(sum(i["total_price_brl"] for i in items if i["payment_status"] == "Pago"), 2)
    return {
        "items": items,
        "total": len(items),
        "total_revenue_brl": total_rev,
        "paid_revenue_brl": paid_rev,
    }


def create_sale(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    qty = max(1, int(data.get("quantity") or 1))
    cat_id = data.get("catalog_item_id")
    auto_queue = bool(data.get("auto_queue_missing", True))
    queued_job: dict[str, Any] | None = None

    with _connect(db_path) as conn:
        cat_row = conn.execute("SELECT * FROM sales_catalog WHERE id = ?", (cat_id,)).fetchone() if cat_id else None
        item_name = str(data.get("item_name") or (cat_row["name"] if cat_row else "Produto Personalizado")).strip()
        unit_price = float(
            data["unit_price_brl"]
            if data.get("unit_price_brl") is not None
            else (cat_row["sale_price_brl"] if cat_row else 0.0)
        )
        total_price = round(unit_price * qty, 2)

        missing_qty = 0
        fulfillment = str(data.get("fulfillment_status") or "Pronta Entrega")
        if cat_row:
            avail = int(cat_row["stock_qty"] or 0)
            used = min(avail, qty)
            missing_qty = qty - used
            conn.execute(
                "UPDATE sales_catalog SET stock_qty = ?, updated_at = ? WHERE id = ?",
                (avail - used, now, cat_id),
            )
            if missing_qty > 0 and "fulfillment_status" not in data:
                fulfillment = "Produzir na Fila"

        cur = conn.execute(
            """
            INSERT INTO sales_orders (
                catalog_item_id, item_name, customer_name, channel, quantity,
                unit_price_brl, total_price_brl, payment_status, fulfillment_status,
                notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cat_id,
                item_name,
                str(data.get("customer_name") or "").strip(),
                str(data.get("channel") or "Instagram"),
                qty,
                unit_price,
                total_price,
                str(data.get("payment_status") or "Pendente"),
                fulfillment,
                str(data.get("notes") or "").strip(),
                now,
            ),
        )
        sale_row = conn.execute("SELECT * FROM sales_orders WHERE id = ?", (cur.lastrowid,)).fetchone()

        if missing_qty > 0 and auto_queue and cat_row:
            est_grams = round(float(cat_row["filament_grams"] or 0.0) * missing_qty, 1)
            j_cur = conn.execute(
                """
                INSERT INTO print_jobs (
                    model_id, catalog_item_id, title, target_type, customer_name,
                    quantity, estimated_grams, priority, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, 'Encomenda', ?, ?, ?, 'Alta', 'Pendente', ?, ?, ?)
                """,
                (
                    cat_row["model_id"],
                    cat_id,
                    f"Encomenda: {item_name} ({missing_qty}x)",
                    str(data.get("customer_name") or "").strip(),
                    missing_qty,
                    est_grams,
                    f"Gerado automaticamente pela venda #{cur.lastrowid}",
                    now,
                    now,
                ),
            )
            queued_job = _get_job(conn, j_cur.lastrowid)

        conn.commit()
    return {"sale": _sale_row(sale_row), "queued_job": queued_job}


def delete_sale(db_path: Path | str, sale_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM sales_orders WHERE id = ?", (sale_id,))
        conn.commit()
        return cur.rowcount > 0


# ---------------- Media & Instagram Studio ---------------- #

def list_media_posts(db_path: Path | str, status: str = "", post_format: str = "") -> dict[str, Any]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM media_posts ORDER BY id DESC").fetchall()
    items = [_media_row(r) for r in rows]
    if status:
        items = [i for i in items if i["status"] == status]
    if post_format:
        items = [i for i in items if i["post_format"] == post_format]
    return {
        "items": items,
        "total": len(items),
        "ready_to_post_count": sum(1 for i in items if i["status"] in {"Legenda Pronta", "Agendado"}),
        "posted_count": sum(1 for i in items if i["status"] == "Postado"),
    }


def create_media_post(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    status = str(data.get("status") or "Banco de Fotos")
    posted_at = now if status == "Postado" else ""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO media_posts (
                filename, file_url, title, model_id, print_job_id, catalog_item_id,
                post_format, status, caption, hashtags, scheduled_date, posted_at,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["filename"],
                data["file_url"],
                str(data.get("title") or "").strip(),
                data.get("model_id"),
                data.get("print_job_id"),
                data.get("catalog_item_id"),
                str(data.get("post_format") or "Feed"),
                status,
                str(data.get("caption") or "").strip(),
                str(data.get("hashtags") or "").strip(),
                str(data.get("scheduled_date") or "").strip(),
                posted_at,
                str(data.get("notes") or "").strip(),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM media_posts WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _media_row(row)


def update_media_post(db_path: Path | str, media_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    now = _now_iso()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM media_posts WHERE id = ?", (media_id,)).fetchone()
        if not row:
            return None
        existing = _media_row(row)
        merged = {**existing, **updates}
        posted_at = existing["posted_at"]
        if merged["status"] == "Postado" and not posted_at:
            posted_at = now
        conn.execute(
            """
            UPDATE media_posts SET
                file_url = ?, title = ?, model_id = ?, print_job_id = ?, catalog_item_id = ?,
                post_format = ?, status = ?, caption = ?, hashtags = ?,
                scheduled_date = ?, posted_at = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(merged.get("file_url") or "").strip(),
                merged.get("title") or "",
                merged.get("model_id"),
                merged.get("print_job_id"),
                merged.get("catalog_item_id"),
                merged["post_format"],
                merged["status"],
                merged.get("caption") or "",
                merged.get("hashtags") or "",
                merged.get("scheduled_date") or "",
                posted_at,
                merged.get("notes") or "",
                now,
                media_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM media_posts WHERE id = ?", (media_id,)).fetchone()
    return _media_row(updated)


def delete_media_post(db_path: Path | str, media_id: int, media_dir: Path) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT filename FROM media_posts WHERE id = ?", (media_id,)).fetchone()
        if not row:
            return False
        rel = unquote(str(row["filename"]))
        conn.execute("DELETE FROM media_posts WHERE id = ?", (media_id,))
        conn.commit()
    if rel:
        target = (media_dir / rel).resolve()
        try:
            if target.is_file() and media_dir.resolve() in target.parents:
                target.unlink()
        except OSError:
            pass
    return True


def generate_instagram_caption(title: str, category: str = "", price_brl: float | None = None, notes: str = "") -> dict[str, str]:
    clean_title = title.strip() or "Peça Exclusiva em Impressão 3D"
    price_line = f"\n💰 Valor: R$ {price_brl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if price_brl and price_brl > 0 else ""
    extra_line = f"\n✨ {notes.strip()}" if notes.strip() else ""
    cat_tag = "".join(ch for ch in category.lower() if ch.isalnum())

    caption = (
        f"✨ {clean_title} — feito com precisão na Ita Arte 3D!\n\n"
        f"Produzido sob medida em impressão 3D de alta definição, com acabamento pensado nos mínimos detalhes."
        f"{extra_line}{price_line}\n\n"
        f"📩 Quer uma peça personalizada ou em outras cores? Chama no Direct ou no link da bio!"
    )
    base_tags = ["#ItaArte3D", "#Impressao3D", "#3DPrintBrasil", "#PresentePersonalizado", "#BambuLabA1"]
    if "direito" in category.lower() or "advoc" in clean_title.lower():
        base_tags.extend(["#Direito", "#Advocacia", "#EscritorioDeAdvocacia", "#PresenteAdvogado"])
    elif "medicina" in category.lower():
        base_tags.extend(["#Medicina", "#Consultorio", "#Medico"])
    elif "chaveiro" in category.lower():
        base_tags.extend(["#ChaveirosPersonalizados", "#BrindesCorporativos"])
    elif cat_tag:
        base_tags.append(f"#{cat_tag}")

    return {"caption": caption, "hashtags": " ".join(dict.fromkeys(base_tags))}


# ---------------- Seeding & Summary ---------------- #

def import_ita_arte_catalog(
    db_path: Path | str,
    media_dir: Path,
    ita_arte_dir: Path = DEFAULT_ITA_ARTE_DIR,
) -> int:
    data_file = ita_arte_dir / "catalogo_dados.json"
    if not data_file.exists():
        return 0
    items = json.loads(data_file.read_text(encoding="utf-8"))
    dest_dir = media_dir / "catalog"
    dest_dir.mkdir(parents=True, exist_ok=True)

    logo_src = ita_arte_dir / "assets" / "logo-ita-arte-3d.jpg"
    if logo_src.exists():
        logo_dest = dest_dir / "logo-ita-arte-3d.jpg"
        if not logo_dest.exists():
            shutil.copy2(logo_src, logo_dest)

    existing_codes = {i["code"] for i in list_catalog_items(db_path)["items"] if i["code"]}
    imported = 0
    with _connect(db_path) as conn:
        model_rows = {r["url"]: r["id"] for r in conn.execute("SELECT id, url FROM models").fetchall()}

    for item in items:
        code = str(item.get("codigo") or "").strip()
        if code and code in existing_codes:
            continue

        img_rel = str(item.get("imagem") or "").replace("\\", "/")
        img_url = str(item.get("imagem_url") or "")
        # Prefer optimized jpg if available
        stem = Path(img_rel).stem if img_rel else ""
        opt_src = ita_arte_dir / "assets" / "produtos_otimizados" / f"{stem}.jpg"
        raw_src = ita_arte_dir / img_rel if img_rel else None
        chosen_src = opt_src if opt_src.exists() else (raw_src if raw_src and raw_src.exists() else None)
        if chosen_src:
            dest_file = dest_dir / chosen_src.name
            if not dest_file.exists():
                shutil.copy2(chosen_src, dest_file)
            img_url = f"/media/catalog/{chosen_src.name}"

        dims_cm = " × ".join(
            str(p) for p in [item.get("altura_cm"), item.get("largura_cm"), item.get("profundidade_cm")] if p is not None and str(p).strip()
        )
        if dims_cm:
            dims_cm += " cm (A×L×P)"

        src_url = str(item.get("url") or "").split("?")[0].split("#")[0]
        cls_list = _classify_sales_catalog_classifications(
            item.get("nome", "Produto"),
            item.get("categoria", "Outros"),
            explicit_subcategory=str(item.get("subcategoria") or ""),
        )
        create_catalog_item(
            db_path,
            {
                "code": code,
                "model_id": model_rows.get(src_url),
                "name": item.get("nome", "Produto"),
                "category": item.get("categoria", "Outros"),
                "subcategory": cls_list[0]["subcategory"] if cls_list else "",
                "classifications": cls_list,
                "source_url": str(item.get("url") or ""),
                "image_url": img_url,
                "dimensions_cm": dims_cm,
                "filament_grams": float(item.get("gramas_filamento") or 0.0),
                "pricing_mode": "rate_per_gram",
                "rate_per_gram_brl": 0.40,
                "stock_qty": 0,
                "notes": str(item.get("medidas_nota") or ""),
            },
        )
        imported += 1
    return imported


def seed_default_business_data(db_path: Path | str, media_dir: Path, ita_arte_dir: Path = DEFAULT_ITA_ARTE_DIR) -> None:
    if list_printers(db_path)["total"] == 0:
        create_printer(
            db_path,
            {
                "name": "Bambu Lab A1 — Principal",
                "brand_model": "Bambu Lab A1",
                "build_volume_mm": "256 x 256 x 256 mm",
                "max_dim_mm": 256.0,
                "nozzle_mm": 0.4,
                "has_ams": True,
                "ams_slots": 4,
                "status": "Disponível",
                "hourly_cost_brl": 2.50,
                "notes": "Impressora principal da Ita Arte 3D com AMS Lite 4 cores.",
            },
        )
    if list_catalog_items(db_path)["total"] == 0 and (ita_arte_dir / "catalogo_dados.json").exists():
        import_ita_arte_catalog(db_path, media_dir, ita_arte_dir=ita_arte_dir)
    seed_default_subcategories(db_path)


def get_hub_summary(db_path: Path | str) -> dict[str, Any]:
    with _connect(db_path) as conn:
        models_total = conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"]
        archived_models = conn.execute("SELECT COUNT(*) AS c FROM models WHERE status = 'Arquivado'").fetchone()["c"]
    printers = list_printers(db_path)
    jobs = list_jobs(db_path)
    archived_jobs = sum(1 for i in jobs["items"] if i["status"] == "Arquivado")
    spools = list_spools(db_path)
    catalog = list_catalog_items(db_path)
    sales = list_sales(db_path)
    media = list_media_posts(db_path)
    return {
        "models_total": models_total,
        "models_active": models_total - archived_models,
        "archived_models": archived_models,
        "archived_jobs": archived_jobs,
        "archived_total": archived_models + archived_jobs,
        "queue_pending": jobs["pending_count"],
        "queue_active": jobs["active_count"],
        "printers_total": printers["total"],
        "printers_busy": sum(1 for p in printers["items"] if p["status"] == "Imprimindo"),
        "spools_total": spools["total"],
        "spools_low": spools["low_stock_count"],
        "spools_grams": spools["total_remaining_grams"],
        "catalog_total": catalog["total"],
        "ready_stock_units": catalog["total_ready_units"],
        "sales_total": sales["total"],
        "sales_revenue_brl": sales["total_revenue_brl"],
        "media_total": media["total"],
        "media_ready": media["ready_to_post_count"],
    }
