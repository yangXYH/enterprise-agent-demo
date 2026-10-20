"""AI 项目推进看板 MySQL 读写服务。

面向给老板汇报的 AI 项目推进看板：
- ai_daily_board_project     项目（名称 / 状态 / 当前重点一句话）
- ai_daily_board_daily_log   每日推进记录（所属项目 / 今天做了什么 / 明天计划 / 风险）
- ai_daily_board_risk        风险与阻塞（自动计算阻塞天数）

前端每次保存整体替换项目与风险记录，日报按日期覆盖，保证页面与库一致。
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Engine, text

from utils import import_service


DEFAULT_BOARD_KEY = "default"
DEFAULT_BOARD_TITLE = "AI 项目进度看板"

_BOARD_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_daily_board (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '看板主键ID',
    board_key VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '看板唯一标识，默认看板为 default，预留多看板扩展',
    board_title VARCHAR(128) NOT NULL DEFAULT 'AI 项目进度看板' COMMENT '看板名称',
    `current_date` DATE NOT NULL COMMENT '看板当前日期',
    show_charts TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示顶部指标，1显示，0隐藏',
    show_standup TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示每日推进记录，1显示，0隐藏',
    show_timeline TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示风险阻塞，1显示，0隐藏',
    show_table TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示项目概览，1显示，0隐藏',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_board_key (board_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板配置表'
"""

_PROJECT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_daily_board_project (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'AI项目主键ID',
    board_id BIGINT NOT NULL COMMENT '所属看板ID，关联ai_daily_board.id',
    client_id VARCHAR(80) NOT NULL COMMENT '前端生成的客户端项目ID',
    name VARCHAR(128) NOT NULL COMMENT '项目名称',
    status VARCHAR(16) NOT NULL DEFAULT '开发中' COMMENT '项目状态：待开启/开发中/已上线',
    focus VARCHAR(255) NOT NULL DEFAULT '' COMMENT '当前重点一句话',
    owner VARCHAR(64) NOT NULL DEFAULT '' COMMENT '项目负责人，为空表示本人',
    start_date DATE NULL COMMENT '项目开始日期',
    end_date DATE NULL COMMENT '项目结束日期',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '项目排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_project_board_client (board_id, client_id),
    KEY idx_ai_daily_project_board (board_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板项目表'
"""

_DAILY_LOG_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_daily_board_daily_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '每日推进记录主键ID',
    board_id BIGINT NOT NULL COMMENT '所属看板ID，关联ai_daily_board.id',
    log_date DATE NOT NULL COMMENT '记录所属日期',
    project_id VARCHAR(80) NOT NULL DEFAULT '' COMMENT '所属项目客户端ID，空表示总体推进',
    project_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '所属项目名称快照',
    work VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '今天做了什么',
    tomorrow VARCHAR(500) NOT NULL DEFAULT '' COMMENT '明天计划',
    risk_note VARCHAR(500) NOT NULL DEFAULT '' COMMENT '风险与阻塞',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_log_board_date_project (board_id, log_date, project_id),
    KEY idx_ai_daily_log_project (board_id, project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板每日推进记录表'
"""

_RISK_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_daily_board_risk (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '风险记录主键ID',
    board_id BIGINT NOT NULL COMMENT '所属看板ID，关联ai_daily_board.id',
    client_id VARCHAR(80) NOT NULL COMMENT '前端生成的客户端风险ID',
    risk VARCHAR(255) NOT NULL COMMENT '风险描述',
    project_id VARCHAR(80) NOT NULL DEFAULT '' COMMENT '所属项目客户端ID，空表示总体',
    project_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '所属项目名称快照',
    impact VARCHAR(16) NOT NULL DEFAULT '中' COMMENT '影响程度：高/中/低',
    owner VARCHAR(64) NOT NULL DEFAULT '' COMMENT '负责人',
    status VARCHAR(32) NOT NULL DEFAULT '待解决' COMMENT '状态：待解决/处理中/已解决',
    blocked_since DATE NULL COMMENT '阻塞开始日期，用于计算已阻塞天数',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '风险在列表中的排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_risk_board_client (board_id, client_id),
    KEY idx_ai_daily_risk_board (board_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板风险表'
"""

_ACTIVITY_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS ai_daily_board_activity (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '操作日志主键ID',
    board_key VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '所属看板标识',
    operator VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人',
    action VARCHAR(64) NOT NULL COMMENT '操作类型',
    target VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作对象（如项目名）',
    detail VARCHAR(500) NOT NULL DEFAULT '' COMMENT '操作详情',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (id),
    KEY idx_ai_daily_activity_board (board_key, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目进度看板操作日志表'
"""


def get_engine(engine: Engine | None = None) -> Engine:
    """返回调用方传入的引擎，未传入时按环境变量创建 MySQL 引擎。"""
    return engine or import_service.get_engine()


def ensure_schema(engine: Engine | None = None) -> None:
    """幂等创建看板五张表，并对存量库补充新列（迁移脚本与这里保持同构）。"""
    db_engine = get_engine(engine)
    with db_engine.begin() as conn:
        conn.execute(text(_BOARD_TABLE_DDL))
        conn.execute(text(_PROJECT_TABLE_DDL))
        conn.execute(text(_DAILY_LOG_TABLE_DDL))
        conn.execute(text(_RISK_TABLE_DDL))
        conn.execute(text(_ACTIVITY_TABLE_DDL))
        _upgrade_project(conn)
        _upgrade_daily_log(conn)
        _upgrade_risk(conn)


def add_activity(
    engine: Engine | None = None,
    board_key: str = DEFAULT_BOARD_KEY,
    operator: str = "",
    action: str = "",
    target: str = "",
    detail: str = "",
) -> None:
    """写入一条操作日志。"""
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ai_daily_board_activity (board_key, operator, action, target, detail)
                VALUES (:board_key, :operator, :action, :target, :detail)
                """
            ),
            {
                "board_key": board_key,
                "operator": str(operator or "")[:64],
                "action": str(action or "操作")[:64],
                "target": str(target or "")[:128],
                "detail": str(detail or "")[:500],
            },
        )


def list_activities(
    engine: Engine | None = None,
    board_key: str = DEFAULT_BOARD_KEY,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """按时间倒序返回最近的操作日志。"""
    db_engine = get_engine(engine)
    ensure_schema(db_engine)
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, operator, action, target, detail, created_at
                FROM ai_daily_board_activity
                WHERE board_key = :board_key
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {"board_key": board_key, "limit": int(limit)},
        ).mappings().all()
    result = []
    for row in rows:
        ts = row["created_at"]
        created = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts)
        result.append(
            {
                "id": int(row["id"]),
                "operator": str(row["operator"] or ""),
                "action": str(row["action"] or ""),
                "target": str(row["target"] or ""),
                "detail": str(row["detail"] or ""),
                "createdAt": created,
            }
        )
    return result


def _column_exists(conn: Any, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c
                """
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _upgrade_project(conn: Any) -> None:
    """早期 project 表补充新列。"""
    adds = {
        "focus": "VARCHAR(255) NOT NULL DEFAULT '' COMMENT '当前重点一句话'",
        "owner": "VARCHAR(64) NOT NULL DEFAULT '' COMMENT '项目负责人，为空表示本人'",
        "start_date": "DATE NULL COMMENT '项目开始日期'",
        "end_date": "DATE NULL COMMENT '项目结束日期'",
    }
    for name, ddl in adds.items():
        if not _column_exists(conn, "ai_daily_board_project", name):
            conn.execute(
                text(f"ALTER TABLE ai_daily_board_project ADD COLUMN {name} {ddl}")
            )


def _upgrade_daily_log(conn: Any) -> None:
    """早期 daily_log 表补充项目关联与 work/tomorrow 列，并移除废弃列。"""
    adds = {
        "project_id": "VARCHAR(80) NOT NULL DEFAULT '' COMMENT '所属项目客户端ID'",
        "project_name": "VARCHAR(128) NOT NULL DEFAULT '' COMMENT '所属项目名称快照'",
        "work": "VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '今天做了什么'",
        "tomorrow": "VARCHAR(500) NOT NULL DEFAULT '' COMMENT '明天计划'",
    }
    for name, ddl in adds.items():
        if not _column_exists(conn, "ai_daily_board_daily_log", name):
            conn.execute(
                text(f"ALTER TABLE ai_daily_board_daily_log ADD COLUMN {name} {ddl}")
            )
    # 移除早期 NOT NULL 且无效的古列，避免插入时报"无默认值"
    for name in ("completed", "effect_change", "problems", "tomorrow_plan"):
        if _column_exists(conn, "ai_daily_board_daily_log", name):
            conn.execute(
                text(f"ALTER TABLE ai_daily_board_daily_log DROP COLUMN {name}")
            )
    # 支持一天多条推进记录（每个任务/项目一条独立记录）：
    # 旧的"一天一条"唯一键 (board_id, log_date) 无法保留多条，改为 (board_id, log_date, project_id)。
    if _index_exists(conn, "ai_daily_board_daily_log", "uk_ai_daily_log_board_date"):
        conn.execute(
            text(
                "ALTER TABLE ai_daily_board_daily_log "
                "DROP INDEX uk_ai_daily_log_board_date"
            )
        )
    if not _index_exists(
        conn, "ai_daily_board_daily_log", "uk_ai_daily_log_board_date_project"
    ):
        conn.execute(
            text(
                "ALTER TABLE ai_daily_board_daily_log "
                "ADD UNIQUE KEY uk_ai_daily_log_board_date_project "
                "(board_id, log_date, project_id)"
            )
        )


def _index_exists(conn: Any, table: str, index_name: str) -> bool:
    """判断某张表的某个索引是否已存在。"""
    return bool(
        conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :t AND index_name = :i
                """
            ),
            {"t": table, "i": index_name},
        ).scalar()
    )


def _default_settings() -> dict[str, Any]:
    return {
        "boardTitle": DEFAULT_BOARD_TITLE,
        "currentDate": date.today().isoformat(),
        "showCharts": True,
        "showStandup": True,
        "showTimeline": True,
        "showTable": True,
    }


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _flag(value: Any) -> int:
    return 1 if value else 0


def _blocked_days(blocked_since: Any) -> int:
    """根据阻塞开始日期计算已阻塞天数（最少 1 天）。"""
    start = _parse_date(blocked_since)
    if start is None:
        return 0
    delta = (date.today() - start).days
    return max(1, delta)


def _upgrade_risk(conn: Any) -> None:
    """早期 risk 表补充所属项目列。"""
    adds = {
        "project_id": "VARCHAR(80) NOT NULL DEFAULT '' COMMENT '所属项目客户端ID，空表示总体'",
        "project_name": "VARCHAR(128) NOT NULL DEFAULT '' COMMENT '所属项目名称快照'",
    }
    for name, ddl in adds.items():
        if not _column_exists(conn, "ai_daily_board_risk", name):
            conn.execute(
                text(f"ALTER TABLE ai_daily_board_risk ADD COLUMN {name} {ddl}")
            )


def _date_text(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if value:
        return str(value)[:10]
    return ""


def get_board_state(
    engine: Engine | None = None,
    board_key: str = DEFAULT_BOARD_KEY,
    target_date: str | None = None,
) -> dict[str, Any]:
    """读取项目、指定日期的每日推进记录、日报日期列表与风险。

    target_date 缺省时返回看板当前日期的日报。
    """
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    with db_engine.connect() as conn:
        board = conn.execute(
            text(
                """
                SELECT id, board_title, `current_date`, show_charts, show_standup,
                       show_timeline, show_table
                FROM ai_daily_board
                WHERE board_key = :board_key
                LIMIT 1
                """
            ),
            {"board_key": board_key},
        ).mappings().one_or_none()

        if board is None:
            return {
                "settings": _default_settings(),
                "projects": [],
                "dailyLogs": [],
                "dailyLogDates": [],
                "risks": [],
                "weekLogs": [],
                "allLogs": [],
            }
        board_id = int(board["id"])
        record_date = _parse_date(target_date) or board["current_date"]

        project_rows = conn.execute(
            text(
                """
                SELECT client_id, name, status, focus, owner, start_date, end_date
                FROM ai_daily_board_project
                WHERE board_id = :board_id
                ORDER BY sort_order, id
                """
            ),
            {"board_id": board_id},
        ).mappings().all()

        daily_log_rows = conn.execute(
            text(
                """
                SELECT project_id, project_name, work, tomorrow, risk_note
                FROM ai_daily_board_daily_log
                WHERE board_id = :board_id AND log_date = :record_date
                ORDER BY id
                """
            ),
            {"board_id": board_id, "record_date": record_date},
        ).mappings().all()

        daily_log_date_rows = conn.execute(
            text(
                """
                SELECT DISTINCT log_date
                FROM ai_daily_board_daily_log
                WHERE board_id = :board_id
                ORDER BY log_date DESC
                """
            ),
            {"board_id": board_id},
        ).scalars().all()

        risk_rows = conn.execute(
            text(
                """
                SELECT client_id, risk, project_id, project_name, impact, owner, status, blocked_since
                FROM ai_daily_board_risk
                WHERE board_id = :board_id
                ORDER BY sort_order, id
                """
            ),
            {"board_id": board_id},
        ).mappings().all()

        # 本周全部推进记录（周一至周日），用于前端按项目汇总"本周做了什么"
        week_start = board["current_date"] - timedelta(
            days=board["current_date"].weekday()
        )
        week_end = week_start + timedelta(days=6)
        week_rows = conn.execute(
            text(
                """
                SELECT log_date, project_id, project_name, work, tomorrow, risk_note
                FROM ai_daily_board_daily_log
                WHERE board_id = :board_id AND log_date BETWEEN :week_start AND :week_end
                ORDER BY log_date, id
                """
            ),
            {
                "board_id": board_id,
                "week_start": week_start,
                "week_end": week_end,
            },
        ).mappings().all()

        all_log_rows = conn.execute(
            text(
                """
                SELECT log_date, project_id, project_name, work, tomorrow, risk_note
                FROM ai_daily_board_daily_log
                WHERE board_id = :board_id
                ORDER BY log_date DESC, id DESC
                """
            ),
            {"board_id": board_id},
        ).mappings().all()

    projects = [
        {
            "id": str(row["client_id"]),
            "name": str(row["name"] or ""),
            "status": str(row["status"] or "开发中"),
            "focus": str(row["focus"] or ""),
            "owner": str(row["owner"] or ""),
            "startDate": _date_text(row["start_date"]),
            "endDate": _date_text(row["end_date"]),
        }
        for row in project_rows
    ]

    risks = [
        {
            "id": str(row["client_id"]),
            "risk": str(row["risk"] or ""),
            "projectId": str(row["project_id"] or ""),
            "projectName": str(row["project_name"] or ""),
            "impact": str(row["impact"] or "中"),
            "owner": str(row["owner"] or ""),
            "status": str(row["status"] or "待解决"),
            "blockedSince": _date_text(row["blocked_since"]),
            "blockedDays": _blocked_days(row["blocked_since"]),
        }
        for row in risk_rows
    ]

    daily_logs = [
        {
            "projectId": str(row["project_id"] or ""),
            "projectName": str(row["project_name"] or ""),
            "work": str(row["work"] or ""),
            "tomorrow": str(row["tomorrow"] or ""),
            "risks": str(row["risk_note"] or ""),
        }
        for row in daily_log_rows
    ]

    settings = {
        "boardTitle": str(board["board_title"] or DEFAULT_BOARD_TITLE),
        "currentDate": _date_text(board["current_date"]),
        "showCharts": bool(board["show_charts"]),
        "showStandup": bool(board["show_standup"]),
        "showTimeline": bool(board["show_timeline"]),
        "showTable": bool(board["show_table"]),
    }
    week_logs = [
        {
            "logDate": _date_text(row["log_date"]),
            "projectId": str(row["project_id"] or ""),
            "projectName": str(row["project_name"] or ""),
            "work": str(row["work"] or ""),
            "tomorrow": str(row["tomorrow"] or ""),
            "risks": str(row["risk_note"] or ""),
        }
        for row in week_rows
    ]
    all_logs = [
        {
            "logDate": _date_text(row["log_date"]),
            "projectId": str(row["project_id"] or ""),
            "projectName": str(row["project_name"] or ""),
            "work": str(row["work"] or ""),
            "tomorrow": str(row["tomorrow"] or ""),
            "risks": str(row["risk_note"] or ""),
        }
        for row in all_log_rows
    ]
    return {
        "settings": settings,
        "projects": projects,
        "dailyLogs": daily_logs,
        "dailyLogDates": [_date_text(day) for day in daily_log_date_rows],
        "risks": risks,
        "weekLogs": week_logs,
        "allLogs": all_logs,
    }


def save_board_state(
    payload: dict[str, Any],
    engine: Engine | None = None,
    board_key: str = DEFAULT_BOARD_KEY,
) -> dict[str, Any]:
    """保存项目与风险（整体替换），并按日期覆盖当天的每日推进记录。"""
    db_engine = get_engine(engine)
    ensure_schema(db_engine)

    settings = payload.get("settings") or {}
    projects = payload.get("projects") or []
    risks = payload.get("risks") or []
    daily_logs = payload.get("dailyLogs")
    # 兼容旧结构：若未提供 dailyLogs，或 dailyLogs 为空但提交了单条 dailyLog，则视为一条记录
    single = payload.get("dailyLog") or {}
    if not daily_logs and single:
        daily_logs = [single] if str(single.get("work") or "").strip() else []
    daily_logs = daily_logs or []
    current_date = _parse_date(settings.get("currentDate")) or date.today()
    board_params = {
        "board_key": board_key,
        "board_title": str(settings.get("boardTitle") or DEFAULT_BOARD_TITLE)[:128],
        "current_date": current_date,
        "show_charts": _flag(settings.get("showCharts", True)),
        "show_standup": _flag(settings.get("showStandup", True)),
        "show_timeline": _flag(settings.get("showTimeline", True)),
        "show_table": _flag(settings.get("showTable", True)),
    }

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT IGNORE INTO ai_daily_board (
                    board_key, board_title, `current_date`,
                    show_charts, show_standup, show_timeline, show_table
                ) VALUES (
                    :board_key, :board_title, :current_date,
                    :show_charts, :show_standup, :show_timeline, :show_table
                )
                """
            ),
            board_params,
        )
        board_id = conn.execute(
            text("SELECT id FROM ai_daily_board WHERE board_key = :board_key LIMIT 1"),
            {"board_key": board_key},
        ).scalar_one()
        conn.execute(
            text(
                """
                UPDATE ai_daily_board SET
                    board_title = :board_title,
                    `current_date` = :current_date,
                    show_charts = :show_charts,
                    show_standup = :show_standup,
                    show_timeline = :show_timeline,
                    show_table = :show_table
                WHERE id = :board_id
                """
            ),
            {**board_params, "board_id": board_id},
        )

        # 项目：整体替换
        conn.execute(
            text("DELETE FROM ai_daily_board_project WHERE board_id = :board_id"),
            {"board_id": board_id},
        )
        project_insert = text(
            """
            INSERT INTO ai_daily_board_project (
                board_id, client_id, name, status, focus, owner,
                start_date, end_date, sort_order
            ) VALUES (
                :board_id, :client_id, :name, :status, :focus, :owner,
                :start_date, :end_date, :sort_order
            )
            """
        )
        for sort_order, project in enumerate(projects):
            conn.execute(
                project_insert,
                {
                    "board_id": board_id,
                    "client_id": str(
                        project.get("id")
                        or f"project-{sort_order + 1}-{time.time_ns()}"
                    )[:80],
                    "name": str(project.get("name") or "")[:128],
                    "status": str(project.get("status") or "开发中")[:16],
                    "focus": str(project.get("focus") or "")[:255],
                    "owner": str(project.get("owner") or "")[:64],
                    "start_date": _parse_date(project.get("startDate")),
                    "end_date": _parse_date(project.get("endDate")),
                    "sort_order": sort_order,
                },
            )

        # 风险：整体替换
        conn.execute(
            text("DELETE FROM ai_daily_board_risk WHERE board_id = :board_id"),
            {"board_id": board_id},
        )
        risk_insert = text(
            """
            INSERT INTO ai_daily_board_risk (
                board_id, client_id, risk, project_id, project_name,
                impact, owner, status, blocked_since, sort_order
            ) VALUES (
                :board_id, :client_id, :risk, :project_id, :project_name,
                :impact, :owner, :status, :blocked_since, :sort_order
            )
            """
        )
        for sort_order, item in enumerate(risks):
            risk_text = str(item.get("risk") or "").strip()[:255]
            if not risk_text:
                continue
            conn.execute(
                risk_insert,
                {
                    "board_id": board_id,
                    "client_id": str(
                        item.get("id") or f"risk-{sort_order + 1}-{time.time_ns()}"
                    )[:80],
                    "risk": risk_text,
                    "project_id": str(item.get("projectId") or "")[:80],
                    "project_name": str(item.get("projectName") or "")[:128],
                    "impact": str(item.get("impact") or "中")[:16],
                    "owner": str(item.get("owner") or "")[:64],
                    "status": str(item.get("status") or "待解决")[:32],
                    "blocked_since": _parse_date(item.get("blockedSince")),
                    "sort_order": sort_order,
                },
            )

        # 每日推进记录：每天可有多条相互独立的记录（每个任务/项目一条），
        # 整体按日期替换当天记录，避免多次保存互相覆盖丢失。
        conn.execute(
            text(
                """
                DELETE FROM ai_daily_board_daily_log
                WHERE board_id = :board_id AND log_date = :log_date
                """
            ),
            {"board_id": board_id, "log_date": current_date},
        )
        daily_log_insert = text(
            """
            INSERT INTO ai_daily_board_daily_log (
                board_id, log_date, project_id, project_name, work, tomorrow, risk_note
            ) VALUES (
                :board_id, :log_date, :project_id, :project_name, :work, :tomorrow, :risk_note
            )
            """
        )
        for raw in daily_logs:
            item = raw or {}
            work = str(item.get("work") or "")
            if not work.strip():
                continue
            conn.execute(
                daily_log_insert,
                {
                    "board_id": board_id,
                    "log_date": current_date,
                    "project_id": str(item.get("projectId") or "")[:80],
                    "project_name": str(item.get("projectName") or "")[:128],
                    "work": work,
                    "tomorrow": str(item.get("tomorrow") or "")[:500],
                    "risk_note": str(item.get("risks") or "")[:500],
                },
            )

    return get_board_state(engine=db_engine, board_key=board_key)
