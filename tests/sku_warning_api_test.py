import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile

import main


class SkuWarningApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_import_refreshes_sku_warning(self) -> None:
        upload = UploadFile(filename="inventory.xlsx", file=BytesIO(b"xlsx-content"))
        captured_path: Path | None = None

        def fake_import(path: Path, engine: object, filename: str) -> dict[str, object]:
            nonlocal captured_path
            captured_path = Path(path)
            return {"rows_read": 10, "snapshot_date": "2026-07-21"}

        inventory_result = {"snapshot_date": "2026-07-21", "plan_count": 8}
        business_result = {"forecast_date": "2026-07-21", "forecast_sku_count": 6}
        warning_result = {"snapshot_date": "2026-07-21", "forecast_sku_count": 4}

        with (
            patch.object(main.inventory_service, "import_inventory_excel", side_effect=fake_import),
            patch.object(
                main.inventory_service,
                "recalculate_inventory_decisions",
                return_value=inventory_result,
            ),
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts",
                return_value=business_result,
            ),
            patch.object(
                main.sku_warning_service,
                "recalculate_sku_warnings",
                return_value=warning_result,
            ) as warning_recalculate,
        ):
            response = await main.import_inventory_excel(upload, auto_calculate=True)

        self.assertEqual(response.data["sku_warning"], warning_result)
        warning_recalculate.assert_called_once_with("2026-07-21")
        self.assertIsNotNone(captured_path)
        self.assertFalse(captured_path.exists())

    async def test_inventory_import_keeps_success_when_sku_warning_fails(self) -> None:
        upload = UploadFile(filename="inventory.xlsx", file=BytesIO(b"xlsx-content"))

        with (
            patch.object(
                main.inventory_service,
                "import_inventory_excel",
                return_value={"rows_read": 10, "snapshot_date": "2026-07-21"},
            ),
            patch.object(
                main.inventory_service,
                "recalculate_inventory_decisions",
                return_value={"snapshot_date": "2026-07-21", "plan_count": 8},
            ),
            patch.object(
                main.business_forecast_service,
                "recalculate_business_forecasts",
                return_value={"forecast_date": "2026-07-21", "forecast_sku_count": 6},
            ),
            patch.object(
                main.sku_warning_service,
                "recalculate_sku_warnings",
                side_effect=RuntimeError("warning boom"),
            ),
            patch.object(main.LOGGER, "warning") as logger_warning,
        ):
            response = await main.import_inventory_excel(upload, auto_calculate=True)

        self.assertTrue(response.data["sku_warning"]["skipped"])
        self.assertIn("warning boom", response.data["sku_warning"]["reason"])
        logger_warning.assert_called_once()

    async def test_list_sku_warnings_passes_params(self) -> None:
        payload = {
            "items": [{"sku_code": "SKU-1", "status": "SAFE"}],
            "total": 1,
            "page": 2,
            "page_size": 50,
            "snapshot_date": "2026-08-05",
            "forecast_days": 90,
            "summary": {"total": 1, "shortage_count": 0, "safe_count": 1, "no_jushuitan_count": 0},
            "brands": ["品牌A"],
            "categories": ["箱包"],
        }
        with patch.object(
            main.sku_warning_service,
            "list_sku_warnings",
            return_value=payload,
        ) as list_warnings:
            response = await main.list_sku_warnings(
                snapshot_date="2026-08-05",
                view="safe",
                sku_code="SKU-1",
                product_name="商品",
                brand="品牌A",
                category="箱包",
                forecast_days=90,
                page=2,
                page_size=50,
            )

        list_warnings.assert_called_once_with(
            None,
            "2026-08-05",
            "safe",
            "SKU-1",
            "商品",
            "品牌A",
            "箱包",
            90,
            2,
            50,
        )
        self.assertEqual(response.items[0]["sku_code"], "SKU-1")
        self.assertEqual(response.total, 1)

    async def test_recalculate_endpoint_passes_snapshot_date(self) -> None:
        with patch.object(
            main.sku_warning_service,
            "recalculate_sku_warnings",
            return_value={"snapshot_date": "2026-08-05", "forecast_sku_count": 3},
        ) as recalculate:
            response = await main.recalculate_sku_warnings(snapshot_date="2026-08-05")

        recalculate.assert_called_once_with("2026-08-05")
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"]["forecast_sku_count"], 3)

    async def test_options_endpoint(self) -> None:
        payload = {
            "snapshot_dates": ["2026-08-05"],
            "latest_snapshot_date": "2026-08-05",
            "brands": ["品牌A"],
            "categories": ["箱包"],
        }
        with patch.object(
            main.sku_warning_service,
            "get_sku_warning_options",
            return_value=payload,
        ):
            response = await main.get_sku_warning_options()

        self.assertEqual(response.data["latest_snapshot_date"], "2026-08-05")
        self.assertEqual(response.data["brands"], ["品牌A"])

    async def test_save_setting_endpoint(self) -> None:
        with patch.object(
            main.sku_warning_service,
            "save_sku_warning_setting",
            return_value={"forecast_days": 90},
        ) as save_setting:
            response = await main.save_sku_warning_setting(
                main.SkuWarningSettingRequest(forecast_days=90)
            )

        save_setting.assert_called_once_with(90)
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"]["forecast_days"], 90)


if __name__ == "__main__":
    unittest.main()
