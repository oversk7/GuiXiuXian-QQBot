import asyncio
import os
import shutil
import sys
from datetime import datetime
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

# 直接使用项目内的数据库与模型
from plugins.xiuxian_game.models.db import safe_session as db_safe_session
from plugins.xiuxian_game.models import Player, ItemInstance  # type: ignore
import plugins.xiuxian_game.models.db as dbmod


def _resolve_db_path() -> str:
    # 与运行时一致：plugins/xiuxian_game/models/db.py 内使用 ../data/game5.db
    models_dir = os.path.dirname(os.path.abspath(dbmod.__file__))
    db_path = os.path.normpath(os.path.join(models_dir, "../data/game5.db"))
    return db_path


def backup_db_file() -> str:
    db_path = _resolve_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"找不到数据库文件: {db_path}")
    backups_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backups_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backups_dir, f"game5.db.{ts}.bak")
    shutil.copy2(db_path, dst)
    return dst


async def migrate(dry_run: bool = True) -> None:
    changed_players = 0
    changed_items = 0

    # 预备：一次性取出全部玩家与已装备物品，避免 N+1 查询
    try:
        async with db_safe_session() as session:
            players = (await session.execute(select(Player))).scalars().all()
            equipped_items = (
                await session.execute(
                    select(ItemInstance).where(ItemInstance.equipped == True)
                )
            ).scalars().all()

            # 将装备按玩家分组
            eq_by_player: Dict[str, List[ItemInstance]] = {}
            for eq in equipped_items:
                pid = getattr(eq, "player_id", None)
                if not pid:
                    continue
                eq_by_player.setdefault(pid, []).append(eq)

            # 逐个玩家处理
            for p in players:
                pid = p.id
                eqs = eq_by_player.get(pid, [])

                # 累计 _persist_bonus.max_hp
                eq_hp_bonus = 0
                for eq in eqs:
                    extra = eq.extra_attrs or {}
                    delta = extra.get("_persist_bonus", {})
                    try:
                        eq_hp_bonus += int(delta.get("max_hp", 0) or 0)
                    except (TypeError, ValueError):
                        # 忽略非整数脏数据
                        pass

                if eq_hp_bonus == 0 and not eqs:
                    continue  # 没有装备或没有HP加成，跳过

                # 先减去装备加的 max_hp
                base_max_hp = int(p.max_hp) - int(eq_hp_bonus)
                if base_max_hp < 0:
                    base_max_hp = 0

                # 再乘以 3
                new_max_hp = base_max_hp * 3

                if dry_run:
                    print(f"[DRY-RUN] 玩家(uid={p.uid}) max_hp: {p.max_hp} -> {new_max_hp} (减去装备{eq_hp_bonus}后×3)")
                else:
                    p.max_hp = new_max_hp
                    # 保证当前 hp 不超过新上限
                    if p.hp > p.max_hp:
                        p.hp = p.max_hp
                    session.add(p)
                    changed_players += 1

                # 将所有装备 bonus.max_hp 置 0
                for eq in eqs:
                    extra = dict(eq.extra_attrs or {})
                    delta = dict((extra.get("_persist_bonus") or {}))
                    old = delta.get("max_hp", 0)
                    if old and int(old) != 0:
                        if dry_run:
                            print(f"[DRY-RUN] 装备(id={eq.id}) _persist_bonus.max_hp: {old} -> 0")
                        else:
                            delta["max_hp"] = 0
                            extra["_persist_bonus"] = delta
                            eq.extra_attrs = extra
                            session.add(eq)
                            changed_items += 1

    except SQLAlchemyError as db_err:
        print(f"⛔ 数据库操作失败: {db_err}")
        raise
    except OSError as os_err:
        print(f"⛔ 文件系统错误: {os_err}")
        raise

    if dry_run:
        print("━━━━━━━━━━━━━")
        print("✅ 干跑完成：未对数据库做任何更改。确认无误后用 --apply 真正执行。")
    else:
        print("━━━━━━━━━━━━━")
        print(f"✅ 迁移完成：更新玩家 {changed_players} 条，装备 {changed_items} 条。")


def parse_args(argv: List[str]) -> Dict[str, bool]:
    return {
        "apply": ("--apply" in argv),
        "no-backup": ("--no-backup" in argv),
    }


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    dry_run = not args["apply"]

    if dry_run:
        print("🔎 干跑模式：仅打印变更，不写入数据库。添加 --apply 执行实际修改。")
    else:
        if not args["no-backup"]:
            try:
                backup = backup_db_file()
                print(f"🗂️ 已备份数据库到: {backup}")
            except OSError as e:
                print(f"⛔ 备份失败: {e}")
                sys.exit(1)

    asyncio.run(migrate(dry_run=dry_run))

