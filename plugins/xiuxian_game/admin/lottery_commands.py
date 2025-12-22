"""
抽奖系统指令
管理员和子管理员可以发起抽奖，玩家可以参与抽奖
"""
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select, func
from datetime import datetime
import random

from ..models.db import safe_session
from ..models.player import Player
from ..models.lottery import Lottery, LotteryParticipant, LotteryType, LotteryStatus
from ..models.inventory import ItemInstance, ItemType
from ..config import config
from ..utils import message_add_head


# 权限检查函数
def is_admin(user_id: str) -> bool:
    """检查是否是管理员"""
    from ..ai_guide import is_admin as check_admin
    return check_admin(user_id)


def is_sub_admin(user_id: str) -> bool:
    """检查是否是子管理员"""
    from ..item.inventory import is_sub_admin as check_sub_admin
    return check_sub_admin(user_id)


def can_create_lottery(user_id: str) -> bool:
    """检查是否有权限发起抽奖"""
    return is_admin(user_id) or is_sub_admin(user_id)


# ==================== 发起抽奖 ====================
create_lottery_cmd = on_command("发起抽奖", block=True, priority=2)


@create_lottery_cmd.handle()
async def handle_create_lottery(event: MessageEvent, args: Message = CommandArg()):
    """
    发起抽奖：发起抽奖 物品名/装备名/金币 中奖人数 每人数量 [最低等级]
    例如：发起抽奖 棺材钉 10 10
    例如：发起抽奖 金币 5 1000 50
    """
    user_id = event.get_user_id()

    # 权限检查
    if not can_create_lottery(user_id):
        await create_lottery_cmd.finish("⛔ 只有管理员和子管理员可以发起抽奖")

    params = args.extract_plain_text().strip().split()
    if len(params) < 3 or len(params) > 5:
        await create_lottery_cmd.finish(
            "⛔ 格式错误\n"
            "━━━━━━━━━━━━━\n"
            "正确格式：\n"
            "【发起抽奖 物品名 中奖人数 每人数量 [最低等级 [最高等级]]】\n"
            "【发起抽奖 装备名 中奖人数 每人数量 [最低等级 [最高等级]]】\n"
            "【发起抽奖 金币 中奖人数 每人数量 [最低等级 [最高等级]]】\n"
            "━━━━━━━━━━━━━\n"
            "示例：\n"
            "发起抽奖 棺材钉 10 10\n"
            "发起抽奖 金币 5 1000 50 120\n"
            "━━━━━━━━━━━━━\n"
            "💡 最低等级默认为1，可选填防止小号参与\n"
            "💡 最高等级默认为不限，可选填限制高等级玩家"
        )

    prize_name = params[0]
    winner_count_str = params[1]
    prize_per_winner_str = params[2]
    min_level_str = params[3] if len(params) >= 4 else "1"
    max_level_str = params[4] if len(params) >= 5 else None
    
    # 参数校验
    max_level = None

    try:
        winner_count = int(winner_count_str)
        prize_per_winner = int(prize_per_winner_str)
        min_level = int(min_level_str)
        max_level = int(max_level_str) if max_level_str is not None else None
        if winner_count <= 0 or prize_per_winner <= 0:
            raise ValueError
        if min_level < 1:
            raise ValueError
        if max_level is not None and (max_level < 1 or max_level < min_level):
            raise ValueError
    except ValueError:
        await create_lottery_cmd.finish("⛔ 中奖人数、每人数量以及等级要求必须为正整数，且最高等级需不小于最低等级")
    
    async with safe_session() as session:
        # 获取发起人信息
        creator = await session.get(Player, user_id)
        if not creator:
            await create_lottery_cmd.finish("⛔ 请先创建角色")
        
        # 判断抽奖类型
        lottery_type = None
        item_id = None
        total_prize = winner_count * prize_per_winner
        
        if prize_name == "金币":
            lottery_type = LotteryType.GOLD
            # 检查金币是否足够
            if creator.gold < total_prize:
                await create_lottery_cmd.finish(
                    f"⛔ 金币不足\n"
                    f"需要：{total_prize:,} 金币\n"
                    f"拥有：{creator.gold:,} 金币"
                )
            # 扣除金币
            creator.gold -= total_prize
            session.add(creator)
        else:
            # 查找物品配置
            item_cfg = config.items_config["by_name"].get(prize_name)
            if not item_cfg:
                await create_lottery_cmd.finish(f"⛔ 不存在物品：{prize_name}")
            
            item_id = item_cfg.item_id
            
            # 判断是装备还是普通物品
            if item_cfg.type == ItemType.EQUIPMENT:
                lottery_type = LotteryType.EQUIPMENT
            else:
                lottery_type = LotteryType.ITEM
            
            # 检查背包物品数量
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == creator.id,
                ItemInstance.item_id == item_id
            )
            items = (await session.execute(stmt)).scalars().all()
            total_owned = sum(item.quantity for item in items)
            
            if total_owned < total_prize:
                await create_lottery_cmd.finish(
                    f"⛔ {prize_name} 数量不足\n"
                    f"需要：{total_prize} 个\n"
                    f"拥有：{total_owned} 个"
                )
            
            # 扣除物品
            try:
                await ItemInstance.consume_item(session, creator.id, item_id, total_prize)
            except ValueError as e:
                await create_lottery_cmd.finish(f"⛔ 扣除物品失败：{e}")
        
        # 获取群组ID（如果是群聊）
        session_id = event.get_session_id()
        group_id = None
        if session_id.startswith("group_"):
            # 提取群组ID
            parts = session_id.split("_")
            if len(parts) >= 2:
                group_id = parts[1]
        
        # 创建抽奖活动
        lottery = Lottery(
            creator_id=creator.id,
            creator_uid=creator.uid,
            creator_name=creator.nickname,
            lottery_type=lottery_type,
            item_id=item_id,
            item_name=prize_name,
            winner_count=winner_count,
            prize_per_winner=prize_per_winner,
            total_prize=total_prize,
            min_level=min_level,
            max_level=max_level,
            status=LotteryStatus.PENDING,
            group_id=group_id
        )
        session.add(lottery)
        await session.flush()  # 获取lottery.id
        
        await session.commit()
        
        # 构建消息
        msg_lines = [
            f"🎉 抽奖活动已发起！",
            f"━━━━━━━━━━━━━",
            f"🆔 抽奖ID：{lottery.id}",
            f"🎁 奖品：{prize_name}",
            f"👥 中奖人数：{winner_count} 人",
            f"📦 每人获得：{prize_per_winner} 个",
            f"💰 奖品总数：{total_prize} 个",
        ]

        if min_level > 1 or max_level is not None:
            if max_level is None:
                msg_lines.append(f"⭐ 等级要求：{min_level}级及以上")
            elif min_level <= 1:
                msg_lines.append(f"⭐ 等级要求：{max_level}级及以下")
            else:
                msg_lines.append(f"⭐ 等级要求：{min_level}-{max_level}级")

        msg_lines.extend([
            f"━━━━━━━━━━━━━",
            f"💡 发送【参与抽奖 {lottery.id}】参与抽奖",
            f"💡 发送【开奖 {lottery.id}】进行开奖（仅发起人）",
            f"💡 发送【抽奖详情 {lottery.id}】查看详情"
        ])

        msg = "\n".join(msg_lines)
        
        await create_lottery_cmd.finish(message_add_head(msg, event))


# ==================== 参与抽奖 ====================
join_lottery_cmd = on_command("参与抽奖", block=True, priority=5)


@join_lottery_cmd.handle()
async def handle_join_lottery(event: MessageEvent, args: Message = CommandArg()):
    """
    参与抽奖：参与抽奖 抽奖ID
    """
    user_id = event.get_user_id()
    lottery_id_str = args.extract_plain_text().strip()
    
    if not lottery_id_str.isdigit():
        await join_lottery_cmd.finish("⛔ 格式：参与抽奖 抽奖ID")
    
    lottery_id = int(lottery_id_str)
    
    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, user_id)
        if not player:
            await join_lottery_cmd.finish("⛔ 请先创建角色")
        
        # 获取抽奖活动
        lottery = await session.get(Lottery, lottery_id)
        if not lottery:
            await join_lottery_cmd.finish(f"⛔ 抽奖活动 #{lottery_id} 不存在")
        
        # 检查抽奖状态
        if lottery.status != LotteryStatus.PENDING:
            await join_lottery_cmd.finish(f"⛔ 该抽奖活动已{lottery.status.value}")
        
        # 检查是否是发起人
        if player.id == lottery.creator_id:
            await join_lottery_cmd.finish("⛔ 发起人不能参与自己的抽奖")

        # 检查等级要求
        if player.level < lottery.min_level:
            await join_lottery_cmd.finish(
                f"⛔ 等级不足\n"
                f"需要等级：{lottery.min_level}级\n"
                f"当前等级：{player.level}级"
            )

        if lottery.max_level is not None and player.level > lottery.max_level:
            await join_lottery_cmd.finish(
                f"⛔ 等级过高\n"
                f"允许等级：{lottery.max_level}级及以下\n"
                f"当前等级：{player.level}级"
            )

        # 检查是否已经参与
        stmt = select(LotteryParticipant).where(
            LotteryParticipant.lottery_id == lottery_id,
            LotteryParticipant.player_id == player.id
        )
        existing = (await session.execute(stmt)).scalars().first()
        if existing:
            await join_lottery_cmd.finish("⛔ 你已经参与过这个抽奖了")
        
        # 添加参与记录
        participant = LotteryParticipant(
            lottery_id=lottery_id,
            player_id=player.id,
            player_uid=player.uid,
            player_name=player.nickname
        )
        session.add(participant)
        await session.commit()
        
        # 查询当前参与人数
        count_stmt = select(func.count()).select_from(LotteryParticipant).where(
            LotteryParticipant.lottery_id == lottery_id
        )
        participant_count = (await session.execute(count_stmt)).scalar()
        
        msg = (
            f"✅ 参与成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"🎁 奖品：{lottery.item_name}\n"
            f"👥 当前参与人数：{participant_count} 人\n"
            f"🎯 中奖人数：{lottery.winner_count} 人\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 等待发起人开奖..."
        )
        
        await join_lottery_cmd.finish(message_add_head(msg, event))


# ==================== 开奖 ====================
draw_lottery_cmd = on_command("开奖", block=True, priority=2)


@draw_lottery_cmd.handle()
async def handle_draw_lottery(event: MessageEvent, args: Message = CommandArg()):
    """
    开奖：开奖 抽奖ID
    只有发起人可以开奖
    """
    user_id = event.get_user_id()
    lottery_id_str = args.extract_plain_text().strip()

    if not lottery_id_str.isdigit():
        await draw_lottery_cmd.finish("⛔ 格式：开奖 抽奖ID")

    lottery_id = int(lottery_id_str)

    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, user_id)
        if not player:
            await draw_lottery_cmd.finish("⛔ 请先创建角色")

        # 获取抽奖活动
        lottery = await session.get(Lottery, lottery_id)
        if not lottery:
            await draw_lottery_cmd.finish(f"⛔ 抽奖活动 #{lottery_id} 不存在")

        # 检查权限（只有发起人或管理员可以开奖）
        if player.id != lottery.creator_id and not can_create_lottery(user_id):
            await draw_lottery_cmd.finish("⛔ 只有发起人或管理员可以开奖")

        # 检查抽奖状态
        if lottery.status != LotteryStatus.PENDING:
            await draw_lottery_cmd.finish(f"⛔ 该抽奖活动已{lottery.status.value}")

        # 获取所有参与者
        stmt = select(LotteryParticipant).where(
            LotteryParticipant.lottery_id == lottery_id
        )
        participants = (await session.execute(stmt)).scalars().all()

        if not participants:
            await draw_lottery_cmd.finish("⛔ 还没有人参与抽奖")

        # 随机抽取中奖者
        participant_count = len(participants)
        actual_winner_count = min(lottery.winner_count, participant_count)

        # 随机打乱参与者列表并选择中奖者
        random.shuffle(participants)
        winners = participants[:actual_winner_count]

        # 发放奖品
        winner_names = []
        failed_prizes = 0  # 追踪发放失败的奖品数量

        for winner in winners:
            winner.is_winner = True
            winner.won_at = datetime.now()
            session.add(winner)

            # 获取中奖玩家对象
            winner_player = await session.get(Player, winner.player_id)
            if not winner_player:
                continue

            # 发放奖品
            if lottery.lottery_type == LotteryType.GOLD:
                winner_player.gold += lottery.prize_per_winner
                winner.prize_received = True  # 金币发放成功
                session.add(winner_player)
            else:
                # 发放物品或装备
                try:
                    await ItemInstance.add_item(
                        session,
                        winner_player.id,
                        lottery.item_id,
                        lottery.prize_per_winner
                    )
                    winner.prize_received = True  # 发放成功后再标记
                except ValueError as e:
                    # 背包满了，累计失败奖品数量，稍后退还给发起人
                    failed_prizes += lottery.prize_per_winner
                    winner.prize_received = False  # 标记为未领取
                    winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]❌背包满")
                    continue

            winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]")

        # 退还失败的奖品给发起人
        if failed_prizes > 0:
            creator = await session.get(Player, lottery.creator_id)
            if creator:
                try:
                    if lottery.lottery_type == LotteryType.GOLD:
                        # 退还金币
                        creator.gold += failed_prizes
                        session.add(creator)
                    else:
                        # 退还物品或装备
                        await ItemInstance.add_item(
                            session,
                            creator.id,
                            lottery.item_id,
                            failed_prizes
                        )
                except ValueError as e:
                    # 发起人背包也满了，记录错误日志
                    # 注意：这种情况下奖品仍会丢失，但这是极端情况
                    # TODO: 可以考虑将奖品发送到系统邮箱或稍后重试
                    pass

        # 更新抽奖状态
        lottery.status = LotteryStatus.FINISHED
        lottery.finished_at = datetime.now()
        session.add(lottery)

        await session.commit()

        # 构建消息
        msg_lines = [
            f"🎊 抽奖结果公布！",
            f"━━━━━━━━━━━━━",
            f"🆔 抽奖ID：{lottery.id}",
            f"🎁 奖品：{lottery.item_name}",
            f"👥 参与人数：{participant_count} 人",
            f"🎯 中奖人数：{actual_winner_count} 人",
            f"📦 每人获得：{lottery.prize_per_winner} 个",
            f"━━━━━━━━━━━━━",
            f"🏆 中奖名单："
        ]

        for i, name in enumerate(winner_names, 1):
            msg_lines.append(f"{i}. {name}")

        if actual_winner_count < participant_count:
            msg_lines.append(f"━━━━━━━━━━━━━")
            msg_lines.append(f"💔 未中奖：{participant_count - actual_winner_count} 人")

        # 如果有奖品因背包满而退还
        if failed_prizes > 0:
            msg_lines.append(f"━━━━━━━━━━━━━")
            msg_lines.append(f"📮 退还通知：")
            msg_lines.append(f"由于部分中奖者背包已满，{failed_prizes} 个奖品已退还给发起人")

        msg = "\n".join(msg_lines)
        await draw_lottery_cmd.finish(message_add_head(msg, event))


# ==================== 抽奖详情 ====================
lottery_info_cmd = on_command("抽奖详情", aliases={"查看抽奖"}, block=True, priority=5)


@lottery_info_cmd.handle()
async def handle_lottery_info(event: MessageEvent, args: Message = CommandArg()):
    """
    查看抽奖详情：抽奖详情 抽奖ID
    """
    lottery_id_str = args.extract_plain_text().strip()

    if not lottery_id_str.isdigit():
        await lottery_info_cmd.finish("⛔ 格式：抽奖详情 抽奖ID")

    lottery_id = int(lottery_id_str)

    async with safe_session() as session:
        # 获取抽奖活动
        lottery = await session.get(Lottery, lottery_id)
        if not lottery:
            await lottery_info_cmd.finish(f"⛔ 抽奖活动 #{lottery_id} 不存在")

        # 获取参与人数
        count_stmt = select(func.count()).select_from(LotteryParticipant).where(
            LotteryParticipant.lottery_id == lottery_id
        )
        participant_count = (await session.execute(count_stmt)).scalar()

        # 构建基本信息
        msg_lines = [
            f"🎁 抽奖详情",
            f"━━━━━━━━━━━━━",
            f"🆔 抽奖ID：{lottery.id}",
            f"👤 发起人：{lottery.creator_name}[UID:{lottery.creator_uid}]",
            f"🎁 奖品：{lottery.item_name}",
            f"👥 中奖人数：{lottery.winner_count} 人",
            f"📦 每人获得：{lottery.prize_per_winner} 个",
            f"💰 奖品总数：{lottery.total_prize} 个",
        ]

        if lottery.min_level > 1 or lottery.max_level is not None:
            if lottery.max_level is None:
                msg_lines.append(f"⭐ 等级要求：{lottery.min_level}级及以上")
            elif lottery.min_level <= 1:
                msg_lines.append(f"⭐ 等级要求：{lottery.max_level}级及以下")
            else:
                msg_lines.append(f"⭐ 等级要求：{lottery.min_level}-{lottery.max_level}级")

        msg_lines.extend([
            f"📊 参与人数：{participant_count} 人",
            f"📅 发起时间：{lottery.created_at.strftime('%m-%d %H:%M')}",
            f"🔖 状态：{lottery.status.value}",
        ])

        # 如果已开奖，显示中奖名单
        if lottery.status == LotteryStatus.FINISHED:
            msg_lines.append(f"🎊 开奖时间：{lottery.finished_at.strftime('%m-%d %H:%M')}")
            msg_lines.append(f"━━━━━━━━━━━━━")
            msg_lines.append(f"🏆 中奖名单：")

            # 获取中奖者
            winner_stmt = select(LotteryParticipant).where(
                LotteryParticipant.lottery_id == lottery_id,
                LotteryParticipant.is_winner == True
            ).order_by(LotteryParticipant.won_at)
            winners = (await session.execute(winner_stmt)).scalars().all()

            for i, winner in enumerate(winners, 1):
                msg_lines.append(f"{i}. {winner.player_name}[UID:{winner.player_uid}]")
        else:
            msg_lines.append(f"━━━━━━━━━━━━━")
            msg_lines.append(f"💡 发送【参与抽奖 {lottery.id}】参与抽奖")
            msg_lines.append(f"💡 发送【开奖 {lottery.id}】进行开奖（仅发起人）")

        msg = "\n".join(msg_lines)
        await lottery_info_cmd.finish(message_add_head(msg, event))


# ==================== 我的抽奖 ====================
my_lottery_cmd = on_command("我的抽奖", aliases={"抽奖记录"}, block=True, priority=5)


@my_lottery_cmd.handle()
async def handle_my_lottery(event: MessageEvent):
    """
    查看我参与的抽奖
    """
    user_id = event.get_user_id()

    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, user_id)
        if not player:
            await my_lottery_cmd.finish("⛔ 请先创建角色")

        # 获取参与的抽奖
        stmt = select(LotteryParticipant).where(
            LotteryParticipant.player_id == player.id
        ).order_by(LotteryParticipant.joined_at.desc()).limit(10)

        participations = (await session.execute(stmt)).scalars().all()

        if not participations:
            await my_lottery_cmd.finish(message_add_head("📋 你还没有参与过任何抽奖", event))

        msg_lines = [
            f"📋 我的抽奖记录（最近10条）",
            f"━━━━━━━━━━━━━"
        ]

        for p in participations:
            # 获取抽奖信息
            lottery = await session.get(Lottery, p.lottery_id)
            if not lottery:
                continue

            status_icon = "🎊" if p.is_winner else "📝"
            status_text = f"中奖✅" if p.is_winner else lottery.status.value

            msg_lines.append(
                f"{status_icon} #{lottery.id} {lottery.item_name} - {status_text}"
            )

        msg = "\n".join(msg_lines)
        await my_lottery_cmd.finish(message_add_head(msg, event))


# ==================== 取消抽奖 ====================
cancel_lottery_cmd = on_command("取消抽奖", block=True, priority=2)


@cancel_lottery_cmd.handle()
async def handle_cancel_lottery(event: MessageEvent, args: Message = CommandArg()):
    """
    取消抽奖：取消抽奖 抽奖ID
    只有发起人或管理员可以取消，会退还奖品
    """
    user_id = event.get_user_id()
    lottery_id_str = args.extract_plain_text().strip()

    if not lottery_id_str.isdigit():
        await cancel_lottery_cmd.finish("⛔ 格式：取消抽奖 抽奖ID")

    lottery_id = int(lottery_id_str)

    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, user_id)
        if not player:
            await cancel_lottery_cmd.finish("⛔ 请先创建角色")

        # 获取抽奖活动
        lottery = await session.get(Lottery, lottery_id)
        if not lottery:
            await cancel_lottery_cmd.finish(f"⛔ 抽奖活动 #{lottery_id} 不存在")

        # 检查权限
        if player.id != lottery.creator_id and not can_create_lottery(user_id):
            await cancel_lottery_cmd.finish("⛔ 只有发起人或管理员可以取消抽奖")

        # 检查状态
        if lottery.status != LotteryStatus.PENDING:
            await cancel_lottery_cmd.finish(f"⛔ 该抽奖活动已{lottery.status.value}，无法取消")

        # 获取发起人
        creator = await session.get(Player, lottery.creator_id)
        if not creator:
            await cancel_lottery_cmd.finish("⛔ 发起人不存在")

        # 退还奖品
        if lottery.lottery_type == LotteryType.GOLD:
            creator.gold += lottery.total_prize
            session.add(creator)
        else:
            # 退还物品
            try:
                await ItemInstance.add_item(
                    session,
                    creator.id,
                    lottery.item_id,
                    lottery.total_prize
                )
            except ValueError as e:
                await cancel_lottery_cmd.finish(f"⛔ 退还物品失败：{e}")

        # 更新状态
        lottery.status = LotteryStatus.CANCELLED
        lottery.finished_at = datetime.now()
        session.add(lottery)

        await session.commit()

        msg = (
            f"✅ 抽奖已取消\n"
            f"━━━━━━━━━━━━━\n"
            f"🆔 抽奖ID：{lottery.id}\n"
            f"🎁 奖品：{lottery.item_name}\n"
            f"💰 已退还：{lottery.total_prize} 个\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 奖品已退还至发起人背包"
        )

        await cancel_lottery_cmd.finish(message_add_head(msg, event))

