"""SKU stock warning: forecast from inventory snapshot vs Jushuitan stock.

The forecast is intentionally inventory-table based. For each SKU we sum the
per-warehouse daily sales produced by inventory_service._forecast_daily_sales
and multiply the total by the configurable safety-period days. Jushuitan stock
is the latest supply-hub stock_qty across 花东仓 and 南沙仓.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import Engine, text

from utils import import_service, inventory_service


FORECAST_DAYS = 60
SUPPLY_WAREHOUSES = (
    inventory_service.SUPPLY_HUB_WAREHOUSE,
    inventory_service.NANSHA_SUPPLY_WAREHOUSE,
)

STATUS_SHORTAGE = "SHORTAGE"
STATUS_SAFE = "SAFE"
STATUS_NO_JUSHUITAN = "NO_JUSHUITAN"

VIEW_SHORTAGE = "shortage"
VIEW_SAFE = "safe"
VIEW_ALL = "all"

_STATUS_PRIORITY = {
    STATUS_SHORTAGE: 0,
    STATUS_NO_JUSHUITAN: 1,
    STATUS_SAFE: 2,
}

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS inv_sku_warning_forecast (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    snapshot_date DATE NOT NULL COMMENT 'Inventory snapshot date',
    sku_code VARCHAR(64) NOT NULL COMMENT 'SKU code',
    product_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'Product name',
    brand VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Brand',
    category VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Category',
    warehouse_count INT NOT NULL DEFAULT 0 COMMENT 'Warehouse rows used',
    daily_sales DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'Daily sales sum across warehouses',
    predicted_60d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'Predicted 60-day sales',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (id),
    UNIQUE KEY uk_inv_sku_warning_date_sku (snapshot_date, sku_code),
    KEY idx_inv_sku_warning_date (snapshot_date),
    KEY idx_inv_sku_warning_brand (snapshot_date, brand),
    KEY idx_inv_sku_warning_category (snapshot_date, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU stock warning forecast table'
"""

_SETTING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS inv_sku_warning_setting (
    id TINYINT NOT NULL DEFAULT 1 COMMENT 'Fixed primary key',
    forecast_days INT NOT NULL DEFAULT 60 COMMENT 'Safety period in days',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU stock warning safety period setting'
"""


def get_engine(engine: Engine | None = None) -> Engine:
    return engine or import_service.get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    db_engine = get_engine(engine)
    with db_engine.begin() as conn:
        conn.execute(text(_TABLE_DDL))
        conn.execute(text(_SETTING_TABLE_DDL))
        conn.execute(
            text(
                """
                INSERT IGNORE INTO inv_sku_warning_setting (id, forecast_days)
                VALUES (1, :forecast_days)
                """
            ),
            {"forecast_days": FORECAST_DAYS},
        )


def _resolve_snapshot_date(
    db_engine: Engine,
    value: str | date | None,
) -> date | None:
    if value:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(snapshot_date) FROM inv_stock_snapshot")
        ).scalar()


def _resolve_warning_date(
    db_engine: Engine,
    value: str | date | None,
) -> date | None:
    if value:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(snapshot_date) FROM inv_sku_warning_forecast")
        ).scalar()


def _load_sku_meta(db_engine: Engine) -> dict[str, dict[str, Any]]:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT sku_code, product_name, brand, category
                FROM inv_sku
                """
            )
        ).mappings().all()
    return {
        str(row["sku_code"]): {
            "product_name": str(row.get("product_name") or "").strip(),
            "brand": str(row.get("brand") or "").strip(),
            "category": str(row.get("category") or "").strip(),
        }
        for row in rows
        if row.get("sku_code")
    }


def _execute_chunks(
    conn: Any,
    sql: Any,
    rows: list[dict[str, Any]],
    chunk_size: int = 500,
) -> None:
    for start in range(0, len(rows), chunk_size):
        conn.execute(sql, rows[start : start + chunk_size])


def get_sku_warning_setting(engine: Engine | None = None) -> dict[str, int]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT forecast_days
                FROM inv_sku_warning_setting
                WHERE id=1
                """
            )
        ).mappings().fetchone()
    return {"forecast_days": int(row["forecast_days"]) if row else FORECAST_DAYS}


def save_sku_warning_setting(
    forecast_days: int,
    engine: Engine | None = None,
) -> dict[str, int]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    clean_days = max(1, min(365, int(forecast_days or FORECAST_DAYS)))
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO inv_sku_warning_setting (id, forecast_days, updated_at)
                VALUES (1, :forecast_days, NOW())
                ON DUPLICATE KEY UPDATE
                    forecast_days=VALUES(forecast_days),
                    updated_at=NOW()
                """
            ),
            {"forecast_days": clean_days},
        )
    return {"forecast_days": clean_days}


def _resolve_forecast_days(
    db_engine: Engine,
    value: int | None,
) -> int:
    if value is not None:
        try:
            return max(1, min(365, int(value)))
        except (TypeError, ValueError):
            pass
    return get_sku_warning_setting(db_engine)["forecast_days"]


def recalculate_sku_warnings(
    snapshot_date: str | date | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    target_date = _resolve_snapshot_date(db_engine, snapshot_date)
    if not target_date:
        return {
            "skipped": True,
            "reason": "NO_INVENTORY_SNAPSHOT",
            "snapshot_date": None,
        }

    with db_engine.connect() as conn:
        snapshot_rows = conn.execute(
            text(
                """
                SELECT sku_code, warehouse_code, sales_1d, sales_7d, sales_30d
                FROM inv_stock_snapshot
                WHERE snapshot_date=:snapshot_date
                """
            ),
            {"snapshot_date": target_date},
        ).mappings().all()

    daily_by_sku: dict[str, float] = defaultdict(float)
    warehouse_count_by_sku: dict[str, int] = defaultdict(int)
    for raw_row in snapshot_rows:
        row = dict(raw_row)
        daily = inventory_service._forecast_daily_sales(row)["daily_sales"]
        sku_code = str(row.get("sku_code") or "")
        if not sku_code:
            continue
        daily_by_sku[sku_code] += daily
        warehouse_count_by_sku[sku_code] += 1

    sku_codes = sorted(daily_by_sku)
    if not sku_codes:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM inv_sku_warning_forecast WHERE snapshot_date=:snapshot_date"
                ),
                {"snapshot_date": target_date},
            )
        return {
            "snapshot_date": target_date.isoformat(),
            "forecast_sku_count": 0,
            "warehouse_count": 0,
            "recalculated": True,
        }

    sku_meta = _load_sku_meta(db_engine)
    forecast_rows: list[dict[str, Any]] = []
    for sku_code in sku_codes:
        daily_sales = daily_by_sku[sku_code]
        meta = sku_meta.get(sku_code, {})
        forecast_rows.append(
            {
                "snapshot_date": target_date,
                "sku_code": sku_code,
                "product_name": meta.get("product_name", ""),
                "brand": meta.get("brand", ""),
                "category": meta.get("category", ""),
                "warehouse_count": int(warehouse_count_by_sku[sku_code]),
                "daily_sales": round(daily_sales, 4),
                "predicted_60d": round(daily_sales * FORECAST_DAYS, 4),
            }
        )

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM inv_sku_warning_forecast WHERE snapshot_date=:snapshot_date"
            ),
            {"snapshot_date": target_date},
        )
        _execute_chunks(
            conn,
            text(
                """
                INSERT INTO inv_sku_warning_forecast (
                    snapshot_date, sku_code, product_name, brand, category,
                    warehouse_count, daily_sales, predicted_60d, created_at, updated_at
                )
                VALUES (
                    :snapshot_date, :sku_code, :product_name, :brand, :category,
                    :warehouse_count, :daily_sales, :predicted_60d, NOW(), NOW()
                )
                """
            ),
            forecast_rows,
        )

    return {
        "snapshot_date": target_date.isoformat(),
        "forecast_sku_count": len(forecast_rows),
        "warehouse_count": sum(int(row["warehouse_count"]) for row in forecast_rows),
        "recalculated": True,
    }


def get_sku_warning_options(engine: Engine | None = None) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.connect() as conn:
        dates = [
            row["snapshot_date"].isoformat()
            for row in conn.execute(
                text(
                    """
                    SELECT DISTINCT snapshot_date
                    FROM inv_sku_warning_forecast
                    ORDER BY snapshot_date DESC
                    """
                )
            ).mappings().all()
            if row.get("snapshot_date")
        ]
        latest_date = dates[0] if dates else None
        brands: list[str] = []
        categories: list[str] = []
        if latest_date:
            brand_rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT brand
                    FROM inv_sku_warning_forecast
                    WHERE snapshot_date=:snapshot_date AND brand<>''
                    ORDER BY brand
                    """
                ),
                {"snapshot_date": latest_date},
            ).mappings().all()
            category_rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT category
                    FROM inv_sku_warning_forecast
                    WHERE snapshot_date=:snapshot_date AND category<>''
                    ORDER BY category
                    """
                ),
                {"snapshot_date": latest_date},
            ).mappings().all()
            brands = [str(row["brand"]) for row in brand_rows if row.get("brand")]
            categories = [str(row["category"]) for row in category_rows if row.get("category")]

    return {
        "snapshot_dates": dates,
        "latest_snapshot_date": latest_date,
        "brands": brands,
        "categories": categories,
        "forecast_days": get_sku_warning_setting(db_engine)["forecast_days"],
    }


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_latest_supply_stock_by_sku(
    db_engine: Engine,
) -> tuple[dict[str, float], str | None]:
    supply_stocks = inventory_service._latest_supply_stocks_by_warehouse(db_engine)
    stock_by_sku: dict[str, float] = defaultdict(float)
    latest_time: str | None = None
    for (warehouse_code, sku_code), row in supply_stocks.items():
        if warehouse_code not in SUPPLY_WAREHOUSES:
            continue
        stock_by_sku[str(sku_code)] += _to_float(row.get("stock_qty"))
        snapshot_time = row.get("snapshot_time")
        if snapshot_time is not None:
            text_time = str(snapshot_time)
            if latest_time is None or text_time > latest_time:
                latest_time = text_time
    return dict(stock_by_sku), latest_time


def _warning_status(predicted_sales: float, stock_qty: float | None) -> str:
    if stock_qty is None:
        return STATUS_NO_JUSHUITAN
    if predicted_sales > stock_qty:
        return STATUS_SHORTAGE
    return STATUS_SAFE


def list_sku_warnings(
    engine: Engine | None = None,
    snapshot_date: str | None = None,
    view: str = VIEW_SHORTAGE,
    sku_code: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    forecast_days: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    active_days = _resolve_forecast_days(db_engine, forecast_days)
    target_date = _resolve_warning_date(db_engine, snapshot_date)
    normalized_view = view if view in {VIEW_SHORTAGE, VIEW_SAFE, VIEW_ALL} else VIEW_SHORTAGE
    clean_page = max(1, int(page or 1))
    clean_page_size = min(200, max(1, int(page_size or 20)))

    empty_result: dict[str, Any] = {
        "items": [],
        "total": 0,
        "page": clean_page,
        "page_size": clean_page_size,
        "snapshot_date": target_date.isoformat() if target_date else None,
        "forecast_days": active_days,
        "summary": {
            "total": 0,
            "shortage_count": 0,
            "safe_count": 0,
            "no_jushuitan_count": 0,
        },
    }
    if not target_date:
        return empty_result

    with db_engine.connect() as conn:
        forecast_rows = conn.execute(
            text(
                """
                SELECT snapshot_date, sku_code, product_name, brand, category,
                       warehouse_count, daily_sales, predicted_60d
                FROM inv_sku_warning_forecast
                WHERE snapshot_date=:snapshot_date
                """
            ),
            {"snapshot_date": target_date},
        ).mappings().all()

    stock_by_sku, latest_supply_time = _load_latest_supply_stock_by_sku(db_engine)
    row_brands = sorted(
        {
            str(row.get("brand") or "").strip()
            for row in forecast_rows
            if str(row.get("brand") or "").strip()
        }
    )
    row_categories = sorted(
        {
            str(row.get("category") or "").strip()
            for row in forecast_rows
            if str(row.get("category") or "").strip()
        }
    )
    sku_text = str(sku_code or "").strip()
    product_text = str(product_name or "").strip()
    brand_text = str(brand or "").strip()
    category_text = str(category or "").strip()

    items: list[dict[str, Any]] = []
    summary = {"total": 0, "shortage_count": 0, "safe_count": 0, "no_jushuitan_count": 0}
    for raw_row in forecast_rows:
        row = dict(raw_row)
        sku = str(row.get("sku_code") or "")
        if not sku:
            continue
        if sku_text and sku_text not in sku:
            continue
        if product_text and product_text not in str(row.get("product_name") or ""):
            continue
        if brand_text and str(row.get("brand") or "").strip() != brand_text:
            continue
        if category_text and str(row.get("category") or "").strip() != category_text:
            continue

        daily_sales = _to_float(row.get("daily_sales"))
        predicted_sales = round(daily_sales * active_days, 1)
        has_jst = sku in stock_by_sku
        jst_stock_qty = round(stock_by_sku[sku], 2) if has_jst else None
        status = _warning_status(predicted_sales, jst_stock_qty)
        shortage_qty = (
            math.ceil(max(0.0, predicted_sales - jst_stock_qty))
            if has_jst and predicted_sales > jst_stock_qty
            else None
        )

        summary["total"] += 1
        if status == STATUS_SHORTAGE:
            summary["shortage_count"] += 1
        elif status == STATUS_SAFE:
            summary["safe_count"] += 1
        else:
            summary["no_jushuitan_count"] += 1

        if normalized_view == VIEW_SHORTAGE and status == STATUS_SAFE:
            continue
        if normalized_view == VIEW_SAFE and status != STATUS_SAFE:
            continue

        items.append(
            {
                "snapshot_date": row.get("snapshot_date").isoformat()
                if hasattr(row.get("snapshot_date"), "isoformat")
                else str(row.get("snapshot_date") or ""),
                "sku_code": sku,
                "product_name": str(row.get("product_name") or ""),
                "brand": str(row.get("brand") or ""),
                "category": str(row.get("category") or ""),
                "warehouse_count": int(row.get("warehouse_count") or 0),
                "daily_sales": round(daily_sales, 4),
                "predicted_sales": predicted_sales,
                "jst_stock_qty": jst_stock_qty,
                "shortage_qty": shortage_qty,
                "status": status,
            }
        )

    items.sort(
        key=lambda item: (
            _STATUS_PRIORITY.get(item["status"], 99),
            -(item["shortage_qty"] or 0),
            -(item["predicted_sales"] or 0),
            item["sku_code"],
        )
    )
    total = len(items)
    offset = (clean_page - 1) * clean_page_size
    return {
        "items": items[offset : offset + clean_page_size],
        "total": total,
        "page": clean_page,
        "page_size": clean_page_size,
        "snapshot_date": target_date.isoformat(),
        "forecast_days": active_days,
        "jst_snapshot_time": latest_supply_time,
        "summary": summary,
        "brands": row_brands,
        "categories": row_categories,
    }
