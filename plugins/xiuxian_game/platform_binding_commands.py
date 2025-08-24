"""
跨平台账号绑定指令模块
提供绑定密钥生成、验证和绑定流程的相关指令
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import datetime

from .models.db import safe_session
from .models.player import Player
from .models.platform_binding import PlatformBinding
from .platform_utils import (
    get_platform_info, PlatformType, is_private_message, 
    is_group_message, is_guild_message, get_unified_player
)
from .utils import message_add_head


# ==================== 生成绑定密钥指令 ====================
generate_binding_key_cmd = on_command("生成绑定密钥", aliases={"绑定密钥"}, block=True, priority=5)

@generate_binding_key_cmd.handle()
async def handle_generate_binding_key(event: MessageEvent):
    """生成绑定密钥（仅限私聊）"""
    if not is_private_message(event):
        await generate_binding_key_cmd.finish("⛔ 绑定密钥只能在私聊中生成")
    
    platform_type, user_id = get_platform_info(event)
    
    async with safe_session() as session:
        # 检查是否已有角色
        player = await session.get(Player, user_id)
        if not player:
            await generate_binding_key_cmd.finish("⛔ 你还没有创建角色，请先在群聊中注册")
        
        # 查找或创建绑定记录
        binding_stmt = select(PlatformBinding).where(
            PlatformBinding.primary_platform_id == user_id,
            PlatformBinding.is_active == True
        )
        binding_result = await session.execute(binding_stmt)
        binding = binding_result.scalars().first()
        
        if binding:
            # 如果已经绑定了频道账号
            if binding.secondary_platform_id:
                await generate_binding_key_cmd.finish("⛔ 你的账号已经绑定了频道账号")
            
            # 如果有有效的密钥
            if binding.is_key_valid():
                await generate_binding_key_cmd.finish(
                    f"🔑 你已有有效的绑定密钥\n"
                    f"密钥：{binding.binding_key}\n"
                    f"状态：永久有效（直到使用成功）\n"
                    f"💡 请在频道中私聊机器人使用：绑定账号 {binding.binding_key} {player.uid}"
                )
        else:
            # 创建新的绑定记录
            binding = PlatformBinding(
                primary_platform_id=user_id,
                secondary_platform_id=None,
                is_active=True
            )
            session.add(binding)
        
        # 生成新的绑定密钥
        binding.binding_key = PlatformBinding.generate_binding_key()
        binding.updated_at = datetime.now()

        await session.commit()

        msg = (
            f"🔑 绑定密钥生成成功\n"
            f"━━━━━━━━━━━━━\n"
            f"密钥：{binding.binding_key}\n"
            f"你的UID：{player.uid}\n"
            f"有效期：永久有效（直到使用成功）\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 使用方法：\n"
            f"1. 在频道中私聊机器人\n"
            f"2. 发送：绑定账号 {binding.binding_key} {player.uid}\n"
            f"3. 验证成功后即可在频道中使用游戏功能\n"
            f"━━━━━━━━━━━━━\n"
            f"⚠️ 请勿将密钥泄露给他人！"
        )
        
        await generate_binding_key_cmd.finish(msg)


# ==================== 绑定账号指令 ====================
bind_account_cmd = on_command("绑定账号", block=True, priority=5)

@bind_account_cmd.handle()
async def handle_bind_account(event: MessageEvent, args: Message = CommandArg()):
    """绑定账号（仅限私聊）"""
    if not is_private_message(event):
        await bind_account_cmd.finish("⛔ 账号绑定只能在私聊中进行")
    
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await bind_account_cmd.finish("⛔ 请提供绑定密钥和UID\n格式：绑定账号 密钥 UID")
    
    parts = args_text.split()
    if len(parts) != 2:
        await bind_account_cmd.finish("⛔ 格式错误\n正确格式：绑定账号 密钥 UID")
    
    binding_key, uid_str = parts
    
    try:
        target_uid = int(uid_str)
    except ValueError:
        await bind_account_cmd.finish("⛔ UID必须为数字")
    
    platform_type, user_id = get_platform_info(event)
    
    async with safe_session() as session:
        # 检查当前用户是否已有角色
        current_player = await session.get(Player, user_id)
        if current_player:
            await bind_account_cmd.finish("⛔ 你已经有角色了，无法绑定其他账号")
        
        # 查找目标玩家
        target_player_stmt = select(Player).where(Player.uid == target_uid)
        target_player_result = await session.execute(target_player_stmt)
        target_player = target_player_result.scalars().first()
        
        if not target_player:
            await bind_account_cmd.finish("⛔ 找不到指定UID的玩家")
        
        # 查找绑定记录
        binding_stmt = select(PlatformBinding).where(
            PlatformBinding.primary_platform_id == target_player.id,
            PlatformBinding.binding_key == binding_key,
            PlatformBinding.is_active == True
        )
        binding_result = await session.execute(binding_stmt)
        binding = binding_result.scalars().first()
        
        if not binding:
            await bind_account_cmd.finish("⛔ 绑定密钥无效或已过期")
        
        if not binding.is_key_valid():
            await bind_account_cmd.finish("⛔ 绑定密钥无效")
        
        if binding.secondary_platform_id:
            await bind_account_cmd.finish("⛔ 该账号已经绑定了其他频道账号")
        
        # 执行绑定
        binding.secondary_platform_id = user_id
        binding.clear_binding_key()  # 清除密钥
        
        await session.commit()
        
        msg = (
            f"✅ 账号绑定成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"已绑定角色：{target_player.nickname}[UID:{target_player.uid}]\n"
            f"绑定时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━\n"
            f"🎉 现在你可以在频道中使用所有游戏功能了！\n"
            f"💡 发送【面板】查看你的角色信息"
        )
        
        await bind_account_cmd.finish(msg)


# ==================== 查看绑定状态指令 ====================
binding_status_cmd = on_command("绑定状态", aliases={"账号绑定状态"}, block=True, priority=5)

@binding_status_cmd.handle()
async def handle_binding_status(event: MessageEvent):
    """查看账号绑定状态"""
    platform_type, user_id = get_platform_info(event)
    
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await binding_status_cmd.finish("⛔ 你还没有创建角色")
        
        # 查找绑定记录
        binding_stmt = select(PlatformBinding).where(
            PlatformBinding.primary_platform_id == player.id,
            PlatformBinding.is_active == True
        )
        binding_result = await session.execute(binding_stmt)
        binding = binding_result.scalars().first()
        
        if not binding:
            msg = (
                f"📱 账号绑定状态\n"
                f"━━━━━━━━━━━━━\n"
                f"角色：{player.nickname}[UID:{player.uid}]\n"
                f"状态：未绑定频道账号\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 如需绑定频道账号，请私聊机器人发送【生成绑定密钥】"
            )
        else:
            if binding.secondary_platform_id:
                msg = (
                    f"🔗 账号绑定状态\n"
                    f"━━━━━━━━━━━━━\n"
                    f"角色：{player.nickname}[UID:{player.uid}]\n"
                    f"状态：已绑定频道账号\n"
                    f"绑定时间：{binding.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"✅ 你可以在群聊和频道中使用游戏功能"
                )
            else:
                # 有绑定记录但未完成绑定
                if binding.is_key_valid():
                    msg = (
                        f"⏳ 账号绑定状态\n"
                        f"━━━━━━━━━━━━━\n"
                        f"角色：{player.nickname}[UID:{player.uid}]\n"
                        f"状态：等待绑定确认\n"
                        f"绑定密钥：{binding.binding_key}\n"
                        f"有效期：永久有效（直到使用成功）\n"
                        f"━━━━━━━━━━━━━\n"
                        f"💡 请在频道中私聊机器人使用：绑定账号 {binding.binding_key} {player.uid}"
                    )
                else:
                    msg = (
                        f"📱 账号绑定状态\n"
                        f"━━━━━━━━━━━━━\n"
                        f"角色：{player.nickname}[UID:{player.uid}]\n"
                        f"状态：无有效绑定密钥\n"
                        f"━━━━━━━━━━━━━\n"
                        f"💡 请重新生成绑定密钥"
                    )
        
        await binding_status_cmd.finish(message_add_head(msg, event))


# ==================== 解除绑定指令 ====================
unbind_account_cmd = on_command("解除绑定", aliases={"取消绑定"}, block=True, priority=5)

@unbind_account_cmd.handle()
async def handle_unbind_account(event: MessageEvent):
    """解除账号绑定（仅限私聊）"""
    if not is_private_message(event):
        await unbind_account_cmd.finish("⛔ 解除绑定只能在私聊中进行")
    
    platform_type, user_id = get_platform_info(event)
    
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await unbind_account_cmd.finish("⛔ 你还没有创建角色")
        
        # 查找绑定记录
        binding_stmt = select(PlatformBinding).where(
            PlatformBinding.primary_platform_id == player.id,
            PlatformBinding.is_active == True
        )
        binding_result = await session.execute(binding_stmt)
        binding = binding_result.scalars().first()
        
        if not binding or not binding.secondary_platform_id:
            await unbind_account_cmd.finish("⛔ 你的账号没有绑定频道账号")
        
        # 解除绑定
        binding.is_active = False
        binding.updated_at = datetime.now()
        
        await session.commit()
        
        msg = (
            f"✅ 账号绑定已解除\n"
            f"━━━━━━━━━━━━━\n"
            f"角色：{player.nickname}[UID:{player.uid}]\n"
            f"解除时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 频道账号将无法再访问此角色数据\n"
            f"💡 如需重新绑定，请生成新的绑定密钥"
        )
        
        await unbind_account_cmd.finish(msg)
