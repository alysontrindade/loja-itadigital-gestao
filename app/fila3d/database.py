from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.fila3d.analyzer import MULTICOLOR_LABEL, normalize_classifications


def _connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                size_tier TEXT NOT NULL,
                dimensions_mm TEXT NOT NULL DEFAULT '',
                max_dimension_mm REAL,
                filament_grams REAL,
                print_time_min INTEGER,
                recommended_filaments_json TEXT NOT NULL DEFAULT '[]',
                filament_reason TEXT NOT NULL DEFAULT '',
                recommended_colors_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'Na Fila',
                notes TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(models)").fetchall()}
        if "subcategory" not in cols:
            conn.execute("ALTER TABLE models ADD COLUMN subcategory TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_models_category ON models(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_models_subcategory ON models(subcategory)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_models_collected_at ON models(collected_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_models_status ON models(status)")
        conn.executescript(
            """
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
        conn.execute(
            """
            INSERT OR IGNORE INTO item_classifications (scope, item_id, category, subcategory, sort_order)
            SELECT 'models', id, category, COALESCE(subcategory, ''), 0
            FROM models m
            WHERE category != ''
              AND NOT EXISTS (
                  SELECT 1 FROM item_classifications ic WHERE ic.scope = 'models' AND ic.item_id = m.id
              )
            """
        )
        conn.commit()


def sync_item_classifications(
    conn: sqlite3.Connection,
    scope: str,
    item_id: int,
    classifications: list[dict[str, str]],
) -> None:
    conn.execute("DELETE FROM item_classifications WHERE scope = ? AND item_id = ?", (scope, item_id))
    for idx, entry in enumerate(classifications):
        cat = str(entry.get("category") or "").strip()
        sub = str(entry.get("subcategory") or "").strip()
        if not cat:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO item_classifications (scope, item_id, category, subcategory, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scope, item_id, cat, sub, idx),
        )


def load_classifications_map(
    conn: sqlite3.Connection,
    scope: str,
    item_id: int | None = None,
) -> dict[int, list[dict[str, str]]]:
    mapping: dict[int, list[dict[str, str]]] = {}
    try:
        if item_id is not None:
            rows = conn.execute(
                "SELECT item_id, category, subcategory FROM item_classifications WHERE scope = ? AND item_id = ? ORDER BY sort_order ASC, id ASC",
                (scope, item_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT item_id, category, subcategory FROM item_classifications WHERE scope = ? ORDER BY item_id ASC, sort_order ASC, id ASC",
                (scope,),
            ).fetchall()
    except sqlite3.OperationalError:
        return mapping
    for r in rows:
        mapping.setdefault(int(r["item_id"]), []).append(
            {"category": r["category"], "subcategory": r["subcategory"]}
        )
    return mapping


def _row_to_dict(row: sqlite3.Row, classifications: list[dict[str, str]] | None = None) -> dict[str, Any]:
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
        "url": row["url"],
        "source": row["source"],
        "external_id": row["external_id"],
        "title": row["title"],
        "description": row["description"],
        "image_url": row["image_url"],
        "category": cls_list[0]["category"] if cls_list else primary_cat,
        "subcategory": cls_list[0]["subcategory"] if cls_list else primary_sub,
        "categories": cats,
        "subcategories": subs,
        "classifications": cls_list,
        "tags": json.loads(row["tags_json"] or "[]"),
        "size_tier": row["size_tier"],
        "dimensions_mm": row["dimensions_mm"],
        "max_dimension_mm": row["max_dimension_mm"],
        "filament_grams": row["filament_grams"],
        "print_time_min": row["print_time_min"],
        "recommended_filaments": json.loads(row["recommended_filaments_json"] or "[]"),
        "filament_reason": row["filament_reason"],
        "recommended_colors": json.loads(row["recommended_colors_json"] or "[]"),
        "status": row["status"],
        "notes": row["notes"],
        "collected_at": row["collected_at"],
        "updated_at": row["updated_at"],
    }


def _parse_dt_aware(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        dt = dt.replace(tzinfo=local_tz)
    return dt


def upsert_model(db_path: Path | str, data: dict[str, Any]) -> dict[str, Any]:
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    collected_at = data.get("collected_at") or now_iso
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
        existing = conn.execute("SELECT id, category, subcategory FROM models WHERE url = ?", (data["url"],)).fetchone()
        params = (
            data.get("source", "Outro"),
            data.get("external_id", ""),
            data["title"],
            data.get("description", ""),
            data.get("image_url", ""),
            primary_cat,
            primary_sub,
            json.dumps(data.get("tags", []), ensure_ascii=False),
            data.get("size_tier", "Médio"),
            data.get("dimensions_mm", ""),
            data.get("max_dimension_mm"),
            data.get("filament_grams"),
            data.get("print_time_min"),
            json.dumps(data.get("recommended_filaments", []), ensure_ascii=False),
            data.get("filament_reason", ""),
            json.dumps(data.get("recommended_colors", []), ensure_ascii=False),
            data.get("status", "Na Fila"),
            data.get("notes", ""),
            collected_at,
            now_iso,
        )
        if existing:
            conn.execute(
                """
                UPDATE models SET
                    source = ?, external_id = ?, title = ?, description = ?,
                    image_url = COALESCE(NULLIF(?, ''), image_url),
                    category = ?,
                    subcategory = COALESCE(NULLIF(?, ''), subcategory),
                    tags_json = ?, size_tier = ?, dimensions_mm = ?,
                    max_dimension_mm = ?, filament_grams = ?, print_time_min = ?,
                    recommended_filaments_json = ?, filament_reason = ?,
                    recommended_colors_json = ?, status = ?, notes = ?,
                    collected_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (*params, existing["id"]),
            )
            model_id = existing["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO models (
                    url, source, external_id, title, description, image_url,
                    category, subcategory, tags_json, size_tier, dimensions_mm,
                    max_dimension_mm, filament_grams, print_time_min,
                    recommended_filaments_json, filament_reason,
                    recommended_colors_json, status, notes,
                    collected_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["url"], *params),
            )
            model_id = cur.lastrowid
        sync_item_classifications(conn, "models", model_id, cls_list)
        conn.commit()
        row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        cls_map = load_classifications_map(conn, "models", item_id=model_id)
        return _row_to_dict(row, cls_map.get(model_id))


def get_model(db_path: Path | str, model_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
        if not row:
            return None
        cls_map = load_classifications_map(conn, "models", item_id=model_id)
        return _row_to_dict(row, cls_map.get(model_id))


def update_model(db_path: Path | str, model_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_model(db_path, model_id)
    if not existing:
        return None

    merged = {**existing, **updates}
    if "dimensions_mm" in updates and "max_dimension_mm" not in updates:
        from app.fila3d.analyzer import _parse_max_dim
        parsed_dim = _parse_max_dim(merged.get("dimensions_mm", ""))
        if parsed_dim is not None:
            merged["max_dimension_mm"] = parsed_dim

    if "classifications" in updates and updates["classifications"] is not None:
        cls_list = normalize_classifications(
            updates["classifications"],
            default_category=merged.get("category") or "Outros",
        )
    elif "category" in updates or "subcategory" in updates:
        next_cat = str(merged.get("category") or "Outros").strip()
        next_sub = str(merged.get("subcategory") or "").strip()
        rest = list(existing.get("classifications") or [])
        cls_list = normalize_classifications(
            [{"category": next_cat, "subcategory": next_sub}, *rest[1:]],
            default_category=next_cat,
        )
    else:
        cls_list = normalize_classifications(
            existing.get("classifications"),
            category=merged["category"],
            subcategory=str(merged.get("subcategory") or ""),
            default_category="Outros",
        )

    merged["category"] = cls_list[0]["category"]
    merged["subcategory"] = cls_list[0]["subcategory"]

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE models SET
                title = ?, description = ?, image_url = ?, category = ?, subcategory = ?,
                tags_json = ?, status = ?, size_tier = ?,
                dimensions_mm = ?, max_dimension_mm = ?, filament_grams = ?,
                print_time_min = ?, recommended_filaments_json = ?,
                filament_reason = ?, recommended_colors_json = ?,
                notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["title"],
                merged.get("description", ""),
                merged.get("image_url", ""),
                merged["category"],
                merged["subcategory"],
                json.dumps(merged.get("tags", []), ensure_ascii=False),
                merged["status"],
                merged["size_tier"],
                merged.get("dimensions_mm", ""),
                merged.get("max_dimension_mm"),
                merged.get("filament_grams"),
                merged.get("print_time_min"),
                json.dumps(merged.get("recommended_filaments", []), ensure_ascii=False),
                merged.get("filament_reason", ""),
                json.dumps(merged.get("recommended_colors", []), ensure_ascii=False),
                merged.get("notes", ""),
                now_iso,
                model_id,
            ),
        )
        sync_item_classifications(conn, "models", model_id, cls_list)
        conn.commit()
    return get_model(db_path, model_id)


def count_models_missing_images(db_path: Path | str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM models WHERE image_url IS NULL OR TRIM(image_url) = ''"
        ).fetchone()
    return int(row[0]) if row else 0


def list_models_missing_images(db_path: Path | str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM models
            WHERE image_url IS NULL OR TRIM(image_url) = ''
            ORDER BY collected_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, max(0, offset)),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def batch_update_enriched_models(db_path: Path | str, patches: list[tuple[int, dict[str, Any]]]) -> int:
    if not patches:
        return 0
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    updated = 0
    with _connect(db_path) as conn:
        for model_id, fields in patches:
            if not fields:
                continue
            conn.execute(
                """
                UPDATE models SET
                    image_url = COALESCE(NULLIF(?, ''), image_url),
                    description = CASE WHEN description = '' THEN ? ELSE description END,
                    tags_json = CASE WHEN tags_json = '[]' AND ? != '[]' THEN ? ELSE tags_json END,
                    dimensions_mm = CASE WHEN dimensions_mm = '' THEN ? ELSE dimensions_mm END,
                    max_dimension_mm = COALESCE(max_dimension_mm, ?),
                    filament_grams = COALESCE(filament_grams, ?),
                    print_time_min = COALESCE(print_time_min, ?),
                    size_tier = COALESCE(NULLIF(?, ''), size_tier),
                    recommended_filaments_json = CASE WHEN ? != '[]' THEN ? ELSE recommended_filaments_json END,
                    recommended_colors_json = CASE WHEN ? != '[]' THEN ? ELSE recommended_colors_json END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    fields.get("image_url", ""),
                    fields.get("description", ""),
                    json.dumps(fields.get("tags", []), ensure_ascii=False),
                    json.dumps(fields.get("tags", []), ensure_ascii=False),
                    fields.get("dimensions_mm", ""),
                    fields.get("max_dimension_mm"),
                    fields.get("filament_grams"),
                    fields.get("print_time_min"),
                    fields.get("size_tier", ""),
                    json.dumps(fields.get("recommended_filaments", []), ensure_ascii=False),
                    json.dumps(fields.get("recommended_filaments", []), ensure_ascii=False),
                    json.dumps(fields.get("recommended_colors", []), ensure_ascii=False),
                    json.dumps(fields.get("recommended_colors", []), ensure_ascii=False),
                    now_iso,
                    model_id,
                ),
            )
            updated += 1
        conn.commit()
    return updated


def delete_model(db_path: Path | str, model_id: int) -> bool:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM item_classifications WHERE scope = 'models' AND item_id = ?", (model_id,))
        cur = conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        conn.commit()
        return cur.rowcount > 0


def list_models(db_path: Path | str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    f = filters or {}
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM models").fetchall()
        cls_map = load_classifications_map(conn, "models")

    items = [_row_to_dict(r, cls_map.get(r["id"])) for r in rows]

    q = str(f.get("q") or "").strip().lower()
    status = str(f.get("status") or "").strip()
    category = str(f.get("category") or "").strip()
    subcategory = str(f.get("subcategory") or "").strip()
    source = str(f.get("source") or "").strip()
    size_tier = str(f.get("size_tier") or "").strip()
    filament = str(f.get("filament") or "").strip()
    color = str(f.get("color") or "").strip()
    include_multicolor = bool(f.get("include_multicolor", False))
    exclude_archived = bool(f.get("exclude_archived", False))

    from_dt = _parse_dt_aware(str(f.get("collected_from") or "").strip())
    to_dt = _parse_dt_aware(str(f.get("collected_to") or "").strip())

    max_dim_limit = f.get("max_dimension_mm")
    max_dim_limit = float(max_dim_limit) if max_dim_limit not in (None, "") else None
    min_grams = f.get("min_grams")
    min_grams = float(min_grams) if min_grams not in (None, "") else None
    max_grams = f.get("max_grams")
    max_grams = float(max_grams) if max_grams not in (None, "") else None

    filtered: list[dict[str, Any]] = []
    for item in items:
        if q:
            haystack = " ".join(
                [
                    item["title"],
                    item["category"],
                    item.get("subcategory", ""),
                    " ".join(item.get("categories", [])),
                    " ".join(item.get("subcategories", [])),
                    item["url"],
                    item["notes"],
                    item["filament_reason"],
                    " ".join(item["tags"]),
                ]
            ).lower()
            if q not in haystack:
                continue

        if status:
            if item["status"] != status:
                continue
        elif exclude_archived and item["status"] == "Arquivado":
            continue
        item_cls = item.get("classifications") or []
        if category and subcategory:
            if not any(c["category"] == category and c["subcategory"] == subcategory for c in item_cls):
                continue
        elif category:
            if category not in item.get("categories", [item["category"]]):
                continue
        elif subcategory:
            if subcategory not in item.get("subcategories", [item.get("subcategory", "")]):
                continue
        if source and item["source"] != source:
            continue
        if size_tier and item["size_tier"] != size_tier:
            continue

        if from_dt or to_dt:
            item_dt = _parse_dt_aware(item["collected_at"])
            if not item_dt:
                continue
            if from_dt and item_dt < from_dt:
                continue
            if to_dt and item_dt > to_dt:
                continue

        if max_dim_limit is not None:
            if item["max_dimension_mm"] is None or item["max_dimension_mm"] > max_dim_limit:
                continue

        if min_grams is not None:
            if item["filament_grams"] is None or item["filament_grams"] < min_grams:
                continue
        if max_grams is not None:
            if item["filament_grams"] is None or item["filament_grams"] > max_grams:
                continue

        if filament and filament not in item["recommended_filaments"]:
            continue

        if color:
            item_colors = set(item["recommended_colors"])
            if color == MULTICOLOR_LABEL:
                if MULTICOLOR_LABEL not in item_colors:
                    continue
            else:
                has_exact = color in item_colors
                has_multi = include_multicolor and MULTICOLOR_LABEL in item_colors
                if not (has_exact or has_multi):
                    continue

        filtered.append(item)

    sort_key = str(f.get("sort") or "collected_desc")
    if sort_key == "collected_asc":
        filtered.sort(key=lambda x: x["collected_at"])
    elif sort_key == "grams_asc":
        filtered.sort(key=lambda x: (x["filament_grams"] is None, x["filament_grams"] or 0))
    elif sort_key == "grams_desc":
        filtered.sort(key=lambda x: (x["filament_grams"] is None, -(x["filament_grams"] or 0)))
    elif sort_key == "size_asc":
        filtered.sort(key=lambda x: (x["max_dimension_mm"] is None, x["max_dimension_mm"] or 0))
    elif sort_key == "size_desc":
        filtered.sort(key=lambda x: (x["max_dimension_mm"] is None, -(x["max_dimension_mm"] or 0)))
    else:
        filtered.sort(key=lambda x: x["collected_at"], reverse=True)

    total_count = len(filtered)
    total_grams = round(sum(float(i["filament_grams"] or 0) for i in filtered), 1)
    na_fila = sum(1 for i in filtered if i["status"] == "Na Fila")
    multicolor_count = sum(1 for i in filtered if MULTICOLOR_LABEL in i["recommended_colors"])

    raw_limit = f.get("limit")
    limit = int(raw_limit) if raw_limit not in (None, "", 0, "0") else None
    offset = max(0, int(f.get("offset") or 0))

    if limit is not None and limit > 0:
        paged = filtered[offset : offset + limit]
        has_more = (offset + len(paged)) < total_count
    else:
        paged = filtered[offset:] if offset > 0 else filtered
        has_more = False

    return {
        "items": paged,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "total_filament_grams": total_grams,
        "stats": {
            "na_fila": na_fila,
            "multicolor": multicolor_count,
        },
    }
