# -*- coding: utf-8 -*-
"""只读经营数据 MCP 服务器（Read-Only MCP Server）

用途
----
把服务器的 enterprise_agent_db 数据库以「只读 MCP 服务器」的形式暴露给
运营电脑上的 DeepSeek Harness。运营的 DSH 通过 mcp__enterprise__* 工具
直接查询经营数据做分析，全程只读：

- 数据库层面：连接 MySQL 只读账号（GRANT SELECT），物理上无法写库；
- 应用层面：只提供 SELECT 查询工具，表名/列名/操作符全部白名单校验，
  参数化拼装 SQL，强制 LIMIT，禁止多语句与危险函数；
- 传输层面：streamable-http + Bearer Token 认证，没有 Token 无法访问。

部署
----
1) pip install mcp pymysql
2) 在 MySQL 创建只读账号（见下方 SQL 注释或部署文档）
3) 设置环境变量（示例）：
     MCP_RO_DB_HOST=127.0.0.1
     MCP_RO_DB_PORT=3306
     MCP_RO_DB_USER=enterprise_agent_ro
     MCP_RO_DB_PASSWORD=<只读账号密码>
     MCP_RO_DB_NAME=enterprise_agent_db
     MCP_RO_TOKEN=<发给运营的访问令牌，自己生成一段随机字符串>
     MCP_RO_ENABLE_SQL=0        # 1=额外开放受控只读 SQL 工具（默认关闭）
     MCP_RO_PORT=8640
4) 启动：python readonly_mcp_server.py
5) 验证：curl http://127.0.0.1:8640/mcp -H "Authorization: Bearer <TOKEN>"
   返回 405/400 而不是 401 即为连通。

只读账号创建 SQL（用管理员执行一次）：
    CREATE USER 'enterprise_agent_ro'@'%' IDENTIFIED BY '<强密码>';
    GRANT SELECT ON enterprise_agent_db.* TO 'enterprise_agent_ro'@'%';
    FLUSH PRIVILEGES;
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import pymysql

LOGGER = logging.getLogger("mcp-readonly")
LOGGER.setLevel(logging.INFO)
_HANDLER = logging.StreamHandler()
_HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
LOGGER.addHandler(_HANDLER)

# ---------------------------------------------------------------------------
# 配置（全部来自环境变量，避免把密码写进代码/仓库）
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("MCP_RO_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MCP_RO_DB_PORT", "3306"))
DB_USER = os.getenv("MCP_RO_DB_USER", "enterprise_agent_ro")
DB_PASSWORD = os.getenv("MCP_RO_DB_PASSWORD", "")
DB_NAME = os.getenv("MCP_RO_DB_NAME", "enterprise_agent_db")
AUTH_TOKEN = os.getenv("MCP_RO_TOKEN", "").strip()
ENABLE_RAW_SQL = os.getenv("MCP_RO_ENABLE_SQL", "0").strip() in ("1", "true", "True")
SERVER_PORT = int(os.getenv("MCP_RO_PORT", "8640"))
MAX_ROWS = int(os.getenv("MCP_RO_MAX_ROWS", "500"))          # 单次返回最大行数
QUERY_TIMEOUT = float(os.getenv("MCP_RO_QUERY_TIMEOUT", "30"))  # 单条查询超时（秒）

if not DB_PASSWORD or not AUTH_TOKEN:
    raise SystemExit(
        "缺少必要配置：请设置 MCP_RO_DB_PASSWORD 与 MCP_RO_TOKEN 环境变量后启动。"
    )

# ---------------------------------------------------------------------------
# 表白名单：默认只开放经营数据相关表（不包含 sys_* / hr_* 等敏感表）。
# 如需增删，直接编辑下面的集合（服务器上可再通过 MCP_RO_ALLOWED_TABLES 覆盖）。
# ---------------------------------------------------------------------------
_DEFAULT_ALLOWED_TABLES = {
    # —— 经营分析（核心） ——
    "jy_records",                 # 经营分析商品日明细（金额字段单位为百万分之一元，返回时已换算为元）
    "jy_batches",                 # 经营分析导入批次
    "jy_operating_brands",        # 经营分析商品名称→品牌映射
    "jy_operating_settings",      # 经营分析内部配置（只读）
    # —— 经营预测 ——
    "inv_business_daily",
    "inv_business_forecast",
    "inv_business_forecast_city",
    "inv_business_import_batch",
    # —— 销售 / 库存 / 采购看板 ——
    "sales_dashboard_item",
    "sales_dashboard_import_batch",
    "jst_product_stock",
    "inv_sku",
    "inv_stock_snapshot",
    "inv_monitor_snapshot",
    "inv_sku_warning_forecast",
    "inventory_product_dashboard_item",
    "inventory_product_import_batch",
    "purchase_order_dashboard_item",
    "purchase_order_dashboard_batch",
}

_env_extra = os.getenv("MCP_RO_ALLOWED_TABLES", "").strip()
if _env_extra:
    # 逗号分隔的额外表名，追加到默认白名单
    _DEFAULT_ALLOWED_TABLES |= {t.strip() for t in _env_extra.split(",") if t.strip()}
ALLOWED_TABLES: set[str] = _DEFAULT_ALLOWED_TABLES

# 表中文说明（describe_table / list_tables 展示给 AI 用）
TABLE_DESCRIPTIONS: dict[str, str] = {
    "jy_records": "经营分析商品日明细：每天每个SKU的成交金额/件数/单量/客户数/浏览量/访客数/加购数据，是经营分析的核心表。",
    "jy_batches": "经营分析报表导入批次记录（文件名/日期范围/行数）。",
    "jy_operating_brands": "经营分析：商品名称与标准化品牌映射表。",
    "jy_operating_settings": "经营分析内部配置键值（如金额单位比例）。",
    "inv_business_daily": "经营预测：每日业务事实数据。",
    "inv_business_forecast": "经营预测：SKU 预测结果。",
    "inv_business_forecast_city": "经营预测：分城市预测数据。",
    "inv_business_import_batch": "经营预测：数据导入批次。",
    "sales_dashboard_item": "销售看板明细数据。",
    "sales_dashboard_import_batch": "销售看板导入批次。",
    "jst_product_stock": "聚水潭商品库存快照。",
    "inv_sku": "库存 SKU 基础信息。",
    "inv_stock_snapshot": "库存快照数据。",
    "inv_monitor_snapshot": "库存监控快照。",
    "inv_sku_warning_forecast": "SKU 缺货预警预测数据。",
    "inventory_product_dashboard_item": "进销商品看板明细。",
    "inventory_product_import_batch": "进销商品看板导入批次。",
    "purchase_order_dashboard_item": "采购单看板明细。",
    "purchase_order_dashboard_batch": "采购单看板导入批次。",
}

# 返回结果时自动换算的列（除以换算系数，统一为“元”），避免 AI 把“百万分之一元”当元用
SCALED_COLUMNS: dict[str, dict[str, float]] = {
    "jy_records": {"revenue": 1_000_000.0, "cart_amount": 1_000_000.0},
}

# ---------------------------------------------------------------------------
# 数据库连接与只读查询
# ---------------------------------------------------------------------------


def _connect() -> pymysql.Connection:
    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
        read_timeout=QUERY_TIMEOUT,
        write_timeout=QUERY_TIMEOUT,
    )
    return conn


def _table_columns(conn: pymysql.Connection, table: str) -> list[dict[str, Any]]:
    """读取真实表结构（列名/类型/注释），列名以数据库为准。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME AS name, COLUMN_TYPE AS ctype,
                   COLUMN_COMMENT AS comment, IS_NULLABLE AS nullable
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (DB_NAME, table),
        )
        return [dict(row) for row in cur.fetchall()]


def _quote_ident(ident: str) -> str:
    """把标识符安全地包进反引号（内部先剔除反引号字符）。"""
    return "`" + ident.replace("`", "") + "`"


_WHERE_OPS: dict[str, str] = {
    "eq": "=",
    "neq": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
}


def _build_where(conn: pymysql.Connection, table: str, where: dict[str, Any]) -> tuple[str, list[Any]]:
    """把结构化过滤条件转成参数化 WHERE（返回 SQL 片段 + 参数列表）。"""
    if not where:
        return "", []
    valid = {c["name"] for c in _table_columns(conn, table)}
    clauses: list[str] = []
    params: list[Any] = []
    for column, cond in where.items():
        if column not in valid:
            raise ValueError(f"未知列 {column}，可用列：{sorted(valid)}")
        ident = _quote_ident(column)
        if isinstance(cond, dict):
            for op, value in cond.items():
                op = str(op).lower()
                if op not in _WHERE_OPS:
                    raise ValueError(f"不支持的过滤算子 {op}，支持：{sorted(_WHERE_OPS)}")
                if op == "like":
                    clauses.append(f"{ident} LIKE %s")
                    params.append(f"%{value}%")
                else:
                    clauses.append(f"{ident} {_WHERE_OPS[op]} %s")
                    params.append(value)
        elif isinstance(cond, list):
            placeholders = ", ".join(["%s"] * len(cond))
            clauses.append(f"{ident} IN ({placeholders})")
            params.extend(cond)
        else:
            clauses.append(f"{ident} = %s")
            params.append(cond)
    return " AND ".join(clauses), params


def _run_query(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 只读 SQL 校验（仅当 MCP_RO_ENABLE_SQL=1 时开放 query_sql 工具）
# ---------------------------------------------------------------------------
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|REPLACE|"
    r"CALL|EXEC|EXECUTE|MERGE|SLEEP|BENCHMARK|LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE|"
    r"INFORMATION_SCHEMA|PERFORMANCE_SCHEMA|MYSQL\.SYS|SHOW\s+GRANTS)\b",
    re.IGNORECASE,
)
_TABLE_REF = re.compile(r"\bFROM\s+`?(\w+)`?|\bJOIN\s+`?(\w+)`?", re.IGNORECASE)


def _validate_readonly_sql(sql: str) -> str:
    """校验只读 SQL：仅单条 SELECT、表名必须白名单、强制 LIMIT。"""
    cleaned = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    cleaned = re.sub(r"--.*?$", "", cleaned, flags=re.M)
    cleaned = cleaned.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("SQL 为空")
    if ";" in cleaned:
        raise ValueError("只允许单条 SQL，禁止分号/多语句")
    upper = cleaned.upper()
    if not upper.startswith("SELECT"):
        raise ValueError("只允许 SELECT 查询")
    if _FORBIDDEN_KEYWORDS.search(upper):
        raise ValueError("SQL 包含不允许的关键字或系统表")
    if re.search(r"\bSELECT\s+\*", upper, re.IGNORECASE):
        raise ValueError("禁止 SELECT *，请显式列出需要的列")
    tables = {
        m.group(1) or m.group(2)
        for m in _TABLE_REF.finditer(cleaned)
        if (m.group(1) or m.group(2))
    }
    unknown = tables - ALLOWED_TABLES
    if unknown:
        raise ValueError(f"SQL 引用了不在白名单内的表：{sorted(unknown)}")
    if not re.search(r"\bLIMIT\s+\d+", upper):
        cleaned = f"{cleaned} LIMIT {MAX_ROWS}"
    return cleaned


# ---------------------------------------------------------------------------
# MCP 工具（兼容 mcp 1.x 的 FastMCP 与 mcp 2.x 的 MCPServer）
# ---------------------------------------------------------------------------
try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _MCPBase
except ImportError:  # mcp < 2.0
    from mcp.server.fastmcp import FastMCP as _MCPBase

MCP = _MCPBase(
    "enterprise-data-readonly",
    instructions=(
        "你是企业「经营数据只读查询」工具。所有工具只能读取服务器数据库，不能修改任何数据。"
        "金额字段（jy_records 的 revenue/cart_amount）已按“元”换算返回。"
        "请先用 list_tables / describe_table 了解表结构，再使用 query_data 查询。"
    ),
)


@MCP.tool()
def list_tables() -> dict[str, Any]:
    """列出当前可查询的所有表及中文说明。"""
    return {
        "tables": [
            {"table": t, "description": TABLE_DESCRIPTIONS.get(t, "")}
            for t in sorted(ALLOWED_TABLES)
        ],
        "note": "只读白名单；如需查询其他表请联系系统管理员。",
    }


@MCP.tool()
def describe_table(table: str) -> dict[str, Any]:
    """查看某张表的字段结构（列名、类型、注释）与金额单位说明。"""
    try:
        return _describe_table_impl(table)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("describe_table 执行异常")
        return {"error": f"查询执行失败：{exc}"}


def _describe_table_impl(table: str) -> dict[str, Any]:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"表 {table} 不在只读白名单内。可用表：{sorted(ALLOWED_TABLES)}")
    conn = _connect()
    try:
        columns = _table_columns(conn, table)
    finally:
        conn.close()
    return {
        "table": table,
        "description": TABLE_DESCRIPTIONS.get(table, ""),
        "columns": columns,
        "scaled_columns": SCALED_COLUMNS.get(table, {}),
        "hint": "字段单位说明：如 jy_records.revenue/cart_amount 原始单位为百万分之一元，返回结果中已自动换算为元。",
    }


@MCP.tool()
def query_data(
    table: str,
    columns: list[str] | None = None,
    aggregations: dict[str, str] | None = None,
    group_by: list[str] | None = None,
    where: dict[str, Any] | None = None,
    order_by: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """结构化只读查询（推荐）。

    参数：
    - table: 表名（必须先 list_tables 确认在白名单内）
    - columns: 需要返回的列名列表（与 aggregations 二选一，省略则返回常用列）
    - aggregations: 聚合计算，如 {"revenue": "sum", "quantity": "sum"}，与 group_by 搭配
    - group_by: 分组列，如 ["day"] 或 ["category"]
    - where: 过滤条件，支持精确/范围/模糊/IN。
            格式：{"列名": 值} 或 {"列名": {"gte": 下限, "lte": 上限, "like": 关键字}}
            日期范围示例：{"day": {"gte": "2026-01-01", "lte": "2026-01-31"}}
    - order_by: 排序，如 [{"column": "revenue", "desc": true}]（聚合模式下也可用
            聚合别名，如 {"column": "sum_revenue", "desc": true}）
    - limit: 返回行数上限（最大 500）
    - offset: 分页偏移
    """
    try:
        return _query_data_impl(
            table, columns, aggregations, group_by, where, order_by, limit, offset
        )
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("query_data 执行异常")
        return {"error": f"查询执行失败：{exc}"}


def _query_data_impl(
    table: str,
    columns: list[str] | None,
    aggregations: dict[str, str] | None,
    group_by: list[str] | None,
    where: dict[str, Any] | None,
    order_by: list[dict[str, Any]] | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"表 {table} 不在只读白名单内。可用表：{sorted(ALLOWED_TABLES)}")
    limit = max(1, min(int(limit), MAX_ROWS))
    offset = max(0, int(offset))
    if offset > 10000:
        raise ValueError("offset 过大，请使用 limit 或缩小查询范围")

    conn = _connect()
    try:
        valid = {c["name"] for c in _table_columns(conn, table)}
        if columns and aggregations:
            raise ValueError("columns 与 aggregations 不能同时使用，请二选一")

        if aggregations:
            agg_ops = {"sum", "avg", "count", "max", "min"}
            selects = [_quote_ident(g) for g in (group_by or [])]  # 分组列自动出现在结果中
            alias_for: dict[str, str] = {}
            for col, op in aggregations.items():
                op = str(op).lower()
                if col not in valid:
                    raise ValueError(f"未知列 {col}")
                if op not in agg_ops:
                    raise ValueError(f"不支持的聚合 {op}，支持：{sorted(agg_ops)}")
                alias = f"{op}_{col}"
                alias_for[col] = alias
                selects.append(f"{op.upper()}({_quote_ident(col)}) AS {_quote_ident(alias)}")
            if not group_by:
                raise ValueError("使用聚合时必须提供 group_by 分组列")
        else:
            cols = columns or sorted(valid)[:20]
            unknown = set(cols) - valid
            if unknown:
                raise ValueError(f"未知列 {sorted(unknown)}，可用列：{sorted(valid)}")
            selects = [_quote_ident(c) for c in cols]

        group_clause = ""
        if group_by:
            unknown_g = set(group_by) - valid
            if unknown_g:
                raise ValueError(f"未知分组列 {sorted(unknown_g)}")
            group_clause = " GROUP BY " + ", ".join(_quote_ident(c) for c in group_by)

        where_sql, params = _build_where(conn, table, where or {})
        where_clause = f" WHERE {where_sql}" if where_sql else ""

        order_clause = ""
        if order_by:
            parts = []
            for item in order_by:
                col = item.get("column")
                if col not in valid and col not in alias_for.values():
                    raise ValueError(
                        f"未知排序列 {col}；明细模式可用列：{sorted(valid)}，"
                        f"聚合模式可排序列：{sorted(group_by or [])} 或聚合别名 {sorted(alias_for.values())}"
                    )
                desc = " DESC" if item.get("desc") else ""
                if aggregations:
                    if col in alias_for:  # 用户传聚合列原名（如 revenue）
                        parts.append(f"{_quote_ident(alias_for[col])}{desc}")
                    elif col in alias_for.values():  # 用户传聚合别名（如 sum_revenue）
                        parts.append(f"{_quote_ident(col)}{desc}")
                    else:  # 分组列
                        parts.append(f"{_quote_ident(col)}{desc}")
                else:
                    parts.append(f"{_quote_ident(col)}{desc}")
            order_clause = " ORDER BY " + ", ".join(parts)

        sql = (
            f"SELECT {', '.join(selects)} FROM {_quote_ident(table)}"
            f"{where_clause}{group_clause}{order_clause} LIMIT {limit} OFFSET {offset}"
        )
        rows = _run_query(sql, params)
    finally:
        conn.close()

    # 金额列换算（百万分之一元 → 元），兼容明细列与 sum_/avg_/max_/min_ 聚合列
    scaled = SCALED_COLUMNS.get(table, {})
    for row in rows:
        for col in list(row.keys()):
            base = next((b for b, f in scaled.items() if col == b or col.endswith("_" + b)), None)
            if base and row[col] is not None:
                try:
                    row[col] = round(float(row[col]) / scaled[base], 2)
                except (TypeError, ValueError):
                    pass

    return {
        "table": table,
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "rows": rows,
        "scaled_columns": scaled,
        "note": "jy_records 金额列已换算为元；rows 为分页结果，若需全量请使用 group_by 聚合。",
    }


if ENABLE_RAW_SQL:

    @MCP.tool()
    def query_sql(sql: str) -> dict[str, Any]:
        """受控只读 SQL 查询（高阶）。仅允许 SELECT，表必须白名单，强制行数上限。

        适合需要复杂 JOIN / 子查询的场景；优先使用 query_data。
        """
        try:
            safe_sql = _validate_readonly_sql(sql)
            started = time.time()
            rows = _run_query(safe_sql, [])
            return {
                "row_count": len(rows),
                "rows": rows,
                "elapsed_ms": int((time.time() - started) * 1000),
                "note": "只读查询；结果最多返回 500 行。金额列（如 jy_records 的 revenue/cart_amount）返回原始单位百万分之一元，"
                        "请除以 1,000,000 换算为元；如需已换算结果请改用 query_data。",
            }
        except ValueError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("query_sql 执行异常")
            return {"error": f"查询执行失败：{exc}"}


# ---------------------------------------------------------------------------
# streamable-http 入口 + Bearer Token 认证
# ---------------------------------------------------------------------------
def _build_app():
    """包装 mcp 的 Starlette app：HTTP 请求先校验 Bearer Token，lifespan 原样透传。

    不能重建 Starlette（会丢失 mcp 自带的 lifespan/task-group 初始化），
    因此这里用纯 ASGI 包装器，对 http 类型请求做认证，其余类型（lifespan）
    直接转发给内部 app。
    """
    from starlette.responses import JSONResponse

    inner = MCP.streamable_http_app()
    expected = f"Bearer {AUTH_TOKEN}".encode("ascii")

    async def dispatch(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        if headers.get(b"authorization", b"") != expected:
            response = JSONResponse(
                {"error": "unauthorized", "message": "缺少或错误的访问令牌"},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        await inner(scope, receive, send)

    return dispatch


if __name__ == "__main__":
    import uvicorn

    LOGGER.info("只读 MCP 服务器启动中：监听 0.0.0.0:%s，数据库 %s/%s，白名单表 %d 张",
                SERVER_PORT, DB_HOST, DB_NAME, len(ALLOWED_TABLES))
    LOGGER.info("受控只读 SQL 工具：%s", "已开放" if ENABLE_RAW_SQL else "关闭")
    uvicorn.run(_build_app(), host="0.0.0.0", port=SERVER_PORT, log_level="info")
