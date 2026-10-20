import unittest
from datetime import date
from unittest.mock import patch

from utils import inventory_service, sku_warning_service


class _Ctx:
    def __init__(self, value):
        self._value = value

    def __enter__(self):
        return self._value

    def __exit__(self, *args):
        return False


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return [dict(row) for row in self._rows]

    def scalar(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, result):
        self._result = result

    def execute(self, sql, params=None):
        return self._result


class _CaptureConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Engine:
    def __init__(self, results, capture=None):
        self._results = [_Result(result) for result in results]
        self._index = 0
        self._capture = capture

    def connect(self):
        result = self._results[min(self._index, len(self._results) - 1)]
        self._index += 1
        return _Ctx(_Conn(result))

    def begin(self):
        return _Ctx(self._capture)


class SkuWarningListTest(unittest.TestCase):
    def setUp(self) -> None:
        self.forecast_rows = [
            {
                "snapshot_date": date(2026, 8, 5),
                "sku_code": "SKU-A",
                "product_name": "商品A",
                "brand": "品牌A",
                "category": "箱包",
                "warehouse_count": 2,
                "daily_sales": 1.6667,
                "predicted_60d": 100.0,
            },
            {
                "snapshot_date": date(2026, 8, 5),
                "sku_code": "SKU-B",
                "product_name": "商品B",
                "brand": "品牌B",
                "category": "箱包",
                "warehouse_count": 1,
                "daily_sales": 0.1667,
                "predicted_60d": 10.0,
            },
            {
                "snapshot_date": date(2026, 8, 5),
                "sku_code": "SKU-C",
                "product_name": "商品C",
                "brand": "",
                "category": "",
                "warehouse_count": 1,
                "daily_sales": 0.0833,
                "predicted_60d": 5.0,
            },
        ]

    def _build_engine(self):
        return _Engine([self.forecast_rows])

    def test_shortage_view_includes_shortage_and_no_jushuitan(self):
        stock_rows = {
            ("花东仓", "SKU-A"): {"stock_qty": 30, "snapshot_time": "2026-08-05 10:00:00"},
            ("南沙仓", "SKU-A"): {"stock_qty": 5, "snapshot_time": "2026-08-05 09:00:00"},
            ("花东仓", "SKU-B"): {"stock_qty": 20, "snapshot_time": "2026-08-05 10:00:00"},
        }
        with (
            patch.object(sku_warning_service, "ensure_schema", return_value=None),
            patch.object(
                sku_warning_service,
                "_resolve_warning_date",
                return_value=date(2026, 8, 5),
            ),
            patch.object(
                inventory_service,
                "_latest_supply_stocks_by_warehouse",
                return_value=stock_rows,
            ),
        ):
            result = sku_warning_service.list_sku_warnings(
                engine=self._build_engine(),
                view="shortage",
                forecast_days=60,
            )

        self.assertEqual(result["total"], 2)
        self.assertEqual([item["sku_code"] for item in result["items"]], ["SKU-A", "SKU-C"])
        sku_a = result["items"][0]
        self.assertEqual(sku_a["jst_stock_qty"], 35.0)
        self.assertEqual(sku_a["shortage_qty"], 65)
        self.assertEqual(sku_a["status"], "SHORTAGE")
        self.assertEqual(result["items"][1]["status"], "NO_JUSHUITAN")
        self.assertEqual(result["summary"]["shortage_count"], 1)
        self.assertEqual(result["summary"]["safe_count"], 1)
        self.assertEqual(result["summary"]["no_jushuitan_count"], 1)
        self.assertEqual(result["forecast_days"], 60)

    def test_safe_view_returns_only_safe_skus(self):
        stock_rows = {
            ("花东仓", "SKU-A"): {"stock_qty": 200},
            ("花东仓", "SKU-B"): {"stock_qty": 20},
        }
        with (
            patch.object(sku_warning_service, "ensure_schema", return_value=None),
            patch.object(
                sku_warning_service,
                "_resolve_warning_date",
                return_value=date(2026, 8, 5),
            ),
            patch.object(
                inventory_service,
                "_latest_supply_stocks_by_warehouse",
                return_value=stock_rows,
            ),
        ):
            result = sku_warning_service.list_sku_warnings(
                engine=self._build_engine(),
                view="safe",
                forecast_days=60,
            )

        self.assertEqual([item["sku_code"] for item in result["items"]], ["SKU-A", "SKU-B"])
        self.assertTrue(all(item["status"] == "SAFE" for item in result["items"]))

    def test_filters_by_brand_and_sku(self):
        stock_rows = {
            ("花东仓", "SKU-A"): {"stock_qty": 30},
            ("花东仓", "SKU-B"): {"stock_qty": 20},
        }
        with (
            patch.object(sku_warning_service, "ensure_schema", return_value=None),
            patch.object(
                sku_warning_service,
                "_resolve_warning_date",
                return_value=date(2026, 8, 5),
            ),
            patch.object(
                inventory_service,
                "_latest_supply_stocks_by_warehouse",
                return_value=stock_rows,
            ),
        ):
            result = sku_warning_service.list_sku_warnings(
                engine=self._build_engine(),
                view="all",
                sku_code="SKU-A",
                brand="品牌A",
                forecast_days=60,
            )

        self.assertEqual([item["sku_code"] for item in result["items"]], ["SKU-A"])

    def test_forecast_days_changes_predicted_sales_and_status(self):
        stock_rows = {
            ("花东仓", "SKU-A"): {"stock_qty": 100},
            ("花东仓", "SKU-B"): {"stock_qty": 20},
        }
        with (
            patch.object(sku_warning_service, "ensure_schema", return_value=None),
            patch.object(
                sku_warning_service,
                "_resolve_warning_date",
                return_value=date(2026, 8, 5),
            ),
            patch.object(
                inventory_service,
                "_latest_supply_stocks_by_warehouse",
                return_value=stock_rows,
            ),
        ):
            result = sku_warning_service.list_sku_warnings(
                engine=self._build_engine(),
                view="all",
                forecast_days=120,
            )

        by_sku = {item["sku_code"]: item for item in result["items"]}
        self.assertEqual(by_sku["SKU-A"]["predicted_sales"], 200.0)
        self.assertEqual(by_sku["SKU-A"]["shortage_qty"], 100)
        self.assertEqual(by_sku["SKU-A"]["status"], "SHORTAGE")
        self.assertEqual(by_sku["SKU-C"]["status"], "NO_JUSHUITAN")


class SkuWarningRecalculateTest(unittest.TestCase):
    def test_predicted_60d_sums_warehouse_daily_sales(self):
        snapshot_rows = [
            {
                "sku_code": "SKU-1",
                "warehouse_code": "广州",
                "sales_1d": 12,
                "sales_7d": 70,
                "sales_30d": 300,
            },
            {
                "sku_code": "SKU-1",
                "warehouse_code": "上海",
                "sales_1d": 1,
                "sales_7d": 7,
                "sales_30d": 30,
            },
        ]
        meta_rows = [
            {
                "sku_code": "SKU-1",
                "product_name": "商品A",
                "brand": "品牌A",
                "category": "箱包",
            }
        ]
        capture = _CaptureConn()
        engine = _Engine([snapshot_rows, meta_rows], capture=capture)
        with (
            patch.object(sku_warning_service, "ensure_schema", return_value=None),
            patch.object(
                sku_warning_service,
                "_resolve_snapshot_date",
                return_value=date(2026, 8, 5),
            ),
        ):
            result = sku_warning_service.recalculate_sku_warnings(engine=engine)

        self.assertEqual(result["forecast_sku_count"], 1)
        insert_call = capture.calls[1]
        inserted = insert_call[1]
        self.assertEqual(len(inserted), 1)
        row = inserted[0]
        self.assertEqual(row["sku_code"], "SKU-1")
        self.assertEqual(row["warehouse_count"], 2)
        self.assertAlmostEqual(row["daily_sales"], 11.2, places=4)
        self.assertAlmostEqual(row["predicted_60d"], 672.0, places=4)
        self.assertEqual(row["brand"], "品牌A")
        self.assertEqual(row["category"], "箱包")


if __name__ == "__main__":
    unittest.main()
