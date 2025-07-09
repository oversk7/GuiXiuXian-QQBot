from __future__ import annotations

"""跑商系统

规则：
1. 仅限现实世界（region == "大都市"）。
2. 商人坐标固定；列表见 MERCHANTS。
3. 价格：每天 09:00 刷新，基于日期+商人ID+item_id 生成哈希随机数。
   - 出售价 = base_price * rand(0.8,1.2)
   - 收购价 = 出售价 * 0.7（向上取整）
4. 指令：
   • 商店            查看当前坐标商人价格表
   • 购买 物品 数量   消耗金币购买
   • 卖出 物品 数量   将背包物品卖给商人
5. 必须玩家坐标与商人坐标一致才可交易。
"""

from datetime import datetime, time, timedelta, date
import random
from typing import Dict, Tuple, List

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..utils import message_add_head
from ..config import config

# ------------------- 商人配置 -------------------
class Merchant:
    def __init__(self, mid: str, name: str, coord: Tuple[int, int], items: List[str]):
        self.id = mid
        self.name = name
        self.x, self.y = coord
        self.items = items

MERCHANTS: List[Merchant] = [
    Merchant("old_goods", "旧货商", (120, 200), [
        "teleport", "heal_potion", "spirit_herb", "ghost_tears", "spirit_bone"
    ]),
    Merchant("occultist", "异物商", (450, 650), [
        "yin_essence", "nightmare_silk", "flesh_crystal", "revive_potion"
    ]),
    Merchant("herbalist", "草药商", (800, 150), [
        "yin_grass", "spirit_herb", "heal_potion", "blood_pact"
    ]),
]

MERCHANT_BY_COORD: Dict[Tuple[int, int], Merchant] = {(m.x, m.y): m for m in MERCHANTS}

# ------------------- 工具函数 -------------------
_DEF_TIME = time(hour=9)


def _current_seed_day() -> date:
    """返回当前价格所属日期：若当前时间 <09:00 视为前一天。"""
    now = datetime.now()
    day = now.date()
    if now.time() < _DEF_TIME:
        day -= timedelta(days=1)
    return day


def _get_rng(merchant_id: str, item_id: str) -> random.Random:
    seed_str = f"{merchant_id}:{item_id}:{_current_seed_day().isoformat()}"
    return random.Random(hash(seed_str))


def _price_for(merchant: Merchant, item_id: str) -> Tuple[int, int]:
    """返回 (sell_price,buy_price) 整数金币"""
    item_cfg = config.items_config["by_id"].get(item_id)
    base_price = item_cfg.price or 1
    rng = _get_rng(merchant.id, item_id)
    factor = rng.uniform(0.8, 1.2)
    sell_price = max(1, int(base_price * factor))
    buy_price = max(1, int(sell_price * 0.7))
    return sell_price, buy_price

# ------------------- 指令 -------------------
shop_cmd = on_command("商店", aliases={"商人"}, block=True, priority=5)

@shop_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await shop_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都市":
            await shop_cmd.finish("⛔ 诡域中没有安全商人！")

        merchant = MERCHANT_BY_COORD.get((player.x, player.y))
        if not merchant:
            await shop_cmd.finish("⛔ 这里没有商人驻扎。")

        lines = [f"🏪 {merchant.name} ({merchant.x},{merchant.y})", "━━━━━━━━━━━━━"]
        for iid in merchant.items:
            item_cfg = config.items_config["by_id"].get(iid)
            sell_p, buy_p = _price_for(merchant, iid)
            lines.append(f"{item_cfg.name}│买 {sell_p}│卖 {buy_p}")
        lines.append("━━━━━━━━━━━━━\n⬇️ 【购买 物品 数量】或【卖出 物品 数量】")
        await shop_cmd.finish(message_add_head("\n".join(lines), event))

# -------- 购买 --------
buy_cmd = on_command("购买", block=True, priority=5)

@buy_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await buy_cmd.finish("📦 格式：购买 物品名 数量")
    item_name, qty_str = parts
    if not qty_str.isdigit():
        await buy_cmd.finish("❌ 数量需为正整数")
    qty = int(qty_str)
    if qty <= 0:
        await buy_cmd.finish("❌ 数量需大于0")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await buy_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都市":
            await buy_cmd.finish("⛔ 诡域中无法与商人交易")
        merchant = MERCHANT_BY_COORD.get((player.x, player.y))
        if not merchant:
            await buy_cmd.finish("⛔ 这里没有商人")
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg or item_cfg.item_id not in merchant.items:
            await buy_cmd.finish("⛔ 商人不出售该物品")

        sell_p, _ = _price_for(merchant, item_cfg.item_id)
        total_cost = sell_p * qty
        if player.gold < total_cost:
            await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")

        # 背包容量检查
        result = await session.execute(
            select(Inventory).where(Inventory.player_id == player.id)
        )
        item_count = len(result.scalars().all())
        inv_record = await session.execute(
            select(Inventory).where(Inventory.player_id == player.id, Inventory.item_id == item_cfg.item_id)
        )
        inv_item = inv_record.scalars().first()
        if not inv_item and item_count >= player.inventory_capacity:
            await buy_cmd.finish("🎒 背包已满，无法购买新物品！")

        # 扣款 & 添物
        player.gold -= total_cost
        if inv_item:
            inv_item.quantity += qty
        else:
            session.add(Inventory(player_id=player.id, item_id=item_cfg.item_id, quantity=qty))
        await session.commit()
        await buy_cmd.finish(message_add_head(
            f"✅ 购买 {item_cfg.name}×{qty} 成功！\n💸 花费 {total_cost} 金币", event))

# -------- 卖出 --------
sell_cmd = on_command("卖出", aliases={"出售"}, block=True, priority=5)

@sell_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await sell_cmd.finish("📦 格式：卖出 物品名 数量")
    item_name, qty_str = parts
    if not qty_str.isdigit():
        await sell_cmd.finish("❌ 数量需为正整数")
    qty = int(qty_str)
    if qty <= 0:
        await sell_cmd.finish("❌ 数量必须大于0")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await sell_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都市":
            await sell_cmd.finish("⛔ 诡域中无法与商人交易！")
        merchant = MERCHANT_BY_COORD.get((player.x, player.y))
        if not merchant:
            await sell_cmd.finish("⛔ 这里只有风～没有商人")
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg or item_cfg.item_id not in merchant.items:
            await sell_cmd.finish("⛔ 商人不收购该物品")

        # 检查库存
        inv_q = await session.execute(
            select(Inventory).where(Inventory.player_id == player.id, Inventory.item_id == item_cfg.item_id)
        )
        inv_item = inv_q.scalars().first()
        if not inv_item or inv_item.quantity < qty:
            await sell_cmd.finish("❌ 背包数量不足")

        _, buy_price = _price_for(merchant, item_cfg.item_id)
        total_gain = buy_price * qty

        # 更新
        inv_item.quantity -= qty
        if inv_item.quantity <= 0:
            await session.delete(inv_item)
        player.gold += total_gain
        await session.commit()
        await sell_cmd.finish(message_add_head(
            f"💰 卖出 {item_cfg.name}×{qty} 成功！\n🪙 获得 {total_gain} 金币", event)) 