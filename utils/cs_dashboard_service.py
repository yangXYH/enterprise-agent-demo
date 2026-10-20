"""客服数据看板 MySQL 共享存储服务。

面向「客服中心 / 客服数据看板」页（前端 CustomerService.vue）：
- 此前上传的 Excel 报表解析后只存在浏览器 localStorage，导致一个人上传后
  其他人看不到、数据无法共享给全员。
- 本服务把解析后的行数据整份持久化到 MySQL（单行 KV 结构），所有登录用户
  读取同一份数据：GET 拉取共享快照，PUT 整体覆盖（前端在上传/恢复快照时提交）。

表结构与读写方式对齐 ecom_dashboard_service / ai_daily_board_service 的成熟模式。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from utils import import_service


_STATE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS cs_dashboard_state (
    id TINYINT NOT NULL DEFAULT 1 COMMENT '固定主键（单行存储）',
    rows_json LONGTEXT NOT NULL COMMENT '客服看板解析后的全部行数据 JSON 数组',
    source_name VARCHAR(255) NOT NULL DEFAULT '' COMMENT '数据来源文件名',
    loaded TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已载入数据，1载入，0未载入',
    updated_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最后更新人（登录用户姓名）',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服数据看板共享状态'
"""


def get_engine(engine: Engine | None = None) -> Engine:
    """返回调用方传入的引擎，未传入时按环境变量创建 MySQL 引擎。"""
    return engine or import_service.get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    """幂等创建客服数据看板共享状态表。"""
    db_engine = get_engine(engine)
    with db_engine.begin() as conn:
        conn.execute(text(_STATE_TABLE_DDL))


def get_state(engine: Engine | None = None) -> dict[str, Any]:
    """读取客服数据看板共享数据（全公司同一份）。

    返回结构形如：
    {
        "rows": [ {store, agentName, account, agentRole, reportWeekKey,
                   reportWeekLabel, visitors, questions, ...}, ... ],
        "sourceName": "全部整合-20260727.xlsx",
        "loaded": True,
        "updatedBy": "张三",
        "updatedAt": "2026-09-07 10:00:00",
    }
    无数据时 rows 为空数组、loaded 为 False。
    """
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rows_json, source_name, loaded, updated_by, updated_at "
                "FROM cs_dashboard_state WHERE id = 1"
            )
        ).mappings().fetchone()

    if not row:
        return {
            "rows": [],
            "sourceName": "",
            "loaded": False,
            "updatedBy": "",
            "updatedAt": "",
        }

    try:
        rows = json.loads(row["rows_json"] or "[]")
        if not isinstance(rows, list):
            rows = []
    except (ValueError, TypeError):
        rows = []

    updated_at = row["updated_at"]
    return {
        "rows": rows,
        "sourceName": str(row["source_name"] or ""),
        "loaded": bool(row["loaded"]),
        "updatedBy": str(row["updated_by"] or ""),
        "updatedAt": str(updated_at) if updated_at else "",
    }


def save_state(
    payload: dict[str, Any],
    updated_by: str = "",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """整体覆盖客服数据看板共享数据（单行 upsert）。

    payload 结构（与前端 persistRows 保持一致）：
    { "rows": [...], "sourceName": "...", "loaded": true }
    """
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    raw_rows = payload.get("rows")
    rows = raw_rows if isinstance(raw_rows, list) else []
    source_name = str(payload.get("sourceName") or "")[:255]
    loaded = 1 if payload.get("loaded") or rows else 0
    operator = str(updated_by or "")[:64]

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cs_dashboard_state (id, rows_json, source_name, loaded, updated_by, updated_at)
                VALUES (1, :rows_json, :source_name, :loaded, :updated_by, :updated_at)
                ON DUPLICATE KEY UPDATE
                    rows_json = VALUES(rows_json),
                    source_name = VALUES(source_name),
                    loaded = VALUES(loaded),
                    updated_by = VALUES(updated_by),
                    updated_at = VALUES(updated_at)
                """
            ),
            {
                "rows_json": json.dumps(rows, ensure_ascii=False),
                "source_name": source_name,
                "loaded": loaded,
                "updated_by": operator,
                "updated_at": datetime.now(),
            },
        )

    return get_state(engine=db_engine)
