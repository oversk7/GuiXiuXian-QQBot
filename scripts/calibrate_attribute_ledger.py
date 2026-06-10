"""属性账本校准脚本（存量漂移一次性核销）

策略（2026-06-10 经用户确认）：玩家属性一切不变，以存储值为准，
给每个漂移玩家补一条 `ledger_calibration` 账目，使账实相符：

  校准值 = base残差 - INIT，使校准后残差恰好回到 INIT

- 六维属性：仅校准负残差（残差 < INIT，历史漏记负账），正残差视为加点不动
- 战斗属性：残差 != INIT 即校准（加点无法分配到战斗属性，偏差必为绕账历史）

校准只写 ElixirUsageLog，不改 player 字段，玩家完全无感。
运行后用 scripts/check_attribute_consistency.py 复核应为 0 漂移。

运行方式:
    .venv/bin/python scripts/calibrate_attribute_ledger.py            # dry-run 预览
    .venv/bin/python scripts/calibrate_attribute_ledger.py --apply    # 实际写入
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
from plugins.xiuxian_game.models.elixir_usage import ElixirUsageLog
from plugins.xiuxian_game.domain.attributes.permanent_change import LEDGER_CALIBRATION
from check_attribute_consistency import decompose, SIX_DIMS, BATTLE_ATTRS


async def main(apply: bool):
    INIT = Player.INIT_ATTRS
    calibrated_players = 0
    total_entries = 0

    async with AsyncSessionLocal() as session:
        players = (await session.execute(select(Player))).scalars().all()
        for player in players:
            parts = await decompose(session, player)
            residual = parts["residual"]

            calib = {}
            for attr in SIX_DIMS:
                if residual[attr] < INIT[attr]:
                    calib[attr] = residual[attr] - INIT[attr]
            for attr in BATTLE_ATTRS:
                if residual[attr] != INIT[attr]:
                    calib[attr] = residual[attr] - INIT[attr]

            if not calib:
                continue

            calibrated_players += 1
            total_entries += len(calib)
            detail = ", ".join(f"{k}{v:+d}" for k, v in calib.items())
            print(f"[{player.id}] {player.nickname or '?'}: {detail}")

            if apply:
                log = await ElixirUsageLog.get_or_create_log(
                    session, player.id, LEDGER_CALIBRATION
                )
                log.record_changes(calib)

        if apply:
            await session.commit()
            print(f"\n已写入: {calibrated_players} 个玩家, {total_entries} 条属性校准")
        else:
            print(f"\n[dry-run] 将校准 {calibrated_players} 个玩家, {total_entries} 条属性（--apply 实际写入）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
