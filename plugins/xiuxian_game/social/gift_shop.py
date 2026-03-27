"""
礼物商店系统

提供直接购买好感度礼物的功能,无需NPC交互
支持每日购买限制,防止玩家只购买性价比最高的礼物
"""
import json
from datetime import date
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.exception import FinishedException

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..models.inventory import ItemType
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..config import config
from ..platform_utils import get_unified_player
from ..economy.market import get_shop_adjusted_price

# 创建命令
gift_shop_cmd = on_command("礼物商店", aliases={"礼物店", "礼品店"}, priority=5, block=True)
buy_gift_cmd = on_command("买礼物", aliases={"购买礼物"}, priority=5, block=True)


def get_daily_gift_purchases(player) -> dict:
    """获取玩家的每日礼物购买记录"""
    if not player.daily_gift_purchases:
        return {}
    try:
        return json.loads(player.daily_gift_purchases)
    except:
        return {}


def update_daily_gift_purchase(player, item_id: str, quantity: int) -> None:
    """更新玩家的每日礼物购买记录"""
    purchases = get_daily_gift_purchases(player)
    today = date.today().isoformat()

    if item_id not in purchases:
        purchases[item_id] = {"date": today, "count": 0}

    # 检查日期是否为今天,如果不是则重置
    if purchases[item_id]["date"] != today:
        purchases[item_id] = {"date": today, "count": 0}

    # 更新购买数量
    purchases[item_id]["count"] += quantity

    # 保存回玩家对象
    player.daily_gift_purchases = json.dumps(purchases, ensure_ascii=False)


def get_today_purchase_count(player, item_id: str) -> int:
    """获取指定礼物今天的购买数量"""
    purchases = get_daily_gift_purchases(player)
    today = date.today().isoformat()

    if item_id not in purchases:
        return 0

    if purchases[item_id]["date"] != today:
        return 0

    return purchases[item_id]["count"]


# 礼物商店菜单
async def get_gift_shop_menu(player_id: str = None) -> str:
    """获取礼物商店菜单"""
    # 获取所有礼物类物品
    gift_items = config.items_config["by_type"][ItemType.GIFT.value]

    # 按品质分组
    from collections import defaultdict
    rarity_groups = defaultdict(list)

    for item_id in gift_items:
        item_config = config.items_config["by_id"][item_id]
        rarity_groups[item_config.rarity].append(item_config)

    # 品质顺序和显示
    rarity_order = ["white", "green", "blue", "purple", "orange", "red"]
    rarity_names = {
        "white": "⚪ 白色品质",
        "green": "🟢 绿色品质",
        "blue": "🔵 蓝色品质",
        "purple": "🟣 紫色品质",
        "orange": "🟠 橙色品质",
        "red": "❤️ 红色品质"
    }

    lines = [
        "# 🎁 礼物商店",
        "***",
    ]

    # 获取玩家购买记录和动态价格
    player_purchases = {}
    async with UnitOfWork(AsyncSessionLocal) as uow:
        if player_id:
            player = await uow.players.get_by_id(player_id)
            if player:
                player_purchases = get_daily_gift_purchases(player)

        for rarity in rarity_order:
            if rarity not in rarity_groups:
                continue

            lines.append("")
            lines.append(f"**{rarity_names[rarity]}**")

            # 按价格排序
            items = sorted(rarity_groups[rarity], key=lambda x: x.price)

            for item in items:
                adj_price = await get_shop_adjusted_price(uow.session, item.price)
                # 获取每日限制
                daily_limit = getattr(item, 'daily_limit', 0)

                # 构建显示文本
                if daily_limit > 0:
                    # 获取今日已购买数量
                    purchased = 0
                    if item.item_id in player_purchases:
                        purchase_info = player_purchases[item.item_id]
                        if purchase_info["date"] == date.today().isoformat():
                            purchased = purchase_info["count"]

                    remaining = daily_limit - purchased
                    iname = item.name
                    lines.append(
                        f"{cmd(iname, f'买礼物 {iname}')}　{adj_price}金币　好感+{item.favorability}　剩余:{remaining}"
                    )
                else:
                    iname = item.name
                    lines.append(
                        f"{cmd(iname, f'买礼物 {iname}')}　{adj_price}金币　好感+{item.favorability}"
                    )

    lines.extend([
        "***",
        cmd("礼物商店") + " | " + cmd("帮助"),
    ])

    return "\n".join(lines)


@gift_shop_cmd.handle()
async def handle_gift_shop(event: MessageEvent, args: Message = CommandArg()):
    """礼物商店命令 - 显示可购买的礼物列表"""
    from ..models.db import safe_session
    async with safe_session() as session:
        player = await get_unified_player(session, event)
    player_id = player.id if player else None
    menu = await get_gift_shop_menu(player_id)
    await gift_shop_cmd.finish(build_markdown(menu))


@buy_gift_cmd.handle()
async def handle_buy_gift(event: MessageEvent, args: Message = CommandArg()):
    """
    买礼物命令 - 购买好感度礼物

    语法: 买礼物 <礼物名> [数量]

    示例:
    - 买礼物 红玫瑰
    - 买礼物 钻戒 3

    注意: 每种礼物有每日购买限制,品质越高限制越严格
    """
    try:
        # 1. 解析参数
        message_text = args.extract_plain_text().strip()
        if not message_text:
            await buy_gift_cmd.finish(
                message_add_head("⛔ 格式错误，正确格式：买礼物 <礼物名> [数量]\n示例：买礼物 红玫瑰 10", event)
            )

        parts = message_text.split()
        if len(parts) < 1:
            await buy_gift_cmd.finish(
                message_add_head("⛔ 格式错误，正确格式：买礼物 <礼物名> [数量]\n示例：买礼物 红玫瑰 10", event)
            )

        # 解析礼物名
        gift_name = parts[0]
        quantity = 1  # 默认数量

        # 解析数量
        if len(parts) >= 2:
            try:
                quantity = int(parts[1])
                if quantity <= 0:
                    await buy_gift_cmd.finish(message_add_head("⛔ 数量必须大于0", event))
            except ValueError:
                await buy_gift_cmd.finish(message_add_head("⛔ 数量格式错误，请输入数字", event))

        # 3. 获取物品配置
        item_config = config.items_config["by_name"].get(gift_name)
        if not item_config:
            await buy_gift_cmd.finish(message_add_head(f"❌ 礼物「{gift_name}」不存在", event))

        # 4. 检查是否为礼物类型
        if item_config.type != ItemType.GIFT:
            await buy_gift_cmd.finish(message_add_head(f"❌ 「{gift_name}」不是礼物,无法在礼物商店购买", event))

        # 5. 检查每日购买限制
        daily_limit = getattr(item_config, 'daily_limit', 0)
        if daily_limit > 0:
            async with UnitOfWork(AsyncSessionLocal) as uow:
                # 获取玩家（通过ownership系统）
                player = await get_unified_player(uow.session, event)
                if not player:
                    await buy_gift_cmd.finish(message_add_head("⛔ 请先创建角色", event))

                # 获取今日已购买数量
                purchased_today = get_today_purchase_count(player, item_config.item_id)

                # 检查是否超过限制
                if purchased_today + quantity > daily_limit:
                    remaining = daily_limit - purchased_today
                    await buy_gift_cmd.finish(
                        message_add_head(
                            f"❌ 今日购买数量已达上限！\n"
                            f"「{item_config.name}」每日限购{daily_limit}个，"
                            f"今日已购买{purchased_today}个，剩余{remaining}个",
                            event
                        )
                    )

        # 6. 计算总价（动态定价）
        # 7. 执行购买
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 获取玩家（通过ownership系统）
            player = await get_unified_player(uow.session, event)
            if not player:
                await buy_gift_cmd.finish(message_add_head("⛔ 请先创建角色", event))
            player_id = player.id

            adj_price = await get_shop_adjusted_price(uow.session, item_config.price)
            total_price = adj_price * quantity

            # 检查金币
            if player.gold < total_price:
                await buy_gift_cmd.finish(
                    message_add_head(f"❌ 金币不足！需要{total_price}金币，当前只有{player.gold}金币", event)
                )

            # 扣除金币
            player.gold -= total_price

            # 添加物品到背包(自动检查背包空间)
            from ..models.inventory import ItemInstance

            try:
                await ItemInstance.add_item(uow.session, player_id, item_config.item_id, quantity)
            except ValueError as e:
                # 背包空间不足
                await buy_gift_cmd.finish(message_add_head(f"❌ 背包已满，无法购买", event))

            # 更新每日购买记录
            if daily_limit > 0:
                update_daily_gift_purchase(player, item_config.item_id, quantity)

            # 提交事务
            await uow.commit()

            # 获取剩余购买次数
            remaining = daily_limit - get_today_purchase_count(player, item_config.item_id) if daily_limit > 0 else "无限制"

            # 返回成功消息
            message = f"""✅ 购买成功！
━━━━━━━━━━━━━
物品: {item_config.name}
数量: {quantity}
单价: {item_config.price}金币
总价: {total_price}金币
好感度: +{item_config.favorability} (每个)
今日剩余: {remaining if isinstance(remaining, int) else f"{remaining}个"}

💡 使用【赠礼 UID {item_config.name}】赠送礼物"""

            await buy_gift_cmd.finish(message_add_head(message, event))
    except FinishedException:
        raise
    except ValueError as e:
        from nonebot import logger
        logger.error(f"买礼物命令处理失败: {e}", exc_info=True)
        await buy_gift_cmd.finish(message_add_head(f"❌ 购买失败: {str(e)}", event))
