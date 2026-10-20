"""人力行政模块 API 测试（后端 8 域 + 脱敏 + 权限）。

运行（项目根目录，venv）：
    venv\\Scripts\\python -m unittest tests.hr_module_api_test -v

依赖：独立 MySQL 演示库已运行且测试花名册已灌入
（tools/full_demo_seed.py）。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from utils.import_service import get_engine


def _make_session_cookie(username: str) -> str:
    engine = get_engine()
    with engine.connect() as conn:
        user_exists = conn.execute(
            text("SELECT 1 FROM sys_user WHERE username = :u LIMIT 1"),
            {"u": username},
        ).scalar_one_or_none()
    if user_exists is None:
        raise RuntimeError(f"用户不存在: {username}")
    return main._encode_auth_session(username)


class HrModuleApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(main.app)
        cls.hr_cookie = _make_session_cookie("demo_hr")       # role=hr
        cls.designer_cookie = _make_session_cookie("demo_designer")  # role=designer
        cls.boss_cookie = _make_session_cookie("demo_boss")        # role=boss

    # ── 认证 ──────────────────────────────────────────────────────────────
    def test_roster_requires_auth(self) -> None:
        resp = self.client.get("/api/hr/roster/list")
        self.assertEqual(resp.status_code, 401)

    # ── 脱敏 ──────────────────────────────────────────────────────────────
    def _first_with_id_card(self, cookie: str) -> dict:
        resp = self.client.get(
            "/api/hr/roster/list?page_size=100",
            cookies={"enterprise_session": cookie},
        )
        self.assertEqual(resp.status_code, 200)
        for item in resp.json()["items"]:
            if item.get("id_card"):
                return item
        raise AssertionError("未找到有身份证数据的员工")

    def test_roster_list_masked_for_designer(self) -> None:
        first = self._first_with_id_card(self.designer_cookie)
        self.assertIn("****", first["id_card"])

    def test_roster_list_full_for_boss_is_masked(self) -> None:
        """按确认的严格策略：boss（总经理）也一律脱敏。"""
        first = self._first_with_id_card(self.boss_cookie)
        self.assertIn("****", first["id_card"])

    def test_roster_list_full_for_hr(self) -> None:
        first = self._first_with_id_card(self.hr_cookie)
        card = first["id_card"]
        self.assertNotIn("****", card)
        self.assertTrue(card.isdigit() or "X" in card.upper())

    # ── 花名册 / 提醒 ─────────────────────────────────────────────────────
    def test_roster_detail(self) -> None:
        resp = self.client.get(
            "/api/hr/roster/list?page_size=1",
            cookies={"enterprise_session": self.hr_cookie},
        )
        emp_id = resp.json()["items"][0]["id"]
        detail = self.client.get(
            f"/api/hr/roster/detail/{emp_id}",
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertIn("contracts", detail.json())

    def test_reminders(self) -> None:
        resp = self.client.get(
            "/api/hr/roster/reminders", cookies={"enterprise_session": self.hr_cookie}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["summary"]["total"], 0)
        self.assertIn("contract_expiry", data["reminders"])

    # ── 驾驶舱 ────────────────────────────────────────────────────────────
    def test_dashboard_overview(self) -> None:
        resp = self.client.get(
            "/api/hr/dashboard/overview", cookies={"enterprise_session": self.hr_cookie}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["active"], 69)

    def test_dashboard_flow(self) -> None:
        resp = self.client.get(
            "/api/hr/dashboard/flow", cookies={"enterprise_session": self.hr_cookie}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_resigns"], 0)
        self.assertGreater(len(data["series"]), 10)

    def test_dashboard_reminders(self) -> None:
        resp = self.client.get(
            "/api/hr/dashboard/reminders", cookies={"enterprise_session": self.hr_cookie}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("upcoming_birthdays", resp.json())

    # ── 招聘 ──────────────────────────────────────────────────────────────
    def test_recruit_crud(self) -> None:
        save = self.client.post(
            "/api/hr/recruit/candidate/save",
            json={"name": "测试候选人", "position": "京东运营", "stage": "resume_pool",
                  "source_channel": "内推", "phone": "13800000000"},
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertEqual(save.status_code, 200)
        cand_id = save.json()["id"]
        listing = self.client.get(
            "/api/hr/recruit/candidates?keyword=测试候选人",
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(any(c["id"] == cand_id for c in listing.json()))
        delete = self.client.post(
            "/api/hr/recruit/candidate/delete", json={"id": cand_id},
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertEqual(delete.status_code, 200)

    def test_requisition_save_and_close(self) -> None:
        save = self.client.post(
            "/api/hr/recruit/requisition/save",
            json={"dept_name": "内容中心", "position": "设计师", "headcount": 2, "priority": "high"},
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertEqual(save.status_code, 200)
        req_id = save.json()["id"]
        self.assertTrue(save.json()["req_no"].startswith("REQ"))
        close = self.client.post(
            "/api/hr/recruit/requisition/close", json={"id": req_id},
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertEqual(close.status_code, 200)
        listing = self.client.get(
            "/api/hr/recruit/requisitions?status=closed",
            cookies={"enterprise_session": self.hr_cookie},
        )
        self.assertTrue(any(r["id"] == req_id for r in listing.json()))

    def test_templates_download(self) -> None:
        resp = self.client.get(
            "/api/hr/attendance/template", cookies={"enterprise_session": self.hr_cookie}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp.headers["content-type"])

    # ── 考勤模板 / 导入日志 ──────────────────────────────────────────────
    def test_import_logs(self) -> None:
        resp = self.client.get(
            "/api/hr/import/logs", cookies={"enterprise_session": self.hr_cookie}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 3)  # roster/resign 幂等重跑后的日志


if __name__ == "__main__":
    unittest.main(verbosity=2)
