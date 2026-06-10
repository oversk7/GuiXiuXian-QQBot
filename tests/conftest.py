"""pytest 全局配置。

plugins.xiuxian_game 包在导入时就注册指令（on_command 内部调用
get_driver()），因此在收集测试之前统一初始化 NoneBot，
与 bot.py 的启动顺序保持一致。不连接数据库、不启动 driver。
"""

import nonebot


def pytest_configure(config):
    # 已初始化则跳过，避免重复 init 覆盖全局 driver
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
        # pet/scheduler.py 里 require("nonebot_plugin_apscheduler") 要求它
        # 先以插件方式加载（与 pyproject [tool.nonebot] plugins 一致）
        nonebot.load_plugin("nonebot_plugin_apscheduler")
