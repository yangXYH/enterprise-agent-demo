import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "utils" / "business_forecast_service.py"
MIGRATION_PATH = (
    ROOT
    / "database"
    / "migrations"
    / "20260714_create_inv_business_forecast_tables.sql"
)
TABLES = {
    "inv_business_import_batch",
    "inv_business_daily",
    "inv_business_forecast",
    "inv_business_forecast_city",
}


def _create_table_statements(sql: str) -> dict[str, str]:
    pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"
        r"(?P<table>inv_business_[a-z_]+)\s*\("
        r"(?P<body>.*?)\)\s*ENGINE\s*=\s*InnoDB\s+"
        r"DEFAULT\s+CHARSET\s*=\s*utf8mb4\s+"
        r"COLLATE\s*=\s*utf8mb4_unicode_ci\s+"
        r"COMMENT\s*=\s*'(?P<comment>[^']*)'\s*;?",
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


def _mutation_columns(service_source: str) -> dict[str, set[str]]:
    result = {table: set() for table in TABLES}
    insert_pattern = re.compile(
        r"INSERT\s+INTO\s+(inv_business_[a-z_]+)\s*\((.*?)\)\s*VALUES",
        re.IGNORECASE | re.DOTALL,
    )
    for match in insert_pattern.finditer(service_source):
        table = match.group(1).lower()
        if table in result:
            result[table].update(
                column.strip().strip("`").lower()
                for column in match.group(2).split(",")
            )

    update_pattern = re.compile(
        r"UPDATE\s+(inv_business_[a-z_]+)\s+SET\s+(.*?)(?:\s+WHERE\s+)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in update_pattern.finditer(service_source):
        table = match.group(1).lower()
        if table in result:
            result[table].update(
                assignment.split("=", 1)[0].strip().strip("`").lower()
                for assignment in match.group(2).split(",")
            )
    return result


class BusinessForecastMigrationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service_source = SERVICE_PATH.read_text(encoding="utf-8")
        cls.migration_source = MIGRATION_PATH.read_text(encoding="utf-8")
        cls.service_tables = _create_table_statements(cls.service_source)
        cls.migration_tables = _create_table_statements(cls.migration_source)

    def test_migration_defines_exactly_the_service_tables(self) -> None:
        self.assertEqual(TABLES, set(self.service_tables))
        self.assertEqual(TABLES, set(self.migration_tables))

    def test_columns_types_keys_indexes_and_options_match_service_ddl(self) -> None:
        self.assertEqual(self.service_tables, self.migration_tables)

    def test_service_insert_and_update_columns_exist_in_migration(self) -> None:
        mutations = _mutation_columns(self.service_source)
        for table, mutation_columns in mutations.items():
            with self.subTest(table=table):
                self.assertTrue(mutation_columns)
                self.assertLessEqual(
                    mutation_columns,
                    _table_columns(self.migration_tables[table]),
                )

    def test_migration_is_additive_and_idempotent(self) -> None:
        upper = self.migration_source.upper()
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("DROP DATABASE", upper)
        self.assertNotIn("TRUNCATE", upper)
        self.assertNotIn("DELETE FROM", upper)
        self.assertEqual(4, upper.count("CREATE TABLE IF NOT EXISTS"))


if __name__ == "__main__":
    unittest.main()
