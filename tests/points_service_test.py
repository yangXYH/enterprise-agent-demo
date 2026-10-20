"""Employee points use roster IDs, preserve ledger history, and rank deterministically."""

import datetime as dt
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text
from fastapi import FastAPI
from fastapi.testclient import TestClient

import points_routes
from utils import points_service as points


class PointsServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE hr_employee (
                    id INTEGER PRIMARY KEY, emp_no TEXT, name TEXT, company TEXT,
                    dept_name TEXT, position TEXT, status TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO hr_employee VALUES
                  (1, 'A01', '甲', '示例科技', '运营部', '专员', 'active'),
                  (2, 'A02', '乙', '示例科技', '运营部', '专员', 'active'),
                  (3, 'B01', '丙', '示例传媒', '客服部', '专员', 'active'),
                  (4, 'A04', '丁', '示例科技', '运营部', '专员', 'resigned')
            """))
        self.patch = patch.object(points.hr_service, "ensure_tables")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.engine.dispose)

    def test_roster_drives_zero_point_leaderboard(self):
        result = points.leaderboard(month="2026-09", engine=self.engine)
        self.assertEqual([row["name"] for row in result["items"]], ["甲", "乙", "丙"])
        self.assertEqual([row["rank"] for row in result["items"]], [1, 1, 1])
        self.assertEqual(result["scored_count"], 0)
        self.assertEqual(result["total_points"], 0)

    def test_ledger_month_and_rule_snapshot(self):
        rule = points.save_rule({"name": "协作", "points": 10}, self.engine)
        points.add_record(1, rule["id"], "帮助跨部门项目", "HR", self.engine)
        points.add_record(2, rule["id"], "帮助跨部门项目", "HR", self.engine)
        negative = points.save_rule({"name": "纠正", "points": -3}, self.engine)
        points.add_record(2, negative["id"], "纠正上次多计", "HR", self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE points_record SET created_at = :date WHERE employee_id = 1"),
                         {"date": dt.datetime(2026, 8, 31, 23, 59, 59)})
        points.save_rule({"id": rule["id"], "name": "协作新版", "points": 20}, self.engine)
        rank = points.leaderboard(month="2026-09", sort="month", engine=self.engine)
        self.assertEqual([(r["name"], r["total_points"], r["month_points"]) for r in rank["items"]],
                         [("乙", 7, 7), ("甲", 10, 0), ("丙", 0, 0)])
        self.assertEqual([r["rank"] for r in rank["items"]], [1, 2, 2])
        august = points.list_records(month="2026-08", engine=self.engine)
        self.assertEqual(august["total"], 1)
        self.assertEqual(august["items"][0]["rule_name"], "协作")
        self.assertEqual(august["items"][0]["points"], 10)

    def test_reject_inactive_employee_rule_and_unexplained_record(self):
        with self.assertRaisesRegex(ValueError, "整数"):
            points.save_rule({"name": "小数", "points": 1.5}, self.engine)
        rule = points.save_rule({"name": "协作", "points": 5}, self.engine)
        with self.assertRaisesRegex(ValueError, "在职员工"):
            points.add_record(4, rule["id"], "事项", "HR", self.engine)
        with self.assertRaisesRegex(ValueError, "事项说明"):
            points.add_record(1, rule["id"], "", "HR", self.engine)
        points.save_rule({"id": rule["id"], "name": "协作", "points": 5, "is_active": False}, self.engine)
        with self.assertRaisesRegex(ValueError, "有效的积分规则"):
            points.add_record(1, rule["id"], "事项", "HR", self.engine)

    def test_general_manager_is_excluded_but_deputy_remains(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO hr_employee VALUES
                  (5, 'A05', '总经理', '示例科技', '总经理', '总经理', 'active'),
                  (6, 'A06', '副总经理', '示例科技', '总经办', '副总经理', 'active')
            """))
        rule = points.save_rule({"name": "协作", "points": 5}, self.engine)
        with self.assertRaisesRegex(ValueError, "总经理不参与"):
            points.add_record(5, rule["id"], "事项", "HR", self.engine)
        points.add_record(6, rule["id"], "事项", "HR", self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO points_record
                  (employee_id, employee_name, rule_id, rule_name, points, note, operator, created_at)
                VALUES (5, '总经理', :rule_id, '协作', 5, '历史事项', 'HR', :created_at)
            """), {"rule_id": rule["id"], "created_at": dt.datetime(2026, 9, 1)})
        rank = points.leaderboard(month="2026-09", engine=self.engine)
        self.assertEqual(rank["total"], 4)
        self.assertNotIn("总经理", [row["name"] for row in rank["items"]])
        self.assertIn("副总经理", [row["name"] for row in rank["items"]])
        self.assertNotIn("总经理", rank["departments"])
        self.assertEqual(points.list_records(employee_id=5, engine=self.engine)["total"], 0)
        self.assertEqual(points.list_records(engine=self.engine)["total"], 1)


class PointsPermissionTest(unittest.TestCase):
    def test_employee_cannot_write_points(self):
        app = FastAPI()
        app.include_router(points_routes.router)
        with patch.object(points_routes, "_user", return_value={"role": "employee"}):
            client = TestClient(app)
            self.assertEqual(client.post("/api/points/rules", json={"name": "测试", "points": 5}).status_code, 403)
            self.assertEqual(client.post("/api/points/records", json={"employee_id": 1, "rule_id": 1, "note": "测试"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
