"""Permission-controlled report lookup, PDF preview, download and upload."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from utils import permission_service, product_quality_report_service as service

router = APIRouter(prefix="/api/product-quality-reports", tags=["产品质检报告"])
PAGE_KEY = "product-quality-reports"
MANAGE_ROLES = {"admin", "管理员", "boss"}


def authorize(request: Request) -> dict[str, Any]:
    from main import _get_authenticated_user, _get_mysql_engine, _is_admin_user

    user = _get_authenticated_user(request)
    if not _is_admin_user(user):
        engine = _get_mysql_engine()
        allowed = permission_service.allowed_page_keys(
            engine, str(user.get("role") or ""),
            permission_service.legacy_name_if_unique(engine, str(user.get("real_name") or "")),
            "account:" + str(user.get("username") or ""),
        )
        if PAGE_KEY not in allowed:
            raise HTTPException(status_code=403, detail="无产品质检报告访问权限")
    return user


@router.get("")
def catalog(request: Request, keyword: str = Query("", max_length=200),
            category: str = Query("", max_length=100), page: int = Query(1, ge=1),
            page_size: int = Query(12, ge=1, le=100)) -> dict[str, Any]:
    user = authorize(request)
    result = service.catalog(keyword, category, page, page_size)
    result["can_upload"] = str(user.get("role") or "").strip().lower() in MANAGE_ROLES
    return result


@router.get("/{report_id}/file")
def report_file(report_id: str, request: Request, download: bool = False) -> FileResponse:
    authorize(request)
    report = service.get_report(report_id)
    path = service.report_path(report_id) if report else None
    if not report or not path:
        raise HTTPException(status_code=404, detail="报告不存在或原文件已丢失")
    return FileResponse(
        path, media_type="application/pdf", filename=report["filename"],
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), category: str = Form("常规检测", max_length=100)) -> dict[str, Any]:
    user = await run_in_threadpool(authorize, request)
    if str(user.get("role") or "").strip().lower() not in MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="仅管理员或总经理可上传质检报告")
    raw = await file.read(service.MAX_FILE_SIZE + 1)
    try:
        return await run_in_threadpool(
            service.save_report, raw, file.filename or "", category,
            str(user.get("real_name") or user.get("username") or "unknown"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
