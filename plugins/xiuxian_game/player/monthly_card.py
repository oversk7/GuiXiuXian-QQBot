from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.monthly_card import MonthlyCard, CardType, get_player_card_benefits, get_card_benefits_config
from ..utils import message_add_head


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
    user_id = event.get_user_id()
    
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await check_monthly_card_cmd.finish("⛔ 请先创建角色")
        
        # 获取所有有效月卡
        active_cards = await MonthlyCard.get_all_active_cards(session, player.id)

        if not active_cards:
            await check_monthly_card_cmd.finish(message_add_head(
                "💳 月卡状态\n"
                "━━━━━━━━━━━━━\n"
                "🚫 暂无有效月卡\n"
                "━━━━━━━━━━━━━",
                event
            ))
        
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
        msg_lines.append("🤖 【一键修复 [金币:怨念]】修复所有装备，可指定比例")
        if benefits["sign_stamina_bonus"] > 0:
            msg_lines.append(f"💪 签到咒抗上限 +{benefits['sign_stamina_bonus']}")

        # 添加扫荡令权益说明
        if benefits["sign_sweep_tokens"] > 0:
            msg_lines.append(f"🎫 签到获得扫荡令*{benefits['sign_sweep_tokens']}")

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
        MAX_INVENTORY_CAPACITY = 200
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
