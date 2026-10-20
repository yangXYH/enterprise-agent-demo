"""MySQL-backed persistence primitives for the operating-analysis module.

The public services historically used sqlite3's small DB-API surface directly.
This adapter keeps that surface stable while routing production traffic through
the application's shared SQLAlchemy/MySQL connection pool.
"""
from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime
from threading import Lock
from weakref import WeakKeyDictionary

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.mysql import VARCHAR as mysql_varchar
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from utils.import_service import get_engine


metadata = MetaData()


def binary_string(length: int):
    """Match SQLite's case-sensitive text identity on MySQL."""
    return String(length).with_variant(mysql_varchar(length, collation="utf8mb4_bin"), "mysql")

batches = Table(
    "jy_batches", metadata,
    Column("filename", binary_string(255), primary_key=True, comment="导入文件名"),
    Column("digest", String(64), comment="文件 SHA-256 摘要"),
    Column("imported_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="导入时间"),
    Column("row_count", Integer, comment="有效明细行数"),
    Column("start", String(10), comment="数据起始日期"),
    Column("end", String(10), comment="数据结束日期"),
    Column("control", Text, comment="原报表合计行 JSON"),
    Column("headers", Text, comment="原报表表头 JSON"),
    comment="经营分析导入批次",
)

records = Table(
    "jy_records", metadata,
    Column("day", binary_string(10), primary_key=True, comment="统计日期 YYYY-MM-DD"),
    Column("sku", binary_string(191), primary_key=True, comment="商品 SKU"),
    Column("name", binary_string(512), comment="SKU 名称"),
    Column("code", binary_string(255), comment="商品货号"),
    Column("category", binary_string(512), comment="三级类目"),
    Column("filename", binary_string(255), primary_key=True, nullable=False, comment="来源文件名"),
    Column("source_row", Integer, comment="来源文件行号"),
    Column("revenue", BigInteger, comment="成交金额，百万分之一元"),
    Column("quantity", Float, comment="成交商品件数"),
    Column("orders", Float, comment="成交单量"),
    Column("customers", Float, comment="成交客户数"),
    Column("views", Float, comment="商品浏览量"),
    Column("visitors", Float, comment="商品访客数"),
    Column("cart_quantity", Float, comment="加购商品件数"),
    Column("cart_customers", Float, comment="加购客户数"),
    Column("cart_amount", BigInteger, comment="加购金额，百万分之一元"),
    Column("raw", Text, comment="原始行完整字段 JSON"),
    Column("source", binary_string(32), nullable=False, server_default=text("'示例科技'")),
    Column("brand", binary_string(255), comment="标准化品牌名称"),
    Index("operating_day", "day"),
    Index("operating_sku", "sku"),
    Index("operating_sku_code", "sku", "code"),
    Index("operating_category", "category"),
    comment="经营分析商品日明细",
)

operating_settings = Table(
    "jy_operating_settings", metadata,
    Column("setting_key", binary_string(100), primary_key=True, comment="配置键"),
    Column("value", Text, comment="配置值"),
    comment="经营分析内部配置及数据版本",
)

operating_brands = Table(
    "jy_operating_brands", metadata,
    Column("name", binary_string(512), primary_key=True, comment="SKU 名称"),
    Column("brand", binary_string(255), comment="标准化品牌名称"),
    Index("operating_brands_brand", "brand"),
    comment="经营分析商品名称与品牌映射",
)

operating_model_mapping = Table(
    "jy_operating_model_mapping", metadata,
    Column("sku", binary_string(191), primary_key=True, comment="商品 SKU"),
    Column("code", binary_string(255), nullable=False, comment="运营维护的商品货号/型号"),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="首次维护时间"),
    Column("updated_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="最后维护时间"),
    Index("operating_model_mapping_code", "code"),
    comment="经营分析 SKU 与型号货号的显式映射",
)

operating_chat_session = Table(
    "jy_operating_chat_session", metadata,
    Column("id", binary_string(32), primary_key=True, comment="会话 ID"),
    Column("owner", binary_string(191), nullable=False, comment="所属用户 ID"),
    Column("title", String(512), nullable=False, comment="会话标题"),
    Column("filters", Text, nullable=False, comment="最近一次有效查询条件 JSON"),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"),
    Column("updated_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="更新时间"),
    Index("operating_chat_owner", "owner", "updated_at"),
    comment="经营分析 AI 会话",
)

operating_chat_turn = Table(
    "jy_operating_chat_turn", metadata,
    Column("id", binary_string(32), primary_key=True, comment="问答轮次 ID"),
    Column("session_id", binary_string(32), nullable=False, comment="所属会话 ID"),
    Column("ordinal", Integer, nullable=False, comment="会话内轮次序号"),
    Column("request_id", binary_string(191), nullable=False, comment="客户端幂等请求 ID"),
    Column("question", Text, nullable=False, comment="用户问题"),
    Column("status", String(32), nullable=False, comment="pending/completed/error"),
    Column("response", Text, comment="完整回答及证据 JSON"),
    Column("context_refs", Text, nullable=False, comment="关联历史轮次 JSON"),
    Column("filters", Text, nullable=False, comment="本轮查询条件 JSON"),
    Column("error", Text, comment="失败原因"),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="提问时间"),
    Column("completed_at", DateTime, comment="完成时间"),
    Column("stage", String(120), server_default=text("''"), comment="生成阶段"),
    Column("partial_answer", Text, comment="生成中的已核对答案"),
    UniqueConstraint("session_id", "request_id", name="uq_operating_turn_request"),
    UniqueConstraint("session_id", "ordinal", name="uq_operating_turn_ordinal"),
    Index("operating_chat_turn_session", "session_id", "ordinal"),
    comment="经营分析 AI 问答轮次",
)

operating_knowledge_document = Table(
    "jy_operating_knowledge_document", metadata,
    Column("id", binary_string(24), primary_key=True, comment="文档版本 ID"),
    Column("library", String(64), comment="知识库类型"),
    Column("path", String(1024), comment="知识目录相对路径"),
    Column("title", String(512), comment="文档标题"),
    Column("digest", String(64), comment="内容 SHA-256 摘要"),
    Column("status", String(32), comment="索引状态"),
    Column("error", Text, comment="解析错误"),
    Column("indexed_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="首次索引时间"),
    Column("modified_ns", BigInteger, server_default=text("0"), comment="源文件修改时间纳秒值"),
    Column("size", BigInteger, server_default=text("0"), comment="源文件字节数"),
    comment="经营分析知识文档索引",
)

operating_knowledge_chunk = Table(
    "jy_operating_knowledge_chunk", metadata,
    Column("id", binary_string(24), primary_key=True, comment="知识片段 ID"),
    Column("document_id", binary_string(24), comment="所属文档 ID"),
    Column("heading", String(512), comment="章节标题"),
    Column("location", String(512), comment="页码或行号位置"),
    Column("text", Text, comment="知识片段正文"),
    Index("operating_knowledge_chunks_doc", "document_id"),
    comment="经营分析知识检索片段",
)

shop_report_chat_session = Table(
    "jy_shop_report_chat_session", metadata,
    Column("id", binary_string(32), primary_key=True, comment="会话 ID"),
    Column("owner", binary_string(191), nullable=False, comment="所属用户 ID"),
    Column("title", String(512), nullable=False, comment="会话标题"),
    Column("filters", Text, nullable=False, comment="最近一次有效查询条件 JSON"),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"),
    Column("updated_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="更新时间"),
    Index("shop_report_chat_owner", "owner", "updated_at"),
    comment="店铺报表 AI 会话",
)

shop_report_chat_turn = Table(
    "jy_shop_report_chat_turn", metadata,
    Column("id", binary_string(32), primary_key=True, comment="问答轮次 ID"),
    Column("session_id", binary_string(32), nullable=False, comment="所属会话 ID"),
    Column("ordinal", Integer, nullable=False, comment="会话内轮次序号"),
    Column("request_id", binary_string(191), nullable=False, comment="客户端幂等请求 ID"),
    Column("question", Text, nullable=False, comment="用户问题"),
    Column("status", String(32), nullable=False, comment="pending/completed/error"),
    Column("response", Text, comment="完整回答及证据 JSON"),
    Column("context_refs", Text, nullable=False, comment="关联历史轮次 JSON"),
    Column("filters", Text, nullable=False, comment="本轮查询条件 JSON"),
    Column("error", Text, comment="失败原因"),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), comment="提问时间"),
    Column("completed_at", DateTime, comment="完成时间"),
    Column("stage", String(120), server_default=text("''"), comment="生成阶段"),
    Column("partial_answer", Text, comment="生成中的已核对答案"),
    UniqueConstraint("session_id", "request_id", name="uq_shop_report_turn_request"),
    UniqueConstraint("session_id", "ordinal", name="uq_shop_report_turn_ordinal"),
    Index("shop_report_chat_turn_session", "session_id", "ordinal"),
    comment="店铺报表 AI 问答轮次",
)

TABLES = {table.name: table for table in metadata.tables.values()}
_schema_lock = Lock()
_initialized_engines: WeakKeyDictionary = WeakKeyDictionary()

MYSQL_BINARY_COLUMNS = {
    "jy_batches": {"filename": "VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"},
    "jy_records": {
        "day": "VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "sku": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "name": "VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL",
        "code": "VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL",
        "category": "VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL",
        "filename": "VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "source": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "brand": "VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL",
    },
    "jy_operating_settings": {"setting_key": "VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"},
    "jy_operating_brands": {
        "name": "VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "brand": "VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL",
    },
    "jy_operating_model_mapping": {
        "sku": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "code": "VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
    },
    "jy_operating_chat_session": {
        "id": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "owner": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
    },
    "jy_operating_chat_turn": {
        "id": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "session_id": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "request_id": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
    },
    "jy_operating_knowledge_document": {
        "id": "VARCHAR(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
    },
    "jy_operating_knowledge_chunk": {
        "id": "VARCHAR(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "document_id": "VARCHAR(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL",
    },
    "jy_shop_report_chat_session": {
        "id": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "owner": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
    },
    "jy_shop_report_chat_turn": {
        "id": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "session_id": "VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
        "request_id": "VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL",
    },
}


class Row:
    """sqlite3.Row-compatible value/key access used by existing services."""

    def __init__(self, keys, values):
        self._keys = tuple(keys)
        self._values = tuple(_normalize(value) for value in values)
        self._mapping = dict(zip(self._keys, self._values))

    def keys(self):
        return self._keys

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else self._mapping[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


def _normalize(value):
    # SQLite returned timestamp/date values as strings. Keep the API payloads
    # byte-for-byte compatible with that behavior after moving to MySQL.
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return value


class Result:
    def __init__(self, result):
        self._result = result
        self.rowcount = result.rowcount
        self._keys = tuple(result.keys()) if result.returns_rows else ()

    def _row(self, row):
        return None if row is None else Row(self._keys, row)

    def fetchone(self):
        return self._row(self._result.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self._result.fetchall()]

    def __iter__(self):
        for row in self._result:
            yield self._row(row)


class Connection:
    def __init__(self, connection):
        self._connection = connection
        self.dialect = connection.dialect.name

    def _sql(self, statement: str) -> str:
        if self.dialect == "mysql":
            return statement.replace("?", "%s")
        if self.dialect == "sqlite":
            return statement.replace(" FOR UPDATE", "")
        return statement

    def execute(self, statement: str, parameters=()):
        result = self._connection.exec_driver_sql(self._sql(statement), tuple(parameters))
        return Result(result)

    def executemany(self, statement: str, parameters: Iterable[tuple]):
        values = list(parameters)
        if not values:
            return None
        result = self._connection.exec_driver_sql(self._sql(statement), values)
        return Result(result)

    def upsert_many(self, table_name: str, rows: Iterable[dict], key_columns: tuple[str, ...]):
        values = list(rows)
        if not values:
            return None
        table = TABLES[table_name]
        update_columns = [column for column in values[0] if column not in key_columns]
        if self.dialect == "mysql":
            statement = mysql_insert(table).values(values)
            statement = statement.on_duplicate_key_update(
                **{column: statement.inserted[column] for column in update_columns}
            )
        elif self.dialect == "sqlite":
            statement = sqlite_insert(table).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=list(key_columns),
                set_={column: getattr(statement.excluded, column) for column in update_columns},
            )
        else:
            raise RuntimeError(f"不支持的经营分析数据库：{self.dialect}")
        return Result(self._connection.execute(statement))

    def insert_many(self, table_name: str, rows: Iterable[dict]):
        values = list(rows)
        if not values:
            return None
        return Result(self._connection.execute(TABLES[table_name].insert(), values))


def _ensure_schema(engine) -> None:
    with _schema_lock:
        if engine in _initialized_engines:
            return
        metadata.create_all(engine)
        # Upgrade databases created by the earlier SQLite schema or an early
        # MySQL preview without dropping user data.
        with engine.begin() as connection:
            if connection.dialect.name == "mysql":
                for table_name, columns in MYSQL_BINARY_COLUMNS.items():
                    for column_name, definition in columns.items():
                        current = connection.exec_driver_sql(
                            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                            (table_name, column_name),
                        ).scalar_one_or_none()
                        if current not in ("utf8mb4_0900_bin", "utf8mb4_bin"):
                            connection.exec_driver_sql(
                                f"ALTER TABLE `{table_name}` MODIFY `{column_name}` {definition}"
                            )
            inspector = inspect(connection)
            record_indexes = {index["name"] for index in inspector.get_indexes("jy_records")}
            if "operating_sku" not in record_indexes:
                connection.exec_driver_sql("CREATE INDEX operating_sku ON jy_records (sku)")
            if "operating_sku_code" not in record_indexes:
                connection.exec_driver_sql("CREATE INDEX operating_sku_code ON jy_records (sku, code)")
            chat_columns = {column["name"] for column in inspector.get_columns("jy_operating_chat_turn")}
            if "stage" not in chat_columns:
                connection.exec_driver_sql("ALTER TABLE jy_operating_chat_turn ADD COLUMN stage VARCHAR(120) DEFAULT '' COMMENT '生成阶段'")
            if "partial_answer" not in chat_columns:
                connection.exec_driver_sql("ALTER TABLE jy_operating_chat_turn ADD COLUMN partial_answer TEXT COMMENT '生成中的已核对答案'")
            knowledge_columns = {column["name"] for column in inspector.get_columns("jy_operating_knowledge_document")}
            if "modified_ns" not in knowledge_columns:
                connection.exec_driver_sql("ALTER TABLE jy_operating_knowledge_document ADD COLUMN modified_ns BIGINT DEFAULT 0 COMMENT '源文件修改时间纳秒值'")
            if "size" not in knowledge_columns:
                connection.exec_driver_sql("ALTER TABLE jy_operating_knowledge_document ADD COLUMN size BIGINT DEFAULT 0 COMMENT '源文件字节数'")
        _initialized_engines[engine] = True


@contextmanager
def connect():
    engine = get_engine()
    _ensure_schema(engine)
    try:
        with engine.begin() as raw_connection:
            yield Connection(raw_connection)
    finally:
        # File-backed SQLite is used only by isolated tests. Closing its pool
        # releases the temporary database immediately on Windows.
        if engine.dialect.name == "sqlite":
            engine.dispose()
