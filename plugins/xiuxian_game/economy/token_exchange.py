"""
月卡兑换系统

提供真还魂丹的功能，作为氪金玩家的专属货币兑换渠道
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..utils_markdown import cmd, build_markdown
from ..platform_utils import require_player

__all__ = [
    "token_exchange_cmd",
    "exchange_elixir_cmd",
]

# 兑换配置
EXCHANGE_CONFIG = {
    "monthly_card_box_to_supreme_revive": {
        "input_item": "monthly_card_box",
        "input_name": "月卡宝箱",
        "output_item": "supreme_revive_elixir",
        "output_name": "真还魂丹",
        "exchange_rate": 2,  # 2个月卡宝箱兑换1个真还魂丹
        "description": "月卡玩家专属兑换：2个月卡宝箱兑换1个真还魂丹"
    }
}

# ---------------- 指令注册 ----------------

token_exchange_cmd = on_command(
    "月卡宝箱兑换",
    aliases={"月卡兑换"},
    block=True,
    priority=7,
)

exchange_elixir_cmd = on_command(
    "兑换真还魂丹",
    aliases={"兑换还魂丹"},
    block=True,
    priority=7,
)

# ---------------- 指令处理 ----------------

@token_exchange_cmd.handle()
async def handle_token_exchange(event: MessageEvent):
    """查看月卡宝箱兑换商店"""
    async with safe_session() as session:
        player = await require_player(session, event, token_exchange_cmd)

        # 获取玩家的月卡宝箱数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "monthly_card_box"
        )
        result = await session.execute(stmt)
        monthly_card_box_item = result.scalar_one_or_none()
        monthly_card_box_count = monthly_card_box_item.quantity if monthly_card_box_item else 0

        # 获取玩家的真还魂丹数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "supreme_revive_elixir"
        )
        result = await session.execute(stmt)
        elixir_item = result.scalar_one_or_none()
        elixir_count = elixir_item.quantity if elixir_item else 0

        content = (
            f"# 💎 月卡宝箱兑换商店\n"
            f"***\n"
            f"💰 你的月卡宝箱：**{monthly_card_box_count}**\n"
            f"💊 你的真还魂丹：**{elixir_count}**\n"
            f"***\n"
            f"🛒 可兑换物品\n"
            f"▫️ {cmd('真还魂丹', '兑换真还魂丹 1')} - **2**月卡宝箱/个\n\n"
            f"💡 月卡用户可以将宝箱兑换成真还魂丹\n"
            f"***\n"
            f"{cmd('兑换真还魂丹 数量', '兑换真还魂丹 ')} | {cmd('月卡宝箱兑换')}"
        )

        await token_exchange_cmd.finish(build_markdown(content))


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
        player = await require_player(session, event, exchange_elixir_cmd)

        config_data = EXCHANGE_CONFIG["monthly_card_box_to_supreme_revive"]
        exchange_rate = config_data["exchange_rate"]

        # 计算需要的月卡宝箱数量
        required_boxes = quantity * exchange_rate

        # 检查玩家的月卡宝箱数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "monthly_card_box"
        )
        result = await session.execute(stmt)
        monthly_card_box_item = result.scalar_one_or_none()

        if not monthly_card_box_item or monthly_card_box_item.quantity < required_boxes:
            current_boxes = monthly_card_box_item.quantity if monthly_card_box_item else 0
            await exchange_elixir_cmd.finish(
                f"⛔ 月卡宝箱不足！需要{required_boxes}个，当前拥有{current_boxes}个"
            )

        # 扣除月卡宝箱
        try:
            await ItemInstance.consume_item(session, player.id, "monthly_card_box", required_boxes)
        except ValueError as e:
            await exchange_elixir_cmd.finish(f"⛔ 扣除月卡宝箱失败：{e}")

        # 添加真还魂丹
        try:
            await ItemInstance.add_item(session, player.id, "supreme_revive_elixir", quantity)
        except ValueError as e:
            # 如果添加失败，需要回滚月卡宝箱
            await ItemInstance.add_item(session, player.id, "monthly_card_box", required_boxes)
            await exchange_elixir_cmd.finish(f"⛔ 背包空间不足：{e}")

        await session.commit()

        content = (
            f"# ✅ 兑换成功\n"
            f"***\n"
            f"💸 消耗：月卡宝箱 x**{required_boxes}**\n"
            f"💊 获得：真还魂丹 x**{quantity}**\n"
            f"***\n"
            f"{cmd('月卡宝箱兑换')} | {cmd('背包')}"
        )
        await exchange_elixir_cmd.finish(build_markdown(content))
