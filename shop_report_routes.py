"""Authenticated, permission-controlled access to the shop expense snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from utils import permission_service


router = APIRouter(prefix="/api/shop-report", tags=["店铺报表"])
SNAPSHOT = Path(__file__).resolve().parent / "data" / "shop_report.json"
PAGE_KEY = "shop-report"


def _authorize(request: Request) -> None:
    # Import lazily: main.py includes this router after defining auth helpers.
    from main import _get_authenticated_user, _get_mysql_engine, _is_admin_user

    user = _get_authenticated_user(request)
    if _is_admin_user(user):
        return
    engine = _get_mysql_engine()
    allowed = permission_service.allowed_page_keys(
        engine,
        str(user.get("role") or ""),
        permission_service.legacy_name_if_unique(engine, str(user.get("real_name") or "")),
        "account:" + str(user.get("username") or ""),
    )
    if PAGE_KEY not in allowed:
        raise HTTPException(status_code=403, detail="无店铺报表访问权限")


def _filter_shops_for_user(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """按当前用户有权访问的具体店铺过滤 shops/rows。

    - admin 不过滤；
    - 已通过 _authorize（拥有 shop-report 总权限）的用户，进一步只保留其 allowed
      中以 "shop-report:" 开头的具体店铺；若 allowed 里没有任何具体店铺 key，
      说明尚未按店铺收窄，则保持全量（兼容升级前配置）。
    """
    from main import _get_authenticated_user, _get_mysql_engine, _is_admin_user

    user = _get_authenticated_user(request)
    if _is_admin_user(user):
        return payload
    engine = _get_mysql_engine()
    allowed = permission_service.allowed_page_keys(
        engine,
        str(user.get("role") or ""),
        permission_service.legacy_name_if_unique(engine, str(user.get("real_name") or "")),
        "account:" + str(user.get("username") or ""),
    )
    shop_keys = {k for k in allowed if k.startswith("shop-report:")}
    if not shop_keys:
        # 尚未按店铺粒度授权：保持现有全量可见行为
        return payload
    kept_shops = [
        s for s in payload.get("shops", [])
        if f"shop-report:{s.get('channel')}:{s.get('shop_id')}" in shop_keys
    ]
    kept_ids = {(s.get("channel"), s.get("shop_id")) for s in kept_shops}
    kept_rows = [
        r for r in payload.get("rows", [])
        if (r.get("channel"), r.get("shop_id")) in kept_ids
    ]
    return {**payload, "shops": kept_shops, "rows": kept_rows}


def _load_snapshot() -> dict[str, Any]:
    try:
        with SNAPSHOT.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="店铺报表尚未导入数据") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="店铺报表快照无法读取") from exc
    if not isinstance(data, dict) or not all(key in data for key in ("source", "months", "shops", "rows")):
        raise HTTPException(status_code=503, detail="店铺报表快照格式不正确")
    return data


@router.get("")
def get_shop_report(request: Request, response: Response) -> dict[str, Any]:
    _authorize(request)
    response.headers["Cache-Control"] = "private, no-store"
    return _filter_shops_for_user(_load_snapshot(), request)
