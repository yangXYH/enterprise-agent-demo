from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from utils.jushuitan_dashboard_service import EXPECTED_HEADERS, _read_products, _where_clause


class JushuitanDashboardServiceTest(unittest.TestCase):
    def test_reads_jushuitan_rows_and_preserves_product_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "products.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(EXPECTED_HEADERS)
            worksheet.append(
                [None, "STYLE-1", "00123", "商品一", "品牌A", "黑色L", "黑色", "L", 9, 2, 7, "2026/9/12 16:30:00"]
            )
            worksheet.append(
                [None, "STYLE-1", "00123", "重复商品", "品牌A", "", "", "", 1, 0, 1, "2026/9/12 16:30:00"]
            )
            workbook.save(path)

            products = _read_products(path)

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["product_code"], "00123")
        self.assertEqual(products[0]["available_stock"], 7.0)
        self.assertEqual(products[0]["stock_updated_at"].year, 2026)

    def test_builds_filter_clause_for_brand_and_low_stock(self) -> None:
        sql, params, bind_params = _where_clause("双肩包", ["测试旅行"], "low")

        self.assertIn("product_name LIKE :keyword", sql)
        self.assertIn("brand IN :brands", sql)
        self.assertIn("available_stock > 0 AND available_stock <= 5", sql)
        self.assertEqual(params["brands"], ["测试旅行"])
        self.assertEqual(len(bind_params), 1)


if __name__ == "__main__":
    unittest.main()
