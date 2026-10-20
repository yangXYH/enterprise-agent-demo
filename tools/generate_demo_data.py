"""Generate deterministic, entirely fictional demo fixtures (standard library only)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build() -> dict:
    shops = [
        {"shop_id": "demo_life", "shop_name": "测试生活自营店", "channel": "self"},
        {"shop_id": "demo_digital", "shop_name": "测试数码旗舰店", "channel": "pop"},
        {"shop_id": "demo_outdoor", "shop_name": "测试户外专卖店", "channel": "pop"},
        {"shop_id": "demo_store", "shop_name": "测试体验门店", "channel": "store"},
    ]
    months = [f"2026-{month:02d}" for month in range(1, 10)]
    rows = []
    for i, shop in enumerate(shops):
        shop["months"] = months[:]
        for month in range(1, 10):
            revenue = 82000 + i * 17000 + month * (6100 + i * 600) + ((month * 7 + i * 3) % 5) * 1800
            cost = round(revenue * (0.49 + i * 0.035), 2)
            promo = round(revenue * (0.07 + i * 0.004), 2)
            platform = round(revenue * 0.035, 2)
            express = 1800 + month * 65 + i * 230
            storage = 650 + i * 120
            fees = round(promo + platform + express + storage, 2)
            profit = round(revenue - cost - fees, 2)
            rows.append({"channel": shop["channel"], "shop_id": shop["shop_id"], "month": f"2026-{month:02d}",
                         "revenue": revenue, "costG": cost, "promo": promo, "platform": platform,
                         "express": express, "storage": storage, "labor": 0, "rentAlloc": 0,
                         "gross_profit": round(revenue - cost, 2), "total_fees": fees,
                         "product_profit": profit, "net_profit": profit, "has_data": True,
                         "quantity": 720 + month * 53 + i * 87, "data_status": "complete",
                         "data_note": "纯公式生成的测试记录，不对应任何真实交易。"})
    departments = ["产品技术部", "电商运营部", "客户服务部", "人力行政部"]
    employees = [{"id": f"TEST-{i:03d}", "name": f"测试员工{i:02d}", "company": "示例科技" if i % 3 else "示例传媒",
                  "department": departments[(i - 1) % 4], "position": ["开发工程师", "运营专员", "客服专员", "人事专员"][(i - 1) % 4],
                  "status": "试用期" if i % 7 == 0 else "在职", "joined": f"2025-{(i - 1) % 12 + 1:02d}-{(i * 3) % 27 + 1:02d}",
                  "contact": f"TEST-CONTACT-{i:03d}"} for i in range(1, 25)]
    inventory = [{"sku": f"TEST-SKU-{i:03d}", "name": ["测试轻量背包", "测试便携键盘", "测试保温水杯", "测试收纳盒"][(i - 1) % 4] + f" · {i:02d}",
                  "warehouse": ["测试东区仓", "测试南区仓"][(i - 1) % 2], "stock": (i * 73) % 520,
                  "safety": 100, "onway": (i % 4) * 40, "sales": 45 + i * 9} for i in range(1, 19)]
    support = [{"name": f"测试客服{i:02d}", "account": f"demo-agent-{i:02d}", "questions": 360 + i * 43,
                "solved": 330 + i * 41, "response": round(1.1 + i * 0.12, 2), "satisfaction": round(98.2 - i * .32, 2)} for i in range(1, 6)]
    projects = [{"id": "DEMO-P01", "name": "测试商品知识库", "owner": "测试员工01", "progress": 85, "status": "进行中"},
                {"id": "DEMO-P02", "name": "测试客服问答助手", "owner": "测试员工03", "progress": 100, "status": "已完成"},
                {"id": "DEMO-P03", "name": "测试经营周报", "owner": "测试员工06", "progress": 62, "status": "进行中"},
                {"id": "DEMO-P04", "name": "测试库存预警", "owner": "测试员工09", "progress": 35, "status": "待评审"}]
    return {"meta": {"synthetic": True, "version": 1, "company": "示例科技", "period": "2026-01 至 2026-09",
                     "notice": "所有人员、企业、店铺、商品和金额均为虚构测试数据，按固定公式生成。"},
            "source": {"name": "Synthetic demo fixtures", "year": 2026, "exported_at": "2026-10-01T00:00:00Z",
                       "currency": "CNY", "labor_included": False, "synthetic": True, "description": "Deterministic synthetic demo data"},
            "months": months, "shops": shops, "fee_keys": ["promo", "platform", "express", "storage"],
            "fee_labels": {"promo": "测试推广费", "platform": "测试平台费", "express": "测试物流费", "storage": "测试仓储费"},
            "rows": rows, "employees": employees, "inventory": inventory, "support": support, "projects": projects}


def main() -> None:
    data = build()
    (ROOT / "demo").mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, indent=2)
    (ROOT / "demo" / "data.js").write_text("// Generated fictional fixtures. See tools/generate_demo_data.py.\nwindow.DEMO_DATA = " + encoded + ";\n", encoding="utf8")
    snapshot = {key: data[key] for key in ("source", "months", "shops", "fee_keys", "fee_labels", "rows")}
    (ROOT / "data" / "shop_report.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"Generated {len(data['rows'])} report rows, {len(data['employees'])} fictional employees.")


if __name__ == "__main__":
    main()
