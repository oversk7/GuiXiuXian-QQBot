"""
属性修复工具
用于修复基础属性为负数的问题
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.permission import SUPERUSER
from sqlalchemy import select
from ..models.db import safe_session
from ..models.player import Player
from ..models.elixir_usage import ElixirUsageLog
from ..models.inventory import ItemInstance
from ..utils import message_add_head

# 管理员专用指令
diagnose_attributes = on_command("诊断属性", permission=SUPERUSER, block=True, priority=1)
fix_attributes = on_command("修复属性", permission=SUPERUSER, block=True, priority=1)
safe_fix_attributes = on_command("安全修复属性", permission=SUPERUSER, block=True, priority=1)

@diagnose_attributes.handle()
async def handle_diagnose_attributes(event: MessageEvent):
    """诊断玩家属性问题"""
    async with safe_session() as session:
        # 获取所有玩家
        stmt = select(Player)
        players = (await session.execute(stmt)).scalars().all()
        
        problem_players = []
        total_players = len(players)
        
        for player in players:
            try:
                breakdown = await player.get_attribute_breakdown(session)
                
                # 检查基础属性是否有负数
                negative_attrs = []
                for attr, value in breakdown["base"].items():
                    if value < 0:
                        negative_attrs.append(f"{attr}:{value}")
                
                if negative_attrs:
                    problem_players.append({
                        "uid": player.uid,
                        "nickname": player.nickname,
                        "negative_attrs": negative_attrs
                    })
                    
            except Exception as e:
                problem_players.append({
                    "uid": player.uid,
                    "nickname": player.nickname,
                    "error": str(e)
                })
        
        # 生成报告
        lines = [
            "🔍 属性诊断报告",
            "━━━━━━━━━━━━━",
            f"📊 总玩家数：{total_players}",
            f"⚠️ 问题玩家数：{len(problem_players)}"
        ]
        
        if problem_players:
            lines.append("")
            lines.append("🚨 发现问题的玩家：")
            for i, player_info in enumerate(problem_players[:10]):  # 只显示前10个
                if "error" in player_info:
                    lines.append(f"{i+1}. UID{player_info['uid']} {player_info['nickname']} - 错误: {player_info['error']}")
                else:
                    lines.append(f"{i+1}. UID{player_info['uid']} {player_info['nickname']} - 负属性: {', '.join(player_info['negative_attrs'])}")
            
            if len(problem_players) > 10:
                lines.append(f"... 还有 {len(problem_players) - 10} 个问题玩家")
            
            lines.append("")
            lines.append("💡 使用【修复属性】指令进行批量修复")
        else:
            lines.append("")
            lines.append("✅ 未发现属性异常问题")
        
        await diagnose_attributes.finish(message_add_head("\n".join(lines), event))


@fix_attributes.handle()
async def handle_fix_attributes(event: MessageEvent):
    """修复玩家属性问题"""
    async with safe_session() as session:
        from ..config import config as gcfg
        
        # 初始基础属性
        INIT_ATTRS = {
            "max_hp": 20,
            "max_mp": 20,
            "attack": 1,
            "defense": 5,
            "agility": 5,
            "luck": 1,
            "critical_rate": 5,
            "critical_power": 0,
            "combo_rate": 0,
            "counter_rate": 0,
            "dodge_rate": 0,
            "accuracy_rate": 80,
            "skill_crit_rate": 0,
            "penetration_rate": 0,
            "anti_crit_rate": 0,
            "lifesteal_rate": 0,
            "immobilize_rate": 0,
            "true_damage_rate": 0,
            "regen_rate": 0,
        }
        
        # 获取所有玩家
        stmt = select(Player)
        players = (await session.execute(stmt)).scalars().all()
        
        fixed_count = 0
        error_count = 0
        
        for player in players:
            try:
                # 重新计算玩家属性
                await _recalculate_player_attributes(session, player, INIT_ATTRS, gcfg)
                fixed_count += 1
                
            except Exception as e:
                error_count += 1
                print(f"修复玩家 {player.uid} 时出错: {e}")
        
        await session.commit()
        
        lines = [
            "🔧 属性修复完成",
            "━━━━━━━━━━━━━",
            f"✅ 成功修复：{fixed_count} 个玩家",
            f"❌ 修复失败：{error_count} 个玩家",
            "",
            "💡 建议再次运行【诊断属性】确认修复效果"
        ]
        
        await fix_attributes.finish(message_add_head("\n".join(lines), event))


@safe_fix_attributes.handle()
async def handle_safe_fix_attributes(event: MessageEvent):
    """安全修复玩家属性问题（只修复明显异常的）"""
    async with safe_session() as session:
        from ..config import config as gcfg

        # 初始基础属性
        INIT_ATTRS = {
            "max_hp": 20,
            "max_mp": 20,
            "attack": 1,
            "defense": 5,
            "agility": 5,
            "luck": 1,
            "critical_rate": 5,
            "critical_power": 0,
            "combo_rate": 0,
            "counter_rate": 0,
            "dodge_rate": 0,
            "accuracy_rate": 80,
            "skill_crit_rate": 0,
            "penetration_rate": 0,
            "anti_crit_rate": 0,
            "lifesteal_rate": 0,
            "immobilize_rate": 0,
            "true_damage_rate": 0,
            "regen_rate": 0,
        }

        # 获取所有玩家
        stmt = select(Player)
        players = (await session.execute(stmt)).scalars().all()

        fixed_count = 0
        skipped_count = 0
        error_count = 0

        for player in players:
            try:
                breakdown = await player.get_attribute_breakdown(session)

                # 检查是否需要修复
                needs_fix = False
                main_attrs = ["max_hp", "max_mp", "attack", "defense", "agility", "luck"]

                for attr in main_attrs:
                    if breakdown["base"][attr] < 0:
                        needs_fix = True
                        break

                if needs_fix:
                    # 只修复有负数基础属性的玩家
                    await _safe_recalculate_player_attributes(session, player, INIT_ATTRS, gcfg)
                    fixed_count += 1
                else:
                    skipped_count += 1

            except Exception as e:
                error_count += 1
                print(f"安全修复玩家 {player.uid} 时出错: {e}")

        await session.commit()

        lines = [
            "🔧 安全属性修复完成",
            "━━━━━━━━━━━━━",
            f"✅ 修复玩家：{fixed_count} 个",
            f"⏭️ 跳过正常：{skipped_count} 个",
            f"❌ 修复失败：{error_count} 个",
            "",
            "💡 只修复了基础属性为负数的玩家",
            "💡 建议再次运行【诊断属性】确认修复效果"
        ]

        await safe_fix_attributes.finish(message_add_head("\n".join(lines), event))


async def _recalculate_player_attributes(session, player: Player, INIT_ATTRS: dict, gcfg):
    """重新计算单个玩家的属性"""

    # 1. 计算丹药加成
    elixir_bonus = {k: 0 for k in INIT_ATTRS}
    stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player.id)
    logs = (await session.execute(stmt)).scalars().all()

    elixir_usage_total = {}
    for log in logs:
        if log.item_id not in elixir_usage_total:
            elixir_usage_total[log.item_id] = 0
        elixir_usage_total[log.item_id] += log.quantity

    for item_id, total_qty in elixir_usage_total.items():
        item_cfg = gcfg.items_config["by_id"].get(item_id)
        if item_cfg and item_cfg.effect_type.value == "BUFF":
            effect_params = item_cfg.effect_params or {}
            for attr, value in effect_params.items():
                if attr in elixir_bonus:
                    elixir_bonus[attr] += int(value) * total_qty

    # 2. 保存当前HP/MP比例
    hp_ratio = player.hp / max(player.max_hp, 1)
    mp_ratio = player.mp / max(player.max_mp, 1)

    # 3. 先卸下所有装备，恢复基础属性
    await _remove_all_equipment_bonus(session, player, gcfg)

    # 4. 重置属性为：初始值 + 丹药加成
    for attr in INIT_ATTRS:
        base_value = INIT_ATTRS[attr] + elixir_bonus[attr]
        setattr(player, attr, base_value)

    # 5. 重新计算装备加成
    await _recalculate_equipment_bonus_for_fix(session, player, gcfg)

    # 6. 恢复HP/MP比例
    player.hp = min(int(player.max_hp * hp_ratio), player.max_hp)
    player.mp = min(int(player.max_mp * mp_ratio), player.max_mp)


async def _remove_all_equipment_bonus(session, player: Player, gcfg):
    """移除所有装备加成"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player.id,
        ItemInstance.equipped == True,
        ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"])
    )
    equipped_items = (await session.execute(stmt)).scalars().all()

    # 移除装备的持久化加成
    for eq in equipped_items:
        delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            if hasattr(player, k):
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - v))

        # 清除持久化记录
        if "_persist_bonus" in (eq.extra_attrs or {}):
            extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
            eq.extra_attrs = extra_new

        session.add(eq)


async def _recalculate_equipment_bonus_for_fix(session, player: Player, gcfg):
    """重新计算装备加成（修复专用）"""
    
    # 获取所有已装备的装备
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player.id,
        ItemInstance.equipped == True,
        ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"])
    )
    equipped_items = (await session.execute(stmt)).scalars().all()
    
    # 清除所有装备的持久化记录
    for eq in equipped_items:
        if "_persist_bonus" in (eq.extra_attrs or {}):
            extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
            eq.extra_attrs = extra_new
    
    # 获取当前基础属性
    base_attrs = {
        "attack": player.attack,
        "defense": player.defense,
        "agility": player.agility,
        "luck": player.luck,
        "max_hp": player.max_hp,
        "max_mp": player.max_mp,
    }
    
    # 重新计算并应用装备加成
    for eq in equipped_items:
        attrs_temp = base_attrs.copy()
        eq.apply_attr_bonus(attrs_temp, base_attrs)
        new_delta = {}
        
        for k in attrs_temp:
            if k in base_attrs:
                if attrs_temp[k] != base_attrs[k]:
                    new_delta[k] = attrs_temp[k] - base_attrs[k]
            else:
                if attrs_temp[k] != 0:
                    new_delta[k] = attrs_temp[k]
        
        # 应用到玩家属性
        for k, v in new_delta.items():
            setattr(player, k, getattr(player, k) + v)
        
        # 保存新的持久化加成
        extra = eq.extra_attrs or {}
        extra["_persist_bonus"] = new_delta
        eq.extra_attrs = extra
        session.add(eq)
    
    # 确保当前HP/MP不超过上限
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp
    
    session.add(player)


async def _safe_recalculate_player_attributes(session, player: Player, INIT_ATTRS: dict, gcfg):
    """安全地重新计算单个玩家的属性（只修复明显异常的）"""

    # 1. 计算丹药加成
    elixir_bonus = {k: 0 for k in INIT_ATTRS}
    stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player.id)
    logs = (await session.execute(stmt)).scalars().all()

    elixir_usage_total = {}
    for log in logs:
        if log.item_id not in elixir_usage_total:
            elixir_usage_total[log.item_id] = 0
        elixir_usage_total[log.item_id] += log.quantity

    for item_id, total_qty in elixir_usage_total.items():
        item_cfg = gcfg.items_config["by_id"].get(item_id)
        if item_cfg and item_cfg.effect_type.value == "BUFF":
            effect_params = item_cfg.effect_params or {}
            for attr, value in effect_params.items():
                if attr in elixir_bonus:
                    elixir_bonus[attr] += int(value) * total_qty

    # 2. 获取当前属性分解
    breakdown = await player.get_attribute_breakdown(session)

    # 3. 只修复基础属性为负数的属性
    main_attrs = ["max_hp", "max_mp", "attack", "defense", "agility", "luck"]

    for attr in main_attrs:
        if breakdown["base"][attr] < 0:
            # 计算应该的最小基础值（初始值 + 一些合理的加点）
            min_base_value = INIT_ATTRS[attr] + max(0, (player.level - 1) // 10)  # 每10级至少1点加点

            # 计算当前总值应该调整多少
            current_total = getattr(player, attr)
            expected_total = (
                min_base_value +
                breakdown["equipment"][attr] +
                breakdown["elixir"][attr] +
                breakdown["temporary"][attr]
            )

            # 如果需要调整，直接设置为期望值
            if expected_total > current_total:
                setattr(player, attr, expected_total)

    session.add(player)
