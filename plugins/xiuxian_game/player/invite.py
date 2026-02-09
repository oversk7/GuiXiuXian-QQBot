from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from pathlib import Path
from typing import Dict, Tuple
from datetime import datetime
import yaml
from ..models.db import safe_session
from ..models.player import Player
from ..models.invite_reward import InviteReward
from ..utils import message_add_head
from .invite_reward_service_new import InviteRewardService
from sqlalchemy import select
from ..platform_utils import get_unified_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的InviteRewardService，False使用旧版本
# =====================================================

# ---------------- 配置常量 ----------------
MULTIPLIER = 97
OFFSET = 12345

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "invite_records.yaml"
DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------- 工具函数 ----------------

def _base36_encode(num: int) -> str:
    """10 进制整数 -> 大写 36 进制字符串"""
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if num == 0:
        return "0"
    arr = []
    while num:
        num, rem = divmod(num, 36)
        arr.append(digits[rem])
    return "".join(reversed(arr))


def _base36_decode(code: str) -> int | None:
    try:
        num = int(code, 36)
        if num < OFFSET or (num - OFFSET) % MULTIPLIER != 0:
            return None
        return (num - OFFSET) // MULTIPLIER
    except ValueError:
        return None


def generate_invite_code(uid: int) -> str:
    crypto = uid * MULTIPLIER + OFFSET
    return _base36_encode(crypto)


def decode_invite_code(code: str) -> int | None:
    return _base36_decode(code.upper())


def load_records() -> Dict[str, int]:
    if DATA_PATH.exists():
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return {str(k): int(v) for k, v in data.items()}
        except yaml.YAMLError:
            pass
    return {}


def save_records(data: Dict[str, int]):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)

# ---------------- 指令 ----------------

invite_cmd = on_command("邀请码", aliases={"我的邀请码"}, block=True, priority=5)
bind_cmd = on_command("绑定邀请码", aliases={"使用邀请码"}, block=True, priority=5)
invite_status_cmd = on_command("邀请状态", aliases={"邀请奖励状态"}, block=True, priority=5)

# 旧版奖励配置（保留用于显示邀请码信息）
# 邀请者：首邀 10000，每多 1 人 +5000，单次奖励最高 30000
BASE_INVITER_REWARD = 10_000
INVITER_REWARD_STEP = 5_000
INVITER_REWARD_MAX = 30_000

# 初始绑定奖励（立即发放）
INITIAL_INVITEE_REWARD = 2000
INITIAL_INVITER_REWARD = 5000


@invite_cmd.handle()
async def _(event: MessageEvent):
    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await invite_cmd.finish("⛔ 请先创建角色")

        code = generate_invite_code(player.uid)

        # 创建InviteRewardService实例
        invite_reward_service = InviteRewardService(
            invite_reward_repo=uow.invite_rewards,
            player_repo=uow.players
        )

        # 获取邀请状态信息 (使用新版本)
        invite_status = await invite_reward_service.get_invite_status(player.uid)
        invite_count = invite_status["invited_count"]

        # 获取待发放奖励信息 (使用新版本)
        pending_rewards = await invite_reward_service.get_pending_rewards_info(player.uid)
    msg = (
        f"📮 你的邀请码：{code}\n"
        f"🎉 已成功邀请：{invite_count} 人\n"
        "━━━━━━━━━━━━━\n"
        "🎁 分级奖励说明：\n"
        "• 绑定时：邀请者+5000金币，被邀请者+2000金币\n"
        "• 1级时：邀请者+3000金币，被邀请者+1000金币\n"
        "• 10级时：邀请者+8000金币，被邀请者+3000金币\n"
        "• 50级时：邀请者+20000金币，被邀请者+8000金币\n"
    )

    if pending_rewards:
        msg += "━━━━━━━━━━━━━\n🎁 待发放奖励：\n"
        for reward in pending_rewards:
            msg += f"• {reward['invitee_name']}({reward['invitee_level']}级) - {reward['reward_level']}级奖励：+{reward['inviter_gold']}金币\n"

    msg += f"\n将该码发送给好友，让 TA 发送 '/绑定邀请码 {code}' 双方均可获得奖励！"

    await invite_cmd.finish(message_add_head(msg, event))


@bind_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    code_str = args.extract_plain_text().strip().upper()
    if not code_str:
        await bind_cmd.finish("⛔ 格式错误，示例：绑定邀请码 ABC123")

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await bind_cmd.finish("⛔ 请先创建角色")

        # 判断是否已绑定（检查新的数据库记录）
        existing_record_stmt = select(InviteReward).where(InviteReward.invitee_uid == player.uid)
        existing_record_result = await uow.session.execute(existing_record_stmt)
        existing_record = existing_record_result.scalars().first()

        if existing_record:
            await bind_cmd.finish("⛔ 你已绑定过邀请码，无法重复绑定")

        # 兼容旧版记录检查
        records = load_records()
        if str(player.uid) in records:
            await bind_cmd.finish("⛔ 你已绑定过邀请码，无法重复绑定")

        inviter_uid = decode_invite_code(code_str)
        if inviter_uid is None:
            await bind_cmd.finish("⛔ 无效的邀请码")
        if inviter_uid == player.uid:
            await bind_cmd.finish("⛔ 不能绑定自己的邀请码！")

        # 检查邀请者是否存在
        inviter_stmt = select(Player).where(Player.uid == inviter_uid)
        inviter = (await uow.session.execute(inviter_stmt)).scalars().first()
        if not inviter:
            await bind_cmd.finish("⛔ 邀请码无效或邀请者不存在")

        # 创建InviteRewardService实例
        invite_reward_service = InviteRewardService(
            invite_reward_repo=uow.invite_rewards,
            player_repo=uow.players
        )

        # ---------------- 创建邀请记录并发放初始奖励 ----------------
        # 创建新的邀请记录 (使用新版本)
        invite_record = await invite_reward_service.create_invite_record(player.uid, inviter_uid)

        # 发放初始绑定奖励
        player.gold += INITIAL_INVITEE_REWARD
        inviter.gold += INITIAL_INVITER_REWARD

        # 如果玩家已经达到1级，立即发放1级奖励
        level_1_reward_msg = ""
        if player.level >= 1:
            level_1_reward = InviteRewardService.LEVEL_REWARDS[1]
            player.gold += level_1_reward["invitee_gold"]
            inviter.gold += level_1_reward["inviter_gold"]
            invite_record.level_1_rewarded = True
            invite_record.level_1_rewarded_at = datetime.now()
            level_1_reward_msg = f"\n🎉 1级奖励同时发放：邀请者+{level_1_reward['inviter_gold']}，被邀请者+{level_1_reward['invitee_gold']}"

        # UoW会在__aexit__中自动commit

        # 兼容性：写入旧版记录文件
        records = load_records()
        records[str(player.uid)] = inviter_uid
        save_records(records)

        await bind_cmd.finish(
            message_add_head(
                f"✅ 绑定成功！\n"
                f"🎁 被邀请者 {player.nickname} 获得 💰{INITIAL_INVITEE_REWARD} 金币\n"
                f"🎁 邀请者 {inviter.nickname} 获得 💰{INITIAL_INVITER_REWARD} 金币"
                + level_1_reward_msg +
                f"\n━━━━━━━━━━━━━\n"
                f"📈 后续奖励将在达到10级、50级时自动发放！",
                event,
            )
        )
@invite_status_cmd.handle()
async def _(event: MessageEvent):
    """查看邀请奖励状态"""
    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await invite_status_cmd.finish("⛔ 请先创建角色")

        # 创建InviteRewardService实例
        invite_reward_service = InviteRewardService(
            invite_reward_repo=uow.invite_rewards,
            player_repo=uow.players
        )

        # 获取邀请状态信息 (使用新版本)
        invite_status = await invite_reward_service.get_invite_status(player.uid)

        # 在UnitOfWork内部构建完整消息
        msg = f"📊 {player.nickname} 的邀请状态\n━━━━━━━━━━━━━\n"

        # 作为邀请者的信息
        if invite_status["invited_count"] > 0:
            msg += f"👥 已邀请玩家：{invite_status['invited_count']} 人\n"

            # 显示每个被邀请者的奖励状态
            for record in invite_status["inviter_records"]:
                # 获取被邀请者信息（在UnitOfWork内部）
                invitee_stmt = select(Player).where(Player.uid == record.invitee_uid)
                invitee_result = await uow.session.execute(invitee_stmt)
                invitee = invitee_result.scalars().first()

                if invitee:
                    status_icons = []
                    if record.level_1_rewarded:
                        status_icons.append("✅1级")
                    else:
                        status_icons.append("❌1级")

                    if record.level_10_rewarded:
                        status_icons.append("✅10级")
                    elif invitee.level >= 10:
                        status_icons.append("🎁10级")
                    else:
                        status_icons.append("❌10级")

                    if record.level_50_rewarded:
                        status_icons.append("✅50级")
                    elif invitee.level >= 50:
                        status_icons.append("🎁50级")
                    else:
                        status_icons.append("❌50级")

                    msg += f"  • {invitee.nickname}(Lv.{invitee.level}) {' '.join(status_icons)}\n"
        else:
            msg += "👥 尚未邀请任何玩家\n"

        # 作为被邀请者的信息
        if invite_status["invitee_record"]:
            record = invite_status["invitee_record"]
            inviter_stmt = select(Player).where(Player.uid == record.inviter_uid)
            inviter_result = await uow.session.execute(inviter_stmt)
            inviter = inviter_result.scalars().first()

            if inviter:
                msg += f"━━━━━━━━━━━━━\n"
                msg += f"🎯 被 {inviter.nickname} 邀请\n"

                status_msg = []
                if record.level_1_rewarded:
                    status_msg.append("✅1级奖励已领取")
                if record.level_10_rewarded:
                    status_msg.append("✅10级奖励已领取")
                elif player.level >= 10:
                    status_msg.append("🎁10级奖励待发放")
                if record.level_50_rewarded:
                    status_msg.append("✅50级奖励已领取")
                elif player.level >= 50:
                    status_msg.append("🎁50级奖励待发放")

                if status_msg:
                    msg += "  " + "\n  ".join(status_msg)

        msg += "\n━━━━━━━━━━━━━\n"
        msg += "💡 说明：✅已领取 🎁待发放 ❌未达成"

    await invite_status_cmd.finish(message_add_head(msg, event))