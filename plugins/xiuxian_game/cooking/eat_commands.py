"""
泛用【吃】指令 - 替代原有【吃鱼】

支持:
- 吃生鱼(保留原有风味描述)
- 吃菜肴(恢复理智 + buff效果)
- 吃黑暗料理(扣理智)
"""

import random
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import require_player
from ..models.inventory import ItemType
from .cooking_service import DishQuality

# ==================== 【吃】指令 ====================

eat_cmd = on_command("吃", aliases={"品尝", "食用", "吃鱼", "吃掉鱼", "品尝鱼"}, priority=11, block=True)


@eat_cmd.handle()
async def handle_eat(event: MessageEvent, args: Message = CommandArg()):
    """【吃 食物名 数量】- 食用食物"""

    args_text = args.extract_plain_text().strip()

    if not args_text:
        await eat_cmd.finish("⛔ 用法: 吃 <食物名> [数量]\n可以吃鱼、菜肴等食物")

    # 解析参数
    parts = args_text.split()
    food_name = parts[0]
    quantity = 1

    if len(parts) > 1:
        try:
            quantity = int(parts[1])
            if quantity <= 0 or quantity > 99:
                await eat_cmd.finish("⛔ 数量必须在 1-99 之间")
        except ValueError:
            await eat_cmd.finish("⛔ 数量必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, eat_cmd)

        # 1. 根据物品名称查找物品配置
        from ..config import config
        item_config = config.items_config["by_name"].get(food_name)

        if not item_config:
            await eat_cmd.finish(f"⛔ 未找到食物【{food_name}】")

        # 2. 判断物品类型并执行对应逻辑
        if item_config.type == ItemType.FISH:
            # 吃生鱼
            msg = await _eat_fish(uow, player, item_config.item_id, quantity)
            await eat_cmd.finish(msg)

        elif item_config.type == ItemType.DISH:
            # 吃菜肴
            # 从item_id中提取品质: dish_{recipe_id}_{quality}
            parts = item_config.item_id.split("_")
            if len(parts) >= 3 and parts[0] == "dish":
                quality = parts[-1]  # dark/normal/fine/perfect
                buff = item_config.effect_params  # 从配置中读取buff

                msg = await _eat_dish(
                    uow, player, item_config.item_id, quality, buff, quantity
                )
                await eat_cmd.finish(msg)
            else:
                await eat_cmd.finish(f"⛔ 菜肴物品ID格式错误: {item_config.item_id}")

        else:
            await eat_cmd.finish(f"⛔ 【{food_name}】不是可食用物品")


# ==================== 私有函数 ====================


async def _eat_fish(uow: UnitOfWork, player, fish_item_id: str, quantity: int) -> str:
    """
    吃生鱼(纯娱乐,无实际效果)

    Args:
        uow: 工作单元
        player: 玩家对象
        fish_item_id: 鱼类物品ID
        quantity: 数量

    Returns:
        消息文本
    """

    # 获取鱼类名称
    from ..config import config
    fish_config = config.items_config["by_id"].get(fish_item_id)
    fish_name = fish_config.name if fish_config else fish_item_id

    # 检查物品数量
    fish_count = await uow.items.get_material_total_quantity(player.id, fish_item_id)

    if fish_count < quantity:
        return f"⛔ 你没有足够的{fish_name}(拥有 {fish_count})"

    # 扣除鱼
    items = await uow.items.get_by_player_and_item_id(player.id, fish_item_id)
    remaining = quantity

    for item in items:
        if remaining <= 0:
            break

        if item.quantity >= remaining:
            item.quantity -= remaining
            if item.quantity == 0:
                await uow.items.delete(item.id)
            else:
                await uow.items.update(item)
            remaining = 0
        else:
            remaining -= item.quantity
            await uow.items.delete(item.id)

    await uow.commit()

    # 生成风味描述(保留原吃鱼的娱乐文本)
    flavor_texts = [
        f"你生吞了{quantity}条{fish_name}，感觉怪怪的...",
        f"你品尝了生{fish_name}的味道，嗯...很原始",
        f"咔嚓咔嚓，你把{fish_name}当零食吃了",
        f"你像猫一样啃食着{fish_name}",
    ]

    return random.choice(flavor_texts)


async def _eat_dish(
    uow: UnitOfWork,
    player,
    dish_item_id: str,
    dish_quality: str,
    dish_buff: dict,
    quantity: int
) -> str:
    """
    吃菜肴(恢复理智 + 可能的buff)

    Args:
        uow: 工作单元
        player: 玩家对象
        dish_item_id: 菜肴物品ID
        dish_quality: 菜肴品质
        dish_buff: buff效果(仅完美品质有效)
        quantity: 数量

    Returns:
        消息文本
    """

    # 获取菜肴名称
    from ..config import config
    dish_config = config.items_config["by_id"].get(dish_item_id)
    dish_name = dish_config.name if dish_config else dish_item_id

    # 检查物品数量
    dish_count = await uow.items.get_material_total_quantity(player.id, dish_item_id)

    if dish_count < quantity:
        return f"⛔ 你没有足够的{dish_name}(拥有 {dish_count})"

    # 扣除菜肴
    items = await uow.items.get_by_player_and_item_id(player.id, dish_item_id)
    remaining = quantity

    for item in items:
        if remaining <= 0:
            break

        if item.quantity >= remaining:
            item.quantity -= remaining
            if item.quantity == 0:
                await uow.items.delete(item.id)
            else:
                await uow.items.update(item)
            remaining = 0
        else:
            remaining -= item.quantity
            await uow.items.delete(item.id)

    # 应用效果
    total_sanity_gain = 0

    if dish_quality == DishQuality.DARK:
        # 黑暗料理:扣2理智
        sanity_loss = 2 * quantity
        player.mp = max(0, player.mp - sanity_loss)
        msg = f"💀 你硬着头皮吃下了黑暗料理...\n理智 -{sanity_loss}"

    elif dish_quality == DishQuality.NORMAL or dish_quality == DishQuality.FINE:
        # 普通/精致:恢复1~3理智
        sanity_gain = random.randint(1, 3) * quantity
        player.mp = min(player.max_mp, player.mp + sanity_gain)
        total_sanity_gain = sanity_gain

        quality_emoji = "🍽️" if dish_quality == DishQuality.NORMAL else "✨"
        msg = f"{quality_emoji} 美味的菜肴!\n理智 +{sanity_gain}"

    elif dish_quality == DishQuality.PERFECT:
        # 完美:回复理智 + 永久幸运加成 + 其他临时buff
        if dish_buff and "sanity" in dish_buff:
            sanity_gain = dish_buff["sanity"] * quantity
            player.mp = min(player.max_mp, player.mp + sanity_gain)
            total_sanity_gain = sanity_gain

        perm_effects = []
        timed_effects = []

        if dish_buff:
            # 幸运永久增加（本轮回有效：记入 volatile 账目，冥返不重放、洗髓不可洗）
            if "luck" in dish_buff:
                luck_gain = dish_buff["luck"] * quantity
                from ..domain.attributes.permanent_change import apply_permanent_change, LEDGER_COOKING_LUCK
                await apply_permanent_change(
                    uow.session, player, {"luck": luck_gain},
                    ledger_item_id=LEDGER_COOKING_LUCK, quantity=quantity
                )
                perm_effects.append(f"幸运+{luck_gain}")

            # 其他属性仍走临时buff（如气血上限）
            TIMED_ATTRS = {"max_hp": "气血上限"}
            timed_bonuses = {
                attr: dish_buff[attr] * quantity
                for attr in TIMED_ATTRS
                if attr in dish_buff
            }

            if timed_bonuses:
                from ..models.temporary_buff import TemporaryBuff

                duration_minutes = dish_buff.get("duration", 30)
                buff_id = f"{dish_item_id}_buff"
                buff_name = f"{dish_name}·完美效果"

                existing_buffs = await TemporaryBuff.get_active_buffs(uow.session, player.id)
                has_existing = any(b.buff_id == buff_id for b in existing_buffs)

                if has_existing:
                    existing = next(b for b in existing_buffs if b.buff_id == buff_id)
                    remaining = existing.get_remaining_minutes()
                    timed_effects.append(f"⚠️ 已有相同效果，剩余{remaining}分钟")
                else:
                    await TemporaryBuff.create_buff(
                        session=uow.session,
                        player_id=player.id,
                        buff_id=buff_id,
                        buff_name=buff_name,
                        attribute_bonuses=timed_bonuses,
                        duration_minutes=duration_minutes,
                        source_item_id=dish_item_id,
                        source_description=f"食用{dish_name}获得"
                    )

                    bonus_strs = [f"{TIMED_ATTRS[k]}+{v}" for k, v in timed_bonuses.items()]
                    if duration_minutes >= 60:
                        h, m = divmod(duration_minutes, 60)
                        time_str = f"{h}小时{m}分钟" if m else f"{h}小时"
                    else:
                        time_str = f"{duration_minutes}分钟"
                    timed_effects.append(f"{' '.join(bonus_strs)}（{time_str}）")

        msg = f"🌟 完美的菜肴!\n理智 +{total_sanity_gain}"
        if perm_effects:
            msg += f"\n⭐ 永久增益(本轮回): {' | '.join(perm_effects)}"
        if timed_effects:
            msg += f"\n✨ 临时增益: {' '.join(timed_effects)}"

    else:
        msg = f"🍴 你吃了 {dish_name}"

    await uow.players.update(player)
    await uow.commit()

    return msg
