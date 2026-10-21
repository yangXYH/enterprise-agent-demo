"""Public demo guest access must never extend to a business database."""
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

import main


def request(cookie=""):
    return Request({"type": "http", "method": "GET", "path": "/api/auth/session",
                    "headers": [(b"cookie", cookie.encode("ascii"))] if cookie else []})


def database(*, name="enterprise_agent_demo", owner="enterprise-agent-demo-synthetic-v2", user=True):
    engine = MagicMock()
    engine.url = make_url(f"mysql+pymysql://demo@localhost/{name}")
    connection = engine.connect.return_value.__enter__.return_value
    marker, result = MagicMock(), MagicMock()
    marker.scalar.return_value = owner
    result.mappings.return_value.fetchone.return_value = {
        "id": 1, "username": "demo_admin", "real_name": "测试管理员", "role": "admin",
        "department": "产品技术部", "job_title": "系统管理员",
    } if user else None
    connection.execute.side_effect = [marker, result]
    return engine


class DemoGuestAccessTest(unittest.TestCase):
    def test_fresh_and_stale_browser_sessions_enter_the_owned_demo(self):
        for cookie in ("", "enterprise_session=expired-or-invalid"):
            with self.subTest(cookie=cookie), patch.dict(os.environ, {"APP_ENV": "demo"}):
                user = main._get_authenticated_user(request(cookie), engine=database())
            self.assertEqual(user["username"], "demo_admin")
            self.assertEqual(user["role"], "admin")
            self.assertNotIn("password", user)

    def test_production_and_test_profiles_still_require_login(self):
        for profile in ("production", "test", "development"):
            engine = database()
            with self.subTest(profile=profile), patch.dict(os.environ, {"APP_ENV": profile}):
                with self.assertRaises(HTTPException) as error:
                    main._get_authenticated_user(request(), engine=engine)
                self.assertEqual(error.exception.status_code, 401)
            engine.connect.assert_not_called()

    def test_demo_profile_cannot_open_another_database(self):
        engine = database(name="enterprise_agent_db")
        with patch.dict(os.environ, {"APP_ENV": "demo", "DB_NAME": "enterprise_agent_demo"}):
            with self.assertRaises(HTTPException) as error:
                main._get_authenticated_user(request(), engine=engine)
        self.assertEqual(error.exception.status_code, 401)
        engine.connect.assert_not_called()

    def test_wrong_missing_marker_or_missing_administrator_fails_closed(self):
        for owner, user in (("not-owned", True), ("", True), ("enterprise-agent-demo-synthetic-v2", False)):
            with self.subTest(owner=owner, user=user), patch.dict(os.environ, {"APP_ENV": "demo"}):
                with self.assertRaises(HTTPException):
                    main._get_authenticated_user(request(), engine=database(owner=owner, user=user))
        engine = database()
        engine.connect.return_value.__enter__.return_value.execute.side_effect = SQLAlchemyError("missing marker")
        with patch.dict(os.environ, {"APP_ENV": "demo"}):
            self.assertIsNone(main._get_demo_guest_user(engine))

    def test_session_supplies_full_identity_without_credentials(self):
        with patch.dict(os.environ, {"APP_ENV": "demo"}), patch.object(main, "_get_mysql_engine", return_value=database()):
            session = main.get_auth_session(request())
        self.assertTrue(session["authenticated"])
        self.assertTrue(session["demo_mode"])
        self.assertEqual(session["username"], "demo_admin")
        self.assertEqual(session["department"], "产品技术部")
        self.assertNotIn("password", session)


if __name__ == "__main__":
    unittest.main()
