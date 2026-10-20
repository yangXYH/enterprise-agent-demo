"""Import and query the supply-chain sales dashboard snapshot."""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
import uuid

import httpx
from openpyxl import load_workbook
from sqlalchemy import Engine, bindparam, text

from utils import import_service


_BATCH_DDL = """
CREATE TABLE IF NOT EXISTS sales_dashboard_import_batch (
    batch_id VARCHAR(32) NOT NULL,
    source_name VARCHAR(255) NOT NULL DEFAULT '',
    row_count INT NOT NULL DEFAULT 0,
    imported_by VARCHAR(64) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售数据看板导入批次'
"""

_ITEM_DDL = """
CREATE TABLE IF NOT EXISTS sales_dashboard_item (
    id BIGINT NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(32) NOT NULL,
    source_row INT NOT NULL,
    image_url TEXT,
    product_code VARCHAR(128) NOT NULL,
    product_name TEXT NOT NULL,
    category VARCHAR(128) NOT NULL DEFAULT '',
    brand VARCHAR(128) NOT NULL DEFAULT '',
    sales_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    shipped_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    returned_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sales_dashboard_source (batch_id, source_row),
    KEY idx_sales_dashboard_code (product_code),
    KEY idx_sales_dashboard_category (category),
    KEY idx_sales_dashboard_brand (brand)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售数据看板当前快照'
"""

EXPECTED_HEADERS = (
    "图片",
    "款式编码/商品编码",
    "款式名称/商品名称",
    "产品分类",
    "商品品牌",
    "销售数量",
    "实发数量",
    "实退数量",
)


def get_engine(engine: Engine | None = None) -> Engine:
    return engine or import_service.get_engine()


# The spreadsheet contains URLs from the ERP image CDN.  Keep the original
# URL in the database, but serve it through this application so the browser
# does not have to reach the CDN directly.  This also makes already-imported
# rows compatible with the proxy endpoint without requiring a re-import.
IMAGE_ROOT = Path(__file__).resolve().parent.parent / "uploads" / "sales"
IMAGE_MAX_BYTES = 15 * 1024 * 1024
IMAGE_TIMEOUT_SECONDS = 20.0
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


def ensure_schema(engine: Engine | None = None) -> None:
    db_engine = get_engine(engine)
    with db_engine.begin() as conn:
        conn.execute(text(_BATCH_DDL))
        conn.execute(text(_ITEM_DDL))


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _normalise_headers(values: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(_clean(value).replace(" ", "") for value in values)


def _read_sales_rows(path: str | Path) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        worksheet.reset_dimensions()
        rows = worksheet.iter_rows(values_only=True)
        headers = _normalise_headers(next(rows, ()))
        header_index = {header: index for index, header in enumerate(headers)}
        missing = [header for header in EXPECTED_HEADERS if header not in header_index]
        if missing:
            raise ValueError(f"不是可识别的销售主题分析表，缺少字段：{'、'.join(missing)}")

        items: list[dict[str, Any]] = []
        for source_row, values in enumerate(rows, start=2):
            if not any(value is not None and _clean(value) for value in values):
                continue
            get_value = lambda header: values[header_index[header]] if header_index[header] < len(values) else None
            product_code = _clean(get_value("款式编码/商品编码"))
            if not product_code:
                continue
            product_name = _clean(get_value("款式名称/商品名称"))
            category = _clean(get_value("产品分类"))
            brand = _clean(get_value("商品品牌"))
            if product_code in {"#", "合计", "总计"} and not any((product_name, category, brand)):
                continue
            items.append(
                {
                    "source_row": source_row,
                    "image_url": _clean(get_value("图片")),
                    "product_code": product_code,
                    "product_name": product_name,
                    "category": category,
                    "brand": brand,
                    "sales_quantity": _number(get_value("销售数量")),
                    "shipped_quantity": _number(get_value("实发数量")),
                    "returned_quantity": _number(get_value("实退数量")),
                }
            )
    finally:
        workbook.close()

    if not items:
        raise ValueError("销售主题分析表未读取到有效数据")
    return items


def import_excel(
    path: str | Path,
    source_name: str = "",
    imported_by: str = "",
    engine: Engine | None = None,
) -> dict[str, Any]:
    source_path = Path(path)
    items = _read_sales_rows(source_path)
    batch_id = uuid.uuid4().hex
    imported_at = datetime.now()
    payload = [
        {
            **item,
            "batch_id": batch_id,
            "imported_at": imported_at,
        }
        for item in items
    ]

    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM sales_dashboard_item"))
        conn.execute(text("DELETE FROM sales_dashboard_import_batch"))
        conn.execute(
            text(
                """
                INSERT INTO sales_dashboard_import_batch
                    (batch_id, source_name, row_count, imported_by, imported_at)
                VALUES
                    (:batch_id, :source_name, :row_count, :imported_by, :imported_at)
                """
            ),
            {
                "batch_id": batch_id,
                "source_name": (source_name or source_path.name)[:255],
                "row_count": len(items),
                "imported_by": _clean(imported_by)[:64],
                "imported_at": imported_at,
            },
        )
        for start in range(0, len(payload), 500):
            conn.execute(
                text(
                    """
                    INSERT INTO sales_dashboard_item (
                        batch_id, source_row, image_url, product_code, product_name,
                        category, brand, sales_quantity, shipped_quantity,
                        returned_quantity, imported_at
                    ) VALUES (
                        :batch_id, :source_row, :image_url, :product_code, :product_name,
                        :category, :brand, :sales_quantity, :shipped_quantity,
                        :returned_quantity, :imported_at
                    )
                    """
                ),
                payload[start : start + 500],
            )

    return {
        "batch_id": batch_id,
        "source_name": source_name or source_path.name,
        "row_count": len(items),
        "imported_at": imported_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _where_clause(
    keyword: str,
    brands: list[str] | None,
    categories: list[str] | None,
) -> tuple[str, dict[str, Any], list[Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    bind_params: list[Any] = []
    clean_keyword = _clean(keyword)
    if clean_keyword:
        clauses.append(
            "(product_code LIKE :keyword OR product_name LIKE :keyword "
            "OR category LIKE :keyword OR brand LIKE :keyword)"
        )
        params["keyword"] = f"%{clean_keyword}%"
    clean_brands = [item.strip() for item in (brands or []) if item and item.strip()]
    if clean_brands:
        clauses.append("brand IN :brands")
        params["brands"] = clean_brands
        bind_params.append(bindparam("brands", expanding=True))
    clean_categories = [item.strip() for item in (categories or []) if item and item.strip()]
    if clean_categories:
        clauses.append("category IN :categories")
        params["categories"] = clean_categories
        bind_params.append(bindparam("categories", expanding=True))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params, bind_params


def list_dashboard(
    keyword: str = "",
    brands: list[str] | None = None,
    categories: list[str] | None = None,
    page: int = 1,
    page_size: int = 50,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    page = max(1, int(page))
    page_size = min(200, max(10, int(page_size)))
    where_sql, params, bind_params = _where_clause(keyword, brands, categories)
    offset = (page - 1) * page_size

    def stmt(sql: str):
        statement = text(sql)
        return statement.bindparams(*bind_params) if bind_params else statement

    with db_engine.connect() as conn:
        batch = conn.execute(
            text(
                "SELECT batch_id, source_name, row_count, imported_by, imported_at "
                "FROM sales_dashboard_import_batch ORDER BY imported_at DESC LIMIT 1"
            )
        ).mappings().fetchone()
        summary = conn.execute(
            stmt(
                """
                SELECT COUNT(*) AS row_count,
                       COUNT(DISTINCT product_code) AS sku_count,
                       COUNT(DISTINCT NULLIF(category, '')) AS category_count,
                       COUNT(DISTINCT NULLIF(brand, '')) AS brand_count,
                       COALESCE(SUM(sales_quantity), 0) AS sales_quantity,
                       COALESCE(SUM(shipped_quantity), 0) AS shipped_quantity,
                       COALESCE(SUM(returned_quantity), 0) AS returned_quantity
                FROM sales_dashboard_item
                """ + where_sql
            ),
            params,
        ).mappings().one()
        total = int(summary["row_count"] or 0)
        items = conn.execute(
            stmt(
                """
                SELECT id, batch_id, source_row, image_url, product_code,
                       product_name, category, brand, sales_quantity,
                       shipped_quantity, returned_quantity
                FROM sales_dashboard_item
                """ + where_sql + " ORDER BY sales_quantity DESC, product_code LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": offset},
        ).mappings().all()
        brand_options = [
            str(value)
            for value in conn.execute(
                text("SELECT DISTINCT brand FROM sales_dashboard_item WHERE brand <> '' ORDER BY brand")
            ).scalars()
        ]
        category_options = [
            str(value)
            for value in conn.execute(
                text("SELECT DISTINCT category FROM sales_dashboard_item WHERE category <> '' ORDER BY category")
            ).scalars()
        ]

    def serialise_row(row: Any) -> dict[str, Any]:
        item = dict(row)
        for key in ("sales_quantity", "shipped_quantity", "returned_quantity"):
            item[key] = float(item[key] or 0)
        image_url = _clean(item.get("image_url"))
        if image_url.startswith(("http://", "https://")):
            item["image_url"] = (
                f"/api/sales-dashboard/images/{item['batch_id']}/{item['source_row']}"
            )
        return item

    serialised_summary = {
        "row_count": int(summary["row_count"] or 0),
        "sku_count": int(summary["sku_count"] or 0),
        "category_count": int(summary["category_count"] or 0),
        "brand_count": int(summary["brand_count"] or 0),
        "sales_quantity": float(summary["sales_quantity"] or 0),
        "shipped_quantity": float(summary["shipped_quantity"] or 0),
        "returned_quantity": float(summary["returned_quantity"] or 0),
    }
    return {
        "batch": {
            **(dict(batch) if batch else {}),
            "imported_at": batch["imported_at"].strftime("%Y-%m-%d %H:%M:%S")
            if batch and batch["imported_at"]
            else "",
        },
        "summary": serialised_summary,
        "filter_options": {"brands": brand_options, "categories": category_options},
        "items": [serialise_row(row) for row in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _image_source_url(batch_id: str, source_row: int, engine: Engine | None = None) -> str:
    """Read the original image URL for one imported row."""

    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.connect() as conn:
        value = conn.execute(
            text(
                "SELECT image_url FROM sales_dashboard_item "
                "WHERE batch_id = :batch_id AND source_row = :source_row LIMIT 1"
            ),
            {"batch_id": batch_id, "source_row": source_row},
        ).scalar()
    return _clean(value)


def _cached_image_path(batch_id: str, source_url: str) -> Path:
    cache_key = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    return IMAGE_ROOT / batch_id / cache_key


def _is_allowed_image_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_image(
    batch_id: str,
    source_row: int,
    engine: Engine | None = None,
) -> tuple[Path, str] | None:
    """Return a cached sales image, fetching the trusted stored URL once."""

    if not re.fullmatch(r"[0-9a-f]{32}", batch_id.lower()):
        return None
    try:
        source_row = int(source_row)
    except (TypeError, ValueError):
        return None
    if source_row < 1:
        return None

    source_url = _image_source_url(batch_id, source_row, engine)
    if not _is_allowed_image_url(source_url):
        return None

    cache_path = _cached_image_path(batch_id, source_url)
    metadata_path = cache_path.with_suffix(".mime")
    if metadata_path.is_file():
        media_type = metadata_path.read_text(encoding="ascii").strip() or "image/*"
        suffix = IMAGE_EXTENSIONS.get(media_type, ".bin")
        final_path = cache_path.with_suffix(suffix)
        if final_path.is_file():
            return final_path, media_type

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(IMAGE_TIMEOUT_SECONDS),
            headers={
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "User-Agent": "EnterpriseAgent/1.0 image-proxy",
            },
        ) as client:
            response = client.get(source_url)
            response.raise_for_status()
            media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if not media_type.startswith("image/"):
                return None
            if len(response.content) > IMAGE_MAX_BYTES:
                return None
    except (httpx.HTTPError, OSError):
        return None

    suffix = IMAGE_EXTENSIONS.get(media_type, ".bin")
    final_path = cache_path.with_suffix(suffix)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    try:
        temp_path.write_bytes(response.content)
        temp_path.replace(final_path)
        metadata_path.write_text(media_type, encoding="ascii")
    except OSError:
        temp_path.unlink(missing_ok=True)
        return None
    return final_path, media_type
