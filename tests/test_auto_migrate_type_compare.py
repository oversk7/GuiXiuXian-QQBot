"""自动迁移的类型比较：MySQL 反射出的排序规则和 BOOLEAN 别名不应触发重复 ALTER（无需数据库连接）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import mysql

from plugins.xiuxian_game.models import auto_migrate


@pytest.mark.parametrize("reflected, target", [
    ('VARCHAR(64) COLLATE "utf8mb4_unicode_ci"', "VARCHAR(64)"),
    ("TINYINT", "BOOLEAN"),
    ("TINYINT(1)", "BOOLEAN"),
    ("INTEGER", "INT"),
])
def test_equivalent_types_compare_equal(reflected, target):
    assert auto_migrate._comparable_type(reflected) == auto_migrate._comparable_type(target)


@pytest.mark.parametrize("reflected, target", [
    ('VARCHAR(32) COLLATE "utf8mb4_unicode_ci"', "VARCHAR(64)"),
    ("INT", "BIGINT"),
    ("TINYINT", "INT"),
])
def test_real_type_changes_still_detected(reflected, target):
    assert auto_migrate._comparable_type(reflected) != auto_migrate._comparable_type(target)


async def test_reflected_mysql_columns_need_no_alter(monkeypatch):
    monkeypatch.setattr(auto_migrate, "REQUIRED_FIELDS", {
        "player": {
            "last_group_openid": auto_migrate.REQUIRED_FIELDS["player"]["last_group_openid"],
            "inventory_compact": auto_migrate.REQUIRED_FIELDS["player"]["inventory_compact"],
        },
    })
    inspector = Mock()
    # 与线上 MySQL 8.0 反射结果一致：字符串带排序规则，BOOLEAN 显示为 TINYINT
    inspector.get_columns.return_value = [
        {"name": "last_group_openid", "type": mysql.VARCHAR(64, collation="utf8mb4_unicode_ci")},
        {"name": "inventory_compact", "type": mysql.TINYINT()},
    ]
    monkeypatch.setattr(auto_migrate, "inspect", Mock(return_value=inspector))

    async def run_sync(callback):
        return callback(object())

    connection = SimpleNamespace(
        dialect=mysql.dialect(),
        run_sync=AsyncMock(side_effect=run_sync),
        execute=AsyncMock(),
    )

    assert await auto_migrate._add_missing_fields(connection, verbose=False) == 0
    connection.execute.assert_not_awaited()
