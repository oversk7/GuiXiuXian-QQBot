"""无数据库的 MySQL 测试开关与收集规则回归。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests import conftest
from tests.mysql_helpers import _local_mysql_url, mysql_session_factory


@pytest.mark.parametrize("service", ["mysql", "redis"])
@pytest.mark.parametrize("database_url", [None, "", "   "])
def test_required_service_fails_early_without_url(monkeypatch, database_url, service):
    variable = f"GUIX_{service.upper()}_TEST_URL"
    if database_url is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, database_url)
    driver = Mock(side_effect=AssertionError("不应初始化 NoneBot"))
    monkeypatch.setattr(conftest.nonebot, "get_driver", driver)
    config = SimpleNamespace(addinivalue_line=Mock(), getoption=lambda option: option == f"--require-{service}")

    with pytest.raises(pytest.UsageError, match=variable):
        conftest.pytest_configure(config)
    driver.assert_not_called()


async def test_default_mode_skips_mysql_without_url(monkeypatch):
    monkeypatch.delenv("GUIX_MYSQL_TEST_URL", raising=False)
    driver = object()
    monkeypatch.setattr(conftest.nonebot, "get_driver", lambda: driver)
    config = SimpleNamespace(addinivalue_line=Mock(), getoption=lambda _: False)

    conftest.pytest_configure(config)
    markers = [call.args[1].split(":", 1)[0] for call in config.addinivalue_line.call_args_list]
    assert markers == ["mysql", "redis"]
    with pytest.raises(pytest.skip.Exception, match="GUIX_MYSQL_TEST_URL"):
        await anext(mysql_session_factory.__wrapped__())


@pytest.mark.parametrize("service,fixture", [("mysql", "mysql_session_factory"), ("redis", "redis_backend_factory")])
def test_indirect_service_fixture_is_marked(service, fixture):
    item = SimpleNamespace(fixturenames=["intermediate_fixture", fixture], add_marker=Mock())
    regular_item = SimpleNamespace(fixturenames=["monkeypatch"], add_marker=Mock())

    conftest.pytest_collection_modifyitems([item, regular_item])

    assert item.add_marker.call_args.args[0].name == service
    regular_item.add_marker.assert_not_called()


@pytest.mark.parametrize("database_url", [
    "mysql+pymysql://user:secret@localhost/ignored",
    "mysql+aiomysql://user:secret@other-host/ignored",
    "mysql+aiomysql://user:secret@localhost/ignored?host=other-host",
    "mysql+aiomysql://user:secret@localhost/ignored?unix_socket=/tmp/mysql.sock",
    "invalid-url-user:secret",
])
def test_mysql_url_rejects_other_drivers_and_hosts_without_leaking_password(database_url):
    with pytest.raises(ValueError, match="本机 mysql\\+aiomysql") as exc:
        _local_mysql_url(database_url)
    assert "secret" not in str(exc.value)


def test_mysql_url_accepts_local_async_driver():
    assert _local_mysql_url("mysql+aiomysql://user:secret@127.0.0.1/ignored").drivername == "mysql+aiomysql"
