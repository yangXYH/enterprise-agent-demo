import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


EMPTY_STATE = {
    "settings": {
        "boardTitle": "AI 项目进度看板",
        "currentDate": "2026-08-17",
        "showCharts": True,
        "showStandup": True,
        "showTimeline": True,
        "showTable": True,
    },
    "projects": [],
    "dailyLogs": [],
    "dailyLogDates": [],
    "risks": [],
    "weekLogs": [],
    "allLogs": [],
}


class AiDailyBoardApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @patch("main.ai_daily_board_service.get_board_state", return_value=EMPTY_STATE)
    def test_get_board_state(self, get_board_state_mock) -> None:
        response = self.client.get("/api/ai-daily-board")
        self.assertEqual(200, response.status_code)
        self.assertEqual(EMPTY_STATE, response.json())
        get_board_state_mock.assert_called_once_with(
            board_key="default",
            target_date=None,
        )

    def test_get_board_state_with_date(self) -> None:
        with patch(
            "main.ai_daily_board_service.get_board_state",
            return_value=EMPTY_STATE,
        ) as get_board_state_mock:
            response = self.client.get("/api/ai-daily-board?date=2026-08-15")
        self.assertEqual(200, response.status_code)
        get_board_state_mock.assert_called_once_with(
            board_key="default",
            target_date="2026-08-15",
        )

    @patch("main.ai_daily_board_service.save_board_state", return_value=EMPTY_STATE)
    def test_save_board_state(self, save_board_state_mock) -> None:
        save_payload = dict(EMPTY_STATE)
        save_payload["dailyLogs"] = [
            {
                "projectId": "project-1",
                "projectName": "项目A",
                "work": "完成A模块",
                "tomorrow": "",
                "risks": "",
            },
            {
                "projectId": "project-2",
                "projectName": "项目B",
                "work": "完成B模块",
                "tomorrow": "",
                "risks": "",
            },
        ]
        save_payload.pop("dailyLogDates")
        save_payload.pop("weekLogs")
        save_payload.pop("allLogs")
        response = self.client.put("/api/ai-daily-board", json=save_payload)
        self.assertEqual(200, response.status_code)
        self.assertEqual(EMPTY_STATE, response.json())
        # 一天多条相互独立的任务推进记录应原样传到 service 层
        save_board_state_mock.assert_called_once_with(
            save_payload,
            board_key="default",
        )

    @patch("main.ai_daily_board_service.save_board_state", return_value=EMPTY_STATE)
    def test_save_board_state_legacy_single_daily_log(self, save_board_state_mock) -> None:
        """兼容旧前端：提交单个 dailyLog 对象仍应被接受。"""
        save_payload = dict(EMPTY_STATE)
        save_payload["dailyLog"] = {
            "projectId": "project-1",
            "projectName": "项目A",
            "work": "完成A模块",
            "tomorrow": "",
            "risks": "",
        }
        save_payload.pop("dailyLogDates")
        save_payload.pop("weekLogs")
        save_payload.pop("allLogs")
        response = self.client.put("/api/ai-daily-board", json=save_payload)
        self.assertEqual(200, response.status_code)
        self.assertEqual(EMPTY_STATE, response.json())
        save_board_state_mock.assert_called_once_with(
            save_payload,
            board_key="default",
        )


if __name__ == "__main__":
    unittest.main()
