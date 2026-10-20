"""Export a configured demo SQLite expense database to the report snapshot.

Use --db path/to/demo.db. The input is opened read-only. For the original application
demo, tools/full_demo_seed.py creates the synthetic snapshot and isolated MySQL fixtures.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "demo.db"
DEFAULT_OUTPUT = ROOT / "data" / "shop_report.json"
STORE_OVERRIDE = ROOT / "data" / "shop_report_store_overrides.json"
STORE_SHOP = {"channel": "store", "shop_id": "demo_store", "shop_name": "测试体验门店", "sort_order": 10}

# 数据不全、用户确认不显示的行：(channel, shop_id, month)。
# POP·测试服饰 1-6 月只有第三方快递费（expressHd）、无销售/成本/其他费用，
# 用户要求暂不显示；源库数据保留，仅从导出快照剔除，补全数据后移除即可恢复。
HIDDEN_ROWS = {
    ("pop", "demo_apparel", month) for month in range(1, 7)
} | {
    # Demo export policy: fee-only months
    # remain in the source database but do not reappear after an export.
    ("self", "fly", month) for month in range(1, 6)
}

# The exact feeKeys order in the source project's index.html calcNet() and
# renderSummaryTable(). The breakdown fields storageGen/storageCons explain
# storage but must not be added again to total fees.
FEE_KEYS = (
    "promo", "maobaoFee", "tcFwd", "tcRev", "storage", "express", "baitiao",
    "promoService", "crossRegion", "transRebate", "commission", "transFee",
    "shipInsure", "prodInsure", "jdBeans", "penalty", "deliveryIncome",
    "priceRebate", "storageHd", "expressHd", "afterSale", "rent", "tax",
    "capital", "platform", "labor", "brand_rebate", "virtual_income",
)

FEE_LABELS = {
    "promo": "推广费", "maobaoFee": "毛保金额", "tcFwd": "TC正向转运费",
    "tcRev": "TC逆向转运费", "storage": "京东仓储费", "express": "京东快递费",
    "baitiao": "白条", "promoService": "促销服务费", "crossRegion": "平行库存补贴",
    "transRebate": "优惠券 / 红包 / 补贴", "commission": "佣金",
    "transFee": "交易服务费", "shipInsure": "运费保险", "prodInsure": "商品保险",
    "jdBeans": "京豆成本", "penalty": "违约金", "deliveryIncome": "配送费收入(抵减)",
    "priceRebate": "价保返佣(抵减)", "storageHd": "花都仓储费(固定)",
    "expressHd": "第三方快递费", "afterSale": "售后赔付", "rent": "租金杂费",
    "tax": "模拟税金", "capital": "资金成本", "platform": "平台服务费",
    "labor": "人工", "brand_rebate": "广告费返款", "virtual_income": "云朵交易服务费",
}
BREAKDOWN_KEYS = ("storageGen", "storageCons")
EXTRA_SOURCE_KEYS = ("ad_rebate", "penalty_virtual")
REQUIRED_SHOP_COLUMNS = {
    "month", "channel", "shop_id", "revenue", "costG", "rentAlloc",
    "data_status", "data_note", *FEE_KEYS, *BREAKDOWN_KEYS, *EXTRA_SOURCE_KEYS,
}


def _assert_source_formula(html_path: Path) -> None:
    """Stop if the original dashboard's fee formula has changed."""
    if not html_path.is_file():
        raise FileNotFoundError(f"找不到源看板公式文件：{html_path}")
    html = html_path.read_text(encoding="utf-8")
    start = html.find("function calcNet(chData)")
    if start < 0:
        raise ValueError("源看板缺少 calcNet 函数，无法核对费用公式")
    match = re.search(r"const feeKeys\s*=\s*\[([^\]]+)\]", html[start : start + 2500])
    if not match:
        raise ValueError("源看板 calcNet 缺少 feeKeys，无法核对费用公式")
    source_keys = tuple(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))
    if source_keys != FEE_KEYS:
        raise ValueError("源看板 feeKeys 已变更，请先同步更新导出脚本的费用口径")


def _money(value: Any) -> float:
    return float(value or 0)


def _calculated(value: float) -> float:
    # Source data may have >2 decimals (e.g. a September settlement amount).
    # Keep calculation precision and let the UI round only for display.
    return round(value, 6)


def build_snapshot(db_path: Path, year: int) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"找不到源数据库：{db_path}")
    _assert_source_formula(db_path.with_name("index.html"))

    # SQLite URI mode=ro prevents accidental writes to the source database.
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    source_tables = ["shop_registry", "shop_data"]
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")  # registry and facts come from one consistent view
        columns = {row[1] for row in conn.execute("PRAGMA table_info(shop_data)")}
        missing = REQUIRED_SHOP_COLUMNS - columns
        if missing:
            raise ValueError(f"shop_data 缺少字段：{', '.join(sorted(missing))}")
        registries = [dict(row) for row in conn.execute(
            "SELECT channel, shop_id, shop_name, sort_order FROM shop_registry "
            "WHERE channel IN ('self', 'pop') "
            "ORDER BY CASE channel WHEN 'self' THEN 0 ELSE 1 END, sort_order, shop_id"
        )]
        if not registries:
            raise ValueError("shop_registry 没有京东自营或 POP 店铺")
        records = [dict(row) for row in conn.execute(
            "SELECT * FROM shop_data WHERE channel IN ('self', 'pop') "
            "ORDER BY month, CASE channel WHEN 'self' THEN 0 ELSE 1 END, shop_id"
        )]
        # The legacy dashboard stores the offline 测试体验门店 in channel_data,
        # rather than shop_registry/shop_data. Include that source alongside
        # the online self/POP shops without changing the source database.
        table_names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        if "channel_data" in table_names:
            source_tables.append("channel_data")
            channel_columns = {row[1] for row in conn.execute("PRAGMA table_info(channel_data)")}
            required_channel_fields = {"month", "channel", "revenue", "costG", "rentAlloc",
                                       *FEE_KEYS, *BREAKDOWN_KEYS, *EXTRA_SOURCE_KEYS}
            missing_channel_fields = required_channel_fields - channel_columns
            if missing_channel_fields:
                raise ValueError(
                    "channel_data 缺少线下店铺字段：" + ", ".join(sorted(missing_channel_fields))
                )
            source_store_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM channel_data WHERE channel = 'store' ORDER BY month"
            )]
            if source_store_rows:
                registries.append(dict(STORE_SHOP))
                for source in source_store_rows:
                    has_revenue = abs(_money(source.get("revenue"))) > 0.000001
                    has_expenses = any(abs(_money(source.get(key))) > 0.000001 for key in FEE_KEYS)
                    record = {
                        "month": source["month"],
                        "channel": "store",
                        "shop_id": STORE_SHOP["shop_id"],
                        "revenue": source.get("revenue", 0),
                        "costG": source.get("costG", 0),
                        "rentAlloc": source.get("rentAlloc", 0),
                        "data_status": "complete" if has_revenue else ("partial" if has_expenses else "empty"),
                        "data_note": "沿用原费用汇总口径；销售明细表同期金额有差异，未覆盖本月账面收入和成本。" if has_revenue else (
                            "本月仅有已录费用，线下销售明细待导入；已录费用不代表经营亏损。"
                            if has_expenses else "当月未提供该店铺数据"
                        ),
                    }
                    for field in (*FEE_KEYS, *BREAKDOWN_KEYS, *EXTRA_SOURCE_KEYS):
                        record[field] = source.get(field, 0)
                    records.append(record)
        incomplete_costs: dict[tuple[str, str, int], int] = {}
        estimated_costs: dict[tuple[str, str, int], dict[str, Any]] = {}
        if "shop_cost_detail" in table_names:
            detail_columns = {r[1] for r in conn.execute("PRAGMA table_info(shop_cost_detail)")}
            if {"channel", "shop_id", "month", "net_qty", "unit_cost", "cost"} <= detail_columns:
                incomplete_costs = {
                    (r[0], r[1], int(r[2])): int(r[3]) for r in conn.execute(
                        "SELECT channel,shop_id,month,COUNT(*) FROM shop_cost_detail "
                        "WHERE ABS(COALESCE(net_qty,0))>0.000001 "
                        "AND (unit_cost IS NULL OR unit_cost<=0 OR cost IS NULL) "
                        "GROUP BY channel,shop_id,month"
                    )
                }
                if "cost_status" in detail_columns:
                    for detail in conn.execute("SELECT channel,shop_id,month,COUNT(*) AS count,SUM(cost) AS amount FROM shop_cost_detail WHERE cost_status='estimated' AND ABS(COALESCE(net_qty,0))>0.000001 GROUP BY channel,shop_id,month"):
                        estimated_costs[(detail[0],detail[1],int(detail[2]))] = {"count":int(detail[3]),"amount":_money(detail[4])}
        audit_flags = {}
        if "shop_report_audit_flags" in table_names:
            audit_flags = {
                (r["channel"], r["shop_id"], int(r["month"])): dict(r)
                for r in conn.execute("SELECT * FROM shop_report_audit_flags WHERE year=?", (year,))
            }
        fee_breakdowns: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        if "shop_report_fee_breakdown" in table_names:
            for r in conn.execute("SELECT * FROM shop_report_fee_breakdown WHERE year=?", (year,)):
                fee_breakdowns.setdefault((r["channel"], r["shop_id"], int(r["month"])), []).append({
                    "key": r["expense_type"], "parent_key": r["fee_field"],
                    "label": r["expense_type"], "amount": _money(r["amount"]),
                })
        conn.commit()
    finally:
        conn.close()

    registry_keys = {(r["channel"], r["shop_id"]) for r in registries}
    if len(registry_keys) != len(registries):
        raise ValueError("shop_registry 存在重复店铺键")
    seen: set[tuple[str, str, int]] = set()
    months_by_shop: dict[tuple[str, str], list[str]] = {key: [] for key in registry_keys}
    all_months: set[str] = set()
    rows: list[dict[str, Any]] = []
    for source in records:
        channel = str(source["channel"])
        shop_id = str(source["shop_id"])
        month_number = int(source["month"])
        if month_number < 1 or month_number > 12:
            raise ValueError(f"无效月份：{month_number}")
        key = (channel, shop_id)
        row_key = (channel, shop_id, month_number)
        if key not in registry_keys:
            raise ValueError(f"shop_data 有未注册店铺：{channel}/{shop_id}")
        if row_key in seen:
            raise ValueError(f"shop_data 有重复店铺月份：{row_key}")
        seen.add(row_key)
        if row_key in HIDDEN_ROWS:
            # 数据不全的月份不进入快照（源库数据保留），见 HIDDEN_ROWS 说明。
            continue
        month = f"{year:04d}-{month_number:02d}"
        all_months.add(month)

        row: dict[str, Any] = {
            "month": month,
            "channel": channel,
            "shop_id": shop_id,
            "revenue": _money(source["revenue"]),
            "costG": _money(source["costG"]),
            "rentAlloc": _money(source["rentAlloc"]),
            "data_status": str(source["data_status"] or "empty"),
            "data_note": str(source["data_note"] or ""),
        }
        for field in (*FEE_KEYS, *BREAKDOWN_KEYS, *EXTRA_SOURCE_KEYS):
            # The original index.html zeroes labor in its public shopData and
            # unlocks real labor through a separate management key. This page
            # uses the same locked view; never put protected labor into JSON.
            row[field] = 0.0 if field == "labor" else _money(source[field])

        fees = _calculated(sum(row[field] for field in FEE_KEYS))
        has_activity = any(abs(row[field]) > 0.000001 for field in
                           ("revenue", "costG", "rentAlloc", *FEE_KEYS,
                            *BREAKDOWN_KEYS, *EXTRA_SOURCE_KEYS))
        expense_only = abs(row["revenue"]) <= 0.000001 and has_activity
        missing_cost = (row["data_status"] == "partial" and
                        abs(row["revenue"]) > 0.000001 and
                        abs(row["costG"]) <= 0.000001)
        missing_cost_count = incomplete_costs.get(row_key, 0)
        missing_cost = missing_cost or missing_cost_count > 0
        flags = audit_flags.get(row_key, {})
        source_conflict = bool(flags.get("source_conflict"))
        missing_fees = bool(flags.get("missing_fees"))
        audit_note = str(flags.get("note") or "")
        if audit_note:
            row["data_note"] = row["data_note"] + "；" + audit_note
        if missing_cost_count:
            row["data_note"] += f"；{missing_cost_count} 个非零净销量 SKU 成本待补，毛利和净利暂不计算"
        row["known_total_fees"] = fees
        row["total_fees"] = None if missing_fees else fees
        row["expense_only"] = expense_only
        row["missing_cost"] = missing_cost
        row["missing_cost_count"] = missing_cost_count
        row["missing_fees"] = missing_fees
        row["source_conflict"] = source_conflict
        estimated = estimated_costs.get(row_key)
        if estimated:
            row["cost_estimated"] = True
            row["estimated_cost_count"] = estimated["count"]
            row["estimated_cost_amount"] = estimated["amount"]
        row["known_fee_keys"] = [key for key in FEE_KEYS if abs(row[key]) > 0.000001]
        row["settlement_fee_breakdown"] = fee_breakdowns.get(row_key, [])
        row["profit_provisional"] = has_activity and (row["data_status"] != "complete" or missing_cost or missing_fees or source_conflict or bool(estimated)) and not expense_only
        row["has_data"] = has_activity
        if not has_activity or expense_only or missing_cost or source_conflict:
            row["gross_profit"] = None
            row["product_profit"] = None
            row["net_profit"] = None
        else:
            gross = _calculated(row["revenue"] - row["costG"])
            product = _calculated(gross - fees)
            row["gross_profit"] = gross
            row["product_profit"] = product
            row["net_profit"] = _calculated(product - row["rentAlloc"])
        _describe_provisional_fees(row)
        if estimated:
            result_note = "收入来源仍有冲突，毛利及净利暂不计算" if source_conflict else "毛利及净利为暂估，实际成本补齐后重算"
            row["data_note"] += f"；含{estimated['count']}个SKU按同店同月均价暂估成本{estimated['amount']:.2f}元，{result_note}"
        rows.append(row)
        if has_activity:
            months_by_shop[key].append(month)

    shops = [
        {
            "channel": str(r["channel"]),
            "shop_id": str(r["shop_id"]),
            "shop_name": str(r["shop_name"]),
            "sort_order": int(r["sort_order"] or 0),
            "months": sorted(months_by_shop[(r["channel"], r["shop_id"])]),
        }
        for r in registries
    ]
    return {
        "source": {
            "name": "DEMO_BAGS 经营分析看板",
            "database": "demo_bags.db",
            "tables": source_tables,
            "formula": "index.html calcNet / renderSummaryTable feeKeys",
            "year": year,
            "profit_policy": "费用待补或成本已按用户授权均价补入时计算暂估项目净利；仍缺成本或收入来源冲突时不计算；未计人工",
            "currency": "CNY",
            "labor_included": False,
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "database_modified_at": datetime.fromtimestamp(db_path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        },
        "months": sorted(all_months),
        "shops": shops,
        "fee_keys": list(FEE_KEYS),
        "fee_labels": FEE_LABELS,
        "rows": rows,
    }


def _describe_provisional_fees(row: dict[str, Any]) -> None:
    if not row.get("missing_fees") or row.get("net_profit") is None:
        return
    note = str(row.get("data_note") or "")
    for old in ("项目净利待补全", "项目净利待完整费用导入后计算", "项目净利仍待完整费用导入后计算"):
        note = note.replace(old, "项目净利按已录费用暂估")
    message = "项目净利按已录费用暂估，费用补齐后重算；未计人工"
    row["data_note"] = note if message in note else note + ("；" if note else "") + message


def _merge_store_overrides(snapshot: dict[str, Any], override_path: Path) -> dict[str, Any]:
    """Overlay offline sales rows that are not yet present in channel_data.

    The spreadsheet has sales but no complete expense ledger. Existing source
    fees (for example, recorded courier charges) are retained. Pending expenses
    allow provisional profit based on recorded fees; missing SKU costs or
    conflicting income still leave profit unavailable.
    """
    if not override_path.is_file():
        return snapshot
    with override_path.open("r", encoding="utf-8") as file:
        overrides = json.load(file)
    if not isinstance(overrides, dict) or not isinstance(overrides.get("rows"), list):
        raise ValueError(f"线下销售导入文件格式不正确：{override_path}")

    store_shops = [shop for shop in snapshot["shops"] if shop.get("channel") == "store"]
    if not store_shops:
        store_shops = [dict(STORE_SHOP, months=[])]
        snapshot["shops"].append(store_shops[0])
    shop = store_shops[0]
    row_index = {
        (row["channel"], row["shop_id"], row["month"]): index
        for index, row in enumerate(snapshot["rows"])
    }
    imported_months: set[str] = set()
    for override in overrides["rows"]:
        if not isinstance(override, dict) or override.get("channel") != "store":
            raise ValueError("线下销售导入文件包含无效行")
        if override.get("shop_id") != STORE_SHOP["shop_id"]:
            raise ValueError("线下销售导入文件的店铺编号不匹配")
        month = str(override.get("month", ""))
        if not re.fullmatch(r"\d{4}-\d{2}", month) or int(month[5:7]) not in range(1, 13):
            raise ValueError(f"线下销售导入文件包含无效月份：{month}")
        accounting = override.get("source_kind") == "project_profit"
        # Reports and AI summaries share the selected reporting year. Historical
        # accounting rows remain archived in overrides, outside this snapshot.
        if int(month[:4]) != int(snapshot["source"]["year"]):
            continue
        key = ("store", STORE_SHOP["shop_id"], month)
        current_index = row_index.get(key)
        current = snapshot["rows"][current_index] if current_index is not None else None
        # For overlapping months, the accounting summary remains authoritative.
        if not accounting and current and abs(_money(current.get("revenue"))) > 0.000001:
            continue

        row = dict(override)
        known_fee_keys = set(row.get("known_fee_keys", []))
        if current and not accounting:
            for field in (*FEE_KEYS, *BREAKDOWN_KEYS, *EXTRA_SOURCE_KEYS):
                value = _money(current.get(field))
                if abs(value) > 0.000001 and field not in row.get("authoritative_fee_keys", []):
                    row[field] = value
                    if field in FEE_KEYS:
                        known_fee_keys.add(field)
            if current.get("rentAlloc") not in (None, 0, 0.0):
                row["rentAlloc"] = current["rentAlloc"]
        # The public report follows the original dashboard's locked labor view.
        row["labor"] = 0.0
        row["known_fee_keys"] = [key for key in FEE_KEYS if key in known_fee_keys and key != "labor"]
        missing_cost = bool(row.get("missing_cost"))
        missing_fees = bool(row.get("missing_fees", True))
        source_conflict = bool(row.get("source_conflict"))
        row["missing_fees"] = missing_fees
        row["total_fees"] = None if missing_fees else _calculated(
            sum(_money(row.get(field)) for field in FEE_KEYS)
        )
        row["known_total_fees"] = _calculated(sum(_money(row.get(field)) for field in FEE_KEYS))
        row["gross_profit"] = None if missing_cost or source_conflict else _calculated(
            _money(row.get("revenue")) - _money(row.get("costG")) + _money(row.get("gross_adjustment"))
        )
        if missing_cost or source_conflict:
            row["product_profit"] = None
            row["net_profit"] = None
            row["profit_provisional"] = True
        else:
            product = _calculated(row["gross_profit"] - row["known_total_fees"])
            row["product_profit"] = product
            row["net_profit"] = _calculated(product - _money(row.get("rentAlloc")))
        row["profit_provisional"] = bool(row.get("profit_provisional")) or missing_cost or missing_fees or source_conflict
        _describe_provisional_fees(row)
        row["expense_only"] = False
        row["has_data"] = True
        row_index[key] = len(snapshot["rows"]) if current_index is None else current_index
        if current_index is None:
            snapshot["rows"].append(row)
        else:
            snapshot["rows"][current_index] = row
        imported_months.add(month)

    shop["shop_name"] = STORE_SHOP["shop_name"]
    shop["months"] = sorted({
        row["month"] for row in snapshot["rows"]
        if row.get("channel") == "store" and row.get("shop_id") == STORE_SHOP["shop_id"] and row.get("has_data")
    })
    snapshot["months"] = sorted(set(snapshot["months"]) | imported_months)
    snapshot["source"]["store_sales_import"] = overrides.get("source", {})
    return snapshot


def export(db_path: Path, output_path: Path, year: int) -> dict[str, Any]:
    snapshot = build_snapshot(db_path, year)
    snapshot = _merge_store_overrides(snapshot, STORE_OVERRIDE)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=output_path.parent,
            prefix=".shop_report_", suffix=".tmp", delete=False,
        ) as file:
            temp_name = file.name
            json.dump(snapshot, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
        os.replace(temp_name, output_path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_SOURCE, help="源项目 demo_bags.db（只读）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="私有 JSON 快照输出路径")
    parser.add_argument("--year", type=int, default=2026, help="源数据库月份对应年份，默认 2026")
    args = parser.parse_args()
    if args.year < 2000 or args.year > 2100:
        parser.error("--year 必须在 2000 到 2100 之间")
    snapshot = export(args.db, args.output, args.year)
    print(f"已导出 {len(snapshot['shops'])} 个店铺、{len(snapshot['months'])} 个月、"
          f"{len(snapshot['rows'])} 行：{args.output.resolve()}")


if __name__ == "__main__":
    main()
