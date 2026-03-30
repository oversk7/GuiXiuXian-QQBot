"""
送礼系统命令处理器

支持两种送礼模式:
1. 赠礼 - 远程送好感度礼物(消耗型,增加好感度和魅力值)
2. 转移 - 当面转移物品(需同地点,物品实际转移)
    - 装备类型支持选择具体实例
"""
import re
import time
from nonebot import on_command, on_message
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.exception import FinishedException

from ..infrastructure.di.container import DIContainer
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal, safe_session
from .relationship_service import RelationshipService
from ..economy.equipment_trade_service import EquipmentTradeService
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..utils import message_add_head
from ..platform_utils import get_unified_player

# 创建命令
gift_command = on_command("赠礼", aliases={"送礼"}, priority=5, block=True)
transfer_command = on_command("转移", priority=5, block=True)


@gift_command.handle()
async def handle_gift_command(event: MessageEvent, args: Message = CommandArg()):
    """
    赠礼命令 - 远程送好感度礼物

    语法: 赠礼 UID 礼物名 数量

    特点:
    - 无地理限制,可远程赠送
    - 物品被消耗,转化为好感度和魅力值
    - 每人对另一人每天最多获得30好感度

    示例:
    - 赠礼 123 红玫瑰 10
    - 赠礼 456 钻戒 1
    """
    try:
        # 1. 解析参数
        message_text = args.extract_plain_text().strip()
        if not message_text:
            await gift_command.finish("⛔ 格式错误，正确格式：赠礼 UID 礼物名 数量\n示例：赠礼 123 红玫瑰 10")

        # 解析参数
        parts = message_text.split()
        if len(parts) < 2:
            await gift_command.finish("⛔ 格式错误，正确格式：赠礼 UID 礼物名 数量\n示例：赠礼 123 红玫瑰 10")

        # 解析UID
        try:
            receiver_uid = int(parts[0])
        except ValueError:
            await gift_command.finish("⛔ UID格式错误，请输入数字\n示例：赠礼 123 红玫瑰 10")

        # 解析礼物名
        item_name = parts[1]
        quantity = 1  # 默认数量

        # 解析数量
        if len(parts) >= 3:
            try:
                quantity = int(parts[2])
                if quantity <= 0:
                    await gift_command.finish("⛔ 数量必须大于0")
            except ValueError:
                await gift_command.finish("⛔ 数量格式错误，请输入数字")

        # 2. 执行送礼
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 获取玩家（通过ownership系统）
            player = await get_unified_player(uow.session, event)
            if not player:
                await gift_command.finish("⛔ 请先创建角色")
            player_id = player.id

            # 创建服务
            relationship_service = RelationshipService(
                player_repo=uow.players,
                relationship_repo=uow.player_relationships,
                item_repo=uow.items,
                uow=uow
            )

            # 调用送礼逻辑
            success, message = await relationship_service.send_gift_favorability(
                sender_id=player_id,
                receiver_uid=receiver_uid,
                item_name=item_name,
                quantity=quantity
            )

            # 4. 返回结果
            if success:
                await gift_command.finish(f"✅ {message}")
            else:
                await gift_command.finish(f"❌ {message}")

    except FinishedException:
        raise
    except Exception as e:
        from nonebot import logger
        logger.error(f"送礼命令处理失败: {e}", exc_info=True)
        await gift_command.finish(f"❌ 送礼失败: {str(e)}")


@transfer_command.handle()
async def handle_transfer_command(event: MessageEvent, args: Message = CommandArg()):
    """
    转移命令 - 当面转移物品

    语法: 转移 UID 物品名 数量

    特点:
    - 必须在同一地点(市集)
    - 物品实际转移到对方背包
    - 不能送材料类物品
    - 不能送好感度礼物(请用【赠礼】命令)

    示例:
    - 转移 123 回春散 5
    - 转移 456 白骨护甲 1
    """
    try:
        # 1. 解析参数
        message_text = args.extract_plain_text().strip()
        if not message_text:
            await transfer_command.finish(
                "⛔ 格式错误，正确格式：转移 UID 物品名 数量\n示例：转移 123 回春散 5"
            )

        # 解析参数
        parts = message_text.split()
        if len(parts) < 2:
            await transfer_command.finish(
                "⛔ 格式错误，正确格式：转移 UID 物品名 数量\n示例：转移 123 回春散 5"
            )

        # 解析UID
        try:
            receiver_uid = int(parts[0])
        except ValueError:
            await transfer_command.finish("⛔ UID格式错误，请输入数字\n示例：转移 123 回春散 5")

        # 解析物品名
        item_name = parts[1]
        quantity = 1  # 默认数量

        # 解析数量
        if len(parts) >= 3:
            try:
                quantity = int(parts[2])
                if quantity <= 0:
                    await transfer_command.finish("⛔ 数量必须大于0")
            except ValueError:
                await transfer_command.finish("⛔ 数量格式错误，请输入数字")

        # 2. 执行转移
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 获取玩家（通过ownership系统）
            player = await get_unified_player(uow.session, event)
            if not player:
                await transfer_command.finish("⛔ 请先创建角色")
            player_id = player.id

            # 创建服务
            relationship_service = RelationshipService(
                player_repo=uow.players,
                relationship_repo=uow.player_relationships,
                item_repo=uow.items,
                uow=uow
            )

            # 调用当面送礼逻辑
            success, message = await relationship_service.send_gift_face_to_face(
                sender_id=player_id,
                receiver_uid=receiver_uid,
                item_name=item_name,
                quantity=quantity
            )

            # 4. 检查是否为装备选择标记
            if not success and message.startswith("__EQUIPMENT_SELECTION__"):
                # 解析标记: __EQUIPMENT_SELECTION__:{item_id}:{item_name}:{count}
                parts = message.split(":")
                item_id = parts[1]
                item_name_display = parts[2]
                # 调用装备选择处理
                await _handle_equipment_transfer_selection(
                    event, player_id, item_id, item_name_display, receiver_uid
                )
                return

            # 5. 返回结果
            if success:
                await transfer_command.finish(f"✅ {message}")
            else:
                await transfer_command.finish(f"❌ {message}")

    except FinishedException:
        raise
    except Exception as e:
        from nonebot import logger
        logger.error(f"转移命令处理失败: {e}", exc_info=True)
        await transfer_command.finish(f"❌ 转移失败: {str(e)}")


# ==================== 装备选择状态管理 ====================
# 格式: {player_id: {"equipment_ids": [...], "receiver_uid": ..., "item_name": ..., "timestamp": ...}}
equipment_transfer_selection_state: dict = {}


async def _cleanup_expired_transfer_states():
    """清理过期的转移选择状态(超过5分钟)"""
    current_time = time.time()
    expired_players = [
        player_id for player_id, state in equipment_transfer_selection_state.items()
        if current_time - state.get("timestamp", 0) > 300  # 5分钟超时
    ]
    for player_id in expired_players:
        del equipment_transfer_selection_state[player_id]


async def _handle_equipment_transfer_selection(
    event: MessageEvent,
    player_id: str,
    item_id: str,
    item_name: str,
    receiver_uid: int
):
    """处理装备转移选择"""
    async with safe_session() as session:
        from ..infrastructure.repositories.item_repository import ItemRepository

        player = await session.get(Player, player_id)
        if not player:
            await transfer_command.finish("⛔ 请先创建角色")

        # 获取装备列表
        item_repo = ItemRepository(session)
        equipment_list = await item_repo.get_player_equipment_list(
            player_id, item_id, equipped=False
        )

        if not equipment_list:
            await transfer_command.finish(f"⛔ 你没有可转移的 {item_name}")

        if len(equipment_list) == 1:
            # 只有一件装备,直接转移
            equipment = equipment_list[0]
            await _execute_equipment_transfer(
                session, player, receiver_uid, equipment, event
            )
            return

        # 多件实例,保存状态并让玩家选择
        from ..economy.equipment_trade_service_new import EquipmentTradeService as ETSNew
        equipment_ids = [eq.id for eq in equipment_list]
        equipment_summaries = [
            ETSNew.generate_instance_summary(eq) for eq in equipment_list
        ]

        equipment_transfer_selection_state[player_id] = {
            "equipment_ids": equipment_ids,
            "equipment_summaries": equipment_summaries,
            "receiver_uid": receiver_uid,
            "item_name": item_name,
            "timestamp": time.time()
        }

        lines = [
            f"📋 选择要转移的 {item_name}：",
            "━━━━━━━━━━━━━"
        ]

        for i, (eq_id, summary) in enumerate(zip(equipment_ids, equipment_summaries), 1):
            lines.append(f"{i}. 🆔{eq_id} {summary}")

        lines.extend([
            "",
            "💡 请直接回复序号选择装备（如：1），或回复 取消"
        ])

        await transfer_command.finish(message_add_head("\n".join(lines), event))


async def _execute_equipment_transfer(
    session,
    player,
    receiver_uid: int,
    equipment: ItemInstance,
    event: MessageEvent
):
    """执行装备转移"""
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository
    from ..infrastructure.repositories.item_repository import ItemRepository
    from ..infrastructure.uow.unit_of_work import UnitOfWork

    # 使用UnitOfWork执行转移
    async with UnitOfWork(AsyncSessionLocal) as uow:
        relationship_service = RelationshipService(
            player_repo=uow.players,
            relationship_repo=uow.player_relationships,
            item_repo=uow.items,
            uow=uow
        )

        success, message = await relationship_service.transfer_equipment_face_to_face(
            sender_id=player.id,
            receiver_uid=receiver_uid,
            equipment_instance_id=equipment.id
        )

        if success:
            await uow.commit()
            await transfer_command.finish(message_add_head(f"✅ {message}", event))
        else:
            await transfer_command.finish(message_add_head(f"❌ {message}", event))


# ==================== 装备选择消息处理器 ====================
equipment_transfer_selection_handler = on_message(priority=10, block=False)


@equipment_transfer_selection_handler.handle()
async def _(event: MessageEvent):
    """处理装备转移选择的数字回复"""
    # 清理过期状态
    await _cleanup_expired_transfer_states()

    # 获取玩家ID
    player_id = None
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            return
        player_id = player.id

        # 检查是否有待处理的装备选择状态
        if player_id not in equipment_transfer_selection_state:
            return

    message_text = event.get_message().extract_plain_text().strip()

    # 处理取消操作
    if message_text in ["取消", "cancel", "0"]:
        del equipment_transfer_selection_state[player_id]
        await equipment_transfer_selection_handler.finish("❌ 已取消装备转移")

    # 检查是否为数字
    if not message_text.isdigit():
        return  # 不是数字，不处理

    try:
        index = int(message_text) - 1  # 转换为0基索引
        if index < 0:
            raise ValueError
    except ValueError:
        return  # 无效数字，不处理

    # 获取状态信息
    state = equipment_transfer_selection_state[player_id]
    equipment_ids = state["equipment_ids"]
    receiver_uid = state["receiver_uid"]

    # 检查序号有效性
    if index >= len(equipment_ids):
        await equipment_transfer_selection_handler.finish("⛔ 无效的装备序号，请重新选择")

    # 获取选中装备的ID
    equipment_id = equipment_ids[index]

    # 清除状态
    del equipment_transfer_selection_state[player_id]

    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            await equipment_transfer_selection_handler.finish("⛔ 请先创建角色")

        # 在新会话中重新获取装备对象
        equipment = await session.get(ItemInstance, equipment_id)
        if not equipment or equipment.player_id != player_id:
            await equipment_transfer_selection_handler.finish("⛔ 装备不存在或不属于你")

        await _execute_equipment_transfer(session, player, receiver_uid, equipment, event)

