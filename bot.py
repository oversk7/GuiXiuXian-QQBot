import nonebot
from nonebot.adapters.qq import Adapter
from nonebot import logger

# 添加日志文件输出（通过 .env 的 LOG_LEVEL 控制详细程度）
logger.add("logs/bot.log", level="INFO", rotation="12h", retention="3 days", encoding="utf-8")

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(Adapter)

nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()