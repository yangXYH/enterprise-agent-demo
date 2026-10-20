"""Populate an isolated MySQL database using the application's real schema/services.

Never reads the original project or its database. Existing demo edits are retained.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.sql.sqltypes import Date, DateTime, Integer, Numeric, Float, Boolean, JSON

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OWNER = "enterprise-agent-demo-synthetic-v2"
VERSION = "full-application-v6"
TODAY = date.fromisoformat(os.getenv("DEMO_DATE", date.today().isoformat()))


def configure():
    path = ROOT / ".env.demo"
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw:
                key, value = raw.split("=", 1)
                if key.strip().startswith(("DEMO_", "LLM_", "OPENAI_", "OPERATING_AI_")):
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    name = os.getenv("DEMO_DB_NAME", "enterprise_agent_demo")
    if not re.fullmatch(r"enterprise_agent_demo(?:_[a-z0-9]+)?", name):
        raise RuntimeError("Only a dedicated enterprise_agent_demo database is allowed.")
    url = URL.create("mysql+pymysql", host=os.getenv("DEMO_DB_HOST", "127.0.0.1"),
                     port=int(os.getenv("DEMO_DB_PORT", "3306")), username=os.getenv("DEMO_DB_USER", "root"),
                     password=os.getenv("DEMO_DB_PASSWORD", "root"), database=name, query={"charset": "utf8mb4"})
    os.environ.update(APP_ENV="demo", DB_URL=url.render_as_string(hide_password=False), DB_NAME=name,
                      JUSHUITAN_SYNC_ENABLED="false", DB_POOL_SIZE="5", DB_MAX_OVERFLOW="5")
    return url


def open_demo_database():
    url = configure()
    # A Docker-provisioned demo user already has a database; no server admin grant is needed.
    admin = create_engine(url.set(database=""), pool_pre_ping=True)
    try:
        with admin.begin() as connection:
            exists = connection.execute(text("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=:name"), {"name": url.database}).scalar()
            if not exists:
                connection.exec_driver_sql(f"CREATE DATABASE `{url.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        admin.dispose()
    from utils import import_service
    engine = import_service.get_engine()
    tables = set(inspect(engine).get_table_names())
    if tables and "demo_runtime_meta" not in tables:
        raise RuntimeError("Refusing to seed an existing database without the demo ownership marker.")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS demo_runtime_meta (meta_key VARCHAR(80) PRIMARY KEY, meta_value VARCHAR(255) NOT NULL)"))
        owner = connection.execute(text("SELECT meta_value FROM demo_runtime_meta WHERE meta_key='owner'")).scalar()
        if owner and owner != OWNER:
            raise RuntimeError("Demo database ownership does not match.")
        connection.execute(text("INSERT IGNORE INTO demo_runtime_meta VALUES ('owner',:owner)"), {"owner": OWNER})
    return engine


def initialize_schema(engine):
    # Reuse only CREATE statements from the original core schema; never run its DROP/USE statements.
    sql = (ROOT / "database/rebuild_from_local_schema.sql").read_text(encoding="utf8")
    with engine.begin() as connection:
        for statement in re.findall(r"CREATE TABLE `[^`]+`\s*\([\s\S]*?;", sql):
            connection.exec_driver_sql(statement.replace("CREATE TABLE `", "CREATE TABLE IF NOT EXISTS `", 1))
        connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS sys_user_login_record (id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, username VARCHAR(50) NOT NULL, login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, KEY idx_login_username(username)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    initializers = {
        "hr_service": "ensure_tables", "inventory_service": "ensure_inventory_schema",
        "business_forecast_service": "ensure_business_schema", "sku_warning_service": "ensure_schema",
        "inventory_product_dashboard_service": "ensure_schema", "jushuitan_dashboard_service": "ensure_schema",
        "purchase_order_dashboard_service": "ensure_schema", "sales_dashboard_service": "ensure_schema",
        "ai_daily_board_service": "ensure_schema", "cs_dashboard_service": "ensure_schema",
        "ecom_dashboard_service": "ensure_schema", "ecom_knowledge_service": "ensure_schema",
        "points_service": "ensure_tables", "design_library_service": "ensure_schema",
        "product_quality_report_service": "ensure_ready", "sku_return_service": "ensure_schema",
    }
    for name, method in initializers.items():
        module = importlib.import_module("utils." + name)
        getattr(module, method)(engine)
        print("Schema ready:", name)
    from utils import operating_db
    operating_db.metadata.create_all(engine)


def count(engine, name):
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError(name)
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar() or 0)


def insert_rows(engine, name, rows, append=False):
    """Fill required columns explicitly, retaining the real service's table/column types."""
    if not rows or (not append and count(engine, name)):
        return
    table = Table(name, MetaData(), autoload_with=engine)
    packed = []
    for index, values in enumerate(rows, 1):
        row = {}
        for column in table.columns:
            if column.name in values:
                row[column.name] = values[column.name]
            elif column.primary_key and column.autoincrement is True:
                continue
            elif column.server_default is not None:
                continue
            elif column.nullable:
                row[column.name] = None
            elif isinstance(column.type, DateTime):
                row[column.name] = datetime.combine(TODAY, datetime.min.time())
            elif isinstance(column.type, Date):
                row[column.name] = TODAY
            elif isinstance(column.type, (Integer, Numeric, Float, Boolean)):
                row[column.name] = 0
            elif isinstance(column.type, JSON):
                row[column.name] = {}
            else:
                row[column.name] = ""
        packed.append(row)
    with engine.begin() as connection:
        statement = table.insert().prefix_with("IGNORE") if append else table.insert()
        connection.execute(statement, packed)
    print(f"Seeded {name}: {len(packed)} synthetic rows")


def seed():
    engine = open_demo_database()
    with engine.connect() as connection:
        current = connection.execute(text("SELECT meta_value FROM demo_runtime_meta WHERE meta_key='version'")).scalar()
    if current == VERSION:
        print("Existing synthetic demo database retained; using original application services.")
        return engine
    initialize_schema(engine)
    from full_demo_fixtures import populate
    populate(engine, TODAY, insert_rows, count)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO demo_runtime_meta VALUES ('version',:version) ON DUPLICATE KEY UPDATE meta_value=VALUES(meta_value)"), {"version": VERSION})
    print("Full application demo database ready. Demo login: demo_admin / Demo@2026")
    return engine


if __name__ == "__main__":
    seed()
