from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from utils.sales_dashboard_service import (
    EXPECTED_HEADERS,
    _is_allowed_image_url,
    _read_sales_rows,
    _where_clause,
)


class SalesDashboardServiceTest(unittest.TestCase):
    def test_reads_requested_sales_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(EXPECTED_HEADERS)
            worksheet.append(["https://example.com/a.png", "SKU-001", "商品一", "箱包", "品牌A", 12, 10, 2])
            worksheet.append([None, "SKU-002", "商品二", "配件", "品牌B", 3, 3, 0])
            worksheet.append([None, "#", None, None, None, 15, 13, 2])
            workbook.save(path)

            rows = _read_sales_rows(path)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["product_code"], "SKU-001")
        self.assertEqual(rows[0]["image_url"], "https://example.com/a.png")
        self.assertEqual(rows[0]["returned_quantity"], 2.0)
        self.assertEqual(sum(row["sales_quantity"] for row in rows), 15.0)

    def test_builds_keyword_brand_and_category_filter(self) -> None:
        sql, params, bind_params = _where_clause("SKU", ["品牌A"], ["箱包"])

        self.assertIn("product_code LIKE :keyword", sql)
        self.assertIn("brand IN :brands", sql)
        self.assertIn("category IN :categories", sql)
        self.assertEqual(params["brands"], ["品牌A"])
        self.assertEqual(params["categories"], ["箱包"])
        self.assertEqual(len(bind_params), 2)

    def test_accepts_only_http_image_sources_for_proxy(self) -> None:
        self.assertTrue(_is_allowed_image_url("https://images.example.com/item.png"))
        self.assertTrue(_is_allowed_image_url("http://images.example.com/item.png"))
        self.assertFalse(_is_allowed_image_url("C:/images/item.png"))
        self.assertFalse(_is_allowed_image_url("javascript:alert(1)"))


if __name__ == "__main__":
    unittest.main()
