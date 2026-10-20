"""Accounting and privacy contracts for the independently reproducible public demo."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicDemoDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "demo/data.js").read_text(encoding="utf8")
        cls.data = json.loads(source.split("window.DEMO_DATA = ", 1)[1].rstrip(";\n"))

    def test_complete_and_unique_month_shop_coverage(self):
        data = self.data
        self.assertTrue(data["meta"]["synthetic"])
        expected = {(month, shop["channel"], shop["shop_id"]) for month in data["months"] for shop in data["shops"]}
        actual = [(row["month"], row["channel"], row["shop_id"]) for row in data["rows"]]
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(set(actual), expected)

    def test_financial_totals_and_individual_records_balance(self):
        for row in self.data["rows"]:
            with self.subTest(month=row["month"], shop=row["shop_id"]):
                self.assertAlmostEqual(row["total_fees"], sum(row[key] for key in self.data["fee_keys"]), places=2)
                self.assertAlmostEqual(row["gross_profit"], row["revenue"] - row["costG"], places=2)
                self.assertAlmostEqual(row["net_profit"], row["gross_profit"] - row["total_fees"], places=2)
                self.assertEqual(row["labor"], 0)
        revenue = sum(row["revenue"] for row in self.data["rows"])
        profit = sum(row["net_profit"] for row in self.data["rows"])
        costs = sum(row["costG"] + row["total_fees"] for row in self.data["rows"])
        self.assertAlmostEqual(revenue, profit + costs, places=2)

    def test_public_snapshot_matches_offline_fixture(self):
        snapshot = json.loads((ROOT / "data/shop_report.json").read_text(encoding="utf8"))
        self.assertEqual(snapshot, {key: self.data[key] for key in snapshot})
        self.assertTrue(snapshot["source"]["synthetic"])

    def test_people_are_explicit_fiction_with_non_dialable_contacts(self):
        for employee in self.data["employees"]:
            self.assertRegex(employee["name"], r"^测试员工\d{2}$")
            self.assertRegex(employee["contact"], r"^TEST-CONTACT-\d{3}$")
            self.assertNotIn("id_card", employee)
            self.assertNotIn("bank_card", employee)
        encoded = json.dumps(self.data, ensure_ascii=False)
        self.assertIsNone(re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", encoded))

    def test_inventory_and_support_records_are_internally_valid(self):
        self.assertEqual(len({row["sku"] for row in self.data["inventory"]}), len(self.data["inventory"]))
        for row in self.data["inventory"]:
            self.assertGreaterEqual(row["stock"], 0)
            self.assertGreater(row["safety"], 0)
        for row in self.data["support"]:
            self.assertGreaterEqual(row["questions"], row["solved"])
            self.assertGreaterEqual(row["satisfaction"], 0)
            self.assertLessEqual(row["satisfaction"], 100)


if __name__ == "__main__":
    unittest.main()
