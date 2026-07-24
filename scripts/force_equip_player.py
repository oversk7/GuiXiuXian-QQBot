"""管理员脚本：为指定玩家破格穿戴背包中的装备（无视等级限制）

运行方式:
    python scripts/force_equip_player.py --uid 101 --dry-run   # 预览
    python scripts/force_equip_player.py --uid 101             # 实际穿戴

规则：
  - 跳过等级校验（破格）
  - 仍然保留：耐久>0、不与已穿同名装备重复、装备栏上限、转数(冥返)要求
  - 穿戴顺序：先穿提供额外装备槽的装备，其余按等级要求从高到低
  - 同名多件只穿耐久最高的一件
  - 穿戴完成后调用 EquipmentService.recalc_equipment_attributes 统一重算属性
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

from plugins.xiuxian_game.models.db import AsyncSessionLocal
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.item.equipment_service import (
    EQUIP_ITEM_IDS, EquipmentService,
)
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository
from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository

BASE_EQUIPMENT_SLOT_LIMIT = 5  # 与 equipment_commands.py 保持一致


def slot_bonus(eq: ItemInstance) -> int:
    cfg = getattr(eq, "config", None)
    try:
        return max(0, int(getattr(cfg, "equipment_slot_bonus", 0) or 0)) if cfg else 0
    except (TypeError, ValueError):
        return 0


async def force_equip(uid: int, dry_run: bool, ignore_reincarnation: bool) -> None:
    async with AsyncSessionLocal() as session:
        player = (await session.execute(
            select(Player).where(Player.uid == uid)
        )).scalar_one_or_none()
        if not player:
            print(f"⛔ 找不到 UID={uid} 的玩家")
            return

        print(f"👤 {player.nickname} [UID:{uid}] Lv.{player.level} "
              f"{player.reincarnation_level or 0}转 (server {player.server_id})")

        equipped = list((await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS),
            )
        )).scalars().all())

        bag = list((await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == False,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS),
            )
        )).scalars().all())

        print(f"🎽 已穿戴 {len(equipped)} 件：" +
              ("、".join(f"{e.config.name}(#{e.id})" for e in equipped) or "无"))
        if not bag:
            print("⛔ 背包中没有未穿戴的装备")
            return
        print(f"🎒 背包装备 {len(bag)} 件待处理")

        # 同名多件只保留耐久最高的
        best_by_item: dict[str, ItemInstance] = {}
        for eq in bag:
            cur = best_by_item.get(eq.item_id)
            if cur is None or eq.durability > cur.durability:
                best_by_item[eq.item_id] = eq
        candidates = list(best_by_item.values())
        # 先穿扩槽装备，其余按等级要求从高到低
        candidates.sort(
            key=lambda e: (-slot_bonus(e), -(e.config.required_level or 1), -e.durability)
        )

        equipped_item_ids = {e.item_id for e in equipped}
        equipped_count = len(equipped)
        success, skipped = [], []

        for eq in candidates:
            name = f"{eq.config.name}(#{eq.id})"
            req_lv = eq.config.required_level or 1
            req_reinc = eq.config.required_reincarnation or 0
            if not ignore_reincarnation and req_reinc > (player.reincarnation_level or 0):
                skipped.append(f"{name}: 转数不足(需{req_reinc}转)")
                continue
            if eq.durability <= 0:
                skipped.append(f"{name}: 已损坏(耐久0)")
                continue
            if eq.item_id in equipped_item_ids:
                skipped.append(f"{name}: 已穿同名装备")
                continue
            limit = BASE_EQUIPMENT_SLOT_LIMIT + sum(slot_bonus(e) for e in equipped) + slot_bonus(eq)
            if equipped_count >= limit:
                skipped.append(f"{name}: 装备栏已满({equipped_count}/{limit})")
                continue

            breaches = []
            if req_lv > player.level:
                breaches.append(f"需Lv.{req_lv}>当前Lv.{player.level}")
            if req_reinc > (player.reincarnation_level or 0):
                breaches.append(f"需{req_reinc}转>当前{player.reincarnation_level or 0}转")
            note = f"（破格：{'，'.join(breaches)}）" if breaches else ""
            success.append(f"{name}{note}")
            eq.equipped = True
            session.add(eq)
            equipped.append(eq)
            equipped_item_ids.add(eq.item_id)
            equipped_count += 1

        print()
        if success:
            print(f"✅ {'[dry-run] 将' if dry_run else '成功'}穿戴 {len(success)} 件：")
            for s in success:
                print(f"  • {s}")
        if skipped:
            print(f"⏭️  跳过 {len(skipped)} 件：")
            for s in skipped:
                print(f"  • {s}")

        if dry_run or not success:
            await session.rollback()
            print("\n（dry-run 或无变更，未写库）")
            return

        service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session),
        )
        await service.recalc_equipment_attributes(player)
        session.add(player)
        await session.commit()
        print(f"\n💾 已提交。当前面板：攻{player.attack} 防{player.defense} "
              f"敏{player.agility} 运{player.luck} HP{player.hp}/{player.max_hp} MP{player.mp}/{player.max_mp}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ignore-reincarnation", action="store_true",
                        help="连转数(冥返)要求也一并无视")
    args = parser.parse_args()
    asyncio.run(force_equip(args.uid, args.dry_run, args.ignore_reincarnation))


if __name__ == "__main__":
    main()
