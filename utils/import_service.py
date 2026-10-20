"""Shared database-engine helper.

The Excel import pipeline for the 京东自营/POP 大盘 pages was removed together
with those pages; this module now only provides the SQLAlchemy engine factory
used by the remaining services (inventory, HR, ecom knowledge, …).
"""

from __future__ import annotations

import logging
import os
from threading import Lock

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL


LOGGER = logging.getLogger(__name__)

DEFAULT_DB_NAME = "enterprise_agent_db"
PRODUCTION_ENVIRONMENTS = {"production", "prod"}
CONFIGURED_ENVIRONMENTS = {"test", "testing", *PRODUCTION_ENVIRONMENTS}

_ENGINE: Engine | None = None
_ENGINE_CONFIG: tuple[object, ...] | None = None
_ENGINE_LOCK = Lock()


def _database_config() -> tuple[object, ...]:
    """Return the settings that determine the shared engine."""

    return (
        os.getenv("APP_ENV", "development").strip().lower(),
        os.getenv("DB_URL") or os.getenv("DATABASE_URL"),
        os.getenv("DB_HOST", "127.0.0.1"),
        os.getenv("DB_PORT", "3306"),
        os.getenv("DB_USER", "root"),
        os.getenv("DB_PASSWORD", "root"),
        os.getenv("DB_NAME", DEFAULT_DB_NAME),
        os.getenv("DB_POOL_SIZE", "5"),
        os.getenv("DB_MAX_OVERFLOW", "5"),
        os.getenv("DB_POOL_TIMEOUT", "30"),
        os.getenv("DB_POOL_RECYCLE", "1800"),
    )


def _pool_options(config: tuple[object, ...]) -> dict[str, object]:
    """Build bounded pool options for MySQL without breaking custom DB URLs."""

    database_url = str(config[1] or "")
    if database_url and not database_url.lower().startswith("mysql"):
        return {}

    def _positive_int_at(index: int, default: int) -> int:
        try:
            return max(1, int(str(config[index])))
        except (TypeError, ValueError):
            return default

    def _nonnegative_int_at(index: int, default: int) -> int:
        try:
            return max(0, int(str(config[index])))
        except (TypeError, ValueError):
            return default

    return {
        "pool_size": _positive_int_at(7, 5),
        "max_overflow": _nonnegative_int_at(8, 5),
        "pool_timeout": _positive_int_at(9, 30),
        "pool_recycle": _positive_int_at(10, 1800),
    }


def get_engine() -> Engine:
    """Return the shared SQLAlchemy engine for the current environment.

    Supported variables:
    DB_URL or DATABASE_URL can provide a full SQLAlchemy URL. Otherwise the
    function uses DB_HOST, DB_PORT, DB_USER, DB_PASSWORD and DB_NAME.

    Each engine owns a connection pool. Creating one for every request caused
    otherwise short-lived page queries to accumulate idle MySQL connections
    until the server returned ``Too many connections``. Reusing one bounded
    pool keeps connection ownership at the process level.
    """

    global _ENGINE, _ENGINE_CONFIG
    config = _database_config()
    app_env = str(config[0])
    database_url = str(config[1] or "")
    if app_env in CONFIGURED_ENVIRONMENTS and not database_url:
        missing = [
            name
            for name in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                f"{app_env} 环境数据库配置不完整，请在对应环境文件或进程环境中设置："
                + ", ".join(missing)
            )
    with _ENGINE_LOCK:
        if _ENGINE is not None and _ENGINE_CONFIG == config:
            return _ENGINE

        if _ENGINE is not None:
            _ENGINE.dispose()

        options = {
            "pool_pre_ping": True,
            "future": True,
            **_pool_options(config),
        }
        if database_url:
            _ENGINE = create_engine(database_url, **options)
        else:
            url = URL.create(
                "mysql+pymysql",
                username=str(config[4]),
                password=str(config[5]),
                host=str(config[2]),
                port=int(str(config[3])),
                database=str(config[6]),
                query={"charset": "utf8mb4"},
            )
            _ENGINE = create_engine(url, **options)

        _ENGINE_CONFIG = config
        return _ENGINE


def dispose_engine() -> None:
    """Dispose the shared pool during application shutdown or reconfiguration."""

    global _ENGINE, _ENGINE_CONFIG
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            _ENGINE.dispose()
        _ENGINE = None
        _ENGINE_CONFIG = None
