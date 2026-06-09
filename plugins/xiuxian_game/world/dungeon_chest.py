"""
深渊探索者宝箱系统

每十层诡域允许玩家领取一个深渊探索者宝箱，鼓励玩家持续探索
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import select
from datetime import datetime

from ..models.db import safe_session
from ..models.player import Player
from ..models.dungeon_chest_record import DungeonChestRecord
from ..models.inventory import ItemInstance
from ..utils import message_add_head
from ..platform_utils import require_player


# 深渊探索者宝箱相关指令
dungeon_chest_cmd = on_command("探索宝箱", aliases={"探索者宝箱"}, block=True, priority=5)
claim_chest_cmd = on_command("领取宝箱", aliases={"领取探索宝箱", "领取探索者宝箱"}, block=True, priority=5)


@dungeon_chest_cmd.handle()
async def handle_dungeon_chest_info(event: MessageEvent):
    """查看深渊探索者宝箱信息"""
    async with safe_session() as session:
        player = await require_player(session, event, dungeon_chest_cmd)
        
        # 获取玩家已领取的宝箱记录
        stmt = select(DungeonChestRecord).where(
            DungeonChestRecord.player_id == player.id
        ).order_by(DungeonChestRecord.dungeon_level)
        claimed_records = (await session.execute(stmt)).scalars().all()
        claimed_levels = {record.dungeon_level for record in claimed_records}
        
        # 获取可以领取的层级
        available_levels = player.get_available_explorer_chest_levels()
        
        # 构建消息
        msg_lines = [
            "🎁 深渊探索者宝箱系统",
            "━━━━━━━━━━━━━",
            f"📊 当前最深探索：第{player.max_dungeon_level or 0}重诡域",
            "",
            "🏆 宝箱领取规则：",
            "• 每探索到第10、20、30...层时可领取一个深渊探索者宝箱",
            "• 每个层级的宝箱只能领取一次",
            "• 宝箱内含珍贵的镶嵌物和材料",
            "",
        ]
        
        if available_levels:
            unclaimed_levels = sorted(
                level for level in available_levels if level not in claimed_levels
            )
            claimed_count = len(claimed_levels)
            if unclaimed_levels:
                unclaimed_display = "、".join(f"第{level}层" for level in unclaimed_levels)
                msg_lines.extend([
                    f"🎁 待领取宝箱：共 {len(unclaimed_levels)} 个",
                    f"  {unclaimed_display}",
                    "",
                    "💡 使用【领取宝箱】一键领取所有可领取的宝箱"
                ])
            else:
                msg_lines.append("🔒 暂无可领取的宝箱")
                msg_lines.append("💡 继续探索诡域，每到达第10层的倍数即可获得宝箱！")

            if claimed_count:
                msg_lines.append(f"✅ 已领取宝箱：{claimed_count} 个")
        else:
            msg_lines.append("🔒 暂无可领取的宝箱")
            msg_lines.append("💡 继续探索诡域，每到达第10层的倍数即可获得宝箱！")
        
        msg = "\n".join(msg_lines)
        await dungeon_chest_cmd.finish(message_add_head(msg, event))


@claim_chest_cmd.handle()
async def handle_claim_chest(event: MessageEvent):
    """一键领取所有可领取的深渊探索者宝箱"""
    async with safe_session() as session:
        player = await require_player(session, event, claim_chest_cmd)

        # 获取玩家已领取的宝箱记录
        stmt = select(DungeonChestRecord).where(
            DungeonChestRecord.player_id == player.id
        )
        claimed_records = (await session.execute(stmt)).scalars().all()
        claimed_levels = {record.dungeon_level for record in claimed_records}

        # 获取可以领取的层级
        available_levels = player.get_available_explorer_chest_levels()

        # 找出未领取的层级
        unclaimed_levels = [level for level in available_levels if level not in claimed_levels]

        if not unclaimed_levels:
            await claim_chest_cmd.finish("⛔ 暂无可领取的宝箱\n💡 继续探索诡域，每到达第10层的倍数即可获得宝箱！")

        # 检查背包容量（使用有效容量，包含月卡加成）
        stmt = select(ItemInstance).where(ItemInstance.player_id == player.id)
        current_items = (await session.execute(stmt)).scalars().all()
        # 计算已使用的背包格数（装备、鱼类、铭文不计入）
        current_slots = sum(1 for item in current_items if not item.is_equipment and not item.is_fish and not item.is_inscription)

        # 获取有效背包容量（包含月卡加成）
        effective_capacity = await player.get_effective_inventory_capacity(session)
        needed_slots = len(unclaimed_levels)
        if current_slots + needed_slots > effective_capacity:
            await claim_chest_cmd.finish(f"⛔ 背包空间不足！需要 {needed_slots} 个空位，当前剩余 {effective_capacity - current_slots} 个空位")

        # 批量创建深渊探索者宝箱和记录
        claimed_count = 0
        for level in unclaimed_levels:
            # 创建深渊探索者宝箱
            chest_item = ItemInstance(
                player_id=player.id,
                item_id="abyss_explorer_chest",
                quantity=1,
                created_at=datetime.now()
            )
            session.add(chest_item)

            # 记录领取记录
            chest_record = DungeonChestRecord(
                player_id=player.id,
                dungeon_level=level,
                claimed_at=datetime.now()
            )
            session.add(chest_record)
            claimed_count += 1

        await session.commit()

        # 构建成功消息
        msg_lines = [
            f"🎁 成功领取 {claimed_count} 个深渊探索者宝箱！",
            "━━━━━━━━━━━━━",
            f"✨ 已领取层级：{', '.join(f'第{level}层' for level in unclaimed_levels)}",
            "🔮 宝箱内含珍贵的镶嵌物和材料",
            "",
            "💡 使用【开宝箱 深渊探索者宝箱】开启宝箱",
            "🏆 继续探索更深的诡域获得更多奖励！"
        ]

        msg = "\n".join(msg_lines)
        await claim_chest_cmd.finish(message_add_head(msg, event))
