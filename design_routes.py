"""Authenticated API for the design department library."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from utils import design_library_service
from utils import permission_service
from utils.import_service import get_engine


router = APIRouter(prefix="/api/design", tags=["设计部资料库"])
DATA = design_library_service.DATA
IMAGE_NAME = re.compile(r"[0-9a-f]{20}\.webp\Z")
IMAGE_PREFIX = "/api/design/image/"
ITEM_TYPES = set(design_library_service.ITEM_TYPES)
TYPE_PAGES = {
    "models": "design-models", "prompts": "design-prompts",
    "comparisons": "design-comparisons", "styles": "design-styles",
}
DESIGN_PAGES = {"design-overview", *TYPE_PAGES.values()}


class DesignItemPayload(BaseModel):
    item_type: Literal["models", "prompts", "comparisons", "styles"]
    title: str = Field(..., min_length=1, max_length=255)
    text: str = Field(..., min_length=1, max_length=200000)
    images: list[str] = Field(default_factory=list, max_length=8)
    original: str | None = Field(default=None, max_length=1024)
    generated: str | None = Field(default=None, max_length=1024)
    product: str = Field(default="", max_length=64)
    scene: str = Field(default="", max_length=64)
    category: str = Field(default="", max_length=64)

    @field_validator("images")
    @classmethod
    def validate_images(cls, values: list[str]) -> list[str]:
        return [_validate_image_url(value) for value in values if str(value).strip()]

    @field_validator("original", "generated")
    @classmethod
    def validate_pair_image(cls, value: str | None) -> str | None:
        return _validate_image_url(value) if value else None


def _validate_image_url(value: str) -> str:
    candidate = str(value).strip()
    if not candidate.startswith(IMAGE_PREFIX):
        raise ValueError("图片地址必须来自设计资料库")
    filename = candidate[len(IMAGE_PREFIX):]
    if not IMAGE_NAME.fullmatch(filename):
        raise ValueError("图片地址格式不正确")
    return candidate


async def require_login(request: Request) -> dict[str, Any]:
    from main import _get_authenticated_user

    return await run_in_threadpool(_get_authenticated_user, request)


def _allowed_pages(user: dict[str, Any]) -> set[str]:
    engine = get_engine()
    return set(permission_service.allowed_page_keys(
        engine, str(user.get("role") or ""),
        permission_service.legacy_name_if_unique(engine, str(user.get("real_name") or "")),
        "account:" + str(user.get("username") or ""),
    )) & DESIGN_PAGES


def _require_page(user: dict[str, Any], page: str) -> None:
    if page not in _allowed_pages(user):
        raise HTTPException(status_code=403, detail="无权访问该设计页面")


def _user_name(user: dict[str, Any]) -> str:
    return str(user.get("real_name") or user.get("username") or "unknown")[:191]


def require_admin(user: dict[str, Any]) -> None:
    if str(user.get("role") or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="仅 admin 角色可以管理设计回收站")


def _require_item_type(item_type: str) -> None:
    if item_type not in ITEM_TYPES:
        raise HTTPException(status_code=400, detail="资料类型不正确")


@router.get("/catalog")
async def catalog(request: Request) -> dict[str, Any]:
    user = await require_login(request)
    allowed = await run_in_threadpool(_allowed_pages, user)
    if not allowed:
        raise HTTPException(status_code=403, detail="无权访问设计资料")
    result = await run_in_threadpool(design_library_service.catalog)
    for item_type, page in TYPE_PAGES.items():
        if page not in allowed:
            result[item_type] = []
    result["sources"] = list(dict.fromkeys(
        str(item.get("source") or "")
        for item_type in TYPE_PAGES for item in result[item_type]
        if item.get("source")
    ))
    return result


@router.get("/image/{filename}")
async def image(filename: str, request: Request) -> FileResponse:
    user = await require_login(request)
    if not IMAGE_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="图片不存在")
    path = DATA / "images" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    allowed = await run_in_threadpool(_allowed_pages, user)
    url = IMAGE_PREFIX + filename
    allowed_types = {item_type for item_type, page in TYPE_PAGES.items() if page in allowed}
    admin = str(user.get("role") or "").strip().lower() == "admin"
    if not await run_in_threadpool(design_library_service.image_is_visible, url, allowed_types, admin=admin):
        raise HTTPException(status_code=403, detail="无权访问该图片")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/upload")
async def upload_image(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    user = await require_login(request)
    allowed = await run_in_threadpool(_allowed_pages, user)
    if not allowed & set(TYPE_PAGES.values()):
        raise HTTPException(status_code=403, detail="无权上传设计资料")
    raw = await file.read()
    try:
        url = await run_in_threadpool(design_library_service.save_image, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"url": url, "operator": _user_name(user)}


@router.post("/items")
async def create_item(payload: DesignItemPayload, request: Request) -> dict[str, Any]:
    user = await require_login(request)
    await run_in_threadpool(_require_page, user, TYPE_PAGES[payload.item_type])
    item = await run_in_threadpool(
        design_library_service.create_item,
        payload.model_dump(),
        user_name=_user_name(user),
    )
    return {"item": item}


@router.put("/items/{item_type}/{item_id}")
async def update_item(item_type: str, item_id: str, payload: DesignItemPayload, request: Request) -> dict[str, Any]:
    user = await require_login(request)
    if item_type not in ITEM_TYPES or payload.item_type != item_type:
        raise HTTPException(status_code=400, detail="资料类型不匹配")
    await run_in_threadpool(_require_page, user, TYPE_PAGES[item_type])
    item = await run_in_threadpool(
        design_library_service.update_item,
        item_type,
        item_id,
        payload.model_dump(),
        user_name=_user_name(user),
    )
    if not item:
        raise HTTPException(status_code=404, detail="设计资料不存在")
    return {"item": item}


@router.delete("/items/{item_type}/{item_id}")
async def delete_item(item_type: str, item_id: str, request: Request) -> dict[str, bool]:
    user = await require_login(request)
    if not await run_in_threadpool(permission_service.can_delete_design_item, user, get_engine()):
        raise HTTPException(status_code=403, detail="无权删除设计资料")
    _require_item_type(item_type)
    await run_in_threadpool(_require_page, user, TYPE_PAGES[item_type])
    deleted = await run_in_threadpool(design_library_service.delete_item, item_type, item_id, user_name=_user_name(user))
    if not deleted:
        raise HTTPException(status_code=404, detail="设计资料不存在")
    return {"deleted": True}


@router.get("/trash")
async def list_trash(request: Request) -> dict[str, Any]:
    user = await require_login(request)
    require_admin(user)
    return {"items": await run_in_threadpool(design_library_service.trash_items)}


@router.post("/trash/{item_type}/{item_id}/restore")
async def restore_item(item_type: str, item_id: str, request: Request) -> dict[str, bool]:
    user = await require_login(request)
    require_admin(user)
    _require_item_type(item_type)
    restored = await run_in_threadpool(design_library_service.restore_item, item_type, item_id)
    if not restored:
        raise HTTPException(status_code=404, detail="回收站中没有这条资料")
    return {"restored": True}


@router.delete("/trash/{item_type}/{item_id}")
async def purge_item(item_type: str, item_id: str, request: Request) -> dict[str, bool]:
    user = await require_login(request)
    require_admin(user)
    _require_item_type(item_type)
    deleted = await run_in_threadpool(design_library_service.purge_item, item_type, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="回收站中没有这条资料")
    return {"deleted": True}
