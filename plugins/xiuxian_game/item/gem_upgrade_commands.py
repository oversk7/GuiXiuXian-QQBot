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
from ..utils_markdown import cmd, build_markdown
from .gem_upgrade_service import GemUpgradeService
from ..platform_utils import require_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的GemUpgradeService，False使用旧版本
# =====================================================


# ---------------- 指令：查看镶嵌物升级信息 ----------------
gem_upgrade_info_cmd = on_command("镶嵌物升级", aliases={"宝石升级", "佛珠升级", "升级镶嵌物"}, block=True, priority=9)

@gem_upgrade_info_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await gem_upgrade_info_cmd.finish("⛔ 格式：镶嵌物升级 镶嵌物名称")

    async with safe_session() as session:
        player = await require_player(session, event, gem_upgrade_info_cmd)

        # 查找镶嵌物
        gem_config = config.items_config["by_name"].get(arg)
        if not gem_config:
            await gem_upgrade_info_cmd.finish("⛔ 未找到指定镶嵌物")

        gem_id = gem_config.item_id

        if not GemUpgradeService.is_upgradeable_gem(gem_id):
            await gem_upgrade_info_cmd.finish("⛔ 该物品不是可升级的镶嵌物")

        # 获取升级信息
        upgrade_info = GemUpgradeService.get_gem_display_info(gem_id, player.luck)
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
            f"# 🔮 {upgrade_info['current_name']} 升级信息",
            f"📊 当前等级: **{upgrade_info['current_level']}**/10",
            f"💎 拥有数量: **{owned_qty}**",
            ""
        ]

        if not upgrade_info["can_upgrade"]:
            lines.append("✨ 已达最高等级！")
        else:
            lines.extend([
                f"⬆️ 升级目标: {upgrade_info['next_name']}",
                f"🔢 需要数量: **{upgrade_info['required_gem_count']}** 个",
                f"💰 消耗金币: **{upgrade_info['required_gold']}**",
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

            # 计算基础成功率（不含运气加成）
            base_success_rate = GemUpgradeService.get_success_rate(upgrade_info['current_level'], False, 0)

            lines.extend([
                "",
                f"📈 基础成功率: {base_success_rate:.1%}",
                f"🍀 运气加成后: {upgrade_info['success_rate']:.1%}",
                f"🛡️ 稳定水晶加成: {upgrade_info['success_rate_with_protection']:.1%}",
                "",
                "💡 使用方法：",
                f"• {cmd(f'合成镶嵌物 {arg}', f'合成镶嵌物 {arg}')}",
                f"• {cmd(f'合成镶嵌物 {arg} 稳定水晶', f'合成镶嵌物 {arg} 稳定水晶')}",
                "",
                "📝 说明：",
                f"• 需要消耗 {upgrade_info['required_gem_count']} 个相同镶嵌物进行合成",
                "• 失败时镶嵌物会降阶（1级镶嵌物失败会消失）",
                "• 使用稳定水晶可保护一个原等级镶嵌物",
                f"• 运气值 {player.luck} 提供额外成功率加成"
            ])

        buttons = f"\n{cmd('可升级镶嵌物')} | {cmd('装备栏')} | {cmd('镶嵌物品')}"
        await gem_upgrade_info_cmd.finish(build_markdown("\n".join(lines) + buttons))


# ---------------- 指令：升级镶嵌物 ----------------
gem_upgrade_cmd = on_command("合成镶嵌物", aliases={"升级宝石", "升级佛珠", "合成宝石", "合成佛珠"}, block=True, priority=9)

@gem_upgrade_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await gem_upgrade_cmd.finish("⛔ 格式：合成镶嵌物 镶嵌物名称 [稳定水晶]")

    # 解析参数
    parts = arg_text.split()
    if not parts:
        await gem_upgrade_cmd.finish("⛔ 格式：合成镶嵌物 镶嵌物名称 [稳定水晶]")
    gem_name = parts[0]
    if len(parts) > 2 or (len(parts) == 2 and parts[1] != "稳定水晶"):
        await gem_upgrade_cmd.finish("⛔ 格式：合成镶嵌物 镶嵌物名称 [稳定水晶]")
    use_protection = len(parts) == 2 and parts[1] == "稳定水晶"

    async with safe_session() as session:
        player = await require_player(session, event, gem_upgrade_cmd)

        # 查找镶嵌物
        gem_config = config.items_config["by_name"].get(gem_name)
        if not gem_config:
            await gem_upgrade_cmd.finish("⛔ 未找到指定镶嵌物")

        gem_id = gem_config.item_id

        # 执行升级
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .gem_upgrade_service import GemUpgradeService

        service = GemUpgradeService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session),
        )
        try:
            success, message, consumed_materials = await service.upgrade_gem(gem_id, player, use_protection)
        except ValueError as e:
            await session.rollback()
            await gem_upgrade_cmd.finish(f"⛔ {e}")
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
            buttons = f"\n{cmd('可升级镶嵌物')} | {cmd('装备栏')} | {cmd('镶嵌物品')}"
            await gem_upgrade_cmd.finish(build_markdown(final_message + buttons))
        else:
            await gem_upgrade_cmd.finish(f"⛔ {final_message}")


# ---------------- 指令：一键合成镶嵌物 ----------------
auto_gem_upgrade_cmd = on_command("一键合成镶嵌物", aliases={"一键合成宝石", "一键合成佛珠"}, block=True, priority=9)

@auto_gem_upgrade_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    usage = (
        "⛔ 格式：一键合成镶嵌物 镶嵌物名称 目标等级 [目标数量] [稳定水晶] [预览]\n"
        "示例：\n"
        "一键合成镶嵌物 抗暴符文 8\n"
        "一键合成镶嵌物 抗暴符文 8 2\n"
        "一键合成镶嵌物 抗暴符文 8 稳定水晶\n"
        "一键合成镶嵌物 抗暴符文 8 预览"
    )
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await auto_gem_upgrade_cmd.finish(usage)

    parts = arg_text.split()
    if len(parts) < 2:
        await auto_gem_upgrade_cmd.finish(usage)

    gem_name = parts[0]
    try:
        target_level = int(parts[1])
    except ValueError:
        await auto_gem_upgrade_cmd.finish("⛔ 目标等级必须是数字（2-10）")
    if target_level < 2 or target_level > 10:
        await auto_gem_upgrade_cmd.finish("⛔ 目标等级范围：2-10")

    # 解析可选参数：目标数量（默认1）、稳定水晶、预览
    target_quantity = 1
    use_protection = False
    preview_only = False
    quantity_seen = False
    for token in parts[2:]:
        if token == "稳定水晶":
            use_protection = True
        elif token == "预览":
            preview_only = True
        elif token.isdigit() and not quantity_seen:
            target_quantity = int(token)
            quantity_seen = True
        else:
            await auto_gem_upgrade_cmd.finish(usage)
    if target_quantity < 1 or target_quantity > 99:
        await auto_gem_upgrade_cmd.finish("⛔ 目标数量范围：1-99")

    async with safe_session() as session:
        player = await require_player(session, event, auto_gem_upgrade_cmd)

        gem_config = config.items_config["by_name"].get(gem_name)
        if not gem_config:
            await auto_gem_upgrade_cmd.finish("⛔ 未找到指定镶嵌物")
        if not GemUpgradeService.is_upgradeable_gem(gem_config.item_id):
            await auto_gem_upgrade_cmd.finish("⛔ 该物品不是可升级的镶嵌物")

        base_type = GemUpgradeService.get_gem_base_type(gem_config.item_id)
        target_gem_id = f"{base_type}_{target_level}"
        target_config = config.items_config["by_id"].get(target_gem_id)
        if not target_config:
            await auto_gem_upgrade_cmd.finish("⛔ 找不到目标等级的镶嵌物配置")

        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository

        item_repo = ItemRepository(session)
        service = GemUpgradeService(
            item_repo=item_repo,
            player_repo=PlayerRepository(session),
        )

        target_owned = await item_repo.get_material_total_quantity(player.id, target_gem_id)

        if preview_only:
            level_ids = [f"{base_type}_{level}" for level in range(1, target_level + 1)]
            owned_map = await item_repo.get_material_total_quantities(player.id, level_ids)
            lines = [
                "# 🔮 一键合成预览",
                f"🎯 目标：{target_config.name} x{target_quantity}（当前拥有 {target_owned}）",
                f"💰 当前金币：{player.gold}",
                f"🛡️ 稳定水晶：{'使用（每轮都消耗）' if use_protection else '不使用'}",
                "",
                "📦 当前各级数量：",
            ]
            for level in range(1, target_level + 1):
                qty = owned_map.get(f"{base_type}_{level}", 0)
                lv_config = config.items_config["by_id"].get(f"{base_type}_{level}")
                lv_name = lv_config.name if lv_config else f"{level}级"
                lines.append(f"• {lv_name}: {qty}")
            execute_hint = f"一键合成镶嵌物 {gem_name} {target_level}"
            if target_quantity > 1:
                execute_hint += f" {target_quantity}"
            if use_protection:
                execute_hint += " 稳定水晶"
            preview_low_qty = sum(
                owned_map.get(f"{base_type}_{level}", 0)
                for level in range(1, target_level)
            )
            preview_max_attempts = max(200, min(preview_low_qty, 1000))
            lines.extend([
                "",
                "📋 执行策略：从一级开始，优先取数量≥2的最低级合成；",
                f"   尝试上限：{preview_max_attempts} 次（按低级数量动态，封顶1000）",
                "   成功率与消耗见【镶嵌物升级】。",
                f"💡 确认执行请发送：{execute_hint}",
            ])
            buttons = f"\n{cmd('可升级镶嵌物')} | {cmd('镶嵌物品')} | {cmd('装备栏')}"
            await auto_gem_upgrade_cmd.finish(build_markdown("\n".join(lines) + buttons))

        if target_owned >= target_quantity:
            tip = (
                f"✅ 你已拥有 {target_config.name} x{target_owned}，无需合成。"
                f"\n如需合成更多，请指定目标数量：一键合成镶嵌物 {gem_name} {target_level} {target_owned + 1}"
            )
            await auto_gem_upgrade_cmd.finish(tip)

        start_gold = player.gold
        initial_target_owned = target_owned
        attempts = 0
        successes = 0
        failures = 0
        round_logs = []
        consumed_totals: dict = {}
        stop_reason = ""
        achieved = False
        candidate_level_ids = [f"{base_type}_{level}" for level in range(1, target_level)]
        low_qty_map = await item_repo.get_material_total_quantities(player.id, candidate_level_ids)
        total_low_qty = sum(low_qty_map.values())
        # 一级优先会先把低级全部合完；低级数量大时需要更高尝试上限，封顶 1000 次避免单次指令过慢
        MAX_ATTEMPTS = max(200, min(total_low_qty, 1000))

        while target_owned < target_quantity and attempts < MAX_ATTEMPTS:
            # 每轮一次批量查询，替代逐级查询；一级优先，先把低级合上去清理背包
            quantities = await item_repo.get_material_total_quantities(player.id, candidate_level_ids)
            candidate_id = None
            candidate_level = 0
            for level in range(1, target_level):
                if quantities.get(f"{base_type}_{level}", 0) >= 2:
                    candidate_id = f"{base_type}_{level}"
                    candidate_level = level
                    break

            if not candidate_id:
                stop_reason = "没有数量≥2的低级镶嵌物可供合成"
                break

            can_upgrade, reason = await service.can_upgrade_gem(candidate_id, player, use_protection)
            if not can_upgrade:
                stop_reason = f"{candidate_level}级合成受阻：{reason}"
                break

            attempts += 1
            try:
                success, _msg, consumed = await service.upgrade_gem(candidate_id, player, use_protection)
            except ValueError as e:
                await session.rollback()
                await auto_gem_upgrade_cmd.finish(f"⛔ 合成中断：{e}")

            if not success and not consumed:
                stop_reason = _msg or f"{candidate_level}级合成无法执行"
                break

            for material_id, qty in consumed.items():
                consumed_totals[material_id] = consumed_totals.get(material_id, 0) + qty

            if success:
                successes += 1
                round_logs.append(f"第{attempts}次：✅ {candidate_level}级 → {candidate_level + 1}级")
                if candidate_level + 1 == target_level:
                    target_owned += 1
                    if target_owned >= target_quantity:
                        achieved = True
                        break
            else:
                failures += 1
                if use_protection:
                    round_logs.append(f"第{attempts}次：🛡️ {candidate_level}级失败（水晶保护）")
                elif candidate_level <= 3:
                    round_logs.append(f"第{attempts}次：❌ {candidate_level}级失败（低阶保护）")
                else:
                    round_logs.append(f"第{attempts}次：📉 {candidate_level}级失败降阶")

        gold_spent = start_gold - player.gold
        await session.commit()

        lines = [
            "# 🔮 一键合成完成",
            f"🎯 目标：{target_config.name} x{target_quantity}（原有 {initial_target_owned}）",
            f"📊 共尝试 **{attempts}** 次（成功 {successes} / 失败 {failures}）",
            f"💰 消耗金币: **{gold_spent}**",
        ]

        if consumed_totals:
            lines.append("📦 消耗材料:")
            for material_id, qty in consumed_totals.items():
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id
                lines.append(f"• {material_name} x{qty}")

        if round_logs:
            lines.append("")
            if len(round_logs) > 15:
                lines.append(f"（仅显示最后15次，共 {len(round_logs)} 次）")
                lines.extend(round_logs[-15:])
            else:
                lines.extend(round_logs)

        lines.append("")
        if achieved:
            lines.append(f"✅ 已达成目标：{target_config.name} x{target_quantity}（当前拥有 {target_owned}）！")
        elif attempts >= MAX_ATTEMPTS:
            lines.append(f"⛔ 已达最大尝试次数（{MAX_ATTEMPTS}次），停止合成")
        else:
            lines.append(f"⛔ 中途停止：{stop_reason}")

        buttons = f"\n{cmd('可升级镶嵌物')} | {cmd('装备栏')} | {cmd('镶嵌物品')}"
        await auto_gem_upgrade_cmd.finish(build_markdown("\n".join(lines) + buttons))


# ---------------- 指令：镶嵌物列表（显示可升级的镶嵌物）----------------
upgradeable_gems_cmd = on_command("可升级镶嵌物", aliases={"我的镶嵌物", "镶嵌物列表"}, block=True, priority=9)

@upgradeable_gems_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, upgradeable_gems_cmd)

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

        lines = ["# 🔮 你的可升级镶嵌物", ""]
        
        for gem in upgradeable_gems:
            status = "⬆️" if gem["can_upgrade"] else "✨"
            max_level_text = " (满级)" if not gem["can_upgrade"] else ""
            lines.append(f"{status} {gem['name']} x**{gem['quantity']}**{max_level_text}")

        lines.extend([
            "",
            "💡 使用方法：",
            "• 镶嵌物升级 镶嵌物名称 - 查看升级信息",
            "• 合成镶嵌物 镶嵌物名称 - 进行升级合成"
        ])

        buttons = f"\n{cmd('可升级镶嵌物')} | {cmd('装备栏')} | {cmd('镶嵌物品')}"
        await upgradeable_gems_cmd.finish(build_markdown("\n".join(lines) + buttons))
