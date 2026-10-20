"""电商中台看板 MySQL 读写服务。

面向示例企业 AI 工作台的「电商中台看板」模板页：
- ecom_menu       左侧树形导航（一级 + 二级）
- ecom_kpi        各页面 KPI 统计卡片
- ecom_table_tab  各页面数据表的 Tab 定义
- ecom_table_col  各表格的列定义（field / label / col_type / width）
- ecom_table_row  通用数据行（业务字段以 JSON 存 meta_json）

前端通过 /api/dashboard/ecom/* 读取；数据由 seed 脚本或管理接口写入。
表结构与读写方式对齐 ai_daily_board_service 的成熟模式。
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import Engine, text

from utils import import_service


_MENU_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ecom_menu (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '菜单主键ID',
    parent_id BIGINT NOT NULL DEFAULT 0 COMMENT '父级ID，0为顶级',
    label VARCHAR(64) NOT NULL COMMENT '菜单名称',
    icon VARCHAR(64) NOT NULL DEFAULT '' COMMENT '图标名',
    route VARCHAR(64) NOT NULL DEFAULT '' COMMENT '路由标识',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ecom_menu_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电商中台看板菜单表'
"""

_KPI_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ecom_kpi (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'KPI主键ID',
    page_key VARCHAR(32) NOT NULL COMMENT '所属页面标识',
    label VARCHAR(64) NOT NULL COMMENT '指标名称',
    value VARCHAR(32) NOT NULL DEFAULT '' COMMENT '指标数值',
    unit VARCHAR(16) NOT NULL DEFAULT '' COMMENT '单位',
    hint VARCHAR(128) NOT NULL DEFAULT '' COMMENT '辅助说明',
    trend VARCHAR(8) NOT NULL DEFAULT 'flat' COMMENT '趋势：up/down/flat',
    color VARCHAR(16) NOT NULL DEFAULT 'blue' COMMENT '主题色',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ecom_kpi_page (page_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电商中台看板KPI表'
"""

_TAB_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ecom_table_tab (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Tab主键ID',
    page_key VARCHAR(32) NOT NULL COMMENT '所属页面标识',
    tab_key VARCHAR(32) NOT NULL COMMENT 'Tab标识',
    label VARCHAR(64) NOT NULL COMMENT 'Tab名称',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ecom_tab_page (page_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电商中台看板数据表Tab表'
"""

_COL_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ecom_table_col (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '列定义主键ID',
    page_key VARCHAR(32) NOT NULL COMMENT '所属页面标识',
    tab_key VARCHAR(32) NOT NULL DEFAULT 'main' COMMENT '所属Tab标识',
    field VARCHAR(64) NOT NULL COMMENT '字段名',
    label VARCHAR(64) NOT NULL DEFAULT '' COMMENT '列头名称',
    col_type VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '列类型：text/date/user/platform/tag/number/checkbox/image/amount',
    width INT NOT NULL DEFAULT 120 COMMENT '列宽',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ecom_col_page_tab (page_key, tab_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电商中台看板表格列定义表'
"""

_ROW_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ecom_table_row (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '数据行主键ID',
    page_key VARCHAR(32) NOT NULL COMMENT '所属页面标识',
    tab_key VARCHAR(32) NOT NULL DEFAULT 'main' COMMENT '所属Tab标识',
    meta_json TEXT NOT NULL COMMENT '业务字段JSON',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ecom_row_page_tab (page_key, tab_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电商中台看板数据行表'
"""


def get_engine(engine: Engine | None = None) -> Engine:
    return engine or import_service.get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    """幂等创建电商中台看板五张表。"""
    db_engine = get_engine(engine)
    with db_engine.begin() as conn:
        for ddl in (
            _MENU_TABLE_DDL,
            _KPI_TABLE_DDL,
            _TAB_TABLE_DDL,
            _COL_TABLE_DDL,
            _ROW_TABLE_DDL,
        ):
            conn.execute(text(ddl))


# ──────────────────────────────────────────────────────────────────────────────
# 读取
# ──────────────────────────────────────────────────────────────────────────────
def get_board_state(engine: Engine | None = None) -> dict[str, Any]:
    """读取电商中台看板全量数据：菜单树 / KPI / 各页面 Tab·列·数据行。"""
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    with db_engine.connect() as conn:
        menu_rows = conn.execute(
            text(
                """
                SELECT id, parent_id, label, icon, route
                FROM ecom_menu ORDER BY sort_order, id
                """
            )
        ).mappings().all()

        kpi_rows = conn.execute(
            text(
                """
                SELECT page_key, label, value, unit, hint, trend, color
                FROM ecom_kpi ORDER BY sort_order, id
                """
            )
        ).mappings().all()

        tab_rows = conn.execute(
            text(
                """
                SELECT page_key, tab_key, label
                FROM ecom_table_tab ORDER BY sort_order, id
                """
            )
        ).mappings().all()

        col_rows = conn.execute(
            text(
                """
                SELECT page_key, tab_key, field, label, col_type, width
                FROM ecom_table_col ORDER BY sort_order, id
                """
            )
        ).mappings().all()

        row_rows = conn.execute(
            text(
                """
                SELECT page_key, tab_key, meta_json
                FROM ecom_table_row ORDER BY sort_order, id
                """
            )
        ).mappings().all()

    # 菜单树
    menu_by_id: dict[int, dict[str, Any]] = {}
    for r in menu_rows:
        menu_by_id[int(r["id"])] = {
            "id": int(r["id"]),
            "parentId": int(r["parent_id"]),
            "label": str(r["label"]),
            "icon": str(r["icon"] or ""),
            "route": str(r["route"] or ""),
            "children": [],
        }
    menus: list[dict[str, Any]] = []
    for node in menu_by_id.values():
        if node["parentId"] == 0:
            menus.append(node)
        else:
            parent = menu_by_id.get(node["parentId"])
            if parent is not None:
                parent["children"].append(node)

    # KPI 按页面分组
    kpis: dict[str, list[dict[str, Any]]] = {}
    for r in kpi_rows:
        kpis.setdefault(str(r["page_key"]), []).append(
            {
                "label": str(r["label"]),
                "value": str(r["value"] or ""),
                "unit": str(r["unit"] or ""),
                "hint": str(r["hint"] or ""),
                "trend": str(r["trend"] or "flat"),
                "color": str(r["color"] or "blue"),
            }
        )

    # Tab 按页面分组
    tabs: dict[str, list[dict[str, str]]] = {}
    for r in tab_rows:
        tabs.setdefault(str(r["page_key"]), []).append(
            {"key": str(r["tab_key"]), "label": str(r["label"])}
        )

    # 列按 (page, tab) 分组，key 用字符串 "page|tab" 便于 JSON 序列化
    cols: dict[str, list[dict[str, Any]]] = {}
    for r in col_rows:
        key = f"{r['page_key']}|{r['tab_key']}"
        cols.setdefault(key, []).append(
            {
                "field": str(r["field"]),
                "label": str(r["label"]),
                "type": str(r["col_type"] or "text"),
                "width": int(r["width"] or 120),
            }
        )

    # 数据行按 (page, tab) 分组，同上用字符串 key
    rows: dict[str, list[dict[str, Any]]] = {}
    for r in row_rows:
        try:
            meta = json.loads(r["meta_json"] or "{}")
        except Exception:
            meta = {}
        key = f"{r['page_key']}|{r['tab_key']}"
        rows.setdefault(key, []).append(meta)

    return {
        "menus": menus,
        "kpis": kpis,
        "tabs": tabs,
        "cols": cols,  # key 为 "page|tab" 拼接，供前端直接使用
        "rows": rows,  # key 同上
    }


# ──────────────────────────────────────────────────────────────────────────────
# 写入 / 重置（seed）
# ──────────────────────────────────────────────────────────────────────────────


def sync_menus_from_payload(
    payload: dict[str, Any],
    engine: Engine | None = None,
) -> int:
    """把 seed 的 menus（导航菜单树）完全对齐进 ecom_menu 表。

    与 save_board_state 的「五张表全清重写」不同，这里只重建 ecom_menu 一张表，
    KPI / TableTab / TableCol / TableRow 等业务数据表保持不动，因此不会
    冲掉将来真实入库的运营数据。

    策略（完全对齐）：以 seed 的 menus 为准，删除 ecom_menu 全部行后按序重建。
    ecom_menu.id 是内部自增主键，无任何外键引用（前端只消费 route/label/icon，
    get_board_state 依据 parent_id 重建树），因此整体重建是安全的，并且天然
    消除历史重复数据（例如手工复制表可能产生的重复菜单）。

    返回重建后的菜单节点总数。
    """
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    menus = payload.get("menus") or []

    menu_insert = text(
        """
        INSERT INTO ecom_menu (parent_id, label, icon, route, sort_order)
        VALUES (:parent_id, :label, :icon, :route, :sort_order)
        """
    )

    def walk_children(conn: Any, items: list[dict[str, Any]], parent_id: int) -> int:
        count = 0
        for i, node in enumerate(items):
            result = conn.execute(
                menu_insert,
                {
                    "parent_id": parent_id,
                    "label": str(node.get("label") or "")[:64],
                    "icon": str(node.get("icon") or "")[:64],
                    "route": str(node.get("route") or "")[:64],
                    "sort_order": i,
                },
            )
            count += 1
            new_id = int(result.lastrowid or 0)
            children = node.get("children") or []
            if children:
                count += walk_children(conn, children, new_id)
        return count

    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ecom_menu"))
        total = walk_children(conn, menus, 0)

    return total


def _reset_tables(conn: Any) -> None:
    for t in (
        "ecom_table_row",
        "ecom_table_col",
        "ecom_table_tab",
        "ecom_kpi",
        "ecom_menu",
    ):
        conn.execute(text(f"DELETE FROM {t}"))


def save_board_state(
    payload: dict[str, Any],
    engine: Engine | None = None,
) -> dict[str, Any]:
    """用前端提交的完整看板数据整体替换库内容（seed / 管理）。"""
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    menus = payload.get("menus") or []
    kpis = payload.get("kpis") or {}
    tabs = payload.get("tabs") or {}
    cols = payload.get("cols") or {}
    rows = payload.get("rows") or {}

    menu_insert = text(
        """
        INSERT INTO ecom_menu (parent_id, label, icon, route, sort_order)
        VALUES (:parent_id, :label, :icon, :route, :sort_order)
        """
    )
    kpi_insert = text(
        """
        INSERT INTO ecom_kpi (page_key, label, value, unit, hint, trend, color, sort_order)
        VALUES (:page_key, :label, :value, :unit, :hint, :trend, :color, :sort_order)
        """
    )
    tab_insert = text(
        """
        INSERT INTO ecom_table_tab (page_key, tab_key, label, sort_order)
        VALUES (:page_key, :tab_key, :label, :sort_order)
        """
    )
    col_insert = text(
        """
        INSERT INTO ecom_table_col (page_key, tab_key, field, label, col_type, width, sort_order)
        VALUES (:page_key, :tab_key, :field, :label, :col_type, :width, :sort_order)
        """
    )
    row_insert = text(
        """
        INSERT INTO ecom_table_row (page_key, tab_key, meta_json, sort_order)
        VALUES (:page_key, :tab_key, :meta_json, :sort_order)
        """
    )

    with db_engine.begin() as conn:
        _reset_tables(conn)

        # 菜单：递归插入，用数据库返回的真实主键作子级 parent_id
        def walk(items: list[dict[str, Any]], parent: int) -> None:
            for i, node in enumerate(items):
                result = conn.execute(
                    menu_insert,
                    {
                        "parent_id": parent,
                        "label": str(node.get("label") or "")[:64],
                        "icon": str(node.get("icon") or "")[:64],
                        "route": str(node.get("route") or "")[:64],
                        "sort_order": i,
                    },
                )
                new_id = int(result.lastrowid or 0)
                if "children" in node:
                    walk(node["children"] or [], new_id)

        walk(menus, 0)

        for page_key, items in kpis.items():
            for i, k in enumerate(items):
                conn.execute(
                    kpi_insert,
                    {
                        "page_key": str(page_key)[:32],
                        "label": str(k.get("label") or "")[:64],
                        "value": str(k.get("value") or "")[:32],
                        "unit": str(k.get("unit") or "")[:16],
                        "hint": str(k.get("hint") or "")[:128],
                        "trend": str(k.get("trend") or "flat")[:8],
                        "color": str(k.get("color") or "blue")[:16],
                        "sort_order": i,
                    },
                )

        for page_key, items in tabs.items():
            for i, t in enumerate(items):
                conn.execute(
                    tab_insert,
                    {
                        "page_key": str(page_key)[:32],
                        "tab_key": str(t.get("key") or "main")[:32],
                        "label": str(t.get("label") or "")[:64],
                        "sort_order": i,
                    },
                )

        for key, items in cols.items():
            page_key, tab_key = _split_key(key)
            for i, c in enumerate(items):
                conn.execute(
                    col_insert,
                    {
                        "page_key": page_key,
                        "tab_key": tab_key,
                        "field": str(c.get("field") or "")[:64],
                        "label": str(c.get("label") or "")[:64],
                        "col_type": str(c.get("type") or "text")[:32],
                        "width": int(c.get("width") or 120),
                        "sort_order": i,
                    },
                )

        for key, items in rows.items():
            page_key, tab_key = _split_key(key)
            for i, row in enumerate(items):
                conn.execute(
                    row_insert,
                    {
                        "page_key": page_key,
                        "tab_key": tab_key,
                        "meta_json": json.dumps(row, ensure_ascii=False),
                        "sort_order": i,
                    },
                )

    return get_board_state(engine=db_engine)


def _split_key(key: str) -> tuple[str, str]:
    """cols/rows 的 key 形如 'home|orders'，拆成 (page, tab)。"""
    if "|" in key:
        parts = key.split("|", 1)
        return parts[0][:32], parts[1][:32]
    return key[:32], "main"
