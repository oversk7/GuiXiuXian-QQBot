from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlmodel import select
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
        # 解析参数
        duration = args.extract_plain_text().strip() or "1"
        
        if not duration.isdigit():
            await cultivate.finish("⛔ 请输入有效的修炼时长（整数）")
        
        # 获取数据库会话
        session = next(get_session())
        
        # 查询玩家数据
        stmt = select(Player).where(Player.uid == event.get_user_id())
        player = session.exec(stmt).first()
        
        if not player:
            await cultivate.finish("⛔ 你还没有创建角色，请先使用「创建角色」指令")
            
        # 计算修炼收益（示例公式）
        exp_gain = int(10 * int(duration) * plugin_config.exp_rate)
        
        # 更新玩家数据
        player.level += 1
        player.hp = min(player.hp + 50, 100)
        session.add(player)
        session.commit()
        
        # 构建富文本消息
        content = f"""
        🌌 修炼成果：
        ▫ 境界提升：{player.level - 1} → {player.level}
        ▫ 气血恢复：+50
        ▫ 累计经验：+{exp_gain}
        """
        await cultivate.finish(create_rich_message("诡道修炼", content))
        
    except ValueError as e:
        await cultivate.finish(f"⛔ 数据异常：{str(e)}")
    except Exception as e:
        # 实际开发中应使用更具体的异常类型
        await cultivate.finish(f"�� 修炼时发生意外：{str(e)}") 