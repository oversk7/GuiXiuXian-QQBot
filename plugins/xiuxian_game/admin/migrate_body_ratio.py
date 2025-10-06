"""
全量迁移：将历史“体”加点的生命值增量从1:1调整为1:3
- 仅迁移“加点带来的基础生命”部分；丹药与装备加成不放大
- 迁移完成后：重算装备加成，并将玩家当前HP置为满血
- 管理员指令：
  【迁移体加点 确认】 执行全服迁移
"""
from typing import Dict, Tuple

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..models.db import safe_session
from ..models.player import Player
from ..models.elixir_usage import ElixirUsageLog
from ..models.inventory import ItemInstance
from ..config import config
from ..utils import message_add_head

# 复用现有的装备重算逻辑（会基于当前基础属性重算百分比加成并持久化）
from ..item.item_effects import _recalculate_equipment_bonus


# 初始基础属性（与各处保持一致）
INIT_MAX_HP = 20


async def _get_elixir_bonus(session, player_id: str) -> Dict[str, int]:
    """计算历史丹药的累计属性加成（只取整型）"""
    elixir_bonus: Dict[str, int] = {
        "max_hp": 0,
        "max_mp": 0,
        "attack": 0,
        "defense": 0,
        "agility": 0,
        "luck": 0,
    }

    # 汇总玩家的所有丹药使用记录
    stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player_id)
    logs = (await session.execute(stmt)).scalars().all()

    if not logs:
        return elixir_bonus

    # 按物品汇总总使用量
    totals: Dict[str, int] = {}
    for log in logs:
        totals[log.item_id] = totals.get(log.item_id, 0) + int(log.quantity)

    # 将 BUFF 型丹药折算为属性加成
    from ..models.inventory import ItemEffectType

    for item_id, qty in totals.items():
        item_cfg = config.items_config["by_id"].get(item_id)
        if not item_cfg or item_cfg.effect_type != ItemEffectType.BUFF:
            continue
        params = item_cfg.effect_params or {}
        for k, v in params.items():
            if isinstance(v, (int, float)):
                if k in elixir_bonus:
                    elixir_bonus[k] += int(v) * int(qty)

    return elixir_bonus


async def _get_equipment_persist_bonus_hp(session, player_id: str) -> int:
    """汇总当前已装备装备在_max_hp上的持久化加成（_persist_bonus）。"""
    gcfg = config
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"]),
    )
    equipped_items = (await session.execute(stmt)).scalars().all()

    total_hp = 0
    for eq in equipped_items:
        delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
        v = int(delta.get("max_hp", 0)) if isinstance(delta, dict) else 0
        total_hp += v
    return total_hp


migrate_body_ratio_cmd = on_command(
    "迁移体加点", aliases={"迁移体比例", "迁移HP加点", "迁移体1比3"}, block=True, priority=2, permission=SUPERUSER
)


@migrate_body_ratio_cmd.handle()
async def handle_migrate(event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if text != "确认":
        await migrate_body_ratio_cmd.finish(
            "⛔ 安全保护：请在命令后附加“确认”二字以执行全服迁移\n"
            "━━━━━━━━━━━━━\n"
            "示例：迁移体加点 确认\n"
            "说明：将历史‘体’加点的生命值增量从1:1调整为1:3，迁移后自动满血，并重算装备加成"
        )

    success = 0
    failed = 0

    async with safe_session() as session:
        # 读取全部玩家
        stmt = select(Player)
        players = (await session.execute(stmt)).scalars().all()

        for player in players:
            try:
                # 1) 获取来源分解所需：丹药加成、装备持久化加成(HP)
                elixir_bonus = await _get_elixir_bonus(session, player.id)
                equip_hp = await _get_equipment_persist_bonus_hp(session, player.id)

                # 2) 计算当前基础HP（初始值+加点，不含丹药与装备）
                base_hp = int(player.max_hp) - int(elixir_bonus.get("max_hp", 0)) - int(equip_hp)
                if base_hp < INIT_MAX_HP:
                    base_hp = INIT_MAX_HP  # 防御脏数据

                # 3) 估算历史“体”加点点数，并按1:3换算新的基础HP
                old_points = base_hp - INIT_MAX_HP
                if old_points < 0:
                    old_points = 0
                new_base_hp = INIT_MAX_HP + old_points * 3

                # 4) 应用新基础HP（先不计装备）+ 丹药加成
                player.max_hp = int(new_base_hp + elixir_bonus.get("max_hp", 0))

                # 5) 基于新的基础属性，重算装备持久化加成
                await _recalculate_equipment_bonus(session, player)

                # 6) 迁移后满血
                player.hp = player.max_hp

                session.add(player)
                success += 1
            except SQLAlchemyError:
                failed += 1
            except ValueError:
                failed += 1

    msg = (
        "🔧 全服迁移完成\n"
        "━━━━━━━━━━━━━\n"
        f"✅ 成功：{success} 人\n"
        f"⚠️ 失败：{failed} 人\n"
        "━━━━━━━━━━━━━\n"
        "说明：已将历史‘体’加点的生命值增量从1:1调整为1:3，迁移后自动满血，并重算装备加成"
    )
    await migrate_body_ratio_cmd.finish(message_add_head(msg, event))

