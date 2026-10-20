"""Authenticated API for employee points."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, Request

from utils import points_service as points

router = APIRouter(prefix="/api/points", tags=["积分系统"])


def _user(request: Request) -> dict:
    from main import _get_authenticated_user
    return _get_authenticated_user(request)


def _editor(request: Request) -> dict:
    user = _user(request)
    if str(user.get("role") or "").strip().lower() not in {"admin", "hr", "管理员"}:
        raise HTTPException(status_code=403, detail="仅管理员或 HR 可管理积分")
    return user


@router.get("/leaderboard")
def leaderboard(
    request: Request, company: str = Query("", max_length=100),
    dept: str = Query("", max_length=100), keyword: str = Query("", max_length=100),
    month: str = Query("", max_length=7), sort: str = Query("total"),
):
    _user(request)
    try:
        return points.leaderboard(company=company, dept=dept, keyword=keyword, month=month, sort=sort)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/rules")
def rules(request: Request):
    _user(request)
    return {"items": points.list_rules()}


@router.post("/rules")
def save_rule(request: Request, payload: dict = Body(...)):
    _editor(request)
    try:
        return points.save_rule(payload)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/records")
def records(
    request: Request, employee_id: int = Query(0, ge=0), month: str = Query("", max_length=7),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    _user(request)
    try:
        return points.list_records(employee_id=employee_id, month=month, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/records")
def add_record(request: Request, payload: dict = Body(...)):
    user = _editor(request)
    try:
        return points.add_record(
            employee_id=int(payload.get("employee_id") or 0),
            rule_id=int(payload.get("rule_id") or 0),
            note=str(payload.get("note") or ""),
            operator=str(user.get("real_name") or user.get("username") or ""),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
