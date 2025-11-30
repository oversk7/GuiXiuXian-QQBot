"""
物品效果适配器示例

展示如何将典型的旧效果迁移到新接口
包含3个代表性示例：简单数值修改、数据库操作、逻辑判断
"""

from nonebot import logger

from ..interfaces import BaseItemEffect, EffectContext, EffectResult, TriggerType
from ..registry import register_effect


# ============ 示例1: 简单数值修改 - 恢复生命值 ============

@register_effect("example_restore_hp")
class ExampleRestoreHPEffect(BaseItemEffect):
    """
    示例：恢复生命值效果（重写版）

    展示如何将简单的数值修改效果迁移到新接口

    旧版本 (item_effects.py:78-93):
    ```python
    @register(ItemEffectType.RESTORE_HP)
    async def _restore_hp(player, cfg, qty, ctx, session):
        value = int(cfg.effect_params.get("value", 0)) * qty
        if player.hp <= 0:
            return False, "🧐 你已经死亡，无法恢复生命"
        # ... 省略
        player.hp = min(effective_max_hp, player.hp + value)
        return True, f"❤️ 恢复 {value} 点生命值"
    ```

    新版本:
    """

    def __init__(self):
        super().__init__("example_restore_hp")

    async def execute(self, context: EffectContext) -> EffectResult:
        """执行恢复生命值效果"""
        player = context.player
        item_cfg = context.item_config
        quantity = context.quantity or 1
        session = context.session

        # 计算恢复量
        value = int(item_cfg.effect_params.get("value", 0)) * quantity

        logger.debug(f"💊 [RestoreHP] 玩家 {player.id} 使用恢复药水: 恢复量={value}")

        # 检查玩家是否死亡
        if player.hp <= 0:
            return EffectResult(
                success=False,
                message="🧐 你已经死亡，无法恢复生命"
            )

        # 获取有效最大生命值
        effective_max_hp = player.max_hp
        if session:
            # 使用AttributeCalculator v2获取有效属性
            from ...domain.attributes import get_effective_attributes_v2
            effective_attrs = await get_effective_attributes_v2(player, session)
            effective_max_hp = effective_attrs.get("max_hp", effective_max_hp)

        # 检查是否已满血
        if player.hp >= effective_max_hp:
            return EffectResult(
                success=False,
                message="🧐 你的生命值已满，不需要使用此物品"
            )

        # 恢复生命值
        old_hp = player.hp
        player.hp = min(effective_max_hp, player.hp + value)
        actual_restore = player.hp - old_hp

        logger.debug(
            f"✅ [RestoreHP] 玩家 {player.id} 恢复生命: "
            f"{old_hp} → {player.hp} (+{actual_restore})"
        )

        return EffectResult(
            success=True,
            message=f"❤️ 恢复 {actual_restore} 点生命值 (当前 {player.hp}/{effective_max_hp})",
            attribute_changes={"hp": actual_restore},
            status_changes=[],
            extra_data={"old_hp": old_hp, "new_hp": player.hp}
        )


# ============ 示例2: 数据库操作 - 临时Buff ============

@register_effect("example_temporary_buff")
class ExampleTemporaryBuffEffect(BaseItemEffect):
    """
    示例：临时Buff效果（重写版）

    展示如何将涉及数据库操作的效果迁移到新接口

    旧版本 (item_effects.py:269-307):
    ```python
    @register(ItemEffectType.TEMPORARY_BUFF)
    async def _temporary_buff(player, cfg, qty, ctx, session):
        # ... 省略
        new_buff = TemporaryBuff(
            player_id=player.id,
            buff_name=buff_name,
            # ...
        )
        session.add(new_buff)
        return True, f"✨ 获得临时增益【{buff_name}】..."
    ```

    新版本:
    """

    def __init__(self):
        super().__init__("example_temporary_buff")

    async def execute(self, context: EffectContext) -> EffectResult:
        """执行临时buff效果"""
        from ...models.temporary_buff import TemporaryBuff
        from ...domain.attributes import invalidate_player_buff_cache

        player = context.player
        item_cfg = context.item_config
        quantity = context.quantity or 1
        session = context.session

        if not session:
            return EffectResult(
                success=False,
                message="❌ 临时buff效果需要数据库会话"
            )

        # 获取buff参数
        params = item_cfg.effect_params
        buff_name = params.get("name", "未命名增益")
        duration_minutes = params.get("duration", 30) * quantity

        # 构建属性加成字典
        bonuses = {}
        for attr in ["attack", "defense", "agility", "luck", "max_hp", "max_mp"]:
            if attr in params:
                bonuses[attr] = params[attr] * quantity

        logger.debug(
            f"🌟 [TempBuff] 玩家 {player.id} 使用buff物品: "
            f"name={buff_name}, duration={duration_minutes}m, bonuses={bonuses}"
        )

        # 创建临时buff记录
        from datetime import datetime, timedelta
        new_buff = TemporaryBuff(
            player_id=player.id,
            buff_name=buff_name,
            attack_bonus=bonuses.get("attack", 0),
            defense_bonus=bonuses.get("defense", 0),
            agility_bonus=bonuses.get("agility", 0),
            luck_bonus=bonuses.get("luck", 0),
            max_hp_bonus=bonuses.get("max_hp", 0),
            max_mp_bonus=bonuses.get("max_mp", 0),
            expires_at=datetime.now() + timedelta(minutes=duration_minutes),
            created_at=datetime.now()
        )

        session.add(new_buff)
        await session.flush()  # 确保buff被写入

        # 使buff缓存失效
        invalidate_player_buff_cache(player.id)

        logger.debug(f"✅ [TempBuff] 玩家 {player.id} 临时buff已创建: ID={new_buff.id}")

        # 构建消息
        bonus_parts = [f"{k}+{v}" for k, v in bonuses.items() if v > 0]
        bonus_text = "、".join(bonus_parts) if bonus_parts else "无加成"

        return EffectResult(
            success=True,
            message=f"✨ 获得临时增益【{buff_name}】({duration_minutes}分钟)\n📊 加成: {bonus_text}",
            attribute_changes=bonuses,
            status_changes=[f"添加临时buff: {buff_name}"],
            extra_data={
                "buff_id": new_buff.id,
                "duration_minutes": duration_minutes,
                "bonuses": bonuses
            }
        )


# ============ 示例3: 逻辑判断 - 获得经验 ============

@register_effect("example_gain_exp")
class ExampleGainExpEffect(BaseItemEffect):
    """
    示例：获得经验效果（重写版）

    展示如何将包含复杂逻辑的效果迁移到新接口

    旧版本 (item_effects.py:336-360):
    ```python
    @register(ItemEffectType.GAIN_EXP)
    async def _gain_exp(player, cfg, qty, ctx, session):
        value = int(cfg.effect_params.get("value", 0)) * qty
        # ... 检查等级上限
        player.exp += value
        # ... 升级逻辑
        return True, msg
    ```

    新版本:
    """

    def __init__(self):
        super().__init__("example_gain_exp")

    async def execute(self, context: EffectContext) -> EffectResult:
        """执行获得经验效果"""
        from ...utils import calculate_level_up_exp

        player = context.player
        item_cfg = context.item_config
        quantity = context.quantity or 1

        # 计算经验值
        exp_value = int(item_cfg.effect_params.get("value", 0)) * quantity

        logger.debug(f"📚 [GainExp] 玩家 {player.id} 使用经验物品: exp={exp_value}")

        # 检查是否达到等级上限
        max_level = 500  # 从配置读取
        if player.level >= max_level:
            return EffectResult(
                success=False,
                message=f"🚫 你已达到等级上限 (Lv.{max_level})，无法继续获得经验"
            )

        # 添加经验
        old_level = player.level
        old_exp = player.exp
        player.exp += exp_value

        # 检查是否升级
        level_up_count = 0
        messages = []

        while player.exp >= calculate_level_up_exp(player.level):
            if player.level >= max_level:
                player.exp = 0  # 满级后清空经验
                break

            # 升级
            player.exp -= calculate_level_up_exp(player.level)
            player.level += 1
            level_up_count += 1

            # 升级奖励
            player.attribute_points += 3
            messages.append(f"🎉 恭喜升级！Lv.{player.level-1} → Lv.{player.level} (获得3点属性点)")

        logger.debug(
            f"✅ [GainExp] 玩家 {player.id} 获得经验: "
            f"Lv.{old_level}({old_exp}) → Lv.{player.level}({player.exp}), "
            f"升级{level_up_count}次"
        )

        # 构建消息
        if level_up_count > 0:
            main_message = f"📖 获得 {exp_value} 点经验值\n" + "\n".join(messages)
        else:
            exp_needed = calculate_level_up_exp(player.level) - player.exp
            main_message = (
                f"📖 获得 {exp_value} 点经验值\n"
                f"当前经验: {player.exp}/{calculate_level_up_exp(player.level)} "
                f"(还需 {exp_needed})"
            )

        return EffectResult(
            success=True,
            message=main_message,
            attribute_changes={
                "exp": exp_value,
                "level": level_up_count,
                "attribute_points": level_up_count * 3
            },
            status_changes=[f"升级{level_up_count}次"] if level_up_count > 0 else [],
            extra_data={
                "old_level": old_level,
                "new_level": player.level,
                "level_up_count": level_up_count
            }
        )
