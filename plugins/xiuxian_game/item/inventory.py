from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..models.inventory import ItemType, ItemEffectType
from ..utils import message_add_head, paginate_items
from sqlalchemy import select
from ..config import config
from .item_effects import apply_effect

inventory_cmd = on_command("背包", block=True, priority=5)
use_item = on_command("使用", block=True, priority=5)
item_detail = on_command("查背包", block=True, priority=5)
teleport_list = on_command("地图", block=True, priority=5)

teleport_cmd = on_command("传送", block=True, priority=5)
rename_cmd = on_command("改名", block=True, priority=5)
revive_cmd = on_command("复活", block=True, priority=5)

@use_item.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await use_item.finish("⛔ 格式错误，正确格式：使用 [物品名称] [数量]")

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
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            await use_item.finish(f"⛔ 不存在物品：{item_name}")

        # 检查背包中是否有该物品
        inv_result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == event.get_user_id())
            .where(Inventory.item_id == item_config.item_id)
        )
        inventory = inv_result.scalars().first()
        
        if not inventory or inventory.quantity < quantity:
            await use_item.finish(f"⛔ {item_name} 数量不足")

        # 特殊道具直接跳转对应指令
        if item_config.effect_type == ItemEffectType.CHANGE_NAME:
            await use_item.finish("🪄 请使用指令进行改名：/改名 新名字")
        elif item_config.effect_type == ItemEffectType.TELEPORT:
            await use_item.finish("🪄 请使用指令进行传送：/传送 地点名称")

        # 调用统一效果执行器
        success, msg = await apply_effect(player, item_config, quantity, ctx="world")

        if not success:
            # 未生效，不扣除物品
            await session.rollback()
            await use_item.finish(msg)

        # 扣除物品数量
        inventory.quantity -= quantity
        if inventory.quantity <= 0:
            await session.delete(inventory)

        session.add(player)
        await session.commit()

        await use_item.finish(f"✅ 成功使用 {item_name} ✖️{quantity}\n" + msg)

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
        await inventory_cmd.finish(message_add_head(formatted, event))

@item_detail.handle()
async def handle_item_detail(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await item_detail.finish("⛔ 格式错误，正确格式：查背包 [页码] [序号]\n例：查背包 1 3")

    try:
        page = int(params[0])
        index = int(params[1])
        if page < 1 or index < 1:
            raise ValueError
    except ValueError:
        await item_detail.finish("⛔ 页码和序号必须为正整数")

    async with safe_session() as session:
        # 获取玩家背包数据
        player = await session.get(Player, event.get_user_id())
        if not player:
            await item_detail.finish("⛔ 请先创建角色")

        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == event.get_user_id())
            .order_by(Inventory.item_id)
        )
        items = result.scalars().all()

        if not items:
            await item_detail.finish("🎒 你的背包空无一物")

        # 从配置获取分页大小
        page_size = config.game_config["game"]["inventory_page_size"]
        total_pages = (len(items) - 1) // page_size + 1
        
        if page > total_pages:
            await item_detail.finish(f"⛔ 最大页码为 {total_pages}")

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = items[start_idx:end_idx]

        if index > len(page_items):
            await item_detail.finish(f"⛔ 该页只有 {len(page_items)} 个物品")

        target_item = page_items[index - 1].config
        effect_info = ""
        if target_item.effect_type and target_item.effect_params:
            effects = {
                "RESTORE_HP": f"❤️ 恢复 {target_item.effect_params.get('value', 0)}点生命",
                "RESTORE_MP": f"🧠 恢复 {target_item.effect_params.get('value', 0)}点理智",
                "BUFF": "✨ " + " ".join([f"{k}+{v}" for k,v in target_item.effect_params.items()])
            }
            effect_info = f"\n🔮 效果：{effects.get(target_item.effect_type.value, '特殊效果')}"

        msg = (
            f"📦 物品详情 [页{page}-{index}]\n"
            f"▫️ 名称：{target_item.name}\n"
            f"▫️ 类型：{target_item.type.value}\n"
            f"▫️ 描述：{target_item.description or '暂无描述'}"
            f"{effect_info}"
        )
        await item_detail.finish(message_add_head(msg, event))

@teleport_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await teleport_cmd.finish("⛔ 请指定目标区域，例如：传送 美少年路口")

    # 验证区域
    valid_regions = list(config.map_config["regions"].keys())
    if target_region not in valid_regions:
        await teleport_cmd.finish("⛔ 目的地不存在，可发送 /地图 查看全部区域")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await teleport_cmd.finish("⛔ 请先创建角色")

        # 检查传送符
        legend_ticket_cfg = config.items_config["by_name"].get("传送符")
        if not legend_ticket_cfg:
            await teleport_cmd.finish("⚠️ 配置缺少 传送符")
        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == player.id)
            .where(Inventory.item_id == legend_ticket_cfg.item_id)
        )
        ticket = result.scalars().first()
        if not ticket or ticket.quantity < 1:
            await teleport_cmd.finish("⛔ 传送符不足，无法启程")

        # 扣除并移动
        ticket.quantity -= 1
        if ticket.quantity <= 0:
            await session.delete(ticket)
        player.region = target_region
        player.x = 0
        player.y = 0
        session.add_all([player])
        await session.commit()

    msg = (
        f"🪄 你使用了一张传送符，穿过层层迷雾抵达『{target_region}』！\n"
        f"当前位置：{target_region} ({player.x},{player.y})"
    )
    await teleport_cmd.finish(message_add_head(msg, event))

@teleport_list.handle()
async def handle_teleport_list(event: MessageEvent):
    """显示所有可传送的地点"""
    async with safe_session() as session:
        # 检查玩家是否存在
        player = await session.get(Player, event.get_user_id())
        if not player:
            await teleport_list.finish("⛔ 请先创建角色")

        # 获取所有可传送地点
        locations = [f"• {name} 🌐" for name in config.map_config["regions"].keys()]
        
        # 格式化消息
        msg = (
            "🪐 可传送区域列表：\n"
            + "\n".join(locations)
            + "\n\n📌 使用方式：传送 [区域]\n"
            "📦 需要消耗：传送符 ✖1"
        )
        
        await teleport_list.finish(message_add_head(msg, event))

@rename_cmd.handle()
async def handle_rename(event: MessageEvent, args: Message = CommandArg()):
    new_name = args.extract_plain_text().strip()
    if not new_name or len(new_name) > 12:
        await rename_cmd.finish("⛔ 名称不能为空且最长12个字符")

    async with safe_session() as session:
        # 获取玩家和改名卡信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await rename_cmd.finish("⛔ 请先创建角色")

        rename_item = config.items_config["by_name"]["改名卡"]
        inv_result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == event.get_user_id())
            .where(Inventory.item_id == rename_item.item_id)
        )
        inventory: Inventory = inv_result.scalars().first()

        if not inventory or inventory.quantity < 1:
            await rename_cmd.finish("⛔ 改名卡数量不足")

        # 执行改名操作
        inventory.quantity -= 1
        if inventory.quantity <= 0:
            await session.delete(inventory)
        
        player.nickname = new_name
        session.add(player)
        await session.commit()

        await rename_cmd.finish(f"🎉 成功修改角色名为：{new_name}\n"
                               f"剩余改名卡：{inventory.quantity-1 if inventory else 0}张")

@revive_cmd.handle()
async def handle_revive(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await revive_cmd.finish("⛔ 请先创建角色")
        if player.hp > 0:
            await revive_cmd.finish("⛔ 你尚未死亡，无需复活")
        player.hp = player.max_hp
        session.add(player)
        await session.commit()
        await revive_cmd.finish("✨ 你死而复生，继续前进吧！")