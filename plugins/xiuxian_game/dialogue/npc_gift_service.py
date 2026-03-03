"""NPC礼物系统 - 允许NPC在对话中赠送少量恢复药品"""
import re
import logging
from datetime import date

from ..models.npc import NPC
from ..models.player import Player

logger = logging.getLogger(__name__)

# 允许赠送的物品白名单：物品名 -> (item_id, 每次最多数量)
GIFT_WHITELIST: dict[str, tuple[str, int]] = {
    "回春散": ("heal_potion", 2),
    "凝神草": ("spirit_herb", 2),
    "血契丹": ("blood_pact",  1),
    "阴冥草": ("yin_grass",   1),
}

_GIFT_PATTERN = re.compile(r'\[赠[:：](.+?)[:：](\d+)\]')


def parse_npc_gift(
    npc: NPC,
    player_id: str,
    response: str,
) -> tuple[str, str | None, int, str | None]:
    """
    从AI回复中解析礼物标记，同时做白名单和冷却检查。

    Returns:
        (cleaned_response, item_id, quantity, item_name)
        item_id 为 None 表示无礼物或校验未通过
    """
    match = _GIFT_PATTERN.search(response)
    # 无论是否送礼，先从文本中删除标记
    cleaned = _GIFT_PATTERN.sub("", response).strip()

    if not match:
        return cleaned, None, 0, None

    item_name = match.group(1).strip()
    qty = int(match.group(2))

    # 白名单校验
    if item_name not in GIFT_WHITELIST:
        logger.warning(f"NPC {npc.name} 尝试赠送非白名单物品: {item_name!r}，已忽略")
        return cleaned, None, 0, None

    item_id, max_qty = GIFT_WHITELIST[item_name]
    qty = max(1, min(qty, max_qty))

    # 冷却检查：每个NPC每天对同一玩家只赠一次
    today = str(date.today())
    gift_log: dict = npc.extra_data.get("gift_log", {})
    if gift_log.get(player_id) == today:
        logger.info(f"NPC {npc.name} 今日已对玩家 {player_id} 赠过物品，冷却中")
        return cleaned, None, 0, None

    return cleaned, item_id, qty, item_name


async def apply_npc_gift(
    session,
    npc: NPC,
    player: Player,
    item_id: str,
    qty: int,
    item_name: str,
) -> bool:
    """执行赠送：写入背包，更新冷却记录"""
    from ..models.inventory import ItemInstance
    from sqlalchemy.orm.attributes import flag_modified

    success = await ItemInstance.add_item(session, player.id, item_id, qty)
    if success:
        today = str(date.today())
        gift_log = npc.extra_data.get("gift_log", {})
        gift_log[player.id] = today
        npc.extra_data["gift_log"] = gift_log
        flag_modified(npc, "extra_data")
        logger.info(f"NPC {npc.name} 赠送 {item_name}×{qty} 给玩家 {player.nickname}")
    else:
        logger.warning(f"NPC {npc.name} 赠送 {item_name}×{qty} 失败（背包已满？）")
    return success
