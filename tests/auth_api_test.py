import base64
import json
import unittest
from http.cookies import SimpleCookie
from typing import Any
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import Response
from starlette.requests import Request

import main


USERNAME = "alice"
REAL_NAME = "Alice Example"


class _FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> "_FakeResult":
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _FakeConnection:
    def __init__(self, engine: "_FakeEngine") -> None:
        self.engine = engine

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return False

    def execute(self, statement: Any, parameters: dict[str, Any]) -> _FakeResult:
        self.engine.executions.append((str(statement), dict(parameters)))
        return _FakeResult(self.engine.user)


class _FakeEngine:
    def __init__(self, user: dict[str, Any] | None = None) -> None:
        self.user = user
        self.executions: list[tuple[str, dict[str, Any]]] = []

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self)

    def begin(self) -> _FakeConnection:
        return _FakeConnection(self)


def _request(cookie_value: str | None = None, *, path: str = "/api/auth/session") -> Request:
    headers = []
    if cookie_value is not None:
        cookie = f"{main.AUTH_SESSION_COOKIE}={cookie_value}"
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": ("203.0.113.8", 443),
            "server": ("testserver", 443),
        }
    )


def _unsigned_payload(token: str) -> dict[str, Any]:
    payload_token = token.rsplit(".", 1)[0]
    padding = "=" * (-len(payload_token) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_token + padding))


def _cookie_value(response: Response) -> str:
    parsed = SimpleCookie()
    parsed.load(response.headers["set-cookie"])
    return parsed[main.AUTH_SESSION_COOKIE].value


class AuthApiTest(unittest.TestCase):
    @staticmethod
    def _user(*, password: str = "correct-password") -> dict[str, Any]:
        return {
            "id": 42,
            "username": USERNAME,
            "password": password,
            "real_name": REAL_NAME,
            "role": "operator",
            "department": "finance",
            "job_title": "analyst",
        }

    def test_signed_cookie_carries_username_and_seven_day_expiry(self) -> None:
        issued_at = 1_768_435_200
        with patch.object(main.time, "time", return_value=issued_at):
            token = main._encode_auth_session(USERNAME)
            decoded = main._decode_auth_session(token)

        payload = _unsigned_payload(token)
        self.assertEqual(
            payload,
            {
                "username": USERNAME,
                "expires_at": issued_at + main.AUTH_SESSION_MAX_AGE_SECONDS,
            },
        )
        self.assertNotIn("session_id", payload)
        self.assertEqual(main.AUTH_SESSION_MAX_AGE_SECONDS, 7 * 24 * 60 * 60)
        self.assertEqual(decoded, payload)

    def test_signed_cookie_rejects_tampering_and_expiry(self) -> None:
        issued_at = 1_768_435_200
        with patch.object(main.time, "time", return_value=issued_at):
            token = main._encode_auth_session(USERNAME)

        payload_token, signature = token.rsplit(".", 1)
        self.assertIsNone(main._decode_auth_session(f"{payload_token}x.{signature}"))

        with patch.object(
            main.time,
            "time",
            return_value=issued_at + main.AUTH_SESSION_MAX_AGE_SECONDS + 1,
        ):
            self.assertIsNone(main._decode_auth_session(token))

    def test_login_records_username_and_sets_cookie(self) -> None:
        engine = _FakeEngine(self._user())
        body = main.LoginRequest(username=USERNAME, password="correct-password")

        with patch.object(main, "_get_mysql_engine", return_value=engine):
            response = main.login(body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.body)["success"])
        self.assertEqual(len(engine.executions), 2)
        self.assertIn("SYS_USER", engine.executions[0][0].upper())
        insert_sql, insert_parameters = engine.executions[1]
        self.assertIn("INSERT INTO SYS_USER_LOGIN_RECORD", insert_sql.upper())
        self.assertEqual(insert_parameters, {"username": USERNAME})

        payload = _unsigned_payload(_cookie_value(response))
        self.assertEqual(payload["username"], USERNAME)
        self.assertNotIn("session_id", payload)
        set_cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", set_cookie)
        self.assertIn("samesite=lax", set_cookie)
        self.assertIn(f"max-age={main.AUTH_SESSION_MAX_AGE_SECONDS}", set_cookie)

    def test_login_accepts_unrestricted_username_and_password(self) -> None:
        username = "杨桑"
        password = "!"
        engine = _FakeEngine(self._user(password=password) | {"username": username})
        body = main.LoginRequest(username=username, password=password)

        with patch.object(main, "_get_mysql_engine", return_value=engine):
            response = main.login(body)

        self.assertTrue(json.loads(response.body)["success"])

    def test_each_successful_login_adds_a_new_record(self) -> None:
        engine = _FakeEngine(self._user())
        body = main.LoginRequest(username=USERNAME, password="correct-password")

        with patch.object(main, "_get_mysql_engine", return_value=engine):
            main.login(body)
            main.login(body)

        inserts = [
            execution
            for execution in engine.executions
            if "INSERT INTO SYS_USER_LOGIN_RECORD" in execution[0].upper()
        ]
        self.assertEqual(len(inserts), 2)
        self.assertEqual(
            [parameters for _, parameters in inserts],
            [{"username": USERNAME}, {"username": USERNAME}],
        )

    def test_login_failure_does_not_write_login_record(self) -> None:
        for user, password in ((None, "unknown-password"), (self._user(), "wrong-password")):
            with self.subTest(user_exists=user is not None):
                engine = _FakeEngine(user)
                body = main.LoginRequest(username=USERNAME, password=password)
                with patch.object(main, "_get_mysql_engine", return_value=engine):
                    response = main.login(body)

                self.assertFalse(json.loads(response.body)["success"])
                self.assertEqual(len(engine.executions), 1)
                self.assertFalse(
                    any(
                        "SYS_USER_LOGIN_RECORD" in sql.upper()
                        for sql, _ in engine.executions
                    )
                )
                self.assertNotIn("set-cookie", response.headers)

    def test_authenticated_user_uses_signed_cookie_and_sys_user_only(self) -> None:
        engine = _FakeEngine(self._user())
        token = main._encode_auth_session(USERNAME, self._user()["password"])

        user = main._get_authenticated_user(_request(token), engine=engine)

        self.assertEqual(user["username"], USERNAME)
        self.assertEqual(user["real_name"], REAL_NAME)
        self.assertNotIn("session_id", user)
        self.assertEqual(len(engine.executions), 1)
        self.assertIn("SYS_USER", engine.executions[0][0].upper())
        self.assertNotIn("SYS_AUTH_", engine.executions[0][0].upper())

    def test_authenticated_user_rejects_missing_sys_user(self) -> None:
        token = main._encode_auth_session(USERNAME, self._user()["password"])
        with self.assertRaises(HTTPException) as raised:
            main._get_authenticated_user(_request(token), engine=_FakeEngine())

        self.assertEqual(raised.exception.status_code, 401)

    def test_heartbeat_route_is_removed(self) -> None:
        matches = [route for route in main.app.routes if route.path == "/api/auth/heartbeat"]
        self.assertEqual(matches, [])

    def test_logout_clears_cookie(self) -> None:
        response = Response()

        result = main.logout(response)

        self.assertTrue(result["success"])
        set_cookie = response.headers["set-cookie"].lower()
        self.assertIn(f"{main.AUTH_SESSION_COOKIE}=", set_cookie)
        self.assertIn("max-age=0", set_cookie)


if __name__ == "__main__":
    unittest.main()
