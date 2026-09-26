import os
from uuid import uuid4

import pytest
from sqlalchemy import JSON, DefaultClause, MetaData, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _local_mysql_url(database_url):
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise ValueError("GUIX_MYSQL_TEST_URL 只允许本机 mysql+aiomysql 测试库") from None
    # 驱动可用 query 参数覆盖 host / unix_socket，测试连接不接受这类覆盖。
    if (url.drivername != "mysql+aiomysql"
            or url.host not in {"localhost", "127.0.0.1"}
            or url.query):
        raise ValueError("GUIX_MYSQL_TEST_URL 只允许本机 mysql+aiomysql 测试库，且不能包含查询参数")
    return url


@pytest.fixture
async def mysql_session_factory():
    database_url = os.environ.get("GUIX_MYSQL_TEST_URL", "").strip()
    if not database_url:
        pytest.skip("设置 GUIX_MYSQL_TEST_URL 运行 MySQL 并发回归")
    url = _local_mysql_url(database_url)
    from plugins.xiuxian_game.models.db import Base

    schema = f"guixiuxian2_test_{uuid4().hex}"
    admin_engine = create_async_engine(url.set(database=None))
    engine = create_async_engine(url.set(database=schema), isolation_level="REPEATABLE READ")
    async with admin_engine.begin() as connection:
        await connection.execute(text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4"))
    try:
        metadata = MetaData()
        for table in Base.metadata.sorted_tables:
            copied = table.to_metadata(metadata)
            for column in copied.columns:
                default = column.server_default
                # MySQL 的 JSON 字面量默认值要求括号表达式。
                if isinstance(column.type, JSON) and default is not None and isinstance(default.arg, str):
                    literal = default.arg.replace("'", "''")
                    column.server_default = DefaultClause(text(f"('{literal}')"))
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f"DROP DATABASE `{schema}`"))
        await admin_engine.dispose()
