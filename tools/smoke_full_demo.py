"""Read/write acceptance checks against a running, explicitly marked full demo."""
from __future__ import annotations

import argparse
import json
from io import BytesIO
from zipfile import ZipFile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4173")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.url, timeout=60)
    marker = client.get("/api/demo/status").json()
    assert marker.get("mode") == "full-application" and marker.get("synthetic_data") and marker.get("dataset_owned"), "Only a marked synthetic demo may be tested."
    response = client.post("/api/auth/login", json={"username": "demo_admin", "password": "Demo@2026"})
    response.raise_for_status()
    api = client.get("/openapi.json").json()
    today = date.today()
    params = {"start": (today - timedelta(days=29)).isoformat(), "end": today.isoformat(), "sku_code": "TEST-SKU-0001", "name": "测试员工01", "month": today.strftime("%Y-%m")}
    excluded = {"/api/ecom-knowledge/preview", "/api/inventory/jst/stock-sync/callback", "/api/inventory/jst/warehouses", "/api/sku-returns/sources"}
    paths = [path for path, methods in api["paths"].items() if "get" in methods and "{" not in path and path not in excluded]
    def check(path):
        try:
            response = client.get(path, params=params)
            if response.status_code != 200:
                return {"path": path, "status": response.status_code, "detail": response.text[:250]}
            if response.headers.get("content-type", "").startswith("application/json"):
                response.json()
            return {"path": path, "status": 200}
        except Exception as error:
            return {"path": path, "error": str(error)[:200]}
    results = list(ThreadPoolExecutor(max_workers=4).map(check, paths))
    failed = [result for result in results if result.get("status") != 200]
    print(json.dumps({"checked": len(results), "passed": len(results) - len(failed), "failures": failed}, ensure_ascii=False, indent=2))
    operating = client.get("/api/operating-analysis", params=params).json()
    assert operating["summary"]["revenue"] > 0, "Synthetic operating revenue must be nonzero."
    report = client.get("/api/shop-report").json()
    assert report["source"]["synthetic"] and len(report["shops"]) == 9
    assert client.get("/api/hr/roster/list", params={"page_size": 100}).json()["total"] >= 72
    assert not failed
    # Exercise the real write services, reread through new HTTP requests, then clean
    # up only the test records just created in this explicitly owned demo database.
    employee = client.post("/api/hr/roster/save", json={"name": "测试验收员工", "emp_no": "TEST-ACCEPTANCE", "dept_name": "产品技术部", "remark": "acceptance-check"})
    employee.raise_for_status()
    employee_id = employee.json()["id"]
    try:
        response = client.post("/api/hr/roster/save", json={"id": employee_id, "remark": "acceptance-persisted"})
        response.raise_for_status()
        assert client.get(f"/api/hr/roster/detail/{employee_id}").json()["remark"] == "acceptance-persisted"
        exported = client.post("/api/hr/roster/export", json={"keyword": "测试验收员工"})
        exported.raise_for_status()
        with ZipFile(BytesIO(exported.content)) as book:
            assert "xl/workbook.xml" in book.namelist()
    finally:
        client.post("/api/hr/roster/delete", json={"id": employee_id, "hard": True}).raise_for_status()
    item = client.post("/api/design/items", json={"item_type": "prompts", "title": "测试验收资料", "text": "Synthetic acceptance record"})
    item.raise_for_status()
    item_id = item.json()["item"]["id"]
    endpoint = f"/api/design/items/prompts/{item_id}"
    try:
        response = client.put(endpoint, json={"item_type": "prompts", "title": "测试验收已保存", "text": "Edited synthetic acceptance record"})
        response.raise_for_status()
        assert any(row["id"] == item_id and row["title"] == "测试验收已保存" for row in client.get("/api/design/catalog").json()["prompts"])
        client.delete(endpoint).raise_for_status()
        client.post(f"/api/design/trash/prompts/{item_id}/restore").raise_for_status()
        assert any(row["id"] == item_id for row in client.get("/api/design/catalog").json()["prompts"])
    finally:
        client.delete(endpoint).raise_for_status()
        client.delete(f"/api/design/trash/prompts/{item_id}").raise_for_status()
    catalogue = client.get("/api/design/catalog").json()
    images = [url for row in catalogue["models"] for url in row.get("images", [])]
    assert images
    image = client.get(images[0])
    image.raise_for_status()
    assert image.headers["content-type"].startswith("image/")
    workbook = client.get("/static/demo-fixtures/customer-service-demo.xlsx")
    workbook.raise_for_status()
    assert workbook.content.startswith(b"PK")
    assert not client.get("/api/auth/session").json().get("password")
    print("Original HR create/edit/read/export/delete and design create/edit/trash/restore passed; image and customer-service workbook served.")
    print("Full application API acceptance passed with real service/database results.")


if __name__ == "__main__":
    main()
