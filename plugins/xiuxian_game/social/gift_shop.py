"""
礼物商店系统

提供直接购买好感度礼物的功能,无需NPC交互
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..models.inventory import ItemType
from ..utils import message_add_head
from ..config import config

# 创建命令
gift_shop_cmd = on_command("礼物商店", aliases={"礼物店", "礼品店"}, priority=5, block=True)
buy_gift_cmd = on_command("买礼物", aliases={"购买礼物"}, priority=5, block=True)


# 礼物商店菜单
async def get_gift_shop_menu() -> str:
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
        "🎁 礼物商店 🎁",
        "━━━━━━━━━━━━━",
        "这里是购买好感度礼物的地方",
        "",
        "📜 使用方法:",
        "【买礼物 <礼物名> [数量]】",
        "示例: 买礼物 红玫瑰 10",
        "",
        "💝 礼物列表:"
    ]

    for rarity in rarity_order:
        if rarity not in rarity_groups:
            continue

        lines.append(f"\n{rarity_names[rarity]}")

        # 按价格排序
        items = sorted(rarity_groups[rarity], key=lambda x: x.price)

        for item in items:
            lines.append(
                f"  • {item.name} - {item.price}金币 (好感+{item.favorability})"
            )

    lines.extend([
        "",
        "━━━━━━━━━━━━━",
        "💡 提示:",
        "• 使用【赠礼 UID 礼物名】赠送礼物增加好感度",
        "• 不同品质的礼物增加的好感度不同",
        "• 礼物也可以通过【转移】当面赠送(不加好感)"
    ])

    return "\n".join(lines)


@gift_shop_cmd.handle()
async def handle_gift_shop(event: MessageEvent, args: Message = CommandArg()):
    """礼物商店命令 - 显示可购买的礼物列表"""
    menu = await get_gift_shop_menu()
    await gift_shop_cmd.finish(message_add_head(menu, event))


@buy_gift_cmd.handle()
async def handle_buy_gift(event: MessageEvent, args: Message = CommandArg()):
    """
    买礼物命令 - 购买好感度礼物

    语法: 买礼物 <礼物名> [数量]

    示例:
    - 买礼物 红玫瑰
    - 买礼物 钻戒 3
    """
    try:
        # 1. 获取玩家ID
        player_id = event.get_user_id()

        # 2. 解析参数
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

        # 5. 计算总价
        total_price = item_config.price * quantity

        # 6. 执行购买
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 获取玩家
            player = await uow.players.get_by_id(player_id)
            if not player:
                await buy_gift_cmd.finish(message_add_head("⛔ 请先创建角色", event))

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

            # 提交事务
            await uow.commit()

            # 返回成功消息
            message = f"""✅ 购买成功！
━━━━━━━━━━━━━
物品: {item_config.name}
数量: {quantity}
单价: {item_config.price}金币
总价: {total_price}金币
好感度: +{item_config.favorability} (每个)

💡 使用【赠礼 UID {item_config.name}】赠送礼物"""

            await buy_gift_cmd.finish(message_add_head(message, event))

    except FinishedException:
        raise
    except Exception as e:
        from nonebot import logger
        logger.error(f"买礼物命令处理失败: {e}", exc_info=True)
        await buy_gift_cmd.finish(message_add_head(f"❌ 购买失败: {str(e)}", event))
