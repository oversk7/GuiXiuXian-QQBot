from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
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
sell_item = on_command("出售", block=True, priority=5)

def generate_daily_shop(player_uid: int) -> tuple:
    """生成每日商店（返回出售列表和收购列表）"""
    today = datetime.now().toordinal()
    random.seed(today + player_uid)
    
    # 出售商品（同原逻辑）
    sellable_items = [item for item in config.items_config["by_id"].values() if item.price > 0]
    sell_list = random.sample(sellable_items, k=5)
    
    # 生成收购商品（只从材料类中选）
    materials = [item for item in config.items_config["by_id"].values() 
                if item.type == "MATERIAL"]
    buy_list = random.sample(materials, k=3)  # 每日收购3种材料
    
    # 处理价格
    shop_sell = []
    for item in sell_list:
        fluctuation = random.uniform(0.7, 1.5)
        shop_sell.append((item, max(1, int(item.price * fluctuation))))
        
    shop_buy = []
    for item in buy_list:
        buy_ratio = random.uniform(0.3, 0.7)  # 收购价是原价的30%-70%
        shop_buy.append((item, max(1, int(item.price * buy_ratio))))
    
    return shop_sell, shop_buy

async def format_shop(shop_data: tuple, player_gold: int) -> str:
    """新版商店格式"""
    sell_list, buy_list = shop_data
    content = [
        "🏪 黑市商人 · 今日交易",
        f"▃▃▃▃▃▃▃▃▃▃▃▃▃",
        f"💰 你的金币：{player_gold}",
        "",
        "🛍️ 今日出售："
    ]
    
    # 出售列表
    for idx, (item, price) in enumerate(sell_list, 1):
        content.append(
            f"{idx}. {item.name} - {price}💰/个\n"
            f"   📜 {item.description}"
        )
    
    content.append("\n💰 今日收购：")
    # 收购列表（从6开始编号）
    for idx, (item, price) in enumerate(buy_list, len(sell_list)+1):
        content.append(
            f"{idx}. {item.name} - {price}💰/个\n"
            f"   📜 {item.description}"
        )
    
    content.extend([
        "\n📝 操作指南：",
        "购买 [出售列表序号] [数量] - 购买商品",
        "出售 [收购列表序号] [数量] - 出售商品",
        "（单次交易最多50个）"
    ])
    return "\n".join(content)

@daily_shop.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await daily_shop.finish("⛔ 请先创建角色")
        
        # 生成当日商店
        shop_data = generate_daily_shop(player.uid)
        await daily_shop.finish(
            create_rich_message(await format_shop(shop_data, player.gold), event)
        )

@buy_item.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_str = args.extract_plain_text().strip()
    args_list = arg_str.split()
    
    # 参数校验
    if len(args_list) < 1 or len(args_list) > 2:
        await buy_item.finish("⛔ 格式错误，正确格式：购买 序号 [数量]\n例：购买 2 或 购买 3 5")
    
    try:
        index = int(args_list[0]) - 1
        quantity = int(args_list[1]) if len(args_list) > 1 else 1
        if quantity < 1 or quantity > 50:  # 添加购买数量限制
            raise ValueError
    except ValueError:
        await buy_item.finish("⛔ 数量必须为1-50之间的整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await buy_item.finish("⛔ 请先创建角色")
        
        # 获取商店数据（拆分为出售列表和收购列表）
        sell_list, buy_list = generate_daily_shop(player.uid)
        
        # 检查是否是出售列表的序号
        if index < 0 or index >= len(sell_list):
            await buy_item.finish("⛔ 无效的出售序号（请使用商店左侧的出售商品序号）")
        
        # 获取出售物品（从出售列表中获取）
        item_config, price = sell_list[index]
        total_price = price * quantity
        
        # 金币检查
        if player.gold < total_price:
            await buy_item.finish(f"⛔ 金币不足，需要 {total_price}💰 当前拥有 {player.gold}💰")
        
        # 持有量检查
        inv = await session.execute(
            select(Inventory).where(
                Inventory.player_id == event.get_user_id(),
                Inventory.item_id == item_config.item_id
            )
        )
        inv = inv.scalars().first()
        current_quantity = inv.quantity if inv else 0
        if current_quantity + quantity > 50:
            await buy_item.finish(f"⛔ 该物品持有量已达上限（{current_quantity}/50）")
        
        # 扣除金币
        player.gold -= total_price
        
        # 更新库存
        if inv:
            inv.quantity += quantity
        else:
            session.add(Inventory(
                player_id=event.get_user_id(),
                item_id=item_config.item_id,
                quantity=quantity
            ))
        
        await session.commit()
        await buy_item.finish(f"✅ 成功购买 {item_config.name} ✖️{quantity}（单价 {price}💰 总花费 {total_price}💰）")

@sell_item.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_str = args.extract_plain_text().strip()
    args_list = arg_str.split()
    
    if len(args_list) < 1 or len(args_list) > 2:
        await sell_item.finish("⛔ 格式错误，正确格式：出售 序号 [数量]\n例：出售 6 或 出售 7 5")
    
    try:
        index = int(args_list[0]) - 1
        quantity = int(args_list[1]) if len(args_list) > 1 else 1
        if quantity < 1 or quantity > 50:
            raise ValueError
    except ValueError:
        await sell_item.finish("⛔ 数量必须为1-50之间的整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await sell_item.finish("⛔ 请先创建角色")
        
        # 获取商店数据
        sell_list, buy_list = generate_daily_shop(player.uid)
        total_items = len(sell_list) + len(buy_list)
        
        # 检查是否是收购列表的序号（6-8号商品）
        if index < len(sell_list) or index >= (len(sell_list) + len(buy_list)):
            await sell_item.finish("⛔ 无效的收购序号（请使用商店右侧的收购商品序号）")
        
        # 获取收购物品
        buy_index = index - len(sell_list)
        item_config, buy_price = buy_list[buy_index]
        
        # 检查背包物品
        inv = await session.execute(
            select(Inventory).where(
                Inventory.player_id == event.get_user_id(),
                Inventory.item_id == item_config.item_id
            )
        )
        inv = inv.scalars().first()
        
        if not inv or inv.quantity < quantity:
            await sell_item.finish(f"⛔ 没有足够的{item_config.name}（当前持有：{inv.quantity if inv else 0}）")
        
        # 交易处理
        total_gain = buy_price * quantity
        inv.quantity -= quantity
        if inv.quantity == 0:
            await session.delete(inv)
        
        player.gold += total_gain
        await session.commit()
        
        await sell_item.finish(f"✅ 成功出售 {item_config.name} ✖️{quantity} 获得 {total_gain}💰")
