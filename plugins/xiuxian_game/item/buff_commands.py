"""
临时buff系统命令模块

提供临时buff相关的用户交互命令：
1. 查看临时buff状态
2. 清理过期buff
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..models.db import safe_session
from ..models import Player
from ..utils import message_add_head
from .item_effects import get_player_buff_status

# ---------------- 指令：查看临时buff状态 ----------------
buff_status_cmd = on_command("增益状态", aliases={"buff状态", "临时增益", "增益", "buff"}, block=True, priority=5)

@buff_status_cmd.handle()
async def handle_buff_status(event: MessageEvent):
    """查看玩家的临时buff状态"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await buff_status_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await buff_status_cmd.finish("⛔ 请先创建角色")
        
        status_msg = await get_player_buff_status(session, player)
        await session.commit()  # 提交清理过期buff的操作
        
        await buff_status_cmd.finish(message_add_head(status_msg, event))


# ---------------- 指令：清理过期buff ----------------
clear_buffs_cmd = on_command("清理增益", aliases={"清理buff", "清理过期增益"}, block=True, priority=5)

@clear_buffs_cmd.handle()
async def handle_clear_buffs(event: MessageEvent):
    """手动清理过期的buff"""
    from ..platform_utils import get_unified_player

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await clear_buffs_cmd.finish("⛔ 请先创建角色")
        
        from ..models.temporary_buff import TemporaryBuff
        
        # 获取清理前的buff数量
        active_buffs_before = await TemporaryBuff.get_active_buffs(session, player.id)
        count_before = len(active_buffs_before)
        
        # 清理过期buff
        await TemporaryBuff.cleanup_expired_buffs(session, player.id)
        await session.commit()
        
        # 获取清理后的buff数量
        active_buffs_after = await TemporaryBuff.get_active_buffs(session, player.id)
        count_after = len(active_buffs_after)
        
        cleared_count = count_before - count_after
        
        if cleared_count > 0:
            msg = f"🧹 已清理 {cleared_count} 个过期的临时增益效果"
            if count_after > 0:
                msg += f"\n✨ 剩余 {count_after} 个有效增益"
        else:
            msg = "✅ 没有发现过期的临时增益效果"
        
        await clear_buffs_cmd.finish(message_add_head(msg, event))


# ---------------- 指令：详细属性分解 ----------------
attribute_breakdown_cmd = on_command("属性分解", aliases={"属性详情", "属性来源"}, block=True, priority=5)

@attribute_breakdown_cmd.handle()
async def handle_attribute_breakdown(event: MessageEvent):
    """显示玩家属性的详细分解信息"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await attribute_breakdown_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await attribute_breakdown_cmd.finish("⛔ 请先创建角色")

        breakdown = await player.get_attribute_breakdown(session)

        # 属性名称映射
        attr_names = {
            "max_hp": "最大生命",
            "max_mp": "最大理智",
            "attack": "攻击力",
            "defense": "防御力",
            "agility": "敏捷",
            "luck": "运气",
            "critical_rate": "暴击率",
            "critical_power": "暴击力",
            "combo_rate": "连击率",
            "counter_rate": "反击率",
            "dodge_rate": "闪避率",
            "accuracy_rate": "命中率",
            "skill_crit_rate": "灵爆率",
            "penetration_rate": "穿透率",
            "anti_crit_rate": "抗暴率"
        }

        lines = [
            f"📊 {player.nickname} 的属性分解",
            "━━━━━━━━━━━━━",
            "💡 基础 = 当前总值 - 所有加成"
        ]

        # 显示主要属性的分解
        main_attrs = ["max_hp", "max_mp", "attack", "defense", "agility", "luck"]

        for attr in main_attrs:
            attr_name = attr_names.get(attr, attr)
            base = breakdown["base"][attr]
            equipment = breakdown["equipment"][attr]
            elixir = breakdown["elixir"][attr]
            vip_equipment = breakdown["vip_equipment"][attr]
            temporary = breakdown["temporary"][attr]
            total = breakdown["total"][attr]

            # 构建显示字符串
            parts = [f"基础{base}"]
            if equipment > 0:
                parts.append(f"装备+{equipment}")
            if elixir > 0:
                parts.append(f"丹药+{elixir}")
            if vip_equipment > 0:
                parts.append(f"特殊装备+{vip_equipment}")
            if temporary > 0:
                parts.append(f"临时+{temporary}")
            elif temporary < 0:
                parts.append(f"临时{temporary}")

            detail = " + ".join(parts) if len(parts) > 1 else parts[0]
            lines.append(f"🔸 {attr_name}: {total} ({detail})")

        # 显示战斗属性（只显示总值，不分解来源，因为主要来自镶嵌宝石）
        battle_attrs = ["critical_rate", "critical_power", "combo_rate", "counter_rate",
                       "dodge_rate", "accuracy_rate", "skill_crit_rate", "penetration_rate", "anti_crit_rate"]

        has_battle_attrs = False
        battle_lines = []

        for attr in battle_attrs:
            total = breakdown["total"][attr]
            # 只显示非零的战斗属性
            if total != 0:
                has_battle_attrs = True
                attr_name = attr_names.get(attr, attr)
                battle_lines.append(f"🔸 {attr_name}: {total}")

        if has_battle_attrs:
            lines.append("")
            lines.append("⚔️ 战斗属性:")
            lines.extend(battle_lines)

        # 显示临时buff状态
        if any(breakdown["temporary"].values()):
            lines.append("")
            lines.append("✨ 当前临时增益:")
            from ..models.temporary_buff import TemporaryBuff
            active_buffs = await TemporaryBuff.get_active_buffs(session, player.id)
            for buff in active_buffs:
                remaining = buff.get_remaining_minutes()
                lines.append(f"  • {buff.buff_name} (剩余{remaining}分钟)")
            lines.append("  ⏰ 临时增益激活时，基础值会相应减少")

        lines.append("")
        lines.append("💡 提示：使用【增益状态】查看临时增益详情")
        lines.append("💡 基础属性 = Player表存储值 + 永久丹药加成")

        # 检查是否有严重异常的基础属性（负值且没有临时buff）
        has_abnormal_base = False
        for attr in main_attrs:
            if breakdown["base"][attr] < 0 and breakdown["temporary"][attr] == 0:
                has_abnormal_base = True
                break

        if has_abnormal_base:
            lines.append("")
            lines.append("⚠️ 检测到基础属性异常，建议联系管理员处理")

        await attribute_breakdown_cmd.finish(message_add_head("\n".join(lines), event))
