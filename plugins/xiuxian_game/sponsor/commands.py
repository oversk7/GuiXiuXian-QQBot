"""
赞助商店 — 指令处理器

指令列表:
  【赞助商店】            查看商店及诡烛余额
  【购买改名卡】          购买改名卡（10诡烛）
  【公会改名 <新名称>】   公会改名（200诡烛，会长专属）
  【购买称号 <文字>】     购买自定义称号（500诡烛）
  【购买棺材钉】          购买棺材钉（50诡烛）
  【购买哭坟帽】          购买哭坟帽（20诡烛）
  【购买重启符 [N]】      购买重启符（1000诡烛/张）
  【背包扩容 N】          背包永久扩容N格（10诡烛/格）
  【购买初级月卡】        购买30天初级月卡（88诡烛）
  【购买高级月卡】        购买30天高级月卡（288诡烛）
  【购买闭关特权】        闭关无时间上限（180诡烛/月）
  【购买远程仓库】        远程存取阴宅仓库（180诡烛/月）
  【购买鱼竿特权】        每次多钓2条鱼（180诡烛/月）
  【购买全视之眼】        俯瞰显示诡域全图（180诡烛/月）
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..platform_utils import get_unified_player, is_guild_message
from ..utils_markdown import cmd, build_markdown
from .service import SponsorShopService


# ==================== 命令注册 ====================

sponsor_shop_cmd = on_command("赞助商店", aliases={"诡烛商店"}, priority=5, block=True)
buy_rename_card_cmd = on_command("购买改名卡", aliases={"赞助改名卡"}, priority=5, block=True)
guild_rename_cmd = on_command("公会改名", aliases={"改名公会"}, priority=5, block=True)
buy_title_cmd = on_command("购买称号", priority=5, block=True)
buy_coffin_nail_cmd = on_command("购买棺材钉", priority=5, block=True)
buy_crying_tomb_hat_cmd = on_command("购买哭坟帽", priority=5, block=True)
buy_reset_talisman_cmd = on_command("购买重启符", aliases={"兑换重启符"}, priority=5, block=True)
buy_santa_rift_cmd = on_command("购买圣诞裂隙", aliases={"购买裂隙"}, priority=5, block=True)
expand_inventory_cmd = on_command("背包扩容", aliases={"扩容背包"}, priority=5, block=True)
buy_basic_monthly_card_cmd = on_command("购买初级月卡", aliases={"兑换初级月卡"}, priority=5, block=True)
buy_premium_monthly_card_cmd = on_command("购买高级月卡", aliases={"兑换高级月卡"}, priority=5, block=True)
# 赞助特权
buy_premium_seclusion_cmd = on_command("购买闭关特权", aliases={"闭关特权"}, block=True, priority=5)
buy_premium_warehouse_cmd = on_command("购买远程仓库", aliases={"远程仓库特权"}, block=True, priority=5)
buy_premium_fishing_cmd = on_command("购买鱼竿特权", aliases={"鱼竿特权"}, block=True, priority=5)
buy_premium_vision_cmd = on_command("购买全视之眼", aliases={"全视之眼特权"}, block=True, priority=5)
my_sponsor_log_cmd = on_command("赞助兑换记录", aliases={"赞助记录"}, priority=5, block=True)
admin_sponsor_log_cmd = on_command("查赞助记录", priority=2, block=True)


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

    buttons = f"\n***\n{cmd('赞助记录')} | {cmd('购买初级月卡')} | {cmd('购买高级月卡')}"
    await sponsor_shop_cmd.finish(build_markdown(info + buttons))


# ==================== 购买改名卡 ====================

@buy_rename_card_cmd.handle()
async def handle_buy_rename_card(event: MessageEvent):
    """购买改名卡（10诡烛）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_rename_card_cmd)
        success, msg = await SponsorShopService.buy_rename_card(player, session)

    buttons = f"\n***\n{cmd('赞助商店')} | {cmd('赞助记录')}"
    await buy_rename_card_cmd.finish(build_markdown(msg + buttons))


# ==================== 公会改名 ====================

@guild_rename_cmd.handle()
async def handle_guild_rename(event: MessageEvent, args: Message = CommandArg()):
    """公会改名（200诡烛，会长专属）"""
    new_name = args.extract_plain_text().strip()

    if not new_name:
        content = (
            "# 🏛️ 公会改名\n"
            "***\n"
            f"用法：{cmd('公会改名 新名称', '公会改名 ')}\n"
            f"示例：{cmd('公会改名 诡域探秘者')}\n"
            "价格：**200** 诡烛\n"
            "限制：最多16字符，仅会长可用\n"
            f"***\n{cmd('赞助商店')}"
        )
        await guild_rename_cmd.finish(build_markdown(content))

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, guild_rename_cmd)
        success, msg = await SponsorShopService.buy_guild_rename(player, new_name, session)

    buttons = f"\n***\n{cmd('我的公会')} | {cmd('赞助商店')}"
    await guild_rename_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买称号 ====================

@buy_title_cmd.handle()
async def handle_buy_title(event: MessageEvent, args: Message = CommandArg()):
    """购买自定义称号（500诡烛）"""
    title_text = args.extract_plain_text().strip()

    if not title_text:
        content = (
            "# 📛 购买自定义称号\n"
            "***\n"
            f"用法：{cmd('购买称号 你的称号', '购买称号 ')}\n"
            f"示例：{cmd('购买称号 万古枭雄')}\n"
            "价格：**500** 诡烛\n"
            "限制：1-8个字符，永久拥有\n"
            f"***\n{cmd('赞助商店')}"
        )
        await buy_title_cmd.finish(build_markdown(content))

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_title_cmd)
        success, msg = await SponsorShopService.buy_custom_title(player, title_text, session)

    buttons = f"\n***\n{cmd('切换称号')} | {cmd('赞助商店')}"
    await buy_title_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买棺材钉 ====================

@buy_coffin_nail_cmd.handle()
async def handle_buy_coffin_nail(event: MessageEvent):
    """购买棺材钉（50诡烛）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_coffin_nail_cmd)
        success, msg = await SponsorShopService.buy_coffin_nail(player, session)

    buttons = f"\n***\n{cmd('赞助商店')} | {cmd('背包')}"
    await buy_coffin_nail_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买哭坟帽 ====================

@buy_crying_tomb_hat_cmd.handle()
async def handle_buy_crying_tomb_hat(event: MessageEvent):
    """购买哭坟帽（20诡烛）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_crying_tomb_hat_cmd)
        success, msg = await SponsorShopService.buy_crying_tomb_hat(player, session)

    buttons = f"\n***\n{cmd('赞助商店')} | {cmd('背包')}"
    await buy_crying_tomb_hat_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买重启符 ====================

@buy_reset_talisman_cmd.handle()
async def handle_buy_reset_talisman(event: MessageEvent, args: Message = CommandArg()):
    """购买重启符（1000诡烛/张）"""
    arg_text = args.extract_plain_text().strip()

    quantity = 1
    if arg_text:
        if not arg_text.isdigit() or int(arg_text) <= 0:
            content = (
                "# 🔄 购买重启符\n"
                "***\n"
                f"用法：{cmd('购买重启符')} {cmd('购买重启符 3', '购买重启符 ')}\n"
                "价格：**1000** 诡烛/张\n"
                "效果：使用后重置所有属性点，可重新分配\n"
                "保留：装备加成、丹药加成、VIP装备加成\n"
                f"***\n{cmd('赞助商店')}"
            )
            await buy_reset_talisman_cmd.finish(build_markdown(content))
        quantity = int(arg_text)

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_reset_talisman_cmd)
        success, msg = await SponsorShopService.buy_reset_talisman(player, quantity, session)

    buttons = f"\n***\n{cmd('赞助商店')} | {cmd('洗点')}"
    await buy_reset_talisman_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买圣诞裂隙 ====================

@buy_santa_rift_cmd.handle()
async def handle_buy_santa_rift(event: MessageEvent, args: Message = CommandArg()):
    """购买圣诞裂隙（30诡烛/个）"""
    arg_text = args.extract_plain_text().strip()

    quantity = 1
    if arg_text:
        if not arg_text.isdigit() or int(arg_text) <= 0:
            content = (
                "# 🌀 购买圣诞裂隙\n"
                "***\n"
                f"用法：{cmd('购买圣诞裂隙')} {cmd('购买圣诞裂隙 3', '购买圣诞裂隙 ')}\n"
                "价格：**30** 诡烛/个\n"
                "效果：瞬移到任意坐标或诡域层级\n"
                f"***\n{cmd('赞助商店')}"
            )
            await buy_santa_rift_cmd.finish(build_markdown(content))
        quantity = int(arg_text)

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_santa_rift_cmd)
        success, msg = await SponsorShopService.buy_santa_rift(player, quantity, session)

    buttons = f"\n***\n{cmd('赞助商店')} | {cmd('背包')}"
    await buy_santa_rift_cmd.finish(build_markdown(msg + buttons))


# ==================== 背包扩容 ====================

@expand_inventory_cmd.handle()
async def handle_expand_inventory(event: MessageEvent, args: Message = CommandArg()):
    """背包永久扩容（10诡烛/格）"""
    arg_text = args.extract_plain_text().strip()

    slots = 1
    if arg_text:
        if not arg_text.isdigit() or int(arg_text) <= 0:
            content = (
                "# 🎒 背包扩容\n"
                "***\n"
                f"用法：{cmd('背包扩容 格数', '背包扩容 ')}\n"
                f"示例：{cmd('背包扩容 5')}\n"
                "价格：**10** 诡烛/格，永久有效\n"
                f"***\n{cmd('赞助商店')}"
            )
            await expand_inventory_cmd.finish(build_markdown(content))
        slots = int(arg_text)

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, expand_inventory_cmd)
        success, msg = await SponsorShopService.expand_inventory(player, slots, session)

    buttons = f"\n***\n{cmd('背包')} | {cmd('赞助商店')}"
    await expand_inventory_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买初级月卡 ====================

@buy_basic_monthly_card_cmd.handle()
async def handle_buy_basic_monthly_card(event: MessageEvent):
    """购买初级月卡（88诡烛，30天）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_basic_monthly_card_cmd)
        success, msg = await SponsorShopService.buy_monthly_card(player, "basic", session)

    buttons = f"\n***\n{cmd('月卡')} | {cmd('赞助商店')}"
    await buy_basic_monthly_card_cmd.finish(build_markdown(msg + buttons))


# ==================== 购买高级月卡 ====================

@buy_premium_monthly_card_cmd.handle()
async def handle_buy_premium_monthly_card(event: MessageEvent):
    """购买高级月卡（288诡烛，30天）"""
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_premium_monthly_card_cmd)
        success, msg = await SponsorShopService.buy_monthly_card(player, "premium", session)

    buttons = f"\n***\n{cmd('月卡')} | {cmd('赞助商店')}"
    await buy_premium_monthly_card_cmd.finish(build_markdown(msg + buttons))


# ==================== 赞助特权购买 ====================

@buy_premium_seclusion_cmd.handle()
async def handle_buy_premium_seclusion(event: MessageEvent):
    """购买闭关无上限特权（180诡烛/月）"""
    from .service import PREMIUM_SECLUSION_PRICE
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_premium_seclusion_cmd)
        success, msg = await SponsorShopService.buy_premium_privilege(
            player, "premium_seclusion_until", "闭关无上限特权",
            PREMIUM_SECLUSION_PRICE, session
        )
    buttons = f"\n***\n{cmd('赞助商店')}"
    await buy_premium_seclusion_cmd.finish(build_markdown(msg + buttons))


@buy_premium_warehouse_cmd.handle()
async def handle_buy_premium_warehouse(event: MessageEvent):
    """购买远程仓库特权（180诡烛/月）"""
    from .service import PREMIUM_WAREHOUSE_PRICE
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_premium_warehouse_cmd)
        success, msg = await SponsorShopService.buy_premium_privilege(
            player, "premium_warehouse_until", "远程仓库特权",
            PREMIUM_WAREHOUSE_PRICE, session
        )
    buttons = f"\n***\n{cmd('赞助商店')}"
    await buy_premium_warehouse_cmd.finish(build_markdown(msg + buttons))


@buy_premium_fishing_cmd.handle()
async def handle_buy_premium_fishing(event: MessageEvent):
    """购买鱼竿特权（180诡烛/月）"""
    from .service import PREMIUM_FISHING_PRICE
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_premium_fishing_cmd)
        success, msg = await SponsorShopService.buy_premium_privilege(
            player, "premium_fishing_until", "鱼竿特权",
            PREMIUM_FISHING_PRICE, session
        )
    buttons = f"\n***\n{cmd('赞助商店')}"
    await buy_premium_fishing_cmd.finish(build_markdown(msg + buttons))


@buy_premium_vision_cmd.handle()
async def handle_buy_premium_vision(event: MessageEvent):
    """购买全视之眼特权（180诡烛/月）"""
    from .service import PREMIUM_VISION_PRICE
    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, buy_premium_vision_cmd)
        success, msg = await SponsorShopService.buy_premium_privilege(
            player, "premium_vision_until", "全视之眼特权",
            PREMIUM_VISION_PRICE, session
        )
    buttons = f"\n***\n{cmd('赞助商店')}"
    await buy_premium_vision_cmd.finish(build_markdown(msg + buttons))


# ==================== 玩家自查兑换记录 ====================

@my_sponsor_log_cmd.handle()
async def handle_my_sponsor_log(event: MessageEvent, args: Message = CommandArg()):
    """查看自己的近期兑换记录（默认最近10条）"""
    from ..models.sponsor_shop_log import SponsorShopLog
    from ..models.player import Player

    arg_text = args.extract_plain_text().strip()
    limit = 10
    if arg_text.isdigit():
        limit = min(int(arg_text), 30)  # 最多30条

    async with safe_session() as session:
        player = await _get_player_or_finish(session, event, my_sponsor_log_cmd)
        logs = (
            await session.execute(
                select(SponsorShopLog)
                .where(SponsorShopLog.player_id == player.id)
                .order_by(SponsorShopLog.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    if not logs:
        content = f"📋 暂无兑换记录\n***\n{cmd('赞助商店')}"
        await my_sponsor_log_cmd.finish(build_markdown(content))

    lines = [
        "# 🕯️ 我的赞助兑换记录",
        "***",
    ]
    for log in logs:
        lines.append(
            f"[{log.created_at.strftime('%m-%d %H:%M')}] {log.action}"
            + (f"({log.detail})" if log.detail else "")
            + f" -**{log.cost}**诡烛 余额:**{log.balance_after}**"
        )
    lines.append(f"\n***\n{cmd('赞助商店')}")

    await my_sponsor_log_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 管理员查任意玩家记录 ====================

@admin_sponsor_log_cmd.handle()
async def handle_admin_sponsor_log(event: MessageEvent, args: Message = CommandArg()):
    """管理员查询玩家兑换记录：【查赞助记录 UID [条数]】"""
    from ..ai_guide import is_admin
    from ..models.sponsor_shop_log import SponsorShopLog
    from ..models.player import Player

    if not is_admin(event.get_user_id()):
        await admin_sponsor_log_cmd.finish("⛔ 权限不足，仅管理员可用")

    parts = args.extract_plain_text().strip().split()
    if not parts or not parts[0].isdigit():
        await admin_sponsor_log_cmd.finish("用法：【查赞助记录 UID】或【查赞助记录 UID 条数】")

    target_uid = int(parts[0])
    limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
    limit = min(limit, 100)

    async with safe_session() as session:
        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await admin_sponsor_log_cmd.finish(f"⛔ 未找到 UID={target_uid} 的玩家")

        logs = (
            await session.execute(
                select(SponsorShopLog)
                .where(SponsorShopLog.player_id == target.id)
                .order_by(SponsorShopLog.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    if not logs:
        await admin_sponsor_log_cmd.finish(f"📋 玩家 {target.nickname}[{target_uid}] 暂无兑换记录")

    lines = [
        f"# 🕯️ {target.nickname}[UID:{target_uid}] 兑换记录",
        "***",
    ]
    for log in logs:
        lines.append(
            f"[{log.created_at.strftime('%Y-%m-%d %H:%M')}] {log.action}"
            + (f"({log.detail})" if log.detail else "")
            + f" -**{log.cost}**诡烛 余:**{log.balance_after}**"
        )
    lines.append("***")
    lines.append(f"共 **{len(logs)}** 条，总消耗 **{sum(l.cost for l in logs)}** 诡烛")

    await admin_sponsor_log_cmd.finish(build_markdown("\n".join(lines)))
