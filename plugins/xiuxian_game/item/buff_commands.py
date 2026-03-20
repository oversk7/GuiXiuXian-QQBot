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
            "💡 基础 = 初始值 + 加点分配"
        ]

        # 显示主要属性的分解
        main_attrs = ["max_hp", "max_mp", "attack", "defense", "agility", "luck"]

        for attr in main_attrs:
            attr_name = attr_names.get(attr, attr)
            base = breakdown["base"][attr]
            equipment = breakdown["equipment"][attr]
            elixir = breakdown["elixir"][attr]
            vip_equipment = breakdown["vip_equipment"][attr]
            reforge = breakdown["reforge"][attr]
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
            if reforge < 0:
                parts.append(f"洗髓{reforge}")
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

        lines.append("")
        lines.append("💡 提示：使用【增益状态】查看临时增益详情")
        lines.append("💡 总属性 = 基础 + 装备 + 丹药 + VIP装备 + 临时增益")

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


# ---------------- 指令：一键嗑药 ----------------
auto_use_medicine_cmd = on_command("一键嗑药", aliases={"一键磕药", "自动嗑药"}, block=True, priority=5)

@auto_use_medicine_cmd.handle()
async def handle_auto_use_medicine(event: MessageEvent):
    """一键嗑药 - 自动使用适量的回春散和凝神草补满血量和法力值"""
    from sqlalchemy import select
    from ..models.inventory import ItemInstance
    from ..config import config
    from .item_effects import apply_effect

    async with safe_session() as session:
        from ..platform_utils import get_unified_player
        player = await get_unified_player(session, event)
        if not player:
            await auto_use_medicine_cmd.finish("⛔ 请先创建角色")

        if player.hp <= 0:
            await auto_use_medicine_cmd.finish(message_add_head(
                "💀 你已经死亡，无法使用药品，请先复活", event
            ))

        effective_attrs = await player.get_effective_attributes(session)
        effective_max_hp = effective_attrs.get("max_hp", player.max_hp)
        effective_max_mp = effective_attrs.get("max_mp", player.max_mp)
        current_hp = min(player.hp, effective_max_hp)
        current_mp = min(player.mp, effective_max_mp)

        hp_needed = max(0, effective_max_hp - current_hp)
        mp_needed = max(0, effective_max_mp - current_mp)

        if hp_needed <= 0 and mp_needed <= 0:
            await auto_use_medicine_cmd.finish(message_add_head(
                "✨ 你的血量和法力值都已满，无需嗑药", event
            ))

        heal_potions = (await session.execute(
            select(ItemInstance).where(ItemInstance.player_id == player.id, ItemInstance.item_id == "heal_potion")
        )).scalars().all()
        heal_potion_count = sum(i.quantity for i in heal_potions)

        spirit_herbs = (await session.execute(
            select(ItemInstance).where(ItemInstance.player_id == player.id, ItemInstance.item_id == "spirit_herb")
        )).scalars().all()
        spirit_herb_count = sum(i.quantity for i in spirit_herbs)

        heal_potion_needed = min((hp_needed + 39) // 40, heal_potion_count) if hp_needed > 0 else 0
        spirit_herb_needed = min((mp_needed + 39) // 40, spirit_herb_count) if mp_needed > 0 else 0

        if heal_potion_needed == 0 and spirit_herb_needed == 0:
            missing = []
            if hp_needed > 0:
                missing.append("回春散")
            if mp_needed > 0:
                missing.append("凝神草")
            await auto_use_medicine_cmd.finish(message_add_head(
                f"⛔ 背包中没有足够的药品：{' 和 '.join(missing)}", event
            ))

        used_items = []
        total_hp_restored = 0
        total_mp_restored = 0

        if heal_potion_needed > 0:
            success, _ = await apply_effect(player, config.items_config["by_id"]["heal_potion"], heal_potion_needed, ctx="world", session=session)
            if success:
                await ItemInstance.consume_item(session, player.id, "heal_potion", heal_potion_needed)
                used_items.append(f"回春散*{heal_potion_needed}")
                total_hp_restored = min(heal_potion_needed * 40, hp_needed)

        if spirit_herb_needed > 0:
            success, _ = await apply_effect(player, config.items_config["by_id"]["spirit_herb"], spirit_herb_needed, ctx="world", session=session)
            if success:
                await ItemInstance.consume_item(session, player.id, "spirit_herb", spirit_herb_needed)
                used_items.append(f"凝神草*{spirit_herb_needed}")
                total_mp_restored = min(spirit_herb_needed * 40, mp_needed)

        if not used_items:
            await auto_use_medicine_cmd.finish(message_add_head("⛔ 药品使用失败，请重试", event))

        session.add(player)
        await session.commit()

        result_msg = ["💊 一键嗑药完成", "━━━━━━━━━━━━━", f"🎯 使用药品：{' + '.join(used_items)}"]
        if total_hp_restored > 0:
            result_msg.append(f"❤️ 恢复生命值：{total_hp_restored}")
        if total_mp_restored > 0:
            result_msg.append(f"💙 恢复法力值：{total_mp_restored}")
        result_msg.extend([
            f"📊 当前状态：{min(player.hp, effective_max_hp)}/{effective_max_hp} HP | {min(player.mp, effective_max_mp)}/{effective_max_mp} MP",
            "━━━━━━━━━━━━━"
        ])
        await auto_use_medicine_cmd.finish(message_add_head("\n".join(result_msg), event))
