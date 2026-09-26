"""pytest 全局配置。

plugins.xiuxian_game 包在导入时就注册指令（on_command 内部调用
get_driver()），因此在收集测试之前统一初始化 NoneBot，
与 bot.py 的启动顺序保持一致。不连接数据库、不启动 driver。
"""

import os

import nonebot
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--require-mysql",
        action="store_true",
        help="要求设置 GUIX_MYSQL_TEST_URL，供 CI 运行 MySQL 测试",
    )
    parser.addoption(
        "--require-redis",
        action="store_true",
        help="要求设置 GUIX_REDIS_TEST_URL，供 CI 运行 Redis 测试",
    )


def pytest_configure(config):
    for service in ("mysql", "redis"):
        config.addinivalue_line("markers", f"{service}: 需要独立的本机 {service} 测试服务")
        variable = f"GUIX_{service.upper()}_TEST_URL"
        if config.getoption(f"--require-{service}") and not os.environ.get(variable, "").strip():
            raise pytest.UsageError(f"--require-{service} 需要设置 {variable}")
    # 已初始化则跳过，避免重复 init 覆盖全局 driver
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
        # pet/scheduler.py 里 require("nonebot_plugin_apscheduler") 要求它
        # 先以插件方式加载（与 pyproject [tool.nonebot] plugins 一致）
        nonebot.load_plugin("nonebot_plugin_apscheduler")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    for item in items:
        if "mysql_session_factory" in item.fixturenames:
            item.add_marker(pytest.mark.mysql)
        if "redis_backend_factory" in item.fixturenames:
            item.add_marker(pytest.mark.redis)
