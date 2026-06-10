"""属性对账脚本（只读）

按账本独立分解每个玩家的属性来源，检测存量数据漂移：

    base残差 = player存储值 - 丹药账本(ElixirUsageLog) - 装备快照(_persist_bonus) - VIP加成

不变量：
  A. 六维属性(max_hp/max_mp/attack/defense/agility/luck)：base残差 >= INIT
     （残差 = 初始值 + 加点投入，加点只增不减，洗髓只动账本部分）
  B. 战斗属性(critical_rate 等 13 项)：base残差 == INIT
     （加点无法分配到战斗属性，永久变化必须全部记录在账本/快照/VIP中）

违反 A → 某次属性扣减没记账（或账本多记）。
违反 B → 某次战斗属性变更绕过了账本（如轮回时战斗属性装备加成重复累积）。

运行方式（只读，不写库）:
    .venv/Scripts/python.exe scripts/check_attribute_consistency.py            # 全量
    .venv/Scripts/python.exe scripts/check_attribute_consistency.py --limit 20 # 只看前20个漂移
"""
import argparse
import asyncio
import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init()
    nonebot.load_plugin("nonebot_plugin_apscheduler")

from sqlalchemy import select

from plugins.xiuxian_game.config import config as gcfg
from plugins.xiuxian_game.models.db import AsyncSessionLocal
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.elixir_usage import ElixirUsageLog
from plugins.xiuxian_game.models.vip_equipment_bonus import VIPEquipmentBonus

SIX_DIMS = {"max_hp", "max_mp", "attack", "defense", "agility", "luck"}
BATTLE_ATTRS = set(Player.INIT_ATTRS) - SIX_DIMS


async def decompose(session, player: Player) -> dict:
    """独立实现的属性分解（不复用 get_attribute_breakdown，作交叉验证）"""
    INIT = Player.INIT_ATTRS

    elixir = {k: 0 for k in INIT}
    logs = (await session.execute(
        select(ElixirUsageLog).where(ElixirUsageLog.player_id == player.id)
    )).scalars().all()
    for log in logs:
        for attr, v in log.get_attribute_bonus().items():
            if attr in elixir:
                elixir[attr] += int(v)

    equip = {k: 0 for k in INIT}
    equipment_ids = gcfg.items_config["by_type"]["EQUIPMENT"]
    items = (await session.execute(
        select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(equipment_ids),
        )
    )).scalars().all()
    for eq in items:
        for k, v in ((eq.extra_attrs or {}).get("_persist_bonus", {})).items():
            if k in equip:
                equip[k] += int(v)

    vip = {k: 0 for k in INIT}
    vip_record = (await session.execute(
        select(VIPEquipmentBonus).where(VIPEquipmentBonus.player_id == player.id)
    )).scalars().first()
    if vip_record:
        for attr, v in vip_record.get_total_bonus().items():
            if attr in vip:
                vip[attr] = int(v)

    residual = {}
    for attr in INIT:
        stored = int(getattr(player, attr, 0) or 0)
        residual[attr] = stored - elixir[attr] - equip[attr] - vip[attr]
    return {"residual": residual, "elixir": elixir, "equip": equip, "vip": vip}


async def main(limit: int):
    INIT = Player.INIT_ATTRS
    drift_a = []  # (player, attr, residual, init)
    drift_b = []
    total_players = 0

    async with AsyncSessionLocal() as session:
        players = (await session.execute(select(Player))).scalars().all()
        for player in players:
            total_players += 1
            parts = await decompose(session, player)
            residual = parts["residual"]
            for attr in SIX_DIMS:
                if residual[attr] < INIT[attr]:
                    drift_a.append((player, attr, residual[attr], INIT[attr]))
            for attr in BATTLE_ATTRS:
                if residual[attr] != INIT[attr]:
                    drift_b.append((player, attr, residual[attr], INIT[attr]))

    print(f"玩家总数: {total_players}")
    print(f"不变量A违反(六维 base残差 < INIT，疑似漏记账): {len(drift_a)} 条")
    for player, attr, res, init in drift_a[:limit]:
        print(f"  [{player.id}] {player.nickname or '?'} {attr}: 残差 {res} < 初始 {init} (差 {res - init})")
    if len(drift_a) > limit:
        print(f"  ... 其余 {len(drift_a) - limit} 条省略")

    print(f"不变量B违反(战斗属性 base残差 != INIT，疑似绕过账本): {len(drift_b)} 条")
    by_attr: dict[str, list[int]] = {}
    for player, attr, res, init in drift_b:
        by_attr.setdefault(attr, []).append(res - init)
    for attr, diffs in sorted(by_attr.items()):
        n = len(diffs)
        print(f"  {attr}: {n} 人, 偏差范围 [{min(diffs)}, {max(diffs)}], 偏差和 {sum(diffs)}")
    for player, attr, res, init in drift_b[:limit]:
        print(f"  [{player.id}] {player.nickname or '?'} {attr}: 残差 {res} != 初始 {init} (差 {res - init})")
    if len(drift_b) > limit:
        print(f"  ... 其余 {len(drift_b) - limit} 条省略")

    clean = total_players - len({p.id for p, *_ in drift_a} | {p.id for p, *_ in drift_b})
    print(f"完全干净的玩家: {clean}/{total_players}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="每类漂移最多展示条数")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
