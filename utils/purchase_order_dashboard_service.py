"""Import and query the purchase-order dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Any
import uuid

from openpyxl import load_workbook
from sqlalchemy import Engine, bindparam, text

from utils import import_service


_BATCH_DDL = """
CREATE TABLE IF NOT EXISTS purchase_order_dashboard_batch (
    batch_id VARCHAR(32) NOT NULL,
    source_name VARCHAR(255) NOT NULL DEFAULT '',
    date_start DATE NULL,
    date_end DATE NULL,
    row_count INT NOT NULL DEFAULT 0,
    order_count INT NOT NULL DEFAULT 0,
    image_count INT NOT NULL DEFAULT 0,
    imported_by VARCHAR(64) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id),
    KEY idx_purchase_order_batch_imported_at (imported_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采购单看板导入批次'
"""

_ITEM_DDL = """
CREATE TABLE IF NOT EXISTS purchase_order_dashboard_item (
    id BIGINT NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(32) NOT NULL,
    source_row INT NOT NULL,
    order_no VARCHAR(128) NOT NULL DEFAULT '',
    purchase_date DATETIME NULL,
    status VARCHAR(64) NOT NULL DEFAULT '',
    receiving_status VARCHAR(64) NOT NULL DEFAULT '',
    purchase_remark TEXT,
    receiving_address TEXT,
    purchase_type VARCHAR(128) NOT NULL DEFAULT '',
    warehouse_party VARCHAR(128) NOT NULL DEFAULT '',
    purchaser VARCHAR(128) NOT NULL DEFAULT '',
    review_date DATETIME NULL,
    last_modified_date DATETIME NULL,
    image_url TEXT,
    product_code VARCHAR(128) NOT NULL DEFAULT '',
    style_code VARCHAR(128) NOT NULL DEFAULT '',
    product_name TEXT,
    color_spec VARCHAR(255) NOT NULL DEFAULT '',
    pending_ship_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    available_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    received_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    variance_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    supplier_product_code VARCHAR(128) NOT NULL DEFAULT '',
    supplier_style_no VARCHAR(128) NOT NULL DEFAULT '',
    detail_no VARCHAR(128) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_purchase_order_source (batch_id, source_row),
    KEY idx_purchase_order_no (order_no),
    KEY idx_purchase_order_date (purchase_date),
    KEY idx_purchase_order_status (status),
    KEY idx_purchase_order_receiving_status (receiving_status),
    KEY idx_purchase_order_warehouse (warehouse_party),
    KEY idx_purchase_order_purchaser (purchaser)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采购单看板明细快照'
"""


EXPECTED_HEADERS = (
    "采购单号",
    "采购日期",
    "状态",
    "收货状态",
    "采购单备注",
    "收货地址",
    "采购单类型",
    "仓储方",
    "采购员",
    "审核日期",
    "最后修改日期",
    "图片",
    "商品编码",
    "款式编码",
    "商品名称",
    "颜色及规格",
    "订单待发数",
    "总可用数",
    "数量",
    "已入库数量",
    "差异数",
    "供应商商品编码",
    "供应商款号",
    "明细单号",
)

# Different exports from the same ERP occasionally shorten two labels. The
# canonical names returned by this module always stay aligned with the user's
# requested dashboard fields.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "颜色及规格": ("颜色及规格", "颜色规格"),
    "已入库数量": ("已入库数量", "已入库"),
    "最后修改日期": ("最后修改日期", "最后修改时间"),
    "明细单号": ("明细单号", "采购明细单号"),
}


def get_engine(engine: Engine | None = None) -> Engine:
    return engine or import_service.get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    db_engine = get_engine(engine)
    with db_engine.begin() as conn:
        conn.execute(text(_BATCH_DDL))
        conn.execute(text(_ITEM_DDL))


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        raw = _clean(value).replace(",", "")
        if raw.startswith("(") and raw.endswith(")"):
            raw = f"-{raw[1:-1]}"
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _normalise_header(value: Any) -> str:
    return re.sub(r"[\s\ufeff\u3000]+", "", _clean(value))


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raw = _clean(value)
    if not raw:
        return None
    for fmt in (
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _date_filter(value: str | None, label: str) -> str | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{label}必须是 YYYY-MM-DD") from exc


def _serialise_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return _clean(value)


def _header_index(values: tuple[Any, ...]) -> dict[str, int]:
    normalised = {_normalise_header(value): index for index, value in enumerate(values)}
    result: dict[str, int] = {}
    missing: list[str] = []
    for canonical in EXPECTED_HEADERS:
        aliases = HEADER_ALIASES.get(canonical, (canonical,))
        index = next((normalised.get(_normalise_header(alias)) for alias in aliases if _normalise_header(alias) in normalised), None)
        if index is None:
            missing.append(canonical)
        else:
            result[canonical] = index
    if missing:
        raise ValueError(f"不是可识别的采购单文件，缺少字段：{'、'.join(missing)}")
    return result


def _read_purchase_orders(path: str | Path) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        worksheet.reset_dimensions()
        rows = worksheet.iter_rows(values_only=True)
        header_values = next(rows, ())
        header_index = _header_index(header_values)

        records: list[dict[str, Any]] = []
        for source_row, values in enumerate(rows, start=2):
            if not any(value is not None and _clean(value) for value in values):
                continue

            def get_value(header: str) -> Any:
                index = header_index[header]
                return values[index] if index < len(values) else None

            order_no = _clean(get_value("采购单号"))
            product_code = _clean(get_value("商品编码"))
            detail_no = _clean(get_value("明细单号"))
            if not order_no and not product_code and not detail_no:
                continue

            records.append(
                {
                    "source_row": source_row,
                    "order_no": order_no,
                    "purchase_date": _as_datetime(get_value("采购日期")),
                    "status": _clean(get_value("状态")),
                    "receiving_status": _clean(get_value("收货状态")),
                    "purchase_remark": _clean(get_value("采购单备注")),
                    "receiving_address": _clean(get_value("收货地址")),
                    "purchase_type": _clean(get_value("采购单类型")),
                    "warehouse_party": _clean(get_value("仓储方")),
                    "purchaser": _clean(get_value("采购员")),
                    "review_date": _as_datetime(get_value("审核日期")),
                    "last_modified_date": _as_datetime(get_value("最后修改日期")),
                    "image_url": _clean(get_value("图片")),
                    "product_code": product_code,
                    "style_code": _clean(get_value("款式编码")),
                    "product_name": _clean(get_value("商品名称")),
                    "color_spec": _clean(get_value("颜色及规格")),
                    "pending_ship_quantity": _number(get_value("订单待发数")),
                    "available_quantity": _number(get_value("总可用数")),
                    "quantity": _number(get_value("数量")),
                    "received_quantity": _number(get_value("已入库数量")),
                    "variance_quantity": _number(get_value("差异数")),
                    "supplier_product_code": _clean(get_value("供应商商品编码")),
                    "supplier_style_no": _clean(get_value("供应商款号")),
                    "detail_no": detail_no,
                }
            )
    finally:
        workbook.close()

    if not records:
        raise ValueError("采购单文件未读取到有效明细")
    return records


def import_excel(
    path: str | Path,
    source_name: str = "",
    imported_by: str = "",
    engine: Engine | None = None,
) -> dict[str, Any]:
    source_path = Path(path)
    records = _read_purchase_orders(source_path)
    batch_id = uuid.uuid4().hex
    imported_at = datetime.now()
    purchase_dates = [item["purchase_date"].date() for item in records if item["purchase_date"]]
    date_start = min(purchase_dates) if purchase_dates else None
    date_end = max(purchase_dates) if purchase_dates else None
    order_count = len({item["order_no"] for item in records if item["order_no"]})
    image_count = sum(1 for item in records if item["image_url"])
    payload = [
        {**item, "batch_id": batch_id, "imported_at": imported_at}
        for item in records
    ]

    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.begin() as conn:
        old_batch_ids = conn.execute(
            text("SELECT batch_id FROM purchase_order_dashboard_batch")
        ).scalars().all()
        for old_batch_id in old_batch_ids:
            conn.execute(
                text("DELETE FROM purchase_order_dashboard_item WHERE batch_id = :batch_id"),
                {"batch_id": old_batch_id},
            )
        conn.execute(text("DELETE FROM purchase_order_dashboard_batch"))
        conn.execute(
            text(
                """
                INSERT INTO purchase_order_dashboard_batch
                    (batch_id, source_name, date_start, date_end, row_count,
                     order_count, image_count, imported_by, imported_at)
                VALUES
                    (:batch_id, :source_name, :date_start, :date_end, :row_count,
                     :order_count, :image_count, :imported_by, :imported_at)
                """
            ),
            {
                "batch_id": batch_id,
                "source_name": (source_name or source_path.name)[:255],
                "date_start": date_start,
                "date_end": date_end,
                "row_count": len(records),
                "order_count": order_count,
                "image_count": image_count,
                "imported_by": _clean(imported_by)[:64],
                "imported_at": imported_at,
            },
        )
        for start in range(0, len(payload), 500):
            conn.execute(
                text(
                    """
                    INSERT INTO purchase_order_dashboard_item (
                        batch_id, source_row, order_no, purchase_date, status,
                        receiving_status, purchase_remark, receiving_address,
                        purchase_type, warehouse_party, purchaser, review_date,
                        last_modified_date, image_url, product_code, style_code,
                        product_name, color_spec, pending_ship_quantity,
                        available_quantity, quantity, received_quantity,
                        variance_quantity, supplier_product_code, supplier_style_no,
                        detail_no, imported_at
                    ) VALUES (
                        :batch_id, :source_row, :order_no, :purchase_date, :status,
                        :receiving_status, :purchase_remark, :receiving_address,
                        :purchase_type, :warehouse_party, :purchaser, :review_date,
                        :last_modified_date, :image_url, :product_code, :style_code,
                        :product_name, :color_spec, :pending_ship_quantity,
                        :available_quantity, :quantity, :received_quantity,
                        :variance_quantity, :supplier_product_code, :supplier_style_no,
                        :detail_no, :imported_at
                    )
                    """
                ),
                payload[start : start + 500],
            )

    return {
        "batch_id": batch_id,
        "source_name": source_name or source_path.name,
        "date_start": date_start.isoformat() if date_start else "",
        "date_end": date_end.isoformat() if date_end else "",
        "row_count": len(records),
        "order_count": order_count,
        "image_count": image_count,
        "imported_at": imported_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _where_clause(
    keyword: str,
    status: str,
    receiving_status: str,
    warehouse_party: str,
    purchaser: str,
    purchase_type: str,
    date_start: str | None,
    date_end: str | None,
) -> tuple[str, dict[str, Any]]:
    clauses = ["batch_id = :batch_id"]
    params: dict[str, Any] = {}
    clean_keyword = _clean(keyword)
    if clean_keyword:
        clauses.append(
            "(order_no LIKE :keyword OR product_code LIKE :keyword OR style_code LIKE :keyword "
            "OR product_name LIKE :keyword OR supplier_product_code LIKE :keyword "
            "OR supplier_style_no LIKE :keyword OR detail_no LIKE :keyword "
            "OR purchase_remark LIKE :keyword)"
        )
        params["keyword"] = f"%{clean_keyword}%"
    for field, value, param_name in (
        ("status", status, "status"),
        ("receiving_status", receiving_status, "receiving_status"),
        ("warehouse_party", warehouse_party, "warehouse_party"),
        ("purchaser", purchaser, "purchaser"),
        ("purchase_type", purchase_type, "purchase_type"),
    ):
        clean_value = _clean(value)
        if clean_value:
            clauses.append(f"{field} = :{param_name}")
            params[param_name] = clean_value
    if date_start:
        clauses.append("purchase_date >= :date_start")
        params["date_start"] = date_start
    if date_end:
        end_exclusive = datetime.strptime(date_end, "%Y-%m-%d").date() + timedelta(days=1)
        clauses.append("purchase_date < :date_end_exclusive")
        params["date_end_exclusive"] = end_exclusive.isoformat()
    return " WHERE " + " AND ".join(clauses), params


def list_dashboard(
    keyword: str = "",
    status: str = "",
    receiving_status: str = "",
    warehouse_party: str = "",
    purchaser: str = "",
    purchase_type: str = "",
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = 1,
    page_size: int = 50,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    page = max(1, int(page))
    page_size = min(200, max(10, int(page_size)))
    clean_date_start = _date_filter(date_start, "开始日期")
    clean_date_end = _date_filter(date_end, "结束日期")
    if clean_date_start and clean_date_end and clean_date_start > clean_date_end:
        raise ValueError("开始日期不能晚于结束日期")

    with db_engine.connect() as conn:
        batch = conn.execute(
            text(
                """
                SELECT batch_id, source_name, date_start, date_end, row_count,
                       order_count, image_count, imported_by, imported_at
                FROM purchase_order_dashboard_batch
                ORDER BY imported_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()
        if batch is None:
            return {
                "batch": {},
                "summary": {
                    "row_count": 0,
                    "order_count": 0,
                    "product_count": 0,
                    "quantity": 0,
                    "received_quantity": 0,
                    "pending_ship_quantity": 0,
                    "available_quantity": 0,
                    "variance_quantity": 0,
                },
                "filter_options": {"statuses": [], "receiving_statuses": [], "warehouses": [], "purchasers": [], "purchase_types": [], "purchase_dates": []},
                "charts": {"status": [], "receiving_status": [], "purchasers": [], "warehouses": [], "trend": []},
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }

        where_sql, params = _where_clause(
            keyword,
            status,
            receiving_status,
            warehouse_party,
            purchaser,
            purchase_type,
            clean_date_start,
            clean_date_end,
        )
        params["batch_id"] = batch["batch_id"]
        summary = conn.execute(
            text(
                """
                SELECT COUNT(*) AS row_count,
                       COUNT(DISTINCT NULLIF(order_no, '')) AS order_count,
                       COUNT(DISTINCT NULLIF(product_code, '')) AS product_count,
                       COALESCE(SUM(quantity), 0) AS quantity,
                       COALESCE(SUM(received_quantity), 0) AS received_quantity,
                       COALESCE(SUM(pending_ship_quantity), 0) AS pending_ship_quantity,
                       COALESCE(SUM(available_quantity), 0) AS available_quantity,
                       COALESCE(SUM(variance_quantity), 0) AS variance_quantity
                FROM purchase_order_dashboard_item
                """ + where_sql
            ),
            params,
        ).mappings().one()
        total = int(summary["row_count"] or 0)

        items = conn.execute(
            text(
                """
                SELECT id, source_row, order_no, purchase_date, status,
                       receiving_status, purchase_remark, receiving_address,
                       purchase_type, warehouse_party, purchaser, review_date,
                       last_modified_date, image_url, product_code, style_code,
                       product_name, color_spec, pending_ship_quantity,
                       available_quantity, quantity, received_quantity,
                       variance_quantity, supplier_product_code, supplier_style_no,
                       detail_no
                FROM purchase_order_dashboard_item
                """ + where_sql + " ORDER BY purchase_date DESC, id DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        ).mappings().all()

        def grouped(field: str, metric: str, limit: int = 12) -> list[dict[str, Any]]:
            rows = conn.execute(
                text(
                    f"""
                    SELECT NULLIF({field}, '') AS name,
                           COUNT(DISTINCT NULLIF(order_no, '')) AS order_count,
                           COALESCE(SUM({metric}), 0) AS quantity
                    FROM purchase_order_dashboard_item
                    """ + where_sql + f" GROUP BY {field} ORDER BY quantity DESC, name LIMIT {limit}"
                ),
                params,
            ).mappings().all()
            return [
                {
                    "name": _clean(row["name"]) or "未填写",
                    "order_count": int(row["order_count"] or 0),
                    "quantity": float(row["quantity"] or 0),
                }
                for row in rows
                if row["name"] is not None or row["quantity"]
            ]

        def distribution(field: str) -> list[dict[str, Any]]:
            rows = conn.execute(
                text(
                    f"""
                    SELECT NULLIF({field}, '') AS name, COUNT(*) AS value
                    FROM purchase_order_dashboard_item
                    """ + where_sql + f" GROUP BY {field} ORDER BY value DESC, name"
                ),
                params,
            ).mappings().all()
            return [
                {"name": _clean(row["name"]) or "未填写", "value": int(row["value"] or 0)}
                for row in rows
                if row["name"] is not None or row["value"]
            ]

        trend_rows = conn.execute(
            text(
                """
                SELECT DATE(purchase_date) AS report_date,
                       COUNT(DISTINCT NULLIF(order_no, '')) AS order_count,
                       COUNT(*) AS row_count,
                       COALESCE(SUM(quantity), 0) AS quantity,
                       COALESCE(SUM(received_quantity), 0) AS received_quantity
                FROM purchase_order_dashboard_item
                """ + where_sql + " AND purchase_date IS NOT NULL GROUP BY DATE(purchase_date) ORDER BY report_date"
            ),
            params,
        ).mappings().all()

        option_sql = " WHERE batch_id = :batch_id"
        option_map = {
            "statuses": "status",
            "receiving_statuses": "receiving_status",
            "warehouses": "warehouse_party",
            "purchasers": "purchaser",
            "purchase_types": "purchase_type",
        }
        options: dict[str, list[str]] = {}
        for key, field in option_map.items():
            options[key] = [
                _clean(value)
                for value in conn.execute(
                    text(f"SELECT DISTINCT {field} FROM purchase_order_dashboard_item{option_sql} AND {field} <> '' ORDER BY {field}"),
                    {"batch_id": batch["batch_id"]},
                ).scalars()
                if _clean(value)
            ]
        options["purchase_dates"] = [
            row[0].isoformat()
            for row in conn.execute(
                text(
                    "SELECT DISTINCT DATE(purchase_date) FROM purchase_order_dashboard_item "
                    "WHERE batch_id = :batch_id AND purchase_date IS NOT NULL ORDER BY DATE(purchase_date)"
                ),
                {"batch_id": batch["batch_id"]},
            ).all()
            if row[0]
        ]

        charts = {
            "status": distribution("status"),
            "receiving_status": distribution("receiving_status"),
            "purchasers": grouped("purchaser", "quantity"),
            "warehouses": grouped("warehouse_party", "quantity"),
            "trend": [
                {
                    "date": row["report_date"].isoformat() if row["report_date"] else "",
                    "order_count": int(row["order_count"] or 0),
                    "row_count": int(row["row_count"] or 0),
                    "quantity": float(row["quantity"] or 0),
                    "received_quantity": float(row["received_quantity"] or 0),
                }
                for row in trend_rows
            ],
        }

    batch_payload = dict(batch)
    for key in ("date_start", "date_end"):
        if batch_payload.get(key):
            batch_payload[key] = batch_payload[key].isoformat()
    if batch_payload.get("imported_at"):
        batch_payload["imported_at"] = _serialise_datetime(batch_payload["imported_at"])

    serialise_numeric = {
        "pending_ship_quantity",
        "available_quantity",
        "quantity",
        "received_quantity",
        "variance_quantity",
    }
    serialised_items: list[dict[str, Any]] = []
    for row in items:
        item = dict(row)
        for key in serialise_numeric:
            item[key] = float(item.get(key) or 0)
        for key in ("purchase_date", "review_date", "last_modified_date"):
            item[key] = _serialise_datetime(item.get(key))
        serialised_items.append(item)

    serialised_summary = {
        "row_count": int(summary["row_count"] or 0),
        "order_count": int(summary["order_count"] or 0),
        "product_count": int(summary["product_count"] or 0),
        "quantity": float(summary["quantity"] or 0),
        "received_quantity": float(summary["received_quantity"] or 0),
        "pending_ship_quantity": float(summary["pending_ship_quantity"] or 0),
        "available_quantity": float(summary["available_quantity"] or 0),
        "variance_quantity": float(summary["variance_quantity"] or 0),
    }
    return {
        "batch": batch_payload,
        "summary": serialised_summary,
        "filter_options": options,
        "charts": charts,
        "items": serialised_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
