"""
赞助商店 — 指令处理器

指令列表:
  【赞助商店】            查看商店及诡烛余额
  【购买改名卡】          购买改名卡（10诡烛）
  【公会改名 <新名称>】   公会改名（200诡烛，会长专属）
  【购买称号 <文字>】     购买自定义称号（500诡烛）
  【购买棺材钉】          购买棺材钉（50诡烛）
  【购买哭坟帽】          购买哭坟帽（20诡烛）
  【购买初级月卡】        购买30天初级月卡（88诡烛）
  【购买高级月卡】        购买30天高级月卡（288诡烛）
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
buy_rename_card_cmd = on_command("购买改名卡", aliases={"赞助改名卡"}, priority=5, block=True)
guild_rename_cmd = on_command("公会改名", aliases={"改名公会"}, priority=5, block=True)
buy_title_cmd = on_command("购买称号", priority=5, block=True)
buy_coffin_nail_cmd = on_command("购买棺材钉", priority=5, block=True)
buy_crying_tomb_hat_cmd = on_command("购买哭坟帽", priority=5, block=True)
buy_basic_monthly_card_cmd = on_command("购买初级月卡", aliases={"兑换初级月卡"}, priority=5, block=True)
buy_premium_monthly_card_cmd = on_command("购买高级月卡", aliases={"兑换高级月卡"}, priority=5, block=True)


# ==================== 工具函数 ====================

async def _get_player_or_finish(session, event, cmd):
    """统一获取玩家，未注册时结束"""
    player = await get_unified_player(session, event)
    if not player:
        if is_guild_message(event):
            await cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
        else:
            await cmd.finish("⛔ 请先使用【注册】命令创建角色")
    return player


# ==================== 赞助商店 ====================

@sponsor_shop_cmd.handle()
async def handle_sponsor_shop(event: MessageEvent):
    """展示赞助商店界面"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, sponsor_shop_cmd)
        info = SponsorShopService.get_shop_info(player)

    await sponsor_shop_cmd.finish(message_add_head(info, event))


# ==================== 购买改名卡 ====================

@buy_rename_card_cmd.handle()
async def handle_buy_rename_card(event: MessageEvent):
    """购买改名卡（10诡烛）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_rename_card_cmd)
        success, msg = await SponsorShopService.buy_rename_card(player, session)

    await buy_rename_card_cmd.finish(message_add_head(msg, event))


# ==================== 公会改名 ====================

@guild_rename_cmd.handle()
async def handle_guild_rename(event: MessageEvent, args: Message = CommandArg()):
    """公会改名（200诡烛，会长专属）"""
    new_name = args.extract_plain_text().strip()

    if not new_name:
        await guild_rename_cmd.finish(message_add_head(
            "🏛️ 公会改名\n"
            "━━━━━━━━━━━━━\n"
            "用法：【公会改名 新名称】\n"
            "示例：【公会改名 诡域探秘者】\n"
            "价格：200 诡烛\n"
            "限制：最多16字符，仅会长可用",
            event
        ))

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, guild_rename_cmd)
        success, msg = await SponsorShopService.buy_guild_rename(player, new_name, session)

    await guild_rename_cmd.finish(message_add_head(msg, event))


# ==================== 购买称号 ====================

@buy_title_cmd.handle()
async def handle_buy_title(event: MessageEvent, args: Message = CommandArg()):
    """购买自定义称号（500诡烛）"""
    title_text = args.extract_plain_text().strip()

    if not title_text:
        await buy_title_cmd.finish(message_add_head(
            "📛 购买自定义称号\n"
            "━━━━━━━━━━━━━\n"
            "用法：【购买称号 你的称号】\n"
            "示例：【购买称号 万古枭雄】\n"
            "价格：500 诡烛\n"
            "限制：1-8个字符，永久拥有",
            event
        ))

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_title_cmd)
        success, msg = SponsorShopService.buy_custom_title(player, title_text)

    await buy_title_cmd.finish(message_add_head(msg, event))


# ==================== 购买棺材钉 ====================

@buy_coffin_nail_cmd.handle()
async def handle_buy_coffin_nail(event: MessageEvent):
    """购买棺材钉（50诡烛）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_coffin_nail_cmd)
        success, msg = await SponsorShopService.buy_coffin_nail(player, session)

    await buy_coffin_nail_cmd.finish(message_add_head(msg, event))


# ==================== 购买哭坟帽 ====================

@buy_crying_tomb_hat_cmd.handle()
async def handle_buy_crying_tomb_hat(event: MessageEvent):
    """购买哭坟帽（20诡烛）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_crying_tomb_hat_cmd)
        success, msg = await SponsorShopService.buy_crying_tomb_hat(player, session)

    await buy_crying_tomb_hat_cmd.finish(message_add_head(msg, event))


# ==================== 购买初级月卡 ====================

@buy_basic_monthly_card_cmd.handle()
async def handle_buy_basic_monthly_card(event: MessageEvent):
    """购买初级月卡（88诡烛，30天）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_basic_monthly_card_cmd)
        success, msg = await SponsorShopService.buy_monthly_card(player, "basic", session)

    await buy_basic_monthly_card_cmd.finish(message_add_head(msg, event))


# ==================== 购买高级月卡 ====================

@buy_premium_monthly_card_cmd.handle()
async def handle_buy_premium_monthly_card(event: MessageEvent):
    """购买高级月卡（288诡烛，30天）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_premium_monthly_card_cmd)
        success, msg = await SponsorShopService.buy_monthly_card(player, "premium", session)

    await buy_premium_monthly_card_cmd.finish(message_add_head(msg, event))
