"""One-time, verified migration of operating-analysis data from SQLite to MySQL.

Run from the project root:
    .venv/Scripts/python.exe tools/migrate_operating_sqlite_to_mysql.py

The destination uses the normal DB_URL / DB_* application settings. Existing
destination data is never overwritten unless --replace is explicitly supplied.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.operating_db import TABLES, connect


ROOT = Path(__file__).resolve().parents[1]
TABLE_MAP = (
    ("operating_settings", "jy_operating_settings"),
    ("batches", "jy_batches"),
    ("operating_brands", "jy_operating_brands"),
    ("records", "jy_records"),
    ("operating_knowledge_document", "jy_operating_knowledge_document"),
    ("operating_knowledge_chunk", "jy_operating_knowledge_chunk"),
    ("operating_chat_session", "jy_operating_chat_session"),
    ("operating_chat_turn", "jy_operating_chat_turn"),
)
DELETE_ORDER = tuple(target for _, target in reversed(TABLE_MAP))


def source_tables(source) -> set[str]:
    return {row[0] for row in source.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}


def counts(source, destination, available):
    source_counts = {
        table: source.execute(f"SELECT COUNT(*) FROM `{table}`").fetchone()[0]
        if table in available else 0
        for table, _ in TABLE_MAP
    }
    target_counts = {
        source_name: destination.execute(f"SELECT COUNT(*) FROM `{target_name}`").fetchone()[0]
        for source_name, target_name in TABLE_MAP
    }
    return source_counts, target_counts


def normalize(source_name, target_name, row):
    values = dict(row)
    if source_name == "operating_settings" and "key" in values:
        values["setting_key"] = values.pop("key")
    table = TABLES[target_name]
    allowed = {column.name for column in table.columns}
    values = {key: value for key, value in values.items() if key in allowed}
    for column in table.columns:
        value = values.get(column.name)
        if isinstance(column.type, DateTime) and isinstance(value, str) and value:
            values[column.name] = datetime.fromisoformat(value)
    return values


def signature_sql(table_name):
    if table_name in ("records", "jy_records"):
        return f"SELECT COUNT(*),COALESCE(SUM(revenue),0),COALESCE(SUM(cart_amount),0),MIN(day),MAX(day) FROM `{table_name}`"
    return f"SELECT COUNT(*) FROM `{table_name}`"


def verify(source, destination, available):
    failures = []
    for source_name, target_name in TABLE_MAP:
        if source_name not in available:
            expected = (0,)
        else:
            expected = tuple(source.execute(signature_sql(source_name)).fetchone())
        actual = tuple(destination.execute(signature_sql(target_name)).fetchone())
        if actual != expected:
            failures.append(f"{target_name}: SQLite={expected}, MySQL={actual}")
    if failures:
        raise RuntimeError("迁移校验失败：\n" + "\n".join(failures))


def migrate(path: Path, replace: bool = False, batch_size: int = 1000):
    if not path.is_file():
        raise FileNotFoundError(f"SQLite 文件不存在：{path}")
    source = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        available = source_tables(source)
        with connect() as destination:
            if destination.dialect != "mysql":
                raise RuntimeError(f"目标数据库不是 MySQL：{destination.dialect}")
            source_counts, target_counts = counts(source, destination, available)
            if any(target_counts.values()) and source_counts == target_counts:
                verify(source, destination, available)
                print("MySQL 中已存在同规模且校验一致的数据，无需重复迁移。", flush=True)
                return source_counts
            if any(target_counts.values()) and not replace:
                raise RuntimeError(
                    "MySQL 经营分析表不是空表，为防止覆盖已停止迁移。"
                    "确认需要以 SQLite 覆盖时，请显式添加 --replace。"
                )
            if replace:
                for table in DELETE_ORDER:
                    destination.execute(f"DELETE FROM `{table}`")

            for source_name, target_name in TABLE_MAP:
                total = source_counts[source_name]
                if not total:
                    print(f"{target_name}: 0", flush=True)
                    continue
                cursor = source.execute(f"SELECT * FROM `{source_name}`")
                copied = 0
                while True:
                    chunk = cursor.fetchmany(batch_size)
                    if not chunk:
                        break
                    destination.insert_many(target_name, [normalize(source_name, target_name, row) for row in chunk])
                    copied += len(chunk)
                    if copied == total or copied % 50000 == 0:
                        print(f"{target_name}: {copied}/{total}", flush=True)
            verify(source, destination, available)
            print("迁移及逐表校验完成。", flush=True)
            return source_counts
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description="将经营分析 SQLite 数据迁移到应用 MySQL")
    parser.add_argument("source", nargs="?", type=Path, default=ROOT / "data" / "operating_analysis.sqlite3")
    parser.add_argument("--replace", action="store_true", help="清空 MySQL 经营分析表后重新迁移")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if not 100 <= args.batch_size <= 5000:
        parser.error("--batch-size 必须在 100 到 5000 之间")
    migrate(args.source, args.replace, args.batch_size)


if __name__ == "__main__":
    main()
