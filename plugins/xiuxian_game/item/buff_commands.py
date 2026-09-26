"""
临时buff系统命令模块

提供临时buff相关的用户交互命令：
1. 查看临时buff状态
2. 清理过期buff
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from .item_effects import get_player_buff_status

# ---------------- 指令：查看临时buff状态 ----------------
buff_status_cmd = on_command("增益状态", aliases={"buff状态", "临时增益", "增益", "buff"}, block=True, priority=9)

@buff_status_cmd.handle()
async def handle_buff_status(event: MessageEvent):
    """查看玩家的临时buff状态"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        player = await require_player(session, event, buff_status_cmd)
        
        status_msg = await get_player_buff_status(session, player)
        await session.commit()  # 提交清理过期buff的操作
        
        buttons = f"\n***\n{cmd('清理增益')} | {cmd('面板')} | {cmd('属性分解')}"
        await buff_status_cmd.finish(build_markdown(status_msg + buttons))


# ---------------- 指令：清理过期buff ----------------
clear_buffs_cmd = on_command("清理增益", aliases={"清理buff", "清理过期增益"}, block=True, priority=9)

@clear_buffs_cmd.handle()
async def handle_clear_buffs(event: MessageEvent):
    """手动清理过期的buff"""
    from ..platform_utils import require_player

    async with safe_session() as session:
        player = await require_player(session, event, clear_buffs_cmd)
        
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
        
        buttons = f"\n***\n{cmd('增益状态')} | {cmd('面板')}"
        await clear_buffs_cmd.finish(build_markdown(msg + buttons))


# ---------------- 指令：详细属性分解 ----------------
attribute_breakdown_cmd = on_command("属性分解", aliases={"属性详情", "属性来源"}, block=True, priority=9)

def format_attribute_breakdown(breakdown: dict, battle_rows: dict) -> list[str]:
    """按同一套来源解释基础属性与战斗属性，保留负数和小数。"""
    from ..battle.attribute_summary import (
        MAIN_ATTRIBUTE_NAMES, format_attribute_value, format_battle_attribute_line,
    )
    sources = (
        ("base", "基础"), ("permanent", "丹药/奖励"),
        ("vip_equipment", "VIP成长"), ("equipment", "装备含宝石"),
        ("pet", "伙伴"), ("temporary", "临时"),
    )

    def source_text(name: str, row: dict | None = None) -> str:
        parts = []
        for key, label in sources:
            value = breakdown.get(key, {}).get(name, 0)
            if value:
                parts.append(f"{label}{format_attribute_value(value)}")
        if row:
            for key, label in (("affix", "词缀"), ("set", "套装"), ("level", "等级")):
                if row.get(key):
                    parts.append(f"{label}{format_attribute_value(row[key])}")
        return "、".join(parts) or "暂无加成"

    lines = [
        "> 基础包含初始、加点及历史未归类部分；丹药/奖励含洗髓变动与本轮烹饪幸运。",
        "", "**基础属性**",
    ]
    for name, label in MAIN_ATTRIBUTE_NAMES.items():
        total = format_attribute_value(breakdown["total"][name])
        lines.extend([f"{label}：**{total}**", f"来源：{source_text(name)}"])
    lines.extend(["", "**战斗属性**", "> 生效值已应用属性上限，尚未扣除对手抗性。"])
    for name, row in battle_rows.items():
        lines.extend([format_battle_attribute_line(name, row), f"来源：{source_text(name, row)}"])
    lines.extend([
        "", "> 装备项包含对加点、丹药与VIP成长的比例放大；伙伴和临时增益在装备之后相加。",
        "> 溢出部分不进入当前开战数值；命中、暴击超过100%仍可能用于抵消对手闪避、抗暴。",
        "> 铭文、体质与装备触发效果另在战斗中结算，不计入这里的来源总和。",
    ])
    return lines


@attribute_breakdown_cmd.handle()
async def handle_attribute_breakdown(event: MessageEvent):
    """显示包括词缀、套装与硬上限溢出的属性来源。"""
    from ..platform_utils import require_player
    from ..battle.attribute_summary import get_battle_attribute_summary, format_attribute_value
    from ..infrastructure.repositories.item_repository import ItemRepository
    from .equipment_service import EQUIP_ITEM_IDS

    async with safe_session() as session:
        player = await require_player(session, event, attribute_breakdown_cmd)
        breakdown = await player.get_attribute_breakdown(session)
        equipped = await ItemRepository(session).get_equipped_equipment(player.id, EQUIP_ITEM_IDS)
        battle_rows = await get_battle_attribute_summary(
            player, session, effective_attrs=breakdown["total"], equipped_items=equipped,
        )
        lines = [f"# 📊 {player.nickname} 的属性分解"]
        lines.extend(format_attribute_breakdown(breakdown, battle_rows))

        # 展示装备的直接比例合计；不将生命/攻击转换特效误计为同属性倍率。
        ratios = {}
        key_map = {"hp": "max_hp", "mp": "max_mp"}
        for eq in equipped:
            for name, value in (eq.config.attr_ratio or {}).items():
                key = key_map.get(name, name)
                ratios[key] = ratios.get(key, 0) + float(value) * eq.get_upgrade_bonus_multiplier()
        if ratios:
            from ..battle.attribute_summary import MAIN_ATTRIBUTE_NAMES
            lines.extend(["", "**当前装备的基底放大**"])
            for name, label in MAIN_ATTRIBUTE_NAMES.items():
                if ratios.get(name):
                    ratio = format_attribute_value(ratios[name] * 100)
                    lines.append(f"{label}基底：装备额外提供{ratio}%（已含升阶）")
            lines.append("> 每件装备都以同一份加点、丹药、VIP成长计算比例；各件比例相加。生命/理智转换特效另计。")

        if any(breakdown.get("pet", {}).values()):
            from ..models.pet_instance import PetInstance
            from ..pet.config import PetConfigManager
            stmt = select(PetInstance).where(
                PetInstance.player_id == player.id, PetInstance.is_active == True,
            )
            pet = (await session.execute(stmt)).scalars().first()
            if pet:
                mood_mult = PetConfigManager().get_mood_multiplier(pet.mood)
                lines.extend([
                    "", f"🐾 {pet.nickname or '伙伴'}：心情{pet.mood}/100，等级属性倍率{mood_mult:.1f}倍",
                    "> 饰品加成不受心情倍率影响。",
                ])
        if any(breakdown["temporary"].values()):
            from ..models.temporary_buff import TemporaryBuff
            active_buffs = await TemporaryBuff.get_active_buffs(session, player.id)
            lines.extend(["", "**当前临时增益**"])
            for buff in active_buffs:
                lines.append(f"{buff.buff_name}（剩余{buff.get_remaining_minutes()}分钟）")
        lines.extend(["***", f"{cmd('战力')} | {cmd('战力说明')} | {cmd('冥返信息')} | {cmd('增益状态')}"])
        message = build_markdown("\n".join(lines))
    await attribute_breakdown_cmd.finish(message)


# ---------------- 指令：一键嗑药 ----------------
auto_use_medicine_cmd = on_command("一键嗑药", aliases={"一键磕药", "自动嗑药"}, block=True, priority=9)

@auto_use_medicine_cmd.handle()
async def handle_auto_use_medicine(event: MessageEvent):
    """一键嗑药 - 自动使用适量的回春散和凝神草补满血量和法力值"""
    from sqlalchemy import select
    from ..models.inventory import ItemInstance
    from ..config import config
    from .item_effects import apply_effect

    async with safe_session() as session:
        from ..platform_utils import require_player
        player = await require_player(session, event, auto_use_medicine_cmd)

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

        # 恢复量以物品配置为准，避免与 items.yaml 脱节导致多嗑
        heal_value = int((config.items_config["by_id"]["heal_potion"].effect_params or {}).get("value", 50))
        herb_value = int((config.items_config["by_id"]["spirit_herb"].effect_params or {}).get("value", 50))
        heal_potion_needed = min((hp_needed + heal_value - 1) // heal_value, heal_potion_count) if hp_needed > 0 else 0
        spirit_herb_needed = min((mp_needed + herb_value - 1) // herb_value, spirit_herb_count) if mp_needed > 0 else 0

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
                total_hp_restored = min(heal_potion_needed * heal_value, hp_needed)

        if spirit_herb_needed > 0:
            success, _ = await apply_effect(player, config.items_config["by_id"]["spirit_herb"], spirit_herb_needed, ctx="world", session=session)
            if success:
                await ItemInstance.consume_item(session, player.id, "spirit_herb", spirit_herb_needed)
                used_items.append(f"凝神草*{spirit_herb_needed}")
                total_mp_restored = min(spirit_herb_needed * herb_value, mp_needed)

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
        result_msg.append(f"{cmd('面板')} | {cmd('背包')}")
        await auto_use_medicine_cmd.finish(build_markdown("\n".join(result_msg)))
