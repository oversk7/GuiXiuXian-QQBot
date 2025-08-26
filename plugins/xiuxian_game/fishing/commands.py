"""钓鱼系统指令处理器

实现钓鱼相关的用户交互界面
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta

from ..models.db import safe_session
from ..models.fishing_record import FishingRecord, FishingStats
from ..models.inventory import ItemInstance
from ..utils import message_add_head
from ..config import config
from .service import FishingService


# 钓鱼指令
fishing_cmd = on_command("钓鱼", block=True, priority=5)

@fishing_cmd.handle()
async def _(event: MessageEvent):
    """钓鱼指令处理"""
    async with safe_session() as session:
        try:
            # 使用跨平台工具获取玩家数据
            from ..platform_utils import get_unified_player, is_guild_message
            player = await get_unified_player(session, event)
            if not player:
                if is_guild_message(event):
                    await fishing_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
                else:
                    await fishing_cmd.finish("⛔ 请先创建角色")

            # 执行钓鱼
            result = await FishingService.do_fishing(session, player)

            if not result["success"]:
                await fishing_cmd.finish(message_add_head(result["message"], event))
        except TypeError as e:
            if "unsupported operand type(s) for +=: 'NoneType' and 'int'" in str(e):
                await fishing_cmd.finish(message_add_head("⛔ 钓鱼数据异常，请联系管理员处理", event))
            else:
                raise
        
        # 构建成功消息
        rarity_emoji = {
            "white": "⚪",
            "green": "🟢", 
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠"
        }
        
        emoji = rarity_emoji.get(result["rarity"], "⚪")
        
        # 根据稀有度显示不同的祝贺信息
        if result["rarity"] == "orange":
            celebration = "🎉✨ 传说级收获！！！ ✨🎉"
        elif result["rarity"] == "purple":
            celebration = "🎊 稀有鱼类！！ 🎊"
        elif result["rarity"] == "blue":
            celebration = "🌟 优质鱼类！ 🌟"
        else:
            celebration = "🎣 钓鱼成功！"
        
        quantity_text = f"×{result['quantity']}" if result['quantity'] > 1 else ""
        
        message = (
            f"{celebration}\n"
            f"━━━━━━━━━━━━━\n"
            f"🐟 {emoji}{result['fish_name']}{quantity_text}\n"
            f"💰 价值：{result['value']} 金币\n"
            f"━━━━━━━━━━━━━\n"
            f"🎣 继续钓鱼需等待 {FishingService.FISHING_COOLDOWN} 分钟"
        )
        
        await fishing_cmd.finish(message_add_head(message, event))


# 钓鱼记录指令
fishing_record_cmd = on_command("钓鱼记录", aliases={"我的钓鱼"}, block=True, priority=5)

@fishing_record_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """查看钓鱼记录"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await fishing_record_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await fishing_record_cmd.finish("⛔ 请先创建角色")

        # 获取钓鱼统计
        stats = await FishingRecord.get_player_fishing_stats(session, player.id)
        
        # 获取最近钓鱼记录
        recent_records = await FishingRecord.get_recent_fishing_records(session, player.id, 5)
        
        lines = [
            "🎣 钓鱼记录",
            "━━━━━━━━━━━━━",
            f"📊 总钓鱼次数：{stats['total_fishing_count']}",
            f"🐟 总钓鱼数量：{stats['total_fish_caught']}",
            f"📅 今日钓鱼：{stats['today_fishing_count']}/{FishingService.DAILY_FISHING_LIMIT}",
            "━━━━━━━━━━━━━"
        ]
        
        if recent_records:
            lines.append("🕐 最近记录：")
            for record in recent_records:
                fish_config = config.items_config["by_id"].get(record.fish_id)
                if fish_config:
                    rarity_display = fish_config.get_rarity_display()
                    quantity_text = f"×{record.quantity}" if record.quantity > 1 else ""
                    time_str = record.fishing_time.strftime("%m-%d %H:%M")
                    lines.append(f"  {rarity_display}{fish_config.name}{quantity_text} ({time_str})")
        else:
            lines.append("📝 暂无钓鱼记录")
        
        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 使用【钓鱼】开始钓鱼")
        
        await fishing_record_cmd.finish(message_add_head("\n".join(lines), event))


# 钓鱼排行榜指令
fishing_leaderboard_cmd = on_command("钓鱼排行", aliases={"钓鱼榜"}, block=True, priority=5)

@fishing_leaderboard_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼排行榜"""
    async with safe_session() as session:
        leaderboard = await FishingService.get_fishing_leaderboard(session, 10)
        
        if not leaderboard:
            await fishing_leaderboard_cmd.finish(message_add_head("📊 暂无钓鱼排行数据", event))
        
        lines = [
            "🏆 钓鱼排行榜（按总价值）",
            "━━━━━━━━━━━━━"
        ]
        
        for i, player_data in enumerate(leaderboard, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

            lines.append(
                f"{medal} {player_data['nickname']}(UID:{player_data['uid']})\n"
                f"   💰 总价值：{player_data['total_fish_value']}\n"
                f"   🎣 钓鱼次数：{player_data['total_fishing_count']}\n"
                f"   🐟 鱼类数量：{player_data['total_fish_caught']}"
            )
            
            if player_data['legendary_fish_caught'] > 0:
                lines.append(f"   🟠 传说鱼类：{player_data['legendary_fish_caught']}")
            if player_data['rare_fish_caught'] > 0:
                lines.append(f"   🟣 稀有鱼类：{player_data['rare_fish_caught']}")
            
            lines.append("──────────")
        
        lines.append("💡 使用【钓鱼】参与排行")
        
        await fishing_leaderboard_cmd.finish(message_add_head("\n".join(lines), event))


# 钓鱼状态指令
fishing_status_cmd = on_command("钓鱼状态", block=True, priority=5)

@fishing_status_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼状态"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await fishing_status_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await fishing_status_cmd.finish("⛔ 请先创建角色")

        # 检查钓鱼状态
        can_fish, reason = await FishingService.can_fishing(session, player)
        
        # 获取统计信息
        stats = await FishingRecord.get_player_fishing_stats(session, player.id)
        
        # 获取钓鱼统计记录
        fishing_stats = await FishingStats.get_or_create(session, player.id)
        
        lines = [
            "🎣 钓鱼状态",
            "━━━━━━━━━━━━━"
        ]
        
        if can_fish:
            lines.append("✅ 可以钓鱼")
        else:
            lines.append(f"⏰ {reason}")
        
        lines.extend([
            f"📅 今日钓鱼：{stats['today_fishing_count']}/{FishingService.DAILY_FISHING_LIMIT}",
            f"🎣 总钓鱼次数：{stats['total_fishing_count']}",
            f"🐟 总鱼类数量：{stats['total_fish_caught']}",
            f"💰 总鱼类价值：{fishing_stats.total_fish_value}",
            "━━━━━━━━━━━━━"
        ])
        
        if fishing_stats.rare_fish_caught > 0:
            lines.append(f"🟣 稀有鱼类：{fishing_stats.rare_fish_caught}")
        if fishing_stats.legendary_fish_caught > 0:
            lines.append(f"🟠 传说鱼类：{fishing_stats.legendary_fish_caught}")
        if fishing_stats.best_fish_value > 0:
            lines.append(f"🏆 最贵单鱼：{fishing_stats.best_fish_value} 金币")
        
        lines.extend([
            "━━━━━━━━━━━━━",
            f"🍀 运气值：{player.luck}（影响稀有鱼概率）",
            "💡 运气值越高，钓到稀有鱼的概率越大"
        ])
        
        await fishing_status_cmd.finish(message_add_head("\n".join(lines), event))


# 钓鱼图鉴指令
fishing_guide_cmd = on_command("钓鱼图鉴", aliases={"鱼类图鉴"}, block=True, priority=5)

@fishing_guide_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼图鉴"""
    lines = [
        "📖 钓鱼图鉴",
        "━━━━━━━━━━━━━",
        "🎣 钓鱼系统说明：",
        "• 随时随地可以钓鱼，方便新手",
        f"• 每次钓鱼冷却时间：{FishingService.FISHING_COOLDOWN}分钟",
        f"• 每日钓鱼次数限制：{FishingService.DAILY_FISHING_LIMIT}次",
        "• 运气值影响稀有鱼概率和数量",
        "• 运气加成采用平衡曲线，保持稀缺性",
        "━━━━━━━━━━━━━",
        "🐟 鱼类稀有度：",
        "⚪ 普通（60%）- 鲤鱼、鲫鱼、草鱼等",
        "🟢 优良（25%）- 鲈鱼、桂鱼、黄花鱼等", 
        "🔵 精品（12%）- 三文鱼、金枪鱼、石斑鱼等",
        "🟣 稀有（2.5%）- 中华鲟、龙鱼等",
        "🟠 传说（0.5%）- 金龙鱼、凤凰鱼等",
        "━━━━━━━━━━━━━",
        "💰 鱼类用途：",
        "• 可在海洋城市舟山(200,-200)出售给商人",
        "• 稀有鱼类价值更高",
        "• 参与钓鱼排行榜竞争",
        "• 使用【丢弃】指令放生鱼类，获得功德（娱乐效果）",
        "━━━━━━━━━━━━━",
        "📋 相关指令：",
        "【钓鱼】- 开始钓鱼",
        "【钓鱼记录】- 查看钓鱼记录",
        "【钓鱼状态】- 查看当前状态",
        "【钓鱼排行】- 查看排行榜",
        "【吃鱼】- 品尝鱼类美味（娱乐功能）"
    ]
    
    await fishing_guide_cmd.finish(message_add_head("\n".join(lines), event))


# 吃鱼指令（娱乐功能，实际为丢弃）
eat_fish_cmd = on_command("吃鱼", aliases={"吃掉鱼", "品尝鱼"}, block=True, priority=5)

@eat_fish_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """吃鱼指令（实际为丢弃鱼类物品）

    用法：吃鱼 [鱼类名称] [数量]
    示例：吃鱼 鲤鱼 2
    """
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await eat_fish_cmd.finish("⛔ 格式错误，正确格式：吃鱼 [鱼类名称] [数量]")

    fish_name, qty_str = params

    # 参数校验
    try:
        quantity = int(qty_str)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await eat_fish_cmd.finish("⛔ 数量必须为正整数")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await eat_fish_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await eat_fish_cmd.finish("⛔ 请先创建角色")

        # 通过名称查找鱼类物品
        fish_config = config.items_config["by_name"].get(fish_name)
        if not fish_config:
            await eat_fish_cmd.finish(f"⛔ 不存在鱼类：{fish_name}")

        # 检查是否为鱼类物品（通过item_id判断）
        # 所有鱼类物品都在钓鱼系统的鱼类列表中
        from .service import FishingService
        all_fish_ids = []
        for rarity_config in FishingService.FISH_RARITY_CONFIG.values():
            all_fish_ids.extend(rarity_config["fish_list"])

        if fish_config.item_id not in all_fish_ids:
            await eat_fish_cmd.finish(f"⛔ {fish_name} 不是鱼类，无法食用")

        # 检查背包中是否有该鱼类
        from sqlalchemy import select
        inv_rows = (await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
            .where(ItemInstance.item_id == fish_config.item_id)
        )).scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)

        if total_qty < quantity:
            await eat_fish_cmd.finish(f"⛔ {fish_name} 数量不足，你只有 {total_qty} 条")

        try:
            # 消耗鱼类物品（实际为丢弃）
            await ItemInstance.consume_item(session, player.id, fish_config.item_id, quantity)
            await session.commit()
        except ValueError as e:
            await eat_fish_cmd.finish(f"⛔ 食用失败：{e}")

        # 根据鱼类稀有度显示不同的食用效果
        rarity_emoji = {
            "white": "⚪",
            "green": "🟢",
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠"
        }

        emoji = rarity_emoji.get(fish_config.rarity, "⚪")
        quantity_text = f"{quantity}条" if quantity > 1 else "1条"

        # 根据稀有度显示不同的食用体验
        if fish_config.rarity == "orange":
            taste_desc = "🌟 传说级的美味！仿佛整个人都被神圣的光芒包围，这味道简直是天界的馈赠！"
            effect_desc = "✨ 你感到体内涌起一股神秘的力量，仿佛连灵魂都得到了升华！"
        elif fish_config.rarity == "purple":
            taste_desc = "🎊 稀有的珍馐！肉质鲜美至极，每一口都是极致的享受！"
            effect_desc = "💫 你感到精神焕发，仿佛获得了某种特殊的力量！"
        elif fish_config.rarity == "blue":
            taste_desc = "🌟 优质的美味！肉质紧实鲜甜，让人回味无穷！"
            effect_desc = "😋 你感到心情愉悦，身体也变得轻盈了一些！"
        elif fish_config.rarity == "green":
            taste_desc = "😋 不错的味道！肉质鲜美，营养丰富！"
            effect_desc = "🍽️ 你感到饱腹感十足，精神也好了不少！"
        else:  # white
            taste_desc = "🐟 普通的鱼肉，但也算是不错的一餐！"
            effect_desc = "😊 你填饱了肚子，感觉还不错！"

        message = (
            f"🍽️ 美食品尝\n"
            f"━━━━━━━━━━━━━\n"
            f"🐟 品尝了 {emoji}{fish_name} ×{quantity_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"{taste_desc}\n"
            f"{effect_desc}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 虽然只是品尝，但这份美味永远留在了记忆中！"
        )

        await eat_fish_cmd.finish(message_add_head(message, event))
