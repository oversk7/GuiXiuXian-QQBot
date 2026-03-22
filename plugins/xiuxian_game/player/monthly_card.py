from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.monthly_card import MonthlyCard, CardType, get_player_card_benefits, get_card_benefits_config
from ..utils import message_add_head
from ..config import config
from ..platform_utils import get_unified_player


# ==================== 管理员指令：添加月卡 ====================
add_monthly_card_cmd = on_command("添加月卡", aliases={"发月卡"}, block=True, priority=2, permission=SUPERUSER)

@add_monthly_card_cmd.handle()
async def handle_add_monthly_card(event: MessageEvent, args: Message = CommandArg()):
    """管理员指令：添加月卡 UID 类型 月数"""
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await add_monthly_card_cmd.finish(
            "格式：添加月卡 UID 类型 月数\n"
            "类型：basic(基础月卡) 或 premium(高级月卡)\n"
            "例如：添加月卡 1001 basic 1"
        )
    
    uid_str, card_type_str, months_str = parts
    
    # 验证UID
    if not uid_str.isdigit():
        await add_monthly_card_cmd.finish("⛔ UID必须为数字")
    target_uid = int(uid_str)
    
    # 验证月卡类型
    if card_type_str.lower() == "basic":
        card_type = CardType.BASIC
    elif card_type_str.lower() == "premium":
        card_type = CardType.PREMIUM
    else:
        await add_monthly_card_cmd.finish("⛔ 月卡类型只能是 basic 或 premium")
    
    # 验证月数
    if not months_str.isdigit() or int(months_str) < 1:
        await add_monthly_card_cmd.finish("⛔ 月数必须为正整数")
    months = int(months_str)
    
    async with safe_session() as session:
        # 查找目标玩家
        result = await session.execute(select(Player).where(Player.uid == target_uid))
        target_player = result.scalars().first()
        
        if not target_player:
            await add_monthly_card_cmd.finish(f"⛔ 找不到UID为 {target_uid} 的玩家")
        
        # 添加月卡
        card = await MonthlyCard.add_monthly_card(session, target_player.id, card_type, months)
        await session.commit()

        card_config = get_card_benefits_config()
        card_name = card_config[card_type]["name"]
        msg = (
            f"✅ 月卡添加成功\n"
            f"━━━━━━━━━━━━━\n"
            f"👤 玩家：{target_player.nickname}[UID:{target_player.uid}]\n"
            f"💳 类型：{card_name}\n"
            f"📅 时长：{months}个月\n"
            f"⏰ 到期：{card.end_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"━━━━━━━━━━━━━"
        )
        
        await add_monthly_card_cmd.finish(msg)


# ==================== 玩家指令：查看月卡 ====================
check_monthly_card_cmd = on_command("月卡", aliases={"我的月卡", "月卡状态"}, block=True, priority=5)

@check_monthly_card_cmd.handle()
async def handle_check_monthly_card(event: MessageEvent):
    """查看玩家的月卡状态"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            await check_monthly_card_cmd.finish("⛔ 请先创建角色")
        
        # 获取所有有效月卡
        active_cards = await MonthlyCard.get_all_active_cards(session, player.id)

        if not active_cards:
            # 没有月卡，但可能有诡烛特权
            from ..sponsor.service import SponsorShopService
            from datetime import datetime
            privilege_list = [
                ("premium_seclusion_until", "闭关无上限"),
                ("premium_warehouse_until", "远程仓库"),
                ("premium_fishing_until", "鱼竿特权"),
                ("premium_vision_until", "全视之眼"),
            ]
            no_card_lines = ["💳 月卡状态", "━━━━━━━━━━━━━", "🚫 暂无有效月卡"]
            active_privs = []
            for key, name in privilege_list:
                extra = player.extra_attrs or {}
                until_str = extra.get(key)
                if until_str:
                    try:
                        end_time = datetime.fromisoformat(until_str)
                        if end_time > datetime.now():
                            remaining = (end_time - datetime.now()).days
                            active_privs.append(f"🔮 {name} - 剩余{remaining}天（{end_time.strftime('%m-%d')}到期）")
                    except (ValueError, TypeError):
                        pass
            if active_privs:
                no_card_lines.append("━━━━━━━━━━━━━")
                no_card_lines.append("🏷️ 诡烛特权：")
                no_card_lines.extend(active_privs)
            no_card_lines.append("━━━━━━━━━━━━━")
            await check_monthly_card_cmd.finish(message_add_head("\n".join(no_card_lines), event))
        
        # 获取月卡权益
        benefits = await get_player_card_benefits(session, player.id)
        card_config = get_card_benefits_config()

        msg_lines = ["💳 月卡状态", "━━━━━━━━━━━━━"]

        # 显示每张月卡
        for card in active_cards:
            card_name = card_config[card.card_type]["name"]
            remaining = card.remaining_days
            msg_lines.append(f"✨ {card_name} - 剩余{remaining}天")
        
        msg_lines.append("━━━━━━━━━━━━━")
        msg_lines.append("🎁 当前权益：")
        
        # 显示权益
        if benefits["cultivation_efficiency"] > 0:
            msg_lines.append(f"⚡ 修炼效率 +{benefits['cultivation_efficiency']*100:.0f}%")
        
        seclusion_hours = benefits["seclusion_time_limit"] // 3600
        msg_lines.append(f"⏰ 闭关时长上限 {seclusion_hours}小时")
        
        if benefits["seclusion_efficiency"] > 0:
            msg_lines.append(f"🔥 闭关效率 +{benefits['seclusion_efficiency']*100:.0f}%")
        
        if benefits["inventory_bonus"] > 0:
            msg_lines.append(f"🎒 背包格子 +{benefits['inventory_bonus']}")
        
        if benefits["auto_collect"]:
            msg_lines.append("🤖 材料自动采集")
        msg_lines.append("🔧 【一键修复 [金币:怨念]】修复所有装备，可指定比例")
        msg_lines.append("⚙️ 【一键献祭 <材料1> [材料2...]】批量献祭指定材料")
        msg_lines.append("⚔️ 【一键升阶 <编号> <目标阶>】连续升阶直到达到目标")
        if benefits["sign_stamina_bonus"] > 0:
            msg_lines.append(f"💪 签到咒抗上限 +{benefits['sign_stamina_bonus']}")

        # 显示签到月卡宝箱权益
        if benefits["sign_monthly_card_boxes"] > 0:
            msg_lines.append(f"💎 签到获得月卡宝箱 +{benefits['sign_monthly_card_boxes']}")

        # 添加突破保护权益说明
        if benefits["breakthrough_protection"] > 0:
            protection_percent = int(benefits["breakthrough_protection"] * 100)
            msg_lines.append(f"🛡️ 突破失败修为保留{protection_percent}%")

        # 显示诡烛特权到期时间
        from ..sponsor.service import SponsorShopService
        from datetime import datetime
        privilege_list = [
            ("premium_seclusion_until", "闭关无上限"),
            ("premium_warehouse_until", "远程仓库"),
            ("premium_fishing_until", "鱼竿特权"),
            ("premium_vision_until", "全视之眼"),
        ]
        active_privileges = []
        for key, name in privilege_list:
            extra = player.extra_attrs or {}
            until_str = extra.get(key)
            if until_str:
                try:
                    end_time = datetime.fromisoformat(until_str)
                    if end_time > datetime.now():
                        remaining = (end_time - datetime.now()).days
                        active_privileges.append(f"🔮 {name} - 剩余{remaining}天（{end_time.strftime('%m-%d')}到期）")
                except (ValueError, TypeError):
                    pass

        if active_privileges:
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("🏷️ 诡烛特权：")
            msg_lines.extend(active_privileges)

        msg_lines.append("━━━━━━━━━━━━━")

        await check_monthly_card_cmd.finish(message_add_head("\n".join(msg_lines), event))


# ==================== 管理员指令：查看玩家月卡 ====================
admin_check_card_cmd = on_command("查看月卡", block=True, priority=2, permission=SUPERUSER)

@admin_check_card_cmd.handle()
async def handle_admin_check_card(event: MessageEvent, args: Message = CommandArg()):
    """管理员指令：查看月卡 UID"""
    uid_str = args.extract_plain_text().strip()
    
    if not uid_str:
        await admin_check_card_cmd.finish("格式：查看月卡 UID")
    
    if not uid_str.isdigit():
        await admin_check_card_cmd.finish("⛔ UID必须为数字")
    
    target_uid = int(uid_str)
    
    async with safe_session() as session:
        # 查找目标玩家
        result = await session.execute(select(Player).where(Player.uid == target_uid))
        target_player = result.scalars().first()
        
        if not target_player:
            await admin_check_card_cmd.finish(f"⛔ 找不到UID为 {target_uid} 的玩家")
        
        # 获取所有月卡（包括过期的）
        result = await session.execute(
            select(MonthlyCard).where(MonthlyCard.player_id == target_player.id)
            .order_by(MonthlyCard.created_at.desc())
        )
        all_cards = result.scalars().all()
        
        if not all_cards:
            await admin_check_card_cmd.finish(f"玩家 {target_player.nickname}[UID:{target_uid}] 没有月卡记录")
        
        msg_lines = [
            f"💳 {target_player.nickname}[UID:{target_uid}] 的月卡记录",
            "━━━━━━━━━━━━━"
        ]
        
        card_config = get_card_benefits_config()
        active_count = 0
        for card in all_cards:
            card_name = card_config[card.card_type]["name"]
            status = "✅有效" if card.is_active else "❌过期"
            if card.is_active:
                active_count += 1
                remaining = card.remaining_days
                msg_lines.append(f"{status} {card_name} - 剩余{remaining}天")
            else:
                msg_lines.append(f"{status} {card_name} - {card.end_time.strftime('%Y-%m-%d')}到期")
        
        msg_lines.append("━━━━━━━━━━━━━")
        msg_lines.append(f"📊 有效月卡数量：{active_count}")
        
        await admin_check_card_cmd.finish("\n".join(msg_lines))


# ==================== 管理员指令：增加背包容量 ====================
add_inventory_cmd = on_command("增加背包", aliases={"加背包", "扩背包"}, block=True, priority=2, permission=SUPERUSER)

@add_inventory_cmd.handle()
async def handle_add_inventory(event: MessageEvent, args: Message = CommandArg()):
    """管理员指令：增加背包 UID 容量"""
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await add_inventory_cmd.finish(
            "格式：增加背包 UID 容量\n"
            "例如：增加背包 1001 10"
        )

    uid_str, capacity_str = parts

    # 验证UID
    if not uid_str.isdigit():
        await add_inventory_cmd.finish("⛔ UID必须为数字")
    target_uid = int(uid_str)

    # 验证容量
    if not capacity_str.isdigit():
        await add_inventory_cmd.finish("⛔ 容量必须为正整数")
    capacity_add = int(capacity_str)

    if capacity_add <= 0:
        await add_inventory_cmd.finish("⛔ 容量必须大于0")

    if capacity_add > 100:
        await add_inventory_cmd.finish("⛔ 单次增加容量不能超过100")

    async with safe_session() as session:
        # 查找目标玩家
        result = await session.execute(select(Player).where(Player.uid == target_uid))
        target_player = result.scalars().first()

        if not target_player:
            await add_inventory_cmd.finish(f"⛔ 找不到UID为 {target_uid} 的玩家")

        # 记录原始容量
        old_capacity = target_player.inventory_capacity

        # 增加背包容量
        target_player.inventory_capacity += capacity_add

        # 设置合理上限（防止过度增加）
        MAX_INVENTORY_CAPACITY = 1000
        if target_player.inventory_capacity > MAX_INVENTORY_CAPACITY:
            target_player.inventory_capacity = MAX_INVENTORY_CAPACITY
            actual_add = MAX_INVENTORY_CAPACITY - old_capacity
        else:
            actual_add = capacity_add

        session.add(target_player)
        await session.commit()

        # 获取有效背包容量（包含月卡加成）
        effective_capacity = await target_player.get_effective_inventory_capacity(session)

        msg = (
            f"✅ 背包容量增加成功\n"
            f"━━━━━━━━━━━━━\n"
            f"👤 玩家：{target_player.nickname}[UID:{target_player.uid}]\n"
            f"📦 原容量：{old_capacity}\n"
            f"📦 新容量：{target_player.inventory_capacity} (+{actual_add})\n"
            f"💎 有效容量：{effective_capacity} (含月卡加成)\n"
            f"━━━━━━━━━━━━━"
        )

        if actual_add < capacity_add:
            msg += f"\n⚠️ 已达到容量上限({MAX_INVENTORY_CAPACITY})，实际增加{actual_add}"

        await add_inventory_cmd.finish(msg)



# ==================== 月卡权益：一键修复装备 ====================
repair_all_equipment_cmd = on_command("一键修复", aliases={"一键修理", "全部修复"}, block=True, priority=5)

@repair_all_equipment_cmd.handle()
async def handle_repair_all_equipment(event: MessageEvent, args: Message = CommandArg()):
    """月卡权益：一键修复 [金币:怨念] - 修复所有装备，可指定比例，不指定默认全部金币支付"""
    # 解析比例参数
    ratio_str = args.extract_plain_text().strip()
    if not ratio_str:
        # 默认全部使用金币
        gold_ratio, grudge_ratio = 1, 0
    else:
        try:
            if ":" in ratio_str:
                gold_ratio, grudge_ratio = map(int, ratio_str.split(":"))
            else:
                gold_ratio, grudge_ratio = int(ratio_str), 0

            if gold_ratio < 0 or grudge_ratio < 0 or (gold_ratio + grudge_ratio) == 0:
                raise ValueError
        except ValueError:
            await repair_all_equipment_cmd.finish("⛔ 比例格式错误，例如：1:0 (纯金币) 或 1:1 (金币:怨念)")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            await repair_all_equipment_cmd.finish("⛔ 请先创建角色")

        # 检查是否有月卡权益
        active_cards = await MonthlyCard.get_all_active_cards(session, player.id)
        if not active_cards:
            await repair_all_equipment_cmd.finish(message_add_head(
                "⛔ 一键修复是月卡专属功能，请先购买月卡",
                event
            ))

        # 获取所有需要修复的装备
        equipment_ids = config.items_config["by_type"]["EQUIPMENT"]
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id.in_(equipment_ids)
        )
        all_equipment = (await session.execute(stmt)).scalars().all()

        # 筛选出需要修复的装备（耐久度未满的）
        damaged_equipment = []
        for equip in all_equipment:
            if equip.durability < equip.config.durability:
                damaged_equipment.append(equip)

        if not damaged_equipment:
            await repair_all_equipment_cmd.finish(message_add_head(
                "✅ 所有装备都处于完好状态，无需修复",
                event
            ))

        # 计算总修理费用
        total_cost = 0
        repair_details = []

        for equip in damaged_equipment:
            repair_needed = equip.config.durability - equip.durability
            # 使用装备配置中的修理费用，如果没有则按价格的10%计算
            if equip.config.repair_cost is not None:
                cost_per_point = equip.config.repair_cost
            else:
                cost_per_point = max(1, int(equip.config.price * 0.1 / equip.config.durability))

            equip_cost = cost_per_point * repair_needed
            total_cost += equip_cost

            repair_details.append({
                "equipment": equip,
                "repair_needed": repair_needed,
                "cost": equip_cost
            })

        # 根据比例计算金币和怨念消耗
        total_ratio = gold_ratio + grudge_ratio
        gold_cost = int(total_cost * gold_ratio / total_ratio)
        grudge_cost = int(total_cost * grudge_ratio / total_ratio)

        # 检查资源是否足够
        if player.gold < gold_cost:
            await repair_all_equipment_cmd.finish(message_add_head(
                f"⛔ 金币不足，需要 {gold_cost} 金币，当前 {player.gold} 金币",
                event
            ))

        if player.resentment < grudge_cost:
            await repair_all_equipment_cmd.finish(message_add_head(
                f"⛔ 怨念不足，需要 {grudge_cost} 怨念，当前 {player.resentment} 怨念",
                event
            ))

        # 执行修理
        player.gold -= gold_cost
        player.resentment -= grudge_cost

        repaired_equipment = []
        for detail in repair_details:
            equip = detail["equipment"]
            equip.durability = equip.config.durability
            session.add(equip)
            repaired_equipment.append(f"{equip.config.name}(ID:{equip.id})")

        session.add(player)
        await session.commit()

        # 构建结果消息
        cost_info = []
        if gold_cost > 0:
            cost_info.append(f"{gold_cost} 金币")
        if grudge_cost > 0:
            cost_info.append(f"{grudge_cost} 怨念")

        cost_str = " + ".join(cost_info)

        # 显示比例信息
        ratio_info = ""
        if grudge_cost > 0:
            ratio_info = f"（按比例 {gold_ratio}:{grudge_ratio}）"
        else:
            ratio_info = "（默认使用金币）"

        result_msg = (
            f"🔧 一键修复完成！\n"
            f"━━━━━━━━━━━━━\n"
            f"✅ 修复装备：{len(repaired_equipment)} 件\n"
            f"💰 消耗：{cost_str}{ratio_info}\n"
            f"━━━━━━━━━━━━━\n"
            f"📋 修复清单：\n{chr(10).join(repaired_equipment)}"
        )

        await repair_all_equipment_cmd.finish(message_add_head(result_msg, event))
