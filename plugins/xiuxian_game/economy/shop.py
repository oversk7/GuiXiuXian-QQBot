from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import MessageEvent, Message
import random
from datetime import datetime
from ..data.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..config import config
from ..utils import create_rich_message
from sqlalchemy import select

daily_shop = on_command("每日商店", aliases={"商店"}, block=True, priority=5)
buy_item = on_command("购买", block=True, priority=5)

def generate_daily_shop(player_uid: int) -> list:
    """生成每日商店商品（带价格波动）"""
    today = datetime.now().toordinal()
    random.seed(today + player_uid)  # 固定种子保证每日一致
    
    all_items = [
        item for item in config.items_config["by_id"].values() 
        if item.price > 0  # 排除不可购买物品
    ]
    selected = random.sample(all_items, k=3)
    
    shop_items = []
    for item in selected:
        # 价格波动 ±20%
        fluctuation = random.uniform(0.8, 1.2)
        current_price = max(1, int(item.price * fluctuation))
        shop_items.append((item, current_price))
    
    return shop_items

async def format_shop(shop_items: list, player_gold: int) -> str:
    """格式化商店展示"""
    content = ["🛍️ 今日商店 | 你的金币：{} 💰".format(player_gold)]
    for idx, (item, price) in enumerate(shop_items, 1):
        content.append(
            f"{idx}. {item.name} - {price}💰\n"
            f"   📜 {item.description}"
        )
    content.append("\n使用【购买 序号】指令进行购买")
    return "\n".join(content)

@daily_shop.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await daily_shop.finish("⛔ 请先创建角色")
        
        # 生成当日商店
        shop_items = generate_daily_shop(player.uid)
        await daily_shop.finish(
            create_rich_message(await format_shop(shop_items, player.gold), event)
        )

@buy_item.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg.isdigit():
        await buy_item.finish("⛔ 请输入要购买的物品序号，例如：购买 2")
    index = int(arg) - 1

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await buy_item.finish("⛔ 请先创建角色")
        
        shop_items = generate_daily_shop(player.uid)
        if index < 0 or index >= len(shop_items):
            await buy_item.finish("⛔ 无效的商品序号")
        
        item_config, price = shop_items[index]
        if player.gold < price:
            await buy_item.finish(f"⛔ 金币不足，需要 {price}💰 当前拥有 {player.gold}💰")
        
        # 扣除金币
        player.gold -= price
        # 添加物品
        inv = await session.execute(
            select(Inventory).where(
                Inventory.player_id == event.get_user_id(),
                Inventory.item_id == item_config.item_id
            )
        )
        inv = inv.scalars().first()
        if inv:
            inv.quantity += 1
        else:
            session.add(Inventory(
                player_id=event.get_user_id(),
                item_id=item_config.item_id,
                quantity=1
            ))
        
        await session.commit()
        await buy_item.finish(f"✅ 成功购买 {item_config.name} ✖️1（花费 {price}💰）")
