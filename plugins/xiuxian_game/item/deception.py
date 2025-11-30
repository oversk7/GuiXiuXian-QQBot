"""
欺骗系统 - 玩家可以用三倍同品质材料转换为指定材料

指令：
- 欺骗 <目标材料名称> <源材料名称> <数量> - 用三倍同品质材料转换为指定材料
- 欺骗帮助 - 查看欺骗系统说明

机制：
1. 需要三倍同品质的材料作为代价
2. 支付高额手续费给"骗人鬼"
3. 只能转换同品质的材料
4. 手续费为材料价值的10倍
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from typing import Dict, List, Tuple, Optional

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance, ItemConfig
from ..config import config
from ..utils import message_add_head
from ..platform_utils import get_unified_player


# ==================== 欺骗指令 ====================
deception_cmd = on_command("欺骗", aliases={"骗人", "欺诈"}, block=True, priority=5)
deception_help_cmd = on_command("欺骗帮助", aliases={"欺骗说明", "欺诈帮助"}, block=True, priority=5)


@deception_help_cmd.handle()
async def handle_deception_help(event: MessageEvent):
    """显示欺骗系统帮助信息"""
    help_msg = (
        "🎭 欺骗世界系统 🎭\n"
        "━━━━━━━━━━━━━\n"
        "💡 系统说明：\n"
        "• 用三倍同品质材料转换为指定材料\n"
        "• 需要支付高额手续费给\"骗人鬼\"\n"
        "• 只能转换同品质的材料\n"
        "━━━━━━━━━━━━━\n"
        "📝 使用方法：\n"
        "【欺骗 <源材料> <目标材料> <目标数量>】\n"
        "━━━━━━━━━━━━━\n"
        "💰 手续费计算：\n"
        "• 手续费 = 目标材料价值 × 10\n"
        "━━━━━━━━━━━━━\n"
        "⚠️ 注意事项：\n"
        "• 只能转换同品质材料\n"
        "• 材料品质：⚪白色 🟢绿色 🔵蓝色 🟣紫色 🟠橙色\n"
        "• 转换后源材料会消失\n"
        "━━━━━━━━━━━━━\n"
        "🌟 示例：欺骗 魂魄结晶 血肉结晶 1"
    )
    await deception_help_cmd.finish(message_add_head(help_msg, event))


@deception_cmd.handle()
async def handle_deception(event: MessageEvent, args: Message = CommandArg()):
    """处理欺骗指令"""
    args_text = args.extract_plain_text().strip()
    
    if not args_text:
        await deception_cmd.finish("⛔ 格式错误，正确格式：欺骗 <源材料> <目标材料> <数量>")
    
    parts = args_text.split()
    if len(parts) != 3:
        await deception_cmd.finish("⛔ 参数错误，正确格式：欺骗 <源材料> <目标材料> <数量>")
    
    source_material_name, target_material_name, quantity_str = parts
    
    try:
        quantity = int(quantity_str)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await deception_cmd.finish("⛔ 数量必须为正整数")
    
    async with safe_session() as session:
        # 获取玩家
        player = await get_unified_player(session, event)
        if not player:
            await deception_cmd.finish("⛔ 请先创建角色")
        
        # 查找目标材料
        target_config = config.items_config["by_name"].get(target_material_name)
        if not target_config:
            await deception_cmd.finish(f"⛔ 不存在目标材料：{target_material_name}")
        
        if target_config.type.value != "MATERIAL":
            await deception_cmd.finish(f"⛔ {target_material_name} 不是材料")
        
        # 查找源材料
        source_config = config.items_config["by_name"].get(source_material_name)
        if not source_config:
            await deception_cmd.finish(f"⛔ 不存在源材料：{source_material_name}")
        
        if source_config.type.value != "MATERIAL":
            await deception_cmd.finish(f"⛔ {source_material_name} 不是材料")
        
        # 检查品质是否相同
        if target_config.rarity != source_config.rarity:
            await deception_cmd.finish(f"⛔ 只能转换同品质材料，{target_material_name}是{target_config.get_rarity_display()}品质，{source_material_name}是{source_config.get_rarity_display()}品质")
        
        # 检查是否为相同材料
        if target_config.item_id == source_config.item_id:
            await deception_cmd.finish("⛔ 不能转换为相同材料")
        
        # 计算所需源材料数量（三倍）
        required_source_quantity = quantity * 3
        
        # 检查源材料是否足够
        source_items = (await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id, ItemInstance.item_id == source_config.item_id)
        )).scalars().all()
        
        total_source_quantity = sum(item.quantity for item in source_items)
        if total_source_quantity < required_source_quantity:
            await deception_cmd.finish(f"⛔ {source_material_name} 数量不足，需要 {required_source_quantity} 个，当前只有 {total_source_quantity} 个")
        
        # 计算手续费（目标材料价值的10倍）
        fee = target_config.price * 10 * quantity
        
        # 检查金币是否足够
        if player.gold < fee:
            await deception_cmd.finish(f"⛔ 金币不足，需要支付手续费 {fee:,}💰，当前只有 {player.gold:,}💰")
        
        # 扣除源材料
        try:
            await ItemInstance.consume_item(session, player.id, source_config.item_id, required_source_quantity)
        except ValueError as e:
            await session.rollback()
            await deception_cmd.finish(f"⛔ 扣除源材料失败：{e}")
        
        # 扣除手续费
        player.gold -= fee
        
        # 添加目标材料
        try:
            await ItemInstance.add_item(session, player.id, target_config.item_id, quantity)
        except ValueError as e:
            # 如果背包满了，恢复金币和源材料
            player.gold += fee
            await session.rollback()
            await deception_cmd.finish(f"⛔ 背包空间不足：{e}")
        
        # 提交事务
        session.add(player)
        await session.commit()
        
        # 构建成功消息
        rarity_emoji = target_config.get_rarity_display()
        success_msg = (
            f"🎭 欺骗成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"📦 转换结果：\n"
            f"• 消耗：{source_config.get_display_name()} ✖️{required_source_quantity}\n"
            f"• 获得：{target_config.get_display_name()} ✖️{quantity}\n"
            f"• 手续费：{fee:,}💰\n"
            f"━━━━━━━━━━━━━\n"
            f"💀 骗人鬼：嘿嘿，又有人上当了呢～\n"
            f"💰 剩余金币：{player.gold:,}"
        )
        
        await deception_cmd.finish(message_add_head(success_msg, event))
