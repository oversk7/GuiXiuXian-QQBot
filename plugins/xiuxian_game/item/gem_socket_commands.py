"""
宝石镶嵌命令模块

提供宝石镶嵌相关的用户交互命令：
1. 查看装备孔位
2. 镶嵌宝石
3. 拆卸宝石
4. 镶嵌物品列表
"""

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils import message_add_head
from .gem_socket_service_new import GemSocketService
from .equipment_commands import find_equipment_by_input
from ..platform_utils import get_unified_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的GemSocketService，False使用旧版本
# =====================================================


# ---------------- 指令：查看装备孔位 ----------------
gem_slots_cmd = on_command("孔位", aliases={"装备孔位", "宝石孔位"}, block=True, priority=5)

@gem_slots_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await gem_slots_cmd.finish("⛔ 格式：孔位 装备ID/名称")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await gem_slots_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, arg)
        if not equip:
            await gem_slots_cmd.finish("⛔ 未找到指定装备")

        if not equip.is_equipment:
            await gem_slots_cmd.finish("⛔ 该物品不是装备")

        # 获取孔位信息
        gem_info = await GemSocketService.get_equipment_gem_info(equip)
        
        lines = [
            f"💎 装备孔位信息",
            f"━━━━━━━━━━━━━",
            f"🎯 装备：{equip.config.name} (ID:{equip.id})",
            f"⭐ 升阶等级：+{equip.upgrade_level}",
            f"🔹 孔位数量：{equip.available_gem_slots}",
            f"💎 已镶嵌：{equip.used_gem_slots}/{equip.available_gem_slots}",
            ""
        ]

        if not gem_info:
            lines.append("❌ 该装备没有孔位")
        else:
            lines.append("🔸 孔位详情：")
            for slot_info in gem_info:
                slot_num = slot_info["slot_number"]
                if slot_info["is_empty"]:
                    lines.append(f"  {slot_num}. 🔘 空孔位")
                else:
                    gem_name = slot_info["gem_name"]
                    gem_type = slot_info["gem_type"]
                    lines.append(f"  {slot_num}. 💎 {gem_type}：{gem_name}")

        lines.extend([
            "",
            "💡 使用方法：",
            f"• 镶嵌 {arg} 孔位号 宝石名称（消耗：镶嵌锤×1 + 1000金币）",
            f"• 拆卸 {arg} 孔位号（消耗：拆卸凿×1 + 500金币，15%宝石损坏风险）",
            f"• 拆卸 {arg} 孔位号 稳定水晶（额外消耗稳定水晶×1，消除所有风险）"
        ])

        await gem_slots_cmd.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：镶嵌宝石 ----------------
socket_gem_cmd = on_command("镶嵌", aliases={"宝石镶嵌"}, block=True, priority=5)

@socket_gem_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await socket_gem_cmd.finish("⛔ 格式：镶嵌 装备编号/名称 孔位号 宝石名称")

    # 解析参数
    parts = arg_text.split()
    if len(parts) < 3:
        await socket_gem_cmd.finish("⛔ 格式：镶嵌 装备编号/名称 孔位号 宝石名称")

    equipment_arg = parts[0]
    try:
        slot_number = int(parts[1])
        slot_index = slot_number - 1  # 转换为0基索引
    except ValueError:
        await socket_gem_cmd.finish("⛔ 孔位号必须是数字")

    gem_name = " ".join(parts[2:])

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await socket_gem_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await socket_gem_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, equipment_arg)
        if not equip:
            await socket_gem_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 查找宝石
        gem_config = config.items_config["by_name"].get(gem_name)
        if not gem_config:
            await socket_gem_cmd.finish("⛔ 未找到指定宝石")

        gem_item_id = gem_config.item_id

        # 执行镶嵌
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .gem_socket_service_new import GemSocketService as GemSocketServiceNew

        service = GemSocketServiceNew(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session),
        )
        success, message = await service.socket_gem(equip, gem_item_id, slot_index, player)
        await session.commit()

        if success:
            await socket_gem_cmd.finish(message_add_head(message, event))
        else:
            await socket_gem_cmd.finish(f"⛔ {message}")


# ---------------- 指令：拆卸宝石 ----------------
remove_gem_cmd = on_command("拆卸", aliases={"宝石拆卸"}, block=True, priority=5)

@remove_gem_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await remove_gem_cmd.finish("⛔ 格式：拆卸 装备编号/名称 孔位号 [稳定水晶]")

    # 解析参数
    parts = arg_text.split()
    if len(parts) < 2:
        await remove_gem_cmd.finish("⛔ 格式：拆卸 装备编号/名称 孔位号 [稳定水晶]")

    equipment_arg = parts[0]
    try:
        slot_number = int(parts[1])
        slot_index = slot_number - 1  # 转换为0基索引
    except ValueError:
        await remove_gem_cmd.finish("⛔ 孔位号必须是数字")

    use_protection = len(parts) > 2 and "稳定水晶" in " ".join(parts[2:])

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await remove_gem_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await remove_gem_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, equipment_arg)
        if not equip:
            await remove_gem_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 执行拆卸
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .gem_socket_service_new import GemSocketService as GemSocketServiceNew

        service = GemSocketServiceNew(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session),
        )
        success, message = await service.remove_gem(equip, slot_index, player, use_protection)
        await session.commit()

        if success:
            await remove_gem_cmd.finish(message_add_head(message, event))
        else:
            await remove_gem_cmd.finish(f"⛔ {message}")


# ---------------- 指令：镶嵌物品列表 ----------------
gem_list_cmd = on_command("镶嵌物品", aliases={"宝石列表", "我的宝石"}, block=True, priority=5)

@gem_list_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await gem_list_cmd.finish("⛔ 请先创建角色")

        # 查询所有GEM类型物品
        gem_item_ids = config.items_config["by_type"].get("GEM", [])
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id.in_(gem_item_ids)
        )
        items = (await session.execute(stmt)).scalars().all()

        if not items:
            await gem_list_cmd.finish("💎 你没有任何可镶嵌的物品")

        lines = ["💎 可镶嵌物品列表", "━━━━━━━━━━━━━"]
        
        # 按类型分组
        gems = []
        beads = []
        runes = []
        
        for item in items:
            item_type = GemSocketService.get_gem_type(item.item_id)
            item_info = f"• {item.config.name} ×{item.quantity}"
            
            if item_type == "宝石":
                gems.append(item_info)
            elif item_type == "佛珠":
                beads.append(item_info)
            elif item_type == "符文":
                runes.append(item_info)

        if gems:
            lines.append("🔸 宝石类：")
            lines.extend(gems)
            lines.append("")

        if beads:
            lines.append("📿 佛珠类：")
            lines.extend(beads)
            lines.append("")

        if runes:
            lines.append("🔮 符文类：")
            lines.extend(runes)
            lines.append("")

        lines.append("💡 使用 /镶嵌 装备名 孔位号 物品名 进行镶嵌")

        await gem_list_cmd.finish(message_add_head("\n".join(lines), event))



