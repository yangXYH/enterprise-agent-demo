"""After-sales quality dashboard service for Samsonite and Delsey."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "after_sales"
    / "2026-08-11-18-35-08--105874739770.xlsx"
)

BRAND_SAMSONITE = "测试旅行"
BRAND_DEMO_BAGS = "测试箱包"
_BRAND_RULES = (
    ("测试旅行", BRAND_SAMSONITE),
    ("测试箱包", BRAND_DEMO_BAGS),
    ("demo_bags", BRAND_DEMO_BAGS),
    ("测试运动", "测试运动"),
    ("aoniijie", "测试运动"),
    ("测试五金", "测试五金"),
    ("fly.globe", "测试五金"),
    ("金宇", "金宇"),
    ("jinyu", "金宇"),
    ("花岗岩", "花岗岩"),
    ("demo_travel", "花岗岩"),
    ("demo_rain", "Rains"),
    ("克鲁伯", "demo_home"),
    ("demo_home", "demo_home"),
)
BRANDS = tuple(sorted({brand for _, brand in _BRAND_RULES}))

_QUALITY_REASON1 = frozenset(
    {
        "商品质量问题",
        "商品质量/故障",
        "商品破损/包装问题",
        "拉链损坏",
        "断底/断面/开胶",
        "配件脱落",
        "商品与页面描述不符",
    }
)

_QUALITY_CUSTOMER1 = frozenset(
    {
        "产品质量",
        "外观问题",
        "物流原因商品损坏",
        "人为损坏",
        "商品原因",
        "产品误导",
    }
)

_DEFECT_KEYWORDS = (
    "拉链",
    "走线",
    "缝线",
    "开线",
    "脱线",
    "线头",
    "开裂",
    "破损",
    "破口",
    "划痕",
    "刮痕",
    "污迹",
    "瑕疵",
    "异味",
    "起球",
    "脱皮",
    "变形",
    "做工",
    "材质",
    "面料",
    "织物",
    "肩带",
    "磁吸扣",
    "配件",
    "脱落",
    "断底",
    "断面",
    "开胶",
    "包装",
    "物流",
    "撞",
    "不顺滑",
    "合不起来",
    "打不开",
    "失灵",
    "转不动",
    "松动",
    "故障",
    "磨破",
    "磨损",
    "褶皱",
)

_CATEGORY_ORDER = (
    "拉链/拉头",
    "拉杆/轮子",
    "肩带/配件",
    "做工/缝制/材质",
    "破损/物流",
    "功能/使用故障",
    "描述/预期不符",
    "其他",
)

_ZIPPER_KEYWORDS = ("拉链", "拉头", "双齿", "防爆拉链")
_ROD_WHEEL_KEYWORDS = ("拉杆", "轮子", "万向轮", "手柄")
_STRAP_PART_KEYWORDS = ("肩带", "配件", "磁吸扣", "搭扣", "扣")
_WORKMANSHIP_KEYWORDS = (
    "走线",
    "缝线",
    "开线",
    "脱线",
    "线头",
    "开裂",
    "做工",
    "瑕疵",
    "异味",
    "起球",
    "脱皮",
    "变形",
    "面料",
    "材质",
    "织物",
    "色差",
    "褶皱",
    "磨损",
    "缝补",
)
_BREAKAGE_KEYWORDS = (
    "破损",
    "破口",
    "划痕",
    "刮痕",
    "污迹",
    "包装",
    "物流",
    "撞",
    "断底",
    "断面",
    "开胶",
    "断",
)
_FUNCTION_KEYWORDS = (
    "不顺滑",
    "合不起来",
    "打不开",
    "失灵",
    "转不动",
    "松动",
    "故障",
    "不能用",
    "锁",
)
_DESCRIPTION_KEYWORDS = (
    "不符",
    "描述",
    "页面",
    "效果",
    "尺寸",
    "型号",
    "静音",
)

_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _round2(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _detect_brand(value: Any) -> str:
    name = _clean_text(value)
    name_lower = name.lower()
    for keyword, brand in _BRAND_RULES:
        if keyword.lower() in name_lower:
            return brand
    return "其他品牌"


def _build_columns(group_row: pd.Series, name_row: pd.Series) -> list[str]:
    columns: list[str] = []
    for group_value, name_value in zip(group_row, name_row):
        group = _clean_text(group_value)
        name = _clean_text(name_value)
        columns.append(f"{group}_{name}" if group else name)
    return columns


def _is_quality(row: pd.Series) -> bool:
    if row["reason1"] in _QUALITY_REASON1 or row["customer1"] in _QUALITY_CUSTOMER1:
        return True
    text = " ".join((row["reason2"], row["customer_desc"], row["customer2"]))
    return any(keyword in text for keyword in _DEFECT_KEYWORDS)


def _classify(row: pd.Series) -> str:
    reason1 = row["reason1"]
    reason2 = row["reason2"]
    customer_desc = row["customer_desc"]
    customer1 = row["customer1"]
    customer2 = row["customer2"]
    text = " ".join((reason2, customer_desc, customer2))

    if any(
        keyword in text or keyword in reason1 or keyword in customer1
        for keyword in _ZIPPER_KEYWORDS
    ):
        return "拉链/拉头"
    if any(
        keyword in text or keyword in reason1 or keyword in customer1
        for keyword in _ROD_WHEEL_KEYWORDS
    ):
        return "拉杆/轮子"
    if any(
        keyword in text or keyword in reason1 or keyword in customer1
        for keyword in _STRAP_PART_KEYWORDS
    ):
        return "肩带/配件"
    if any(
        keyword in text or keyword in reason1
        for keyword in _WORKMANSHIP_KEYWORDS
    ):
        return "做工/缝制/材质"
    if any(
        keyword in text or keyword in reason1 or keyword in customer1
        for keyword in _BREAKAGE_KEYWORDS
    ):
        return "破损/物流"
    if any(keyword in text for keyword in _FUNCTION_KEYWORDS):
        return "功能/使用故障"
    if (
        reason1 == "商品与页面描述不符"
        or customer1 == "产品误导"
        or any(keyword in text for keyword in _DESCRIPTION_KEYWORDS)
    ):
        return "描述/预期不符"
    return "其他"


def _normalize_frame(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.iloc[2:].copy()
    frame.columns = _build_columns(raw.iloc[0], raw.iloc[1])

    frame["service_no"] = frame.iloc[:, 0].astype(str)
    frame["order_no"] = frame.iloc[:, 8].astype(str)
    frame["product_no"] = frame.iloc[:, 14].astype(str)
    frame["product_name"] = frame.iloc[:, 15].apply(_clean_text)
    frame["reason1"] = frame.iloc[:, 3].apply(_clean_text)
    frame["reason2"] = frame.iloc[:, 4].apply(_clean_text)
    frame["customer_desc"] = frame.iloc[:, 5].apply(_clean_text)
    frame["audit_opinion"] = frame.iloc[:, 21].apply(_clean_text)
    frame["customer1"] = frame.iloc[:, 23].apply(_clean_text)
    frame["customer2"] = frame.iloc[:, 24].apply(_clean_text)
    frame["receive_reason"] = frame.iloc[:, 33].apply(_clean_text)
    frame["receiver"] = frame.iloc[:, 34].apply(_clean_text)
    frame["handle_result"] = frame.iloc[:, 35].apply(_clean_text)
    frame["apply_time_raw"] = frame.iloc[:, 7]
    frame["apply_time"] = pd.to_datetime(frame["apply_time_raw"], errors="coerce")
    frame["apply_date"] = frame["apply_time"].dt.strftime("%Y-%m-%d")
    frame["amount"] = pd.to_numeric(frame.iloc[:, 16], errors="coerce").fillna(0.0)
    frame["refund_amount"] = pd.to_numeric(frame.iloc[:, 37], errors="coerce").fillna(0.0)
    frame["duration_hours"] = pd.to_numeric(frame.iloc[:, 45], errors="coerce").fillna(0.0)
    frame["store_name"] = frame["receiver"].replace("", "未登记")
    frame["brand"] = frame["product_name"].apply(_detect_brand)
    frame["is_quality"] = frame.apply(_is_quality, axis=1)
    frame["category"] = frame.apply(_classify, axis=1)
    return frame


def _load_frame() -> pd.DataFrame:
    path = Path(os.getenv("AFTER_SALES_QUALITY_XLSX", str(DEFAULT_DATA_FILE)))
    if not path.exists():
        raise FileNotFoundError(f"售后数据文件不存在: {path}")
    stat = path.stat()
    with _cache_lock:
        cached = _cache.get("frame")
        if (
            cached is not None
            and _cache.get("path") == str(path)
            and _cache.get("mtime") == stat.st_mtime
        ):
            return cached

    raw = pd.read_excel(path, header=None, engine="openpyxl")
    if len(raw) < 3:
        raise ValueError("售后数据文件缺少表头或数据行")
    frame = _normalize_frame(raw)

    with _cache_lock:
        _cache["path"] = str(path)
        _cache["mtime"] = stat.st_mtime
        _cache["frame"] = frame
    return frame


def _apply_filters(
    frame: pd.DataFrame,
    brand: str,
    store: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    result = frame.copy()
    selected_brands = _normalize_brand_selection(brand)
    if selected_brands:
        result = result[result["brand"].isin(selected_brands)]
    if store and store != "全部":
        result = result[result["store_name"] == store]
    if start_date:
        result = result[result["apply_date"] >= start_date]
    if end_date:
        result = result[result["apply_date"] <= end_date]
    return result


def _normalize_brand_selection(brand: Any) -> list[str]:
    if isinstance(brand, (list, tuple, set)):
        raw_values = list(brand)
    else:
        raw_values = [brand]
    selected: list[str] = []
    for raw_value in raw_values:
        for part in str(raw_value or "").split(","):
            part = part.strip()
            if part and part != "全部":
                selected.append(part)
    return selected


def _ordered_brands(frame: pd.DataFrame) -> list[str]:
    counts = frame["brand"].value_counts()
    return [str(brand) for brand in counts.index]


def _brand_metrics(
    all_frame: pd.DataFrame,
    display_frame: pd.DataFrame,
    quality_frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for brand in _ordered_brands(all_frame):
        all_brand = all_frame[all_frame["brand"] == brand]
        display_brand = display_frame[display_frame["brand"] == brand]
        quality_brand = quality_frame[quality_frame["brand"] == brand]
        total = len(all_brand)
        display_count = len(display_brand)
        quality_count = len(quality_brand)
        metrics.append(
            {
                "brand": brand,
                "after_sales": total,
                "quality": display_count,
                "quality_rate": round(quality_count / total * 100, 2) if total else 0.0,
                "refund_amount": _round2(display_brand["refund_amount"].sum()),
                "avg_duration_hours": (
                    _round2(display_brand["duration_hours"].mean()) if display_count else 0.0
                ),
            }
        )
    return metrics


def _store_metrics(all_frame: pd.DataFrame, quality_frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for store_name, group in all_frame.groupby("store_name"):
        quality_group = quality_frame[quality_frame["store_name"] == store_name]
        total = len(group)
        quality = len(quality_group)
        rows.append(
            {
                "store_name": store_name,
                "after_sales": total,
                "quality": quality,
                "quality_rate": round(quality / total * 100, 2) if total else 0.0,
                "refund_amount": _round2(quality_group["refund_amount"].sum()),
                "avg_duration_hours": (
                    _round2(quality_group["duration_hours"].mean()) if quality else 0.0
                ),
            }
        )
    return sorted(rows, key=lambda row: (-row["quality"], -row["after_sales"]))


def _trend_data(quality_frame: pd.DataFrame, date_min: str, date_max: str) -> list[dict[str, Any]]:
    if not quality_frame.empty and date_min and date_max:
        dates = pd.date_range(start=date_min, end=date_max, freq="D")
    else:
        dates = []

    trend: list[dict[str, Any]] = []
    for day in dates:
        day_value = day.strftime("%Y-%m-%d")
        day_frame = quality_frame[quality_frame["apply_date"] == day_value]
        brand_counts = day_frame["brand"].value_counts().to_dict()
        trend.append(
            {
                "date": day_value,
                "brands": {str(brand): int(count) for brand, count in brand_counts.items()},
                "total": len(day_frame),
            }
        )
    return trend


def _category_data(quality_frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category in _CATEGORY_ORDER:
        category_frame = quality_frame[quality_frame["category"] == category]
        if category_frame.empty:
            continue
        brand_counts = category_frame["brand"].value_counts().to_dict()
        rows.append(
            {
                "category": category,
                "brands": {str(brand): int(count) for brand, count in brand_counts.items()},
                "total": len(category_frame),
            }
        )
    return rows


def _product_metrics(
    all_frame: pd.DataFrame,
    display_frame: pd.DataFrame,
    quality_frame: pd.DataFrame,
    limit: int = 12,
) -> list[dict[str, Any]]:
    all_counts = all_frame.groupby("product_name").size().rename("after_sales")
    display_counts = display_frame.groupby("product_name").size().rename("display_count")
    quality_counts = quality_frame.groupby("product_name").size().rename("quality_count")
    merged = (
        all_counts.to_frame()
        .join(display_counts, how="left")
        .join(quality_counts, how="left")
        .fillna(0)
    )
    merged["display_count"] = merged["display_count"].astype(int)
    merged["quality_count"] = merged["quality_count"].astype(int)
    merged = merged.sort_values(["display_count", "after_sales"], ascending=[False, False]).head(limit)

    rows: list[dict[str, Any]] = []
    for product_name, row in merged.iterrows():
        total = int(row["after_sales"])
        display_count = int(row["display_count"])
        quality_count = int(row["quality_count"])
        rows.append(
            {
                "product_name": product_name,
                "after_sales": total,
                "quality": display_count,
                "quality_count": quality_count,
                "non_quality_count": total - quality_count,
                "quality_rate": round(quality_count / total * 100, 2) if total else 0.0,
            }
        )
    return rows


def _detail_records(detail_frame: pd.DataFrame) -> list[dict[str, Any]]:
    if detail_frame.empty:
        return []
    frame = detail_frame.sort_values(["apply_time", "service_no"], ascending=False)
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        apply_time = (
            row["apply_time"].strftime("%Y-%m-%d %H:%M:%S")
            if pd.notna(row["apply_time"])
            else ""
        )
        records.append(
            {
                "service_no": row["service_no"],
                "order_no": row["order_no"],
                "apply_time": apply_time,
                "brand": row["brand"],
                "store_name": row["store_name"],
                "product_no": row["product_no"],
                "product_name": row["product_name"],
                "category": row["category"],
                "is_quality": bool(row["is_quality"]),
                "reason1": row["reason1"],
                "reason2": row["reason2"],
                "customer_desc": row["customer_desc"],
                "customer1": row["customer1"],
                "customer2": row["customer2"],
                "audit_opinion": row["audit_opinion"],
                "handle_result": row["handle_result"],
                "refund_amount": _round2(row["refund_amount"]),
                "duration_hours": _round2(row["duration_hours"]),
            }
        )
    return records


def get_dashboard(
    brand: str = "全部",
    store: str = "全部",
    category: str = "全部",
    start_date: str = "",
    end_date: str = "",
    problem_scope: str = "all",
) -> dict[str, Any]:
    """Build the after-sales quality dashboard payload."""
    frame = _load_frame()
    all_frame = _apply_filters(frame, brand, store, start_date, end_date)
    quality_frame = all_frame[all_frame["is_quality"]].copy()
    non_quality_frame = all_frame[~all_frame["is_quality"]].copy()
    if problem_scope == "quality":
        display_frame = quality_frame.copy()
    elif problem_scope == "non_quality":
        display_frame = non_quality_frame.copy()
    else:
        display_frame = all_frame.copy()
    detail_frame = all_frame.copy()
    if category and category != "全部":
        quality_frame = quality_frame[quality_frame["category"] == category]
        non_quality_frame = non_quality_frame[non_quality_frame["category"] == category]
        display_frame = display_frame[display_frame["category"] == category]
        detail_frame = detail_frame[detail_frame["category"] == category]

    date_values = all_frame.loc[all_frame["apply_date"] != "", "apply_date"].dropna()
    date_min = date_values.min() if not date_values.empty else ""
    date_max = date_values.max() if not date_values.empty else ""

    total = len(all_frame)
    quality = len(quality_frame)
    non_quality = len(detail_frame) - int(detail_frame["is_quality"].sum())
    problem_total = len(display_frame)
    path = Path(os.getenv("AFTER_SALES_QUALITY_XLSX", str(DEFAULT_DATA_FILE)))
    full_date_values = frame.loc[frame["apply_date"] != "", "apply_date"].dropna()
    full_date_min = full_date_values.min() if not full_date_values.empty else ""
    full_date_max = full_date_values.max() if not full_date_values.empty else ""

    return {
        "meta": {
            "source_name": path.name,
            "date_min": date_min,
            "date_max": date_max,
            "data_date_min": full_date_min,
            "data_date_max": full_date_max,
            "after_sales_total": total,
            "quality_total": quality,
            "non_quality_total": non_quality,
            "problem_total": problem_total,
            "problem_scope": problem_scope,
            "quality_rate": round(quality / total * 100, 2) if total else 0.0,
            "refund_amount": _round2(display_frame["refund_amount"].sum()),
            "avg_duration_hours": (
                _round2(display_frame["duration_hours"].mean()) if problem_total else 0.0
            ),
        },
        "brand_options": _ordered_brands(frame),
        "brands": _brand_metrics(all_frame, display_frame, quality_frame),
        "stores": _store_metrics(all_frame, display_frame),
        "trend": _trend_data(display_frame, date_min, date_max),
        "categories": _category_data(display_frame),
        "top_products": _product_metrics(all_frame, display_frame, quality_frame),
        "details": _detail_records(display_frame),
    }
