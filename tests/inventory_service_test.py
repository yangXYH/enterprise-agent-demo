import unittest
from datetime import date
from unittest.mock import MagicMock

from utils import inventory_service


class ForecastDailySalesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {
            "sku_code": "SKU-001",
            "warehouse_code": "SH",
            "stock_qty": 0,
            "inbound_qty": 0,
            "sales_1d": 12,
            "sales_7d": 70,
            "sales_30d": 300,
        }

    def test_forecast_uses_latest_snapshot_only(self) -> None:
        empty_history = inventory_service._forecast_daily_sales(self.snapshot)
        rich_history = inventory_service._forecast_daily_sales(
            self.snapshot,
            [
                {
                    "snapshot_date": date(2026, 7, 30),
                    "sku_code": "SKU-001",
                    "warehouse_code": "SH",
                    "stock_qty": 0,
                    "inbound_qty": 0,
                    "sales_1d": 2,
                    "sales_7d": 14,
                    "sales_30d": 60,
                },
                {
                    "snapshot_date": date(2026, 7, 29),
                    "sku_code": "SKU-001",
                    "warehouse_code": "SH",
                    "stock_qty": 0,
                    "inbound_qty": 0,
                    "sales_1d": 20,
                    "sales_7d": 140,
                    "sales_30d": 600,
                },
            ],
        )

        self.assertEqual(empty_history["daily_sales"], rich_history["daily_sales"])
        self.assertEqual(rich_history["trend_factor"], 1.0)
        self.assertEqual(rich_history["volatility_factor"], 1.0)

    def test_forecast_base_formula(self) -> None:
        forecast = inventory_service._forecast_daily_sales(self.snapshot)

        self.assertAlmostEqual(forecast["daily_sales"], 10.2, places=4)
        self.assertEqual(forecast["trend_factor"], 1.0)
        self.assertEqual(forecast["volatility_factor"], 1.0)

    def test_risk_rows_do_not_depend_on_history(self) -> None:
        rows, stats = inventory_service._calculate_risk_rows(
            run_id=1,
            snapshot_date=date(2026, 7, 31),
            snapshots=[{**self.snapshot, "brand": "", "category": ""}],
            policies={},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["HIGH"], 1)
        self.assertAlmostEqual(rows[0]["daily_sales"], 10.2, places=4)
        self.assertEqual(rows[0]["trend_factor"], 1.0)
        self.assertEqual(rows[0]["volatility_factor"], 1.0)
        self.assertEqual(rows[0]["consecutive_high_days"], 0)
        self.assertAlmostEqual(rows[0]["need_qty"], 306.0, places=4)

    def test_inbound_is_treated_as_already_arrived(self) -> None:
        forecast = inventory_service._forecast_daily_sales(
            {
                "sku_code": "SKU-INBOUND",
                "warehouse_code": "SH",
                "stock_qty": 10,
                "inbound_qty": 40,
                "sales_1d": 5,
                "sales_7d": 35,
                "sales_30d": 150,
            }
        )

        self.assertEqual(inventory_service._inbound_credit_qty(40, forecast["daily_sales"]), 40.0)

        rows, _ = inventory_service._calculate_risk_rows(
            run_id=1,
            snapshot_date=date(2026, 7, 31),
            snapshots=[
                {
                    "sku_code": "SKU-INBOUND",
                    "warehouse_code": "SH",
                    "stock_qty": 10,
                    "inbound_qty": 40,
                    "sales_1d": 5,
                    "sales_7d": 35,
                    "sales_30d": 150,
                    "brand": "",
                    "category": "",
                }
            ],
            policies={},
        )

        self.assertEqual(rows[0]["available_qty"], 50.0)
        self.assertEqual(rows[0]["inbound_credit_qty"], 40.0)
        self.assertEqual(rows[0]["inbound_credit_rate"], 1.0)


class InventoryHistoryPurgeTest(unittest.TestCase):
    def test_purge_keeps_three_days_and_skips_business_tables(self) -> None:
        cutoff = date(2026, 7, 29)
        conn = MagicMock()

        def fake_execute(sql, params=None):
            if params and "offset" in params:
                result = MagicMock()
                result.scalar.return_value = cutoff
                return result
            result = MagicMock()
            result.rowcount = 3
            return result

        conn.execute.side_effect = fake_execute

        deleted = inventory_service._purge_old_inventory_history(conn)

        self.assertGreater(deleted, 0)
        delete_calls = [
            str(call.args[0])
            for call in conn.execute.call_args_list
            if str(call.args[0]).startswith("DELETE")
        ]
        self.assertEqual(len(delete_calls), 7)
        self.assertTrue(any("inv_stock_snapshot" in sql for sql in delete_calls))
        self.assertTrue(any("inv_risk_score" in sql for sql in delete_calls))
        self.assertTrue(any("inv_transfer_plan" in sql for sql in delete_calls))
        self.assertFalse(any("inv_business" in sql for sql in delete_calls))

    def test_purge_does_nothing_with_less_than_three_dates(self) -> None:
        conn = MagicMock()
        conn.execute.return_value = MagicMock()
        conn.execute.return_value.scalar.return_value = None

        deleted = inventory_service._purge_old_inventory_history(conn)

        self.assertEqual(deleted, 0)
        conn.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
