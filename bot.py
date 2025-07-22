import nonebot
from nonebot.adapters.qq import Adapter
from nonebot import logger

# 添加日志文件输出
logger.add("logs/command_log.txt", level="INFO", rotation="1 day", retention="30 days", encoding="utf-8")

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(Adapter)

nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()