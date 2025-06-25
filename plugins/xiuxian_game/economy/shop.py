from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..config import config
from ..utils import message_add_head
from sqlalchemy import select

daily_shop = on_command("商店", aliases={"每日商店", "商城", "店铺"}, block=True, priority=5)
buy_item = on_command("购买", block=True, priority=5)

def generate_common_shop() -> list:
    """生成普通商店出售列表[(ItemConfig, price)]"""
    consumable_ids = config.items_config["by_type"].get("CONSUMABLE", [])
    # 过滤掉无价格物品并按价格排序
    items = [config.items_config["by_id"][iid] for iid in consumable_ids]
    items = [i for i in items if i.price and i.price > 0]
    items.sort(key=lambda x: x.price)
    return [(item, item.price) for item in items]

async def format_shop(shop_sell: list, player_gold: int) -> str:
    """普通商店展示格式"""
    content = [
        "🏪 凡人镇 · 常驻商店",
        f"▃▃▃▃▃▃▃▃▃▃▃▃▃",
        f"💰 你的金币：{player_gold}",
        "",
        "🛍️ 可购买物品："
    ]
    
    # 出售列表
    for idx, (item, price) in enumerate(shop_sell, 1):
        content.append(
            f"{idx}. {item.name} - {price}💰/个\n"
            f"   📜 {item.description}"
        )
    
    # 操作说明
    content.extend([
        "\n📝 操作指南：",
        "购买 [物品序号] [数量] - 购买商品",
        "出售 [材料名称] [数量] - 出售材料",
        "（单次购买/出售数量 1-50）"
    ])
    return "\n".join(content)

@daily_shop.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await daily_shop.finish("⛔ 请先创建角色")
        
        # 生成普通商店
        shop_sell = generate_common_shop()
        await daily_shop.finish(
            message_add_head(await format_shop(shop_sell, player.gold), event)
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
        
        # 获取商店商品列表
        sell_list = generate_common_shop()
        
        # 检查序号
        if index < 0 or index >= len(sell_list):
            await buy_item.finish("⛔ 无效的物品序号")
        
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

# -----------------------------------------------------------
# 出售（材料）
# -----------------------------------------------------------

SELL_RATIO: float = 0.5  # 收购价 = 配置价 × 0.5，可根据需要调整

sell_item = on_command("出售", block=True, priority=5)

@sell_item.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """玩家出售材料换取金币，格式：出售 材料名 [数量]"""
    arg_str = args.extract_plain_text().strip()
    parts = arg_str.split()

    # 参数校验
    if not parts or len(parts) > 2:
        await sell_item.finish("⛔ 格式错误，正确示例：出售 鬼泪 3")

    item_name = parts[0]
    try:
        quantity = int(parts[1]) if len(parts) == 2 else 1
        if quantity < 1 or quantity > 50:
            raise ValueError
    except ValueError:
        await sell_item.finish("⛔ 数量必须为 1-50 的整数")

    # 获取物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg or item_cfg.type.value != "MATERIAL":
        await sell_item.finish("⛔ 仅可出售材料类物品！")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await sell_item.finish("⛔ 请先创建角色")

        # 检查玩家背包
        inv_stmt = select(Inventory).where(
            Inventory.player_id == event.get_user_id(),
            Inventory.item_id == item_cfg.item_id
        )
        inv = (await session.execute(inv_stmt)).scalars().first()

        if not inv or inv.quantity < quantity:
            await sell_item.finish(f"⛔ {item_cfg.name} 数量不足（当前持有：{inv.quantity if inv else 0}）")

        # 计算收益
        unit_price = max(1, int(item_cfg.price * SELL_RATIO))
        total_gain = unit_price * quantity

        # 更新库存 & 金币
        inv.quantity -= quantity
        if inv.quantity == 0:
            await session.delete(inv)

        player.gold += total_gain

        await session.commit()

        await sell_item.finish(
            f"✅ 成功出售 {item_cfg.name} ✖️{quantity}\n💰 单价：{unit_price} 金币\n💰 共获得：{total_gain} 金币"
        )
