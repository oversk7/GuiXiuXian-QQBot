from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func
from ..data.db import get_session
from ..models.player import Player
from ..config import Config
from ..utils import create_rich_message
from nonebot import get_driver

cultivate = on_command("修炼", block=True, priority=5, aliases={"cultivate"})

# 获取插件配置
plugin_config = Config.parse_obj(get_driver().config)

@cultivate.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    try:
        duration = args.extract_plain_text().strip() or "1"
        
        if not duration.isdigit():
            await cultivate.finish("⛔ 请输入有效的修炼时长（整数）")
        
        duration = min(int(duration), plugin_config.cultivate.daily_limit)  # 限制最大时长
        
        async with get_session() as session:
            # 使用SQLAlchemy核心查询
            result = await session.execute(
                select(Player).where(Player.uid == event.get_user_id())
            )
            player = result.scalars().first()
            
            if not player:
                await cultivate.finish("⛔ 你还没有创建角色，请先使用「创建角色」指令")
            
            # 更新数据
            await session.execute(
                update(Player)
                .where(Player.uid == event.get_user_id())
                .values(
                    level=Player.level + 1,
                    hp=func.min(Player.hp + 50, 100)
                )
            )
            await session.commit()
            
            # 获取更新后的数据
            result = await session.execute(
                select(Player).where(Player.uid == event.get_user_id())
            )
            player = result.scalars().first()
            
            # 修改经验计算逻辑
            exp_gain = plugin_config.cultivate.base_exp * int(duration) * (player.level ** 2)
            
            # 构建富文本消息
            content = f"""
            🌌 修炼成果：
            ▫ 境界提升：{player.level - 1} → {player.level}
            ▫ 气血恢复：+50
            ▫ 累计经验：+{exp_gain}
            """
            await cultivate.finish(create_rich_message("诡道修炼", content))
        
    except SQLAlchemyError as e:
        await cultivate.finish(f"⛔ 数据库操作失败：{str(e)}")
    except ValueError as e:
        await cultivate.finish(f"⛔ 数据异常：{str(e)}")
    except Exception as e:
        # 实际开发中应使用更具体的异常类型
        await cultivate.finish(f"⛔ 修炼时发生意外：{str(e)}") 