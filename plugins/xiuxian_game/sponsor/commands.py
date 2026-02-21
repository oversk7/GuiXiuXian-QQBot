"""
赞助商店 — 指令处理器

指令列表:
  【赞助商店】        查看商店及诡烛余额
  【诡烛余额】        快速查看诡烛余额
  【购买称号 <文字>】 购买自定义称号
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head
from .service import SponsorShopService


# ==================== 命令注册 ====================

sponsor_shop_cmd = on_command("赞助商店", aliases={"诡烛商店"}, priority=5, block=True)
gui_zhu_balance_cmd = on_command("诡烛余额", aliases={"诡烛查询", "我的诡烛"}, priority=5, block=True)
buy_title_cmd = on_command("购买称号", priority=5, block=True)


# ==================== 赞助商店 ====================

@sponsor_shop_cmd.handle()
async def handle_sponsor_shop(event: MessageEvent):
    """展示赞助商店界面"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await sponsor_shop_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await sponsor_shop_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        info = SponsorShopService.get_shop_info(player)

    await sponsor_shop_cmd.finish(message_add_head(info, event))


# ==================== 诡烛余额 ====================

@gui_zhu_balance_cmd.handle()
async def handle_gui_zhu_balance(event: MessageEvent):
    """快速查看诡烛余额"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await gui_zhu_balance_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await gui_zhu_balance_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        msg = (
            f"🕯️ 诡烛余额\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 {player.nickname} 的诡烛: {player.gui_zhu} 枚\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 【赞助商店】查看可购买服务"
        )

    await gui_zhu_balance_cmd.finish(message_add_head(msg, event))


# ==================== 购买称号 ====================

@buy_title_cmd.handle()
async def handle_buy_title(event: MessageEvent, args: Message = CommandArg()):
    """购买自定义称号"""
    title_text = args.extract_plain_text().strip()

    if not title_text:
        await buy_title_cmd.finish(message_add_head(
            "📛 购买自定义称号\n"
            "━━━━━━━━━━━━━\n"
            "用法：【购买称号 你的称号】\n"
            "示例：【购买称号 万古枭雄】\n"
            f"价格：100 诡烛\n"
            "限制：2-8个字符，永久拥有",
            event
        ))

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await buy_title_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await buy_title_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        success, msg = SponsorShopService.buy_custom_title(player, title_text)

    await buy_title_cmd.finish(message_add_head(msg, event))
