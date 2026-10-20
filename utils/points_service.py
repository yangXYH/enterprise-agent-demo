"""Employee points backed by the HR roster and an append-only points ledger."""

from __future__ import annotations

import datetime as dt
import re
import threading
import weakref
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, Text, text
from sqlalchemy.engine import Engine

from utils import hr_service
from utils.import_service import get_engine


metadata = MetaData()
points_rule = Table(
    "points_rule", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("points", Integer, nullable=False),
    Column("description", String(500), nullable=False, default=""),
    Column("is_active", Integer, nullable=False, default=1),
    Column("created_at", DateTime, nullable=False),
)
points_record = Table(
    "points_record", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", Integer, nullable=False),
    Column("employee_name", String(100), nullable=False),
    Column("rule_id", Integer, nullable=False),
    Column("rule_name", String(100), nullable=False),
    Column("points", Integer, nullable=False),
    Column("note", Text, nullable=False, default=""),
    Column("operator", String(100), nullable=False),
    Column("created_at", DateTime, nullable=False),
)
_indexes = (
    Index("idx_points_rule_active", points_rule.c.is_active),
    Index("idx_points_record_employee_time", points_record.c.employee_id, points_record.c.created_at),
    Index("idx_points_record_time", points_record.c.created_at),
)
_prepared_engines: weakref.WeakSet[Engine] = weakref.WeakSet()
_prepare_lock = threading.Lock()
_EXCLUDED_POSITION = "总经理"


def ensure_tables(engine: Engine | None = None) -> Engine:
    engine = engine or get_engine()
    if engine in _prepared_engines:
        return engine
    with _prepare_lock:
        if engine not in _prepared_engines:
            hr_service.ensure_tables(engine)
            metadata.create_all(engine)
            for index in _indexes:
                index.create(engine, checkfirst=True)
            _prepared_engines.add(engine)
    return engine


def list_rules(engine: Engine | None = None) -> list[dict[str, Any]]:
    engine = ensure_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name, points, description, is_active, created_at FROM points_rule ORDER BY is_active DESC, id DESC")).mappings()
        return [dict(row) for row in rows]


def save_rule(payload: dict[str, Any], engine: Engine | None = None) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or "").strip()
    raw_score = payload.get("points")
    if isinstance(raw_score, bool) or not re.fullmatch(r"[+-]?\d+", str(raw_score or "")):
        raise ValueError("积分必须是整数")
    score = int(raw_score)
    try:
        rule_id = int(payload.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("规则编号无效") from exc
    if not name or len(name) > 100:
        raise ValueError("规则名称不能为空且不能超过100字")
    if len(description) > 500:
        raise ValueError("规则说明不能超过500字")
    if score == 0 or abs(score) > 100000:
        raise ValueError("积分须为非零整数，绝对值不超过100000")
    active = 1 if payload.get("is_active", True) else 0
    engine = ensure_tables(engine)
    with engine.begin() as conn:
        if rule_id:
            result = conn.execute(points_rule.update().where(points_rule.c.id == rule_id).values(
                name=name, points=score, description=description, is_active=active,
            ))
            if result.rowcount == 0:
                raise KeyError("积分规则不存在")
        else:
            result = conn.execute(points_rule.insert().values(
                name=name, points=score, description=description, is_active=active,
                created_at=dt.datetime.now(),
            ))
            rule_id = int(result.inserted_primary_key[0])
    return {"id": rule_id, "name": name, "points": score, "description": description, "is_active": active}


def add_record(employee_id: int, rule_id: int, note: str, operator: str, engine: Engine | None = None) -> dict[str, Any]:
    note = note.strip()
    if not note:
        raise ValueError("请填写积分事项说明")
    if len(note) > 1000:
        raise ValueError("备注不能超过1000字")
    engine = ensure_tables(engine)
    with engine.begin() as conn:
        employee = conn.execute(text("SELECT id, name, position FROM hr_employee WHERE id = :id AND status = 'active'"), {"id": employee_id}).mappings().first()
        if not employee:
            raise ValueError("仅能为花名册中的在职员工登记积分")
        if str(employee["position"] or "").strip() == _EXCLUDED_POSITION:
            raise ValueError("总经理不参与积分系统")
        rule = conn.execute(text("SELECT id, name, points FROM points_rule WHERE id = :id AND is_active = 1"), {"id": rule_id}).mappings().first()
        if not rule:
            raise ValueError("请选择有效的积分规则")
        result = conn.execute(points_record.insert().values(
            employee_id=employee_id, employee_name=employee["name"], rule_id=rule_id,
            rule_name=rule["name"], points=rule["points"], note=note,
            operator=operator[:100], created_at=dt.datetime.now(),
        ))
        return {"id": int(result.inserted_primary_key[0]), "employee_id": employee_id, "points": int(rule["points"])}


def _month_bounds(month: str) -> tuple[dt.datetime, dt.datetime]:
    try:
        start = dt.datetime.strptime(month, "%Y-%m")
        if start.strftime("%Y-%m") != month:
            raise ValueError
    except ValueError as exc:
        raise ValueError("月份格式应为 YYYY-MM") from exc
    end = dt.datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, end


def leaderboard(
    *, company: str = "", dept: str = "", keyword: str = "", month: str = "",
    sort: str = "total", engine: Engine | None = None,
) -> dict[str, Any]:
    engine = ensure_tables(engine)
    month = month or dt.date.today().strftime("%Y-%m")
    start, end = _month_bounds(month)
    if sort not in {"total", "month"}:
        raise ValueError("排序方式无效")
    filters = ["e.status = 'active'", "TRIM(COALESCE(e.position, '')) <> :excluded_position"]
    params: dict[str, Any] = {"start": start, "end": end, "excluded_position": _EXCLUDED_POSITION}
    if company:
        filters.append("e.company = :company")
        params["company"] = company
    if dept:
        filters.append("e.dept_name = :dept")
        params["dept"] = dept
    if keyword:
        filters.append("(e.name LIKE :keyword OR e.emp_no LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    query = """
        SELECT e.id, e.emp_no, e.name, e.company, e.dept_name, e.position,
               COALESCE(p.total_points, 0) AS total_points,
               COALESCE(p.month_points, 0) AS month_points,
               COALESCE(p.record_count, 0) AS record_count
        FROM hr_employee e
        LEFT JOIN (
            SELECT employee_id, SUM(points) AS total_points,
                   SUM(CASE WHEN created_at >= :start AND created_at < :end THEN points ELSE 0 END) AS month_points,
                   COUNT(*) AS record_count
            FROM points_record GROUP BY employee_id
        ) p ON p.employee_id = e.id
        WHERE """ + " AND ".join(filters)
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(text(query), params).mappings()]
        options = [dict(row) for row in conn.execute(text(
            "SELECT DISTINCT company, dept_name FROM hr_employee "
            "WHERE status = 'active' AND TRIM(COALESCE(position, '')) <> :excluded_position "
            "ORDER BY company, dept_name"
        ), {"excluded_position": _EXCLUDED_POSITION}).mappings()]
    primary = "month_points" if sort == "month" else "total_points"
    rows.sort(key=lambda r: (-int(r[primary]), -int(r["total_points"]), int(r["id"])))
    previous: int | None = None
    rank = 0
    for index, row in enumerate(rows, 1):
        score = int(row[primary])
        if score != previous:
            rank = index
            previous = score
        row["rank"] = rank
        row["total_points"] = int(row["total_points"])
        row["month_points"] = int(row["month_points"])
        row["record_count"] = int(row["record_count"])
    return {
        "items": rows, "total": len(rows), "month": month, "sort": sort,
        "scored_count": sum(1 for row in rows if row["record_count"]),
        "total_points": sum(row["total_points"] for row in rows),
        "companies": sorted({r["company"] for r in options if r["company"]}),
        "departments": sorted({r["dept_name"] for r in options if r["dept_name"] and (not company or r["company"] == company)}),
    }


def list_records(
    *, employee_id: int = 0, month: str = "", page: int = 1,
    page_size: int = 20, engine: Engine | None = None,
) -> dict[str, Any]:
    engine = ensure_tables(engine)
    conditions = ["employee_id NOT IN (SELECT id FROM hr_employee WHERE TRIM(COALESCE(position, '')) = :excluded_position)"]
    params: dict[str, Any] = {"excluded_position": _EXCLUDED_POSITION}
    if employee_id:
        conditions.append("employee_id = :employee_id")
        params["employee_id"] = employee_id
    if month:
        params["start"], params["end"] = _month_bounds(month)
        conditions.append("created_at >= :start AND created_at < :end")
    where = " AND ".join(conditions)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM points_record WHERE {where}"), params).scalar_one()
        rows = conn.execute(text(
            f"SELECT id, employee_id, employee_name, rule_name, points, note, operator, created_at "
            f"FROM points_record WHERE {where} ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        ), {**params, "limit": page_size, "offset": (page - 1) * page_size}).mappings()
        items = [dict(row) for row in rows]
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}
