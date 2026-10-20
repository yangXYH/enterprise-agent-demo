import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from utils import inventory_service


class InventoryMonitorServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        schema = patch.object(inventory_service, "ensure_inventory_schema")
        schema.start()
        self.addCleanup(schema.stop)
        with self.engine.begin() as conn:
            conn.execute(text("""CREATE TABLE inv_monitor_snapshot (
                snapshot_date TEXT, sku_code TEXT, product_name TEXT, brand TEXT,
                category_l1 TEXT, category_l2 TEXT, category_l3 TEXT, shop_name TEXT,
                product_status TEXT,
                national_stock_qty INTEGER, national_orderable_qty INTEGER,
                national_sales_1d INTEGER, national_sales_7d INTEGER,
                national_sales_30d INTEGER, city_metrics TEXT
            )"""))
        self.insert("2026-09-12", "SKU-A", "Alpha", "Food", "Main", 30)
        self.insert("2026-09-12", "SKU-B", "Alphabet", "Foods", "Mainland", 20)
        self.insert("2026-09-12", "SKU-C", "Alpha", "Food", "Main", 10)
        self.insert("2026-09-11", "SKU-OLD", "Old", "Other", "Archive", 99)
        self.insert("2026-09-10", "SKU-EMPTY", "", "   ", None, 1)

    def insert(self, day, sku, brand, category, shop, stock, status="", metrics=None):
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO inv_monitor_snapshot VALUES (
                :day, :sku, :name, :brand, :category, '', '', :shop, :status,
                :stock, :stock, 1, 7, 30, :metrics
            )"""), dict(day=day, sku=sku, name=f"Product {sku}", brand=brand,
                        category=category, shop=shop, stock=stock, status=status,
                        metrics=metrics or '{"Shanghai": {"stock_qty": 3}}'))

    def query(self, **kwargs):
        return inventory_service.list_inventory_monitor(engine=self.engine, **kwargs)

    def test_latest_pagination_and_full_filter_options(self):
        result = self.query(page=2, page_size=1)
        self.assertEqual(result["total"], 3)
        self.assertEqual([row["sku_code"] for row in result["items"]], ["SKU-B"])
        self.assertEqual(result["summary"]["snapshot_date"], "2026-09-12")
        self.assertEqual(result["summary"]["stock_qty"], 60)
        self.assertEqual(result["items"][0]["city_metrics"]["Shanghai"]["stock_qty"], 3)
        self.assertEqual(result["filter_options"], {
            "snapshot_dates": ["2026-09-12", "2026-09-11", "2026-09-10"],
            "brands": ["Alpha", "Alphabet", "Old"],
            "categories": ["Food", "Foods", "Other"],
            "shops": ["Archive", "Main", "Mainland"],
        })

    def test_exact_filters_and_options_are_independent(self):
        expected_options = self.query()["filter_options"]
        for filters in ({"brand": "Alpha"}, {"category_l1": "Food"},
                        {"shop_name": "Main"},
                        {"brand": "Alpha", "category_l1": "Food", "shop_name": "Main"}):
            with self.subTest(filters=filters):
                result = self.query(**filters)
                self.assertEqual([row["sku_code"] for row in result["items"]], ["SKU-A", "SKU-C"])
                self.assertEqual(result["filter_options"], expected_options)

    def test_explicit_date_and_keyword(self):
        result = self.query(snapshot_date="2026-09-11", keyword="SKU-OLD")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["snapshot_date"], "2026-09-11")
        self.assertEqual(result["summary"]["stock_qty"], 99)
        self.assertEqual(self.query(keyword="Product SKU-C")["total"], 1)

    def test_product_status_filter_groups_equivalent_shelf_statuses(self):
        self.insert("2026-09-12", "SKU-LISTED", "Alpha", "Food", "Main", 8, "可上柜")
        self.insert("2026-09-12", "SKU-OFF", "Alpha", "Food", "Main", 7, "下架")

        listed = self.query(product_status="上柜")
        self.assertEqual([row["sku_code"] for row in listed["items"]], ["SKU-LISTED"])

        delisted = self.query(product_status=["下柜"])
        self.assertEqual([row["sku_code"] for row in delisted["items"]], ["SKU-OFF"])

        all_statuses = self.query(product_status=["上柜", "下柜"])
        self.assertEqual(all_statuses["total"], 2)

    def test_no_match_and_page_out_of_range_keep_options(self):
        options = self.query()["filter_options"]
        for filters in ({"brand": "Missing"}, {"snapshot_date": "2026-01-01"},
                        {"shop_name": "Main' OR 1=1 --"}):
            with self.subTest(filters=filters):
                result = self.query(**filters)
                self.assertEqual(result["items"], [])
                self.assertEqual(result["total"], 0)
                self.assertEqual(result["summary"]["stock_qty"], 0)
                self.assertEqual(result["filter_options"], options)
        result = self.query(page=99, page_size=1)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["filter_options"], options)

    def test_empty_table(self):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM inv_monitor_snapshot"))
        result = self.query()
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertIsNone(result["summary"]["snapshot_date"])
        self.assertEqual(result["filter_options"], {
            "snapshot_dates": [], "brands": [], "categories": [], "shops": [],
        })

    def test_metric_summary_and_details_use_shop_filter(self):
        metrics = '{"\\u4e0a\\u6d77": {"stock_qty": 0, "sales_30d": 60}, "\\u5317\\u4eac": {"stock_qty": 8, "sales_30d": 0}}'
        self.insert("2026-09-12", "SKU-OUT", "Alpha", "Food", "Main", 8, "\u4e0a\u67dc", metrics)
        self.insert("2026-09-12", "SKU-OFF", "Alpha", "Food", "Other", 9, "\u4e0b\u67dc", '{"Shanghai": {"stock_qty": 9, "sales_30d": 0}}')

        result = self.query(shop_name="Main")
        self.assertEqual(result["summary"]["metrics"]["stockout"], 1)
        self.assertEqual(result["summary"]["metrics"]["shortage"], 1)
        self.assertEqual(result["summary"]["metrics"]["listed"], 1)
        self.assertEqual(result["summary"]["metrics"]["delisted"], 0)

        details = inventory_service.list_inventory_monitor_details(
            engine=self.engine, metric="shortage", shop_name="Main"
        )
        self.assertEqual(details["total"], 1)
        self.assertEqual(details["items"][0]["warehouse"], "\u4e0a\u6d77\u4ed3")
        self.assertEqual(details["items"][0]["category_l1"], "Food")
        self.assertEqual(details["items"][0]["daily_sales"], 2.0)
        self.assertEqual(details["items"][0]["target_stock_qty"], 60.0)
        self.assertEqual(details["items"][0]["shortage_qty"], 60.0)

        delisted = inventory_service.list_inventory_monitor_details(
            engine=self.engine, metric="delisted", shop_name="Other"
        )
        self.assertEqual([item["sku_code"] for item in delisted["items"]], ["SKU-OFF"])
        self.assertEqual(delisted["items"][0]["national_stock_qty"], 9.0)
        self.assertEqual(delisted["items"][0]["city_metrics"]["Shanghai"]["stock_qty"], 9)


if __name__ == "__main__":
    unittest.main()
