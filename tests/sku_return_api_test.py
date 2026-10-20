"""SKU 退货 API 的独立鉴权和请求契约测试，不连接生产数据库。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from sku_return_routes import router
from utils import permission_service


class SkuReturnApiTests(unittest.TestCase):
    RUN_ID = "a" * 32
    OTHER_RUN_ID = "b" * 32

    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.user = {"username": "buyer1", "real_name": "张三", "role": "boss"}
        self.auth = patch("main._get_authenticated_user", return_value=self.user)
        self.engine = patch("main._get_mysql_engine", return_value=object())
        self.allowed = patch(
            "utils.permission_service.allowed_page_keys",
            return_value=["sku-return-data"],
        )
        self.auth.start()
        self.engine.start()
        self.allowed_mock = self.allowed.start()

    def tearDown(self):
        self.allowed.stop()
        self.engine.stop()
        self.auth.stop()
        self.client.close()

    def test_metadata_and_filter_contract_pin_run_id(self):
        with (
            patch("sku_return_routes.service.get_metadata", return_value={"run_id": self.RUN_ID}) as metadata,
            patch("sku_return_routes.service.list_suppliers", return_value={"run_id": self.RUN_ID, "items": ["供应商一"]}) as suppliers,
            patch("sku_return_routes.service.get_summary", return_value={"run_id": self.RUN_ID}) as summary,
        ):
            self.assertEqual(self.client.get("/api/sku-returns/metadata").json(), {"run_id": self.RUN_ID})
            self.assertEqual(self.client.get(
                "/api/sku-returns/options/suppliers",
                params={"run_id": self.RUN_ID, "keyword": "供应", "limit": 25},
            ).json()["items"], ["供应商一"])
            response = self.client.get(
                "/api/sku-returns/summary",
                params=[
                    ("run_id", self.RUN_ID), ("period", "2026-06"), ("period", "2026-07"),
                    ("entity", "B2B"), ("supplier", "供应商一"),
                    ("sku_keyword", "  003 "),
                ],
            )
        self.assertEqual(response.status_code, 200)
        metadata.assert_called_once_with(run_id=None)
        suppliers.assert_called_once_with(
            keyword="供应", limit=25, run_id=self.RUN_ID,
            filters={
                "period": [], "entity": [], "category": [], "brand": [],
                "supplier": [], "sku_keyword": "",
            },
        )
        summary.assert_called_once_with(
            filters={
                "period": ["2026-06", "2026-07"],
                "entity": ["B2B"], "category": [], "brand": [],
                "supplier": ["供应商一"], "sku_keyword": "003",
            },
            run_id=self.RUN_ID,
        )
        self.allowed_mock.assert_called_with(
            unittest.mock.ANY, "boss", "张三", "account:buyer1"
        )

    def test_items_sources_and_export_preserve_scope(self):
        source_payload = {"run_id": self.OTHER_RUN_ID, "items": [{"relative_path": "2026/6月/a.xlsx"}]}
        with (
            patch("sku_return_routes.service.list_items", return_value={"run_id": self.OTHER_RUN_ID, "total": 1, "items": []}) as items,
            patch("sku_return_routes.service.list_sources", return_value=source_payload) as sources,
            patch("sku_return_routes.service.export_items", return_value=("退货明细.xlsx", b"xlsx-bytes")) as export,
        ):
            item_response = self.client.get(
                "/api/sku-returns/items",
                params={"run_id": self.OTHER_RUN_ID, "view": "detail", "page": 2,
                        "page_size": 80, "sort_by": "period", "sort_dir": "asc"},
            )
            source_response = self.client.get(
                "/api/sku-returns/sources",
                params={"run_id": self.OTHER_RUN_ID, "sku_code": "001", "sku_name": "商品甲",
                        "detail_period": "2026-06", "detail_entity": "B2B",
                        "detail_category": "箱包", "detail_supplier_name": "供应商一"},
            )
            missing_name_response = self.client.get(
                "/api/sku-returns/sources",
                params={"run_id": self.OTHER_RUN_ID, "sku_code": "001", "sku_name": ""},
            )
            export_response = self.client.get(
                "/api/sku-returns/export",
                params={"run_id": self.OTHER_RUN_ID, "view": "detail", "sort_by": "period"},
            )
        self.assertEqual(item_response.status_code, 200)
        self.assertEqual(source_response.json(), source_payload)
        self.assertEqual(missing_name_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.content, b"xlsx-bytes")
        self.assertIn("filename*=UTF-8''", export_response.headers["content-disposition"])
        self.assertEqual(export_response.headers["cache-control"], "no-store")
        items.assert_called_once_with(
            filters={"period": [], "entity": [], "category": [], "brand": [],
                     "supplier": [], "sku_keyword": ""},
            view="detail", page=2, page_size=80, sort_by="period", sort_dir="asc", run_id=self.OTHER_RUN_ID,
        )
        self.assertEqual(sources.call_args_list[0].kwargs["period"], "2026-06")
        self.assertEqual(sources.call_args_list[0].kwargs["supplier_name"], "供应商一")
        self.assertEqual(sources.call_args_list[1].args[:2], ("001", ""))
        self.assertEqual(export.call_args.kwargs["run_id"], self.OTHER_RUN_ID)

    def test_monthly_trend_uses_same_filters_and_permission(self):
        with patch("sku_return_routes.service.get_monthly_trend", return_value={"run_id": self.RUN_ID, "items": []}) as trend:
            response = self.client.get("/api/sku-returns/monthly-trend", params=[
                ("run_id", self.RUN_ID), ("period", "2026-06"), ("period", "2026-07"),
                ("entity", "B2B"), ("brand", "iGear"), ("sku_keyword", "  001  "),
            ])
            self.assertEqual(response.status_code, 200)
            trend.assert_called_once_with(filters={
                "period": ["2026-06", "2026-07"], "entity": ["B2B"],
                "category": [], "brand": ["iGear"], "supplier": [], "sku_keyword": "001",
            }, run_id=self.RUN_ID)
            self.allowed_mock.return_value = []
            self.assertEqual(self.client.get("/api/sku-returns/monthly-trend").status_code, 403)
            self.assertEqual(trend.call_count, 1)

    def test_unauthorized_user_cannot_read_or_export(self):
        self.allowed_mock.return_value = []
        with (
            patch("sku_return_routes.service.get_metadata") as metadata,
            patch("sku_return_routes.service.get_summary") as summary,
            patch("sku_return_routes.service.list_items") as items,
            patch("sku_return_routes.service.list_sources") as sources,
            patch("sku_return_routes.service.export_items") as export,
        ):
            for path in (
                "/api/sku-returns/metadata",
                "/api/sku-returns/options/suppliers",
                "/api/sku-returns/summary",
                "/api/sku-returns/items",
                "/api/sku-returns/sources?sku_code=1&sku_name=x",
                "/api/sku-returns/export",
                "/api/sku-returns/brand-rules",
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 403)
        metadata.assert_not_called()
        summary.assert_not_called()
        items.assert_not_called()
        sources.assert_not_called()
        export.assert_not_called()

    def test_unauthenticated_user_gets_401(self):
        with patch("main._get_authenticated_user", side_effect=HTTPException(401, "login required")):
            self.assertEqual(self.client.get("/api/sku-returns/metadata").status_code, 401)

    def test_brand_write_excludes_boss_even_with_page_permission(self):
        body = {"rules": [{"match_type": "prefix", "pattern": "测试旅行",
                           "canonical_brand": "测试旅行", "priority": 1, "enabled": True}]}
        with (
            patch("sku_return_routes.service.list_brand_rules") as list_rules,
            patch("sku_return_routes.service.preview_brand_rules") as preview,
            patch("sku_return_routes.service.replace_brand_rules") as replace,
        ):
            self.assertEqual(self.client.get("/api/sku-returns/brand-rules").status_code, 403)
            self.assertEqual(self.client.post("/api/sku-returns/brand-rules/preview", json=body).status_code, 403)
            self.assertEqual(self.client.put(
                "/api/sku-returns/brand-rules", json={**body, "expected_version": 1}
            ).status_code, 403)
        list_rules.assert_not_called()
        preview.assert_not_called()
        replace.assert_not_called()

    def test_operator_can_preview_and_update_brand_rules(self):
        self.user["role"] = "operator"
        rule = {"match_type": "prefix", "pattern": "测试旅行",
                "canonical_brand": "测试旅行", "priority": 1, "enabled": True}
        with (
            patch("sku_return_routes.service.preview_brand_rules", return_value={"matches": 2}) as preview,
            patch("sku_return_routes.service.replace_brand_rules", return_value={"version": 2}) as replace,
        ):
            self.assertEqual(self.client.post(
                "/api/sku-returns/brand-rules/preview", json={"rules": [rule]}
            ).json(), {"matches": 2})
            self.assertEqual(self.client.put(
                "/api/sku-returns/brand-rules",
                json={"rules": [rule], "expected_version": 1},
            ).json(), {"version": 2})
        preview.assert_called_once_with([rule])
        replace.assert_called_once_with([rule], 1, "buyer1")

    def test_admin_can_read_and_manage_without_explicit_page_grant(self):
        self.user["role"] = "admin"
        self.allowed_mock.return_value = []
        with (
            patch("sku_return_routes.service.get_metadata", return_value={"run_id": None}),
            patch("sku_return_routes.service.list_brand_rules", return_value={"version": 0, "items": []}),
        ):
            self.assertEqual(self.client.get("/api/sku-returns/metadata").status_code, 200)
            self.assertEqual(self.client.get("/api/sku-returns/brand-rules").status_code, 200)
        self.allowed_mock.assert_not_called()

    def test_brand_rule_text_cannot_exceed_database_column(self):
        self.user["role"] = "operator"
        with patch("sku_return_routes.service.preview_brand_rules") as preview:
            response = self.client.post(
                "/api/sku-returns/brand-rules/preview",
                json={"rules": [{"match_type": "prefix", "pattern": "甲" * 192,
                                 "canonical_brand": "品牌", "priority": 1, "enabled": True}]},
            )
        self.assertEqual(response.status_code, 422)
        preview.assert_not_called()

    def test_invalid_sort_and_page_size_are_rejected_before_service(self):
        with patch("sku_return_routes.service.list_items") as items:
            for params in (
                {"sort_by": "DROP TABLE sku_return_fact"},
                {"sort_by": "period", "view": "sku"},
                {"page_size": 201},
                {"run_id": "7"},
            ):
                with self.subTest(params=params):
                    self.assertEqual(self.client.get("/api/sku-returns/items", params=params).status_code, 422)
        items.assert_not_called()

    def test_stale_run_returns_refreshable_conflict(self):
        from utils.sku_return_service import StaleRunError
        with patch("sku_return_routes.service.get_summary", side_effect=StaleRunError("数据版本已过期，请刷新")):
            response = self.client.get("/api/sku-returns/summary", params={"run_id": self.RUN_ID})
        self.assertEqual(response.status_code, 409)
        self.assertIn("刷新", response.json()["detail"])

    def test_new_page_inherits_existing_chat_roles_without_overwrite(self):
        self.assertEqual(permission_service.PAGE_DEFS["sku-return-data"], "SKU 退货数据")
        self.assertEqual(set(permission_service.PAGE_DEFS), set(permission_service.PERM_DEFAULTS))
        issued = []

        class Result:
            def scalar(self):
                return json.dumps(["operator", "finance"])

        class Connection:
            def execute(self, sql, params=None):
                issued.append((str(sql), params))
                return Result()

        permission_service._ensure_page_permissions(Connection())
        insert = next(
            params for statement, params in issued
            if statement.startswith("INSERT IGNORE") and params["k"] == "sku-return-data"
        )
        self.assertEqual(json.loads(insert["r"]), ["operator", "finance"])
        self.assertTrue(any(
            "SELECT roles" in statement and params == {"source": "operating-chat"}
            for statement, params in issued
        ))

    def test_main_registers_sku_return_routes(self):
        import main

        paths = {route.path for route in main.app.routes}
        self.assertIn("/api/sku-returns/metadata", paths)
        self.assertIn("/api/sku-returns/export", paths)
        self.assertIn("/api/sku-returns/brand-rules", paths)


if __name__ == "__main__":
    unittest.main()
