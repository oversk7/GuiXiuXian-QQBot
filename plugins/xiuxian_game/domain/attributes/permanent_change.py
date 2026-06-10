"""玩家永久属性变更的唯一写入口（写入收口）

所有永久改变 player 属性字段的操作必须经过 apply_permanent_change，
它原子地完成四件事，缺一不可：

1. 改 player 字段
2. 记账到 ElixirUsageLog（永久属性账本——轮回重建、洗髓额度、属性分解都以它为准）
3. 触发装备加成重算（装备百分比加成以基础属性为基数）
4. hp/mp 超上限收口

绕过本函数直接 setattr 会导致账实漂移，且该加成会在玩家轮回时被静默吞掉。
对账工具：scripts/check_attribute_consistency.py
"""
from typing import Dict

# 非丹药来源的账本条目 id（不与任何物品 item_id 冲突，不以 _elixir 结尾）
LEDGER_LADDER_SHOP = "ladder_shop_attr"
LEDGER_STORY_REWARD = "story_reward_attr"
LEDGER_DUNGEON_REWARD = "dungeon_reward_attr"
LEDGER_EXPLORE_FORTUNE = "explore_fortune_attr"
LEDGER_CALIBRATION = "ledger_calibration"


async def apply_permanent_change(session, player, deltas: Dict[str, int], *,
                                 ledger_item_id: str, quantity: int = 1) -> Dict[str, int]:
    """应用一次永久属性变更（正负皆可），返回实际写入的变更。

    Args:
        session: 数据库会话（事务由外层 safe_session/UoW 管理，本函数不 commit）
        player: 玩家对象
        deltas: 属性变更 {"attack": 10, "max_hp": -30, ...}，0 值与未知字段被忽略
        ledger_item_id: 账本条目 id——丹药传物品 item_id，
            其他来源用本模块顶部的 LEDGER_* 常量
        quantity: 使用次数（丹药每日用量统计依赖它；非丹药来源传 1）
    """
    actual: Dict[str, int] = {}
    for attr, delta in (deltas or {}).items():
        d = int(delta)
        if d == 0 or not hasattr(player, attr):
            continue
        setattr(player, attr, getattr(player, attr) + d)
        actual[attr] = d

    if not actual:
        return actual

    # 基础属性变化后重算装备加成（装备 attr_ratio 百分比加成以基础属性为基数）
    from ...infrastructure.repositories.item_repository import ItemRepository
    from ...infrastructure.repositories.player_repository import PlayerRepository
    from ...item.equipment_service import EquipmentService

    equipment_service = EquipmentService(
        item_repo=ItemRepository(session),
        player_repo=PlayerRepository(session),
    )
    await equipment_service.recalc_equipment_attributes(player)

    # 当前血量/理智不得超过新上限
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    from ...models.elixir_usage import ElixirUsageLog

    log = await ElixirUsageLog.get_or_create_log(session, player.id, ledger_item_id)
    log.quantity += quantity
    log.record_changes(actual)
    return actual
