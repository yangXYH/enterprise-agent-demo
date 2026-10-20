"""SKU 退货数据查询、导出和品牌规则接口。"""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils import sku_return_service as service


router = APIRouter(prefix="/api/sku-returns", tags=["SKU 退货数据"])
_READ_PAGE = "sku-return-data"
_WRITE_ROLES = frozenset(("admin", "管理员", "operator"))
_SORT_FIELDS = frozenset((
    "sales_quantity", "return_in_quantity", "after_sales_quantity",
    "return_quantity", "return_rate", "sku_code", "sku_name", "period",
))


def authorize(request: Request, *, write: bool = False) -> dict:
    """每次请求重新校验登录及页面授权；写入规则另限管理员和运营。"""
    from main import _get_authenticated_user, _get_mysql_engine, _is_admin_user
    from utils.permission_service import allowed_page_keys

    user = _get_authenticated_user(request)
    role = str(user.get("role") or "").strip()
    if not _is_admin_user(user):
        engine = _get_mysql_engine()
        account_key = "account:" + str(user.get("username") or "").strip()
        allowed = allowed_page_keys(
            engine, role, str(user.get("real_name") or ""), account_key
        )
        if _READ_PAGE not in allowed:
            raise HTTPException(403, "无 SKU 退货数据页面访问权限")
    if write and role not in _WRITE_ROLES:
        raise HTTPException(403, "仅管理员或运营角色可维护品牌规则")
    return user


async def _invoke(fn, /, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except service.StaleRunError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def query_filters(
    period: list[str] | None = Query(None),
    entity: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    brand: list[str] | None = Query(None),
    supplier: list[str] | None = Query(None),
    sku_keyword: str = Query("", max_length=191),
) -> dict:
    """重复查询参数构成多选筛选；空数组代表不限制。"""
    return {
        "period": period or [],
        "entity": entity or [],
        "category": category or [],
        "brand": brand or [],
        "supplier": supplier or [],
        "sku_keyword": sku_keyword.strip(),
    }


def _check_sort(view: str, sort_by: str) -> None:
    if sort_by not in _SORT_FIELDS or (sort_by == "period" and view != "detail"):
        raise HTTPException(422, "不支持的排序字段")


@router.get("/metadata")
async def metadata(request: Request, run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$")):
    await run_in_threadpool(authorize, request)
    return await _invoke(service.get_metadata, run_id=run_id)


@router.get("/options/suppliers")
async def suppliers(
    request: Request,
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    keyword: str = Query("", max_length=191),
    limit: int = Query(50, ge=1, le=200),
    filters: dict = Depends(query_filters),
):
    await run_in_threadpool(authorize, request)
    return await _invoke(
        service.list_suppliers, keyword=keyword, limit=limit, run_id=run_id,
        filters=filters,
    )


@router.get("/options")
async def filter_options(
    request: Request,
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    filters: dict = Depends(query_filters),
):
    await run_in_threadpool(authorize, request)
    return await _invoke(service.get_filter_options, filters=filters, run_id=run_id)


@router.get("/summary")
async def summary(
    request: Request,
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    filters: dict = Depends(query_filters),
):
    await run_in_threadpool(authorize, request)
    return await _invoke(service.get_summary, filters=filters, run_id=run_id)


@router.get("/monthly-trend")
async def monthly_trend(
    request: Request,
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    filters: dict = Depends(query_filters),
):
    await run_in_threadpool(authorize, request)
    return await _invoke(service.get_monthly_trend, filters=filters, run_id=run_id)


@router.get("/items")
async def items(
    request: Request,
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    filters: dict = Depends(query_filters),
    view: Literal["sku", "detail"] = "sku",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = "return_quantity",
    sort_dir: Literal["asc", "desc"] = "desc",
):
    await run_in_threadpool(authorize, request)
    _check_sort(view, sort_by)
    return await _invoke(
        service.list_items, filters=filters, view=view, page=page,
        page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, run_id=run_id,
    )


@router.get("/sources")
async def sources(
    request: Request,
    sku_code: str = Query(..., min_length=1),
    sku_name: str = Query(...),
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    filters: dict = Depends(query_filters),
    detail_period: str | None = None,
    detail_entity: str | None = None,
    detail_category: str | None = None,
    detail_supplier_name: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    await run_in_threadpool(authorize, request)
    return await _invoke(
        service.list_sources, sku_code, sku_name, filters=filters,
        period=detail_period, entity=detail_entity, category=detail_category,
        supplier_name=detail_supplier_name, limit=limit, run_id=run_id,
    )


@router.get("/export")
async def export(
    request: Request,
    run_id: str | None = Query(None, pattern=r"^[0-9a-f]{32}$"),
    filters: dict = Depends(query_filters),
    view: Literal["sku", "detail"] = "sku",
    sort_by: str = "return_quantity",
    sort_dir: Literal["asc", "desc"] = "desc",
):
    await run_in_threadpool(authorize, request)
    _check_sort(view, sort_by)
    filename, content = await _invoke(
        service.export_items, filters=filters, view=view,
        sort_by=sort_by, sort_dir=sort_dir, run_id=run_id,
    )
    media_type = (
        "text/csv; charset=utf-8" if filename.lower().endswith(".csv")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    extension = "csv" if filename.lower().endswith(".csv") else "xlsx"
    return StreamingResponse(
        iter((content,)), media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=sku-returns.{extension}; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


class BrandRule(BaseModel):
    match_type: Literal["exact", "prefix"]
    pattern: str = Field(min_length=1, max_length=191)
    canonical_brand: str = Field(min_length=1, max_length=191)
    priority: int = 0
    enabled: bool = True


class BrandRulesPreview(BaseModel):
    rules: list[BrandRule] = Field(max_length=1000)


class BrandRulesUpdate(BrandRulesPreview):
    expected_version: int | str


@router.get("/brand-rules")
async def brand_rules(request: Request):
    await run_in_threadpool(authorize, request, write=True)
    return await _invoke(service.list_brand_rules)


@router.post("/brand-rules/preview")
async def preview_brand_rules(request: Request, body: BrandRulesPreview):
    await run_in_threadpool(authorize, request, write=True)
    return await _invoke(
        service.preview_brand_rules, [rule.model_dump() for rule in body.rules]
    )


@router.put("/brand-rules")
async def update_brand_rules(request: Request, body: BrandRulesUpdate):
    user = await run_in_threadpool(authorize, request, write=True)
    updated_by = str(user.get("username") or user.get("real_name") or "")
    return await _invoke(
        service.replace_brand_rules,
        [rule.model_dump() for rule in body.rules],
        body.expected_version,
        updated_by,
    )
