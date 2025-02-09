from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from ..data.db import safe_session
from ..models.player import Player
from ..models.item import Inventory, Item
from ..models.item import ItemType, ItemEffectType
from ..utils import create_rich_message, paginate_items
from sqlalchemy import select

inventory_cmd = on_command("背包", aliases={"查看背包"}, block=True, priority=5)
use_item = on_command("使用物品", block=True, priority=5)

@inventory_cmd.handle()
async def handle_inventory(event: MessageEvent, args: Message = CommandArg()):
    page = args.extract_plain_text().strip()
    try:
        page = int(page) if page else 1
    except ValueError:
        page = 1

    async with safe_session() as session:
        # 获取玩家背包数据
        player = await session.get(Player, event.get_user_id())
        if not player:
            await inventory_cmd.finish("⛔ 请先创建角色")

        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == event.get_user_id())
            .order_by(Inventory.item_id)
        )
        items = result.scalars().all()

        if not items:
            await inventory_cmd.finish("🎒 你的背包空无一物")

        # 分页处理
        total_pages = (len(items) - 1) // 10 + 1
        page = max(1, min(page, total_pages))
        
        formatted = await paginate_items(items, page)
        await inventory_cmd.finish(create_rich_message(formatted, event))

@use_item.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await use_item.finish("⛔ 格式错误，正确格式：使用物品 [物品名称] [数量]")

    item_name, quantity = params
    try:
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await use_item.finish("⛔ 数量必须为正整数")

    async with safe_session() as session:
        # 获取玩家和物品信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await use_item.finish("⛔ 请先创建角色")

        # 查找物品
        item_result = await session.execute(
            select(Item).where(Item.name == item_name)
        )
        item = item_result.scalars().first()
        if not item:
            await use_item.finish(f"⛔ 不存在物品：{item_name}")

        # 检查背包中是否有该物品
        inv_result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == event.get_user_id())
            .where(Inventory.item_id == item.item_id)
        )
        inventory = inv_result.scalars().first()
        
        if not inventory or inventory.quantity < quantity:
            await use_item.finish(f"⛔ {item.name} 数量不足")

        # 应用物品效果
        if item.type == ItemType.CONSUMABLE:
            if item.effect_type == ItemEffectType.RESTORE_HP:
                player.hp = min(player.max_hp, player.hp + item.effect_params["value"] * quantity)
            elif item.effect_type == ItemEffectType.RESTORE_MP:
                player.mp = min(player.max_mp, player.mp + item.effect_params["value"] * quantity)
            
            # 更新背包数量
            inventory.quantity -= quantity
            if inventory.quantity <= 0:
                await session.delete(inventory)
            
            session.add(player)
            await session.commit()
            
            await use_item.finish(f"✅ 成功使用 {item.name} ✖️{quantity}\n"
                                 f"当前生命：{player.hp}/{player.max_hp} ❤️\n"
                                 f"当前理智：{player.mp}/{player.max_mp} 🧠")
        else:
            await use_item.finish("⛔ 该物品无法直接使用") 