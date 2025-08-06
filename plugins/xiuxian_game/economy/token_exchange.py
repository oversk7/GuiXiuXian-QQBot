"""
扫荡令兑换系统

提供扫荡令兑换真还魂丹的功能，作为氪金玩家的专属货币兑换渠道
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..utils import message_add_head

__all__ = [
    "token_exchange_cmd",
    "exchange_elixir_cmd",
]

# 兑换配置
EXCHANGE_CONFIG = {
    "sweep_token_to_supreme_revive": {
        "input_item": "sweep_token",
        "input_name": "扫荡令",
        "output_item": "supreme_revive_elixir",
        "output_name": "真还魂丹",
        "exchange_rate": 2,  # 2个扫荡令兑换1个真还魂丹
        "description": "氪金玩家专属兑换：2个扫荡令兑换1个真还魂丹"
    }
}

# ---------------- 指令注册 ----------------

token_exchange_cmd = on_command(
    "扫荡令兑换",
    aliases={"令牌兑换", "扫荡兑换"},
    block=True,
    priority=5,
)

exchange_elixir_cmd = on_command(
    "兑换真还魂丹",
    aliases={"兑换还魂丹"},
    block=True,
    priority=5,
)

# ---------------- 指令处理 ----------------

@token_exchange_cmd.handle()
async def handle_token_exchange(event: MessageEvent):
    """查看扫荡令兑换商店"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await token_exchange_cmd.finish("⛔ 请先创建角色")

        # 获取玩家的扫荡令数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "sweep_token"
        )
        result = await session.execute(stmt)
        sweep_token_item = result.scalar_one_or_none()
        sweep_token_count = sweep_token_item.quantity if sweep_token_item else 0

        # 获取玩家的真还魂丹数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "supreme_revive_elixir"
        )
        result = await session.execute(stmt)
        elixir_item = result.scalar_one_or_none()
        elixir_count = elixir_item.quantity if elixir_item else 0

        lines = [
            "⚡ 扫荡令兑换商店",
            "━━━━━━━━━━━━━",
            f"💰 你的扫荡令：{sweep_token_count}",
            f"💊 你的真还魂丹：{elixir_count}",
            "",
            "🛒 可兑换物品：",
            "1. 真还魂丹 - 2扫荡令/个 (无限制)",
            "",
            "💡 兑换说明：",
            "• 扫荡令是氪金玩家的专属货币",
            "• 通过月卡签到获得扫荡令",
            "• 可用扫荡令兑换珍贵的真还魂丹",
            "• 氪金玩家专享，无每日限制",
            "",
            "📝 操作指南：",
            "【兑换真还魂丹 数量】 - 兑换真还魂丹",
            "例如：兑换真还魂丹 5"
        ]

        await token_exchange_cmd.finish(message_add_head("\n".join(lines), event))


@exchange_elixir_cmd.handle()
async def handle_exchange_elixir(event: MessageEvent, args: Message = CommandArg()):
    """兑换真还魂丹"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await exchange_elixir_cmd.finish("⛔ 格式：兑换真还魂丹 <数量>")

    try:
        quantity = int(args_text)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await exchange_elixir_cmd.finish("⛔ 数量必须是正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await exchange_elixir_cmd.finish("⛔ 请先创建角色")

        config_data = EXCHANGE_CONFIG["sweep_token_to_supreme_revive"]
        exchange_rate = config_data["exchange_rate"]

        # 计算需要的扫荡令数量
        required_tokens = quantity * exchange_rate

        # 检查玩家的扫荡令数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "sweep_token"
        )
        result = await session.execute(stmt)
        sweep_token_item = result.scalar_one_or_none()
        
        if not sweep_token_item or sweep_token_item.quantity < required_tokens:
            current_tokens = sweep_token_item.quantity if sweep_token_item else 0
            await exchange_elixir_cmd.finish(
                f"⛔ 扫荡令不足！需要{required_tokens}个，当前拥有{current_tokens}个"
            )

        # 扣除扫荡令
        try:
            await ItemInstance.consume_item(session, player.id, "sweep_token", required_tokens)
        except ValueError as e:
            await exchange_elixir_cmd.finish(f"⛔ 扣除扫荡令失败：{e}")

        # 添加真还魂丹
        try:
            await ItemInstance.add_item(session, player.id, "supreme_revive_elixir", quantity)
        except ValueError as e:
            # 如果添加失败，需要回滚扫荡令
            await ItemInstance.add_item(session, player.id, "sweep_token", required_tokens)
            await exchange_elixir_cmd.finish(f"⛔ 背包空间不足：{e}")

        await session.commit()

        await exchange_elixir_cmd.finish(message_add_head(
            f"✅ 兑换成功！\n"
            f"💸 消耗：扫荡令×{required_tokens}\n"
            f"💊 获得：真还魂丹×{quantity}",
            event
        ))
