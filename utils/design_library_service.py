"""Persistence helpers for the design department library.

The imported images remain files because they are large binary assets.  The
editable metadata lives in MySQL so the four design pages can share the same
records, permissions and backup strategy as the rest of the application.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from weakref import WeakSet

from PIL import Image, ImageOps
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from utils import import_service


LOGGER = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent / "data" / "design-data"
CATALOG_PATH = DATA / "catalog.json"
IMAGE_DIR = DATA / "images"
ITEM_TYPES = ("models", "prompts", "comparisons", "styles")
_READY_ENGINES: WeakSet[Engine] = WeakSet()
_READY_LOCK = Lock()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS design_library_item (
    id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    item_type VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    body LONGTEXT NOT NULL,
    product VARCHAR(64) NOT NULL DEFAULT '',
    scene VARCHAR(64) NOT NULL DEFAULT '',
    category VARCHAR(64) NOT NULL DEFAULT '',
    images_json LONGTEXT NULL,
    original_url VARCHAR(1024) NULL,
    generated_url VARCHAR(1024) NULL,
    source VARCHAR(512) NOT NULL DEFAULT '手动新增',
    sort_order INT NOT NULL DEFAULT 0,
    created_by VARCHAR(191) NOT NULL DEFAULT '',
    updated_by VARCHAR(191) NOT NULL DEFAULT '',
    deleted_by VARCHAR(191) NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_design_item_type (item_type, sort_order, id),
    KEY idx_design_deleted (deleted_at, item_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CREATE_META_SQL = """
CREATE TABLE IF NOT EXISTS design_library_meta (
    meta_key VARCHAR(64) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _engine(engine: Engine | None = None) -> Engine:
    return engine or import_service.get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    """Create the additive table when an older deployment first uses this module."""

    selected = _engine(engine)
    with selected.begin() as connection:
        connection.execute(text(CREATE_TABLE_SQL))
        connection.execute(text(CREATE_META_SQL))
    columns = {column["name"] for column in inspect(selected).get_columns("design_library_item")}
    for column in ("deleted_by", "deleted_at"):
        if column not in columns:
            definition = "VARCHAR(191) NULL" if column == "deleted_by" else "DATETIME NULL"
            try:
                with selected.begin() as connection:
                    connection.execute(text(f"ALTER TABLE design_library_item ADD COLUMN {column} {definition}"))
            except SQLAlchemyError:
                if column not in {item["name"] for item in inspect(selected).get_columns("design_library_item")}:
                    raise
    indexes = {index["name"] for index in inspect(selected).get_indexes("design_library_item")}
    if "idx_design_deleted" not in indexes:
        try:
            with selected.begin() as connection:
                connection.execute(text("ALTER TABLE design_library_item ADD KEY idx_design_deleted (deleted_at, item_type)"))
        except SQLAlchemyError:
            if "idx_design_deleted" not in {index["name"] for index in inspect(selected).get_indexes("design_library_item")}:
                raise


def _catalog_payload() -> dict[str, Any]:
    if not CATALOG_PATH.is_file():
        return {"models": [], "prompts": [], "comparisons": [], "styles": [], "sources": []}
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("[design-library] 读取旧资料目录失败: %s", exc)
        return {"models": [], "prompts": [], "comparisons": [], "styles": [], "sources": []}
    return payload if isinstance(payload, dict) else {}


def _normalise_images(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:8]


def _row_values(item: dict[str, Any], *, user_name: str, sort_order: int | None = None) -> dict[str, Any]:
    item_type = str(item.get("item_type") or "").strip()
    images = _normalise_images(item.get("images"))
    raw_order = item.get("sort_order") if sort_order is None else sort_order
    return {
        "id": str(item.get("id") or "").strip(),
        "item_type": item_type,
        "title": str(item.get("title") or "").strip(),
        "body": str(item.get("text") or ""),
        "product": str(item.get("product") or "").strip(),
        "scene": str(item.get("scene") or "").strip(),
        "category": str(item.get("category") or "").strip(),
        "images_json": json.dumps(images, ensure_ascii=False),
        "original_url": str(item.get("original") or "").strip() or None,
        "generated_url": str(item.get("generated") or "").strip() or None,
        "source": str(item.get("source") or "手动新增").strip() or "手动新增",
        "sort_order": int(raw_order or 0),
        "user_name": user_name,
    }


def _seed_if_empty(engine: Engine) -> None:
    with engine.begin() as connection:
        seeded = connection.execute(text(
            "SELECT 1 FROM design_library_meta WHERE meta_key = 'legacy_catalog_seeded'"
        )).scalar()
        if seeded:
            return
        count = int(connection.execute(text("SELECT COUNT(*) FROM design_library_item")).scalar() or 0)
        if count:
            connection.execute(text(
                "INSERT IGNORE INTO design_library_meta (meta_key) VALUES ('legacy_catalog_seeded')"
            ))
            return
        payload = _catalog_payload()
        rows: list[dict[str, Any]] = []
        for item_type in ITEM_TYPES:
            for index, item in enumerate(payload.get(item_type) or []):
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row["item_type"] = item_type
                rows.append(_row_values(row, user_name="system-import", sort_order=index))
        if rows:
            connection.execute(
                text(
                    """
                    INSERT IGNORE INTO design_library_item
                    (id, item_type, title, body, product, scene, category, images_json,
                     original_url, generated_url, source, sort_order, created_by, updated_by)
                    VALUES
                    (:id, :item_type, :title, :body, :product, :scene, :category, :images_json,
                     :original_url, :generated_url, :source, :sort_order, :user_name, :user_name)
                    """
                ),
                rows,
            )
            LOGGER.info("[design-library] seeded %d imported records into MySQL", len(rows))
        connection.execute(text(
            "INSERT IGNORE INTO design_library_meta (meta_key) VALUES ('legacy_catalog_seeded')"
        ))


def ensure_ready(engine: Engine | None = None) -> Engine:
    selected = _engine(engine)
    if selected not in _READY_ENGINES:
        with _READY_LOCK:
            if selected not in _READY_ENGINES:
                ensure_schema(selected)
                _seed_if_empty(selected)
                _READY_ENGINES.add(selected)
    return selected


def _decode_images(value: Any) -> list[str]:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return _normalise_images(decoded)


def _serialize(row: Any) -> dict[str, Any]:
    item_type = str(row["item_type"])
    item: dict[str, Any] = {
        "id": row["id"],
        "title": row["title"],
        "text": row["body"],
        "images": _decode_images(row["images_json"]),
        "product": row["product"] or "",
        "scene": row["scene"] or "",
        "category": row["category"] or "",
        "source": row["source"] or "手动新增",
    }
    if item_type == "comparisons":
        item["original"] = row["original_url"] or None
        item["generated"] = row["generated_url"] or None
    if "deleted_at" in row and row["deleted_at"] is not None:
        item["item_type"] = item_type
        item["deleted_by"] = row["deleted_by"] or ""
        deleted_at = row["deleted_at"]
        item["deleted_at"] = deleted_at.isoformat(sep=" ") if hasattr(deleted_at, "isoformat") else str(deleted_at)
    return item


def catalog(engine: Engine | None = None) -> dict[str, Any]:
    selected = ensure_ready(engine)
    with selected.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, item_type, title, body, product, scene, category, images_json,
                       original_url, generated_url, source
                FROM design_library_item
                WHERE deleted_at IS NULL
                ORDER BY item_type, sort_order, id
                """
            )
        ).mappings().all()
    result: dict[str, Any] = {"version": 2, "models": [], "prompts": [], "comparisons": [], "styles": [], "sources": []}
    for row in rows:
        item_type = str(row["item_type"])
        if item_type in ITEM_TYPES:
            result[item_type].append(_serialize(row))
        source = str(row["source"] or "").strip()
        if source and source not in result["sources"]:
            result["sources"].append(source)
    return result


def get_item(item_type: str, item_id: str, engine: Engine | None = None) -> dict[str, Any] | None:
    selected = ensure_ready(engine)
    with selected.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id, item_type, title, body, product, scene, category, images_json,
                       original_url, generated_url, source
                FROM design_library_item
                WHERE item_type = :item_type AND id = :id AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"item_type": item_type, "id": item_id},
        ).mappings().fetchone()
    return _serialize(row) if row else None


def create_item(payload: dict[str, Any], *, user_name: str, engine: Engine | None = None) -> dict[str, Any]:
    selected = ensure_ready(engine)
    item_type = str(payload["item_type"])
    item_id = f"design-{item_type}-{uuid.uuid4().hex[:16]}"
    row = _row_values({**payload, "id": item_id}, user_name=user_name)
    with selected.begin() as connection:
        min_order = connection.execute(
            text("SELECT COALESCE(MIN(sort_order), 0) FROM design_library_item WHERE item_type = :item_type"),
            {"item_type": item_type},
        ).scalar()
        # Lower sort_order values are rendered first.  Put each new record
        # before the current head so newly added design material is visible
        # immediately instead of being appended to the end of the page.
        row["sort_order"] = int(min_order or 0) - 1
        connection.execute(
            text(
                """
                INSERT INTO design_library_item
                (id, item_type, title, body, product, scene, category, images_json,
                 original_url, generated_url, source, sort_order, created_by, updated_by)
                VALUES
                (:id, :item_type, :title, :body, :product, :scene, :category, :images_json,
                 :original_url, :generated_url, :source, :sort_order, :user_name, :user_name)
                """
            ),
            row,
        )
    return get_item(item_type, item_id, selected) or {}


def update_item(item_type: str, item_id: str, payload: dict[str, Any], *, user_name: str, engine: Engine | None = None) -> dict[str, Any]:
    selected = ensure_ready(engine)
    values = _row_values(payload, user_name=user_name)
    values.update({"item_type": item_type, "id": item_id})
    with selected.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE design_library_item
                SET title = :title, body = :body, product = :product, scene = :scene,
                    category = :category, images_json = :images_json,
                    original_url = :original_url, generated_url = :generated_url,
                    updated_by = :user_name
                WHERE item_type = :item_type AND id = :id AND deleted_at IS NULL
                """
            ),
            values,
        )
        if result.rowcount != 1:
            return {}
    return get_item(item_type, item_id, selected) or {}


def trash_items(engine: Engine | None = None) -> list[dict[str, Any]]:
    selected = ensure_ready(engine)
    with selected.connect() as connection:
        rows = connection.execute(text("""
            SELECT id, item_type, title, body, product, scene, category, images_json,
                   original_url, generated_url, source, deleted_by, deleted_at
            FROM design_library_item WHERE deleted_at IS NOT NULL
            ORDER BY deleted_at DESC, id
        """)).mappings().all()
    return [_serialize(row) for row in rows]


def image_is_visible(
    url: str, allowed_types: set[str], *, admin: bool, engine: Engine | None = None
) -> bool:
    """Check image references without loading the full active and deleted catalog."""
    selected = ensure_ready(engine)
    with selected.connect() as connection:
        rows = connection.execute(text("""
            SELECT item_type, deleted_at FROM design_library_item
            WHERE images_json LIKE :needle OR original_url = :url OR generated_url = :url
        """), {"needle": f'%"{url}"%', "url": url}).mappings().all()
    return any(
        (row["deleted_at"] is None and row["item_type"] in allowed_types)
        or (row["deleted_at"] is not None and admin)
        for row in rows
    )


def delete_item(item_type: str, item_id: str, *, user_name: str, engine: Engine | None = None) -> bool:
    """Move a visible record into the recycle bin without deleting its images."""

    selected = ensure_ready(engine)
    with selected.begin() as connection:
        result = connection.execute(
            text("""UPDATE design_library_item SET deleted_at = CURRENT_TIMESTAMP,
                   deleted_by = :user_name WHERE item_type = :item_type AND id = :id
                   AND deleted_at IS NULL"""),
            {"item_type": item_type, "id": item_id, "user_name": user_name},
        )
        return result.rowcount == 1


def restore_item(item_type: str, item_id: str, engine: Engine | None = None) -> bool:
    selected = ensure_ready(engine)
    with selected.begin() as connection:
        result = connection.execute(text("""
            UPDATE design_library_item SET deleted_at = NULL, deleted_by = NULL
            WHERE item_type = :item_type AND id = :id AND deleted_at IS NOT NULL
        """), {"item_type": item_type, "id": item_id})
        return result.rowcount == 1


def purge_item(item_type: str, item_id: str, engine: Engine | None = None) -> bool:
    """Permanently delete a trashed record; shared image files remain untouched."""
    selected = ensure_ready(engine)
    with selected.begin() as connection:
        result = connection.execute(text("""
            DELETE FROM design_library_item
            WHERE item_type = :item_type AND id = :id AND deleted_at IS NOT NULL
        """), {"item_type": item_type, "id": item_id})
        return result.rowcount == 1


def save_image(raw: bytes) -> str:
    """Validate, normalize and store an uploaded image, returning its API URL."""

    if not raw or len(raw) > 15 * 1024 * 1024:
        raise ValueError("图片不能为空且不能超过 15MB")
    try:
        with Image.open(BytesIO(raw)) as source:
            source = ImageOps.exif_transpose(source)
            source.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            image = source.convert("RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=90, method=6)
            normalized = output.getvalue()
    except Exception as exc:
        raise ValueError("上传文件不是可识别的图片") from exc

    digest = hashlib.sha256(normalized).hexdigest()[:20]
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = IMAGE_DIR / f"{digest}.webp"
    if not target.exists():
        target.write_bytes(normalized)
    return f"/api/design/image/{target.name}"
