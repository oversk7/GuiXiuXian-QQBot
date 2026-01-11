"""
送礼系统命令处理器

支持两种送礼模式:
1. 赠礼 - 远程送好感度礼物(消耗型,增加好感度和魅力值)
2. 转移 - 当面转移物品(需同地点,物品实际转移)
"""
import re
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.exception import FinishedException

from ..infrastructure.di.container import DIContainer
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from .relationship_service import RelationshipService

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
        # 1. 获取玩家ID
        player_id = event.get_user_id()

        # 2. 解析参数
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

        # 3. 执行送礼
        async with UnitOfWork(AsyncSessionLocal) as uow:
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
    from nonebot import logger
    try:
        # 1. 获取玩家ID
        player_id = event.get_user_id()

        # 2. 解析参数
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

        # 3. 执行转移
        logger.info(f"[转移命令] 开始执行转移: sender_id={player_id}, receiver_uid={receiver_uid}, item={item_name}, quantity={quantity}")
        async with UnitOfWork(AsyncSessionLocal) as uow:
            logger.debug(f"[转移命令] UnitOfWork 会话创建成功")
            # 创建服务
            logger.debug(f"[转移命令] 开始创建 RelationshipService")
            relationship_service = RelationshipService(
                player_repo=uow.players,
                relationship_repo=uow.player_relationships,
                item_repo=uow.items,
                uow=uow
            )
            logger.debug(f"[转移命令] RelationshipService 创建成功")

            # 调用当面送礼逻辑
            logger.debug(f"[转移命令] 开始调用 send_gift_face_to_face")
            success, message = await relationship_service.send_gift_face_to_face(
                sender_id=player_id,
                receiver_uid=receiver_uid,
                item_name=item_name,
                quantity=quantity
            )

            # 4. 返回结果
            logger.info(f"[转移命令] 转移完成: success={success}, message={message}")
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
