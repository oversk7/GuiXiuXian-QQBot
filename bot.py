import nonebot
from nonebot.adapters.qq import Adapter
from nonebot import logger

# 添加日志文件输出
logger.add("logs/command_log.txt", level="INFO", rotation="12h", retention="3 days", encoding="utf-8")
# 添加调试日志输出
logger.add("logs/debug.log", level="DEBUG", rotation="12h", retention="3 days", encoding="utf-8")

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(Adapter)

nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()