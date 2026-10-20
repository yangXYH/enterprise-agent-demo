"""Business-metric trend forecasting for inventory replenishment.

The inventory engine stays deterministic and operational. This module adds an
observation layer: daily business metrics calculate a national SKU trend, while
each city's absolute demand continues to start from its own outbound baseline.
"""

from __future__ import annotations

import json
import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
import pandas as pd
from sqlalchemy import Engine, text

from utils import import_service, inventory_service


DEFAULT_FORECAST_DAYS = 7
LOOKBACK_DAYS = 30
BACKTEST_LOOKBACK_DAYS = 120

TREND_UP = "UP"
TREND_STABLE = "STABLE"
TREND_DOWN = "DOWN"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MID = "MID"
CONFIDENCE_LOW = "LOW"

LINKED = "LINKED"
PENDING_LINK = "PENDING_LINK"

FORECAST_CITY_ALLOWLIST = frozenset({"广州", "上海", "北京", "成都", "武汉", "西安", "德州", "沈阳"})
PURCHASE_EXPORT_CITIES = ("北京", "上海", "广州", "成都", "武汉", "沈阳", "西安", "德州")
PURCHASE_EXPORT_HEADERS = (
    "采购员ERP",
    "商品编号",
    "商品名称",
    "商品属性",
    "采购场景",
    "预计消化时间",
    "采购原因",
    *PURCHASE_EXPORT_CITIES,
)
PURCHASE_EXPORT_WIDTHS = {
    "A": 32.125,
    "B": 20.8166666666667,
    "C": 19.125,
    "D": 15,
    "E": 15,
    "F": 15,
    "G": 15,
    "H": 13,
    "I": 13,
    "J": 13,
    "K": 13,
    "L": 13,
    "M": 13,
    "N": 13,
    "O": 13,
}
SIGNAL_CLIP_LOW = -0.8
SIGNAL_CLIP_HIGH = 0.8
ADJUSTMENT_LOW = 0.8
ADJUSTMENT_HIGH = 1.25
SIGNAL_STABLE_BAND = 0.04

SIGNAL_GROUPS: dict[str, tuple[tuple[str, float], ...]] = {
    "traffic": (
        ("page_views", 0.30),
        ("visitors", 0.35),
        ("views_per_visitor", 0.15),
        ("avg_stay_seconds", 0.20),
    ),
    "interest": (
        ("cart_users", 0.45),
        ("cart_conversion_rate", 0.25),
        ("cart_units", 0.30),
    ),
    "conversion": (
        ("buyers", 0.30),
        ("conversion_rate", 0.40),
        ("order_count", 0.30),
    ),
    "quality": (
        ("gmv_amount", 0.65),
        ("avg_order_value", 0.35),
    ),
}

SIGNAL_WEIGHTS = {
    "sales": 0.35,
    "traffic": 0.20,
    "interest": 0.20,
    "conversion": 0.15,
    "quality": 0.10,
}


def _is_forecast_city(warehouse_code: Any) -> bool:
    return inventory_service._base_city(str(warehouse_code or "")) in FORECAST_CITY_ALLOWLIST


def _visible_city_counts(rows: Iterable[Any]) -> tuple[int, int]:
    affected_count = 0
    suggestion_count = 0
    for row in rows:
        if not _is_forecast_city(row.get("warehouse_code")):
            continue
        if row.get("risk_level") == "HIGH":
            affected_count += 1
        if _safe_float(row.get("suggested_qty")) > 0:
            suggestion_count += 1
    return affected_count, suggestion_count


BUSINESS_COLUMNS = {
    "biz_date": "时间",
    "product_name": "商品名称",
    "sku_code": "SKU",
    "brand": "品牌",
    "category_l1": "一级类目",
    "category_l2": "二级类目",
    "category_l3": "三级类目",
    "shop_name": "店铺名称",
    "business_mode": "经营模式",
    "page_views": "浏览量",
    "visitors": "访客数",
    "views_per_visitor": "人均浏览量",
    "avg_stay_seconds": "平均停留时长",
    "buyers": "成交人数",
    "conversion_rate": "成交转化率",
    "order_count": "成交单量",
    "sold_units": "成交商品件数",
    "gmv_amount": "成交金额",
    "avg_order_value": "成交客单价",
    "cart_users": "加购人数",
    "cart_conversion_rate": "加购转化率",
    "cart_units": "加购商品件数",
}

NUMERIC_FIELDS = [
    "page_views",
    "visitors",
    "views_per_visitor",
    "avg_stay_seconds",
    "buyers",
    "conversion_rate",
    "order_count",
    "sold_units",
    "gmv_amount",
    "avg_order_value",
    "cart_users",
    "cart_conversion_rate",
    "cart_units",
]


def get_engine(engine: Engine | None = None) -> Engine:
    return engine or import_service.get_engine()


def ensure_business_schema(engine: Engine | None = None) -> None:
    db_engine = get_engine(engine)
    inventory_service.ensure_inventory_schema(db_engine)

    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS inv_business_import_batch (
            id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
            batch_no VARCHAR(64) NOT NULL COMMENT '导入批次号',
            file_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT '导入文件名',
            status VARCHAR(32) NOT NULL DEFAULT 'RUNNING' COMMENT '批次状态 RUNNING/SUCCESS/FAILED',
            min_biz_date DATE NULL COMMENT '本批次最早经营日期',
            max_biz_date DATE NULL COMMENT '本批次最晚经营日期',
            rows_read INT NOT NULL DEFAULT 0 COMMENT 'Excel读取行数',
            rows_imported INT NOT NULL DEFAULT 0 COMMENT '写入经营明细行数',
            unique_sku_count INT NOT NULL DEFAULT 0 COMMENT '本批次SKU数量',
            message TEXT NULL COMMENT '处理说明',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            finished_at DATETIME NULL COMMENT '结束时间',
            PRIMARY KEY (id),
            UNIQUE KEY uk_inv_business_import_batch_no (batch_no),
            KEY idx_inv_business_import_date (max_biz_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营明细导入批次表'
        """,
        """
        CREATE TABLE IF NOT EXISTS inv_business_daily (
            id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
            biz_date DATE NOT NULL COMMENT '经营日期',
            sku_code VARCHAR(64) NOT NULL COMMENT 'SKU编码',
            product_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT '商品名称',
            brand VARCHAR(128) NOT NULL DEFAULT '' COMMENT '品牌',
            category_l1 VARCHAR(128) NOT NULL DEFAULT '' COMMENT '一级类目',
            category_l2 VARCHAR(128) NOT NULL DEFAULT '' COMMENT '二级类目',
            category_l3 VARCHAR(128) NOT NULL DEFAULT '' COMMENT '三级类目',
            shop_name VARCHAR(255) NOT NULL DEFAULT '' COMMENT '店铺名称',
            business_mode VARCHAR(64) NOT NULL DEFAULT '' COMMENT '经营模式',
            page_views DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '浏览量',
            visitors DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '访客数',
            views_per_visitor DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '人均浏览量',
            avg_stay_seconds DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '平均停留时长秒数',
            buyers DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '成交人数',
            conversion_rate DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '成交转化率',
            order_count DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '成交单量',
            sold_units DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '成交商品件数',
            gmv_amount DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '成交金额',
            avg_order_value DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '成交客单价',
            cart_users DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '加购人数',
            cart_conversion_rate DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '加购转化率',
            cart_units DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '加购商品件数',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            PRIMARY KEY (id),
            UNIQUE KEY uk_inv_business_daily_date_sku (biz_date, sku_code),
            KEY idx_inv_business_daily_sku_date (sku_code, biz_date),
            KEY idx_inv_business_daily_brand_date (brand, biz_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营数据按天SKU明细表'
        """,
        """
        CREATE TABLE IF NOT EXISTS inv_business_forecast (
            id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
            forecast_date DATE NOT NULL COMMENT '预测生成日期',
            target_start_date DATE NOT NULL COMMENT '预测目标开始日期',
            target_end_date DATE NOT NULL COMMENT '预测目标结束日期',
            sku_code VARCHAR(64) NOT NULL COMMENT 'SKU编码',
            product_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT '商品名称',
            brand VARCHAR(128) NOT NULL DEFAULT '' COMMENT '品牌',
            category VARCHAR(128) NOT NULL DEFAULT '' COMMENT '库存类目',
            category_l1 VARCHAR(128) NOT NULL DEFAULT '' COMMENT '经营一级类目',
            category_l2 VARCHAR(128) NOT NULL DEFAULT '' COMMENT '经营二级类目',
            category_l3 VARCHAR(128) NOT NULL DEFAULT '' COMMENT '经营三级类目',
            sku_link_status VARCHAR(32) NOT NULL DEFAULT 'PENDING_LINK' COMMENT 'SKU关联状态 LINKED/PENDING_LINK',
            days_covered INT NOT NULL DEFAULT 0 COMMENT '近30天有经营记录天数',
            total_30d_units DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '近30天成交商品件数',
            recent_3d_avg DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '近3日日均成交件数',
            recent_7d_avg DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '近7日日均成交件数',
            recent_14d_avg DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '近14日日均成交件数',
            recent_30d_avg DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '近30日日均成交件数',
            base_pred_7d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '未修正未来7天成交预测',
            adjusted_pred_7d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '经营指标修正后未来7天成交预测',
            unit_momentum DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '成交件数趋势',
            visitor_momentum DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '访客趋势',
            cart_momentum DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '加购人数趋势',
            conversion_momentum DECIMAL(18,6) NOT NULL DEFAULT 0 COMMENT '成交转化率趋势',
            adjustment_factor DECIMAL(18,6) NOT NULL DEFAULT 1 COMMENT '经营趋势修正系数',
            trend_level VARCHAR(16) NOT NULL DEFAULT 'STABLE' COMMENT '趋势 UP/STABLE/DOWN',
            confidence_level VARCHAR(16) NOT NULL DEFAULT 'LOW' COMMENT '置信度 HIGH/MID/LOW',
            affected_warehouse_count INT NOT NULL DEFAULT 0 COMMENT '预测受影响风险仓数量',
            suggestion_count INT NOT NULL DEFAULT 0 COMMENT '预测补货建议数量',
            pending_city_split TINYINT NOT NULL DEFAULT 0 COMMENT '是否无法分仓',
            reason_json JSON NULL COMMENT '可解释计算依据',
            actual_7d DECIMAL(18,4) NULL COMMENT '预测目标窗口真实成交件数',
            forecast_error DECIMAL(18,4) NULL COMMENT '真实成交-预测成交',
            abs_percentage_error DECIMAL(18,6) NULL COMMENT '绝对百分比误差',
            hit_flag TINYINT NULL COMMENT '是否命中，误差不超过20%或1件',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            PRIMARY KEY (id),
            UNIQUE KEY uk_inv_business_forecast_date_sku (forecast_date, sku_code),
            KEY idx_inv_business_forecast_brand (forecast_date, brand),
            KEY idx_inv_business_forecast_trend (forecast_date, trend_level, confidence_level),
            KEY idx_inv_business_forecast_link (forecast_date, sku_link_status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营趋势SKU预测表'
        """,
        """
        CREATE TABLE IF NOT EXISTS inv_business_forecast_city (
            id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
            forecast_id BIGINT NOT NULL COMMENT '经营预测ID',
            forecast_date DATE NOT NULL COMMENT '预测生成日期',
            sku_code VARCHAR(64) NOT NULL COMMENT 'SKU编码',
            warehouse_code VARCHAR(128) NOT NULL COMMENT '城市/仓库编码',
            city_sales_30d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '该城市近30日出库',
            city_share DECIMAL(18,8) NOT NULL DEFAULT 0 COMMENT '城市需求基线占全国城市基线比例',
            predicted_city_7d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '城市需求基线经全国趋势修正后的未来7天需求',
            daily_city_forecast DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '该城市预测日均销量',
            target_days DECIMAL(10,2) NOT NULL DEFAULT 30 COMMENT '目标周转天数',
            stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '当前库存',
            inbound_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '采购未到货',
            available_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '库存+在途',
            days_of_supply DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '按经营趋势预测的当前库存可售天数',
            risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW' COMMENT '预测风险 HIGH/MID/LOW',
            shortage_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '达到目标周转需补足数量',
            suggested_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '预测建议补货数量',
            suggested_source VARCHAR(128) NOT NULL DEFAULT '' COMMENT '预测建议供给来源',
            eta_days INT NOT NULL DEFAULT 0 COMMENT '预计到达天数',
            route_path VARCHAR(512) NOT NULL DEFAULT '' COMMENT '预测补货路径',
            status VARCHAR(32) NOT NULL DEFAULT 'OBSERVE' COMMENT '观察状态 OBSERVE/PENDING_LINK/NO_CITY_SPLIT',
            reason VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '预测建议原因',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            PRIMARY KEY (id),
            KEY idx_inv_business_city_forecast (forecast_id),
            KEY idx_inv_business_city_date_sku (forecast_date, sku_code),
            KEY idx_inv_business_city_risk (forecast_date, risk_level),
            KEY idx_inv_business_city_wh (warehouse_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营趋势城市风险与补货观察表'
        """,
        """
        CREATE TABLE IF NOT EXISTS inv_business_forecast_setting (
            id TINYINT NOT NULL DEFAULT 1 COMMENT '主键ID',
            apply_trend_factor TINYINT NOT NULL DEFAULT 1 COMMENT '补货计算是否应用经营趋势因子 1=应用 0=不应用',
            purchase_formula VARCHAR(16) NOT NULL DEFAULT 'excel' COMMENT '补货导出算法 system=现行算法 excel=运营表算法',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营趋势预测计算设置表'
        """,
    ]
    with db_engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))
        conn.execute(
            text(
                """
                INSERT IGNORE INTO inv_business_forecast_setting (id, apply_trend_factor)
                VALUES (1, 1)
                """
            )
        )
        # 老库迁移：为已存在的设置表补充 purchase_formula 列
        database_name = conn.execute(text("SELECT DATABASE()")).scalar()
        if database_name:
            has_column = bool(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA=:schema
                          AND TABLE_NAME='inv_business_forecast_setting'
                          AND COLUMN_NAME='purchase_formula'
                        """
                    ),
                    {"schema": database_name},
                ).scalar()
            )
            if not has_column:
                conn.execute(
                    text(
                        """
                        ALTER TABLE inv_business_forecast_setting
                        ADD COLUMN purchase_formula VARCHAR(16) NOT NULL DEFAULT 'excel'
                        COMMENT '补货导出算法 system=现行算法 excel=运营表算法'
                        AFTER apply_trend_factor
                        """
                    )
                )


def import_business_excel(
    excel_path: str | Path,
    engine: Engine | None = None,
    original_file_name: str = "",
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)

    batch_no = f"BIZ-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
    rows: list[dict[str, Any]] = []
    min_date: date | None = None
    max_date: date | None = None
    unique_skus: set[str] = set()

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO inv_business_import_batch
                    (batch_no, file_name, status, created_at)
                VALUES (:batch_no, :file_name, 'RUNNING', NOW())
                """
            ),
            {"batch_no": batch_no, "file_name": original_file_name or Path(excel_path).name},
        )

    try:
        frame = pd.read_excel(excel_path, dtype=object, engine="openpyxl")
        frame.columns = [str(col).strip() for col in frame.columns]
        missing = [label for label in BUSINESS_COLUMNS.values() if label not in frame.columns]
        if missing:
            raise ValueError(f"经营报表缺少必要字段: {', '.join(missing)}")

        for _, raw in frame.iterrows():
            biz_date = _parse_date(raw[BUSINESS_COLUMNS["biz_date"]])
            sku_code = inventory_service._clean_sku(raw[BUSINESS_COLUMNS["sku_code"]])
            if not biz_date or not sku_code:
                continue
            min_date = biz_date if min_date is None else min(min_date, biz_date)
            max_date = biz_date if max_date is None else max(max_date, biz_date)
            unique_skus.add(sku_code)
            shop_name = _clean_text(raw[BUSINESS_COLUMNS["shop_name"]])
            brand = _normalize_business_brand(raw[BUSINESS_COLUMNS["brand"]], shop_name)
            row: dict[str, Any] = {
                "biz_date": biz_date,
                "sku_code": sku_code,
                "product_name": _clean_text(raw[BUSINESS_COLUMNS["product_name"]]),
                "brand": brand,
                "category_l1": _clean_text(raw[BUSINESS_COLUMNS["category_l1"]]),
                "category_l2": _clean_text(raw[BUSINESS_COLUMNS["category_l2"]]),
                "category_l3": _clean_text(raw[BUSINESS_COLUMNS["category_l3"]]),
                "shop_name": shop_name,
                "business_mode": _clean_text(raw[BUSINESS_COLUMNS["business_mode"]]),
            }
            for field in NUMERIC_FIELDS:
                value = raw[BUSINESS_COLUMNS[field]]
                if field in {"conversion_rate", "cart_conversion_rate"}:
                    row[field] = _to_rate(value)
                elif field == "avg_stay_seconds":
                    row[field] = _to_seconds(value)
                else:
                    row[field] = _to_float(value)
            rows.append(row)

        if not rows:
            raise ValueError("经营报表没有可导入的有效日期+SKU数据")

        with db_engine.begin() as conn:
            _execute_chunks(
                conn,
                text(
                    """
                    INSERT INTO inv_business_daily (
                        biz_date, sku_code, product_name, brand, category_l1, category_l2,
                        category_l3, shop_name, business_mode, page_views, visitors,
                        views_per_visitor, avg_stay_seconds, buyers, conversion_rate,
                        order_count, sold_units, gmv_amount, avg_order_value,
                        cart_users, cart_conversion_rate, cart_units, created_at, updated_at
                    )
                    VALUES (
                        :biz_date, :sku_code, :product_name, :brand, :category_l1, :category_l2,
                        :category_l3, :shop_name, :business_mode, :page_views, :visitors,
                        :views_per_visitor, :avg_stay_seconds, :buyers, :conversion_rate,
                        :order_count, :sold_units, :gmv_amount, :avg_order_value,
                        :cart_users, :cart_conversion_rate, :cart_units, NOW(), NOW()
                    )
                    ON DUPLICATE KEY UPDATE
                        product_name=VALUES(product_name),
                        brand=VALUES(brand),
                        category_l1=VALUES(category_l1),
                        category_l2=VALUES(category_l2),
                        category_l3=VALUES(category_l3),
                        shop_name=VALUES(shop_name),
                        business_mode=VALUES(business_mode),
                        page_views=VALUES(page_views),
                        visitors=VALUES(visitors),
                        views_per_visitor=VALUES(views_per_visitor),
                        avg_stay_seconds=VALUES(avg_stay_seconds),
                        buyers=VALUES(buyers),
                        conversion_rate=VALUES(conversion_rate),
                        order_count=VALUES(order_count),
                        sold_units=VALUES(sold_units),
                        gmv_amount=VALUES(gmv_amount),
                        avg_order_value=VALUES(avg_order_value),
                        cart_users=VALUES(cart_users),
                        cart_conversion_rate=VALUES(cart_conversion_rate),
                        cart_units=VALUES(cart_units),
                        updated_at=NOW()
                    """
                ),
                rows,
            )
            conn.execute(
                text(
                    """
                    UPDATE inv_business_import_batch
                    SET status='SUCCESS',
                        min_biz_date=:min_date,
                        max_biz_date=:max_date,
                        rows_read=:rows_read,
                        rows_imported=:rows_imported,
                        unique_sku_count=:unique_sku_count,
                        message=:message,
                        finished_at=NOW()
                    WHERE batch_no=:batch_no
                    """
                ),
                {
                    "batch_no": batch_no,
                    "min_date": min_date,
                    "max_date": max_date,
                    "rows_read": int(len(frame)),
                    "rows_imported": len(rows),
                    "unique_sku_count": len(unique_skus),
                    "message": "经营明细导入成功",
                },
            )
    except Exception as exc:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE inv_business_import_batch
                    SET status='FAILED', message=:message, finished_at=NOW()
                    WHERE batch_no=:batch_no
                    """
                ),
                {"batch_no": batch_no, "message": str(exc)[:2000]},
            )
        raise

    return {
        "batch_no": batch_no,
        "rows_imported": len(rows),
        "unique_sku_count": len(unique_skus),
        "min_biz_date": min_date.isoformat() if min_date else None,
        "max_biz_date": max_date.isoformat() if max_date else None,
    }


def recalculate_business_forecasts(
    forecast_date: str | date | None = None,
    engine: Engine | None = None,
    sku_codes: Iterable[str] | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    target_date = _resolve_business_date(db_engine, forecast_date)
    sku_filter = sorted({inventory_service._clean_sku(item) for item in (sku_codes or []) if inventory_service._clean_sku(item)})

    rows = _load_business_rows(db_engine, target_date, sku_filter)
    if not rows:
        raise ValueError("暂无经营明细数据，无法生成趋势预测")

    forecast_settings = get_business_forecast_settings(db_engine)
    apply_trend_factor = forecast_settings.get("apply_trend_factor", True)
    purchase_formula = str(forecast_settings.get("purchase_formula") or "system")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["sku_code"])].append(row)

    sku_list = sorted(grouped.keys())
    inventory_meta = _load_inventory_sku_meta(db_engine, sku_list)
    snapshot_date = inventory_service._resolve_snapshot_date(db_engine, None, allow_none=True)
    snapshots_by_sku = _load_latest_snapshots(db_engine, snapshot_date, sku_list) if snapshot_date else {}

    policies = inventory_service._load_replenishment_policies(db_engine)
    supply_stocks = inventory_service._latest_supply_stocks_by_warehouse(db_engine)

    forecast_rows: list[dict[str, Any]] = []
    city_rows_by_sku: dict[str, list[dict[str, Any]]] = {}

    for sku_code, sku_rows in grouped.items():
        forecast, cities = _build_sku_forecast(
            forecast_date=target_date,
            sku_code=sku_code,
            rows=sku_rows,
            inventory_meta=inventory_meta.get(sku_code),
            snapshots=snapshots_by_sku.get(sku_code, []),
            policies=policies,
            supply_stocks=supply_stocks,
            apply_trend_factor=apply_trend_factor,
            purchase_formula=purchase_formula,
        )
        forecast_rows.append(forecast)
        city_rows_by_sku[sku_code] = cities

    with db_engine.begin() as conn:
        _delete_existing_forecasts(conn, target_date, sku_list if sku_filter else None)
        _execute_chunks(conn, _forecast_insert_sql(), forecast_rows, chunk_size=500)
        id_rows = conn.execute(
            text(
                f"""
                SELECT id, sku_code
                FROM inv_business_forecast
                WHERE forecast_date=:forecast_date
                  AND sku_code IN ({_placeholders('sku', sku_list)})
                """
            ),
            {"forecast_date": target_date, **{f"sku_{idx}": sku for idx, sku in enumerate(sku_list)}},
        ).mappings().all()
        forecast_ids = {str(row["sku_code"]): int(row["id"]) for row in id_rows}
        city_rows: list[dict[str, Any]] = []
        for sku_code, rows_for_sku in city_rows_by_sku.items():
            forecast_id = forecast_ids.get(sku_code)
            if not forecast_id:
                continue
            for row in rows_for_sku:
                row["forecast_id"] = forecast_id
                city_rows.append(row)
        if city_rows:
            _execute_chunks(conn, _city_insert_sql(), city_rows, chunk_size=1000)

    backtest = _refresh_backtest(db_engine, target_date)
    linked_count = sum(1 for row in forecast_rows if row["sku_link_status"] == LINKED)
    pending_count = len(forecast_rows) - linked_count
    affected_count = sum(int(row["affected_warehouse_count"]) for row in forecast_rows)
    suggestion_count = sum(int(row["suggestion_count"]) for row in forecast_rows)
    return {
        "forecast_date": target_date.isoformat(),
        "target_start_date": (target_date + timedelta(days=1)).isoformat(),
        "target_end_date": (target_date + timedelta(days=DEFAULT_FORECAST_DAYS)).isoformat(),
        "forecast_sku_count": len(forecast_rows),
        "linked_sku_count": linked_count,
        "pending_link_count": pending_count,
        "affected_warehouse_count": affected_count,
        "suggestion_count": suggestion_count,
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "backtest": backtest,
    }


def recalculate_business_forecasts_for_policy_scope(
    engine: Engine | None = None,
    forecast_date: str | date | None = None,
    policy_type: str = "BRAND",
    brand: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    target_date = _resolve_business_forecast_date(db_engine, forecast_date)
    if not target_date:
        return {"skipped": True, "reason": "NO_BUSINESS_FORECAST"}

    normalized_type = (policy_type or "BRAND").upper()
    brand_text = _clean_text(brand)
    category_text = _clean_text(category)
    where = ["forecast_date=:forecast_date"]
    params: dict[str, Any] = {"forecast_date": target_date}
    if normalized_type == "BRAND":
        if not brand_text:
            return {"skipped": True, "reason": "EMPTY_BRAND_SCOPE", "forecast_date": target_date.isoformat()}
        where.append("brand=:brand")
        params["brand"] = brand_text
    elif normalized_type == "CATEGORY":
        if not category_text:
            return {"skipped": True, "reason": "EMPTY_CATEGORY_SCOPE", "forecast_date": target_date.isoformat()}
        where.append(
            "(category=:category OR category_l1=:category OR category_l2=:category OR category_l3=:category)"
        )
        params["category"] = category_text

    with db_engine.connect() as conn:
        sku_rows = conn.execute(
            text(
                f"""
                SELECT DISTINCT sku_code
                FROM inv_business_forecast
                WHERE {' AND '.join(where)}
                """
            ),
            params,
        ).mappings().all()

    sku_codes = sorted({inventory_service._clean_sku(row["sku_code"]) for row in sku_rows if row.get("sku_code")})
    if not sku_codes:
        return {"skipped": True, "reason": "NO_MATCHING_BUSINESS_SKU", "forecast_date": target_date.isoformat()}

    try:
        result = recalculate_business_forecasts(target_date, db_engine, sku_codes)
    except ValueError as exc:
        return {
            "skipped": True,
            "reason": "BUSINESS_RECALCULATE_UNAVAILABLE",
            "message": str(exc),
            "forecast_date": target_date.isoformat(),
            "policy_scope_sku_count": len(sku_codes),
        }
    result["policy_scope_sku_count"] = len(sku_codes)
    result["policy_scope"] = {
        "policy_type": normalized_type,
        "brand": brand_text,
        "category": category_text,
    }
    return result


def get_business_forecast_summary(engine: Engine | None = None, forecast_date: str | date | None = None) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    target_date = _resolve_business_forecast_date(db_engine, forecast_date)
    if not target_date:
        latest_biz = _latest_business_date(db_engine)
        return {
            "forecast_date": None,
            "latest_business_date": latest_biz.isoformat() if latest_biz else None,
            "forecast_sku_count": 0,
            "linked_sku_count": 0,
            "pending_link_count": 0,
            "up_high_count": 0,
            "affected_warehouse_count": 0,
            "suggestion_count": 0,
            "backtest_hit_rate": None,
            "backtest_wape": None,
        }

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    COUNT(*) AS forecast_sku_count,
                    SUM(CASE WHEN sku_link_status='LINKED' THEN 1 ELSE 0 END) AS linked_sku_count,
                    SUM(CASE WHEN sku_link_status='PENDING_LINK' THEN 1 ELSE 0 END) AS pending_link_count,
                    SUM(CASE WHEN trend_level='UP' AND confidence_level='HIGH' THEN 1 ELSE 0 END) AS up_high_count
                FROM inv_business_forecast
                WHERE forecast_date=:forecast_date
                """
            ),
            {"forecast_date": target_date},
        ).mappings().fetchone()
        city_rows = conn.execute(
            text(
                """
                SELECT warehouse_code, risk_level, suggested_qty
                FROM inv_business_forecast_city
                WHERE forecast_date=:forecast_date
                """
            ),
            {"forecast_date": target_date},
        ).mappings().all()
        backtest = conn.execute(
            text(
                """
                SELECT
                    AVG(CASE WHEN hit_flag IS NULL THEN NULL ELSE hit_flag END) AS hit_rate,
                    SUM(ABS(forecast_error)) / NULLIF(SUM(actual_7d), 0) AS wape
                FROM inv_business_forecast
                WHERE actual_7d IS NOT NULL
                  AND forecast_date >= DATE_SUB(:forecast_date, INTERVAL 60 DAY)
                """
            ),
            {"forecast_date": target_date},
        ).mappings().fetchone()

    latest_biz = _latest_business_date(db_engine)
    data = _mapping_to_dict(row)
    affected_count, suggestion_count = _visible_city_counts(city_rows)
    data.update(
        {
            "forecast_date": target_date.isoformat(),
            "latest_business_date": latest_biz.isoformat() if latest_biz else None,
            "affected_warehouse_count": affected_count,
            "suggestion_count": suggestion_count,
            "backtest_hit_rate": _safe_float((backtest or {}).get("hit_rate")),
            "backtest_wape": _safe_float((backtest or {}).get("wape")),
        }
    )
    return data


def get_business_forecast_settings(engine: Engine | None = None) -> dict[str, Any]:
    """Return business forecast calculation settings (trend factor switch + purchase formula)."""

    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT apply_trend_factor, purchase_formula FROM inv_business_forecast_setting WHERE id=1"
            )
        ).mappings().first()
    return {
        "apply_trend_factor": bool(row["apply_trend_factor"]) if row and row["apply_trend_factor"] is not None else True,
        "purchase_formula": str(row["purchase_formula"] or "excel") if row else "excel",
    }


def save_business_forecast_settings(
    apply_trend_factor: bool,
    purchase_formula: str = "excel",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Persist business forecast calculation settings."""

    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    formula = "excel" if str(purchase_formula or "").strip().lower() == "excel" else "system"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO inv_business_forecast_setting (id, apply_trend_factor, purchase_formula, updated_at)
                VALUES (1, :value, :formula, NOW())
                ON DUPLICATE KEY UPDATE
                    apply_trend_factor=VALUES(apply_trend_factor),
                    purchase_formula=VALUES(purchase_formula),
                    updated_at=NOW()
                """
            ),
            {"value": 1 if apply_trend_factor else 0, "formula": formula},
        )
    return get_business_forecast_settings(db_engine)


def get_business_forecast_options(engine: Engine | None = None) -> dict[str, Any]:
    """Return persisted date and dimension values used by the observation page filters."""

    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    with db_engine.connect() as conn:
        forecast_dates = conn.execute(
            text(
                """
                SELECT DISTINCT forecast_date
                FROM inv_business_forecast
                ORDER BY forecast_date DESC
                LIMIT 120
                """
            )
        ).scalars().all()
        business_dates = conn.execute(
            text(
                """
                SELECT DISTINCT biz_date
                FROM inv_business_daily
                ORDER BY biz_date DESC
                LIMIT 120
                """
            )
        ).scalars().all()

        latest_forecast_date = forecast_dates[0] if forecast_dates else None
        latest_snapshot_date = conn.execute(
            text("SELECT MAX(snapshot_date) FROM inv_stock_snapshot")
        ).scalar()
        brands: list[str] = []
        categories: list[str] = []
        if latest_forecast_date:
            brands = [
                str(value)
                for value in conn.execute(
                    text(
                        """
                        SELECT DISTINCT brand
                        FROM inv_business_forecast
                        WHERE forecast_date=:forecast_date AND brand<>''
                        ORDER BY brand
                        """
                    ),
                    {"forecast_date": latest_forecast_date},
                ).scalars().all()
            ]
            categories = [
                str(value)
                for value in conn.execute(
                    text(
                        """
                        SELECT category_name
                        FROM (
                            SELECT category AS category_name
                            FROM inv_business_forecast
                            WHERE forecast_date=:forecast_date AND category<>''
                            UNION
                            SELECT category_l1 AS category_name
                            FROM inv_business_forecast
                            WHERE forecast_date=:forecast_date AND category_l1<>''
                            UNION
                            SELECT category_l2 AS category_name
                            FROM inv_business_forecast
                            WHERE forecast_date=:forecast_date AND category_l2<>''
                            UNION
                            SELECT category_l3 AS category_name
                            FROM inv_business_forecast
                            WHERE forecast_date=:forecast_date AND category_l3<>''
                        ) AS category_options
                        ORDER BY category_name
                        """
                    ),
                    {"forecast_date": latest_forecast_date},
                ).scalars().all()
            ]

    return {
        "forecast_dates": [_parse_date(value).isoformat() for value in forecast_dates if _parse_date(value)],
        "business_dates": [_parse_date(value).isoformat() for value in business_dates if _parse_date(value)],
        "latest_snapshot_date": _parse_date(latest_snapshot_date).isoformat() if _parse_date(latest_snapshot_date) else None,
        "brands": brands,
        "categories": categories,
    }


def _business_forecast_filter_clause(
    target_date: date,
    sku_code: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    trend_level: str | None = None,
    confidence_level: str | None = None,
    sku_link_status: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    where = ["forecast_date=:forecast_date"]
    params: dict[str, Any] = {"forecast_date": target_date}
    if sku_code:
        where.append("sku_code LIKE :sku_code")
        params["sku_code"] = f"%{inventory_service._clean_sku(sku_code)}%"
    if product_name:
        where.append("product_name LIKE :product_name")
        params["product_name"] = f"%{product_name.strip()}%"
    if brand:
        where.append("brand=:brand")
        params["brand"] = brand.strip()
    if category:
        where.append("(category=:category OR category_l1=:category OR category_l2=:category OR category_l3=:category)")
        params["category"] = category.strip()
    if trend_level:
        where.append("trend_level=:trend_level")
        params["trend_level"] = trend_level.strip().upper()
    if confidence_level:
        where.append("confidence_level=:confidence_level")
        params["confidence_level"] = confidence_level.strip().upper()
    if sku_link_status:
        where.append("sku_link_status=:sku_link_status")
        params["sku_link_status"] = sku_link_status.strip().upper()
    return where, params


def list_business_forecasts(
    engine: Engine | None = None,
    forecast_date: str | date | None = None,
    sku_code: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    trend_level: str | None = None,
    confidence_level: str | None = None,
    sku_link_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    target_date = _resolve_business_forecast_date(db_engine, forecast_date)
    if not target_date:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    where, params = _business_forecast_filter_clause(
        target_date,
        sku_code,
        product_name,
        None,
        None,
        trend_level,
        confidence_level,
        sku_link_status,
    )

    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 20)))
    offset = (page - 1) * page_size

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT f.*,
                       NULLIF(s.brand, '') AS inventory_brand,
                       NULLIF(s.category, '') AS inventory_category,
                       NULLIF(s.product_name, '') AS inventory_product_name
                FROM (
                    SELECT *
                    FROM inv_business_forecast
                    WHERE {' AND '.join(where)}
                ) f
                LEFT JOIN inv_sku s ON s.sku_code=f.sku_code
                """
            ),
            params,
        ).mappings().all()
        city_rows = conn.execute(
            text(
                """
                SELECT sku_code, warehouse_code, risk_level, suggested_qty
                FROM inv_business_forecast_city
                WHERE forecast_date=:forecast_date
                """
            ),
            {"forecast_date": target_date},
        ).mappings().all()

    cities_by_sku: dict[str, list[Any]] = defaultdict(list)
    for city_row in city_rows:
        cities_by_sku[str(city_row.get("sku_code") or "")].append(city_row)

    items = [_normalize_forecast_row(row) for row in rows]
    for item in items:
        affected_count, suggestion_count = _visible_city_counts(
            cities_by_sku.get(str(item.get("sku_code") or ""), [])
        )
        item["affected_warehouse_count"] = affected_count
        item["suggestion_count"] = suggestion_count

    trend_order = {TREND_UP: 0, TREND_STABLE: 1, TREND_DOWN: 2}
    confidence_order = {CONFIDENCE_HIGH: 0, CONFIDENCE_MID: 1, CONFIDENCE_LOW: 2}
    items.sort(
        key=lambda item: (
            trend_order.get(str(item.get("trend_level") or ""), 2),
            confidence_order.get(str(item.get("confidence_level") or ""), 2),
            -int(item.get("suggestion_count") or 0),
            -_safe_float(item.get("adjusted_pred_7d")),
            str(item.get("sku_code") or ""),
        )
    )
    total = len(items)
    paged_items = items[offset : offset + page_size]

    return {
        "items": paged_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_business_forecast_detail(
    sku_code: str,
    engine: Engine | None = None,
    forecast_date: str | date | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    clean_sku = inventory_service._clean_sku(sku_code)
    target_date = _resolve_business_forecast_date(db_engine, forecast_date)
    if not target_date or not clean_sku:
        return {"forecast": None, "cities": []}

    with db_engine.connect() as conn:
        forecast = conn.execute(
            text(
                """
                SELECT *
                FROM inv_business_forecast
                WHERE forecast_date=:forecast_date AND sku_code=:sku_code
                LIMIT 1
                """
            ),
            {"forecast_date": target_date, "sku_code": clean_sku},
        ).mappings().fetchone()
        if not forecast:
            return {"forecast": None, "cities": []}
        cities = conn.execute(
            text(
                """
                SELECT *
                FROM inv_business_forecast_city
                WHERE forecast_date=:forecast_date AND sku_code=:sku_code
                ORDER BY
                  CASE risk_level WHEN 'HIGH' THEN 0 WHEN 'MID' THEN 1 ELSE 2 END,
                  suggested_qty DESC,
                  predicted_city_7d DESC,
                  warehouse_code ASC
                """
            ),
            {"forecast_date": target_date, "sku_code": clean_sku},
        ).mappings().all()

    forecast_data = _normalize_forecast_row(forecast)
    affected_count, suggestion_count = _visible_city_counts(cities)
    forecast_data["affected_warehouse_count"] = affected_count
    forecast_data["suggestion_count"] = suggestion_count
    return {
        "forecast": forecast_data,
        "cities": [_normalize_city_row(row) for row in cities if _is_forecast_city(row.get("warehouse_code"))],
    }


def _business_forecast_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    trend_order = {TREND_UP: 0, TREND_STABLE: 1, TREND_DOWN: 2}
    confidence_order = {CONFIDENCE_HIGH: 0, CONFIDENCE_MID: 1, CONFIDENCE_LOW: 2}
    return (
        trend_order.get(str(item.get("trend_level") or ""), 2),
        confidence_order.get(str(item.get("confidence_level") or ""), 2),
        -int(item.get("suggestion_count") or 0),
        -_safe_float(item.get("adjusted_pred_7d")),
        str(item.get("sku_code") or ""),
    )


def _forecast_brand(inventory_brand: Any, business_brand: Any) -> str:
    return _clean_text(inventory_brand) or _clean_text(business_brand)


def _purchase_export_filename(brand: str | None = None) -> str:
    brand_text = (brand or "").strip()
    if brand_text:
        safe_brand = "".join(ch for ch in brand_text if ch not in r'\/:*?"<>|').strip()
        return f"{safe_brand or brand_text}补货.xlsx"
    return "全部导出.xlsx"


def _purchase_export_erp(brand: str | None = None) -> str:
    brand_text = (brand or "").strip()
    if "测试旅行" in brand_text or "samsonite" in brand_text.lower():
        return "fengjingwei"
    return ""


def _purchase_export_qty(value: Any) -> int:
    qty = _safe_float(value)
    if qty <= 0:
        return 0
    return int(math.ceil(qty))


def _format_purchase_number(value: Any, *, digits: int = 1) -> str:
    number = _safe_float(value)
    if abs(number - round(number)) < 0.05:
        return str(int(round(number)))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _merge_purchase_city_detail(city_row: Any, target: dict[str, Any], *, signed: bool = False) -> None:
    if signed:
        # Excel 算法下保留负数展示（负值=已超储）
        suggested_qty = _safe_float(city_row.get("suggested_qty"))
    else:
        suggested_qty = _purchase_export_qty(city_row.get("suggested_qty"))
    target["suggested_qty"] = target.get("suggested_qty", 0) + suggested_qty
    for key in (
        "predicted_city_7d",
        "daily_city_forecast",
        "stock_qty",
        "inbound_qty",
        "available_qty",
        "orderable_qty",
        "shortage_qty",
        "city_sales_30d",
    ):
        target[key] = _safe_float(target.get(key)) + _safe_float(city_row.get(key))

    stock_qty = _safe_float(target.get("stock_qty"))
    inbound_qty = _safe_float(target.get("inbound_qty"))
    available_qty = _safe_float(target.get("available_qty"))
    if available_qty <= 0 and (stock_qty > 0 or inbound_qty > 0):
        available_qty = stock_qty + inbound_qty
        target["available_qty"] = available_qty

    daily_forecast = _safe_float(target.get("daily_city_forecast"))
    if daily_forecast <= 0:
        predicted_city_7d = _safe_float(target.get("predicted_city_7d"))
        if predicted_city_7d > 0:
            daily_forecast = predicted_city_7d / 7
            target["daily_city_forecast"] = daily_forecast

    if daily_forecast > 0 or available_qty > 0:
        target["days_of_supply"] = _days_of_supply(available_qty, daily_forecast)
    elif "days_of_supply" not in target:
        target["days_of_supply"] = _safe_float(city_row.get("days_of_supply"))

    target_days = _safe_float(city_row.get("target_days"))
    if target_days > 0:
        target["target_days"] = max(_safe_float(target.get("target_days")), target_days)

    if suggested_qty > 0:
        if city_row.get("route_path") and not target.get("route_path"):
            target["route_path"] = str(city_row.get("route_path") or "")
        if city_row.get("eta_days") and not target.get("eta_days"):
            target["eta_days"] = int(_safe_float(city_row.get("eta_days")))


def _purchase_city_reason(city: str, qty: int, detail: dict[str, Any] | None) -> str:
    if not detail:
        return f"{city}补{qty}件，是因为该仓近30日出库按目标周转测算后存在缺口。"

    sales_30d = _format_purchase_number(detail.get("city_sales_30d"))
    stock = _format_purchase_number(detail.get("stock_qty"))
    inbound = _format_purchase_number(detail.get("inbound_qty"))
    target_days = _safe_float(detail.get("target_days")) or 30

    text = (
        f"{city}补{qty}件：该仓近30日出库约{sales_30d}件，"
        f"按目标周转{_format_purchase_number(target_days)}天与可订购库存(库存{stock}件+在途{inbound}件)测算，"
        f"仍缺{qty}件"
    )
    route_path = str(detail.get("route_path") or "").strip()
    eta_days = int(_safe_float(detail.get("eta_days")))
    if route_path:
        text += f"，参考路径{route_path}"
        if eta_days > 0:
            text += f"，约{eta_days}天到"
    return text + "。"


def _purchase_reason_summary(row: dict[str, Any], city_qty: dict[str, int]) -> str:
    # Excel 算法下 city_qty 可能含负数（超储），合计只累计正数可执行补货量
    total_qty = sum(_purchase_export_qty(v) for v in city_qty.values())
    sales_30d_total = _safe_float(row.get("sales_30d_total"))
    target_days = _safe_float(row.get("target_days")) or 30
    if total_qty <= 0:
        return "当前八大仓按近30日出库与目标周转测算后暂无补货缺口。"

    active_cities = [city for city in PURCHASE_EXPORT_CITIES if city_qty.get(city, 0) > 0]
    city_text = "、".join(f"{city}{city_qty.get(city, 0)}件" for city in active_cities[:4])
    if len(active_cities) > 4:
        city_text += f"等{len(active_cities)}个仓"
    return (
        f"该SKU八大仓近30日出库合计约{_format_purchase_number(sales_30d_total)}件，"
        f"按目标周转{_format_purchase_number(target_days)}天与可订购库存测算，"
        f"{city_text}需要补货，合计{total_qty}件；未列出的仓当前不缺货。"
    )


def _purchase_reason_details(
    city_qty: dict[str, int],
    city_detail: dict[str, dict[str, Any]] | None = None,
    huadong_available_qty: float | None = None,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for city in PURCHASE_EXPORT_CITIES:
        qty = city_qty.get(city, 0)
        if qty <= 0:
            continue
        detail = (city_detail or {}).get(city, {})
        details.append(
            {
                "city": city,
                "suggested_qty": qty,
                "predicted_city_7d": round(_safe_float(detail.get("predicted_city_7d")), 1),
                "stock_qty": round(_safe_float(detail.get("stock_qty")), 1),
                "inbound_qty": round(_safe_float(detail.get("inbound_qty")), 1),
                "available_qty": round(_safe_float(detail.get("available_qty")), 1),
                "orderable_qty": round(_safe_float(detail.get("orderable_qty")), 1),
                "huadong_available_qty": round(_safe_float(huadong_available_qty), 1),
                "days_of_supply": round(_safe_float(detail.get("days_of_supply")), 1),
                "target_days": round(_safe_float(detail.get("target_days")) or 30, 1),
                "route_path": str(detail.get("route_path") or ""),
                "eta_days": int(_safe_float(detail.get("eta_days"))),
            }
        )
    return details


def _purchase_reason_text(
    row: dict[str, Any],
    city_qty: dict[str, int],
    city_detail: dict[str, dict[str, Any]] | None = None,
) -> str:
    total_qty = sum(_purchase_export_qty(v) for v in city_qty.values())
    if total_qty > 0:
        active_cities = [city for city in PURCHASE_EXPORT_CITIES if city_qty.get(city, 0) > 0]
        city_reasons = " ".join(
            _purchase_city_reason(city, city_qty.get(city, 0), (city_detail or {}).get(city))
            for city in active_cities
        )
        return f"{_purchase_reason_summary(row, city_qty)}{city_reasons}"
    return _purchase_reason_summary(row, city_qty)


def _purchase_row_total_qty(row: dict[str, Any]) -> int:
    return sum(_purchase_export_qty(row.get(city)) for city in PURCHASE_EXPORT_CITIES)


def _purchase_filter_options(rows: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    brands = sorted({str(row.get("brand") or "").strip() for row in rows if str(row.get("brand") or "").strip()})
    categories = sorted({str(row.get("category") or "").strip() for row in rows if str(row.get("category") or "").strip()})
    return {"brands": brands, "categories": categories}


def _purchase_row_category(row: dict[str, Any]) -> str:
    return (
        str(row.get("inventory_category") or "").strip()
        or str(row.get("inventory_category_l1") or "").strip()
        or str(row.get("inventory_category_l2") or "").strip()
        or str(row.get("inventory_category_l3") or "").strip()
        or str(row.get("category") or "").strip()
        or str(row.get("category_l1") or "").strip()
        or str(row.get("category_l2") or "").strip()
        or str(row.get("category_l3") or "").strip()
        or inventory_service._brand_category(row.get("inventory_brand") or row.get("brand"))
    )


def _purchase_hub_available_qty(hub_stock_by_sku: dict[str, dict[str, Any]] | None, sku_code: str) -> float:
    stock = (hub_stock_by_sku or {}).get(sku_code) or {}
    available = _safe_float(stock.get("available_qty"))
    if available > 0:
        return available
    stock_qty = _safe_float(stock.get("stock_qty"))
    inbound_qty = _safe_float(stock.get("inbound_qty"))
    return stock_qty + inbound_qty


def _filter_purchase_rows_by_effective_fields(
    items: Iterable[dict[str, Any]],
    *,
    sku_code: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    sku_text = inventory_service._clean_sku(sku_code or "")
    product_text = (product_name or "").strip()
    brand_text = (brand or "").strip()
    category_text = (category or "").strip()
    filtered: list[dict[str, Any]] = []
    for row in items:
        if sku_text and sku_text not in str(row.get("sku_code") or ""):
            continue
        if product_text and product_text not in str(row.get("product_name") or ""):
            continue
        if brand_text and str(row.get("brand") or "").strip() != brand_text:
            continue
        if category_text and str(row.get("category") or "").strip() != category_text:
            continue
        filtered.append(row)
    return filtered


def _load_transfer_purchase_city_rows(db_engine: Engine, target_date: date) -> list[dict[str, Any]]:
    """Load today's executable transfer suggestions as purchase-export fallback rows."""

    with db_engine.connect() as conn:
        plan_date = conn.execute(
            text(
                """
                SELECT MAX(plan_date)
                FROM inv_transfer_plan
                WHERE plan_date <= :target_date
                """
            ),
            {"target_date": target_date},
        ).scalar()
        if not plan_date:
            return []

        rows = conn.execute(
            text(
                """
                SELECT
                    p.plan_date AS forecast_date,
                    p.sku_code,
                    p.to_warehouse AS warehouse_code,
                    p.transfer_qty AS suggested_qty,
                    p.route_path,
                    p.eta_days,
                    p.target_days,
                    sku.product_name AS inventory_product_name,
                    sku.brand AS inventory_brand,
                    sku.category AS inventory_category,
                    to_snap.stock_qty,
                    to_snap.inbound_qty,
                    to_risk.daily_sales AS daily_city_forecast,
                    to_risk.days_of_supply
                FROM inv_transfer_plan p
                LEFT JOIN inv_sku sku ON sku.sku_code=p.sku_code
                LEFT JOIN inv_stock_snapshot to_snap
                  ON to_snap.snapshot_date=p.plan_date
                 AND to_snap.sku_code=p.sku_code
                 AND to_snap.warehouse_code=p.to_warehouse
                LEFT JOIN inv_risk_score to_risk
                  ON to_risk.snapshot_date=p.plan_date
                 AND to_risk.sku_code=p.sku_code
                 AND to_risk.warehouse_code=p.to_warehouse
                WHERE p.plan_date=:plan_date
                  AND p.transfer_qty > 0
                  AND p.status <> 'CANCELLED'
                """
            ),
            {"plan_date": plan_date},
        ).mappings().all()

    output: list[dict[str, Any]] = []
    for row in rows:
        data = _mapping_to_dict(row)
        base_city = inventory_service._base_city(str(data.get("warehouse_code") or ""))
        if base_city not in PURCHASE_EXPORT_CITIES:
            continue
        daily = _safe_float(data.get("daily_city_forecast"))
        stock = _safe_float(data.get("stock_qty"))
        inbound = _safe_float(data.get("inbound_qty"))
        available = stock + inbound
        target_days = _safe_float(data.get("target_days")) or 30
        data["warehouse_code"] = base_city
        data["predicted_city_7d"] = daily * DEFAULT_FORECAST_DAYS
        data["available_qty"] = available
        if _safe_float(data.get("days_of_supply")) <= 0:
            data["days_of_supply"] = _days_of_supply(available, daily)
        data["target_days"] = target_days
        output.append(data)
    return output


def _merge_transfer_purchase_fallback(
    forecast_rows: list[Any],
    city_rows: list[Any],
    transfer_rows: Iterable[dict[str, Any]],
) -> tuple[list[Any], list[Any]]:
    """Add transfer-plan SKU/city rows missing from business forecast suggestions."""

    merged_forecasts: list[Any] = list(forecast_rows)
    merged_cities: list[dict[str, Any]] = [_mapping_to_dict(row) for row in city_rows]
    forecast_skus = {str(row.get("sku_code") or "") for row in map(_mapping_to_dict, forecast_rows)}
    synthetic_forecast_by_sku: dict[str, dict[str, Any]] = {}
    business_city_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in merged_cities:
        key = (
            str(row.get("sku_code") or ""),
            inventory_service._base_city(str(row.get("warehouse_code") or "")),
        )
        business_city_by_key.setdefault(key, row)
    covered_city_keys = {
        key
        for key, row in business_city_by_key.items()
        if _purchase_export_qty(row.get("suggested_qty")) > 0
    }

    for raw_row in transfer_rows:
        row = _mapping_to_dict(raw_row)
        sku = str(row.get("sku_code") or "")
        city = inventory_service._base_city(str(row.get("warehouse_code") or ""))
        if not sku or city not in PURCHASE_EXPORT_CITIES:
            continue
        # iGear/iGear工业品 不走调拨回退：其补货导出明细按货盘表
        # 「近30日出库 − 可订 + 箱规取整」公式独立计算，避免旧经营预测调拨量混入。
        if inventory_service._is_nansha_supply_brand(row.get("inventory_brand")):
            continue
        existing = business_city_by_key.get((sku, city))
        if existing is not None:
            if _purchase_export_qty(existing.get("suggested_qty")) > 0:
                continue
            transfer_qty = _purchase_export_qty(row.get("suggested_qty"))
            if transfer_qty <= 0:
                continue
            existing["suggested_qty"] = transfer_qty
            if not existing.get("route_path") and row.get("route_path"):
                existing["route_path"] = str(row.get("route_path") or "")
            if not existing.get("eta_days") and row.get("eta_days"):
                existing["eta_days"] = int(_safe_float(row.get("eta_days")))
            covered_city_keys.add((sku, city))
            continue
        if (sku, city) in covered_city_keys:
            continue
        merged_cities.append(row)
        covered_city_keys.add((sku, city))
        predicted_7d = _safe_float(row.get("predicted_city_7d"))
        if sku in synthetic_forecast_by_sku:
            synthetic = synthetic_forecast_by_sku[sku]
            synthetic["base_pred_7d"] = _safe_float(synthetic.get("base_pred_7d")) + predicted_7d
            synthetic["adjusted_pred_7d"] = _safe_float(synthetic.get("adjusted_pred_7d")) + predicted_7d
        elif sku not in forecast_skus:
            synthetic = {
                "forecast_date": row.get("forecast_date"),
                "sku_code": sku,
                "product_name": row.get("inventory_product_name") or "",
                "inventory_product_name": row.get("inventory_product_name") or "",
                "brand": row.get("inventory_brand") or "",
                "inventory_brand": row.get("inventory_brand") or "",
                "category": row.get("inventory_category") or "",
                "inventory_category": row.get("inventory_category") or "",
                "sku_link_status": LINKED,
                "trend_level": TREND_STABLE,
                "confidence_level": CONFIDENCE_MID,
                "base_pred_7d": predicted_7d,
                "adjusted_pred_7d": predicted_7d,
            }
            merged_forecasts.append(synthetic)
            synthetic_forecast_by_sku[sku] = synthetic
            forecast_skus.add(sku)

    return merged_forecasts, merged_cities


def _build_purchase_rows_from_forecasts(
    forecast_rows: Iterable[Any],
    city_rows: Iterable[Any],
    *,
    only_with_qty: bool = True,
    transfer_reason_by_sku: dict[str, str] | None = None,
    hub_stock_by_sku: dict[str, dict[str, Any]] | None = None,
    signed_qty: bool = False,
) -> list[dict[str, Any]]:
    _ = transfer_reason_by_sku
    city_qty_by_sku: dict[str, dict[str, int]] = defaultdict(lambda: {city: 0 for city in PURCHASE_EXPORT_CITIES})
    city_detail_by_sku: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for city_row in city_rows:
        base_city = inventory_service._base_city(str(city_row.get("warehouse_code") or ""))
        if base_city not in PURCHASE_EXPORT_CITIES:
            continue
        sku = str(city_row.get("sku_code") or "")
        if signed_qty:
            # Excel 算法下保留负数展示（负值=已超储）
            qty = _safe_float(city_row.get("suggested_qty"))
        else:
            qty = _purchase_export_qty(city_row.get("suggested_qty"))
        city_qty_by_sku[sku][base_city] += qty
        detail = city_detail_by_sku[sku].setdefault(base_city, {})
        _merge_purchase_city_detail(city_row, detail, signed=signed_qty)

    export_rows: list[dict[str, Any]] = []
    for raw_row in forecast_rows:
        row = _normalize_forecast_row(raw_row)
        if row.get("sku_link_status") == PENDING_LINK:
            continue
        sku = str(row.get("sku_code") or "")
        city_qty = city_qty_by_sku.get(sku, {city: 0 for city in PURCHASE_EXPORT_CITIES})
        city_detail = city_detail_by_sku.get(sku, {})
        huadong_available_qty = _purchase_hub_available_qty(hub_stock_by_sku, sku)
        product_name = str(row.get("inventory_product_name") or row.get("product_name") or "").strip()
        brand = str(row.get("inventory_brand") or row.get("brand") or "").strip()
        category = _purchase_row_category(row)
        export_row: dict[str, Any] = {
            "purchaser_erp": _purchase_export_erp(brand),
            "sku_code": sku,
            "product_name": product_name,
            "brand": brand,
            "category": category,
            "category_l1": str(row.get("category_l1") or "").strip(),
            "category_l2": str(row.get("category_l2") or "").strip(),
            "category_l3": str(row.get("category_l3") or "").strip(),
            "huadong_available_qty": round(huadong_available_qty, 1),
            "purchase_reason": _purchase_reason_text(row, city_qty, city_detail),
            "purchase_reason_summary": _purchase_reason_summary(row, city_qty),
            "purchase_reason_details": _purchase_reason_details(city_qty, city_detail, huadong_available_qty),
            "trend_level": row.get("trend_level"),
            "confidence_level": row.get("confidence_level"),
            "suggestion_count": sum(1 for qty in city_qty.values() if qty > 0),
            "adjusted_pred_7d": row.get("adjusted_pred_7d"),
        }
        export_row.update(city_qty)
        if only_with_qty and _purchase_row_total_qty(export_row) <= 0:
            continue
        export_rows.append(export_row)

    export_rows.sort(key=_business_forecast_sort_key)
    return export_rows


def _load_transfer_reason_by_sku(db_engine: Engine, target_date: date) -> dict[str, str]:
    """Load the latest transfer-plan reason for each SKU around the forecast date."""

    with db_engine.connect() as conn:
        plan_date = conn.execute(
            text(
                """
                SELECT MAX(plan_date)
                FROM inv_transfer_plan
                WHERE plan_date <= :target_date
                """
            ),
            {"target_date": target_date},
        ).scalar()
        if not plan_date:
            return {}

        rows = conn.execute(
            text(
                """
                SELECT sku_code, reason
                FROM inv_transfer_plan
                WHERE plan_date=:plan_date
                  AND reason IS NOT NULL
                  AND reason<>''
                ORDER BY
                    sku_code ASC,
                    CASE priority WHEN 'HIGH' THEN 0 WHEN 'MID' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,
                    eta_late DESC,
                    risk_days ASC,
                    eta_days ASC,
                    transfer_qty DESC,
                    score DESC,
                    id ASC
                """
            ),
            {"plan_date": plan_date},
        ).mappings().all()

    reasons: dict[str, str] = {}
    for row in rows:
        sku = str(row.get("sku_code") or "")
        reason = str(row.get("reason") or "").strip()
        if sku and reason and sku not in reasons:
            reasons[sku] = reason
    return reasons


def build_business_purchase_export_workbook(export_rows: list[dict[str, Any]]) -> bytes:
    """Build the replenishment workbook in the operator-provided horizontal style."""

    wb = Workbook()
    ws = wb.active
    ws.title = "Horizontal"

    for col_idx, header in enumerate(PURCHASE_EXPORT_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(name="微软雅黑", size=14)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.number_format = "@" if col_idx != 2 else "0_);[Red]\\(0\\)"
    ws.row_dimensions[1].height = 36

    for row_idx, row in enumerate(export_rows, start=2):
        values = [
            row.get("purchaser_erp") or "",
            str(row.get("sku_code") or ""),
            row.get("product_name") or "",
            None,
            None,
            None,
            None,
            *[_purchase_export_qty(row.get(city)) for city in PURCHASE_EXPORT_CITIES],
        ]
        for col_idx, value in enumerate(values, start=1):
            if value is None and 4 <= col_idx <= 7:
                continue
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 3:
                cell.font = Font(name="微软雅黑", size=11)
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col_idx == 1:
                cell.font = Font(name="宋体", size=12)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 2:
                cell.font = Font(name="宋体", size=12)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.number_format = "@"
            elif col_idx in {3, 7}:
                cell.font = Font(name="微软雅黑", size=11)
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.font = Font(name="宋体", size=11)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if col_idx >= 8:
                    cell.number_format = "0"
            ws.row_dimensions[row_idx].height = 16.5

    for col, width in PURCHASE_EXPORT_WIDTHS.items():
        ws.column_dimensions[col].width = width

    io = BytesIO()
    wb.save(io)
    return io.getvalue()


def export_business_purchase_replenishment(
    engine: Engine | None = None,
    forecast_date: str | date | None = None,
    sku_code: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    trend_level: str | None = None,
    confidence_level: str | None = None,
    sku_link_status: str | None = None,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    # 补货导出与经营预测解耦：数据源固定为最新库存快照，忽略经营预测日期。
    snapshot_date = inventory_service._resolve_snapshot_date(db_engine, None, allow_none=True)
    filename = _purchase_export_filename(brand)
    if not snapshot_date:
        raise ValueError("暂无库存快照数据，请先导入库存表")

    purchase_formula = str(get_business_forecast_settings(db_engine).get("purchase_formula", "system")).lower()
    forecast_rows, city_rows = _build_snapshot_purchase_forecast_rows(
        db_engine, snapshot_date, purchase_formula
    )
    hub_stock_by_sku = inventory_service._latest_supply_stocks(
        db_engine,
        inventory_service.SUPPLY_HUB_WAREHOUSE,
    )
    forecast_rows, city_rows = _merge_transfer_purchase_fallback(
        forecast_rows,
        city_rows,
        _load_transfer_purchase_city_rows(db_engine, snapshot_date),
    )
    export_rows = _filter_purchase_rows_by_effective_fields(
        _build_purchase_rows_from_forecasts(
            forecast_rows,
            city_rows,
            hub_stock_by_sku=hub_stock_by_sku,
            signed_qty=(purchase_formula == "excel"),
        ),
        sku_code=sku_code,
        product_name=product_name,
        brand=brand,
        category=category,
    )
    if not export_rows:
        raise ValueError("当前筛选下暂无可导出的补货明细")
    return {
        "filename": filename,
        "content": build_business_purchase_export_workbook(export_rows),
        "row_count": len(export_rows),
        "forecast_date": snapshot_date.isoformat(),
    }


def _load_snapshot_purchase_snapshots(db_engine: Engine, snapshot_date: date) -> list[dict[str, Any]]:
    """Load active inventory snapshots joined with SKU meta for snapshot-driven purchase rows.

    补货导出明细与经营预测解耦后，直接以最新库存快照为数据源：
    每条快照自带 库存件数/采购未到货/近1/7/30日出库，足以按 40周转 公式独立计算。
    """
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    s.sku_code,
                    s.warehouse_code,
                    s.stock_qty,
                    s.inbound_qty,
                    s.available_qty,
                    s.orderable_qty,
                    s.sales_1d,
                    s.sales_7d,
                    s.sales_14d,
                    s.sales_30d,
                    NULLIF(sku.product_name, '') AS product_name,
                    NULLIF(sku.brand, '') AS brand,
                    NULLIF(sku.category, '') AS category,
                    NULLIF(sku.shop_name, '') AS shop_name,
                    NULLIF(sku.case_pack, 0) AS case_pack
                FROM inv_stock_snapshot s
                LEFT JOIN inv_sku sku ON sku.sku_code = s.sku_code
                WHERE s.snapshot_date=:snapshot_date
                  AND s.is_decision_active=1
                """
            ),
            {"snapshot_date": snapshot_date},
        ).mappings().all()
    return [_mapping_to_dict(row) for row in rows]


def _snapshot_trend_level(snapshots: list[dict[str, Any]]) -> str:
    sales_7d = sum(_safe_float(snap.get("sales_7d")) for snap in snapshots)
    sales_30d = sum(_safe_float(snap.get("sales_30d")) for snap in snapshots)
    daily_recent = sales_7d / 7.0
    daily_overall = sales_30d / 30.0
    if daily_overall <= 0:
        return TREND_STABLE
    ratio = daily_recent / daily_overall
    if ratio >= 1.15:
        return TREND_UP
    if ratio <= 0.85:
        return TREND_DOWN
    return TREND_STABLE


def _snapshot_confidence_level(sales_30d_total: float) -> str:
    if sales_30d_total >= 60:
        return CONFIDENCE_HIGH
    if sales_30d_total >= 15:
        return CONFIDENCE_MID
    return CONFIDENCE_LOW


def _build_snapshot_purchase_forecast_rows(
    db_engine: Engine,
    snapshot_date: date,
    purchase_formula: str = "system",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build purchase forecast-shaped rows + city rows directly from the latest inventory snapshot.

    不读取 inv_business_forecast / inv_business_forecast_city，因此补货导出明细
    只依赖库存快照与品牌周转策略，与经营预测完全解耦。
    """
    purchase_formula = str(purchase_formula or "system").lower()
    snapshots = _load_snapshot_purchase_snapshots(db_engine, snapshot_date)
    if not snapshots:
        return [], []
    policies = inventory_service._load_replenishment_policies(db_engine)
    supply_stocks = inventory_service._latest_supply_stocks_by_warehouse(db_engine)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snap in snapshots:
        if not _is_forecast_city(snap.get("warehouse_code")):
            continue
        if (
            _safe_float(snap.get("sales_1d"))
            + _safe_float(snap.get("sales_7d"))
            + _safe_float(snap.get("sales_30d"))
        ) <= 0:
            continue
        grouped.setdefault(str(snap["sku_code"] or ""), []).append(snap)

    forecast_rows: list[dict[str, Any]] = []
    city_rows: list[dict[str, Any]] = []
    for sku_code, sku_snaps in sorted(grouped.items()):
        if not sku_code:
            continue
        meta = sku_snaps[0]
        brand = _clean_text(meta.get("brand"))
        category = _clean_text(meta.get("category")) or inventory_service._brand_category(brand)
        policy = inventory_service._resolve_policy(policies, brand, category)
        cities, _ = _build_city_rows(
            forecast_date=snapshot_date,
            sku_code=sku_code,
            brand=brand,
            category=category,
            adjustment_factor=1.0,
            snapshots=sku_snaps,
            policy=policy,
            supply_stocks=supply_stocks,
            purchase_formula=purchase_formula,
            case_pack=_safe_float(meta.get("case_pack")),
        )
        if not cities:
            continue
        sales_30d_total = sum(_safe_float(cr.get("city_sales_30d")) for cr in cities)
        daily_total = sum(_safe_float(cr.get("daily_city_forecast")) for cr in cities)
        pred_7d = daily_total * DEFAULT_FORECAST_DAYS
        product_name = _clean_text(meta.get("product_name"))
        forecast_rows.append(
            {
                "forecast_date": snapshot_date,
                "sku_code": sku_code,
                "product_name": product_name,
                "brand": brand,
                "category": category,
                "inventory_product_name": product_name,
                "inventory_brand": brand,
                "inventory_category": category,
                "sku_link_status": LINKED,
                "trend_level": _snapshot_trend_level(sku_snaps),
                "confidence_level": _snapshot_confidence_level(sales_30d_total),
                "adjusted_pred_7d": round(pred_7d, 4),
                "base_pred_7d": round(pred_7d, 4),
                "sales_30d_total": round(sales_30d_total, 4),
                "target_days": float(policy.target_days or inventory_service.TARGET_DAYS),
            }
        )
        city_rows.extend(cities)
    return forecast_rows, city_rows


def list_business_purchase_replenishment_rows(
    engine: Engine | None = None,
    forecast_date: str | date | None = None,
    sku_code: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    trend_level: str | None = None,
    confidence_level: str | None = None,
    sku_link_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    db_engine = get_engine(engine)
    ensure_business_schema(db_engine)
    # 补货导出明细与经营预测解耦：数据源固定为最新库存快照，忽略经营预测日期。
    snapshot_date = inventory_service._resolve_snapshot_date(db_engine, None, allow_none=True)
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 20)))
    if not snapshot_date:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_qty": 0,
            "forecast_date": None,
            "purchase_formula": "excel",
            "brands": [],
            "categories": [],
        }

    # Excel 算法下保留负数展示（负值=已超储）；现行算法仍只出正整数
    purchase_formula = str(get_business_forecast_settings(db_engine).get("purchase_formula", "system")).lower()
    forecast_rows, city_rows = _build_snapshot_purchase_forecast_rows(
        db_engine, snapshot_date, purchase_formula
    )
    hub_stock_by_sku = inventory_service._latest_supply_stocks(
        db_engine,
        inventory_service.SUPPLY_HUB_WAREHOUSE,
    )
    forecast_rows, city_rows = _merge_transfer_purchase_fallback(
        forecast_rows,
        city_rows,
        _load_transfer_purchase_city_rows(db_engine, snapshot_date),
    )
    all_items = _build_purchase_rows_from_forecasts(
        forecast_rows,
        city_rows,
        hub_stock_by_sku=hub_stock_by_sku,
        signed_qty=(purchase_formula == "excel"),
    )
    filter_options = _purchase_filter_options(all_items)
    items = _filter_purchase_rows_by_effective_fields(
        all_items,
        sku_code=sku_code,
        product_name=product_name,
        brand=brand,
        category=category,
    )
    total_qty = sum(_purchase_row_total_qty(row) for row in items)
    offset = (page - 1) * page_size
    return {
        "items": items[offset : offset + page_size],
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "total_qty": total_qty,
        "forecast_date": snapshot_date.isoformat(),
        "purchase_formula": purchase_formula,
        **filter_options,
    }


def _build_sku_forecast(
    forecast_date: date,
    sku_code: str,
    rows: list[dict[str, Any]],
    inventory_meta: dict[str, Any] | None,
    snapshots: list[dict[str, Any]],
    policies: dict[str, Any],
    supply_stocks: dict[tuple[str, str], dict[str, Any]],
    apply_trend_factor: bool = True,
    purchase_formula: str = "system",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows_by_date = {row["biz_date"]: row for row in rows}
    window_dates = [forecast_date - timedelta(days=offset) for offset in range(LOOKBACK_DAYS - 1, -1, -1)]
    dense = [rows_by_date.get(day, _zero_metric_row(day, sku_code)) for day in window_dates]
    latest = _latest_nonempty_row(rows)

    sold = _metric_series(dense, "sold_units")

    avg3 = _avg_tail(sold, 3)
    avg7 = _avg_tail(sold, 7)
    avg14 = _avg_tail(sold, 14)
    avg30 = _avg_tail(sold, 30)
    base_pred = DEFAULT_FORECAST_DAYS * (avg3 * 0.20 + avg7 * 0.45 + avg14 * 0.25 + avg30 * 0.10)

    unit_momentum = _momentum(avg3, avg14)
    visitor_momentum = _metric_momentum(dense, "visitors")[0]
    cart_momentum = _metric_momentum(dense, "cart_users")[0]
    conversion_momentum = _metric_momentum(dense, "conversion_rate")[0]

    traffic_score, traffic_details, traffic_coverage = _signal_group_score(dense, SIGNAL_GROUPS["traffic"])
    interest_score, interest_details, interest_coverage = _signal_group_score(dense, SIGNAL_GROUPS["interest"])
    conversion_score, conversion_details, conversion_coverage = _signal_group_score(dense, SIGNAL_GROUPS["conversion"])
    quality_score, quality_details, quality_coverage = _signal_group_score(dense, SIGNAL_GROUPS["quality"])
    sales_score = _clip(unit_momentum, SIGNAL_CLIP_LOW, SIGNAL_CLIP_HIGH)
    signal_scores = {
        "sales": round(sales_score, 6),
        "traffic": round(traffic_score, 6),
        "interest": round(interest_score, 6),
        "conversion": round(conversion_score, 6),
        "quality": round(quality_score, 6),
    }
    signal_coverage = {
        "traffic": round(traffic_coverage, 4),
        "interest": round(interest_coverage, 4),
        "conversion": round(conversion_coverage, 4),
        "quality": round(quality_coverage, 4),
    }
    signal_windows = {
        "traffic": _signal_group_index_windows(dense, SIGNAL_GROUPS["traffic"], traffic_score),
        "interest": _signal_group_index_windows(dense, SIGNAL_GROUPS["interest"], interest_score),
        "conversion": _signal_group_index_windows(dense, SIGNAL_GROUPS["conversion"], conversion_score),
        "quality": _signal_group_index_windows(dense, SIGNAL_GROUPS["quality"], quality_score),
    }
    signal_score = (
        SIGNAL_WEIGHTS["sales"] * sales_score
        + SIGNAL_WEIGHTS["traffic"] * traffic_score
        + SIGNAL_WEIGHTS["interest"] * interest_score
        + SIGNAL_WEIGHTS["conversion"] * conversion_score
        + SIGNAL_WEIGHTS["quality"] * quality_score
    )

    raw_factor = 1 + signal_score
    if abs(signal_score) < SIGNAL_STABLE_BAND:
        factor = 1.0
    else:
        factor = _clip(raw_factor, ADJUSTMENT_LOW, ADJUSTMENT_HIGH)

    if factor >= 1.05:
        trend = TREND_UP
    elif factor <= 0.95:
        trend = TREND_DOWN
    else:
        trend = TREND_STABLE

    # 开关关闭时不应用经营趋势因子：预测与补货建议按城市销量基线口径计算（因子视作 1.0），
    # 但 trend_level 仍保留真实信号，仅用于展示。
    calc_factor = factor if apply_trend_factor else 1.0

    adjusted_pred = max(0.0, base_pred * calc_factor)
    days_covered = len({row["biz_date"] for row in rows if forecast_date - timedelta(days=LOOKBACK_DAYS - 1) <= row["biz_date"] <= forecast_date})
    total_30d = sum(sold)
    confidence = _confidence(days_covered, total_30d)
    linked = bool(inventory_meta)
    category = _clean_text((inventory_meta or {}).get("category")) or _clean_text(latest.get("category_l1"))
    brand = _forecast_brand((inventory_meta or {}).get("brand"), latest.get("brand"))
    product_name = _clean_text((inventory_meta or {}).get("product_name")) or _clean_text(latest.get("product_name"))
    pending_city_split = False
    city_rows: list[dict[str, Any]] = []

    if linked and snapshots:
        policy = inventory_service._resolve_policy(policies, brand, category)
        city_rows, pending_city_split = _build_city_rows(
            forecast_date=forecast_date,
            sku_code=sku_code,
            brand=brand,
            category=category,
            adjustment_factor=calc_factor,
            snapshots=snapshots,
            policy=policy,
            supply_stocks=supply_stocks,
            purchase_formula=purchase_formula,
        )
    elif linked:
        pending_city_split = True

    affected_count, suggestion_count = _visible_city_counts(city_rows)
    reason = {
        "national_formula": "future_7d = 7 * (0.20*avg3 + 0.45*avg7 + 0.25*avg14 + 0.10*avg30) * adjustment_factor",
        "adjustment_formula": "adjustment_factor = clamp(1 + 0.35*sales + 0.20*traffic + 0.20*interest + 0.15*conversion + 0.10*quality, 0.80, 1.25)",
        "city_formula": "city_future_7d = inventory_city_daily_baseline * 7 * adjustment_factor",
        "avg3": round(avg3, 4),
        "avg7": round(avg7, 4),
        "avg14": round(avg14, 4),
        "avg30": round(avg30, 4),
        "unit_momentum": round(unit_momentum, 6),
        "visitor_momentum": round(visitor_momentum, 6),
        "cart_momentum": round(cart_momentum, 6),
        "conversion_momentum": round(conversion_momentum, 6),
        "signal_score": round(signal_score, 6),
        "signal_scores": signal_scores,
        "signal_weights": SIGNAL_WEIGHTS,
        "signal_coverage": signal_coverage,
        "signal_windows": signal_windows,
        "signal_window_unit": "综合指数，近30日=100；未来点为按当前信号修正后的预测指数",
        "signal_details": {
            "traffic": traffic_details,
            "interest": interest_details,
            "conversion": conversion_details,
            "quality": quality_details,
        },
        "guardrails": {
            "metric_clip_low": SIGNAL_CLIP_LOW,
            "metric_clip_high": SIGNAL_CLIP_HIGH,
            "adjustment_low": ADJUSTMENT_LOW,
            "adjustment_high": ADJUSTMENT_HIGH,
            "stable_band": SIGNAL_STABLE_BAND,
        },
        "adjustment_factor": round(calc_factor, 6),
        "sku_link_status": LINKED if linked else PENDING_LINK,
        "pending_city_split": pending_city_split,
    }

    forecast = {
        "forecast_date": forecast_date,
        "target_start_date": forecast_date + timedelta(days=1),
        "target_end_date": forecast_date + timedelta(days=DEFAULT_FORECAST_DAYS),
        "sku_code": sku_code,
        "product_name": product_name,
        "brand": brand,
        "category": category,
        "category_l1": _clean_text(latest.get("category_l1")),
        "category_l2": _clean_text(latest.get("category_l2")),
        "category_l3": _clean_text(latest.get("category_l3")),
        "sku_link_status": LINKED if linked else PENDING_LINK,
        "days_covered": days_covered,
        "total_30d_units": round(total_30d, 4),
        "recent_3d_avg": round(avg3, 4),
        "recent_7d_avg": round(avg7, 4),
        "recent_14d_avg": round(avg14, 4),
        "recent_30d_avg": round(avg30, 4),
        "base_pred_7d": round(base_pred, 4),
        "adjusted_pred_7d": round(adjusted_pred, 4),
        "unit_momentum": round(unit_momentum, 6),
        "visitor_momentum": round(visitor_momentum, 6),
        "cart_momentum": round(cart_momentum, 6),
        "conversion_momentum": round(conversion_momentum, 6),
        "adjustment_factor": round(calc_factor, 6),
        "trend_level": trend,
        "confidence_level": confidence,
        "affected_warehouse_count": affected_count,
        "suggestion_count": suggestion_count,
        "pending_city_split": 1 if pending_city_split else 0,
        "reason_json": json.dumps(reason, ensure_ascii=False),
    }
    return forecast, city_rows


def _round_to_case_pack(raw_suggestion: float, case_pack: float) -> int | float:
    """按箱规四舍五入到最近整箱；正数至少 1 箱，负数保留原值（超储展示）。"""
    case_pack = float(case_pack or 0)
    if case_pack <= 0:
        return int(math.ceil(raw_suggestion))
    if raw_suggestion <= 0:
        return int(math.ceil(raw_suggestion))
    boxes = int(math.floor(raw_suggestion / case_pack + 0.5))
    if boxes < 1:
        boxes = 1
    rounded = float(boxes * case_pack)
    return int(rounded) if rounded == int(rounded) else round(rounded, 2)


def _build_city_rows(
    forecast_date: date,
    sku_code: str,
    brand: str,
    category: str,
    adjustment_factor: float,
    snapshots: list[dict[str, Any]],
    policy: Any,
    supply_stocks: dict[tuple[str, str], dict[str, Any]],
    purchase_formula: str = "system",
    case_pack: float = 0,
) -> tuple[list[dict[str, Any]], bool]:
    # Stock and inbound alone do not prove that a city operates this SKU. Only
    # cities with an actual outbound history are eligible for city forecasts.
    active = [
        snap for snap in snapshots
        if _is_forecast_city(snap.get("warehouse_code")) and (
            _safe_float(snap.get("sales_1d"))
            + _safe_float(snap.get("sales_7d"))
            + _safe_float(snap.get("sales_30d"))
        ) > 0
    ]
    if not active:
        return [], True

    city_daily_baselines = [
        max(0.0, _safe_float(inventory_service._forecast_daily_sales(snap, []).get("daily_sales")))
        for snap in active
    ]
    total_city_baseline = sum(city_daily_baselines)
    if total_city_baseline <= 0:
        return [], True

    target_days = float(policy.target_days or inventory_service.TARGET_DAYS)
    reserve_days = float(policy.reserve_days or inventory_service.DONOR_RESERVE_DAYS)
    city_base: list[dict[str, Any]] = []
    for snap, city_daily_baseline in zip(active, city_daily_baselines):
        sales30 = _safe_float(snap.get("sales_30d"))
        share = city_daily_baseline / total_city_baseline
        daily = city_daily_baseline * max(0.0, adjustment_factor)
        predicted_7d = daily * DEFAULT_FORECAST_DAYS
        stock = _safe_float(snap.get("stock_qty"))
        inbound = _safe_float(snap.get("inbound_qty"))
        available = stock + inbound
        # 运营表 40 周转口径的减项用「可订购」字段（系统导出列：XX可订购/XX可订购库存）。
        # 旧快照未导入该字段（为 0）时，退回 库存件数+采购未到货，保证历史口径不变。
        orderable = _safe_float(snap.get("orderable_qty"))
        if orderable <= 0:
            orderable = available
        days_supply = _days_of_supply(available, daily)
        target_need = daily * target_days
        shortage = max(0.0, target_need - available)
        if daily <= 0:
            risk = "LOW"
        elif days_supply < target_days:
            risk = "HIGH"
        elif days_supply < target_days + 10:
            risk = "MID"
        else:
            risk = "LOW"
        city_base.append(
            {
                "warehouse_code": str(snap["warehouse_code"]),
                "city_sales_30d": sales30,
                "city_sales_14d": _safe_float(snap.get("sales_14d")),
                "city_sales_7d": _safe_float(snap.get("sales_7d")),
                "city_share": share,
                "predicted_city_7d": predicted_7d,
                "daily_city_forecast": daily,
                "target_days": target_days,
                "stock_qty": stock,
                "inbound_qty": inbound,
                "available_qty": available,
                "orderable_qty": orderable,
                "days_of_supply": days_supply,
                "risk_level": risk,
                "shortage_qty": shortage,
            }
        )

    donor_candidates: list[dict[str, Any]] = []
    if policy.allow_jd_transfer and category != inventory_service.BOX_CATEGORY and not inventory_service._is_supplier_direct_brand(brand):
        for row in city_base:
            if row["daily_city_forecast"] <= 0:
                continue
            reserve_stock = row["daily_city_forecast"] * reserve_days
            max_transfer = max(0.0, row["stock_qty"] - reserve_stock)
            target_excess = max(0.0, row["stock_qty"] - row["daily_city_forecast"] * target_days)
            can_transfer = min(max_transfer, target_excess)
            if can_transfer > 0:
                donor_candidates.append({**row, "can_transfer": can_transfer})

    supply_source = policy.preferred_source_warehouse or inventory_service.SUPPLY_HUB_WAREHOUSE
    supply_stock = inventory_service._supply_stock_for_policy(supply_stocks, policy, sku_code)
    # 供应仓（花东/南沙·聚水潭）无该 SKU 库存数据时，视为可发量未知：
    # 不按可发量封顶，直接按缺货量给出补货建议，避免测试/无聚水潭数据环境
    # 下只能靠供应仓补货的 SKU 因建议量被压成 0 而不出现在补货导出明细。
    has_supply_stock = supply_stock is not None
    supply_available = _safe_float((supply_stock or {}).get("available_qty")) or _safe_float((supply_stock or {}).get("stock_qty"))
    supply_remaining = max(0.0, supply_available)
    excel_formula = purchase_formula == "excel"
    output: list[dict[str, Any]] = []
    for row in city_base:
        suggestion = 0
        source = ""
        route_path = ""
        eta_days = 0
        status = "OBSERVE"
        reason = ""
        if excel_formula:
            # Excel 40周转算法（八大仓口径）：
            #   建议补货数 = 该仓近30日出库商品件数 × (目标周转天数 / 30) − 可订购库存(库存件数+采购未到货)
            # 表格里的 1.3 即 40/30≈1.333 的运营简化，此处用周转策略的 target_days/30 与之联动。
            # 与表格一致：负值保留展示（表示已超储）；每仓独立计算，不做调拨/供应仓封顶。
            sales30 = row["city_sales_30d"]
            sales14 = row["city_sales_14d"]
            sales7 = row["city_sales_7d"]
            available = row["available_qty"]
            if inventory_service._is_nansha_supply_brand(brand):
                candidates = [sales30 - available, sales7 / 7.0 * 25.0 - available]
                if sales14 > 0:
                    candidates.append(sales14 / 14.0 * 25.0 - available)
                raw_suggestion = min(candidates)
                suggestion = max(0, math.ceil(raw_suggestion))
                formula_note = (
                    f"近30日{sales30:.0f}件、近14日{sales14:.0f}件、近7日{sales7:.0f}件"
                    if sales14 > 0
                    else f"近30日{sales30:.0f}件、近7日{sales7:.0f}件（近14日数据待下次RDC导入补齐）"
                )
                reason = (
                    f"按iGear货盘表保守补货口径：{formula_note}，可订(库存+采购未到){available:.0f}件；"
                    f"取30天、14天、7天预测缺口中的最小值{raw_suggestion:.1f}件"
                    f" → 建议补货{suggestion:.0f}件。"
                )
            else:
                turnover_factor = target_days / 30.0
                orderable = row["orderable_qty"]
                raw_suggestion = sales30 * turnover_factor - orderable
                suggestion = math.ceil(raw_suggestion)
                reason = (
                    f"按Excel 40周转口径：该仓近30日出库{sales30:.0f}件 × 目标周转{target_days:.0f}天/30"
                    f" ≈ {sales30 * turnover_factor:.1f}件，减可订购{orderable:.0f}件"
                    f" → 建议补货{suggestion:.0f}件（负数表示已超储）。"
                )
            row["risk_level"] = "HIGH" if suggestion > 0 else "LOW"
            row["shortage_qty"] = max(0.0, suggestion)
            if suggestion > 0:
                source = supply_source
                eta_days = int(inventory_service.estimate_transfer_route(source, row["warehouse_code"])["eta_days"])
                route_path = f"{source} → {row['warehouse_code']}"
        else:
            suggestion = math.ceil(row["shortage_qty"]) if row["risk_level"] == "HIGH" and row["shortage_qty"] > 0 else 0
            if suggestion > 0:
                if inventory_service._is_supplier_direct_brand(brand):
                    source = inventory_service.FOSHAN_SUPPLIER_WAREHOUSE
                    eta_days = int(inventory_service.estimate_transfer_route(source, row["warehouse_code"])["eta_days"])
                    route_path = f"{source} → {row['warehouse_code']}"
                else:
                    donor = _select_donor(donor_candidates, row["warehouse_code"], suggestion)
                    if donor:
                        source = donor["warehouse_code"]
                        eta_days = int(inventory_service.estimate_transfer_route(source, row["warehouse_code"])["eta_days"])
                        route_path = f"{source} → {row['warehouse_code']}"
                    else:
                        if has_supply_stock:
                            suggestion = min(suggestion, max(0, math.floor(supply_remaining)))
                        if suggestion > 0:
                            source = supply_source
                            eta_days = int(inventory_service.estimate_transfer_route(source, row["warehouse_code"])["eta_days"])
                            route_path = f"{source} → {row['warehouse_code']}"
                            if has_supply_stock:
                                supply_remaining -= suggestion
                if suggestion > 0:
                    reason = (
                        f"经营趋势预测未来7天该仓需求约{row['predicted_city_7d']:.1f}件，"
                        f"当前库存可售约{row['days_of_supply']:.1f}天，低于{target_days:.0f}天目标。"
                    )
        output.append(
            {
                "forecast_date": forecast_date,
                "sku_code": sku_code,
                "warehouse_code": row["warehouse_code"],
                "city_sales_30d": round(row["city_sales_30d"], 4),
                "city_sales_14d": round(row["city_sales_14d"], 4),
                "city_sales_7d": round(row["city_sales_7d"], 4),
                "city_share": round(row["city_share"], 8),
                "predicted_city_7d": round(row["predicted_city_7d"], 4),
                "daily_city_forecast": round(row["daily_city_forecast"], 4),
                "target_days": round(row["target_days"], 2),
                "stock_qty": round(row["stock_qty"], 4),
                "inbound_qty": round(row["inbound_qty"], 4),
                "available_qty": round(row["available_qty"], 4),
                "orderable_qty": round(row["orderable_qty"], 4),
                "days_of_supply": round(row["days_of_supply"], 4),
                "risk_level": row["risk_level"],
                "shortage_qty": round(row["shortage_qty"], 4),
                "suggested_qty": suggestion,
                "suggested_source": source,
                "eta_days": eta_days,
                "route_path": route_path,
                "status": status,
                "reason": reason,
            }
        )
    return output, False


def _select_donor(donors: list[dict[str, Any]], to_warehouse: str, need_qty: float) -> dict[str, Any] | None:
    candidates = []
    for donor in donors:
        if donor["warehouse_code"] == to_warehouse or donor["can_transfer"] < need_qty:
            continue
        route = inventory_service.estimate_transfer_route(donor["warehouse_code"], to_warehouse)
        candidates.append((int(route["eta_days"]), -float(donor["can_transfer"]), donor))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _load_business_rows(db_engine: Engine, forecast_date: date, sku_filter: list[str]) -> list[dict[str, Any]]:
    start_date = forecast_date - timedelta(days=BACKTEST_LOOKBACK_DAYS)
    where = ["biz_date BETWEEN :start_date AND :forecast_date"]
    params: dict[str, Any] = {"start_date": start_date, "forecast_date": forecast_date}
    if sku_filter:
        where.append(f"sku_code IN ({_placeholders('sku', sku_filter)})")
        params.update({f"sku_{idx}": sku for idx, sku in enumerate(sku_filter)})
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM inv_business_daily
                WHERE {' AND '.join(where)}
                ORDER BY sku_code, biz_date
                """
            ),
            params,
        ).mappings().all()
    return [_normalize_business_daily_row(row) for row in rows]


def _load_inventory_sku_meta(db_engine: Engine, sku_codes: list[str]) -> dict[str, dict[str, Any]]:
    if not sku_codes:
        return {}
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT sku_code, product_name, brand, category, shop_name, barcode
                FROM inv_sku
                WHERE sku_code IN ({_placeholders('sku', sku_codes)})
                """
            ),
            {f"sku_{idx}": sku for idx, sku in enumerate(sku_codes)},
        ).mappings().all()
    return {str(row["sku_code"]): _mapping_to_dict(row) for row in rows}


def _load_latest_snapshots(db_engine: Engine, snapshot_date: date, sku_codes: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not sku_codes:
        return {}
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT s.snapshot_date, s.sku_code, s.warehouse_code,
                       s.stock_qty, s.inbound_qty, s.sales_1d, s.sales_7d, s.sales_30d,
                       sku.product_name, sku.brand, sku.category
                FROM inv_stock_snapshot s
                LEFT JOIN inv_sku sku ON sku.sku_code=s.sku_code
                WHERE s.snapshot_date=:snapshot_date
                  AND s.is_decision_active=1
                  AND s.sku_code IN ({_placeholders('sku', sku_codes)})
                """
            ),
            {"snapshot_date": snapshot_date, **{f"sku_{idx}": sku for idx, sku in enumerate(sku_codes)}},
        ).mappings().all()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["sku_code"])].append(_mapping_to_dict(row))
    return grouped


def _delete_existing_forecasts(conn: Any, forecast_date: date, sku_codes: list[str] | None = None) -> None:
    params: dict[str, Any] = {"forecast_date": forecast_date}
    where = ["forecast_date=:forecast_date"]
    if sku_codes:
        where.append(f"sku_code IN ({_placeholders('sku', sku_codes)})")
        params.update({f"sku_{idx}": sku for idx, sku in enumerate(sku_codes)})
    conn.execute(text(f"DELETE FROM inv_business_forecast_city WHERE {' AND '.join(where)}"), params)
    conn.execute(text(f"DELETE FROM inv_business_forecast WHERE {' AND '.join(where)}"), params)


def _forecast_insert_sql() -> Any:
    return text(
        """
        INSERT INTO inv_business_forecast (
            forecast_date, target_start_date, target_end_date, sku_code, product_name,
            brand, category, category_l1, category_l2, category_l3, sku_link_status,
            days_covered, total_30d_units, recent_3d_avg, recent_7d_avg,
            recent_14d_avg, recent_30d_avg, base_pred_7d, adjusted_pred_7d,
            unit_momentum, visitor_momentum, cart_momentum, conversion_momentum,
            adjustment_factor, trend_level, confidence_level, affected_warehouse_count,
            suggestion_count, pending_city_split, reason_json, created_at, updated_at
        )
        VALUES (
            :forecast_date, :target_start_date, :target_end_date, :sku_code, :product_name,
            :brand, :category, :category_l1, :category_l2, :category_l3, :sku_link_status,
            :days_covered, :total_30d_units, :recent_3d_avg, :recent_7d_avg,
            :recent_14d_avg, :recent_30d_avg, :base_pred_7d, :adjusted_pred_7d,
            :unit_momentum, :visitor_momentum, :cart_momentum, :conversion_momentum,
            :adjustment_factor, :trend_level, :confidence_level, :affected_warehouse_count,
            :suggestion_count, :pending_city_split, :reason_json, NOW(), NOW()
        )
        """
    )


def _city_insert_sql() -> Any:
    return text(
        """
        INSERT INTO inv_business_forecast_city (
            forecast_id, forecast_date, sku_code, warehouse_code, city_sales_30d,
            city_share, predicted_city_7d, daily_city_forecast, target_days,
            stock_qty, inbound_qty, available_qty, days_of_supply, risk_level,
            shortage_qty, suggested_qty, suggested_source, eta_days, route_path,
            status, reason, created_at
        )
        VALUES (
            :forecast_id, :forecast_date, :sku_code, :warehouse_code, :city_sales_30d,
            :city_share, :predicted_city_7d, :daily_city_forecast, :target_days,
            :stock_qty, :inbound_qty, :available_qty, :days_of_supply, :risk_level,
            :shortage_qty, :suggested_qty, :suggested_source, :eta_days, :route_path,
            :status, :reason, NOW()
        )
        """
    )


def _refresh_backtest(db_engine: Engine, current_date: date) -> dict[str, Any]:
    start_date = current_date - timedelta(days=60)
    with db_engine.begin() as conn:
        # 单条聚合查询，替代逐候选行的 N+1 查询：LEFT JOIN 实际销量并按 forecast 主键聚合。
        candidates = conn.execute(
            text(
                """
                SELECT f.id, f.sku_code, f.target_start_date, f.target_end_date,
                       f.adjusted_pred_7d,
                       COALESCE(SUM(d.sold_units), 0) AS actual_sum
                FROM inv_business_forecast f
                LEFT JOIN inv_business_daily d
                       ON d.sku_code = f.sku_code
                      AND d.biz_date BETWEEN f.target_start_date AND f.target_end_date
                WHERE f.target_end_date <= :current_date
                  AND f.forecast_date >= :start_date
                GROUP BY f.id, f.sku_code, f.target_start_date, f.target_end_date, f.adjusted_pred_7d
                """
            ),
            {"current_date": current_date, "start_date": start_date},
        ).mappings().all()
        updates: list[dict[str, Any]] = []
        for row in candidates:
            actual = _safe_float(row["actual_sum"])
            pred = _safe_float(row["adjusted_pred_7d"])
            error = actual - pred
            ape = abs(error) / max(actual, 1.0)
            hit = 1 if abs(error) <= max(actual * 0.2, 1.0) else 0
            updates.append(
                {
                    "id": row["id"],
                    "actual_7d": round(actual, 4),
                    "forecast_error": round(error, 4),
                    "abs_percentage_error": round(ape, 6),
                    "hit_flag": hit,
                }
            )
        if updates:
            _execute_chunks(
                conn,
                text(
                    """
                    UPDATE inv_business_forecast
                    SET actual_7d=:actual_7d,
                        forecast_error=:forecast_error,
                        abs_percentage_error=:abs_percentage_error,
                        hit_flag=:hit_flag,
                        updated_at=NOW()
                    WHERE id=:id
                    """
                ),
                updates,
            )
    hit_count = sum(int(row["hit_flag"]) for row in updates)
    return {"evaluated": len(updates), "hit_count": hit_count}


def _resolve_business_date(db_engine: Engine, value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if value:
        parsed = _parse_date(value)
        if not parsed:
            raise ValueError("forecast_date必须是YYYY-MM-DD格式")
        return parsed
    latest = _latest_business_date(db_engine)
    if not latest:
        raise ValueError("暂无经营明细数据，请先导入经营报表")
    return latest


def _resolve_business_forecast_date(db_engine: Engine, value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        parsed = _parse_date(value)
        if not parsed:
            raise ValueError("forecast_date必须是YYYY-MM-DD格式")
        return parsed
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT MAX(forecast_date) FROM inv_business_forecast")).scalar()


def _latest_business_date(db_engine: Engine) -> date | None:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT MAX(biz_date) FROM inv_business_daily")).scalar()


def _normalize_forecast_row(row: Any) -> dict[str, Any]:
    data = _mapping_to_dict(row)
    for key in ("forecast_date", "target_start_date", "target_end_date", "created_at", "updated_at"):
        if data.get(key) is not None and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()
    if isinstance(data.get("reason_json"), str):
        try:
            data["reason_json"] = json.loads(data["reason_json"])
        except json.JSONDecodeError:
            pass
    return data


def _normalize_city_row(row: Any) -> dict[str, Any]:
    data = _mapping_to_dict(row)
    for key in ("forecast_date", "created_at"):
        if data.get(key) is not None and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()
    return data


def _normalize_business_daily_row(row: Any) -> dict[str, Any]:
    data = _mapping_to_dict(row)
    biz_date = _parse_date(data.get("biz_date"))
    if biz_date is None:
        raise ValueError("inv_business_daily.biz_date contains an invalid date")
    data["biz_date"] = biz_date
    return data


def _mapping_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row or {})
    return {key: _jsonable(value) for key, value in data.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "__float__"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip().replace("T", " ").replace("Z", "")
    if not text:
        return None
    # 快路径：常见 ISO 格式用 C 级 strptime，避免逐行调用 pandas.to_datetime
    # （后者是向量化接口，单值调用慢一个数量级）。
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if not value or value in {"-", "--"}:
            return 0.0
        if value.endswith("%"):
            value = value[:-1]
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_rate(value: Any) -> float:
    if isinstance(value, str) and value.strip().endswith("%"):
        return _to_float(value) / 100
    number = _to_float(value)
    if number > 1 and number <= 100:
        return number / 100
    return number


def _to_seconds(value: Any) -> float:
    if isinstance(value, str):
        text_value = value.strip()
        parts = text_value.split(":")
        if len(parts) == 3 and all(part.replace(".", "", 1).isdigit() for part in parts):
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return _to_float(value)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _normalize_business_brand(brand: Any, shop_name: Any = "") -> str:
    return _clean_text(brand)


def _zero_metric_row(day: date, sku_code: str) -> dict[str, Any]:
    row = {"biz_date": day, "sku_code": sku_code}
    row.update({field: 0.0 for field in NUMERIC_FIELDS})
    return row


def _latest_nonempty_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return sorted(rows, key=lambda row: row["biz_date"])[-1]


def _avg_tail(values: list[float], days: int) -> float:
    if not values:
        return 0.0
    tail = values[-days:]
    return sum(tail) / max(len(tail), 1)


def _metric_series(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [_safe_float(row.get(field)) for row in rows]


def _metric_momentum(rows: list[dict[str, Any]], field: str) -> tuple[float, float, float]:
    values = _metric_series(rows, field)
    recent = _avg_tail(values, 3)
    baseline = _avg_tail(values, 14)
    return _momentum(recent, baseline), recent, baseline


def _signal_group_score(
    rows: list[dict[str, Any]],
    metrics: tuple[tuple[str, float], ...],
) -> tuple[float, dict[str, dict[str, float]], float]:
    weighted_score = 0.0
    active_weight = 0.0
    details: dict[str, dict[str, float]] = {}
    total_weight = sum(weight for _, weight in metrics) or 1.0

    for field, weight in metrics:
        momentum, recent, baseline = _metric_momentum(rows, field)
        active = recent > 0 or baseline > 0
        clipped = _clip(momentum, SIGNAL_CLIP_LOW, SIGNAL_CLIP_HIGH) if active else 0.0
        if active:
            weighted_score += clipped * weight
            active_weight += weight
        details[field] = {
            "recent_3d_avg": round(recent, 6),
            "baseline_14d_avg": round(baseline, 6),
            "momentum": round(momentum, 6),
            "score": round(clipped, 6),
            "weight": round(weight, 4),
            "active": 1.0 if active else 0.0,
        }

    if active_weight <= 0:
        return 0.0, details, 0.0
    return weighted_score / active_weight, details, active_weight / total_weight


def _signal_group_index_windows(
    rows: list[dict[str, Any]],
    metrics: tuple[tuple[str, float], ...],
    score: float,
) -> list[dict[str, Any]]:
    """Return a real-data composite index series for mixed-unit signal groups.

    Each metric is compared with its own 30-day average, then weighted into a
    group index. This keeps visitors, rates, money and seconds from being added
    together directly while still showing concrete window numbers.
    """

    windows = [("近30", 30), ("近14", 14), ("近7", 7), ("近3", 3)]
    series_by_field = {field: _metric_series(rows, field) for field, _ in metrics}
    avg30_by_field = {field: _avg_tail(values, 30) for field, values in series_by_field.items()}
    points: list[dict[str, Any]] = []

    for name, days in windows:
        weighted_index = 0.0
        active_weight = 0.0
        for field, weight in metrics:
            baseline = avg30_by_field[field]
            if baseline <= 0:
                continue
            window_avg = _avg_tail(series_by_field[field], days)
            weighted_index += _clip(window_avg / baseline * 100, 0, 300) * weight
            active_weight += weight
        value = weighted_index / active_weight if active_weight > 0 else 0.0
        points.append({"name": name, "value": round(value, 2), "label": f"{value:.1f}"})

    recent_value = points[-1]["value"] if points else 0.0
    projected_value = _clip(recent_value * (1 + _clip(score, SIGNAL_CLIP_LOW, SIGNAL_CLIP_HIGH) * 0.25), 0, 300)
    points.append({"name": "未来", "value": round(projected_value, 2), "label": f"{projected_value:.1f}"})
    return points


def _momentum(recent: float, baseline: float) -> float:
    if baseline <= 0 and recent <= 0:
        return 0.0
    if baseline <= 0:
        return 0.8
    return recent / baseline - 1


def _confidence(days_covered: int, total_30d_units: float) -> str:
    if days_covered >= 21 and total_30d_units >= 14:
        return CONFIDENCE_HIGH
    if days_covered >= 7 or total_30d_units >= 3:
        return CONFIDENCE_MID
    return CONFIDENCE_LOW


def _days_of_supply(stock_qty: float, daily_sales: float) -> float:
    if daily_sales <= 0:
        return 9999.0 if stock_qty > 0 else 0.0
    return stock_qty / daily_sales


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _execute_chunks(conn: Any, sql: Any, rows: list[dict[str, Any]], chunk_size: int = 1000) -> None:
    for idx in range(0, len(rows), chunk_size):
        conn.execute(sql, rows[idx : idx + chunk_size])


def _placeholders(prefix: str, values: list[Any]) -> str:
    return ", ".join(f":{prefix}_{idx}" for idx, _ in enumerate(values))
