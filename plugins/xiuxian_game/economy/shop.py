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
        "购买 [商品序号|名称] [数量] - 购买商品",
        "出售 [背包序号|名称] [数量] - 出售材料",
        "（数量需为正整数）"
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
        await buy_item.finish(
            "⛔ 格式错误，正确示例：购买 2 3 或 购买 传送符 2"
        )
    
    # 解析数量（默认 1）
    try:
        quantity = int(args_list[1]) if len(args_list) == 2 else 1
        if quantity < 1:
            raise ValueError
    except ValueError:
        await buy_item.finish("⛔ 数量必须为正整数")

    # 判断数字序号还是商品名称
    is_index_mode = args_list[0].isdigit()

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await buy_item.finish("⛔ 请先创建角色")
        
        # 获取商店商品列表
        sell_list = generate_common_shop()
        
        if is_index_mode:
            # -------------------------------
            #   序号购买模式
            # -------------------------------
            try:
                index = int(args_list[0]) - 1
                if index < 0:
                    raise ValueError
            except ValueError:
                await buy_item.finish("⛔ 无效的商品序号")

            if index >= len(sell_list):
                await buy_item.finish("⛔ 无效的商品序号")

            item_config, price = sell_list[index]
        else:
            # -------------------------------
            #   名称购买模式
            # -------------------------------
            item_name = args_list[0]
            match = next(
                ((cfg, pr) for cfg, pr in sell_list if cfg.name == item_name),
                None,
            )
            if not match:
                await buy_item.finish("⛔ 无效的商品名称，或当前未上架")
            item_config, price = match

        total_price = price * quantity
        
        # 金币检查
        if player.gold < total_price:
            await buy_item.finish(
                f"⛔ 金币不足，需要 {total_price}💰 当前拥有 {player.gold}💰"
            )
        
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
    """玩家出售材料换取金币，格式：出售 背包序号|材料名称 [数量]"""
    arg_str = args.extract_plain_text().strip()
    parts = arg_str.split()

    # 参数校验
    if not parts or len(parts) > 2:
        await sell_item.finish("⛔ 格式错误，正确示例：出售 5 3 或 出售 鬼泪 3")

    # 解析数量
    try:
        quantity = int(parts[1]) if len(parts) == 2 else 1
        if quantity < 1:
            raise ValueError
    except ValueError:
        await sell_item.finish("⛔ 数量必须为正整数")

    # 判断首参数是背包序号还是物品名
    is_index_mode = parts[0].isdigit()

    # 根据模式获取物品配置与库存记录
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await sell_item.finish("⛔ 请先创建角色")

        if is_index_mode:
            # -------------------------------
            #   序号出售模式
            # -------------------------------
            try:
                target_index = int(parts[0])
                if target_index < 1:
                    raise ValueError
            except ValueError:
                await sell_item.finish("⛔ 无效的背包序号")

            # 获取该玩家所有背包物品（按 item_id 排序，保证与背包指令一致）
            inv_stmt = (
                select(Inventory)
                .where(Inventory.player_id == event.get_user_id())
                .order_by(Inventory.item_id)
            )
            inv_items = (await session.execute(inv_stmt)).scalars().all()

            if not inv_items or target_index > len(inv_items):
                await sell_item.finish("⛔ 无效的背包序号")

            target_inv = inv_items[target_index - 1]
            item_cfg = target_inv.config

            # 仅允许出售材料
            if item_cfg.type.value != "MATERIAL":
                await sell_item.finish("⛔ 仅可出售材料类物品！")

        else:
            # -------------------------------
            #   名称出售模式（保留原逻辑）
            # -------------------------------
            item_name = parts[0]
            item_cfg = config.items_config["by_name"].get(item_name)
            if not item_cfg or item_cfg.type.value != "MATERIAL":
                await sell_item.finish("⛔ 仅可出售材料类物品！")

            # 检查玩家背包中是否拥有该物品
            inv_stmt = select(Inventory).where(
                Inventory.player_id == event.get_user_id(),
                Inventory.item_id == item_cfg.item_id,
            )
            target_inv = (await session.execute(inv_stmt)).scalars().first()

            if not target_inv:
                await sell_item.finish(f"⛔ {item_cfg.name} 数量不足（当前持有：0）")

        # -------------------------------
        #   通用检查 & 结算流程
        # -------------------------------

        if target_inv.quantity < quantity:
            await sell_item.finish(
                f"⛔ {target_inv.config.name} 数量不足（当前持有：{target_inv.quantity}）"
            )

        # 计算收益
        unit_price = max(1, int(item_cfg.price * SELL_RATIO))
        total_gain = unit_price * quantity

        # 更新库存 & 金币
        target_inv.quantity -= quantity
        if target_inv.quantity == 0:
            await session.delete(target_inv)

        player.gold += total_gain

        await session.commit()

        await sell_item.finish(
            f"✅ 成功出售 {item_cfg.name} ✖️{quantity}\n💰 单价：{unit_price} 金币\n💰 共获得：{total_gain} 金币"
        )
