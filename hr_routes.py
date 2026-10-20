"""人力行政模块 API 路由。

挂载方式（main.py 中，SPA catch-all 之前）：
    from hr_routes import router as hr_router
    app.include_router(hr_router, prefix="/api/hr", tags=["人力资源模块"])

角色与脱敏（已确认的严格策略）：
- 全字段可见可编辑：admin / hr / 管理员；
- 其余角色（含 boss 总经理/副总）一律脱敏：身份证前6后4、银行卡后4、电话中间4、住址仅市/区；
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

import utils.hr_service as hr
import utils.permission_service as permission_service
from utils.import_service import get_engine

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["人力资源模块"])

# 敏感字段全见角色
_FULL_ACCESS_ROLES = {"admin", "hr", "管理员"}


def _current_user(request: Request) -> dict[str, Any]:
    """取当前登录用户（复用 main 的会话解析；懒导入避免循环依赖）。"""
    try:
        from main import _get_authenticated_user

        return _get_authenticated_user(request)
    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.warning("解析登录会话失败: %s", exc)
        raise HTTPException(status_code=401, detail="请先登录") from exc


def _can_view_all(request: Request) -> bool:
    user = _current_user(request)
    return str(user.get("role") or "").strip().lower() in _FULL_ACCESS_ROLES


def _save_upload(upload: UploadFile) -> str:
    """保存上传文件到临时目录，返回路径（调用方负责 finally 删除）。"""
    suffix = Path(upload.filename or "upload.xlsx").suffix or ".xlsx"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(upload.file.read())
    except Exception:
        os.unlink(tmp_path)
        raise
    return tmp_path


def _safe_unlink(path: str) -> None:
    """删除临时文件；Windows 下文件句柄/杀软可能短暂占用，删除失败时重试。"""
    import gc
    import time

    for _ in range(5):
        try:
            os.unlink(path)
            return
        except PermissionError:
            gc.collect()
            time.sleep(0.3)
    # 多次重试仍失败则静默忽略（临时文件由操作系统临时目录机制兜底清理）


# ── 人员花名册 ────────────────────────────────────────────────────────────────


@router.get("/roster/list")
def hr_roster_list(
    request: Request,
    keyword: str = Query("", max_length=100),
    dept: str = Query("", max_length=100),
    status: str = Query("active", max_length=20),
    education: str = Query("", max_length=20),
    company: str = Query("", max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    try:
        return hr.list_employees(
            keyword=keyword, dept=dept, status=status, education=education, company=company,
            page=page, page_size=page_size, can_view_all=_can_view_all(request),
        )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询员工列表失败")
        raise HTTPException(status_code=500, detail=f"查询员工列表失败: {exc}") from exc


@router.get("/roster/detail/{employee_id}")
def hr_roster_detail(employee_id: int, request: Request):
    try:
        return hr.get_employee_detail(employee_id, can_view_all=_can_view_all(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询员工详情失败")
        raise HTTPException(status_code=500, detail=f"查询员工详情失败: {exc}") from exc


@router.post("/roster/save")
def hr_roster_save(payload: dict = Body(...), request: Request = None):
    if not _can_view_all(request):
        raise HTTPException(status_code=403, detail="仅 HR/管理员可编辑员工档案")
    try:
        return hr.save_employee(payload)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("保存员工失败")
        raise HTTPException(status_code=500, detail=f"保存员工失败: {exc}") from exc


@router.post("/roster/delete")
def hr_roster_delete(payload: dict = Body(...), request: Request = None):
    if not _can_view_all(request):
        raise HTTPException(status_code=403, detail="仅 HR/管理员可删除员工档案")
    try:
        return hr.delete_employee(int(payload.get("id", 0)), hard=bool(payload.get("hard", False)))
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("删除员工失败")
        raise HTTPException(status_code=500, detail=f"删除员工失败: {exc}") from exc


@router.get("/roster/reminders")
def hr_roster_reminders():
    try:
        return hr.build_reminders()
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("生成提醒失败")
        raise HTTPException(status_code=500, detail=f"生成提醒失败: {exc}") from exc


@router.post("/roster/export")
def hr_roster_export(request: Request, payload: dict = Body(default={})):
    """导出花名册 Excel。默认脱敏列；admin/hr 可选全量（payload.full = true）。"""
    can_view_all = _can_view_all(request)
    try:
        data = hr.list_employees(
            keyword=str(payload.get("keyword", "")), dept=str(payload.get("dept", "")),
            status=str(payload.get("status", "active")), education=str(payload.get("education", "")),
            company=str(payload.get("company", "")),
            page=1, page_size=500, can_view_all=can_view_all,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导出数据失败: {exc}") from exc

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    _thin = Side(style="thin")
    _border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
    _header_fill = PatternFill("solid", fgColor="f1f5f9")
    _center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "员工花名册"
    headers = [
        "序号", "姓名", "部门", "组别", "岗位", "入职日期", "转正日期",
        "性别", "年龄", "学历", "学校", "专业", "电话", "邮箱", "合同类型", "状态",
    ]
    if can_view_all:
        headers += ["身份证号", "身份证有效期", "银行卡号", "开户行", "户口地址", "身份证住址", "现住地址", "紧急联系人", "关系", "联系电话"]
    else:
        headers += ["身份证号(脱敏)", "银行卡号(脱敏)", "住址(脱敏)"]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = Font(bold=True, size=11)
        c.fill = _header_fill
        c.alignment = _center
        c.border = _border
    for i, item in enumerate(data.get("items", []), start=1):
        vals = [
            i, item.get("name"), item.get("dept_name"), item.get("group_name"),
            item.get("position"), item.get("hire_date"), item.get("regular_date"),
            item.get("gender"), item.get("age") or "", item.get("education"),
            item.get("school"), item.get("major"), item.get("phone"), item.get("email"),
            item.get("contract_type"), "在职" if item.get("status") == "active" else "离职",
        ]
        if can_view_all:
            vals += [
                item.get("id_card"), item.get("id_card_expiry"), item.get("bank_card"),
                item.get("bank_name"), item.get("hukou_address"), item.get("id_address"),
                item.get("current_address"), "", "", "",
            ]
        else:
            vals += [item.get("id_card"), item.get("bank_card"), item.get("current_address")]
        for col_idx, v in enumerate(vals, start=1):
            c = ws.cell(row=i + 1, column=col_idx, value=v if v is not None else "")
            c.border = _border
            c.alignment = _center
    widths = [6, 10, 14, 10, 12, 12, 12, 6, 6, 8, 16, 12, 14, 22, 10, 8]
    if can_view_all:
        widths += [20, 12, 18, 14, 30, 30, 30, 10, 8, 14]
    else:
        widths += [20, 14, 24]
    for letter, w in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", widths):
        ws.column_dimensions[letter].width = w
    ws.freeze_panes = "A2"

    import io as _io

    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="hr-roster.xlsx"'},
    )


@router.get("/recruit/dashboard")
def hr_recruit_dashboard():
    try:
        return hr.recruit_dashboard()
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("招聘看板统计失败")
        raise HTTPException(status_code=500, detail=f"招聘看板统计失败: {exc}") from exc


# ── 考勤 ──────────────────────────────────────────────────────────────────────


@router.get("/attendance/summary")
def hr_attendance_summary(month: str = Query("", max_length=7), dept: str = Query("", max_length=100),
                          keyword: str = Query("", max_length=50)):
    try:
        return hr.list_attendance(month=month, dept=dept, keyword=keyword)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询考勤汇总失败")
        raise HTTPException(status_code=500, detail=f"查询考勤汇总失败: {exc}") from exc


@router.get("/attendance/overview")
def hr_attendance_overview(month: str = Query("", max_length=7)):
    try:
        return hr.attendance_overview(month=month)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("考勤概览统计失败")
        raise HTTPException(status_code=500, detail=f"考勤概览统计失败: {exc}") from exc


@router.get("/attendance/detail")
def hr_attendance_detail(month: str = Query("", max_length=7), name: str = Query("", max_length=50),
                         dept: str = Query("", max_length=100)):
    try:
        return hr.list_attendance_detail(month=month, name=name, dept=dept)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询考勤每日明细失败")
        raise HTTPException(status_code=500, detail=f"查询考勤每日明细失败: {exc}") from exc


@router.get("/attendance/late")
def hr_attendance_late(month: str = Query("", max_length=7), name: str = Query("", max_length=50)):
    try:
        return hr.list_attendance_late(month=month, name=name)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询考勤迟到记录失败")
        raise HTTPException(status_code=500, detail=f"查询考勤迟到记录失败: {exc}") from exc


@router.get("/attendance/leave")
def hr_attendance_leave(month: str = Query("", max_length=7), name: str = Query("", max_length=50)):
    try:
        return hr.list_attendance_leave(month=month, name=name)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询考勤请假记录失败")
        raise HTTPException(status_code=500, detail=f"查询考勤请假记录失败: {exc}") from exc


@router.get("/attendance/makeup")
def hr_attendance_makeup(month: str = Query("", max_length=7), name: str = Query("", max_length=50)):
    try:
        return hr.list_attendance_makeup(month=month, name=name)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询考勤补卡记录失败")
        raise HTTPException(status_code=500, detail=f"查询考勤补卡记录失败: {exc}") from exc


@router.get("/attendance/person")
def hr_attendance_person(month: str = Query("", max_length=7), name: str = Query("", max_length=50)):
    try:
        return hr.attendance_person(month=month, name=name)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询员工考勤档案失败")
        raise HTTPException(status_code=500, detail=f"查询员工考勤档案失败: {exc}") from exc


@router.get("/attendance/dept-summary")
def hr_attendance_dept_summary(month: str = Query("", max_length=7)):
    try:
        return hr.attendance_dept_summary(month=month)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("考勤部门汇总失败")
        raise HTTPException(status_code=500, detail=f"考勤部门汇总失败: {exc}") from exc


@router.get("/attendance/template")
def hr_attendance_template():
    return _build_simple_template(
        "考勤导入模板",
        ["姓名", "一级部门", "二级部门", "三级部门", "岗位", "月份(YYYY-MM)", "应计薪天数", "实际计薪天数",
         "应出勤天数", "实际出勤天数", "迟到次数", "迟到负激励", "早退次数", "早退负激励", "补卡次数", "补卡负激励",
         "旷工天数", "事假天数", "病假天数", "年假天数", "调休天数", "加班时长", "异常次数", "备注"],
        [["示例员工", "内容中心", "视觉设计组", "设计助理", "设计助理", "2026-08", 22, 22, 22, 22, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ""]],
        "attendance-template.xlsx",
    )


# ── 驾驶舱 ────────────────────────────────────────────────────────────────────


@router.get("/dashboard/overview")
def hr_dashboard_overview(company: str = Query("", max_length=50)):
    try:
        return hr.dashboard_overview(company=company)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("驾驶舱概览统计失败")
        raise HTTPException(status_code=500, detail=f"驾驶舱概览统计失败: {exc}") from exc


@router.get("/dashboard/flow")
def hr_dashboard_flow(months: int = Query(12, ge=3, le=24), company: str = Query("", max_length=50)):
    try:
        return hr.dashboard_flow(months=months, company=company)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("人员流动统计失败")
        raise HTTPException(status_code=500, detail=f"人员流动统计失败: {exc}") from exc


@router.get("/dashboard/reminders")
def hr_dashboard_reminders(company: str = Query("", max_length=50)):
    try:
        return hr.dashboard_reminders(company=company)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("驾驶舱到期分布统计失败")
        raise HTTPException(status_code=500, detail=f"驾驶舱到期分布统计失败: {exc}") from exc


# ── 导入引擎 ──────────────────────────────────────────────────────────────────


@router.post("/import/roster")
async def hr_import_roster(request: Request, file: UploadFile = File(...), operator: str = Form("")):
    """上传《员工花名册.xlsx》→ 清洗/校验/幂等入库 + 报告。"""
    _can_view_all(request)
    tmp = _save_upload(file)
    try:
        r1 = hr.import_roster_workbook(tmp, operator=operator or str(_current_user(request).get("real_name") or ""))
        r2 = hr.import_resign_workbook(tmp, operator=operator or str(_current_user(request).get("real_name") or ""))
        return {"code": 200, "roster": r1, "resign": r2}
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("花名册导入失败")
        raise HTTPException(status_code=500, detail=f"花名册导入失败: {exc}") from exc
    finally:
        os.unlink(tmp)


@router.post("/import/attendance")
async def hr_import_attendance(request: Request, file: UploadFile = File(...)):
    tmp = _save_upload(file)
    try:
        report = hr.import_attendance_excel(tmp, operator=str(_current_user(request).get("real_name") or ""))
        return {"code": 200, **report}
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("考勤导入失败")
        raise HTTPException(status_code=500, detail=f"考勤导入失败: {exc}") from exc
    finally:
        _safe_unlink(tmp)


@router.get("/import/logs")
def hr_import_logs(limit: int = Query(20, ge=1, le=100)):
    try:
        return hr.list_import_logs(limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("查询导入日志失败")
        raise HTTPException(status_code=500, detail=f"查询导入日志失败: {exc}") from exc


# ── 人力资源页面权限管理 ─────────────────────────────────────────────────────

def _require_admin_user(request: Request) -> dict[str, Any]:
    """权限管理后台：仅 sys_user.role 为 admin/管理员 可访问。"""
    user = _current_user(request)
    role = str(user.get("role") or "").strip().lower()
    if role not in {a.lower() for a in permission_service.ADMIN_ROLES}:
        raise HTTPException(status_code=403, detail="仅管理员可访问权限管理")
    return user


@router.get("/permission/my")
def hr_permission_my(request: Request):
    """当前登录用户对人力资源页面的可见性（供前端导航/页签过滤）。"""
    user = _current_user(request)
    role = str(user.get("role") or "").strip()
    is_admin = role.lower() in {a.lower() for a in permission_service.ADMIN_ROLES}
    engine = get_engine()
    personal_key = permission_service.legacy_name_if_unique(engine, str(user.get("real_name") or ""))
    account_key = "account:" + str(user.get("username") or "")
    # 新授权使用账号；仅对唯一姓名兼容历史个人授权。
    allowed = permission_service.allowed_page_keys(
        engine,
        role,
        personal_key,
        account_key,
    )
    # 页签级权限：页面内按 sub_key 返回当前用户可见的内容（如库存分析决策的页签）
    allowed_subpages: dict[str, list[str]] = {}
    for pk in permission_service.SUB_PERM_DEFS:
        allowed_subpages[pk] = permission_service.allowed_subpage_keys(
            engine, pk, role, personal_key, account_key,
        )
    return {
        "role": role,
        "is_admin": is_admin,
        "can_delete_design": permission_service.can_delete_design_item(user, engine),
        "allowed": allowed,
        "allowed_subpages": allowed_subpages,
    }


@router.get("/permission/pages")
def hr_permission_pages(request: Request):
    """管理后台：全部页面配置 + 页签级（内容）配置 + 可选角色/人员清单。"""
    _require_admin_user(request)
    engine = get_engine()
    perms = permission_service.get_page_permissions(engine)
    subperms = permission_service.get_subpage_permissions(engine)
    pages = []
    for key, label in permission_service.all_page_defs().items():
        found = next((p for p in perms if p["page_key"] == key), None)
        roles = found["roles"] if found else list(permission_service.PERM_DEFAULTS.get(key, ["admin", "hr"]))
        entry: dict[str, Any] = {
            "page_key": key,
            "label": label,
            "roles": roles,
        }
        subs = [s for s in subperms if s["page_key"] == key]
        if subs:
            sub_defs = permission_service.SUB_PERM_DEFS.get(key, {})
            entry["subpages"] = [
                {
                    "sub_key": s["sub_key"],
                    "label": sub_defs.get(s["sub_key"], s["sub_key"]),
                    "roles": s["roles"],
                }
                for s in subs
            ]
        pages.append(entry)
    return {
        "pages": pages,
        "roles": permission_service.get_all_roles(engine),
        "users": permission_service.get_all_users(engine),
        "subpages": subperms,
    }


@router.put("/permission/pages")
def hr_permission_update(request: Request, payload: dict = Body(...)):
    """管理后台：保存页面权限配置（updates）与页签级权限配置（sub_updates，可选）。"""
    _require_admin_user(request)
    engine = get_engine()
    updates = payload.get("updates")
    if not isinstance(updates, list):
        raise HTTPException(status_code=400, detail="updates 需为数组")
    pages = permission_service.save_page_permissions(engine, updates)
    subpages: list[dict[str, Any]] = []
    sub_updates = payload.get("sub_updates")
    if isinstance(sub_updates, list) and sub_updates:
        subpages = permission_service.save_subpage_permissions(engine, sub_updates)
    return {"ok": True, "pages": pages, "subpages": subpages}


# ── 模板生成 ──────────────────────────────────────────────────────────────────


def _build_simple_template(title: str, headers: list[str], sample_rows: list[list[Any]], filename: str) -> StreamingResponse:
    import io as _io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "模板"
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = Font(bold=True, color="ffffff")
        c.fill = PatternFill("solid", fgColor="0f766e")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for i, row in enumerate(sample_rows, start=2):
        for j, v in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=v)
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + col_idx)].width = 16
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
