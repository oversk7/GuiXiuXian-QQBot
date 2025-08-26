"""钓鱼系统指令处理器

实现钓鱼相关的用户交互界面
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta

from ..models.db import safe_session
from ..models.fishing_record import FishingRecord, FishingStats
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
                f"{medal} {player_data['nickname']}\n"
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
        "━━━━━━━━━━━━━",
        "📋 相关指令：",
        "【钓鱼】- 开始钓鱼",
        "【钓鱼记录】- 查看钓鱼记录",
        "【钓鱼状态】- 查看当前状态",
        "【钓鱼排行】- 查看排行榜"
    ]
    
    await fishing_guide_cmd.finish(message_add_head("\n".join(lines), event))
