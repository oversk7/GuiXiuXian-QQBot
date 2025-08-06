"""
镶嵌物升级命令模块

提供镶嵌物升级相关的用户交互命令：
1. 查看镶嵌物升级信息
2. 升级镶嵌物
"""

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils import message_add_head
from .gem_upgrade_service import GemUpgradeService


# ---------------- 指令：查看镶嵌物升级信息 ----------------
gem_upgrade_info_cmd = on_command("镶嵌物升级", aliases={"宝石升级", "佛珠升级", "升级镶嵌物"}, block=True, priority=5)

@gem_upgrade_info_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await gem_upgrade_info_cmd.finish("⛔ 格式：镶嵌物升级 镶嵌物名称")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await gem_upgrade_info_cmd.finish("⛔ 请先创建角色")

        # 查找镶嵌物
        gem_config = config.items_config["by_name"].get(arg)
        if not gem_config:
            await gem_upgrade_info_cmd.finish("⛔ 未找到指定镶嵌物")

        gem_id = gem_config.item_id

        if not GemUpgradeService.is_upgradeable_gem(gem_id):
            await gem_upgrade_info_cmd.finish("⛔ 该物品不是可升级的镶嵌物")

        # 获取升级信息
        upgrade_info = GemUpgradeService.get_gem_display_info(gem_id)
        if not upgrade_info:
            await gem_upgrade_info_cmd.finish("⛔ 获取升级信息失败")

        # 查询拥有数量
        stmt = select(ItemInstance.quantity).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id == gem_id
        )
        result = await session.execute(stmt)
        owned_qty = sum(result.scalars().all())

        lines = [
            f"🔮 {upgrade_info['current_name']} 升级信息",
            f"📊 当前等级: {upgrade_info['current_level']}/10",
            f"💎 拥有数量: {owned_qty}",
            ""
        ]

        if not upgrade_info["can_upgrade"]:
            lines.append("✨ 已达最高等级！")
        else:
            lines.extend([
                f"⬆️ 升级目标: {upgrade_info['next_name']}",
                f"🔢 需要数量: {upgrade_info['required_gem_count']} 个",
                f"💰 消耗金币: {upgrade_info['required_gold']}",
                ""
            ])

            # 显示升阶石需求和拥有情况
            lines.append("📦 所需材料:")
            for material_id, required_qty in upgrade_info["required_materials"].items():
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id

                # 查询拥有数量
                stmt = select(ItemInstance.quantity).where(
                    ItemInstance.player_id == event.get_user_id(),
                    ItemInstance.item_id == material_id
                )
                result = await session.execute(stmt)
                owned_qty_material = sum(result.scalars().all())

                status = "✅" if owned_qty_material >= required_qty else "❌"
                lines.append(f"{status} {material_name}: {owned_qty_material}/{required_qty}")

            lines.extend([
                "",
                f"📈 成功率: {upgrade_info['success_rate']:.1%}",
                f"🛡️ 保护成功率: {upgrade_info['success_rate_with_protection']:.1%}",
                "",
                "💡 使用方法：",
                f"• 合成镶嵌物 {arg}",
                f"• 合成镶嵌物 {arg} 稳定水晶",
                "",
                "📝 说明：",
                f"• 需要消耗 {upgrade_info['required_gem_count']} 个相同镶嵌物进行合成",
                "• 失败时镶嵌物会消失，使用稳定水晶可保护一个镶嵌物"
            ])

        await gem_upgrade_info_cmd.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：升级镶嵌物 ----------------
gem_upgrade_cmd = on_command("合成镶嵌物", aliases={"升级宝石", "升级佛珠", "合成宝石", "合成佛珠"}, block=True, priority=5)

@gem_upgrade_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await gem_upgrade_cmd.finish("⛔ 格式：合成镶嵌物 镶嵌物名称 [稳定水晶]")

    # 解析参数
    parts = arg_text.split()
    gem_name = parts[0]
    use_protection = len(parts) > 1 and "稳定水晶" in " ".join(parts[1:])

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await gem_upgrade_cmd.finish("⛔ 请先创建角色")

        # 查找镶嵌物
        gem_config = config.items_config["by_name"].get(gem_name)
        if not gem_config:
            await gem_upgrade_cmd.finish("⛔ 未找到指定镶嵌物")

        gem_id = gem_config.item_id

        # 执行升级
        success, message, consumed_materials = await GemUpgradeService.upgrade_gem(
            session, gem_id, player, use_protection
        )

        await session.commit()

        # 构建详细消息
        result_lines = [message]
        
        if consumed_materials:
            result_lines.append("\n📦 消耗材料:")
            for material_id, qty in consumed_materials.items():
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id
                result_lines.append(f"• {material_name} x{qty}")

        final_message = "\n".join(result_lines)
        
        if success:
            await gem_upgrade_cmd.finish(message_add_head(final_message, event))
        else:
            await gem_upgrade_cmd.finish(f"⛔ {final_message}")


# ---------------- 指令：镶嵌物列表（显示可升级的镶嵌物）----------------
upgradeable_gems_cmd = on_command("可升级镶嵌物", aliases={"我的镶嵌物", "镶嵌物列表"}, block=True, priority=5)

@upgradeable_gems_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await upgradeable_gems_cmd.finish("⛔ 请先创建角色")

        # 查询所有镶嵌物
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.quantity > 0
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        # 筛选可升级的镶嵌物
        upgradeable_gems = []
        for item in items:
            if GemUpgradeService.is_upgradeable_gem(item.item_id):
                gem_config = config.items_config["by_id"].get(item.item_id)
                if gem_config:
                    level = GemUpgradeService.get_gem_level(item.item_id)
                    upgradeable_gems.append({
                        "name": gem_config.name,
                        "level": level,
                        "quantity": item.quantity,
                        "can_upgrade": level < 10
                    })

        if not upgradeable_gems:
            await upgradeable_gems_cmd.finish("⛔ 你还没有可升级的镶嵌物")

        # 按等级和名称排序
        upgradeable_gems.sort(key=lambda x: (x["level"], x["name"]))

        lines = ["🔮 你的可升级镶嵌物：", ""]
        
        for gem in upgradeable_gems:
            status = "⬆️" if gem["can_upgrade"] else "✨"
            max_level_text = " (满级)" if not gem["can_upgrade"] else ""
            lines.append(f"{status} {gem['name']} x{gem['quantity']}{max_level_text}")

        lines.extend([
            "",
            "💡 使用方法：",
            "• 镶嵌物升级 镶嵌物名称 - 查看升级信息",
            "• 合成镶嵌物 镶嵌物名称 - 进行升级合成"
        ])

        await upgradeable_gems_cmd.finish(message_add_head("\n".join(lines), event))
