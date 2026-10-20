from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from utils.inventory_product_dashboard_service import (
    EXPECTED_HEADERS,
    _read_products,
    parse_report_date,
    report_period,
)


class InventoryProductDashboardServiceTest(unittest.TestCase):
    def test_reads_requested_fields_and_stagnant_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "进销存_按商品_20260914141038_192911439_1.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(EXPECTED_HEADERS)
            worksheet.append(["https://example.com/a.png", "箱包", "STYLE-1", "00123", "商品一", "黑色", "品牌A", 10, 10])
            worksheet.append([None, "双肩包", "STYLE-2", "SKU-2", "商品二", "蓝色", "品牌B", 10, 8])
            workbook.save(path)

            rows = _read_products(path)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["product_code"], "00123")
        self.assertEqual(rows[0]["opening_quantity"], 10.0)
        self.assertEqual(rows[1]["closing_quantity"], 8.0)

    def test_derives_requested_period_from_filename_date(self) -> None:
        report_date = parse_report_date("进销存_按商品_20260914141038_192911439_1.xlsx")
        self.assertEqual(report_date, date(2026, 9, 14))
        self.assertEqual(report_period(report_date), (date(2026, 9, 6), date(2026, 9, 13)))


if __name__ == "__main__":
    unittest.main()
