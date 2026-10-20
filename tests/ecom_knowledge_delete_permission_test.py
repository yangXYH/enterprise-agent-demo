"""电商中台看板 · 知识管理文件删除权限测试。

需求：仅 sys_user.role 为 boss/admin 的用户可在「电商中台 / 公司首页 / 知识管理」
删除文件（POST /api/ecom-knowledge/delete）。其余角色 403，未登录 401。
"""

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

import main


CLIENT_IP = "203.0.113.8"
USER_AGENT = "ExampleBrowser/1.0"


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/ecom-knowledge/delete",
            "raw_path": "/api/ecom-knowledge/delete".encode("ascii"),
            "query_string": b"",
            "headers": [(b"user-agent", USER_AGENT.encode("ascii"))],
            "client": (CLIENT_IP, 443),
            "server": ("testserver", 443),
        }
    )


class EcomKnowledgeDeletePermissionTest(unittest.TestCase):
    @staticmethod
    def _endpoint():
        matches = [
            route.endpoint
            for route in main.app.routes
            if route.path == "/api/ecom-knowledge/delete"
            and "POST" in (getattr(route, "methods", None) or set())
        ]
        assert len(matches) == 1, "missing POST /api/ecom-knowledge/delete route"
        return matches[0]

    def _payload(self):
        return main.EcomKnowledgeDeleteRequest(
            library="product", path="brand-vi/落地页.xlsx", kind="file"
        )

    def test_operator_role_gets_403_and_service_not_called(self) -> None:
        endpoint = self._endpoint()
        with (
            patch.object(
                main,
                "_get_authenticated_user",
                return_value={"username": "alice", "real_name": "Alice", "role": "operator"},
            ),
            patch.object(main.ecom_knowledge_service, "delete_item") as delete_item,
        ):
            with self.assertRaises(HTTPException) as raised:
                endpoint(self._payload(), _request())

        self.assertEqual(raised.exception.status_code, 403)
        delete_item.assert_not_called()

    def test_role_free_user_gets_403_and_service_not_called(self) -> None:
        endpoint = self._endpoint()
        with (
            patch.object(
                main,
                "_get_authenticated_user",
                return_value={"username": "bob", "real_name": "Bob", "role": ""},
            ),
            patch.object(main.ecom_knowledge_service, "delete_item") as delete_item,
        ):
            with self.assertRaises(HTTPException) as raised:
                endpoint(self._payload(), _request())

        self.assertEqual(raised.exception.status_code, 403)
        delete_item.assert_not_called()

    def test_boss_and_admin_roles_may_delete_file(self) -> None:
        endpoint = self._endpoint()
        for role in ("boss", "admin"):
            with self.subTest(role=role):
                with (
                    patch.object(
                        main,
                        "_get_authenticated_user",
                        return_value={"username": "who", "real_name": "Who", "role": role},
                    ),
                    patch.object(
                        main.ecom_knowledge_service, "delete_item", return_value=True
                    ) as delete_item,
                ):
                    result = endpoint(self._payload(), _request())

                delete_item.assert_called_once_with(
                    library="product", path="brand-vi/落地页.xlsx", kind="file"
                )
                self.assertTrue(result)

    def test_unauthenticated_request_get_401_before_delete(self) -> None:
        endpoint = self._endpoint()
        with (
            patch.object(
                main,
                "_get_authenticated_user",
                side_effect=HTTPException(status_code=401, detail="登录状态已失效，请重新登录"),
            ),
            patch.object(main.ecom_knowledge_service, "delete_item") as delete_item,
        ):
            with self.assertRaises(HTTPException) as raised:
                endpoint(self._payload(), _request())

        self.assertEqual(raised.exception.status_code, 401)
        delete_item.assert_not_called()

    def test_helper_accepts_boss_admin_case_insensitively(self) -> None:
        for role in ("boss", "admin", "BOSS", "Admin", "  Boss  "):
            with self.subTest(role=role):
                with patch.object(
                    main,
                    "_get_authenticated_user",
                    return_value={"username": "u", "real_name": "U", "role": role},
                ):
                    user = main._require_ecom_knowledge_delete_permission(_request())
                self.assertEqual(user["role"], role)

    def test_helper_rejects_other_roles_with_403(self) -> None:
        for role in ("user", "staff", "manager", "boss_user"):
            with self.subTest(role=role):
                with patch.object(
                    main,
                    "_get_authenticated_user",
                    return_value={"username": "u", "real_name": "U", "role": role},
                ):
                    with self.assertRaises(HTTPException) as raised:
                        main._require_ecom_knowledge_delete_permission(_request())
                self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
