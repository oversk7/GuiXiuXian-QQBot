from __future__ import annotations

"""打工系统初始化脚本

用于初始化工作地点数据和相关配置
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.permission import SUPERUSER

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .part_time_job_service import PartTimeJobService


# 管理员命令：初始化打工系统
init_part_time_job_cmd = on_command("初始化打工系统", block=True, priority=1, permission=SUPERUSER)


@init_part_time_job_cmd.handle()
async def handle_init_part_time_job(event: MessageEvent):
    """初始化打工系统数据"""
    try:
        async with safe_session() as session:
            # 初始化工作地点
            await PartTimeJobService.initialize_job_locations(session)

            result_msg = (
                "✅ 打工系统初始化完成！\n"
                "━━━━━━━━━━━━━\n"
                f"📍 已创建 {len(PartTimeJobService.JOB_LOCATIONS)} 个工作地点\n"
                f"💼 共配置 {len(PartTimeJobService.JOB_TYPES)} 种工作类型\n"
                "🎯 玩家可前往对应坐标开始打工\n"
                "🏘️ 所有打工地点已整合到相应城镇中"
            )

            await init_part_time_job_cmd.finish(message_add_head(result_msg, event))

    except ValueError as e:
        await init_part_time_job_cmd.finish(f"❌ 初始化失败：{str(e)}")


# 管理员命令：查看打工系统状态
check_part_time_job_cmd = on_command("查看打工系统", block=True, priority=1, permission=SUPERUSER)


@check_part_time_job_cmd.handle()
async def handle_check_part_time_job(event: MessageEvent):
    """查看打工系统状态"""
    try:
        async with safe_session() as session:
            locations = await PartTimeJobService.get_job_locations_list(session)

            if not locations:
                await check_part_time_job_cmd.finish("❌ 未找到工作地点，请先初始化系统")

            lines = ["🏢 打工系统状态", "━━━━━━━━━━━━━"]

            for location in locations:
                lines.append(f"📍 {location['name']}")
                lines.append(f"   坐标：({location['x']}, {location['y']})")
                lines.append(f"   工作数：{location['job_count']}个")
                lines.append(f"   等级要求：{location['required_level']}级")
                lines.append("")

            lines.extend([
                "━━━━━━━━━━━━━",
                f"📊 总计：{len(locations)}个工作地点",
                f"💼 工作类型：{len(PartTimeJobService.JOB_TYPES)}种"
            ])

            await check_part_time_job_cmd.finish(message_add_head("\n".join(lines), event))

    except Exception as e:
        await check_part_time_job_cmd.finish(f"❌ 查看失败：{str(e)}")


# 测试命令：模拟完成工作（仅用于测试）
test_complete_job_cmd = on_command("测试完成工作", block=True, priority=1, permission=SUPERUSER)


@test_complete_job_cmd.handle()
async def handle_test_complete_job(event: MessageEvent):
    """测试命令：立即完成当前工作"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await test_complete_job_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await test_complete_job_cmd.finish("⛔ 请先创建角色")

        # 获取当前工作状态
        success, msg, status = await PartTimeJobService.get_current_job_status(session, player)

        if not success:
            await test_complete_job_cmd.finish(f"❌ {msg}")

        # 强制设置工作为已完成
        from sqlalchemy import select, and_
        from ..models.part_time_job import PartTimeJob
        from datetime import datetime

        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player.id,
                PartTimeJob.is_working == True
            )
        )
        current_job = (await session.execute(stmt)).scalars().first()

        if current_job:
            # 设置为已完成
            current_job.end_time = datetime.now()
            session.add(current_job)
            await session.commit()

            await test_complete_job_cmd.finish("✅ 工作已设置为完成状态，请使用【收工】获得奖励")
        else:
            await test_complete_job_cmd.finish("❌ 未找到当前工作")