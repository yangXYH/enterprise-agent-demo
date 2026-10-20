"""Financial and disclosure checks for the DEMO_BAGS shop snapshot."""

import sqlite3
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from tools import export_shop_report as report


class ShopReportExportTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.db = self.root / "demo_bags.db"
        formula = ",".join(repr(field) for field in report.FEE_KEYS)
        (self.root / "index.html").write_text(
            f"function calcNet(chData) {{ const feeKeys = [{formula}]; }}",
            encoding="utf-8",
        )
        numeric = ("revenue", "costG", "rentAlloc", *report.FEE_KEYS,
                   *report.BREAKDOWN_KEYS, *report.EXTRA_SOURCE_KEYS)
        self.columns = ("month", "channel", "shop_id", *numeric,
                        "data_status", "data_note")
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("CREATE TABLE shop_registry "
                         "(channel TEXT, shop_id TEXT, shop_name TEXT, sort_order INTEGER)")
            conn.execute("INSERT INTO shop_registry VALUES ('self','demo_bags','测试箱包',1)")
            fields = ["month INTEGER", "channel TEXT", "shop_id TEXT"]
            fields += [f'"{key}" REAL' for key in numeric]
            fields += ["data_status TEXT", "data_note TEXT"]
            conn.execute("CREATE TABLE shop_data (" + ",".join(fields) + ")")
            self._insert(conn, month=1, revenue=100, costG=20, promo=10,
                         labor=50, rentAlloc=5, data_status="complete")
            self._insert(conn, month=2, platform=12, data_status="partial",
                         data_note="仅有费用")
            self._insert(conn, month=3, revenue=100, costG=0,
                         data_status="partial", data_note="成本待补")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.folder.cleanup()

    def _insert(self, conn, **values):
        row = {column: 0 for column in self.columns}
        row.update(channel="self", shop_id="demo_bags", data_status="empty", data_note="")
        row.update(values)
        marks = ",".join("?" for _ in self.columns)
        quoted = ",".join(f'"{column}"' for column in self.columns)
        conn.execute(f"INSERT INTO shop_data ({quoted}) VALUES ({marks})",
                     [row[column] for column in self.columns])

    def test_formula_hides_protected_labor_and_does_not_invent_expense_only_loss(self):
        snapshot = report.build_snapshot(self.db, 2026)
        first, second, third = snapshot["rows"]
        self.assertFalse(snapshot["source"]["labor_included"])
        self.assertEqual(first["labor"], 0)
        self.assertEqual(first["total_fees"], 10)
        self.assertEqual(first["gross_profit"], 80)
        self.assertEqual(first["net_profit"], 65)
        self.assertTrue(second["expense_only"])
        self.assertEqual(second["total_fees"], 12)
        self.assertIsNone(second["net_profit"])
        self.assertTrue(third["missing_cost"])
        self.assertTrue(third["profit_provisional"])
        self.assertIsNone(third["gross_profit"])
        self.assertIsNone(third["net_profit"])

    def test_partial_nonzero_cost_does_not_publish_incomplete_profit(self):
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE shop_cost_detail (month INTEGER,channel TEXT,shop_id TEXT,net_qty REAL,unit_cost REAL,cost REAL)")
        conn.execute("INSERT INTO shop_cost_detail VALUES (1,'self','demo_bags',2,NULL,NULL)")
        conn.commit()
        conn.close()
        first = report.build_snapshot(self.db, 2026)["rows"][0]
        self.assertEqual(first["costG"], 20)
        self.assertTrue(first["missing_cost"])
        self.assertEqual(first["missing_cost_count"], 1)
        self.assertIsNone(first["gross_profit"])
        self.assertIsNone(first["net_profit"])

    def test_ai_summary_respects_missing_cost_and_conflicting_income(self):
        from utils.shop_report_query_service import summarize
        for flag in ("missing_cost", "source_conflict"):
            total = summarize([{"revenue": 100, "costG": 20, "promo": 5, flag: True, "missing_fees": True}], ["promo"])
            self.assertEqual(total["revenue"], 100)
            self.assertIsNone(total["gross_profit"])
            self.assertIsNone(total["net_profit"])

    def test_average_cost_allows_profit_but_remains_estimated_even_with_complete_fees(self):
        with closing(sqlite3.connect(self.db)) as conn,conn:
            conn.execute("CREATE TABLE shop_cost_detail(month INTEGER,channel TEXT,shop_id TEXT,net_qty REAL,unit_cost REAL,cost REAL,cost_status TEXT)")
            conn.execute("INSERT INTO shop_cost_detail VALUES(1,'self','demo_bags',1,20,20,'estimated')")
        first=report.build_snapshot(self.db,2026)['rows'][0]
        self.assertFalse(first['missing_cost']);self.assertTrue(first['cost_estimated'])
        self.assertEqual(first['estimated_cost_count'],1);self.assertEqual(first['estimated_cost_amount'],20)
        self.assertEqual(first['net_profit'],65);self.assertTrue(first['profit_provisional'])
        self.assertIn('均价暂估',first['data_note'])
        from utils.shop_report_query_service import summarize
        summary=summarize([first],list(report.FEE_KEYS))
        self.assertTrue(summary['cost_estimated']);self.assertTrue(summary['provisional'])
        self.assertEqual(summary['net_profit'],65)

    def test_average_cost_does_not_override_income_source_conflict(self):
        with closing(sqlite3.connect(self.db)) as conn,conn:
            conn.execute("CREATE TABLE shop_cost_detail(month INTEGER,channel TEXT,shop_id TEXT,net_qty REAL,unit_cost REAL,cost REAL,cost_status TEXT)")
            conn.execute("INSERT INTO shop_cost_detail VALUES(1,'self','demo_bags',1,20,20,'estimated')")
            conn.execute("CREATE TABLE shop_report_audit_flags(year INTEGER,month INTEGER,channel TEXT,shop_id TEXT,missing_fees INTEGER,source_conflict INTEGER,note TEXT)")
            conn.execute("INSERT INTO shop_report_audit_flags VALUES(2026,1,'self','demo_bags',0,1,'收入来源冲突')")
        first=report.build_snapshot(self.db,2026)['rows'][0]
        self.assertTrue(first['cost_estimated']);self.assertIsNone(first['net_profit'])
        self.assertIn('毛利及净利暂不计算',first['data_note'])

    def test_pending_fees_publish_provisional_profit_and_recalculate_when_added(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("CREATE TABLE shop_report_audit_flags(year INTEGER,month INTEGER,channel TEXT,shop_id TEXT,missing_fees INTEGER,source_conflict INTEGER,note TEXT)")
            conn.execute("INSERT INTO shop_report_audit_flags VALUES(2026,1,'self','demo_bags',1,0,'费用来源未齐，项目净利待补全')")
        first = report.build_snapshot(self.db, 2026)["rows"][0]
        self.assertEqual(first["product_profit"], 70)
        self.assertEqual(first["net_profit"], 65)
        self.assertEqual(first["known_total_fees"], 10)
        self.assertIsNone(first["total_fees"])
        self.assertTrue(first["missing_fees"])
        self.assertTrue(first["profit_provisional"])
        self.assertIn("费用补齐后重算", first["data_note"])
        self.assertNotIn("项目净利待补全", first["data_note"])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE shop_data SET promo=15 WHERE month=1")
        updated = report.build_snapshot(self.db, 2026)["rows"][0]
        self.assertEqual(updated["net_profit"], 60)
        from utils.shop_report_query_service import summarize
        summary = summarize([updated], list(report.FEE_KEYS))
        self.assertEqual(summary["net_profit"], updated["net_profit"])
        self.assertEqual(summary["net_rate"], 60)
        self.assertTrue(summary["provisional"])
        self.assertTrue(summary["fees_partial"])
        self.assertIsNone(summary["total_fees"])

    def test_changed_source_formula_stops_export(self):
        (self.root / "index.html").write_text(
            "function calcNet(chData) { const feeKeys = ['promo']; }",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "feeKeys 已变更"):
            report.build_snapshot(self.db, 2026)

    def test_accounting_override_excludes_prior_years_and_replaces_old_estimates(self):
        snapshot = report.build_snapshot(self.db, 2026)
        snapshot["shops"].append(dict(report.STORE_SHOP, months=["2026-01", "2026-09"]))
        current = dict(month="2026-01", channel="store", shop_id="demo_store", revenue=999,
                       costG=300, platform=99, rentAlloc=500, has_data=True)
        september = dict(month="2026-09", channel="store", shop_id="demo_store", revenue=12, has_data=True)
        snapshot["rows"].extend([current, september])
        def accounting(month):
            return dict(month=month, channel="store", shop_id="demo_store", source_kind="project_profit",
                        revenue=100, costG=20, gross_adjustment=12, rentAlloc=0,
                        missing_fees=False, missing_cost=False, profit_provisional=False,
                        known_fee_keys=["platform"], **{k: 0 for k in report.FEE_KEYS})
        historical = accounting("2025-01")
        new = accounting("2026-01")
        new.update(platform=7, labor=77)
        path = self.root / "overrides.json"
        path.write_text(json.dumps({"rows": [historical, new]}), encoding="utf-8")
        merged = report._merge_store_overrides(snapshot, path)
        stores = {r["month"]: r for r in merged["rows"] if r["channel"] == "store"}
        self.assertEqual(set(stores), {"2026-01", "2026-09"})
        self.assertEqual(stores["2026-09"], september)
        self.assertEqual(stores["2026-01"]["rentAlloc"], 0)
        self.assertEqual(stores["2026-01"]["platform"], 7)
        self.assertEqual(stores["2026-01"]["labor"], 0)
        self.assertEqual(stores["2026-01"]["gross_profit"], 92)
        self.assertEqual(stores["2026-01"]["net_profit"], 85)
        self.assertNotIn("2025-01", merged["months"])
        from utils.shop_report_query_service import summarize
        summary = summarize([stores["2026-01"]], list(report.FEE_KEYS))
        self.assertEqual(summary["gross_profit"], 92)
        self.assertEqual(summary["net_profit"], 85)


    def test_offline_store_rows_publish_provisional_profit_from_known_fees(self):
        numeric = ("revenue", "costG", "rentAlloc", *report.FEE_KEYS,
                   *report.BREAKDOWN_KEYS, *report.EXTRA_SOURCE_KEYS)
        conn = sqlite3.connect(self.db)
        try:
            fields = ["month INTEGER", "channel TEXT"]
            fields += [f'"{key}" REAL' for key in numeric]
            conn.execute("CREATE TABLE channel_data (" + ",".join(fields) + ")")
            rows = []
            for month, revenue, cost, rent, express in (
                (1, 100.0, 20.0, 10.0, 5.0),
                (2, 0.0, 0.0, 0.0, 12.0),
            ):
                row = {key: 0.0 for key in numeric}
                row.update(month=month, channel="store", revenue=revenue, costG=cost,
                           rentAlloc=rent, expressHd=express, labor=77.0)
                rows.append([row.get("month", 0), row.get("channel", "store"),
                             *[row[key] for key in numeric]])
            names = ["month", "channel", *numeric]
            quoted = ",".join(f'"{name}"' for name in names)
            marks = ",".join("?" for _ in names)
            conn.executemany(f"INSERT INTO channel_data ({quoted}) VALUES ({marks})", rows)
            conn.commit()
        finally:
            conn.close()

        snapshot = report.build_snapshot(self.db, 2026)
        january = next(row for row in snapshot["rows"] if row["channel"] == "store" and row["month"] == "2026-01")
        february = next(row for row in snapshot["rows"] if row["channel"] == "store" and row["month"] == "2026-02")
        self.assertEqual(january["labor"], 0)
        self.assertEqual(january["net_profit"], 65)
        self.assertTrue(february["expense_only"])

        override = {
            "source": {"files": ["store.xls"]},
            "rows": [{
                "month": "2026-02", "channel": "store", "shop_id": "demo_store",
                "revenue": 1000.0, "costG": 300.0, "rentAlloc": None,
                "gross_profit": 700.0, "total_fees": None,
                "product_profit": None, "net_profit": None,
                "data_status": "partial", "data_note": "费用待补",
                "missing_cost": False, "missing_fees": True,
                "known_fee_keys": [], "profit_provisional": True,
                "expense_only": False, "has_data": True,
                **{key: 0.0 for key in report.FEE_KEYS},
            }],
        }
        override_path = self.root / "overrides.json"
        override_path.write_text(json.dumps(override), encoding="utf-8")
        merged = report._merge_store_overrides(snapshot, override_path)
        imported = next(row for row in merged["rows"] if row["channel"] == "store" and row["month"] == "2026-02")
        self.assertEqual(imported["revenue"], 1000.0)
        self.assertEqual(imported["expressHd"], 12.0)
        self.assertEqual(imported["known_fee_keys"], ["expressHd"])
        self.assertIsNone(imported["total_fees"])
        self.assertEqual(imported["product_profit"], 688)
        self.assertEqual(imported["net_profit"], 688)
        self.assertTrue(imported["profit_provisional"])

        # An actual POS fee must win over an earlier source estimate.
        snapshot = report.build_snapshot(self.db, 2026)
        february = next(row for row in snapshot["rows"] if row["channel"] == "store" and row["month"] == "2026-02")
        february["platform"] = 99.0
        override["rows"][0].update(platform=7.5, authoritative_fee_keys=["platform"])
        override_path.write_text(json.dumps(override), encoding="utf-8")
        latest = report._merge_store_overrides(snapshot, override_path)
        imported = next(row for row in latest["rows"] if row["channel"] == "store" and row["month"] == "2026-02")
        self.assertEqual(imported["platform"], 7.5)
        self.assertEqual(imported["net_profit"], 680.5)


if __name__ == "__main__":
    unittest.main()
