"""Full application demo contracts, requiring neither MySQL nor external APIs."""
import hashlib
import json
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import full_demo_seed as bootstrap
from full_demo_fixtures import synthetic_identity
from package_full_frontend import digest
from utils import hr_service


class FullApplicationDemoTest(unittest.TestCase):
    def test_bundle_matches_original_vue_source(self):
        manifest = json.loads((ROOT / "demo/frontend-manifest.json").read_text(encoding="utf8"))
        self.assertGreater(len(manifest["source"]), 40)
        for group in ("source", "bundle"):
            for name, expected in manifest[group].items():
                with self.subTest(path=name):
                    self.assertEqual(digest(ROOT / name), expected)

    def test_real_company_database_names_are_refused(self):
        for name in ("enterprise_agent_db", "mysql", "enterprise_agent_demo`; DROP DATABASE mysql;--"):
            with self.subTest(name=name), patch.dict(os.environ, {"DEMO_DB_NAME": name}):
                with self.assertRaises(RuntimeError):
                    bootstrap.configure()

    def test_only_dedicated_demo_database_is_used(self):
        with patch.dict(os.environ, {"DEMO_DB_NAME": "enterprise_agent_demo_acceptance", "DB_URL": "sqlite:///business.db"}):
            url = bootstrap.configure()
            self.assertEqual(url.database, "enterprise_agent_demo_acceptance")
            self.assertEqual(os.environ["DB_NAME"], url.database)
            self.assertEqual(os.environ["JUSHUITAN_SYNC_ENABLED"], "false")
            self.assertNotIn("business.db", os.environ["DB_URL"])

    def test_id_fixture_uses_impossible_region(self):
        for i in range(1, 81):
            identity = synthetic_identity(date(1996, 3, 10), i)
            self.assertEqual(len(identity), 18)
            self.assertTrue(identity.startswith("000000"))

    def test_shop_snapshot_preserves_full_accounting_schema(self):
        snapshot = json.loads((ROOT / "data/shop_report.json").read_text(encoding="utf8"))
        self.assertTrue(snapshot["source"]["synthetic"])
        self.assertEqual(len(snapshot["shops"]), 9)
        self.assertEqual(len(snapshot["fee_keys"]), 28)
        seen = set()
        for row in snapshot["rows"]:
            key = (row["month"], row["channel"], row["shop_id"])
            self.assertNotIn(key, seen)
            seen.add(key)
            self.assertAlmostEqual(sum(row[k] for k in snapshot["fee_keys"]), row["total_fees"], places=2)
            self.assertAlmostEqual(row["revenue"] - row["costG"] - row["total_fees"], row["net_profit"], places=2)

    def test_hr_schema_migrates_once_per_engine_under_parallel_reads(self):
        engine = Mock()
        engine.dialect.name = "mysql"
        with patch.object(hr_service.metadata, "create_all") as create, patch.object(hr_service, "_migrate_attendance_tables") as migrate:
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda _: hr_service.ensure_tables(engine), range(32)))
            self.assertEqual(create.call_count, 1)
            self.assertEqual(migrate.call_count, 1)
            other = Mock()
            other.dialect.name = "mysql"
            hr_service.ensure_tables(other)
            self.assertEqual(migrate.call_count, 2)

    def test_failed_hr_migration_can_be_retried(self):
        engine = Mock()
        engine.dialect.name = "mysql"
        with patch.object(hr_service.metadata, "create_all"), patch.object(hr_service, "_migrate_attendance_tables", side_effect=[RuntimeError("retry"), None]) as migrate:
            with self.assertRaises(RuntimeError):
                hr_service.ensure_tables(engine)
            hr_service.ensure_tables(engine)
            self.assertEqual(migrate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
