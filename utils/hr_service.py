"""人力行政模块服务层（人力资源子模块）。

职责：
- 定义并创建仍在使用的 hr_* 表（与 database/migrations/20260825_create_hr_module_tables.sql 一致）；
- 统一脱敏（仅 admin/hr 可见敏感字段，其余角色一律掩码）；
- 花名册 / 离职 / 考勤 Excel 导入引擎（清洗 · 校验 · 幂等 · 报告）；
- 员工档案 CRUD、提醒中心、招聘管道与需求台账、考勤查询、
  驾驶舱聚合统计、导入日志。

设计约定：
- 幂等键 source_key（sheet:序号 / manual:xxx / upload:md5）唯一，重导更新不重复；
- 日期清洗统一 _parse_date；身份证统一 normalize_id_card（15→18、校验位、出生/性别）；
- 统计口径：离职率 = 期间离职人数 / 期初期末平均在册人数；到岗率 = 到岗+入职 / 录用；
  平均招聘周期 = 平均(入职日 - 首次面试日)。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    DECIMAL,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.engine import Engine

from utils.import_service import get_engine

LOGGER = logging.getLogger(__name__)

metadata = MetaData()

# ──────────────────────────────────────────────────────────────────────────────
# 表定义
# ──────────────────────────────────────────────────────────────────────────────

hr_employee = Table(
    "hr_employee", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_key", String(100), nullable=False, default=""),
    Column("emp_no", String(50), nullable=False, default=""),
    Column("name", String(50), nullable=False, default=""),
    Column("company", String(100), nullable=False, default="示例科技"),
    Column("contract_type", String(50), nullable=False, default=""),
    Column("dept_name", String(100), nullable=False, default=""),
    Column("group_name", String(100), nullable=False, default=""),
    Column("position", String(100), nullable=False, default=""),
    Column("hire_date", Date, nullable=True),
    Column("regular_date", Date, nullable=True),
    Column("seniority_text", String(50), nullable=False, default=""),
    Column("id_card", String(30), nullable=False, default=""),
    Column("id_card_hash", String(64), nullable=False, default=""),
    Column("id_card_expiry", Date, nullable=True),
    Column("birthday", Date, nullable=True),
    Column("gender", String(10), nullable=False, default=""),
    Column("nationality", String(20), nullable=False, default=""),
    Column("marital_status", String(20), nullable=False, default=""),
    Column("political_status", String(20), nullable=False, default=""),
    Column("phone", String(30), nullable=False, default=""),
    Column("email", String(100), nullable=False, default=""),
    Column("education", String(20), nullable=False, default=""),
    Column("is_fulltime", String(10), nullable=False, default=""),
    Column("school", String(100), nullable=False, default=""),
    Column("major", String(100), nullable=False, default=""),
    Column("cert_no", String(100), nullable=False, default=""),
    Column("grad_date", Date, nullable=True),
    Column("tech_title", String(100), nullable=False, default=""),
    Column("hukou_type", String(50), nullable=False, default=""),
    Column("native_place", String(100), nullable=False, default=""),
    Column("hukou_address", String(255), nullable=False, default=""),
    Column("id_address", String(255), nullable=False, default=""),
    Column("current_address", String(255), nullable=False, default=""),
    Column("bank_card", String(50), nullable=False, default=""),
    Column("bank_name", String(100), nullable=False, default=""),
    Column("has_social_insurance", String(10), nullable=False, default=""),
    Column("has_housing_fund", String(10), nullable=False, default=""),
    Column("fund_ratio", String(50), nullable=False, default=""),
    Column("remark", Text, nullable=True),
    Column("status", String(20), nullable=False, default="active"),
    Column("source_sheet", String(50), nullable=False, default=""),
    Column("source_row", Integer, nullable=True),
    Column("created_at", DateTime, nullable=True),
    Column("updated_at", DateTime, nullable=True),
)

hr_emergency_contact = Table(
    "hr_emergency_contact", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, nullable=False),
    Column("contact_name", String(50), nullable=False, default=""),
    Column("relation", String(20), nullable=False, default=""),
    Column("phone", String(30), nullable=False, default=""),
    Column("sort_no", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=True),
)

hr_contract = Table(
    "hr_contract", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, nullable=False),
    Column("contract_type", String(50), nullable=False, default=""),
    Column("seq_no", Integer, nullable=False, default=1),
    Column("start_date", Date, nullable=True),
    Column("end_date", Date, nullable=True),
    Column("note", String(255), nullable=False, default=""),
    Column("source_key", String(100), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
)

hr_resign = Table(
    "hr_resign", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_key", String(100), nullable=False, default=""),
    Column("name", String(50), nullable=False, default=""),
    Column("company", String(100), nullable=False, default="示例科技"),
    Column("contract_type", String(50), nullable=False, default=""),
    Column("dept_name", String(100), nullable=False, default=""),
    Column("group_name", String(100), nullable=False, default=""),
    Column("position", String(100), nullable=False, default=""),
    Column("hire_date", Date, nullable=True),
    Column("regular_date", Date, nullable=True),
    Column("resign_date", Date, nullable=True),
    Column("resign_reason", String(255), nullable=False, default=""),
    Column("id_card", String(30), nullable=False, default=""),
    Column("id_card_hash", String(64), nullable=False, default=""),
    Column("phone", String(30), nullable=False, default=""),
    Column("education", String(20), nullable=False, default=""),
    Column("source_sheet", String(50), nullable=False, default=""),
    Column("source_row", Integer, nullable=True),
    Column("created_at", DateTime, nullable=True),
)

hr_attendance_sum = Table(
    "hr_attendance_sum", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, nullable=True),
    Column("month", String(7), nullable=False, default=""),
    Column("name", String(50), nullable=False, default=""),
    Column("dept_name", String(100), nullable=False, default=""),
    Column("work_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("actual_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("late_count", Integer, nullable=False, default=0),
    Column("early_count", Integer, nullable=False, default=0),
    Column("absent_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("leave_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("overtime_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("abnormal_count", Integer, nullable=False, default=0),
    Column("remark", String(255), nullable=False, default=""),
    # ── 每日明细聚合补齐：异常/缺卡/加班明细 ─────────────────────
    Column("makeup_count", Integer, nullable=False, default=0),
    Column("on_missing_count", Integer, nullable=False, default=0),
    Column("off_missing_count", Integer, nullable=False, default=0),
    Column("serious_late_count", Integer, nullable=False, default=0),
    Column("late_minutes", Integer, nullable=False, default=0),
    Column("early_minutes", Integer, nullable=False, default=0),
    # ── 汇总表扩展：组织与在职信息 ──────────────────────────────
    Column("company", String(50), nullable=False, default=""),
    Column("dept1", String(100), nullable=False, default=""),   # 一级部门
    Column("dept2", String(100), nullable=False, default=""),   # 二级部门
    Column("dept3", String(100), nullable=False, default=""),   # 三级部门
    Column("position", String(100), nullable=False, default=""),
    Column("hire_date", Date, nullable=True),
    Column("resign_date", Date, nullable=True),
    # ── 汇总表扩展：计薪 / 出勤天数 ────────────────────────────
    Column("paid_days", DECIMAL(6, 2), nullable=False, default=0),        # 应计薪天数
    Column("actual_paid_days", DECIMAL(6, 2), nullable=False, default=0),  # 实际计薪天数
    Column("legal_holidays", DECIMAL(6, 2), nullable=False, default=0),    # 当月法定节假日
    Column("shift_extra_days", DECIMAL(6, 2), nullable=False, default=0),  # 通班加算出勤天
    Column("hire_resign_diff", DECIMAL(6, 2), nullable=False, default=0),  # 入离职时间差
    # ── 汇总表扩展：带薪休假（天） ─────────────────────────────
    Column("annual_leave", DECIMAL(6, 2), nullable=False, default=0),      # 年假
    Column("comp_leave", DECIMAL(6, 2), nullable=False, default=0),        # 调休
    Column("maternity_leave", DECIMAL(6, 2), nullable=False, default=0),   # 产假
    Column("paternity_leave", DECIMAL(6, 2), nullable=False, default=0),   # 陪产假
    Column("prenatal_leave", DECIMAL(6, 2), nullable=False, default=0),    # 产检假/哺乳假
    Column("marriage_leave", DECIMAL(6, 2), nullable=False, default=0),    # 婚假
    Column("funeral_leave", DECIMAL(6, 2), nullable=False, default=0),     # 丧假
    Column("sick_days", DECIMAL(6, 2), nullable=False, default=0),         # 病假
    Column("personal_days", DECIMAL(6, 2), nullable=False, default=0),     # 事假
    Column("absent_work_days", DECIMAL(6, 2), nullable=False, default=0),  # 旷工（天）
    # ── 汇总表扩展：需支付 / 异常情况 ───────────────────────────
    Column("sick_wage", DECIMAL(8, 2), nullable=False, default=0),         # 病假工资
    Column("late_penalty", DECIMAL(8, 2), nullable=False, default=0),      # 迟到负激励
    Column("early_penalty", DECIMAL(8, 2), nullable=False, default=0),     # 早退负激励
    Column("makeup_penalty", DECIMAL(8, 2), nullable=False, default=0),    # 补卡负激励
    Column("comp_days_extra", DECIMAL(6, 2), nullable=False, default=0),   # 本月多上，后可调休
    Column("source_key", String(100), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
    Column("updated_at", DateTime, nullable=True),
)

# 考勤每日明细（对应《每日统计》表）
hr_attendance_detail = Table(
    "hr_attendance_detail", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, nullable=True),
    Column("month", String(7), nullable=False, default=""),
    Column("name", String(50), nullable=False, default=""),
    Column("dept_name", String(100), nullable=False, default=""),
    Column("position", String(100), nullable=False, default=""),
    Column("work_date", Date, nullable=True),
    Column("weekday", String(20), nullable=False, default=""),
    Column("on_time", String(20), nullable=False, default=""),
    Column("on_result", String(50), nullable=False, default=""),
    Column("on_location", String(255), nullable=False, default=""),
    Column("off_time", String(20), nullable=False, default=""),
    Column("off_result", String(50), nullable=False, default=""),
    Column("off_location", String(255), nullable=False, default=""),
    # 出勤统计
    Column("work_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("work_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("rest_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("actual_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("actual_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("shift_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("business_days", DECIMAL(6, 2), nullable=False, default=0),
    Column("outing_hours", DECIMAL(6, 2), nullable=False, default=0),
    # 异常统计
    Column("makeup_count", Integer, nullable=False, default=0),
    Column("late_count", Integer, nullable=False, default=0),
    Column("late_minutes", Integer, nullable=False, default=0),
    Column("serious_late_count", Integer, nullable=False, default=0),
    Column("serious_late_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("early_count", Integer, nullable=False, default=0),
    Column("early_minutes", Integer, nullable=False, default=0),
    Column("absent_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("on_missing_count", Integer, nullable=False, default=0),
    Column("off_missing_count", Integer, nullable=False, default=0),
    Column("absentee_days", DECIMAL(6, 2), nullable=False, default=0),
    # 加班统计
    Column("overtime_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("overtime_paid_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("overtime_comp_hours", DECIMAL(6, 2), nullable=False, default=0),
    Column("source_key", String(120), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
    Column("updated_at", DateTime, nullable=True),
)

# 迟到明细（对应《迟到》表）
hr_attendance_late = Table(
    "hr_attendance_late", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("month", String(7), nullable=False, default=""),
    Column("employee_id", Integer, nullable=True),
    Column("name", String(50), nullable=False, default=""),
    Column("late_date", Date, nullable=True),
    Column("late_time", String(20), nullable=False, default=""),
    Column("penalty_amount", DECIMAL(8, 1), nullable=False, default=0),
    Column("source_key", String(120), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
)

# 请假明细（对应《请假》表）
hr_attendance_leave = Table(
    "hr_attendance_leave", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("month", String(7), nullable=False, default=""),
    Column("employee_id", Integer, nullable=True),
    Column("name", String(50), nullable=False, default=""),
    Column("leave_type", String(30), nullable=False, default=""),
    Column("reason", String(255), nullable=False, default=""),
    Column("start_time", String(40), nullable=False, default=""),
    Column("end_time", String(40), nullable=False, default=""),
    Column("hours", DECIMAL(6, 1), nullable=False, default=0),
    Column("days", DECIMAL(6, 1), nullable=False, default=0),
    Column("source_key", String(120), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
)

# 补卡明细（对应《补卡》表）
hr_attendance_makeup = Table(
    "hr_attendance_makeup", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("month", String(7), nullable=False, default=""),
    Column("employee_id", Integer, nullable=True),
    Column("name", String(50), nullable=False, default=""),
    Column("reason", String(255), nullable=False, default=""),
    Column("makeup_date", Date, nullable=True),
    Column("makeup_time", String(20), nullable=False, default=""),
    Column("penalty_amount", DECIMAL(8, 1), nullable=False, default=0),
    Column("source_key", String(120), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
)

hr_import_log = Table(
    "hr_import_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("import_type", String(50), nullable=False, default=""),
    Column("filename", String(255), nullable=False, default=""),
    Column("sheet_name", String(50), nullable=False, default=""),
    Column("rows_read", Integer, nullable=False, default=0),
    Column("inserted", Integer, nullable=False, default=0),
    Column("updated", Integer, nullable=False, default=0),
    Column("skipped", Integer, nullable=False, default=0),
    Column("errors_json", Text, nullable=True),
    Column("operator", String(50), nullable=False, default=""),
    Column("created_at", DateTime, nullable=True),
)

_SENSITIVE_FIELDS = ("id_card", "bank_card", "phone", "hukou_address", "id_address", "current_address")

# ──────────────────────────────────────────────────────────────────────────────
# 基础工具
# ──────────────────────────────────────────────────────────────────────────────


def ensure_tables(engine: Optional[Engine] = None) -> None:
    """确保所有 hr_* 表存在（CREATE TABLE IF NOT EXISTS 语义）。"""
    engine = engine or get_engine()
    metadata.create_all(engine)
    _migrate_attendance_tables(engine)


# 老库升级：为已存在的 hr_attendance_sum 补充 2026-09 新增列（幂等）
_ATT_SUM_NEW_COLUMNS: list[tuple[str, str]] = [
    ("company", "VARCHAR(50) NOT NULL DEFAULT ''"),
    ("dept1", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("dept2", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("dept3", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("position", "VARCHAR(100) NOT NULL DEFAULT ''"),
    ("hire_date", "DATE NULL"),
    ("resign_date", "DATE NULL"),
    ("paid_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("actual_paid_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("legal_holidays", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("shift_extra_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("hire_resign_diff", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("annual_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("comp_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("maternity_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("paternity_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("prenatal_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("marriage_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("funeral_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("sick_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("personal_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("absent_work_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("sick_wage", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("late_penalty", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("early_penalty", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("makeup_penalty", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("comp_days_extra", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("makeup_count", "INTEGER NOT NULL DEFAULT 0"),
    ("on_missing_count", "INTEGER NOT NULL DEFAULT 0"),
    ("off_missing_count", "INTEGER NOT NULL DEFAULT 0"),
    ("serious_late_count", "INTEGER NOT NULL DEFAULT 0"),
    ("late_minutes", "INTEGER NOT NULL DEFAULT 0"),
    ("early_minutes", "INTEGER NOT NULL DEFAULT 0"),
]

# 老库升级：数值列统一精度 2 位小数（0.31 / 1.24 / 23.76 等），幂等
_ATT_SUM_MODIFY_COLUMNS: list[tuple[str, str]] = [
    ("work_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("actual_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("absent_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("leave_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("overtime_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("paid_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("actual_paid_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("legal_holidays", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("shift_extra_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("hire_resign_diff", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("annual_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("comp_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("maternity_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("paternity_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("prenatal_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("marriage_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("funeral_leave", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("sick_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("personal_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("absent_work_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("comp_days_extra", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("sick_wage", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("late_penalty", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("early_penalty", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
    ("makeup_penalty", "DECIMAL(8,2) NOT NULL DEFAULT 0"),
]

# 每日明细表数值列精度修正
_ATT_DETAIL_MODIFY_COLUMNS: list[tuple[str, str]] = [
    ("work_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("work_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("rest_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("actual_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("actual_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("shift_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("business_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("outing_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("serious_late_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("absent_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("absentee_days", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("overtime_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("overtime_paid_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
    ("overtime_comp_hours", "DECIMAL(6,2) NOT NULL DEFAULT 0"),
]


def _migrate_attendance_tables(engine: Engine) -> None:
    """为已存在的考勤表补充新增列 / 修正精度（CREATE TABLE 不会修改既有表）。"""
    try:
        from sqlalchemy import inspect

        insp = inspect(engine)
        if insp.has_table("hr_attendance_sum"):
            existing = {c["name"] for c in insp.get_columns("hr_attendance_sum")}
            with engine.begin() as conn:
                for name, col_sql in _ATT_SUM_NEW_COLUMNS:
                    if name not in existing:
                        conn.execute(text(f"ALTER TABLE hr_attendance_sum ADD COLUMN {name} {col_sql}"))
                for name, col_sql in _ATT_SUM_MODIFY_COLUMNS:
                    if name in existing:
                        conn.execute(text(f"ALTER TABLE hr_attendance_sum MODIFY COLUMN {name} {col_sql}"))
        if insp.has_table("hr_attendance_detail"):
            existing = {c["name"] for c in insp.get_columns("hr_attendance_detail")}
            with engine.begin() as conn:
                for name, col_sql in _ATT_DETAIL_MODIFY_COLUMNS:
                    if name in existing:
                        conn.execute(text(f"ALTER TABLE hr_attendance_detail MODIFY COLUMN {name} {col_sql}"))
    except Exception as exc:  # 迁移失败不阻断启动，后续查询兜底
        LOGGER.warning("考勤表结构迁移失败: %s", exc)


def _now() -> _dt.datetime:
    return _dt.datetime.now()


def _iso(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    return str(v)


def _d(v: Any) -> Optional[_dt.date]:
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return None


def _clean_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip().replace("\n", " ").replace("\r", " ")


def _clean_int(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group(0)) if m else 0


def _clean_decimal(v: Any) -> Decimal:
    """数值清洗：去掉单位/汉字，转 Decimal（非法返回 0）。"""
    if v is None:
        return Decimal("0")
    if isinstance(v, (int, float, Decimal)):
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return Decimal(m.group(0)) if m else Decimal("0")


def _parse_date(v: Any) -> Optional[_dt.date]:
    """宽松日期解析：datetime/date/多种字符串格式。失败返回 None。"""
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = _clean_str(v)
    if not s:
        return None
    if s in ("长期", "至今", "-", "--"):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日", "%Y-%m", "%Y/%m"):
        try:
            return _dt.datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})?", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
        except ValueError:
            return None
    return None


# ── 身份证 ────────────────────────────────────────────────────────────────────

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK = ["1", "0", "X", "9", "8", "7", "6", "5", "4", "3", "2"]


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def normalize_id_card(raw: Any) -> dict[str, Any]:
    """身份证标准化。

    返回 {value, birthday, gender, valid, message}
    - 15 位自动升 18 位；18 位校验校验位；出生日期与性别（第 17 位奇男偶女）提取。
    """
    s = _clean_str(raw).upper()
    out = {"value": s, "birthday": None, "gender": "", "valid": True, "message": ""}
    if not s:
        return out
    if len(s) == 15 and s.isdigit():
        s = s[:6] + "19" + s[6:]
        # 补校验位
        total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
        s += _ID_CHECK[total % 11]
        out["value"] = s
    if not re.match(r"^\d{17}[\dX]$", s):
        out["valid"] = False
        out["message"] = "身份证位数或格式不正确"
        return out
    total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
    if _ID_CHECK[total % 11] != s[17]:
        out["valid"] = False
        out["message"] = "身份证校验位错误"
        return out
    try:
        out["birthday"] = _dt.date(int(s[6:10]), int(s[10:12]), int(s[12:14]))
    except ValueError:
        out["valid"] = False
        out["message"] = "身份证出生日期非法"
        return out
    out["gender"] = "男" if int(s[16]) % 2 == 1 else "女"
    return out


# ── 脱敏 ──────────────────────────────────────────────────────────────────────


def _mask_id_card(v: str) -> str:
    return (v[:6] + "******" + v[-4:]) if len(v) >= 10 else ("****" if v else "")


def _mask_bank_card(v: str) -> str:
    return ("**** " + v[-4:]) if len(v) >= 4 else ("****" if v else "")


def _mask_phone(v: str) -> str:
    s = _clean_str(v)
    return (s[:3] + "****" + s[-4:]) if len(s) >= 7 else ("****" if s else "")


def _mask_address(v: str) -> str:
    """住址仅保留到市/区/县一级。"""
    s = _clean_str(v)
    if not s:
        return ""
    m = re.match(r"^.{1,40}?(市|区|县)", s)
    if m:
        return m.group(0)
    return s[:6] + "…" if len(s) > 6 else s


def mask_sensitive(row: dict[str, Any], can_view_all: bool = False) -> dict[str, Any]:
    """按角色脱敏。can_view_all（admin/hr）时返回原样，否则掩码敏感字段。"""
    if can_view_all:
        return row
    out = dict(row)
    if row.get("id_card"):
        out["id_card"] = _mask_id_card(row["id_card"])
    if row.get("bank_card"):
        out["bank_card"] = _mask_bank_card(row["bank_card"])
    if row.get("phone"):
        out["phone"] = _mask_phone(row["phone"])
    for f in ("hukou_address", "id_address", "current_address"):
        if row.get(f):
            out[f] = _mask_address(row[f])
    return out


def mask_sensitive_list(rows: list[dict[str, Any]], can_view_all: bool = False) -> list[dict[str, Any]]:
    return [mask_sensitive(r, can_view_all) for r in rows]


# ── 序列化 ────────────────────────────────────────────────────────────────────


def _serialize_row(row: dict[str, Any], fields: Optional[list[str]] = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if fields is not None and k not in fields:
            continue
        if isinstance(v, (_dt.datetime, _dt.date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 花名册导入（员工主档 + 合同 + 紧急联系人）
# ──────────────────────────────────────────────────────────────────────────────

# 员工花名册工作表按列字母的固定字段映射（已实测核对 48 列）
ROSTER_COL_MAP = {
    "A": ("seq", "int"), "B": ("company", "str"), "C": ("contract_type", "str"),
    "D": ("dept_name", "str"), "E": ("group_name", "str"), "F": ("name", "str"),
    "G": ("position", "str"), "H": ("hire_date", "date"), "I": ("regular_date", "date"),
    "J": ("seniority_text", "str"), "K": ("id_card", "idcard"), "L": ("id_card_expiry", "date"),
    "M": ("birthday", "date"), "N": ("birth_month", "str"), "O": ("gender", "str"),
    "P": ("age_raw", "str"), "Q": ("nationality", "str"), "R": ("marital_status", "str"),
    "S": ("political_status", "str"), "T": ("phone", "str"), "U": ("email", "str"),
    "V": ("education", "str"), "W": ("is_fulltime", "str"), "X": ("school", "str"),
    "Y": ("major", "str"), "Z": ("cert_no", "str"), "AA": ("grad_date", "date"),
    "AB": ("tech_title", "str"), "AC": ("hukou_type", "str"), "AD": ("native_place", "str"),
    "AE": ("hukou_address", "str"), "AF": ("id_address", "str"), "AG": ("current_address", "str"),
    "AH": ("bank_card", "str"), "AI": ("bank_name", "str"), "AJ": ("has_social_insurance", "str"),
    "AK": ("has_housing_fund", "str"), "AL": ("fund_ratio", "str"),
    "AM": ("emg_name", "str"), "AN": ("emg_relation", "str"), "AO": ("emg_phone", "str"),
    "AP": ("contract1_start", "date"), "AQ": ("contract1_end", "date"),
    "AR": ("contract2_start", "date"), "AS": ("contract2_end", "date"),
    "AT": ("contract3_start", "date"), "AU": ("contract3_end", "date"),
    "AV": ("remark", "str"),
}

# 离职表字段：按表头关键字匹配（名称/部门/岗位/日期/原因等）
RESIGN_HEADER_KEYWORDS = {
    "序号": "seq", "所属公司": "company", "合同类型": "contract_type", "部门": "dept_name",
    "组别": "group_name", "姓名": "name", "岗位": "position", "入职日期": "hire_date",
    "转正": "regular_date", "工龄": "seniority_text", "离职日期": "resign_date",
    "离职原因": "resign_reason", "身份证": "id_card", "电话": "phone", "学历": "education",
}


def _clean_geo(v: str) -> str:
    """籍贯只保留最上级行政区。"""
    s = _clean_str(v)
    if not s:
        return ""
    m = re.match(r"^.{0,20}?(省|自治区|市)", s)
    return m.group(0) if m else s


def _read_headers_merge(ws) -> dict[str, str]:
    """读取双层表头形成 letter(2位) -> 表头文本 的字典。"""
    import openpyxl

    cols: dict[str, str] = {}
    for col_idx in range(1, ws.max_column + 1):
        letter = openpyxl.utils.get_column_letter(col_idx)
        h1 = _clean_str(ws.cell(row=1, column=col_idx).value)
        h2 = _clean_str(ws.cell(row=2, column=col_idx).value)
        cols[letter] = (h2 or h1)
    return cols


def import_roster_workbook(path: str, operator: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """导入《员工花名册.xlsx》的员工花名册工作表 → hr_employee/hr_contract/hr_emergency_contact。

    幂等：source_key = f"员工花名册:{seq}"，存在则更新。
    """
    import openpyxl

    ensure_tables(engine)
    engine = engine or get_engine()
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["员工花名册"]

    report = {"rows_read": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": []}

    for r in range(3, ws.max_row + 1):
        raw: dict[str, Any] = {}
        for letter, (field, kind) in ROSTER_COL_MAP.items():
            cell = ws.cell(row=r, column=openpyxl.utils.column_index_from_string(letter))
            v = cell.value
            if kind == "date":
                raw[field] = _parse_date(v)
            elif kind == "int":
                raw[field] = _clean_int(v)
            elif kind == "idcard":
                raw[field] = _clean_str(v)
            else:
                raw[field] = _clean_str(v)
        report["rows_read"] += 1

        name = raw.get("name", "")
        if not name:
            report["skipped"] += 1
            report["errors"].append({"row": r, "field": "name", "level": "error", "message": "姓名为空，跳过"})
            continue

        source_key = f"员工花名册:{raw.get('seq', r)}"
        idc = normalize_id_card(raw.get("id_card", ""))
        row_err: list[dict[str, Any]] = []
        if raw.get("id_card") and not idc["valid"]:
            row_err.append({"row": r, "field": "id_card", "level": "warning", "message": idc["message"] + "，已保留原值"})

        hire = raw.get("hire_date")
        regular = raw.get("regular_date")
        birthday = raw.get("birthday") or idc["birthday"]
        gender = raw.get("gender", "") or idc["gender"]

        emp = {
            "source_key": source_key,
            "emp_no": f"EMP{raw.get('seq', r):04d}",
            "name": name,
            "company": raw.get("company", "") or infer_company_from_dept(raw.get("dept_name", "")),
            "contract_type": raw.get("contract_type", ""),
            "dept_name": raw.get("dept_name", ""),
            "group_name": "" if raw.get("group_name", "") in ("", "/") else raw.get("group_name", ""),
            "position": raw.get("position", ""),
            "hire_date": hire,
            "regular_date": regular,
            "seniority_text": raw.get("seniority_text", ""),
            "id_card": idc["value"],
            "id_card_hash": _sha256(idc["value"]) if idc["value"] else "",
            "id_card_expiry": raw.get("id_card_expiry"),
            "birthday": birthday,
            "gender": gender,
            "nationality": raw.get("nationality", ""),
            "marital_status": raw.get("marital_status", ""),
            "political_status": raw.get("political_status", ""),
            "phone": raw.get("phone", ""),
            "email": raw.get("email", "").lower(),
            "education": raw.get("education", ""),
            "is_fulltime": raw.get("is_fulltime", ""),
            "school": raw.get("school", ""),
            "major": raw.get("major", ""),
            "cert_no": raw.get("cert_no", ""),
            "grad_date": raw.get("grad_date"),
            "tech_title": raw.get("tech_title", ""),
            "hukou_type": raw.get("hukou_type", ""),
            "native_place": _clean_geo(raw.get("native_place", "")),
            "hukou_address": raw.get("hukou_address", ""),
            "id_address": raw.get("id_address", ""),
            "current_address": raw.get("current_address", ""),
            "bank_card": raw.get("bank_card", ""),
            "bank_name": raw.get("bank_name", ""),
            "has_social_insurance": raw.get("has_social_insurance", ""),
            "has_housing_fund": raw.get("has_housing_fund", ""),
            "fund_ratio": raw.get("fund_ratio", ""),
            "remark": raw.get("remark", ""),
            "status": "active",
            "source_sheet": "员工花名册",
            "source_row": r,
        }
        contracts = []
        for seq, (s_key, e_key) in (
            (1, ("contract1_start", "contract1_end")),
            (2, ("contract2_start", "contract2_end")),
            (3, ("contract3_start", "contract3_end")),
        ):
            s, e = raw.get(s_key), raw.get(e_key)
            if s or e:
                contracts.append({"seq_no": seq, "start_date": s, "end_date": e})
        contacts = []
        if raw.get("emg_name") or raw.get("emg_phone"):
            contacts.append({
                "sort_no": 1, "contact_name": raw.get("emg_name", ""),
                "relation": raw.get("emg_relation", ""), "phone": raw.get("emg_phone", ""),
            })

        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM hr_employee WHERE source_key = :sk LIMIT 1"), {"sk": source_key}
            ).scalar_one_or_none()
            if existing is not None:
                _upd = {k: v for k, v in emp.items() if k != "source_key"}
                conn.execute(
                    hr_employee.update().where(hr_employee.c.id == existing), _upd
                )
                conn.execute(text("DELETE FROM hr_contract WHERE employee_id = :eid"), {"eid": existing})
                conn.execute(text("DELETE FROM hr_emergency_contact WHERE employee_id = :eid"), {"eid": existing})
                report["updated"] += 1
            else:
                ins = conn.execute(hr_employee.insert(), emp)
                existing = ins.inserted_primary_key[0]
                report["inserted"] += 1
            for i, c in enumerate(contracts):
                conn.execute(hr_contract.insert(), {
                    "employee_id": existing, "contract_type": f"contract_{c['seq_no']}",
                    "seq_no": c["seq_no"], "start_date": c["start_date"], "end_date": c["end_date"],
                    "note": "", "source_key": f"{source_key}:contract:{c['seq_no']}",
                    "created_at": _now(),
                })
            for i, ct in enumerate(contacts):
                conn.execute(hr_emergency_contact.insert(), {
                    "employee_id": existing, "contact_name": ct["contact_name"],
                    "relation": ct["relation"], "phone": ct["phone"],
                    "sort_no": ct["sort_no"], "created_at": _now(),
                })
        report["errors"].extend(row_err)

    _log_import(engine, "roster", path, "员工花名册", report, operator)
    report["message"] = (
        f"导入完成：读取 {report['rows_read']} 行，新增 {report['inserted']}，"
        f"更新 {report['updated']}，跳过 {report['skipped']}，警告 {len(report['errors'])} 条"
    )
    return report


def import_resign_workbook(path: str, operator: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """导入离职工作表（离职员工 / 2024年5月前离职人员）→ hr_resign。"""
    import openpyxl

    ensure_tables(engine)
    engine = engine or get_engine()
    wb = openpyxl.load_workbook(path, data_only=True)

    report = {"rows_read": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": []}
    for sheet_name in ("离职员工", "2024年5月前离职人员"):
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        headers = _read_headers_merge(ws)
        col_of: dict[str, str] = {}
        for letter, h in headers.items():
            for kw, field in RESIGN_HEADER_KEYWORDS.items():
                if kw in h and field not in col_of:
                    col_of[field] = letter
        for r in range(3, ws.max_row + 1):
            def cell(field: str) -> Any:
                letter = col_of.get(field)
                if not letter:
                    return None
                return ws.cell(row=r, column=openpyxl.utils.column_index_from_string(letter)).value

            report["rows_read"] += 1
            seq = _clean_int(cell("seq"))
            name = _clean_str(cell("name"))
            if not name:
                report["skipped"] += 1
                report["errors"].append({"row": r, "field": "name", "level": "error", "message": "姓名为空，跳过"})
                continue
            idc = normalize_id_card(cell("id_card"))
            source_key = f"{sheet_name}:{seq or r}"
            resign = {
                "source_key": source_key,
                "name": name,
                "company": cell("company") or infer_company_from_dept(cell("dept_name")),
                "contract_type": cell("contract_type") or "",
                "dept_name": cell("dept_name") or "",
                "group_name": cell("group_name") or "",
                "position": cell("position") or "",
                "hire_date": _parse_date(cell("hire_date")),
                "regular_date": _parse_date(cell("regular_date")),
                "resign_date": _parse_date(cell("resign_date")),
                "resign_reason": _clean_str(cell("resign_reason")),
                "id_card": idc["value"],
                "id_card_hash": _sha256(idc["value"]) if idc["value"] else "",
                "phone": _clean_str(cell("phone")),
                "education": _clean_str(cell("education")),
                "source_sheet": sheet_name,
                "source_row": r,
                "created_at": _now(),
            }
            with engine.begin() as conn:
                existing = conn.execute(
                    text("SELECT id FROM hr_resign WHERE source_key = :sk LIMIT 1"), {"sk": source_key}
                ).scalar_one_or_none()
                if existing is not None:
                    conn.execute(hr_resign.update().where(hr_resign.c.id == existing), resign)
                    report["updated"] += 1
                else:
                    conn.execute(hr_resign.insert(), resign)
                    report["inserted"] += 1
            if cell("id_card") and not idc["valid"]:
                report["errors"].append({"row": r, "field": "id_card", "level": "warning", "message": idc["message"]})

    _log_import(engine, "resign", path, "离职表", report, operator)
    report["message"] = (
        f"离职表导入完成：读取 {report['rows_read']} 行，新增 {report['inserted']}，"
        f"更新 {report['updated']}，跳过 {report['skipped']}"
    )
    return report


def _log_import(engine: Engine, import_type: str, filename: str, sheet: str,
                report: dict[str, Any], operator: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(hr_import_log.insert(), {
                "import_type": import_type, "filename": filename, "sheet_name": sheet,
                "rows_read": int(report.get("rows_read", 0)),
                "inserted": int(report.get("inserted", 0)),
                "updated": int(report.get("updated", 0)),
                "skipped": int(report.get("skipped", 0)),
                "errors_json": json.dumps(report.get("errors", []), ensure_ascii=False),
                "operator": operator, "created_at": _now(),
            })
    except Exception as exc:  # 日志失败不阻断导入
        LOGGER.warning("写入导入日志失败: %s", exc)


def list_import_logs(limit: int = 20, engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, import_type, filename, sheet_name, rows_read, inserted, updated, "
                "skipped, errors_json, operator, created_at FROM hr_import_log "
                "ORDER BY id DESC LIMIT :lim"
            ),
            {"lim": max(1, min(limit, 100))},
        ).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["created_at"] = _iso(d.get("created_at"))
        d["errors"] = json.loads(d.pop("errors_json") or "[]")
        out.append(d)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 员工档案 CRUD
# ──────────────────────────────────────────────────────────────────────────────

_EMPLOYEE_FIELDS = tuple(col.name for col in hr_employee.columns)  # 用于序列化白名单


def infer_company_from_dept(dept_name: str) -> str:
    """按部门推断所属公司。

    业务口径：兴趣电商部隶属示例传媒；其余部门均默认隶属示例科技。
    花名册导入/手动建档时若未指定公司，按此规则回填，保证公司与部门一一对应。
    """
    if not dept_name:
        return "示例科技"
    s = str(dept_name).strip()
    if s == "兴趣电商部":
        return "示例传媒"
    return "示例科技"


def list_employees(
    keyword: str = "",
    dept: str = "",
    status: str = "active",
    education: str = "",
    company: str = "",
    page: int = 1,
    page_size: int = 20,
    can_view_all: bool = False,
    engine: Optional[Engine] = None,
) -> dict[str, Any]:
    ensure_tables(engine)
    engine = engine or get_engine()
    where = ["1=1"]
    params: dict[str, Any] = {}
    if keyword:
        where.append("(name LIKE :kw OR position LIKE :kw OR emp_no LIKE :kw OR phone LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    if dept:
        where.append("dept_name = :dept")
        params["dept"] = dept
    if status:
        where.append("status = :status")
        params["status"] = status
    if education:
        where.append("education = :edu")
        params["edu"] = education
    if company:
        where.append("company = :company")
        params["company"] = company
    _where = " AND ".join(where)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM hr_employee WHERE {_where}"), params).scalar()
        rows = conn.execute(
            text(f"SELECT * FROM hr_employee WHERE {_where} ORDER BY id LIMIT :lim OFFSET :off"),
            {**params, "lim": page_size, "off": offset},
        ).mappings().all()
    items = [mask_sensitive(_serialize_row(dict(r)), can_view_all) for r in rows]
    return {"total": int(total or 0), "page": page, "page_size": page_size, "items": items}


def get_employee_detail(employee_id: int, can_view_all: bool = False, engine: Optional[Engine] = None) -> dict[str, Any]:
    ensure_tables(engine)
    engine = engine or get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM hr_employee WHERE id = :id LIMIT 1"), {"id": employee_id}
        ).mappings().one_or_none()
        if row is None:
            raise KeyError("员工不存在")
        contracts = conn.execute(
            text("SELECT seq_no, contract_type, start_date, end_date, note FROM hr_contract WHERE employee_id = :id ORDER BY seq_no"),
            {"id": employee_id},
        ).mappings().all()
        contacts = conn.execute(
            text("SELECT sort_no, contact_name, relation, phone FROM hr_emergency_contact WHERE employee_id = :id ORDER BY sort_no"),
            {"id": employee_id},
        ).mappings().all()
    emp = mask_sensitive(_serialize_row(dict(row)), can_view_all)
    emp["contracts"] = [_serialize_row(dict(c)) for c in contracts]
    emp["emergency_contacts"] = []
    for c in contacts:
        _ct = dict(c)
        if not can_view_all:
            _ct["phone"] = _mask_phone(_ct.get("phone", ""))
        emp["emergency_contacts"].append(_serialize_row(_ct))
    return emp


# 系统内维护：manual:{秒级时间戳}:{uuid短串} 生成幂等键
def _manual_source_key() -> str:
    import uuid
    return f"manual:{int(_dt.datetime.now().timestamp() * 1000)}:{uuid.uuid4().hex[:8]}"


def save_employee(payload: dict[str, Any], engine: Optional[Engine] = None) -> dict[str, Any]:
    """新增/更新员工。payload 含 id（更新）或全字段（新增），source_key 缺省自动生成。"""
    ensure_tables(engine)
    engine = engine or get_engine()
    employee_id = payload.get("id")
    data = {k: payload.get(k) for k in _EMPLOYEE_FIELDS if k in payload}
    for date_field in ("hire_date", "regular_date", "id_card_expiry", "birthday", "grad_date"):
        if date_field in data and data[date_field]:
            data[date_field] = _parse_date(data[date_field])
    idc_raw = _clean_str(payload.get("id_card", ""))
    if idc_raw:
        idc = normalize_id_card(idc_raw)
        data["id_card"] = idc["value"]
        data["id_card_hash"] = _sha256(idc["value"])
        if not data.get("birthday"):
            data["birthday"] = idc["birthday"]
        if not data.get("gender"):
            data["gender"] = idc["gender"]
    if "remark" in payload:
        data["remark"] = _clean_str(payload.get("remark"))
    if "source_key" not in data or not data.get("source_key"):
        data["source_key"] = _manual_source_key()
    data.setdefault("status", "active")
    # 公司缺省时按部门推断：兴趣电商部 → 示例传媒；其它 → 示例科技
    if not _clean_str(data.get("company")):
        data["company"] = infer_company_from_dept(data.get("dept_name", ""))

    with engine.begin() as conn:
        if employee_id:
            conn.execute(
                hr_employee.update().where(hr_employee.c.id == employee_id),
                {k: v for k, v in data.items() if k != "id"},
            )
        else:
            ins = conn.execute(hr_employee.insert(), data)
            employee_id = ins.inserted_primary_key[0]
    return _serialize_row({"id": employee_id, **data})


def delete_employee(employee_id: int, hard: bool = False, engine: Optional[Engine] = None) -> dict[str, Any]:
    ensure_tables(engine)
    engine = engine or get_engine()
    with engine.begin() as conn:
        if hard:
            conn.execute(hr_employee.delete().where(hr_employee.c.id == employee_id))
            conn.execute(text("DELETE FROM hr_contract WHERE employee_id = :id"), {"id": employee_id})
            conn.execute(text("DELETE FROM hr_emergency_contact WHERE employee_id = :id"), {"id": employee_id})
        else:
            conn.execute(
                hr_employee.update().where(hr_employee.c.id == employee_id),
                {"status": "resigned", "updated_at": _now()},
            )
    return {"deleted": int(employee_id)}


# ──────────────────────────────────────────────────────────────────────────────
# 提醒中心
# ──────────────────────────────────────────────────────────────────────────────

class _ReminderItem:
    kind: str
    title: str
    days: Optional[int]
    employee_id: int
    name: str


def build_reminders(
    engine: Optional[Engine] = None,
    today: Optional[_dt.date] = None,
) -> dict[str, Any]:
    """提醒中心：合同到期 / 转正 / 试用期到期 / 生日当月 / 证件有效期到期。"""
    ensure_tables(engine)
    engine = engine or get_engine()
    today = today or _dt.date.today()
    soon = today + _dt.timedelta(days=90)

    reminders: dict[str, list[dict[str, Any]]] = {
        "contract_expiry": [], "regular_upcoming": [], "probation_expiry": [],
        "birthday": [], "id_card_expiry": [], "probation_overdue": [],
    }
    with engine.connect() as conn:
        emp_rows = conn.execute(
            text("SELECT id, name, dept_name, position, hire_date, regular_date, birthday, id_card_expiry FROM hr_employee WHERE status = 'active'")
        ).mappings().all()
        contracts = conn.execute(
            text(
                "SELECT c.employee_id, e.name, e.dept_name, e.position, c.seq_no, c.end_date "
                "FROM hr_contract c JOIN hr_employee e ON e.id = c.employee_id "
                "WHERE e.status = 'active' AND c.end_date IS NOT NULL AND c.end_date >= :today "
                "AND c.end_date <= :soon ORDER BY c.end_date"
            ),
            {"today": today, "soon": soon},
        ).mappings().all()

    for c in contracts:
        end = _d(c["end_date"])
        days = (end - today).days if end else 0
        reminders["contract_expiry"].append({
            "employee_id": c["employee_id"], "name": c["name"],
            "dept": c["dept_name"], "position": c["position"],
            "seq": c["seq_no"], "end_date": _iso(end), "days_left": days,
            "level": "danger" if days <= 30 else "warning",
        })

    for e in emp_rows:
        name = e["name"]
        if e["regular_date"]:
            rd = _d(e["regular_date"])
            if rd and today <= rd <= soon:
                reminders["regular_upcoming"].append({
                    "employee_id": e["id"], "name": name, "dept": e["dept_name"],
                    "regular_date": _iso(rd), "days_left": (rd - today).days,
                })
        else:
            # 试用期到期：入职 + 90 天（可配置化默认）
            if e["hire_date"]:
                hd = _d(e["hire_date"])
                if hd:
                    probation_end = hd + _dt.timedelta(days=90)
                    if probation_end < today:
                        reminders["probation_overdue"].append({
                            "employee_id": e["id"], "name": name, "dept": e["dept_name"],
                            "hire_date": _iso(hd), "days_overdue": (today - probation_end).days,
                        })
                    elif today <= probation_end <= soon:
                        reminders["probation_expiry"].append({
                            "employee_id": e["id"], "name": name, "dept": e["dept_name"],
                            "hire_date": _iso(hd), "probation_end": _iso(probation_end),
                            "days_left": (probation_end - today).days,
                        })
        if e["birthday"]:
            bd = _d(e["birthday"])
            if bd:
                next_birthday = _dt.date(today.year, bd.month, bd.day)
                if next_birthday < today:
                    next_birthday = _dt.date(today.year + 1, bd.month, bd.day)
                if next_birthday <= soon:
                    reminders["birthday"].append({
                        "employee_id": e["id"], "name": name, "dept": e["dept_name"],
                        "birthday": _iso(next_birthday), "days_left": (next_birthday - today).days,
                        "age": today.year - bd.year,
                    })
        if e["id_card_expiry"]:
            ie = _d(e["id_card_expiry"])
            if ie and today <= ie <= soon:
                reminders["id_card_expiry"].append({
                    "employee_id": e["id"], "name": name, "dept": e["dept_name"],
                    "expiry_date": _iso(ie), "days_left": (ie - today).days,
                    "level": "danger" if (ie - today).days <= 30 else "warning",
                })

    summary = {k: len(v) for k, v in reminders.items()}
    summary["total"] = sum(summary.values())
    return {"summary": summary, "reminders": reminders}


def recruit_dashboard(engine: Optional[Engine] = None) -> dict[str, Any]:
    """招聘总览 KPI：基于面试邀约登记表（interview_register）实时统计。

    与页面「面试邀约信息」表格同源，候选人总数 / 待跟进 / 录用率 / 到岗率 /
    平均招聘周期 全部来自简历跟进看板数据；**归档记录也一并计入统计**。

    指标口径：
      - total_candidates  候选人总数 = 登记总行数（含归档）
      - pending_followup  待跟进     = 未填写面试情况的行数（含归档）
      - offer_rate        录用率     = 面试通过(N) / 已填写面试情况(N)
      - onboard_rate      到岗率     = 已填入职时间(N) / 面试通过(N)
      - avg_cycle_days    平均招聘周期 = avg(入职时间 - 初面日期)
    """
    engine = engine or get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN interview_status IS NULL OR interview_status = ''
                       THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN interview_status LIKE '面试通过%' THEN 1 ELSE 0 END) AS passed,
              SUM(CASE WHEN interview_status IS NOT NULL AND interview_status <> ''
                       THEN 1 ELSE 0 END) AS decided,
              SUM(CASE WHEN join_date IS NOT NULL AND join_date <> ''
                       THEN 1 ELSE 0 END) AS joined,
              AVG(CASE
                    WHEN join_date IS NOT NULL AND join_date <> ''
                     AND first_interview_date IS NOT NULL AND first_interview_date <> ''
                    THEN DATEDIFF(
                           STR_TO_DATE(join_date, '%Y-%m-%d'),
                           STR_TO_DATE(first_interview_date, '%Y-%m-%d'))
                  END) AS avg_cycle
            FROM interview_register
            """
        )).one()
    total = int(row.total or 0)
    pending = int(row.pending or 0)
    passed = int(row.passed or 0)
    decided = int(row.decided or 0)
    joined = int(row.joined or 0)
    avg_cycle = row.avg_cycle
    return {
        "kpis": {
            "total_candidates": total,
            "pending_followup": pending,
            "offer_rate": round(passed / decided, 4) if decided else 0,
            "onboard_rate": round(joined / passed, 4) if passed else 0,
            "avg_cycle_days": round(float(avg_cycle), 1) if avg_cycle is not None else 0,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# 考勤通用导入 + 查询
# ──────────────────────────────────────────────────────────────────────────────

def _match_employee(conn, name: str) -> Optional[int]:
    """按姓名匹配在职员工，返回 id。"""
    row = conn.execute(
        text("SELECT id FROM hr_employee WHERE name = :n AND status = 'active' ORDER BY id LIMIT 1"),
        {"n": name},
    ).scalar_one_or_none()
    return int(row) if row else None


def _read_simple_table(path: str) -> list[tuple[str, list[dict[str, Any]]]]:
    """读取 Excel 所有工作表为 (sheet_name, [row_dict])，第一行为表头。"""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        result = []
        for ws in wb.worksheets:
            header: list[str] = []
            rows: list[dict[str, Any]] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    header = [_clean_str(c) for c in row]
                    continue
                d = {header[j]: (row[j] if j < len(row) else None) for j in range(len(header))}
                rows.append(d)
            result.append((ws.title, rows))
        return result
    finally:
        wb.close()


def _norm_hdr(s: Any) -> str:
    """表头归一化：去空白/换行/全角括号，便于模糊匹配。"""
    return re.sub(r"[\s（）()\u3000]", "", _clean_str(s))


def _find_col(row: dict[str, Any], keys: list[str]) -> Any:
    """按归一化表头模糊匹配列值：返回第一个同时命中的列。"""
    for k, v in row.items():
        nk = _norm_hdr(k)
        for key in keys:
            if _norm_hdr(key) in nk:
                return v
    return None


def _extract_month(v: Any) -> str:
    """从字符串中提取 'YYYY-MM'（如 '2026年07月10日 09:30' / '2026-07-31'）。"""
    s = _clean_str(v)
    m = re.search(r"(20\d{2})\s*[年\-/\.]\s*(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s*月", s)
    if m:
        y = re.search(r"(20\d{2})\s*年", s)
        return f"{y.group(1)}-{int(m.group(1)):02d}" if y else ""
    return ""


def _extract_date(v: Any) -> Optional[_dt.date]:
    """从字符串中提取日期（容忍 '2026年07月10日 09:30' 等）。"""
    s = _clean_str(v)
    m = re.search(r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    return _parse_date(v)


def _month_from_filename(path: str) -> str:
    base = str(Path(path)).replace("\\", "/").rsplit("/", 1)[-1]
    m = re.search(r"(20\d{2})\s*[年\-/\.]\s*(\d{1,2})\s*月?", base)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s*月", base)
    if m:
        return f"{_dt.date.today().year}-{int(m.group(1)):02d}"
    return ""


def _find_col_excl(row: dict[str, Any], keys: list[str], excl: list[str]) -> Any:
    """归一化表头模糊匹配，排除含 excl 关键词的列（如排除 入职/离职 取 日期）。"""
    for k, v in row.items():
        nk = _norm_hdr(k)
        if any(_norm_hdr(e) in nk for e in excl):
            continue
        for key in keys:
            if _norm_hdr(key) in nk:
                return v
    return None


def _read_attendance_sheets(path: str) -> list[tuple[str, list[dict[str, Any]]]]:
    """读取考勤工作簿：自动合并两行表头（分组头+子列头），返回各 sheet 的 dict 列表。

    兼容三类格式：
    - 考勤汇总工作簿（《汇总表》《迟到》《请假》《补卡》《每日统计》多表，两行表头）；
    - 每日统计工作簿（两行表头，按人按天）；
    - 旧版单行表头（姓名/部门/月份/应出勤/…）。

    两行表头判定：第 2 行首列为空（序号/姓名 等分组头仅在第 1 行），且第 2 行其余位置有子列头。
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        result: list[tuple[str, list[dict[str, Any]]]] = []
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            if not rows:
                result.append((ws.title, []))
                continue
            row0 = [_clean_str(c) for c in rows[0]]
            header = row0
            start = 1
            if len(rows) > 1:
                row1 = [_clean_str(c) for c in rows[1]]
                two_row = (
                    not _norm_hdr(row1[0]) if row1 else False
                ) and any(_norm_hdr(c) for c in row1[1:])
                if two_row:
                    header = [
                        (f"{row0[i]}/{row1[i]}").strip("/") if _norm_hdr(row0[i]) else row1[i]
                        for i in range(max(len(row0), len(row1)))
                    ]
                    start = 2
            dict_rows: list[dict[str, Any]] = []
            for r in rows[start:]:
                # 重复表头（右侧透视表列）只保留首次出现，避免覆盖主表列
                d: dict[str, Any] = {}
                for j in range(len(header)):
                    key = header[j]
                    if key not in d:
                        d[key] = r[j] if j < len(r) else None
                dict_rows.append(d)
            result.append((ws.title, dict_rows))
        return result
    finally:
        wb.close()


# ──────────────────────────────────────────────────────────────────────────────
# 考勤导入（汇总表 / 每日统计 / 迟到 / 请假 / 补卡）
# ──────────────────────────────────────────────────────────────────────────────

# 汇总表字段映射：归一化表头关键词 → 入库字段
_SUMMARY_FIELD_KEYS: list[tuple[str, list[str]]] = [
    ("company", ["所属公司"]),
    ("dept1", ["一级部门"]),
    ("dept2", ["二级部门"]),
    ("dept3", ["三级部门"]),
    ("position", ["岗位"]),
    ("hire_date", ["入职时间", "入职日期"]),
    ("resign_date", ["离职时间", "离职日期"]),
    ("paid_days", ["应计薪天数"]),
    ("actual_paid_days", ["实际计薪天数"]),
    ("work_days", ["应出勤天数", "应出勤"]),
    ("actual_days", ["实际出勤"]),
    ("legal_holidays", ["当月法定节假日", "法定节假日"]),
    ("shift_extra_days", ["通班加算出勤天", "通班"]),
    ("hire_resign_diff", ["入离职时间差"]),
    ("annual_leave", ["年假"]),
    ("comp_leave", ["调休"]),
    ("maternity_leave", ["产假"]),
    ("paternity_leave", ["陪产假"]),
    ("prenatal_leave", ["产检", "哺乳假"]),
    ("marriage_leave", ["婚假"]),
    ("funeral_leave", ["丧假"]),
    ("sick_days", ["病假（", "病假(天", "请假情况/病假", "病假\n", "病假天"]),
    ("personal_days", ["事假"]),
    ("absent_work_days", ["旷工"]),
    ("sick_wage", ["病假工资"]),
    ("late_penalty", ["迟到负激励", "迟到负"]),
    ("early_penalty", ["早退负激励", "早退负"]),
    ("makeup_penalty", ["补卡负激励", "补卡负"]),
    ("comp_days_extra", ["本月多上", "后可调休"]),
    ("remark", ["备注"]),
]

# 每日统计字段映射
_DAILY_FIELD_KEYS: list[tuple[str, list[str]]] = [
    ("dept_name", ["部门"]),
    ("position", ["职务"]),
    ("work_date", ["考勤组信息/日期", "/日期"]),
    ("weekday", ["星期"]),
    ("on_time", ["上班1打卡时间", "上班1上班打卡"]),
    ("on_result", ["上班1打卡结果", "上班1结果"]),
    ("on_location", ["上班1打卡地点"]),
    ("off_time", ["下班1打卡时间"]),
    ("off_result", ["下班1打卡结果"]),
    ("off_location", ["下班1打卡地点"]),
    ("work_days", ["应出勤天数"]),
    ("work_hours", ["应出勤时长"]),
    ("rest_days", ["休息或未排班天数", "未排班"]),
    ("actual_days", ["实际出勤天数"]),
    ("actual_hours", ["实际出勤时长"]),
    ("shift_hours", ["班内工作时长"]),
    ("business_days", ["出差天数"]),
    ("outing_hours", ["外出时长"]),
    ("makeup_count", ["补卡次数"]),
    ("late_count", ["迟到次数"]),
    ("late_minutes", ["迟到时长"]),
    ("serious_late_count", ["严重迟到次数"]),
    ("serious_late_hours", ["严重迟到时长"]),
    ("early_count", ["早退次数"]),
    ("early_minutes", ["早退时长"]),
    ("absent_hours", ["缺勤时长"]),
    ("on_missing_count", ["上班缺卡次数", "上班缺卡"]),
    ("off_missing_count", ["下班缺卡次数", "下班缺卡"]),
    ("absentee_days", ["旷工天数"]),
    ("overtime_hours", ["加班总时长"]),
    ("overtime_paid_hours", ["计加班费"]),
    ("overtime_comp_hours", ["计调休"]),
]


def _classify_sheet(sheet_name: str, headers: list[str]) -> str:
    """判定 sheet 类型：summary / daily / late / leave / makeup / simple。"""
    hs = [_norm_hdr(h) for h in headers]
    joined = "|".join(hs)
    if any("所属公司" in h or "一级部门" in h for h in hs) or ("应计薪天数" in joined and "姓名" in joined):
        return "summary"
    if any("迟到日期" in h for h in hs):
        return "late"
    if any("假期类型" in h or "请假事由" in h for h in hs):
        return "leave"
    if any("补卡日期" in h for h in hs):
        return "makeup"
    if any("上班1" in h or "出勤统计" in h for h in hs) and any("日期" in h for h in hs):
        return "daily"
    if any("月份" in h or "考勤月份" in h for h in hs):
        return "simple"
    return "simple"


def import_attendance_excel(path: str, operator: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """考勤 Excel 导入（兼容汇总工作簿 / 每日统计 / 旧版单表）。

    写入：
    - hr_attendance_sum      月度汇总（按 姓名+月份 幂等 upsert，汇总表优先，每日/迟到等补齐）；
    - hr_attendance_detail   每日明细；
    - hr_attendance_late     迟到记录；
    - hr_attendance_leave    请假记录；
    - hr_attendance_makeup   补卡记录（明细表按 月份+文件内姓名 替换式重建）。
    """
    ensure_tables(engine)
    engine = engine or get_engine()

    sheets = _read_attendance_sheets(path)
    report = {"rows_read": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": [], "details": {}}

    summaries: list[dict[str, Any]] = []
    dailies: list[dict[str, Any]] = []
    lates: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    makeups: list[dict[str, Any]] = []
    simple_rows: list[dict[str, Any]] = []

    month_hits: list[str] = []
    for sheet_name, rows in sheets:
        if not rows:
            continue
        headers = list(rows[0].keys())
        kind = _classify_sheet(sheet_name, headers)
        for row in rows:
            name = _clean_str(_find_col(row, ["姓名", "员工姓名"]))
            if not name:
                continue
            if kind == "summary":
                rec: dict[str, Any] = {"name": name}
                for field, keys in _SUMMARY_FIELD_KEYS:
                    rec[field] = _find_col(row, keys)
                summaries.append(rec)
                report["rows_read"] += 1
            elif kind == "daily":
                rec = {"name": name}
                for field, keys in _DAILY_FIELD_KEYS:
                    if field == "work_date":
                        rec[field] = _find_col_excl(row, keys, ["入职", "离职"])
                    else:
                        rec[field] = _find_col(row, keys)
                dailies.append(rec)
                report["rows_read"] += 1
                d = _extract_date(rec.get("work_date"))
                if d:
                    month_hits.append(f"{d.year:04d}-{d.month:02d}")
            elif kind == "late":
                d = _extract_date(_find_col(row, ["迟到日期"]))
                if d:
                    month_hits.append(f"{d.year:04d}-{d.month:02d}")
                lates.append({
                    "name": name, "late_date": d,
                    "late_time": _clean_str(_find_col(row, ["迟到时间"])),
                    "penalty_amount": _clean_decimal(_find_col(row, ["迟到负激励", "负激励", "金额"])),
                })
                report["rows_read"] += 1
            elif kind == "leave":
                st = _clean_str(_find_col(row, ["开始时间", "开始"]))
                en = _clean_str(_find_col(row, ["结束时间", "结束"]))
                m1, m2 = _extract_month(st), _extract_month(en)
                if m1:
                    month_hits.append(m1)
                if m2:
                    month_hits.append(m2)
                leaves.append({
                    "name": name,
                    "leave_type": _clean_str(_find_col(row, ["假期类型"])),
                    "reason": _clean_str(_find_col(row, ["请假事由", "事由"])),
                    "start_time": st, "end_time": en,
                    "hours": _clean_decimal(_find_col(row, ["时长（小时）", "时长(小时)", "时长小时", "小时"])),
                    "days": _clean_decimal(_find_col(row, ["时长（天）", "时长(天)", "时长天", "天数"])),
                })
                report["rows_read"] += 1
            elif kind == "makeup":
                d = _extract_date(_find_col(row, ["补卡日期"]))
                if d:
                    month_hits.append(f"{d.year:04d}-{d.month:02d}")
                makeups.append({
                    "name": name,
                    "reason": _clean_str(_find_col(row, ["补卡事由", "事由"])),
                    "makeup_date": d,
                    "makeup_time": _clean_str(_find_col(row, ["补卡时间", "时间"])),
                    "penalty_amount": _clean_decimal(_find_col(row, ["补卡负激励", "负激励", "金额"])),
                })
                report["rows_read"] += 1
            else:  # simple 旧版单表
                simple_rows.append(row)
                report["rows_read"] += 1

    # 确定月份：显式月份列 > 数据日期推断 > 文件名
    month = ""
    for row in simple_rows:
        m = _clean_str(_find_col(row, ["月份", "考勤月份", "YYYY-MM"]))
        if re.match(r"^\d{4}-\d{2}$", m):
            month = m
            break
    if not month:
        from collections import Counter

        cnt = Counter(month_hits)
        if cnt:
            month = cnt.most_common(1)[0][0]
    if not month:
        month = _month_from_filename(path)

    if not month:
        report["message"] = "考勤导入失败：无法识别考勤月份（缺少月份列且文件/数据无日期）"
        return report

    # ── 每日明细聚合 → 月度统计补齐 ──
    daily_agg: dict[tuple[str, str], dict[str, Any]] = {}
    for d in dailies:
        key = (month, d["name"])
        agg = daily_agg.setdefault(key, {
            "work_days": Decimal("0"), "actual_days": Decimal("0"),
            "late_count": 0, "early_count": 0, "makeup_count": 0,
            "absent_hours": Decimal("0"), "on_missing_count": 0, "off_missing_count": 0,
            "overtime_hours": Decimal("0"), "serious_late_count": 0, "early_minutes": 0,
            "late_minutes": 0,
        })
        agg["work_days"] += _clean_decimal(d.get("work_days"))
        agg["actual_days"] += _clean_decimal(d.get("actual_days"))
        agg["late_count"] += _clean_int(d.get("late_count"))
        agg["early_count"] += _clean_int(d.get("early_count"))
        agg["makeup_count"] += _clean_int(d.get("makeup_count"))
        agg["absent_hours"] += _clean_decimal(d.get("absent_hours"))
        agg["on_missing_count"] += _clean_int(d.get("on_missing_count"))
        agg["off_missing_count"] += _clean_int(d.get("off_missing_count"))
        agg["overtime_hours"] += _clean_decimal(d.get("overtime_hours"))
        agg["serious_late_count"] += _clean_int(d.get("serious_late_count"))
        agg["early_minutes"] += _clean_int(d.get("early_minutes"))
        agg["late_minutes"] += _clean_int(d.get("late_minutes"))

    # ── 汇总记录合并（汇总表优先，每日/迟到/请假/补卡补齐） ──
    # 类型清洗字段清单
    _dec_fields = ("work_days", "actual_days", "paid_days", "actual_paid_days", "legal_holidays",
                   "shift_extra_days", "hire_resign_diff", "annual_leave", "comp_leave",
                   "maternity_leave", "paternity_leave", "prenatal_leave", "marriage_leave",
                   "funeral_leave", "sick_days", "personal_days", "absent_work_days", "sick_wage",
                   "late_penalty", "early_penalty", "makeup_penalty", "comp_days_extra",
                   "absent_days", "leave_days", "overtime_hours")
    _int_fields = ("late_count", "early_count", "abnormal_count", "makeup_count",
                   "on_missing_count", "off_missing_count", "serious_late_count",
                   "late_minutes", "early_minutes")
    _str_fields = ("company", "dept1", "dept2", "dept3", "position", "remark")

    def _norm_summary_rec(raw: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"month": month, "name": raw.get("name", "")}
        for f in _dec_fields:
            out[f] = _clean_decimal(raw.get(f))
        for f in _int_fields:
            out[f] = _clean_int(raw.get(f))
        for f in _str_fields:
            out[f] = _clean_str(raw.get(f))
        out["dept_name"] = _clean_str(raw.get("dept1") or "") or _clean_str(raw.get("dept_name"))
        out["hire_date"] = _extract_date(raw.get("hire_date"))
        out["resign_date"] = _extract_date(raw.get("resign_date"))
        return out

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for s in summaries:
        key = (month, s["name"])
        merged[key] = _norm_summary_rec(s)

    # 旧版单表
    for row in simple_rows:
        name = _clean_str(_find_col(row, ["姓名", "员工姓名"]))
        key = (month, name)
        rec = merged.get(key) or {
            "month": month, "name": name,
            "dept_name": _clean_str(_find_col(row, ["部门"])),
            "work_days": _clean_decimal(_find_col(row, ["应出勤", "应勤"])),
            "actual_days": _clean_decimal(_find_col(row, ["实际出勤", "实出勤", "出勤天"])),
            "late_count": _clean_int(_find_col(row, ["迟到"])),
            "early_count": _clean_int(_find_col(row, ["早退"])),
            "absent_days": _clean_decimal(_find_col(row, ["缺勤"])),
            "leave_days": _clean_decimal(_find_col(row, ["请假"])),
            "overtime_hours": _clean_decimal(_find_col(row, ["加班"])),
            "abnormal_count": _clean_int(_find_col(row, ["异常"])),
            "remark": _clean_str(_find_col(row, ["备注"])),
        }
        merged[key] = rec

    # 仅来自每日统计的人：生成最小汇总记录（先于统计口径合并，确保 work_days 等被补齐）
    for key in daily_agg.keys():
        if key not in merged:
            name = key[1]
            agg = daily_agg[key]
            raw = {
                "name": name,
                "work_days": agg["work_days"], "actual_days": agg["actual_days"],
                "late_count": agg["late_count"], "early_count": agg["early_count"],
                "absent_days": agg["absent_hours"], "overtime_hours": agg["overtime_hours"],
                "makeup_count": agg["makeup_count"], "on_missing_count": agg["on_missing_count"],
                "off_missing_count": agg["off_missing_count"], "serious_late_count": agg["serious_late_count"],
                "late_minutes": agg["late_minutes"], "early_minutes": agg["early_minutes"],
            }
            rec = _norm_summary_rec(raw)
            rec["abnormal_count"] = agg["late_count"] + agg["early_count"] + agg["makeup_count"] + agg["on_missing_count"] + agg["off_missing_count"]
            # 部门取该人每日明细的第一个部门
            for d in dailies:
                if d["name"] == name and d.get("dept_name"):
                    rec["dept_name"] = _clean_str(d.get("dept_name"))
                    break
            merged[key] = rec

    # 迟到 / 补卡 / 请假补齐
    late_by_name: dict[str, list[dict[str, Any]]] = {}
    for lr in lates:
        late_by_name.setdefault(lr["name"], []).append(lr)
    makeup_by_name: dict[str, list[dict[str, Any]]] = {}
    for mr in makeups:
        makeup_by_name.setdefault(mr["name"], []).append(mr)
    leave_by_name: dict[str, list[dict[str, Any]]] = {}
    for lv in leaves:
        leave_by_name.setdefault(lv["name"], []).append(lv)

    all_names = {k[1] for k in merged.keys()} | {k[1] for k in daily_agg.keys()}

    # 来自汇总表/旧版单表的 key：有完整字段，可全量覆盖
    summary_keys = {key for s in summaries for key in [(month, s["name"])]} | {
        (month, _clean_str(_find_col(r, ["姓名", "员工姓名"]))) for r in simple_rows
    }

    for key, rec in merged.items():
        name = key[1]
        agg = daily_agg.get(key)
        if agg:
            if not _clean_decimal(rec.get("work_days")):
                rec["work_days"] = agg["work_days"]
            if not _clean_decimal(rec.get("actual_days")):
                rec["actual_days"] = agg["actual_days"]
            if not _clean_int(rec.get("late_count")):
                rec["late_count"] = agg["late_count"]
            if not _clean_int(rec.get("early_count")):
                rec["early_count"] = agg["early_count"]
            if not _clean_int(rec.get("makeup_count")):
                rec["makeup_count"] = agg["makeup_count"]
            if not _clean_decimal(rec.get("absent_days")):
                rec["absent_days"] = agg["absent_hours"]
            if not _clean_decimal(rec.get("overtime_hours")):
                rec["overtime_hours"] = agg["overtime_hours"]
            rec["on_missing_count"] = agg["on_missing_count"]
            rec["off_missing_count"] = agg["off_missing_count"]
            rec["serious_late_count"] = agg["serious_late_count"]
            rec["late_minutes"] = agg["late_minutes"]
            rec["early_minutes"] = agg["early_minutes"]
            rec["abnormal_count"] = agg["late_count"] + agg["early_count"] + agg["makeup_count"] + agg["on_missing_count"] + agg["off_missing_count"]
        lrs = late_by_name.get(name, [])
        if lrs:
            if not _clean_int(rec.get("late_count")):
                rec["late_count"] = len(lrs)
            if not _clean_decimal(rec.get("late_penalty")):
                rec["late_penalty"] = sum((_clean_decimal(x.get("penalty_amount")) for x in lrs), Decimal("0"))
        mrs = makeup_by_name.get(name, [])
        if mrs:
            if not _clean_int(rec.get("makeup_count")):
                rec["makeup_count"] = len(mrs)
            if not _clean_decimal(rec.get("makeup_penalty")):
                rec["makeup_penalty"] = sum((_clean_decimal(x.get("penalty_amount")) for x in mrs), Decimal("0"))
        lvs = leave_by_name.get(name, [])
        if lvs and not _clean_decimal(rec.get("leave_days")):
            rec["leave_days"] = sum((_clean_decimal(x.get("days")) for x in lvs), Decimal("0"))
            if not _clean_decimal(rec.get("sick_days")):
                rec["sick_days"] = sum((_clean_decimal(x.get("days")) for x in lvs if "病" in x.get("leave_type", "")), Decimal("0"))
            if not _clean_decimal(rec.get("personal_days")):
                rec["personal_days"] = sum((_clean_decimal(x.get("days")) for x in lvs if "事" in x.get("leave_type", "")), Decimal("0"))

    # ── 写库 ──
    sum_inserted = sum_updated = 0
    names_in_file = sorted(all_names)

    def _delete_by_names(table: str, month: str, names: list[str]) -> None:
        if not names:
            return
        ph = ",".join([f":n{i}" for i in range(len(names))])
        params: dict[str, Any] = {"m": month}
        params.update({f"n{i}": n for i, n in enumerate(names)})
        conn.execute(text(f"DELETE FROM {table} WHERE month = :m AND name IN ({ph})"), params)

    with engine.begin() as conn:
        # 明细类记录：按 月份+文件内姓名 替换式重建
        _delete_by_names("hr_attendance_detail", month, names_in_file if dailies else [])
        _delete_by_names("hr_attendance_late", month, names_in_file if lates else [])
        _delete_by_names("hr_attendance_leave", month, names_in_file if leaves else [])
        _delete_by_names("hr_attendance_makeup", month, names_in_file if makeups else [])

        # 每日明细
        detail_n = 0
        for d in dailies:
            emp_id = _match_employee(conn, d["name"])
            wd = _extract_date(d.get("work_date"))
            detail_n += 1
            conn.execute(hr_attendance_detail.insert(), {
                "employee_id": emp_id, "month": month, "name": d["name"],
                "dept_name": _clean_str(d.get("dept_name")),
                "position": _clean_str(d.get("position")),
                "work_date": wd, "weekday": _clean_str(d.get("weekday")),
                "on_time": _clean_str(d.get("on_time")), "on_result": _clean_str(d.get("on_result")),
                "on_location": _clean_str(d.get("on_location")),
                "off_time": _clean_str(d.get("off_time")), "off_result": _clean_str(d.get("off_result")),
                "off_location": _clean_str(d.get("off_location")),
                "work_days": _clean_decimal(d.get("work_days")), "work_hours": _clean_decimal(d.get("work_hours")),
                "rest_days": _clean_decimal(d.get("rest_days")), "actual_days": _clean_decimal(d.get("actual_days")),
                "actual_hours": _clean_decimal(d.get("actual_hours")), "shift_hours": _clean_decimal(d.get("shift_hours")),
                "business_days": _clean_decimal(d.get("business_days")), "outing_hours": _clean_decimal(d.get("outing_hours")),
                "makeup_count": _clean_int(d.get("makeup_count")), "late_count": _clean_int(d.get("late_count")),
                "late_minutes": _clean_int(d.get("late_minutes")),
                "serious_late_count": _clean_int(d.get("serious_late_count")),
                "serious_late_hours": _clean_decimal(d.get("serious_late_hours")),
                "early_count": _clean_int(d.get("early_count")), "early_minutes": _clean_int(d.get("early_minutes")),
                "absent_hours": _clean_decimal(d.get("absent_hours")),
                "on_missing_count": _clean_int(d.get("on_missing_count")),
                "off_missing_count": _clean_int(d.get("off_missing_count")),
                "absentee_days": _clean_decimal(d.get("absentee_days")),
                "overtime_hours": _clean_decimal(d.get("overtime_hours")),
                "overtime_paid_hours": _clean_decimal(d.get("overtime_paid_hours")),
                "overtime_comp_hours": _clean_decimal(d.get("overtime_comp_hours")),
                "source_key": f"attd:{month}:{d['name']}:{wd.isoformat() if wd else '-'}",
                "created_at": _now(),
            })
        for lr in lates:
            emp_id = _match_employee(conn, lr["name"])
            conn.execute(hr_attendance_late.insert(), {
                "month": month, "employee_id": emp_id, "name": lr["name"],
                "late_date": lr["late_date"], "late_time": lr["late_time"],
                "penalty_amount": lr["penalty_amount"],
                "source_key": f"attl:{month}:{lr['name']}:{lr['late_date'].isoformat() if lr['late_date'] else '-'}",
                "created_at": _now(),
            })
        for lv in leaves:
            emp_id = _match_employee(conn, lv["name"])
            conn.execute(hr_attendance_leave.insert(), {
                "month": month, "employee_id": emp_id, "name": lv["name"],
                "leave_type": lv["leave_type"], "reason": lv["reason"],
                "start_time": lv["start_time"], "end_time": lv["end_time"],
                "hours": lv["hours"], "days": lv["days"],
                "source_key": f"attv:{month}:{lv['name']}:{lv['start_time'] or lv['end_time'] or '-'}",
                "created_at": _now(),
            })
        for mr in makeups:
            emp_id = _match_employee(conn, mr["name"])
            conn.execute(hr_attendance_makeup.insert(), {
                "month": month, "employee_id": emp_id, "name": mr["name"],
                "reason": mr["reason"], "makeup_date": mr["makeup_date"],
                "makeup_time": mr["makeup_time"], "penalty_amount": mr["penalty_amount"],
                "source_key": f"attm:{month}:{mr['name']}:{mr['makeup_date'].isoformat() if mr['makeup_date'] else '-'}",
                "created_at": _now(),
            })

        # 月度汇总 upsert（姓名+月份）
        # 仅来自每日统计（无汇总表）的记录：只更新统计口径字段，保留既有组织/计薪/负激励字段
        #   · 计数类（迟到/早退/补卡/缺卡/严重迟到…）：每日口径，始终覆盖
        #   · 天数/时长类（应出勤/实出勤/缺勤/加班）：若汇总表已提供非 0 值则保留
        _daily_only_always = ("late_count", "early_count", "makeup_count", "on_missing_count",
                              "off_missing_count", "serious_late_count", "late_minutes",
                              "early_minutes", "abnormal_count")
        _daily_only_fill = ("work_days", "actual_days", "absent_days", "overtime_hours")
        for key, rec in merged.items():
            name = key[1]
            emp_id = _match_employee(conn, name)
            rec["employee_id"] = emp_id
            existing = conn.execute(
                text("SELECT id FROM hr_attendance_sum WHERE month = :m AND ((employee_id = :eid AND :eid IS NOT NULL) OR (employee_id IS NULL AND name = :n)) LIMIT 1"),
                {"m": month, "eid": emp_id, "n": name},
            ).scalar_one_or_none()
            if existing is not None:
                if key in summary_keys:
                    conn.execute(hr_attendance_sum.update().where(hr_attendance_sum.c.id == existing), {**rec, "updated_at": _now()})
                else:
                    cur = conn.execute(
                        text("SELECT dept_name, work_days, actual_days, absent_days, overtime_hours FROM hr_attendance_sum WHERE id = :id"),
                        {"id": existing},
                    ).mappings().one()
                    upd: dict[str, Any] = {}
                    for f in _daily_only_always:
                        upd[f] = rec[f]
                    for f in _daily_only_fill:
                        if not _clean_decimal(cur.get(f)):
                            upd[f] = rec[f]
                    if not _clean_str(cur.get("dept_name")) and _clean_str(rec.get("dept_name")):
                        upd["dept_name"] = rec["dept_name"]
                    upd["updated_at"] = _now()
                    conn.execute(hr_attendance_sum.update().where(hr_attendance_sum.c.id == existing), upd)
                sum_updated += 1
            else:
                conn.execute(hr_attendance_sum.insert(), {"source_key": f"att:{month}:{name}", "created_at": _now(), **rec})
                sum_inserted += 1

    report["inserted"] = sum_inserted
    report["updated"] = sum_updated
    report["details"] = {
        "month": month,
        "summaries": len(summaries) + len(simple_rows),
        "daily": len(dailies),
        "late": len(lates),
        "leave": len(leaves),
        "makeup": len(makeups),
    }
    _log_import(engine, "attendance", path, "", report, operator)
    report["message"] = (
        f"考勤导入完成（{month}）：汇总 {report['details']['summaries']} 条，每日明细 {report['details']['daily']} 条，"
        f"迟到 {report['details']['late']} 条，请假 {report['details']['leave']} 条，补卡 {report['details']['makeup']} 条；"
        f"月度新增 {sum_inserted} / 更新 {sum_updated}"
    )
    return report


def list_attendance(month: str = "", dept: str = "", keyword: str = "", engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    clauses, params = [], {}
    if month:
        clauses.append("month = :month")
        params["month"] = month
    if dept:
        clauses.append("(dept_name = :dept OR dept1 = :dept)")
        params["dept"] = dept
    if keyword:
        clauses.append("name LIKE :kw")
        params["kw"] = f"%{keyword}%"
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM hr_attendance_sum{where} ORDER BY month DESC, dept_name, name"), params).mappings().all()
    return [_serialize_row(dict(r)) for r in rows]


def attendance_overview(month: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """考勤首页统计卡片：应出勤/实际出勤/迟到/早退/缺勤/请假/加班/异常/负激励。"""
    ensure_tables(engine)
    engine = engine or get_engine()
    where, params = "", {}
    if month:
        where = "WHERE month = :month"
        params["month"] = month
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*) employee_count, "
            "ROUND(COALESCE(SUM(work_days),0),1) work_days_total, "
            "ROUND(COALESCE(SUM(actual_days),0),1) actual_days_total, "
            "COALESCE(SUM(late_count),0) late_total, "
            "COALESCE(SUM(early_count),0) early_total, "
            "ROUND(COALESCE(SUM(absent_days),0),1) absent_total, "
            "ROUND(COALESCE(SUM(leave_days),0),1) leave_total, "
            "ROUND(COALESCE(SUM(overtime_hours),0),1) overtime_total, "
            "COALESCE(SUM(abnormal_count),0) abnormal_total, "
            "COALESCE(SUM(makeup_count),0) makeup_total, "
            "ROUND(COALESCE(SUM(late_penalty),0),1) late_penalty_total, "
            "ROUND(COALESCE(SUM(early_penalty),0),1) early_penalty_total, "
            "ROUND(COALESCE(SUM(makeup_penalty),0),1) makeup_penalty_total, "
            "ROUND(COALESCE(SUM(sick_wage),0),1) sick_wage_total, "
            "ROUND(COALESCE(SUM(personal_days),0),1) personal_days_total, "
            "ROUND(COALESCE(SUM(sick_days),0),1) sick_days_total "
            f"FROM hr_attendance_sum {where}"
        ), params).mappings().one()
    out = dict(row)
    out["penalty_total"] = round(float(out["late_penalty_total"] or 0) + float(out["early_penalty_total"] or 0) + float(out["makeup_penalty_total"] or 0), 1)
    return _serialize_row(out)


def attendance_dept_summary(month: str = "", engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    where, params = "", {}
    if month:
        where = "WHERE month = :month"
        params["month"] = month
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT COALESCE(NULLIF(dept1,''), dept_name) dept_name, COUNT(*) employee_count, "
            "ROUND(AVG(actual_days),1) avg_actual_days, ROUND(AVG(work_days),1) avg_work_days, "
            "SUM(late_count) late_total, "
            "SUM(early_count) early_total, ROUND(SUM(absent_days),1) absent_total, "
            "ROUND(SUM(leave_days),1) leave_total, ROUND(SUM(overtime_hours),1) overtime_total, "
            "ROUND(SUM(late_penalty),1) late_penalty_total "
            f"FROM hr_attendance_sum {where} GROUP BY COALESCE(NULLIF(dept1,''), dept_name) ORDER BY dept_name"
        ), params).mappings().all()
    return [_serialize_row(dict(r)) for r in rows]


def list_attendance_detail(month: str = "", name: str = "", dept: str = "", engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    clauses, params = [], {}
    if month:
        clauses.append("d.month = :month")
        params["month"] = month
    if name:
        clauses.append("d.name = :name")
        params["name"] = name
    if dept:
        # 兼容一级部门（汇总表 dept1）与每日明细自身部门（dept_name）
        clauses.append("(d.dept_name = :dept OR COALESCE(s.dept1, '') = :dept)")
        params["dept"] = dept
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT d.* FROM hr_attendance_detail d "
            f"LEFT JOIN hr_attendance_sum s ON s.month = d.month AND s.name = d.name{where} "
            "ORDER BY d.work_date DESC, d.name"
        ), params).mappings().all()
    return [_serialize_row(dict(r)) for r in rows]


def list_attendance_late(month: str = "", name: str = "", engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    clauses, params = [], {}
    if month:
        clauses.append("month = :month")
        params["month"] = month
    if name:
        clauses.append("name = :name")
        params["name"] = name
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM hr_attendance_late{where} ORDER BY late_date DESC, name"), params).mappings().all()
    return [_serialize_row(dict(r)) for r in rows]


def list_attendance_leave(month: str = "", name: str = "", engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    clauses, params = [], {}
    if month:
        clauses.append("month = :month")
        params["month"] = month
    if name:
        clauses.append("name = :name")
        params["name"] = name
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM hr_attendance_leave{where} ORDER BY start_time DESC, name"), params).mappings().all()
    return [_serialize_row(dict(r)) for r in rows]


def list_attendance_makeup(month: str = "", name: str = "", engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    ensure_tables(engine)
    engine = engine or get_engine()
    clauses, params = [], {}
    if month:
        clauses.append("month = :month")
        params["month"] = month
    if name:
        clauses.append("name = :name")
        params["name"] = name
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM hr_attendance_makeup{where} ORDER BY makeup_date DESC, name"), params).mappings().all()
    return [_serialize_row(dict(r)) for r in rows]


def attendance_person(month: str = "", name: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """某员工某月考勤档案：汇总 + 每日明细 + 迟到/请假/补卡记录。"""
    ensure_tables(engine)
    engine = engine or get_engine()
    summary: dict[str, Any] = {}
    if month and name:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM hr_attendance_sum WHERE month = :m AND name = :n LIMIT 1"),
                {"m": month, "n": name},
            ).mappings().one_or_none()
            if row:
                summary = _serialize_row(dict(row))
    return {
        "summary": summary,
        "daily": list_attendance_detail(month=month, name=name, engine=engine),
        "late": list_attendance_late(month=month, name=name, engine=engine),
        "leave": list_attendance_leave(month=month, name=name, engine=engine),
        "makeup": list_attendance_makeup(month=month, name=name, engine=engine),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 驾驶舱
# ──────────────────────────────────────────────────────────────────────────────

def dashboard_overview(company: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """驾驶舱总览。company 非空时仅统计该公司（如 示例科技 / 示例传媒）。"""
    ensure_tables(engine)
    engine = engine or get_engine()
    today = _dt.date.today()
    month_start = today.replace(day=1)
    comp = " AND company = :company" if company else ""
    comp_params = {"company": company} if company else {}
    with engine.connect() as conn:
        active = conn.execute(
            text("SELECT COUNT(*) FROM hr_employee WHERE status = 'active'" + comp),
            comp_params,
        ).scalar()
        resigned = conn.execute(
            text("SELECT COUNT(*) FROM hr_employee WHERE status = 'resigned'" + comp),
            comp_params,
        ).scalar()
        hired_month = conn.execute(
            text("SELECT COUNT(*) FROM hr_employee WHERE hire_date >= :ms" + comp),
            {**comp_params, "ms": month_start},
        ).scalar()
        depts = conn.execute(
            text("SELECT dept_name, COUNT(*) cnt FROM hr_employee WHERE status='active'" + comp
                 + " GROUP BY dept_name ORDER BY cnt DESC"),
            comp_params,
        ).mappings().all()
        tenures = conn.execute(
            text("SELECT CASE WHEN DATEDIFF(CURDATE(), hire_date) < 365 THEN '1年以内' "
                 "WHEN DATEDIFF(CURDATE(), hire_date) < 1095 THEN '1-3年' "
                 "WHEN DATEDIFF(CURDATE(), hire_date) < 1825 THEN '3-5年' ELSE '5年以上' END bucket, COUNT(*) cnt "
                 "FROM hr_employee WHERE status='active' AND hire_date IS NOT NULL" + comp + " GROUP BY bucket"),
            comp_params,
        ).mappings().all()
        educations = conn.execute(
            text("SELECT education, COUNT(*) cnt FROM hr_employee WHERE status='active'"
                 + comp + " GROUP BY education ORDER BY cnt DESC"),
            comp_params,
        ).mappings().all()
    return {
        "active": int(active or 0), "resigned": int(resigned or 0),
        "hired_this_month": int(hired_month or 0),
        "dept_structure": [_serialize_row(dict(r)) for r in depts],
        "tenure_structure": [_serialize_row(dict(r)) for r in tenures],
        "education_structure": [_serialize_row(dict(r)) for r in educations],
    }


# ── 离职原因归并（口径稳定，驾驶舱 Top 看板） ────────────────────────────────
# 顺序敏感：先匹配先生效，避免长尾误入。
# 类别：未填写 / 个人原因 / 试用期淘汰 / 主动离职 / 试用期主动离职 / 劳动纠纷 / 其他
RESIGN_REASON_GROUPS: list[tuple[str, list[str]]] = [
    ("未填写", [r"^\s*$", r"未填写", r"未明确", r"不详"]),
    ("试用期淘汰", [
        r"试用期.*淘汰", r"试岗不合适", r"试用期业绩.*不达标", r"试用期.*业绩",
        r"综合表现差", r"不合适.*淘汰",
    ]),
    ("试用期主动离职", [r"试用期.*主动", r"试用期主动", r"试岗.*主动"]),
    ("个人原因", [
        r"个人原因", r"个人提出", r"回家", r"家族企业", r"个人发展",
        r"换个行业", r"自主创业", r"妹妹生病", r"老婆生小孩", r"照顾",
        r"想换", r"项目撤销",
    ]),
    ("主动离职", [
        r"主动离职", r"因仓库搬迁", r"因公司搬迁", r"不服从", r"不接受工作安排",
        r"身体不舒服", r"身体问题", r"想转", r"换个",
    ]),
    ("劳动纠纷", [r"劳动纠纷", r"仲裁", r"投诉"]),
    ("其他", [r"薪酬", r"福利", r"转合作", r"团队优化", r"着装", r"话术"]),
]


def _group_resign_reasons(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 RESIGN_REASON_GROUPS 把原始离职原因归并为 6-7 大类，按计数倒序返回。

    每条原始 (resign_reason, cnt) 命中首个匹配的正则即归入对应类别；未命中归"其他"。
    空字符串/未填写归"未填写"，避免与"个人原因"混淆。
    """
    buckets: dict[str, int] = {}
    for item in items:
        reason = _clean_str(item.get("resign_reason"))
        cnt = _clean_int(item.get("cnt"))
        if not cnt:
            continue
        category = "其他"
        for name, patterns in RESIGN_REASON_GROUPS:
            hit = False
            for pat in patterns:
                if re.search(pat, reason):
                    hit = True
                    break
            if hit:
                category = name
                break
        buckets[category] = buckets.get(category, 0) + cnt
    return [
        {"resign_reason": name, "cnt": cnt}
        for name, cnt in sorted(buckets.items(), key=lambda x: -x[1])
    ]


def dashboard_flow(months: int = 12, company: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """入职-离职趋势 + 离职率与离职原因。离职率 = 离职 / 期初期末平均在册。

    company 非空时仅统计该公司。
    """
    ensure_tables(engine)
    engine = engine or get_engine()
    today = _dt.date.today()
    start = today.replace(day=1) - _dt.timedelta(days=90 * 12)
    comp = " AND company = :company" if company else ""
    comp_params = {"company": company} if company else {}
    with engine.connect() as conn:
        hires = conn.execute(text(
            "SELECT DATE_FORMAT(hire_date, '%Y-%m') ym, COUNT(*) cnt FROM hr_employee "
            "WHERE hire_date >= :s" + comp + " GROUP BY ym"
        ), {**comp_params, "s": start}).mappings().all()
        resigns = conn.execute(text(
            "SELECT DATE_FORMAT(resign_date, '%Y-%m') ym, COUNT(*) cnt FROM hr_resign "
            "WHERE resign_date >= :s" + comp + " GROUP BY ym"
        ), {**comp_params, "s": start}).mappings().all()
        reasons = conn.execute(text(
            "SELECT resign_reason, COUNT(*) cnt FROM hr_resign WHERE resign_date >= :s" + comp
            + " GROUP BY resign_reason ORDER BY cnt DESC LIMIT 50"
        ), {**comp_params, "s": start}).mappings().all()
        total_resign = conn.execute(
            text("SELECT COUNT(*) FROM hr_resign WHERE resign_date >= :s" + comp),
            {**comp_params, "s": start},
        ).scalar()
        probation_resign = conn.execute(text(
            "SELECT COUNT(*) FROM hr_resign WHERE resign_date >= :s" + comp
            + " AND (resign_reason LIKE '%试用期%' OR resign_reason LIKE '%试岗%')"
        ), {**comp_params, "s": start}).scalar()
    hire_map = {r["ym"]: int(r["cnt"]) for r in hires}
    resign_map = {r["ym"]: int(r["cnt"]) for r in resigns}
    series = []
    cursor = _dt.date(start.year, start.month, 1)
    while cursor <= today:
        ym = cursor.strftime("%Y-%m")
        series.append({"month": ym, "hires": hire_map.get(ym, 0), "resigns": resign_map.get(ym, 0)})
        cursor = _dt.date(cursor.year + (1 if cursor.month == 12 else 0), (cursor.month % 12) + 1, 1)
    total_hires = sum(hire_map.values())
    # 离职率 = 期间离职 / 期初期末平均在册人数
    # 窗口起始在册 = 期末在册 - 期间净增 = active - (hires - resigns)
    with engine.connect() as conn:
        active_now = conn.execute(
            text("SELECT COUNT(*) FROM hr_employee WHERE status = 'active'" + comp),
            comp_params,
        ).scalar()
    start_headcount = int(active_now or 0) - total_hires + total_resign
    avg_headcount = (start_headcount + int(active_now or 0)) / 2
    resign_rate = round(total_resign / avg_headcount, 4) if avg_headcount else 0
    return {
        "series": series,
        "total_hires": int(total_hires),
        "total_resigns": int(total_resign),
        "start_headcount": int(start_headcount),
        "avg_headcount": round(avg_headcount, 1),
        "resign_rate": resign_rate,
        "probation_resign_rate": round(probation_resign / max(total_resign, 1), 4),
        "top_reasons": _group_resign_reasons([dict(r) for r in reasons]),
    }


def dashboard_reminders(company: str = "", engine: Optional[Engine] = None) -> dict[str, Any]:
    """驾驶舱侧的合同到期提醒与近期生日。company 非空时仅统计该公司。"""
    ensure_tables(engine)
    engine = engine or get_engine()
    today = _dt.date.today()
    soon = today + _dt.timedelta(days=90)
    comp = " AND e.company = :company" if company else ""
    comp_params = {"company": company} if company else {}
    with engine.connect() as conn:
        contract_by_days = conn.execute(text(
            "SELECT CASE WHEN DATEDIFF(c.end_date, CURDATE()) <= 30 THEN '0-30天' "
            "WHEN DATEDIFF(c.end_date, CURDATE()) <= 60 THEN '31-60天' "
            "WHEN DATEDIFF(c.end_date, CURDATE()) <= 90 THEN '61-90天' END bucket, COUNT(*) cnt "
            "FROM hr_contract c JOIN hr_employee e ON e.id = c.employee_id "
            "WHERE c.end_date >= CURDATE() AND c.end_date <= :soon" + comp + " GROUP BY bucket"
        ), {**comp_params, "soon": soon}).mappings().all()
        # 合同即将到期的具体员工（按到期日升序，前端用于提醒卡片）
        contract_employees = conn.execute(text(
            "SELECT e.id, e.name, e.dept_name, e.position, "
            "c.seq_no, c.contract_type, c.end_date, "
            "DATEDIFF(c.end_date, CURDATE()) days_left "
            "FROM hr_contract c JOIN hr_employee e ON e.id = c.employee_id "
            "WHERE e.status = 'active' AND c.end_date IS NOT NULL "
            "AND c.end_date >= CURDATE() AND c.end_date <= :soon" + comp + " "
            "ORDER BY c.end_date ASC"
        ), {**comp_params, "soon": soon}).mappings().all()
        birthdays = conn.execute(text(
            "SELECT id, name, dept_name, birthday FROM hr_employee "
            "WHERE status='active' AND birthday IS NOT NULL"
            + comp.replace("e.company", "company")
            + " AND MONTH(birthday) IN (:m1, :m2) ORDER BY DAY(birthday)"
        ), {**comp_params, "m1": today.month, "m2": (today.month % 12) + 1}).mappings().all()
    out = []
    for r in contract_employees:
        days = int(r["days_left"] or 0)
        out.append({
            "id": int(r["id"]),
            "name": r["name"],
            "dept": r["dept_name"] or "",
            "position": r["position"] or "",
            "seq_no": int(r["seq_no"] or 1),
            "end_date": _iso(r["end_date"]),
            "days_left": days,
            "level": "danger" if days <= 30 else "warning",
        })
    return {
        "contract_expiry_distribution": [_serialize_row(dict(r)) for r in contract_by_days],
        "contract_expiry_employees": out,
        "upcoming_birthdays": [
            {**dict(r), "birthday": _iso(r["birthday"]),
             "upcoming_birthday": _iso(_dt.date(today.year, r["birthday"].month, r["birthday"].day)
                                       if r["birthday"].month >= today.month else _dt.date(today.year + 1, r["birthday"].month, r["birthday"].day))}
            for r in birthdays
        ],
    }
