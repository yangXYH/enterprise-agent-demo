"""Parameterized queries over the shop-report snapshot, facts and evidence.

The snapshot is a small flat table (one row per shop-month).  Queries filter
by month range, channel/shop and metric, then group by shop/month/channel or
aggregate to a total, and optionally compare with the preceding period (环比)
or the same period a year earlier (同比).  All numbers are recomputed from the
source fields with the same formulas as ``tools/export_shop_report.py`` so the
AI answers always agree with the page.
"""
from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

from utils import shop_report_service as service

CORE_LABELS = {
    "revenue": "收入", "costG": "产品成本", "rentAlloc": "房租分摊",
    "gross_profit": "毛利", "total_fees": "费用合计",
    "product_profit": "产品净利润", "net_profit": "项目净利",
    "gross_rate": "毛利率", "fee_rate": "费用率", "net_rate": "净利率",
}
RATE_METRICS = {"gross_rate", "fee_rate", "net_rate"}
GROUP_LABELS = {"total": "汇总", "shop": "店铺", "month": "月份", "channel": "渠道", "fee": "费用项"}


class ShopQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^Q[1-6]$")
    title: str = Field(min_length=1, max_length=140)
    start: str = Field(pattern=r"^\d{4}-\d{2}$")   # YYYY-MM
    end: str = Field(pattern=r"^\d{4}-\d{2}$")
    shop_name: str = Field("", max_length=120)      # 名称包含匹配，用于同品牌多店
    channel: str = Field("", max_length=12)         # self/pop/store/空
    shop_id: str = Field("", max_length=64)         # 精确店铺（与 channel 组合）
    metric: str = Field("net_profit", max_length=64)
    group: Literal["total", "shop", "month", "channel", "fee"] = "total"
    order: Literal["desc", "asc"] = "desc"
    limit: int = Field(10, ge=1, le=30)
    sign: Literal["", "positive", "negative"] = ""
    comparisons: list[Literal["mom", "yoy"]] = Field(default_factory=list, max_length=2)
    drivers: bool = False


class ShopPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["lookup", "ranking", "trend", "comparison", "diagnosis", "fee", "overview", "clarification"]
    normalized_question: str = Field(min_length=1, max_length=2400)
    answer_requirements: list[str] = Field(default_factory=list, max_length=10)
    queries: list[ShopQuery] = Field(default_factory=list, max_length=6)
    clarification: str = Field("", max_length=800)
    execution: Literal["model_assisted", "deterministic"] = "model_assisted"


def metric_label(metric: str, d: dict | None = None) -> str:
    if metric in CORE_LABELS:
        return CORE_LABELS[metric]
    labels = (d or {}).get("fee_labels", {})
    return labels.get(metric, metric)


def metric_unit(metric: str) -> str:
    return "%" if metric in RATE_METRICS else "元"


def _money(value) -> float:
    return float(value or 0)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").casefold())


def _round(value) -> float:
    return round(value, 2) if value is not None else None


def _month_label(value: str) -> str:
    y, m = value.split("-")
    return f"{y}年{int(m)}月"


def _channel_label(channel: str) -> str:
    return {"self": "京东自营", "pop": "POP", "store": "线下"}.get(channel, channel)


def _shop_label(d: dict, channel: str, shop_id: str) -> str:
    shop = service.shop_by_id(d).get((channel, shop_id))
    return service.shop_display(shop) if shop else f"{_channel_label(channel)} · {shop_id}"


def summarize(rows: list[dict], fee_keys: list[str]) -> dict:
    revenue = sum(_money(r.get("revenue")) for r in rows)
    cost = sum(_money(r.get("costG")) for r in rows)
    rent = sum(_money(r.get("rentAlloc")) for r in rows)
    fee_total = sum(_money(r.get(k)) for r in rows for k in fee_keys)
    expense_only = any(r.get("expense_only") for r in rows)
    fees_partial = any(r.get("missing_fees") for r in rows)
    cost_partial = any(r.get("missing_cost") for r in rows)
    cost_estimated = any(r.get("cost_estimated") for r in rows)
    source_conflict = any(r.get("source_conflict") for r in rows)
    provisional = any(bool(r.get("profit_provisional")) or (r.get("data_status") and r["data_status"] != "complete") for r in rows)
    provisional = provisional or fees_partial or cost_partial or source_conflict or cost_estimated
    gross_adjustment = sum(_money(r.get("gross_adjustment")) for r in rows)
    gross = None if (expense_only or cost_partial or source_conflict) else _round(revenue - cost + gross_adjustment)
    product = None if gross is None else _round(gross - fee_total)
    net = None if product is None else _round(product - rent)
    # 与页面口径一致：只要范围内有“费用待补”的月份，费用合计就不出确定数（单项已知费用仍逐项可见）。
    total_fees = None if fees_partial else _round(fee_total)

    def rate(num):
        return _round(num / revenue * 100) if revenue and num is not None else None

    s = {
        "row_count": len(rows),
        "revenue": _round(revenue), "costG": _round(cost), "rentAlloc": _round(rent),
        "total_fees": total_fees, "gross_profit": gross, "gross_adjustment": _round(gross_adjustment),
        "product_profit": product, "net_profit": net,
        "gross_rate": rate(gross), "fee_rate": rate(total_fees), "net_rate": rate(net),
        "expense_only": expense_only, "fees_partial": fees_partial,
        "cost_partial": cost_partial, "source_conflict": source_conflict, "provisional": provisional,
        "cost_estimated": cost_estimated,
        "estimated_cost_count": sum(int(r.get("estimated_cost_count") or 0) for r in rows),
        "estimated_cost_amount": _round(sum(_money(r.get("estimated_cost_amount")) for r in rows)),
        "months": sorted({r.get("month") for r in rows if r.get("month")}),
    }
    for key in fee_keys:
        s[key] = _round(sum(_money(r.get(key)) for r in rows))
    return s


def _empty_summary(fee_keys: list[str]) -> dict:
    return summarize([], fee_keys)


def filter_rows(d: dict, q: ShopQuery, start: str | None = None, end: str | None = None) -> list[dict]:
    start = start or q.start
    end = end or q.end
    by_id = service.shop_by_id(d)
    out = []
    for r in d.get("rows", []):
        if not r.get("has_data"):
            continue
        month = r.get("month")
        if not month or month < start or month > end:
            continue
        if q.channel and r.get("channel") != q.channel:
            continue
        if q.shop_id and r.get("shop_id") != q.shop_id:
            continue
        if q.shop_name:
            shop = by_id.get((r.get("channel"), r.get("shop_id")))
            if not shop or q.shop_name.casefold() not in str(shop.get("shop_name") or "").casefold():
                continue
        out.append(r)
    return out


def _group_key(q: ShopQuery, row: dict):
    if q.group == "month":
        return row["month"]
    if q.group == "channel":
        return row["channel"]
    if q.group == "shop":
        return (row["channel"], row["shop_id"])
    return None


def _group_label(q: ShopQuery, d: dict, key) -> str:
    if q.group == "month":
        return _month_label(key)
    if q.group == "channel":
        return _channel_label(key)
    if q.group == "shop":
        return _shop_label(d, key[0], key[1])
    return str(key)


def execute(d: dict, q: ShopQuery) -> dict:
    fee_keys = d.get("fee_keys", [])
    rows = filter_rows(d, q)
    result = {
        "id": q.id, "title": q.title, "spec": q.model_dump(),
        "metric_label": metric_label(q.metric, d), "unit": metric_unit(q.metric),
        "comparisons": {}, "object": None,
    }
    if not rows:
        result.update({"summary": _empty_summary(fee_keys), "rows": [], "group_count": 0, "value": None})
    elif q.group == "fee":
        items = []
        for key in fee_keys:
            value = _round(sum(_money(r.get(key)) for r in rows))
            if abs(value or 0) >= 0.005:
                items.append({"label": d.get("fee_labels", {}).get(key, key), "key": key, "value": value})
        items.sort(key=lambda x: -abs(x["value"] or 0))
        result.update({"summary": summarize(rows, fee_keys), "rows": items,
                       "group_count": len(items), "value": None})
    elif q.group == "total":
        summary = summarize(rows, fee_keys)
        result.update({"summary": summary, "rows": [], "group_count": 1,
                       "value": summary.get(q.metric)})
        if q.shop_id and not q.shop_name:
            matching = [shop for shop in service.shop_by_id(d).values()
                        if shop["shop_id"] == q.shop_id and (not q.channel or shop["channel"] == q.channel)]
            if len(matching) == 1:
                result["object"] = service.shop_display(matching[0])
            elif len(matching) > 1:
                # 同品牌自营与 POP 共享 shop_id：明确展示“自营＋POP”，避免只显示一家。
                result["object"] = matching[0]["shop_name"] + "（" + "＋".join(
                    service.shop_label(shop["channel"]) for shop in matching) + "）"
    else:
        buckets: dict = {}
        for row in rows:
            key = _group_key(q, row)
            buckets.setdefault(key, []).append(row)
        items = []
        for key, group in buckets.items():
            summary = summarize(group, fee_keys)
            value = summary.get(q.metric)
            # 费用待补按已录费用暂估，并保留暂估标记；成本缺失或来源
            # 冲突导致净利为 None 时，不列入可判断符号的店铺。
            if q.sign == "negative" and (value is None or value >= 0):
                continue
            if q.sign == "positive" and (value is None or value <= 0):
                continue
            items.append({"key": key, "label": _group_label(q, d, key), "summary": summary,
                          "value": value, "provisional": summary["provisional"],
                          "expense_only": summary["expense_only"], "months": summary["months"]})
        items.sort(key=lambda x: (x["value"] is None, -(x["value"] or 0) if q.order == "desc" else (x["value"] or 0), x["label"]))
        result.update({"summary": summarize(rows, fee_keys), "rows": items,
                       "group_count": len(items), "value": summarize(rows, fee_keys).get(q.metric)})
        # 分组（尤其店铺）的环比/同比按每个分组自身比较，总环比会因个别店铺缺数据失效。
        if q.group == "shop" and q.comparisons:
            for item in items:
                channel, shop_id = item["key"]
                single = q.model_copy(update={"group": "total", "channel": channel, "shop_id": shop_id, "shop_name": ""})
                item["per_comparisons"] = {kind: _compare(d, single, kind) for kind in q.comparisons}

    if q.group == "total":
        for kind in q.comparisons:
            result["comparisons"][kind] = _compare(d, q, kind)
    return result


def _shift_month(year: int, month: int, delta: int):
    total = year * 12 + (month - 1) + delta
    return divmod(total, 12)


def _compare(d: dict, q: ShopQuery, kind: str) -> dict:
    y1, m1 = int(q.start[:4]), int(q.start[5:7])
    y2, m2 = int(q.end[:4]), int(q.end[5:7])
    length = (y2 * 12 + m2) - (y1 * 12 + m1) + 1
    offset = length if kind == "mom" else 12
    sy, sm = _shift_month(y1, m1, -offset)
    ey, em = _shift_month(y2, m2, -offset)
    cstart, cend = f"{sy:04d}-{sm:02d}", f"{ey:04d}-{em:02d}"
    rows = filter_rows(d, q, cstart, cend)
    fee_keys = d.get("fee_keys", [])
    prev = summarize(rows, fee_keys) if rows else None
    prev_value = prev.get(q.metric) if prev else None
    cur_value = _matching_total(d, q)
    available = bool(rows)
    rate = delta = None
    if available and cur_value is not None and prev_value not in (None, 0):
        delta = _round(cur_value - prev_value)
        rate = _round((cur_value - prev_value) / abs(prev_value) * 100)
    return {"period": f"{cstart} 至 {cend}", "available": available, "value": prev_value, "delta": delta, "rate": rate}


def _matching_total(d: dict, q: ShopQuery) -> float | None:
    rows = filter_rows(d, q)
    if not rows:
        return None
    return summarize(rows, d.get("fee_keys", [])).get(q.metric)


# ─────────────────────────── 确定性规划器 ───────────────────────────

_MONTH_RE = r"(?<!\d)(1[0-2]|0?[1-9])月"
_YEAR_RE = r"(?<!\d)(20\d{2})年"
_RANK_WORDS = ("排行", "排名", "最高", "最低", "最好", "最差", "最赚钱", "最盈利", "最好卖", "榜首", "垫底", "前", "top")
_TREND_WORDS = ("趋势", "走势", "逐月", "各月", "变化趋势")
_DIAG_WORDS = ("为什么", "为何", "原因", "解读", "下降", "下滑", "亏损", "增长", "上涨", "改善", "恶化", "变动", "分析")
_FEE_STRUCTURE_WORDS = ("费用结构", "费用构成", "各项费用", "费用明细", "费用项")
_GENERIC_OVERVIEW_WORDS = ("经营数据", "经营情况", "经营业绩", "怎么样", "表现", "汇总", "整体", "情况", "看看", "看一下", "数据", "如何", "怎样")


def detect_metric(question: str, d: dict) -> str:
    compact = _compact(question)
    for key in d.get("fee_keys", []):
        label = d.get("fee_labels", {}).get(key)
        if label and _compact(label) and _compact(label) in compact:
            return key
    spec = [
        ("净利率", "net_rate"), ("毛利率", "gross_rate"), ("费用率", "fee_rate"),
        ("净利润", "net_profit"), ("净利", "net_profit"), ("项目净利", "net_profit"),
        ("利润", "net_profit"), ("盈亏", "net_profit"), ("赚钱", "net_profit"), ("盈利", "net_profit"), ("亏", "net_profit"),
        ("毛利", "gross_profit"),
        ("费用合计", "total_fees"), ("总费用", "total_fees"), ("费用", "total_fees"),
        ("产品成本", "costG"), ("成本", "costG"),
        ("房租分摊", "rentAlloc"), ("租金", "rentAlloc"),
        ("收入", "revenue"), ("营收", "revenue"), ("销售额", "revenue"), ("成交额", "revenue"), ("流水", "revenue"), ("卖得好", "revenue"),
    ]
    for token, metric in spec:
        if token in compact:
            return metric
    return ""


def _month_clusters(question: str) -> list[int]:
    return sorted({int(m) for m in re.findall(_MONTH_RE, question)})


def detect_period(question: str, months: list[str]):
    """Return (start, end, note). 单月同起止；数据外的月份被夹到可用区间。"""
    if not months:
        return None, None, "没有可用的店铺报表月份"
    latest = months[-1]
    compact = _compact(question)
    year_match = re.search(_YEAR_RE, question)
    year = int(year_match.group(1)) if year_match else int(latest[:4])
    note = ""

    range_match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*(?:[-~到至])\s*(1[0-2]|0?[1-9])月", question)
    month_nums = _month_clusters(question)
    if range_match:
        a, b = int(range_match.group(1)), int(range_match.group(2))
        start, end = f"{year:04d}-{min(a, b):02d}", f"{year:04d}-{max(a, b):02d}"
    elif "上半年" in compact:
        start, end = f"{year:04d}-01", f"{year:04d}-06"
    elif "下半年" in compact:
        start, end = f"{year:04d}-07", f"{year:04d}-12"
    elif len(month_nums) == 1:
        m = month_nums[0]
        start = end = f"{year:04d}-{m:02d}"
    elif "全年" in compact or "今年" in compact:
        start, end = f"{year:04d}-01", f"{year:04d}-12"
    elif re.search("上月|上个月", compact):
        py, pm = _shift_month(int(latest[:4]), int(latest[5:7]), -1)
        start = end = f"{py:04d}-{pm:02d}"
    elif re.search("最近|最新|当前|本月|这个月|这月", compact):
        start = end = latest
    elif len(month_nums) >= 2:
        start, end = f"{year:04d}-{month_nums[0]:02d}", f"{year:04d}-{month_nums[-1]:02d}"
    else:
        start, end = months[0], months[-1]

    if start < months[0]:
        start = months[0]
        note = f"数据从 {_month_label(months[0])} 开始，已按可用月份调整"
    if end > latest:
        end = latest
        note = f"数据截至 {_month_label(latest)}，已按可用月份调整"
    if start > end:
        start = end
    return start, end, note


def _detect_shop_clusters(question: str, d: dict) -> list[set]:
    """按出现位置聚类店铺别名，用于识别“A 对比 B”的多主体问题。"""
    occurrences = []
    for key, aliases in service.SHOP_ALIASES.items():
        for alias in aliases:
            for match in re.finditer(re.escape(alias), question, re.IGNORECASE):
                occurrences.append((match.start(), match.end(), key))
    occurrences.sort()
    clusters = []
    for start, end, key in occurrences:
        for cluster in clusters:
            if start <= cluster["end"]:
                cluster["end"] = max(cluster["end"], end)
                cluster["keys"].add(key)
                break
        else:
            clusters.append({"end": end, "keys": {key}})
    return [cluster["keys"] for cluster in clusters]


def _scope_for_keys(keys: set, d: dict) -> tuple[str, str]:
    """把一组店铺键转成 (shop_id, shop_name) 过滤条件。"""
    shop_ids = {key[1] for key in keys}
    if len(shop_ids) == 1:
        return shop_ids.pop(), ""
    names = {str(service.shop_by_id(d).get(key, {}).get("shop_name") or "") for key in keys}
    names.discard("")
    if len(names) == 1:
        return "", names.pop()
    return "", ""


def _default_rank_metric(compact: str) -> str:
    if re.search("亏|赚钱|盈利|利润|净利", compact):
        return "net_profit"
    if re.search("收入|销售|卖|营收|成交", compact):
        return "revenue"
    return "net_profit"


def _period_text(start: str, end: str) -> str:
    return _month_label(start) if start == end else f"{_month_label(start)} 至 {_month_label(end)}"


def deterministic_plan(question: str, meta: dict, filters: dict | None = None, history: list | None = None) -> ShopPlan:
    compact = _compact(question)
    months = meta.get("months") or []
    if not months:
        return ShopPlan(intent="clarification", normalized_question=question,
                        clarification="店铺报表还没有数据，请先完成数据导入", execution="deterministic")
    d = service.load()
    channel = service.detect_channel(question)
    metric = detect_metric(question, d)
    clusters = _detect_shop_clusters(question, d)
    shops = service.detect_shops(question, d)
    month_nums = _month_clusters(question)
    has_compare = any(word in compact for word in ("对比", "相比", "比较", "和", "与", "vs"))
    two_month_compare = len(month_nums) >= 2 and bool(re.search(r"(对比|相比|比较)", compact)) and not re.search(r"到|至|-|~", compact)
    two_shop_compare = len(clusters) >= 2 and has_compare and not two_month_compare

    # 1) 两月对比（同一店铺范围）：Q1 月份 A、Q2 月份 B，由写作器给出差额
    if two_month_compare:
        a, b = month_nums[:2]
        year_match = re.search(_YEAR_RE, question)
        year = int(year_match.group(1)) if year_match else int(months[-1][:4])
        shop_id, shop_name = ("", "")
        if shops:
            shop_id, shop_name = _scope_for_keys({(s["channel"], s["shop_id"]) for s in shops}, d)
        m = metric or "net_profit"

        def mk(qid, month):
            return ShopQuery(id=qid, title=f"{year}年{month}月{metric_label(m, d)}",
                             start=f"{year:04d}-{month:02d}", end=f"{year:04d}-{month:02d}",
                             channel=channel, shop_id=shop_id, shop_name=shop_name, metric=m, group="total")
        return ShopPlan(intent="comparison", normalized_question=f"对比 {year} 年 {a} 月与 {b} 月的{metric_label(m, d)}",
                        answer_requirements=["分别给出两个月的数据与差额", "说明店铺范围与数据覆盖"],
                        queries=[mk("Q1", a), mk("Q2", b)], execution="deterministic")

    # 2) 两店对比（同一期间）
    if two_shop_compare:
        shop_id_a, shop_name_a = _scope_for_keys(clusters[0], d)
        shop_id_b, shop_name_b = _scope_for_keys(clusters[1], d)
        period = detect_period(question, months)
        if period[0]:
            start, end, _ = period
            m = metric or "net_profit"
            common = dict(channel=channel, start=start, end=end, metric=m, group="total")
            return ShopPlan(intent="comparison",
                            normalized_question=f"对比 {start} 至 {end} 两个店铺的{metric_label(m, d)}",
                            answer_requirements=["分别给出两个店铺的数据与差额", "说明统计期间"],
                            queries=[ShopQuery(id="Q1", title="店铺A数据", **common, shop_id=shop_id_a, shop_name=shop_name_a),
                                     ShopQuery(id="Q2", title="店铺B数据", **common, shop_id=shop_id_b, shop_name=shop_name_b)],
                            execution="deterministic")

    period = detect_period(question, months)
    if period[0] is None:
        return ShopPlan(intent="clarification", normalized_question=question,
                        clarification="请指定要查询的月份或店铺", execution="deterministic")
    start, end, period_note = period
    shop_id, shop_name = ("", "")
    if shops:
        shop_id, shop_name = _scope_for_keys({(s["channel"], s["shop_id"]) for s in shops}, d)
    scope_text = service.shop_names_of(shops) if shops else ("全部店铺" if not channel else f"{service.shop_label(channel)}店铺")

    comparisons = []
    if re.search("环比|较上月|跟上月|比上月|与上月|上月比|对比上个月", compact):
        comparisons.append("mom")
    if re.search("同比|较去年|去年同期|与去年|去年比", compact):
        comparisons.append("yoy")

    fee_structure = any(word in compact for word in _FEE_STRUCTURE_WORDS)
    ranking = any(word in compact for word in _RANK_WORDS) or "哪" in question
    trend = any(word in compact for word in _TREND_WORDS)
    diagnosis = any(word in compact for word in _DIAG_WORDS) and not ranking
    # 概览：用户要的是整体经营表现（“数据如何/经营情况/怎么样”等）且未点名具体指标；
    # 一旦有具体指标（如推广费、净利）就走对应查询，不做概览。
    overview = any(word in compact for word in _GENERIC_OVERVIEW_WORDS) and not (ranking or trend or diagnosis or fee_structure) and not metric

    def q(qid, title, group="total", m=None, order="desc", limit=10, sign="", cmps=None):
        return ShopQuery(id=qid, title=title, start=start, end=end, channel=channel, shop_id=shop_id,
                         shop_name=shop_name, metric=m or metric or "net_profit", group=group,
                         order=order, limit=limit, sign=sign, comparisons=list(cmps if cmps is not None else comparisons))

    # 3) 费用结构（先于排名，避免“哪些费用”被“哪”误判为店铺排行）
    if fee_structure:
        return ShopPlan(intent="fee", normalized_question=f"{scope_text} {start} 至 {end} 的费用结构",
                        answer_requirements=["列出费用项及金额", "说明占比最高的费用", "说明费用口径（人工未计入等）"],
                        queries=[q("Q1", f"{_period_text(start, end)}费用构成", group="fee")], execution="deterministic")

    # 4) 排名
    if ranking:
        m = metric or _default_rank_metric(compact)
        order = "desc" if re.search("最高|最好|最赚钱|盈利|最盈利|前|top|榜首|最多|最大", compact) else "asc"
        sign = "negative" if re.search("亏损|亏钱|不赚钱|为负|负利润", compact) else ("positive" if re.search("盈利|赚钱", compact) else "")
        limit = 10
        num = re.search(r"前\s*([1-9][0-9]?)\s*(?:名|位)?", question)
        if num:
            limit = int(num.group(1))
        # “哪些店铺亏损/盈利 + 分析原因”这类问题在排行外附带环比，方便定位变化
        cmps = comparisons + (["mom"] if any(word in compact for word in _DIAG_WORDS) else [])
        return ShopPlan(intent="ranking", normalized_question=f"{scope_text} {start} 至 {end} 的{metric_label(m, d)}店铺排行",
                        answer_requirements=["直接说出第一名（或最差）店铺及金额", "给出排行依据的统计口径与期间", "说明暂估或仅有费用的店铺"],
                        queries=[q("Q1", f"{_period_text(start, end)}{metric_label(m, d)}店铺排行", group="shop", m=m, order=order, limit=limit, sign=sign, cmps=list(dict.fromkeys(cmps)))],
                        execution="deterministic")

    # 5) 趋势
    if trend:
        m = metric or "net_profit"
        return ShopPlan(intent="trend", normalized_question=f"{scope_text} {start} 至 {end} 的{metric_label(m, d)}逐月变化",
                        answer_requirements=["展示逐月数值", "指出峰值与低点", "说明各月数据完整度"],
                        queries=[q("Q1", f"{metric_label(m, d)}逐月走势", group="month", m=m, order="asc", limit=30)],
                        execution="deterministic")

    # 6) 原因分析：主指标环比 + 收入/成本/费用分解 + 店铺归因
    if diagnosis:
        m = metric or "net_profit"
        main = q("Q1", f"{metric_label(m, d)}与上期对比", m=m, cmps=list(set(comparisons) | {"mom"}))
        decompose = [q("Q2", "收入变化", m="revenue", cmps=["mom"]),
                     q("Q3", "产品成本变化", m="costG", cmps=["mom"]),
                     q("Q4", "费用合计变化", m="total_fees", cmps=["mom"])]
        shop_rank = q("Q5", f"{metric_label(m, d)}环比变化的店铺贡献", group="shop", m=m, order="asc", cmps=["mom"], limit=8)
        return ShopPlan(intent="diagnosis", normalized_question=f"{scope_text} {start} 至 {end} 的{metric_label(m, d)}变化原因分析",
                        answer_requirements=["直接给出本期数值与上期对比", "用收入、成本、费用的算术变化分解定位来源", "指出变化较大的店铺"],
                        queries=[main, *decompose, shop_rank], execution="deterministic")

    # 7) 概览/单点查询
    m = metric or "net_profit"
    if overview:
        queries = [q("Q1", "收入", m="revenue"), q("Q2", "毛利", m="gross_profit"),
                   q("Q3", "费用合计", m="total_fees"), q("Q4", "项目净利", m="net_profit")]
        if not shops and not channel and start == end:
            queries.append(q("Q5", "各店铺项目净利排行", group="shop", m="net_profit"))
        return ShopPlan(intent="overview", normalized_question=f"{scope_text} {start} 至 {end} 的经营概览",
                        answer_requirements=["直接给出收入、毛利、费用与项目净利", "说明统计期间与店铺范围", "说明数据完整度"],
                        queries=queries[:6], execution="deterministic")

    # 完全没有可识别对象（无月份、无店铺、无指标）时不要臆造全量查询，改为澄清。
    explicit_signal = bool(re.search(_MONTH_RE, question) or re.search(
        "最近|最新|当前|本月|这个月|这月|上月|全年|今年|上半年|下半年|全量|全部", compact))
    if not (explicit_signal or metric or shops or channel):
        return ShopPlan(intent="clarification", normalized_question=question,
                        clarification="可以问我某月各店铺的净利、毛利、收入、费用，或某店某月的经营情况、费用结构、排行与原因分析", execution="deterministic")

    queries = [q("Q1", f"{_period_text(start, end)}{metric_label(m, d)}", m=m)]
    return ShopPlan(intent="lookup", normalized_question=f"{scope_text} {start} 至 {end} 的{metric_label(m, d)}",
                    answer_requirements=["直接给出数值", "说明统计期间与店铺范围", "说明数据完整度"],
                    queries=queries, execution="deterministic")


def facts_for(results: list[dict], plan: ShopPlan, meta: dict) -> tuple[dict, list[dict]]:
    facts: dict[str, dict] = {}
    tables: list[dict] = []

    def add(identifier, label, text):
        facts[identifier] = {"id": identifier, "label": label, "text": text}

    for r in results:
        q = r["spec"]
        qid = r["id"]
        start, end = q["start"], q["end"]
        period_text = _month_label(start) if start == end else f"{_month_label(start)} 至 {_month_label(end)}"
        scope = "、".join(x for x in (period_text, q["shop_name"] or (_channel_label(q["channel"]) if q["channel"] and not q["shop_id"] else "")) if x) or "全部期间"
        add(qid + ".scope", r["title"] + "统计范围",
            f"{scope}，指标为{r['metric_label']}；该范围内有 {r['summary']['row_count']} 条店铺月度记录")
        if r["object"]:
            add(qid + ".object", "精确查询店铺", r["object"])
        if not r["rows"] and r["value"] is None:
            if r["summary"]["row_count"]:
                add(qid + ".value", r["title"] + r["metric_label"], "该范围数据不完整（部分店铺费用或成本待补），无法汇总确定数值")
            else:
                add(qid + ".value", r["title"] + r["metric_label"], "该统计期间没有对应店铺数据")
        elif r["value"] is not None:
            add(qid + ".value", r["title"] + r["metric_label"], formatted(r["value"], q["metric"]))
        for kind, comp in r["comparisons"].items():
            name = {"mom": "上期", "yoy": "去年同期"}[kind]
            add(qid + "." + kind + ".period", name + "范围", comp["period"])
            add(qid + "." + kind + ".value", name + r["metric_label"],
                "无数据" if not comp["available"] else formatted(comp["value"], q["metric"]))
            add(qid + "." + kind + ".rate", name + "变化率",
                f"{comp['rate']:+.2f}%" if comp["rate"] is not None else "不可完整比较（基期为0或无数据）")
            add(qid + "." + kind + ".delta", name + "变化量",
                formatted_delta(comp["delta"], q["metric"]) if comp["delta"] is not None else "不可完整比较")
        if r["rows"]:
            rows = []
            for i, row in enumerate(r["rows"]):
                value_text = formatted(row["value"], q["metric"]) if q["group"] != "fee" else formatted(row["value"], "total_fees")
                marker = ""
                if q["group"] != "fee":
                    marker = "（暂估）" if row.get("provisional") and not row.get("expense_only") else ("（仅有费用）" if row.get("expense_only") else "")
                display = row.get("label", "") + marker
                fid = f"{qid}.row{i + 1}"
                # 费用项名称短而稳定：事实只放金额，由写作器从事实标签写出名称，避免“推广费 推广费”重复。
                if q["group"] == "fee":
                    add(fid, r["title"] + "费用项" + display, value_text)
                else:
                    add(fid, r["title"] + "记录" + str(i + 1), f"{display}，{value_text}")
                for kind, comp in (row.get("per_comparisons") or {}).items():
                    name = {"mom": "上期", "yoy": "去年同期"}[kind]
                    tail = "无数据" if not comp["available"] else (
                        f"{formatted(comp['value'], q['metric'])}，较本店{name}变化率 "
                        f"{comp['rate']:+.2f}%" if comp["rate"] is not None else f"{formatted(comp['value'], q['metric'])}（不可完整比较）")
                    add(f"{fid}.{kind}", f"{display}{name}对照", tail)
                rows.append({"object": display, "value": value_text, "fact_id": fid})
            tables.append({"title": r["title"], "query_id": qid,
                           "columns": [{"key": "object", "label": GROUP_LABELS.get(q["group"], "对象")},
                                       {"key": "value", "label": r["metric_label"]}], "rows": rows})
            valid = [row for row in r["rows"] if row.get("value") is not None]
            if q["group"] in ("month", "shop") and valid:
                hi = max(valid, key=lambda x: x["value"] or 0)
                lo = min(valid, key=lambda x: x["value"] or 0)
                hi_fid, lo_fid = f"{qid}.row{valid.index(hi) + 1}", f"{qid}.row{valid.index(lo) + 1}"
                if hi_fid in facts and lo_fid in facts:
                    add(qid + ".peak", "区间最高", facts[hi_fid]["text"])
                    add(qid + ".low", "区间最低", facts[lo_fid]["text"])
    # 两期/两店对比：给出差额与相对变化率，供写作器和回退草稿直接引用
    if plan.intent == "comparison" and len(results) == 2:
        a, b = results[0], results[1]
        metric = a["spec"]["metric"]
        if metric == b["spec"]["metric"] and a["value"] is not None and b["value"] is not None:
            delta = _round(a["value"] - b["value"])
            rate = _round((a["value"] - b["value"]) / abs(b["value"]) * 100) if b["value"] else None
            add("C1.delta", "两期差额", formatted_delta(delta, metric))
            add("C1.rate", "相对变化率", f"{rate:+.2f}%" if rate is not None else "不可计算（基数为0或无数据）")
            add("C1.left", "左侧数值", formatted(a["value"], metric))
            add("C1.right", "右侧数值", formatted(b["value"], metric))
    return facts, tables


def formatted(value, metric: str) -> str:
    if value is None:
        return "不可计算（无完整数据）"
    if metric in RATE_METRICS:
        return f"{value:,.2f}%"
    return f"{value:,.2f} 元"


def formatted_delta(value, metric: str) -> str:
    if value is None:
        return "不可计算"
    if metric in RATE_METRICS:
        return f"{value:+,.2f} 个百分点"
    return ("+" if value > 0 else "") + f"{value:,.2f} 元"
