"""
管理员指令：迁移加体比例（1:3）

功能：
- 对所有玩家执行：先减去装备持久化加的 max_hp，再乘以 3，写回 player.max_hp；确保当前 hp 不超过新上限
- 将所有已穿戴装备的 extra_attrs._persist_bonus.max_hp 清零
- 提供 预览/执行 两种模式；执行模式默认先备份（备份当前 models.db 所指向的实际 db 文件）

用法：
- 预览（默认）： 迁移加体比例 [预览]
- 执行：       迁移加体比例 执行 [不备份]

注意：
- 仅管理员可用
- 所有输出均为被动触发，block=True
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from typing import Dict, List, Tuple

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..ai_guide import is_admin
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..utils import message_add_head


CMD = on_command("迁移加体比例", aliases={"迁移体比例", "修复体上限"}, block=True, priority=1)


def _resolve_db_path() -> str:
    # 与 plugins/xiuxian_game/models/db.py 中的 engine 配置保持一致（相对 models 目录的 ../data/game5.db）
    from ..models import db as dbmod
    models_dir = os.path.dirname(os.path.abspath(dbmod.__file__))
    db_path = os.path.normpath(os.path.join(models_dir, "../data/game5.db"))
    return db_path


def _backup_db_if_needed(skip_backup: bool) -> Tuple[bool, str]:
    if skip_backup:
        return True, "已跳过备份"
    try:
        db_path = _resolve_db_path()
        if not os.path.exists(db_path):
            return False, f"找不到数据库文件: {db_path}"
        backups_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backups_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(backups_dir, f"game5.db.{ts}.bak")
        shutil.copy2(db_path, dst)
        return True, f"已备份到 {os.path.basename(dst)}"
    except OSError as e:
        return False, f"备份失败: {e}"


async def _collect_changes(session) -> Tuple[List[str], int, int]:
    """返回预览文本（最多展示前10条）、将会变更的玩家数与装备数。
    只做计算，不写库。
    """
    preview_lines: List[str] = []

    players = (await session.execute(select(Player))).scalars().all()
    equipped_items = (
        await session.execute(select(ItemInstance).where(ItemInstance.equipped == True))
    ).scalars().all()

    # 按玩家分组装备
    eq_by_player: Dict[str, List[ItemInstance]] = {}
    for eq in equipped_items:
        pid = getattr(eq, "player_id", None)
        if not pid:
            continue
        eq_by_player.setdefault(pid, []).append(eq)

    changed_players = 0
    changed_items = 0

    for p in players:
        eqs = eq_by_player.get(p.id, [])
        # 汇总 max_hp 持久化加成
        eq_hp_bonus = 0
        for eq in eqs:
            extra = eq.extra_attrs or {}
            delta = extra.get("_persist_bonus", {})
            try:
                eq_hp_bonus += int(delta.get("max_hp", 0) or 0)
            except (TypeError, ValueError):
                # 忽略非整型脏数据
                pass

        # 计算新 max_hp
        base_max_hp = int(p.max_hp) - int(eq_hp_bonus)
        if base_max_hp < 0:
            base_max_hp = 0
        new_max_hp = base_max_hp * 3

        if new_max_hp != int(p.max_hp) or eq_hp_bonus != 0:
            changed_players += 1
            # 统计需要清零的装备条数
            for eq in eqs:
                delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
                try:
                    old = int(delta.get("max_hp", 0) or 0)
                except (TypeError, ValueError):
                    old = 0
                if old != 0:
                    changed_items += 1

            if len(preview_lines) < 10:
                preview_lines.append(
                    f"UID{p.uid}：max_hp {p.max_hp} -> {new_max_hp}（减装{eq_hp_bonus}后×3）"
                )

    if changed_players == 0:
        preview_lines.append("未检测到需要变更的数据")

    return preview_lines, changed_players, changed_items


async def _apply_changes(session) -> Tuple[int, int]:
    """执行迁移，返回(修改的玩家数, 修改的装备数)"""
    players = (await session.execute(select(Player))).scalars().all()
    equipped_items = (
        await session.execute(select(ItemInstance).where(ItemInstance.equipped == True))
    ).scalars().all()

    eq_by_player: Dict[str, List[ItemInstance]] = {}
    for eq in equipped_items:
        pid = getattr(eq, "player_id", None)
        if not pid:
            continue
        eq_by_player.setdefault(pid, []).append(eq)

    changed_players = 0
    changed_items = 0

    for p in players:
        eqs = eq_by_player.get(p.id, [])
        eq_hp_bonus = 0
        for eq in eqs:
            extra = eq.extra_attrs or {}
            delta = extra.get("_persist_bonus", {})
            try:
                eq_hp_bonus += int(delta.get("max_hp", 0) or 0)
            except (TypeError, ValueError):
                pass

        base_max_hp = int(p.max_hp) - int(eq_hp_bonus)
        if base_max_hp < 0:
            base_max_hp = 0
        new_max_hp = base_max_hp * 3

        changed = False
        if new_max_hp != int(p.max_hp):
            p.max_hp = new_max_hp
            if p.hp > p.max_hp:
                p.hp = p.max_hp
            session.add(p)
            changed_players += 1
            changed = True

        # 清零装备的 _persist_bonus.max_hp
        for eq in eqs:
            extra = dict(eq.extra_attrs or {})
            delta = dict((extra.get("_persist_bonus") or {}))
            old = delta.get("max_hp", 0)
            try:
                need_zero = int(old) != 0
            except (TypeError, ValueError):
                need_zero = False
            if need_zero:
                delta["max_hp"] = 0
                extra["_persist_bonus"] = delta
                eq.extra_attrs = extra
                session.add(eq)
                changed_items += 1
                changed = True

        # 若本玩家有变更，立即落库，避免超长事务
        if changed:
            # 让 safe_session 的自动提交生效；这里不手动 commit
            pass

    return changed_players, changed_items


@CMD.handle()
async def handle_migrate(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()

    # 权限校验
    if not is_admin(user_id):
        await CMD.finish(message_add_head("⛔ 仅管理员可用", event))

    text = args.extract_plain_text().strip()
    mode_tokens = text.split() if text else []
    do_apply = any(t in ("执行", "apply", "确认") for t in mode_tokens)
    skip_backup = any(t in ("不备份", "nobackup", "skip") for t in mode_tokens)

    # 预览模式
    if not do_apply:
        try:
            async with safe_session() as session:
                preview_lines, changed_players, changed_items = await _collect_changes(session)
        except SQLAlchemyError as e:
            await CMD.finish(message_add_head(f"❌ 预览失败：数据库错误 {e}", event))

        lines = [
            "🧪 迁移加体比例（预览）",
            "━━━━━━━━━━━━━",
            *preview_lines,
            "━━━━━━━━━━━━━",
            f"预计影响玩家：{changed_players} 人",
            f"涉及装备条目：{changed_items} 条",
            "━━━━━━━━━━━━━",
            "发送【迁移加体比例 执行】开始迁移（将自动备份）",
            "发送【迁移加体比例 执行 不备份】跳过备份",
        ]
        await CMD.finish(message_add_head("\n".join(lines), event))

    # 执行模式
    # 先备份（除非用户明确跳过）
    ok, tip = _backup_db_if_needed(skip_backup)
    if not ok:
        await CMD.finish(message_add_head(f"❌ 迁移中止：{tip}", event))

    try:
        async with safe_session() as session:
            changed_players, changed_items = await _apply_changes(session)
    except SQLAlchemyError as e:
        await CMD.finish(message_add_head(f"❌ 迁移失败：数据库错误 {e}", event))

    lines = [
        "✅ 迁移完成",
        "━━━━━━━━━━━━━",
        f"玩家属性已更新：{changed_players} 条",
        f"装备bonus已清零：{changed_items} 条",
        "━━━━━━━━━━━━━",
        "提示：请玩家重新穿戴装备以应用新规则",
        (f"📦 备份：{tip}" if not skip_backup else "⚠️ 未执行备份")
    ]
    await CMD.finish(message_add_head("\n".join(lines), event))

