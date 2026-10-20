"""Shop report snapshot: read-only access to the private JSON snapshot.

The exported ``data/shop_report.json`` is the single source for the shop
report page and its AI Q&A.  Reading the file on every request is cheap
(75 rows) and keeps both surfaces on the latest exported data, so the
exporter never needs a service restart to be reflected here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "shop_report.json"

CHANNEL_LABELS = {"self": "京东自营", "pop": "POP", "store": "线下"}
CHANNEL_ORDER = {"self": 0, "pop": 1, "store": 2}
# 渠道口语别名 → channel 键。店铺报表把同品牌自营与 POP 分成不同店铺，
# 用户说“自营/POP/线下”时用它收窄范围。
CHANNEL_ALIASES = {
    "京东自营": "self", "自营": "self",
    "pop": "pop", "POP": "pop", "旗舰店": "pop",
    "线下": "store", "门店": "store", "实体": "store",
}
# 每个店铺的常见称呼。别名按长度优先，避免“示例生活”误配“示例生活·家装(B2B)”。
SHOP_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("self", "demo_bags"): ("测试箱包自营", "自营测试箱包", "测试箱包"),
    ("pop", "demo_bags"): ("测试箱包pop", "测试箱包POP", "测试箱包"),
    ("self", "demo_life"): ("示例生活自营", "示例生活"),
    ("self", "home"): ("示例生活·家装", "示例生活家装", "家装自营", "家装", "b2b"),
    ("self", "demo_apparel"): ("demo_apparel自营", "dk自营", "demo_apparel", "dk"),
    ("pop", "demo_apparel"): ("demo_apparel pop", "dk pop", "demo_apparel", "dk"),
    ("self", "fly"): ("测试五金",),
    ("self", "demo_security"): ("测试安防", "工艺品", "安防"),
    ("store", "demo_store"): ("测试门店门店", "测试门店", "线下门店"),
}


def _load() -> dict[str, Any]:
    try:
        with SNAPSHOT.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError("店铺报表尚未导入数据") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("店铺报表快照无法读取") from exc
    if not isinstance(data, dict) or not all(key in data for key in ("source", "months", "shops", "fee_keys", "fee_labels", "rows")):
        raise ValueError("店铺报表快照格式不正确")
    return data


def load() -> dict[str, Any]:
    """Latest snapshot, re-read on every call so fresh exports are visible."""
    return _load()


def metadata() -> dict[str, Any]:
    d = _load()
    source = d.get("source", {})
    return {
        "source": source,
        "months": d.get("months", []),
        "shops": d.get("shops", []),
        "fee_keys": d.get("fee_keys", []),
        "fee_labels": d.get("fee_labels", {}),
        "row_count": len(d.get("rows", [])),
        "currency": source.get("currency", "CNY"),
        "labor_included": bool(source.get("labor_included")),
        "ai_configured": True,
    }


def shop_by_id(d: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(s["channel"], s["shop_id"]): s for s in d.get("shops", [])}


def shop_display(shop: dict[str, Any]) -> str:
    return f"{CHANNEL_LABELS.get(shop['channel'], shop['channel'])} · {shop['shop_name']}"


def shop_label(channel: str) -> str:
    return CHANNEL_LABELS.get(channel, channel)


def detect_channel(question: str) -> str:
    """Return self/pop/store when the question names a channel, else ''."""
    compact = _compact(question)
    for alias, key in CHANNEL_ALIASES.items():
        if alias in compact:
            return key
    return ""


def _compact(text: str) -> str:
    import re
    return re.sub(r"\s+", "", (text or "").casefold())


def detect_shops(question: str, d: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve shop mentions in the question.

    - 同品牌自营与 POP 名称相同：无渠道词时两个都选（表示该品牌全部店铺）；
      有渠道词时只选对应渠道。
    - 别名按最长匹配优先（“示例生活”精确选示例生活自营，不会误选“示例生活·家装(B2B)”）。
    - 未命中任何店铺返回空列表（= 全部店铺）。
    """
    compact = _compact(question)
    channel = detect_channel(question)
    scored: dict[tuple[str, str], int] = {}
    for shop in d.get("shops", []):
        key = (shop["channel"], shop["shop_id"])
        best = 0
        for alias in SHOP_ALIASES.get(key, ()):
            stripped = _compact(alias)
            if stripped and stripped in compact and len(stripped) > best:
                best = len(stripped)
        # 完整店名兜底（例如“示例生活 · 家装(B2B)”原文出现）
        full = _compact(shop["shop_name"])
        if full in compact and len(full) > best:
            best = len(full)
        if best:
            scored[key] = best
    if not scored:
        return []
    best_len = max(scored.values())
    picked = [k for k, v in scored.items() if v == best_len]
    if channel and len(picked) > 1:
        picked = [k for k in picked if k[0] == channel]
    by_id = shop_by_id(d)
    return [by_id[k] for k in picked]


def shop_names_of(shops: list[dict[str, Any]]) -> str:
    """Join resolved shops into a human-readable scope string."""
    if not shops:
        return "全部店铺"
    labels = []
    seen = set()
    for shop in shops:
        display = shop_display(shop)
        if display not in seen:
            seen.add(display)
            labels.append(display)
    return "、".join(labels)
