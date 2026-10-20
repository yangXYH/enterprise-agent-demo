import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

import main


class BusinessForecastApiTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _business_forecast_detail() -> dict[str, object]:
        return {
            "forecast": {
                "forecast_date": "2026-07-13",
                "target_start_date": "2026-07-14",
                "target_end_date": "2026-07-20",
                "sku_code": "SKU-1",
                "product_name": "测试商品",
                "brand": "测试品牌",
                "category": "测试类目",
                "sku_link_status": "LINKED",
                "days_covered": 31,
                "total_30d_units": 120.0,
                "recent_3d_avg": 5.0,
                "recent_7d_avg": 4.5,
                "recent_14d_avg": 4.0,
                "recent_30d_avg": 3.8,
                "base_pred_7d": 29.0,
                "adjusted_pred_7d": 34.8,
                "unit_momentum": 0.25,
                "visitor_momentum": 0.18,
                "cart_momentum": 0.12,
                "conversion_momentum": 0.08,
                "adjustment_factor": 1.2,
                "trend_level": "UP",
                "confidence_level": "HIGH",
                "affected_warehouse_count": 2,
                "suggestion_count": 1,
                "reason_json": (
                    '{"internal":"must not be sent",'
                    '"signal_scores":{"sales":0.25,"traffic":0.18,"interest":0.12,"conversion":0.08,"quality":0.05},'
                    '"signal_weights":{"sales":0.35,"traffic":0.2,"interest":0.2,"conversion":0.15,"quality":0.1},'
                    '"signal_details":{"traffic":{"visitors":{"momentum":0.18}}},'
                    '"guardrails":{"adjustment_low":0.8,"adjustment_high":1.25}}'
                ),
            },
            "cities": [
                {
                    "warehouse_code": "广州",
                    "predicted_city_7d": 8.4,
                    "daily_city_forecast": 1.2,
                    "target_days": 30.0,
                    "stock_qty": 8.0,
                    "inbound_qty": 2.0,
                    "available_qty": 10.0,
                    "days_of_supply": 6.7,
                    "risk_level": "HIGH",
                    "shortage_qty": 26.0,
                    "suggested_qty": 20.0,
                    "suggested_source": "花东仓",
                    "eta_days": 3,
                    "route_path": "花东仓 → 广州",
                    "reason": "经营趋势上涨且库存覆盖不足",
                    "internal_row_id": 99,
                },
                {
                    "warehouse_code": "上海",
                    "predicted_city_7d": 6.3,
                    "daily_city_forecast": 0.9,
                    "target_days": 30.0,
                    "stock_qty": 40.0,
                    "inbound_qty": 0.0,
                    "available_qty": 40.0,
                    "days_of_supply": 44.4,
                    "risk_level": "LOW",
                    "shortage_qty": 0.0,
                    "suggested_qty": 0.0,
                    "suggested_source": "",
                    "eta_days": 0,
                    "route_path": "",
                    "reason": "",
                },
            ],
        }

    async def test_inventory_import_refreshes_inventory_and_business_forecast(self) -> None:
        upload = UploadFile(filename="inventory.xlsx", file=BytesIO(b"xlsx-content"))
        captured_path: Path | None = None

        def fake_import(path: Path, engine: object, filename: str) -> dict[str, object]:
            nonlocal captured_path
            captured_path = Path(path)
            self.assertTrue(captured_path.exists())
            self.assertIsNone(engine)
            self.assertEqual(filename, "inventory.xlsx")
            return {"rows_read": 10, "snapshot_date": "2026-07-21"}

        inventory_result = {"snapshot_date": "2026-07-21", "plan_count": 8}
        business_result = {"forecast_date": "2026-07-21", "forecast_sku_count": 6}

        with (
            patch.object(main.inventory_service, "import_inventory_excel", side_effect=fake_import),
            patch.object(
                main.inventory_service,
                "recalculate_inventory_decisions",
                return_value=inventory_result,
            ) as inventory_recalculate,
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts",
                return_value=business_result,
            ) as business_recalculate,
            patch.object(
                main.sku_warning_service,
                "recalculate_sku_warnings",
                return_value={"snapshot_date": "2026-07-21", "forecast_sku_count": 4},
            ),
        ):
            response = await main.import_inventory_excel(upload, auto_calculate=True)

        self.assertEqual(response.data["import"]["rows_read"], 10)
        self.assertEqual(response.data["decision"], inventory_result)
        self.assertEqual(response.data["business_forecast"], business_result)
        inventory_recalculate.assert_called_once_with("2026-07-21")
        business_recalculate.assert_called_once_with(None)
        self.assertIsNotNone(captured_path)
        self.assertFalse(captured_path.exists())

    async def test_inventory_import_keeps_inventory_success_when_business_forecast_has_no_data(self) -> None:
        upload = UploadFile(filename="inventory.xlsx", file=BytesIO(b"xlsx-content"))
        inventory_result = {"snapshot_date": "2026-07-21", "plan_count": 8}

        with (
            patch.object(
                main.inventory_service,
                "import_inventory_excel",
                return_value={"rows_read": 10, "snapshot_date": "2026-07-21"},
            ),
            patch.object(
                main.inventory_service,
                "recalculate_inventory_decisions",
                return_value=inventory_result,
            ),
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts",
                side_effect=ValueError("暂无经营明细数据"),
            ),
            patch.object(
                main.sku_warning_service,
                "recalculate_sku_warnings",
                return_value={"snapshot_date": "2026-07-21", "forecast_sku_count": 4},
            ),
            patch.object(main.LOGGER, "warning") as logger_warning,
        ):
            response = await main.import_inventory_excel(upload, auto_calculate=True)

        self.assertEqual(response.data["decision"], inventory_result)
        self.assertTrue(response.data["business_forecast"]["skipped"])
        self.assertIn("暂无经营明细数据", response.data["business_forecast"]["reason"])
        logger_warning.assert_called_once()

    async def test_import_persists_temp_file_and_optionally_recalculates(self) -> None:
        upload = UploadFile(filename="经营报表.xlsx", file=BytesIO(b"xlsx-content"))
        captured_path: Path | None = None

        def fake_import(path: Path, engine: object, filename: str) -> dict[str, object]:
            nonlocal captured_path
            captured_path = Path(path)
            self.assertTrue(captured_path.exists())
            self.assertIsNone(engine)
            self.assertEqual(filename, "经营报表.xlsx")
            return {"rows_imported": 12, "max_biz_date": "2026-07-13"}

        with (
            patch.object(main.business_forecast_service, "import_business_excel", side_effect=fake_import),
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts",
                return_value={"forecast_sku_count": 3},
            ) as recalculate,
        ):
            response = await main.import_business_forecast_excel(upload, auto_calculate=True)

        self.assertEqual(response.data["import"]["rows_imported"], 12)
        self.assertEqual(response.data["forecast"]["forecast_sku_count"], 3)
        recalculate.assert_called_once_with("2026-07-13")
        self.assertIsNotNone(captured_path)
        self.assertFalse(captured_path.exists())

    async def test_import_value_error_becomes_bad_request(self) -> None:
        upload = UploadFile(filename="bad.xlsx", file=BytesIO(b"not-empty"))
        with patch.object(
            main.business_forecast_service,
            "import_business_excel",
            side_effect=ValueError("经营报表缺少必要字段"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.import_business_forecast_excel(upload, auto_calculate=False)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "经营报表缺少必要字段")

    async def test_recalculate_passes_date_and_clean_sku_filter(self) -> None:
        body = main.BusinessForecastRecalculateRequest(
            forecast_date="2026-07-13",
            sku_codes=[" SKU-1 ", "", "SKU-2"],
        )
        with patch.object(
            main.business_forecast_service,
            "recalculate_business_forecasts",
            return_value={"forecast_sku_count": 2},
        ) as service_call:
            response = await main.recalculate_business_forecast(body)

        self.assertEqual(response.data["forecast_sku_count"], 2)
        service_call.assert_called_once_with("2026-07-13", None, ["SKU-1", "SKU-2"])

    async def test_recalculate_unexpected_error_becomes_server_error(self) -> None:
        body = main.BusinessForecastRecalculateRequest()
        with (
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts",
                side_effect=RuntimeError("database unavailable"),
            ),
            patch.object(main.LOGGER, "exception"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.recalculate_business_forecast(body)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn("经营趋势预测计算失败", raised.exception.detail)

    async def test_list_passes_all_filters_and_pagination(self) -> None:
        service_result = {"items": [{"sku_code": "SKU-1"}], "total": 1, "page": 3, "page_size": 50}
        with patch.object(
            main.business_forecast_service,
            "list_business_forecasts",
            return_value=service_result,
        ) as service_call:
            response = await main.list_business_forecasts(
                forecast_date="2026-07-13",
                sku_code="SKU",
                product_name="测试商品",
                brand="测试品牌",
                category="测试类目",
                trend_level="UP",
                confidence_level="HIGH",
                sku_link_status="LINKED",
                page=3,
                page_size=50,
            )

        self.assertEqual(response.total, 1)
        service_call.assert_called_once_with(
            None,
            "2026-07-13",
            "SKU",
            "测试商品",
            "测试品牌",
            "测试类目",
            "UP",
            "HIGH",
            "LINKED",
            3,
            50,
        )

    async def test_detail_passes_sku_and_date(self) -> None:
        service_result = {
            "forecast": {"sku_code": "SKU-1"},
            "cities": [{"warehouse_code": "CITY-A"}],
        }
        with patch.object(
            main.business_forecast_service,
            "get_business_forecast_detail",
            return_value=service_result,
        ) as service_call:
            response = await main.get_business_forecast_detail(" SKU-1 ", "2026-07-13")

        self.assertEqual(response.cities[0]["warehouse_code"], "CITY-A")
        service_call.assert_called_once_with("SKU-1", None, "2026-07-13")

    async def test_options_adds_static_filter_enums(self) -> None:
        dynamic_options = {
            "forecast_dates": ["2026-07-13"],
            "business_dates": ["2026-07-13"],
            "brands": ["测试品牌"],
            "categories": ["测试类目"],
        }
        with patch.object(
            main.business_forecast_service,
            "get_business_forecast_options",
            return_value=dynamic_options,
        ) as service_call:
            response = await main.get_business_forecast_options()

        service_call.assert_called_once_with()
        self.assertEqual(response.data["trend_levels"], ["UP", "STABLE", "DOWN"])
        self.assertEqual(response.data["sku_link_statuses"], ["LINKED", "PENDING_LINK"])

    async def test_sku_decision_attaches_business_forecast_observation(self) -> None:
        inventory_result = {"sku_code": "SKU-1", "plans": []}
        business_result = {
            "forecast": {"sku_code": "SKU-1", "predicted_7d": 18.0},
            "cities": [{"warehouse_code": "CITY-A", "suggested_qty": 3.0}],
        }
        with (
            patch.object(
                main.inventory_service,
                "get_sku_replenishment_decision",
                return_value=inventory_result,
            ) as inventory_call,
            patch.object(
                main.business_forecast_service,
                "get_business_forecast_detail",
                return_value=business_result,
            ) as business_call,
        ):
            response = await main.get_inventory_sku_decision(
                "SKU-1",
                snapshot_date="2026-07-13",
                forecast_date="2026-07-14",
            )

        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"]["sku_code"], "SKU-1")
        self.assertEqual(response["data"]["business_forecast"]["status"], "AVAILABLE")
        self.assertEqual(response["data"]["business_forecast"]["forecast"]["predicted_7d"], 18.0)
        self.assertEqual(response["data"]["business_forecast"]["cities"][0]["suggested_qty"], 3.0)
        inventory_call.assert_called_once_with("SKU-1", "2026-07-13")
        business_call.assert_called_once_with("SKU-1", None, "2026-07-14")

    async def test_sku_decision_ignores_business_forecast_error(self) -> None:
        inventory_result = {"sku_code": "SKU-1", "plans": [{"transfer_qty": 5}]}
        with (
            patch.object(
                main.inventory_service,
                "get_sku_replenishment_decision",
                return_value=inventory_result,
            ),
            patch.object(
                main.business_forecast_service,
                "get_business_forecast_detail",
                side_effect=RuntimeError("forecast table unavailable"),
            ),
            patch.object(main.LOGGER, "warning") as logger_warning,
        ):
            response = await main.get_inventory_sku_decision("SKU-1")

        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"]["plans"][0]["transfer_qty"], 5)
        self.assertEqual(response["data"]["business_forecast"]["status"], "UNAVAILABLE")
        self.assertIsNone(response["data"]["business_forecast"]["forecast"])
        self.assertEqual(response["data"]["business_forecast"]["cities"], [])
        logger_warning.assert_called_once()

    async def test_ai_explain_uses_trusted_forecast_and_filtered_city_context(self) -> None:
        detail = self._business_forecast_detail()
        captured_context: dict[str, object] | None = None
        captured_message: str | None = None
        captured_history: list[main.BusinessForecastAgentMessage] | None = None

        async def fake_explain(
            context: dict[str, object],
            message: str,
            history: list[main.BusinessForecastAgentMessage],
        ) -> str:
            nonlocal captured_context, captured_message, captured_history
            captured_context = context
            captured_message = message
            captured_history = history
            return "未来7天全国需求上升，广州仓库存覆盖不足，建议优先关注补货。"

        body = main.BusinessForecastExplainRequest(
            sku_code=" SKU-1 ",
            forecast_date="2026-07-13",
            message="为什么要关注这个SKU？",
            messages=[main.BusinessForecastAgentMessage(role="user", content="先看趋势")],
        )
        with (
            patch.object(
                main.business_forecast_service,
                "get_business_forecast_detail",
                return_value=detail,
            ) as service_call,
            patch.object(
                main,
                "_explain_business_forecast_with_llm",
                side_effect=fake_explain,
            ) as ai_call,
        ):
            response = await main.explain_business_forecast(body)

        self.assertEqual(response.code, 200)
        self.assertEqual(response.source, "AI")
        self.assertIn("广州仓", response.answer)
        service_call.assert_called_once_with("SKU-1", None, "2026-07-13")
        ai_call.assert_awaited_once()
        self.assertEqual(captured_message, "为什么要关注这个SKU？")
        self.assertEqual(len(captured_history or []), 1)
        self.assertIsNotNone(captured_context)
        assert captured_context is not None
        national = captured_context["forecast"]
        cities = captured_context["cities"]
        self.assertEqual(national["adjusted_pred_7d"], 34.8)
        self.assertEqual(national["trend_level"], "UP")
        self.assertEqual(national["confidence_level"], "HIGH")
        self.assertEqual(national["adjustment_factor"], 1.2)
        self.assertNotIn("reason_json", national)
        self.assertIn("signal_context", national)
        self.assertEqual(national["signal_context"]["signal_scores"]["traffic"], 0.18)
        self.assertEqual(national["signal_context"]["signal_weights"]["sales"], 0.35)
        self.assertNotIn("internal", national["signal_context"])
        self.assertEqual([row["warehouse_code"] for row in cities], ["广州", "上海"])
        self.assertEqual(cities[0]["suggested_qty"], 20.0)
        self.assertEqual(cities[0]["days_of_supply"], 6.7)
        self.assertNotIn("internal_row_id", cities[0])

    def test_ai_context_normalizes_warehouse_aliases_before_city_allowlist(self) -> None:
        context = main._business_forecast_ai_context(
            {
                "forecast": {"sku_link_status": "LINKED"},
                "cities": [
                    {"warehouse_code": "上海RDC", "suggested_qty": 11.0},
                    {"warehouse_code": "广州仓", "suggested_qty": 7.0},
                    {"warehouse_code": "杭州仓", "suggested_qty": 5.0},
                ],
            }
        )

        self.assertEqual(
            [row["warehouse_code"] for row in context["cities"]],
            ["上海", "广州"],
            "AI context 应先用 inventory_service._base_city 归一化仓名，再按八大仓白名单过滤",
        )
        self.assertEqual(
            [row["suggested_qty"] for row in context["cities"]],
            [11.0, 7.0],
        )

    async def test_ai_explain_missing_forecast_returns_not_found(self) -> None:
        body = main.BusinessForecastExplainRequest(sku_code="SKU-NOT-FOUND")
        with (
            patch.object(
                main.business_forecast_service,
                "get_business_forecast_detail",
                return_value={"forecast": None, "cities": []},
            ) as service_call,
            patch.object(main, "_explain_business_forecast_with_llm") as ai_call,
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.explain_business_forecast(body)

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("经营趋势预测", raised.exception.detail)
        service_call.assert_called_once_with("SKU-NOT-FOUND", None, None)
        ai_call.assert_not_called()

    async def test_ai_explain_llm_error_uses_existing_server_error_policy(self) -> None:
        body = main.BusinessForecastExplainRequest(sku_code="SKU-1")
        with (
            patch.object(
                main.business_forecast_service,
                "get_business_forecast_detail",
                return_value=self._business_forecast_detail(),
            ),
            patch.object(
                main,
                "_explain_business_forecast_with_llm",
                side_effect=RuntimeError("LLM unavailable"),
            ),
            patch.object(main.LOGGER, "exception") as logger_exception,
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.explain_business_forecast(body)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn("经营趋势解释生成失败", raised.exception.detail)
        logger_exception.assert_called_once()

    async def test_inventory_policy_recalculate_refreshes_business_forecast_scope(self) -> None:
        body = main.InventoryPolicyUpsertRequest(
            policy_type="BRAND",
            brand="Test Brand",
            category="",
            target_days=45,
            reserve_days=15,
            supplier_eta_days=7,
            allow_jd_transfer=True,
            preferred_source_warehouse="Hub",
            recalculate=True,
        )
        policy = {
            "policy_type": "BRAND",
            "brand": "Test Brand",
            "category": "",
            "target_days": 45,
        }
        inventory_result = {"plan_count": 3}
        business_result = {"forecast_sku_count": 2, "policy_scope_sku_count": 2}

        with (
            patch.object(main.inventory_service, "upsert_replenishment_policy", return_value=policy),
            patch.object(
                main.inventory_service,
                "recalculate_inventory_decisions",
                return_value=inventory_result,
            ) as inventory_recalculate,
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts_for_policy_scope",
                return_value=business_result,
            ) as business_recalculate,
        ):
            response = await main.upsert_inventory_policy(body)

        self.assertEqual(response["data"]["recalculation"], inventory_result)
        self.assertEqual(response["data"]["business_forecast_recalculation"], business_result)
        inventory_recalculate.assert_called_once_with(None, None, "Test Brand", None)
        business_recalculate.assert_called_once_with(None, None, "BRAND", "Test Brand", "")

    def test_routes_are_registered_before_spa_fallback(self) -> None:
        routes = {
            (route.path, tuple(sorted(getattr(route, "methods", None) or [])))
            for route in main.app.routes
        }
        self.assertIn(("/api/inventory/business-forecast/import", ("POST",)), routes)
        self.assertIn(("/api/inventory/business-forecast/recalculate", ("POST",)), routes)
        self.assertIn(("/api/inventory/business-forecast/options", ("GET",)), routes)
        self.assertIn(("/api/inventory/business-forecast/summary", ("GET",)), routes)
        self.assertIn(("/api/inventory/business-forecast/forecasts", ("GET",)), routes)
        self.assertIn(("/api/inventory/business-forecast/detail", ("GET",)), routes)
        self.assertIn(("/api/inventory/business-forecast/purchase-rows", ("GET",)), routes)
        self.assertIn(("/api/inventory/business-forecast/export-purchase", ("GET",)), routes)
        self.assertIn(("/api/ai/business_forecast/explain", ("POST",)), routes)


if __name__ == "__main__":
    unittest.main()
