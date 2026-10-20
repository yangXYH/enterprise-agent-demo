"""Administrator account management API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from utils.import_service import get_engine

router = APIRouter(prefix="/api/admin", tags=["系统管理"])
ROLES = {"admin", "管理员", "boss", "operator", "designer", "hr", "finance", "supply", "user"}


class NewUser(BaseModel):
    username: str
    password: str
    real_name: str = Field(min_length=1, max_length=50)
    department: str = Field(min_length=1, max_length=100)
    job_title: str = Field(default="", max_length=100)
    role: str = Field(default="user", max_length=50)


class EditUser(BaseModel):
    real_name: str = Field(min_length=1, max_length=50)
    department: str = Field(min_length=1, max_length=100)
    job_title: str = Field(default="", max_length=100)
    role: str = Field(max_length=50)


class ResetPassword(BaseModel):
    password: str


def _admin(request: Request) -> dict[str, Any]:
    from main import _get_authenticated_user
    user = _get_authenticated_user(request)
    if str(user.get("role") or "").strip().lower() not in {"admin", "管理员"}:
        raise HTTPException(status_code=403, detail="仅管理员可管理账号")
    return user


def _validate_role(role: str) -> str:
    role = role.strip()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="角色不在允许范围内")
    return role


def _require_remaining_admin(conn: Any, target_role: str) -> None:
    if target_role.lower() not in {"admin", "管理员"}:
        return
    # 锁住管理员行，避免两个管理员同时删除/降权后一个都不剩。
    admins = conn.execute(text(
        "SELECT id FROM sys_user WHERE LOWER(role) IN ('admin', '管理员') FOR UPDATE"
    )).all()
    if len(admins) <= 1:
        raise HTTPException(status_code=409, detail="必须保留至少一个管理员账号")


def _clean(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{label}不能为空")
    return value


@router.get("/users")
def list_users(request: Request):
    _admin(request)
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT id, username, real_name, department, job_title, role, created_at "
            "FROM sys_user ORDER BY id DESC"
        )).mappings().all()
    return {"users": [dict(row) for row in rows], "roles": sorted(ROLES)}


@router.post("/users", status_code=201)
def create_user(body: NewUser, request: Request):
    _admin(request)
    username = body.username
    values = {
        "username": username,
        "password": body.password,
        "real_name": _clean(body.real_name, "姓名"),
        "department": _clean(body.department, "部门"),
        "job_title": body.job_title.strip(),
        "role": _validate_role(body.role),
    }
    try:
        with get_engine().begin() as conn:
            conn.execute(text(
                "INSERT INTO sys_user (username, password, real_name, department, job_title, role) "
                "VALUES (:username, :password, :real_name, :department, :job_title, :role)"
            ), values)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该登录账号已存在") from exc
    return {"ok": True}


@router.put("/users/{user_id}")
def update_user(user_id: int, body: EditUser, request: Request):
    _admin(request)
    values = {
        "id": user_id,
        "real_name": _clean(body.real_name, "姓名"),
        "department": _clean(body.department, "部门"),
        "job_title": body.job_title.strip(),
        "role": _validate_role(body.role),
    }
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT role FROM sys_user WHERE id = :id FOR UPDATE"), {"id": user_id}).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="账号不存在")
        if str(row["role"]).lower() in {"admin", "管理员"} and values["role"].lower() not in {"admin", "管理员"}:
            _require_remaining_admin(conn, str(row["role"]))
        conn.execute(text(
            "UPDATE sys_user SET real_name=:real_name, department=:department, "
            "job_title=:job_title, role=:role WHERE id=:id"
        ), values)
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: ResetPassword, request: Request):
    _admin(request)
    with get_engine().begin() as conn:
        result = conn.execute(text("UPDATE sys_user SET password=:password WHERE id=:id"), {
            "password": body.password, "id": user_id,
        })
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="账号不存在")
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request):
    actor = _admin(request)
    if int(actor["id"]) == user_id:
        raise HTTPException(status_code=409, detail="不能删除当前登录账号")
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT role FROM sys_user WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="账号不存在")
        _require_remaining_admin(conn, str(row["role"]))
        conn.execute(text("DELETE FROM sys_user WHERE id=:id"), {"id": user_id})
    return {"ok": True}
