# -*- coding: utf-8 -*-
"""只读 MCP 端点集成模块：把现有系统的经营分析接口以 MCP 协议暴露给运营 DSH。

设计目标
--------
运营电脑上的 DeepSeek Harness 通过 MCP 客户端连到本系统后，AI 直接调用
「系统现有的经营分析查询接口」（operating_analysis_service 的只读函数），
由系统返回数据 —— 不需要给运营数据库账号，也不需要另起独立进程。

安全边界
--------
- 只暴露**只读查询**能力（经营分析看板/元数据），不暴露导入、保存等写接口；
- 请求必须携带 Bearer Token（环境变量 OPERATING_MCP_TOKEN），否则 401；
- 未设置 OPERATING_MCP_TOKEN 时本模块不挂载任何端点，不影响主应用。

用法（在 main.py 里，SPA 兜底路由之前）：
    from mcp_integration import mount_mcp
    mount_mcp(app)

依赖：pip install "mcp>=2.0"
"""

from __future__ import annotations

import logging
import os
from typing import Any

LOGGER = logging.getLogger("mcp-integration")

MCP_TOKEN = os.getenv("OPERATING_MCP_TOKEN", "").strip()
MCP_PATH = os.getenv("OPERATING_MCP_PATH", "/mcp").strip() or "/mcp"

# 金额字段说明（供 AI 理解返回结构）
_METRICS_HINT = (
    "经营分析金额字段（revenue 成交金额、cart_amount 加购金额）接口返回单位均为元。"
    "指标可选：revenue 成交金额 / quantity 成交件数 / orders 成交单量 / customers 成交客户数 / "
    "views 浏览量 / visitors 访客数 / cart_quantity 加购件数 / cart_customers 加购客户数 / cart_amount 加购金额。"
    "分组可选：sku / category / model。"
)


def mount_mcp(app) -> bool:
    """把只读 MCP 端点挂到 FastAPI 应用上。返回是否成功挂载。

    - 未设置 OPERATING_MCP_TOKEN 时直接跳过（返回 False）；
    - mcp 库未安装 / 版本不兼容时抛 ImportError（由调用方决定是否吞掉）。
    """
    if not MCP_TOKEN:
        LOGGER.warning("未设置 OPERATING_MCP_TOKEN，只读 MCP 端点不启用")
        return False

    from contextlib import asynccontextmanager

    try:  # mcp >= 2.0
        from mcp.server.mcpserver import MCPServer as _MCPBase
    except ImportError:  # mcp < 2.0
        from mcp.server.fastmcp import FastMCP as _MCPBase

    mcp = _MCPBase(
        "enterprise-operating-readonly",
        instructions=(
            "你是企业「经营数据只读查询」助手。所有工具只读取数据，不能修改任何数据。"
            "优先使用 operating_dashboard 查询经营分析数据；先用 operating_metadata 了解支持的数据范围。"
        ),
    )

    # ── 工具：经营分析元数据 ──
    @mcp.tool()
    def operating_metadata() -> dict[str, Any]:
        """查看经营分析支持的数据范围（起止日期、指标、分组、口径说明）。"""
        from utils import operating_analysis_service as service

        try:
            return service.metadata()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("operating_metadata 失败")
            return {"error": f"查询失败：{exc}"}

    # ── 工具：经营分析看板查询（只读，复用系统现有接口逻辑） ──
    @mcp.tool()
    def operating_dashboard(
        start: str,
        end: str,
        keyword: str = "",
        category: str = "",
        brand: str = "",
        metric: str = "revenue",
        group: str = "sku",
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """经营分析看板查询（只读）。

        参数：
        - start / end: 日期区间，格式 YYYY-MM-DD，跨度不超过 3 年
        - keyword: 按 SKU / 商品名称 / 货号模糊筛选（可选）
        - category: 三级类目精确筛选（可选）
        - brand: 品牌筛选（可选，如"测试旅行""DEMO_BAGS"）
        - metric: 排序/排名指标，默认 revenue（成交金额）
        - group: 排名分组，sku / category / model，默认 sku
        - page / page_size: 明细分页（page_size 最大 200）

        返回：summary 汇总、coverage 数据覆盖、comparisons 同比/环比、
        trend 每日趋势、ranking 排名、items 明细、category_distribution 类目分布。
        """
        from utils import operating_analysis_service as service

        try:
            page = max(1, int(page))
            page_size = min(max(1, int(page_size)), 200)
            result = service.dashboard(
                start=start,
                end=end,
                keyword=keyword or "",
                category=category or "",
                brand=brand or "",
                metric=metric or "revenue",
                group=group or "sku",
                page=page,
                page_size=page_size,
            )
            # 明细里的原始行 JSON（raw）体积大且对分析无益，剥离后再返回
            for item in result.get("items", []):
                item.pop("raw", None)
            result["hint"] = _METRICS_HINT
            return result
        except ValueError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("operating_dashboard 失败")
            return {"error": f"查询失败：{exc}"}

    # ── streamable-http 子应用 + Bearer Token 认证 ──
    inner = mcp.streamable_http_app(streamable_http_path="/")
    session_manager = getattr(getattr(mcp, "_lowlevel_server", None), "_session_manager", None)
    if session_manager is None:
        raise ImportError("无法获取 MCP session manager，请安装 mcp>=2.0")

    from starlette.responses import JSONResponse

    expected = f"Bearer {MCP_TOKEN}".encode("ascii")

    async def _auth_dispatch(scope, receive, send):
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

    # 挂载 + 合并 lifespan（手动启动 mcp 的 session manager）
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _combined_lifespan(app_):
        async with session_manager.run():
            async with original_lifespan(app_):
                yield

    app.router.lifespan_context = _combined_lifespan
    app.mount(MCP_PATH, _auth_dispatch)

    LOGGER.info("只读 MCP 端点已挂载：%s（Token 认证开启）", MCP_PATH)
    return True
