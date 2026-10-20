import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "utils" / "ai_daily_board_service.py"
MIGRATION_PATH = (
    ROOT
    / "database"
    / "migrations"
    / "20260817_create_ai_daily_board_tables.sql"
)
TABLES = {
    "ai_daily_board",
    "ai_daily_board_project",
    "ai_daily_board_daily_log",
    "ai_daily_board_risk",
    "ai_daily_board_activity",
}


def _create_table_statements(sql: str) -> dict[str, str]:
    pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"
        r"(?P<table>ai_daily_board(?:_project|_daily_log|_risk|_activity)?)\s*\("
        r"(?P<body>.*?)\)\s*ENGINE\s*=\s*InnoDB\s+"
        r"DEFAULT\s+CHARSET\s*=\s*utf8mb4\s+"
        r"COLLATE\s*=\s*utf8mb4_unicode_ci\s+"
        r"COMMENT\s*=\s*'[^']*'\s*;?",
        re.IGNORECASE | re.DOTALL,
    )
    return {
        match.group("table").lower(): _normalize_ddl(match.group(0))
        for match in pattern.finditer(sql)
    }


def _normalize_ddl(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).lower()


def _table_columns(create_sql: str) -> set[str]:
    body = create_sql[create_sql.index("(") + 1 : create_sql.rindex(")")]
    columns = set()
    for part in body.split(","):
        token = part.strip().split(None, 1)[0].strip("`").lower()
        if token not in {"primary", "unique", "key", "constraint", "foreign"}:
            columns.add(token)
    return columns


class AiDailyBoardMigrationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service_source = SERVICE_PATH.read_text(encoding="utf-8")
        cls.migration_source = MIGRATION_PATH.read_text(encoding="utf-8")
        cls.service_tables = _create_table_statements(cls.service_source)
        cls.migration_tables = _create_table_statements(cls.migration_source)

    def test_migration_defines_exactly_the_service_tables(self) -> None:
        self.assertEqual(TABLES, set(self.service_tables))
        self.assertEqual(TABLES, set(self.migration_tables))

    def test_columns_types_keys_and_indexes_match_service_ddl(self) -> None:
        self.assertEqual(self.service_tables, self.migration_tables)

    def test_migration_contains_chinese_comments(self) -> None:
        upper = self.migration_source.upper()
        self.assertIn("COMMENT", upper)
        self.assertRegex(self.migration_source, r"COMMENT '[^']*[\u4e00-\u9fff]")
        self.assertRegex(self.migration_source, r"-- [\u4e00-\u9fff]")

    def test_migration_is_additive_and_idempotent(self) -> None:
        upper = self.migration_source.upper()
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("DROP DATABASE", upper)
        self.assertNotIn("TRUNCATE", upper)
        self.assertNotIn("DELETE FROM", upper)
        create_count = len(
            re.findall(
                r"^\s*CREATE TABLE IF NOT EXISTS\s",
                upper,
                flags=re.MULTILINE,
            )
        )
        self.assertEqual(5, create_count)
        self.assertEqual(
            _table_columns(self.migration_tables["ai_daily_board"]),
            {
                "id",
                "board_key",
                "board_title",
                "current_date",
                "show_charts",
                "show_standup",
                "show_timeline",
                "show_table",
                "created_at",
                "updated_at",
            },
        )


if __name__ == "__main__":
    unittest.main()
