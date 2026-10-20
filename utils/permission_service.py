"""页面查看权限管理服务（覆盖全部业务页面）。

页面权限模型（可在「权限管理」后台配置，仅 admin/管理员 可修改）：
- 管控范围：全部业务页面（人力资源、AI 项目看板、库存决策、客服/售后看板、AI 知识问答等）；
- 权限粒度：按角色（sys_user.role）配置，角色支持特殊值 "*" 表示所有人可见；
- 管理入口 sys-permissions 仅 admin/管理员 可见（前端 + 接口双重控制）。

配置存储于 MySQL 表 sys_page_permission（page_key -> roles JSON 数组）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Engine, text

from utils.import_service import get_engine

# 所有人可见的特殊角色值
ALL_ROLES = "*"

# 店铺报表快照路径（与 shop_report_routes.py 保持一致）
SHOP_REPORT_SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "shop_report.json"

_SHOP_CHANNEL_LABELS = {"self": "自营", "pop": "POP", "store": "线下"}

# 可配置的页面（page_key -> 中文名），覆盖全部业务页面
PAGE_DEFS: dict[str, str] = {
    "ecommerce-dashboard": "经营看板首页",
    "insight": "经营总览",
    "insight-trend": "趋势分析",
    "insight-category": "品类分析",
    "insight-brand": "品牌与商品",
    "shop-report": "店铺报表",
    "shop-report-chat": "店铺报表 AI 问答",
    # 人力资源
    "hr-driver": "人事驾驶舱",
    "hr-roster": "人员花名册",
    "hr-recruit": "招聘管理",
    "hr-knowledge": "人力行政知识库",
    "hr-filter": "AI 智能简历筛选",
    # 设计部
    "design-overview": "设计资料总览",
    "design-models": "AI模特与场景案例",
    "design-prompts": "AI生图提示词库",
    "design-comparisons": "生图前后对照",
    "design-styles": "视觉要素手册",
    # 其他业务页面
    "ai-project-board": "AI 项目进度看板",
    "operating-analysis": "经营数据分析",
    "operating-chat": "AI 经营问答",
    "sku-return-data": "SKU 退货数据",
    "inventory-decision": "库存分析决策",
    "inventory-monitor": "库存看板监控",
    "inventory-stockout": "库存断货数据",
    "inventory-shortage": "库存缺货数据",
    "inventory-listed": "库存上柜数据",
    "inventory-delisted": "库存下柜数据",
    "jushuitan-dashboard": "商品库存看板",
    "sales-dashboard": "销售数据看板",
    "inventory-product-dashboard": "进销商品看板",
    "purchase-order-dashboard": "采购单看板",
    "cs-audit": "客服数据看板",
    "after-sales-quality": "售后质量分析",
    "product-quality-reports": "产品质检报告",
    "knowledge-qa": "AI 知识问答",
    "points": "积分排行榜",
    "points-rule": "积分规则",
    "points-log": "积分明细",
}

# 每页默认可见角色（默认一律为空：不预选任何角色，由管理员在权限后台自行设计；
# 仅对缺失的页面生效，绝不覆盖已保存的配置）
PERM_DEFAULTS: dict[str, list[str]] = {key: [] for key in (
    "ecommerce-dashboard", "insight", "insight-trend", "insight-category", "insight-brand", "shop-report",
    "hr-driver", "hr-roster", "hr-recruit", "hr-knowledge", "hr-filter",
    "design-overview", "design-models", "design-prompts", "design-comparisons", "design-styles",
    "ai-project-board", "inventory-decision", "inventory-monitor", "inventory-product-dashboard", "jushuitan-dashboard", "purchase-order-dashboard", "sales-dashboard", "cs-audit",
    "inventory-stockout", "inventory-shortage", "inventory-listed", "inventory-delisted",
    "after-sales-quality", "knowledge-qa", "points", "points-rule", "points-log",
)}
# 库存看板监控是运营部入口，首次升级时默认向已有运营人员开放。
PERM_DEFAULTS["inventory-monitor"] = [ALL_ROLES]
PERM_DEFAULTS["operating-chat"] = ['admin', '管理员', 'operator', 'boss']
PERM_DEFAULTS["sku-return-data"] = list(PERM_DEFAULTS["operating-chat"])
PERM_DEFAULTS["operating-analysis"] = ['admin', '管理员', 'operator', 'boss']
for _insight_key in ("insight", "insight-trend", "insight-category", "insight-brand"):
    PERM_DEFAULTS[_insight_key] = list(PERM_DEFAULTS["operating-analysis"])
PERM_DEFAULTS["shop-report"] = list(PERM_DEFAULTS["operating-analysis"])
for _metric_key in ("inventory-stockout", "inventory-shortage", "inventory-listed", "inventory-delisted"):
    PERM_DEFAULTS[_metric_key] = [ALL_ROLES]
PERM_DEFAULTS["jushuitan-dashboard"] = [ALL_ROLES]
PERM_DEFAULTS["sales-dashboard"] = [ALL_ROLES]
PERM_DEFAULTS["inventory-product-dashboard"] = [ALL_ROLES]
PERM_DEFAULTS["purchase-order-dashboard"] = [ALL_ROLES]
PERM_DEFAULTS["ecommerce-dashboard"] = [ALL_ROLES]
# 共享产品资料默认供所有登录员工查询，管理员可按页面收窄访问范围。
PERM_DEFAULTS["product-quality-reports"] = [ALL_ROLES]
for _points_key in ("points", "points-rule", "points-log"):
    PERM_DEFAULTS[_points_key] = [ALL_ROLES]
# 设计资料此前对所有已登录用户开放，新增可配置项时保留原访问范围。
for _design_key in ("design-overview", "design-models", "design-prompts", "design-comparisons", "design-styles"):
    PERM_DEFAULTS[_design_key] = [ALL_ROLES]

# 管理角色：可进入权限管理后台
ADMIN_ROLES: tuple[str, ...] = ("admin", "管理员")

# 角色中文名（管理后台展示用）
ROLE_LABELS: dict[str, str] = {
    "admin": "管理员",
    "管理员": "管理员",
    "hr": "HR专员",
    "boss": "总经理/副总",
    "designer": "设计师",
    "finance": "财务",
    "operator": "运营/客服",
    "supply": "供应链",
    "user": "普通员工",
}

# 页签级（页面内容）权限定义：page_key -> {sub_key: 中文名}。
# 用于在页面内按席位隐藏局部内容（目前仅库存分析决策页签需要控制，
# 后续其他页面有内容级权限需求时可在此扩展，无需改动读取/保存逻辑）。
SUB_PERM_DEFS: dict[str, dict[str, str]] = {
    "inventory-decision": {
        # 顺序与页面 tab 视觉顺序保持一致：默认 tab 在前，受控页签在后
        "forecast": "经营趋势预测",
        "purchase-export": "补货导出明细",
        "sku-warning": "SKU库存预警",
        "plans": "今日调拨建议",
        "sku-decision": "SKU补货决策",
        "settings": "库存分析设置",
        "cities": "城市库存健康度",
        "simulate": "单SKU调拨模拟",
    },
}

# 页签级权限默认可见角色：默认空 = 对所有角色/人员隐藏，由管理员在权限后台配置。
# （与页面级默认策略一致：只对缺失配置生效，绝不覆盖已保存的数据。）
SUB_PERM_DEFAULTS: dict[tuple[str, str], list[str]] = {
    (page_key, sub_key): []
    for page_key, subs in SUB_PERM_DEFS.items()
    for sub_key in subs
}


# ── 动态店铺报表页面（按店铺粒度授权） ──────────────────────────────────────
# 店铺列表来自 data/shop_report.json 快照，与前端侧边栏「店铺报表」展开的子项一一对应。
# page_key = "shop-report:{channel}:{shop_id}"，label = "自营 · 测试箱包" 等。
# 保留静态 "shop-report" 作为模块总入口；具体店铺首次落库时继承 "shop-report" 的现有权限，
# 升级后原访问范围不变，管理员再在权限后台按店铺收窄。

def load_shop_report_shops() -> list[dict[str, str]]:
    """读取店铺报表快照中的店铺清单；快照缺失或异常时返回空列表（不阻塞权限管理）。"""
    try:
        data = json.loads(SHOP_REPORT_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    raw = data.get("shops") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    shops: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        channel = str(item.get("channel") or "").strip()
        shop_id = str(item.get("shop_id") or "").strip()
        shop_name = str(item.get("shop_name") or "").strip()
        if channel and shop_id and shop_name:
            shops.append({"channel": channel, "shop_id": shop_id, "shop_name": shop_name})
    return shops


def shop_page_defs() -> dict[str, str]:
    """动态生成每个店铺对应的 page_key -> 中文名。"""
    out: dict[str, str] = {}
    for shop in load_shop_report_shops():
        channel_label = _SHOP_CHANNEL_LABELS.get(shop["channel"], shop["channel"])
        out[f"shop-report:{shop['channel']}:{shop['shop_id']}"] = (
            f"{channel_label} · {shop['shop_name']}"
        )
    return out


def all_page_defs() -> dict[str, str]:
    """全部可授权页面（静态 PAGE_DEFS + 动态店铺），保持稳定顺序。

    动态店铺插入在静态 "shop-report" / "shop-report-chat" 之后、人力资源页之前，
    与前端侧边栏分组位置一致。
    """
    shops = shop_page_defs()
    if not shops:
        return dict(PAGE_DEFS)
    out: dict[str, str] = {}
    inserted = False
    for key, label in PAGE_DEFS.items():
        out[key] = label
        if key == "shop-report-chat" and not inserted:
            out.update(shops)
            inserted = True
    if not inserted:
        # 静态定义里没有 shop-report-chat 时兜底追加到末尾
        out.update(shops)
    return out


def _ensure_page_permissions(conn: Any) -> None:
    """建表（幂等）并为缺失页面补默认配置，不覆盖已有配置。"""
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS sys_page_permission (
          page_key VARCHAR(128) PRIMARY KEY,
          roles TEXT NOT NULL,
          updated_at DATETIME NULL
        )
        """
    ))
    all_defs = all_page_defs()
    for key in all_defs:
        defaults = list(PERM_DEFAULTS.get(key, []))
        source = {
            "operating-analysis": "inventory-decision",
            "operating-chat": "operating-analysis",
            "sku-return-data": "operating-chat",
            "insight": "operating-analysis",
            "insight-trend": "operating-analysis",
            "insight-category": "operating-analysis",
            "insight-brand": "operating-analysis",
            "shop-report": "operating-analysis",
            "inventory-stockout": "inventory-monitor",
            "inventory-shortage": "inventory-monitor",
            "inventory-listed": "inventory-monitor",
            "inventory-delisted": "inventory-monitor",
        }.get(key)
        # 动态店铺 key 首次落库时继承静态 "shop-report" 的现有角色，保证升级后访问范围不变。
        if not source and key.startswith("shop-report:"):
            source = "shop-report"
        if source:
            # 新页面首次继承原页面的访问范围，已有配置不受影响。
            existing = conn.execute(text(
                "SELECT roles FROM sys_page_permission WHERE page_key = :source"
            ), {"source": source}).scalar()
            if existing:
                try:
                    defaults = json.loads(existing)
                except (ValueError, TypeError):
                    pass
        conn.execute(
            text(
                "INSERT IGNORE INTO sys_page_permission (page_key, roles, updated_at) "
                "VALUES (:k, :r, :t)"
            ),
            {
                "k": key,
                "r": json.dumps(defaults, ensure_ascii=False),
                "t": datetime.now(),
            },
        )


def get_page_permissions(engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    """读取全部页面权限配置。"""
    engine = engine or get_engine()
    with engine.begin() as conn:
        _ensure_page_permissions(conn)
        rows = conn.execute(text("SELECT page_key, roles FROM sys_page_permission")).all()
    result = []
    for r in rows:
        try:
            roles = json.loads(r.roles or "[]")
        except (ValueError, TypeError):
            roles = list(PERM_DEFAULTS.get(str(r.page_key), ["admin", "hr"]))
        result.append({"page_key": str(r.page_key), "roles": roles})
    return result


def get_all_roles(engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    """返回 sys_user 实际角色清单，附带中文名与代表用户名（管理后台展示用）。"""
    engine = engine or get_engine()
    rows = []
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT role, username, real_name FROM sys_user "
            "WHERE role IS NOT NULL AND role <> '' ORDER BY role"
        )).all()
    by_role: dict[str, dict[str, str]] = {}
    for role, username, real_name in rows:
        key = str(role).strip()
        if key not in by_role:
            by_role[key] = {"role": key, "username": "", "real_name": ""}
        # 取每个角色第一个用户作为代表（保持可读）
        if not by_role[key]["username"]:
            by_role[key]["username"] = str(username or "")
            by_role[key]["real_name"] = str(real_name or "")
    # 保证 admin / hr 在选项中
    for base in ("admin", "hr"):
        if base not in by_role:
            by_role[base] = {"role": base, "username": "", "real_name": ""}
    result = []
    for item in by_role.values():
        item["label"] = ROLE_LABELS.get(item["role"], item["role"])
        result.append(item)
    return sorted(result, key=lambda r: (r["role"] != "admin", r["role"] != "hr", r["role"]))


def get_all_users(engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    """返回实际可登录账号，授权键使用账号，避免同名员工共享权限。"""
    engine = engine or get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT username, real_name, department, job_title, role FROM sys_user "
            "ORDER BY department, real_name, username"
        )).all()
    return [
        {
            "username": "account:" + str(r.username or "").strip(),
            "real_name": str(r.real_name or "").strip(),
            "emp_no": str(r.username or "").strip(),
            "department": str(r.department or "").strip(),
            "job_title": str(r.job_title or "").strip(),
            "role": str(r.role or "").strip(),
        }
        for r in rows
    ]


def legacy_name_if_unique(engine: Optional[Engine], real_name: str) -> str:
    """兼容旧姓名授权；同名账号不沿用以免相互继承权限。"""
    name = (real_name or "").strip()
    if not name:
        return ""
    engine = engine or get_engine()
    with engine.connect() as conn:
        count = conn.execute(text(
            "SELECT COUNT(*) FROM sys_user WHERE real_name = :name"
        ), {"name": name}).scalar()
    return name if int(count or 0) == 1 else ""


def can_delete_design_item(user: dict[str, Any], engine: Optional[Engine] = None) -> bool:
    """Allow design deletion to admins and the two named, unique sys_user accounts."""
    if str(user.get("role") or "").strip().lower() == "admin":
        return True
    name = str(user.get("real_name") or "").strip()
    return name in {"聂悠悠", "曾浠洋"} and legacy_name_if_unique(engine, name) == name


def allowed_page_keys(engine: Optional[Engine], role: str, personal_key: str = "", account_key: str = "") -> list[str]:
    """返回指定角色/人员可见的页面 key 列表。

    - roles 配置含 "*" 的页面所有人可见；
    - 其余按小写匹配：命中 role（按角色授权）或 personal_key（按个人授权，
      权限后台个人勾选的键为员工姓名）。
    """
    role = (role or "").strip().lower()
    personal_key = (personal_key or "").strip().lower()
    account_key = (account_key or "").strip().lower()
    perms = get_page_permissions(engine)
    all_defs = all_page_defs()
    allowed = []
    for p in perms:
        key = str(p.get("page_key") or "")
        # 只认已注册页面（静态 PAGE_DEFS + 动态店铺）；数据库里残留的旧页面键
        # 不再参与授权，避免孤儿配置影响访问。
        if key not in all_defs:
            continue
        roles = {str(x).strip().lower() for x in p.get("roles", [])}
        if ALL_ROLES in roles or role in roles or (personal_key and personal_key in roles) or (account_key and account_key in roles):
            allowed.append(key)
    return allowed


def save_page_permissions(
    engine: Optional[Engine],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """保存页面权限配置。

    - 只更新提交的页面；
    - roles 含 "*" 时整页存为 ["*"]（所有人可见）；
    - 其余角色数组照单保存（含空数组 = 该页暂不对任何角色开放），
      不做任何强制注入，完全由管理员自行设计。
    """
    engine = engine or get_engine()
    now = datetime.now()
    all_defs = all_page_defs()
    with engine.begin() as conn:
        _ensure_page_permissions(conn)
        for item in updates or []:
            key = str(item.get("page_key") or "").strip()
            if key not in all_defs:
                continue
            raw = item.get("roles")
            if not isinstance(raw, list):
                continue
            roles = [str(x).strip() for x in raw if str(x).strip()]
            if ALL_ROLES in roles:
                roles = [ALL_ROLES]
            roles = sorted(set(roles), key=lambda x: (x != ALL_ROLES, x != "admin", x != "管理员", x))
            conn.execute(
                text(
                    "UPDATE sys_page_permission SET roles = :r, updated_at = :t "
                    "WHERE page_key = :k"
                ),
                {"k": key, "r": json.dumps(roles, ensure_ascii=False), "t": now},
            )
    return get_page_permissions(engine)


# ── 页签级（页面内容）权限 ─────────────────────────────────────────────────────


def _ensure_subpage_permissions(conn: Any) -> None:
    """建表（幂等）并为缺失页签补默认配置，不覆盖已有配置。"""
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS sys_subpage_permission (
          page_key VARCHAR(64) NOT NULL,
          sub_key VARCHAR(64) NOT NULL,
          roles TEXT NOT NULL,
          updated_at DATETIME NULL,
          PRIMARY KEY (page_key, sub_key)
        )
        """
    ))
    for (page_key, sub_key), roles in SUB_PERM_DEFAULTS.items():
        conn.execute(
            text(
                "INSERT IGNORE INTO sys_subpage_permission "
                "(page_key, sub_key, roles, updated_at) VALUES (:pk, :sk, :r, :t)"
            ),
            {
                "pk": page_key,
                "sk": sub_key,
                "r": json.dumps(roles, ensure_ascii=False),
                "t": datetime.now(),
            },
        )


def get_subpage_permissions(
    engine: Optional[Engine] = None,
    page_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """读取页签级权限配置。

    始终以 SUB_PERM_DEFS 全量清单为主体合并数据库记录：任一页签即使没有
    数据库行（首次部署/种子行未落库）也会返回默认角色，保证读取完整且不丢已保存配置。
    """
    engine = engine or get_engine()
    with engine.begin() as conn:
        _ensure_subpage_permissions(conn)
        sql = "SELECT page_key, sub_key, roles FROM sys_subpage_permission"
        params: dict[str, Any] = {}
        if page_key:
            sql += " WHERE page_key = :pk"
            params["pk"] = page_key
        rows = conn.execute(text(sql), params).all()
    saved: dict[tuple[str, str], list[str]] = {}
    for r in rows:
        try:
            saved[(str(r.page_key), str(r.sub_key))] = json.loads(r.roles or "[]")
        except (ValueError, TypeError):
            saved[(str(r.page_key), str(r.sub_key))] = []
    result: list[dict[str, Any]] = []
    for pk, subs in SUB_PERM_DEFS.items():
        if page_key and pk != page_key:
            continue
        for sk in subs:
            roles = saved.get((pk, sk), list(SUB_PERM_DEFAULTS.get((pk, sk), [])))
            result.append({"page_key": pk, "sub_key": sk, "roles": roles})
    return result


def allowed_subpage_keys(
    engine: Optional[Engine],
    page_key: str,
    role: str,
    personal_key: str = "",
    account_key: str = "",
) -> list[str]:
    """返回指定角色/人员对某页面内容（页签）可见的 sub_key 列表。

    语义与 allowed_page_keys 一致：
    - 该页签 roles 配置含 "*" 则所有人可见；
    - 其余按小写匹配 role（按角色授权）或 personal_key（按个人授权，员工姓名）。
    """
    role = (role or "").strip().lower()
    personal_key = (personal_key or "").strip().lower()
    account_key = (account_key or "").strip().lower()
    perms = [
        p for p in get_subpage_permissions(engine, page_key=page_key)
        if p.get("page_key") == page_key
    ]
    allowed = []
    for p in perms:
        sub_key = str(p.get("sub_key") or "")
        roles = {str(x).strip().lower() for x in p.get("roles", [])}
        if ALL_ROLES in roles or role in roles or (personal_key and personal_key in roles) or (account_key and account_key in roles):
            allowed.append(sub_key)
    return allowed


def save_subpage_permissions(
    engine: Optional[Engine],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """保存页签级权限配置。

    - 只更新提交且存在于 SUB_PERM_DEFS 的页签；
    - roles 含 "*" 时整项存为 ["*"]（所有人可见）；
    - 空数组 = 该页签对所有角色/人员隐藏；
    - 使用 UPSERT 写入，避免依赖种子行是否已落库。
    """
    engine = engine or get_engine()
    now = datetime.now()
    with engine.begin() as conn:
        _ensure_subpage_permissions(conn)
        for item in updates or []:
            pk = str(item.get("page_key") or "").strip()
            sk = str(item.get("sub_key") or "").strip()
            subs = SUB_PERM_DEFS.get(pk)
            if subs is None or sk not in subs:
                continue
            raw = item.get("roles")
            if not isinstance(raw, list):
                continue
            roles = [str(x).strip() for x in raw if str(x).strip()]
            if ALL_ROLES in roles:
                roles = [ALL_ROLES]
            roles = sorted(set(roles), key=lambda x: (x != ALL_ROLES, x != "admin", x != "管理员", x))
            conn.execute(
                text(
                    "INSERT INTO sys_subpage_permission (page_key, sub_key, roles, updated_at) "
                    "VALUES (:pk, :sk, :r, :t) "
                    "ON DUPLICATE KEY UPDATE roles = VALUES(roles), updated_at = VALUES(updated_at)"
                ),
                {"pk": pk, "sk": sk, "r": json.dumps(roles, ensure_ascii=False), "t": now},
            )
    return get_subpage_permissions(engine)
