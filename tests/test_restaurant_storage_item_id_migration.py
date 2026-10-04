"""餐厅仓库长物品 ID 的 MySQL 自动迁移回归（无需数据库连接）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from sqlalchemy.dialects import mysql

from plugins.xiuxian_game.models import auto_migrate
from plugins.xiuxian_game.models.restaurant import RestaurantStorage


@pytest.fixture
def migration_connection(monkeypatch):
    # 取真实迁移配置，仅隔离无关表；漏配 restaurant_storage 时仍应失败。
    fields = auto_migrate.REQUIRED_FIELDS["restaurant_storage"]
    monkeypatch.setattr(auto_migrate, "REQUIRED_FIELDS", {"restaurant_storage": fields})
    inspector = Mock()
    sync_connection = object()
    inspect_mock = Mock(return_value=inspector)
    monkeypatch.setattr(auto_migrate, "inspect", inspect_mock)

    async def run_sync(callback):
        # 执行真实反射回调，覆盖从 SQLAlchemy 类型提取 VARCHAR 长度的逻辑。
        return callback(sync_connection)

    connection = SimpleNamespace(
        dialect=mysql.dialect(),
        run_sync=AsyncMock(side_effect=run_sync),
        execute=AsyncMock(),
    )
    return connection, inspector, inspect_mock, sync_connection


def storage_columns(length):
    return [{"name": "item_id", "type": mysql.VARCHAR(length)}]


def test_storage_model_and_migration_support_long_dish_id():
    dish_id = "dish_stir_fried_spirit_cabbage_normal"
    column = RestaurantStorage.__table__.c.item_id
    field_def = auto_migrate.REQUIRED_FIELDS["restaurant_storage"]["item_id"]

    assert 32 < len(dish_id) <= 64
    assert column.type.length == 64
    assert column.nullable is False
    assert field_def == f"VARCHAR(64) NOT NULL COMMENT '{column.comment}'"


async def test_old_storage_item_id_is_widened_once(migration_connection):
    connection, inspector, inspect_mock, sync_connection = migration_connection
    # 第一次是旧库，第二次反射迁移后的结构。
    inspector.get_columns.side_effect = [storage_columns(32), storage_columns(64)]

    assert await auto_migrate._add_missing_fields(connection, verbose=False) == 1
    connection.execute.assert_awaited_once()
    statement = connection.execute.await_args.args[0]
    assert str(statement.compile(dialect=connection.dialect)) == (
        "ALTER TABLE restaurant_storage MODIFY COLUMN item_id "
        "VARCHAR(64) NOT NULL COMMENT '食材物品ID(items.yaml)'"
    )

    assert await auto_migrate._add_missing_fields(connection, verbose=False) == 0
    connection.execute.assert_awaited_once()
    assert inspector.get_columns.call_args_list == [
        call("restaurant_storage"),
        call("restaurant_storage"),
    ]
    assert connection.run_sync.await_count == 2
    inspect_mock.assert_called_with(sync_connection)


async def test_new_storage_item_id_needs_no_repeated_migration(migration_connection):
    connection, inspector, _, _ = migration_connection
    inspector.get_columns.return_value = storage_columns(64)

    for _ in range(2):
        assert await auto_migrate._add_missing_fields(connection, verbose=False) == 0

    connection.execute.assert_not_awaited()
    assert inspector.get_columns.call_count == 2
    assert connection.run_sync.await_count == 2
