import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import admin_user_routes
from utils.account_password import hash_password, verify_password


class AccountManagementTest(unittest.TestCase):
    def test_new_password_is_hashed_and_legacy_password_can_be_verified(self):
        stored = hash_password("CorrectHorse123")
        self.assertLessEqual(len(stored), 100)  # existing sys_user.password column
        self.assertTrue(verify_password("CorrectHorse123", stored))
        self.assertFalse(verify_password("incorrect", stored))
        self.assertTrue(verify_password("old-password", "old-password"))

    def test_non_admin_cannot_manage_accounts(self):
        with patch("main._get_authenticated_user", return_value={"id": 1, "role": "designer"}):
            with self.assertRaises(HTTPException) as context:
                admin_user_routes._admin(None)
        self.assertEqual(context.exception.status_code, 403)

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            admin_user_routes._validate_role("superuser")
        self.assertEqual(context.exception.status_code, 400)

    def test_create_list_and_reset_password_do_not_expose_secret(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE sys_user (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(50) UNIQUE, "
                "password VARCHAR(100), real_name VARCHAR(50), department VARCHAR(100), "
                "job_title VARCHAR(100), role VARCHAR(50), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
        actor = {"id": 999, "username": "root", "role": "admin"}
        with patch("main._get_authenticated_user", return_value=actor), \
             patch.object(admin_user_routes, "get_engine", return_value=engine):
            result = admin_user_routes.create_user(admin_user_routes.NewUser(
                username="designer.1", password="InitialPass123", real_name="设计一",
                department="设计部", job_title="设计师", role="designer",
            ), None)
            self.assertTrue(result["ok"])
            listed = admin_user_routes.list_users(None)["users"]
            self.assertEqual(len(listed), 1)
            self.assertNotIn("password", listed[0])
            admin_user_routes.reset_password(listed[0]["id"],
                admin_user_routes.ResetPassword(password="NewSecurePass456"), None)
        with engine.connect() as conn:
            stored = conn.execute(text("SELECT password FROM sys_user WHERE username='designer.1'")).scalar()
        self.assertEqual(stored, "NewSecurePass456")
        engine.dispose()

    def test_create_account_accepts_any_initial_password(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE sys_user (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(50) UNIQUE, "
                "password VARCHAR(100), real_name VARCHAR(50), department VARCHAR(100), "
                "job_title VARCHAR(100), role VARCHAR(50), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ))
        actor = {"id": 999, "username": "root", "role": "admin"}
        with patch("main._get_authenticated_user", return_value=actor), \
             patch.object(admin_user_routes, "get_engine", return_value=engine):
            result = admin_user_routes.create_user(admin_user_routes.NewUser(
                username="杨桑", password="!", real_name="短密码",
                department="测试部", job_title="测试", role="user",
            ), None)
            self.assertTrue(result["ok"])
        with engine.connect() as conn:
            stored = conn.execute(text("SELECT password FROM sys_user WHERE username='杨桑'")).scalar()
        self.assertEqual(stored, "!")
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
