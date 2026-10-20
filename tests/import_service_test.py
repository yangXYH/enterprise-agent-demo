import os
import unittest
from unittest.mock import patch

from utils import import_service


class ImportServiceEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        import_service.dispose_engine()

    def tearDown(self) -> None:
        import_service.dispose_engine()

    def test_get_engine_reuses_one_engine_for_repeated_calls(self) -> None:
        with patch.dict(os.environ, {"DB_URL": "sqlite:///:memory:"}):
            first = import_service.get_engine()
            second = import_service.get_engine()

        self.assertIs(first, second)

    def test_production_requires_explicit_database_configuration(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "production 环境数据库配置不完整"):
                import_service.get_engine()

    def test_test_environment_requires_explicit_database_configuration(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "test"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "test 环境数据库配置不完整"):
                import_service.get_engine()


if __name__ == "__main__":
    unittest.main()
