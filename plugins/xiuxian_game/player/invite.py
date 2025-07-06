from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from pathlib import Path
from typing import Dict
import yaml
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from sqlalchemy import select

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

# 奖励配置
# 邀请者：首邀 10000，每多 1 人 +5000，单次奖励最高 30000
BASE_INVITER_REWARD = 10_000
INVITER_REWARD_STEP = 5_000
INVITER_REWARD_MAX = 30_000

# 受邀者固定奖励
INVITEE_REWARD_GOLD = 5_000


@invite_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await invite_cmd.finish("⛔ 请先创建角色")

        code = generate_invite_code(player.uid)
        records = load_records()
        invite_count = sum(1 for v in records.values() if v == player.uid)
        next_reward = min(BASE_INVITER_REWARD + invite_count * INVITER_REWARD_STEP, INVITER_REWARD_MAX)
        msg = (
            f"📮 你的邀请码：{code}\n"
            f"🎉 已成功邀请：{invite_count} 人\n"
            f"📈 下一位好友成功绑定你将获得：{next_reward} 金币\n"
            f"将该码发送给好友，让 TA 发送 '/绑定邀请码 {code}' 双方均可获得奖励！"
        )
        await invite_cmd.finish(message_add_head(msg, event))


@bind_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    code_str = args.extract_plain_text().strip().upper()
    if not code_str:
        await bind_cmd.finish("⛔ 格式错误，示例：绑定邀请码 ABC123")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await bind_cmd.finish("⛔ 请先创建角色")

        # 判断是否已绑定
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
        inviter = (await session.execute(inviter_stmt)).scalars().first()
        if not inviter:
            await bind_cmd.finish("⛔ 邀请码无效或邀请者不存在")

        # ---------------- 结算奖励 ----------------
        invite_count_before = sum(1 for v in records.values() if v == inviter_uid)
        inviter_reward = min(BASE_INVITER_REWARD + invite_count_before * INVITER_REWARD_STEP,
                             INVITER_REWARD_MAX)

        player.gold += INVITEE_REWARD_GOLD
        inviter.gold += inviter_reward
        await session.commit()

        # 写入记录文件
        records[str(player.uid)] = inviter_uid
        save_records(records)

        await bind_cmd.finish(
            message_add_head(
                f"✅ 绑定成功！\n已获得 💰{INVITEE_REWARD_GOLD} 金币奖励\n"
                f"🎁 邀请者 {inviter.nickname} 获得 💰{inviter_reward} 金币！",
                event,
            )
        ) 