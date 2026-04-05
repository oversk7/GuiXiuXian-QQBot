"""NPC AI对话管理员命令"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import logging

from ..models.db import safe_session
from ..world.npc_service_new import NPCService
from ..ai_guide import is_admin

logger = logging.getLogger(__name__)

# 启用NPC AI对话
enable_npc_ai = on_command("启用NPC AI", aliases={"开启NPC AI"}, block=True, priority=15)

@enable_npc_ai.handle()
async def handle_enable_npc_ai(event: MessageEvent, args: Message = CommandArg()):
    """启用NPC的AI对话功能"""
    user_id = event.get_user_id()

    # 验证管理员权限
    if not is_admin(user_id):
        await enable_npc_ai.finish("❌ 仅管理员可以使用此命令")

    npc_name = args.extract_plain_text().strip()
    if not npc_name:
        await enable_npc_ai.finish("❌ 请指定NPC名称\n用法: 【启用NPC AI <NPC名称>】")

    async with safe_session() as session:
        npc_service = NPCService(session)

        # 查询NPC
        npc = await npc_service.get_npc_by_name(npc_name)
        if not npc:
            await enable_npc_ai.finish(f"❌ 找不到NPC: {npc_name}")

        # 启用AI对话
        try:
            # 构建AI配置
            ai_config = {
                "ai_model": "GLM-4-Flash-250414",
                "base_favorability": 50
            }

            success = await npc_service.enable_ai_for_npc(
                npc_id=npc.npc_id,
                ai_config=ai_config
            )

            if not success:
                await enable_npc_ai.finish(f"❌ 启用失败：无法找到NPC")

            msg = f"""✅ 已为NPC「{npc.name}」启用AI对话

配置信息:
- AI模型: GLM-4-Flash-250414
- 初始好感度: 50
- 启用状态: ✅ 已启用

玩家现在可以通过【交互 {npc.name}】与该NPC进行AI对话。"""
            await enable_npc_ai.finish(msg)

        except Exception as e:
            logger.error(f"启用NPC AI对话失败: {e}", exc_info=True)
            await enable_npc_ai.finish(f"❌ 启用失败: {str(e)}")


# 禁用NPC AI对话
disable_npc_ai = on_command("禁用NPC AI", aliases={"关闭NPC AI"}, block=True, priority=15)

@disable_npc_ai.handle()
async def handle_disable_npc_ai(event: MessageEvent, args: Message = CommandArg()):
    """禁用NPC的AI对话功能"""
    user_id = event.get_user_id()

    if not is_admin(user_id):
        await disable_npc_ai.finish("❌ 仅管理员可以使用此命令")

    npc_name = args.extract_plain_text().strip()
    if not npc_name:
        await disable_npc_ai.finish("❌ 请指定NPC名称\n用法: 【禁用NPC AI <NPC名称>】")

    async with safe_session() as session:
        npc_service = NPCService(session)

        npc = await npc_service.get_npc_by_name(npc_name)
        if not npc:
            await disable_npc_ai.finish(f"❌ 找不到NPC: {npc_name}")

        # 禁用AI对话
        try:
            if not npc.extra_data:
                npc.extra_data = {}
            npc.extra_data["ai_enabled"] = False
            await session.commit()

            await disable_npc_ai.finish(f"✅ 已为NPC「{npc.name}」禁用AI对话\n\n该NPC将恢复使用预设对话模式。")

        except Exception as e:
            logger.error(f"禁用NPC AI对话失败: {e}", exc_info=True)
            await disable_npc_ai.finish(f"❌ 禁用失败: {str(e)}")


# 查看NPC AI状态
check_npc_ai = on_command("查看NPC AI", aliases={"NPC AI状态"}, block=True, priority=15)

@check_npc_ai.handle()
async def handle_check_npc_ai(event: MessageEvent, args: Message = CommandArg()):
    """查看NPC的AI对话状态"""
    user_id = event.get_user_id()

    if not is_admin(user_id):
        await check_npc_ai.finish("❌ 仅管理员可以使用此命令")

    npc_name = args.extract_plain_text().strip()
    if not npc_name:
        await check_npc_ai.finish("❌ 请指定NPC名称\n用法: 【查看NPC AI <NPC名称>】")

    async with safe_session() as session:
        npc_service = NPCService(session)

        npc = await npc_service.get_npc_by_name(npc_name)
        if not npc:
            await check_npc_ai.finish(f"❌ 找不到NPC: {npc_name}")

        # 检查AI状态
        ai_enabled = npc_service.is_ai_enabled(npc)
        ai_model = npc_service.get_ai_model(npc)
        personality = npc_service.get_ai_personality(npc)
        forbidden_topics = npc_service.get_ai_forbidden_topics(npc)

        # 检查是否有预设人设
        from ..dialogue.npc_personality import PersonalityManager
        has_personality = PersonalityManager.has_personality(npc.name)

        status_icon = "✅" if ai_enabled else "❌"
        personality_icon = "✅" if has_personality else "⚠️"

        msg = f"""NPC「{npc.name}」AI对话状态

{status_icon} AI对话: {'已启用' if ai_enabled else '未启用'}
🤖 AI模型: {ai_model or '未配置'}
{personality_icon} 预设人设: {'已配置' if has_personality else '未配置（将使用默认配置）'}

当前配置:
- 初始好感度: {npc.extra_data.get('base_favorability', 50) if npc.extra_data else 50}
- 禁忌话题: {', '.join(forbidden_topics) if forbidden_topics else '无'}
- 性格配置: {'已自定义' if personality else '使用默认'}"""

        await check_npc_ai.finish(msg)


# 批量启用NPC AI对话
batch_enable_npc_ai = on_command("批量启用NPC AI", aliases={"启用所有NPC AI", "全部启用NPC AI"}, block=True, priority=15)

@batch_enable_npc_ai.handle()
async def handle_batch_enable_npc_ai(event: MessageEvent, args: Message = CommandArg()):
    """批量启用所有NPC或指定地点NPC的AI对话功能"""
    user_id = event.get_user_id()

    if not is_admin(user_id):
        await batch_enable_npc_ai.finish("❌ 仅管理员可以使用此命令")

    location_filter = args.extract_plain_text().strip()

    async with safe_session() as session:
        npc_service = NPCService(session)

        # 获取所有活跃NPC
        from sqlalchemy import select
        from ..models.npc import NPC
        from ..models.location import Location

        # 导入NPCType以过滤鬼怪
        from ..models.npc import NPCType

        if location_filter:
            # 按地点过滤（排除鬼怪）
            stmt = (
                select(NPC)
                .join(Location, NPC.location_id == Location.id)
                .where(
                    NPC.is_active == True,
                    Location.name == location_filter,
                    NPC.npc_type != NPCType.GHOST  # 排除鬼怪
                )
            )
        else:
            # 所有NPC（排除鬼怪）
            stmt = select(NPC).where(
                NPC.is_active == True,
                NPC.npc_type != NPCType.GHOST  # 排除鬼怪
            )

        result = await session.execute(stmt)
        npcs = list(result.scalars().all())

        if not npcs:
            if location_filter:
                await batch_enable_npc_ai.finish(f"❌ 在地点「{location_filter}」找不到任何NPC")
            else:
                await batch_enable_npc_ai.finish("❌ 找不到任何NPC")

        # 批量启用
        enabled_count = 0
        skipped_count = 0
        error_count = 0

        for npc in npcs:
            try:
                # 检查是否已启用
                if npc_service.is_ai_enabled(npc):
                    skipped_count += 1
                    continue

                # 启用AI对话
                ai_config = {
                    "ai_model": "GLM-4-Flash-250414",
                    "base_favorability": 50
                }
                success = await npc_service.enable_ai_for_npc(
                    npc_id=npc.npc_id,
                    ai_config=ai_config
                )
                if success:
                    enabled_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(f"启用NPC {npc.name} 的AI对话失败: {e}")
                error_count += 1

        # 提交更改
        await session.commit()

        # 生成报告
        msg = f"""✅ 批量启用NPC AI对话完成

📊 统计信息:
- 总NPC数: {len(npcs)} (已排除鬼怪)
- ✅ 成功启用: {enabled_count}
- ⏭️ 已启用跳过: {skipped_count}
- ❌ 启用失败: {error_count}

配置信息:
- AI模型: GLM-4-Flash-250414
- 初始好感度: 50
- 过滤规则: 仅启用非鬼怪类NPC"""

        if location_filter:
            msg += f"\n- 地点过滤: {location_filter}"

        if enabled_count > 0:
            msg += f"\n\n玩家现在可以通过【交互 <NPC名称>】与这些NPC进行AI对话。"

        await batch_enable_npc_ai.finish(msg)


# 批量禁用NPC AI对话
batch_disable_npc_ai = on_command("批量禁用NPC AI", aliases={"禁用所有NPC AI", "全部禁用NPC AI"}, block=True, priority=15)

@batch_disable_npc_ai.handle()
async def handle_batch_disable_npc_ai(event: MessageEvent, args: Message = CommandArg()):
    """批量禁用所有NPC或指定地点NPC的AI对话功能"""
    user_id = event.get_user_id()

    if not is_admin(user_id):
        await batch_disable_npc_ai.finish("❌ 仅管理员可以使用此命令")

    location_filter = args.extract_plain_text().strip()

    async with safe_session() as session:
        npc_service = NPCService(session)

        # 获取所有活跃NPC（排除鬼怪）
        from sqlalchemy import select
        from ..models.npc import NPC, NPCType
        from ..models.location import Location

        if location_filter:
            stmt = (
                select(NPC)
                .join(Location, NPC.location_id == Location.id)
                .where(
                    NPC.is_active == True,
                    Location.name == location_filter,
                    NPC.npc_type != NPCType.GHOST  # 排除鬼怪
                )
            )
        else:
            stmt = select(NPC).where(
                NPC.is_active == True,
                NPC.npc_type != NPCType.GHOST  # 排除鬼怪
            )

        result = await session.execute(stmt)
        npcs = list(result.scalars().all())

        if not npcs:
            if location_filter:
                await batch_disable_npc_ai.finish(f"❌ 在地点「{location_filter}」找不到任何NPC")
            else:
                await batch_disable_npc_ai.finish("❌ 找不到任何NPC")

        # 批量禁用
        disabled_count = 0
        skipped_count = 0

        for npc in npcs:
            if not npc.extra_data:
                npc.extra_data = {}
                skipped_count += 1
                continue

            if not npc_service.is_ai_enabled(npc):
                skipped_count += 1
                continue

            npc.extra_data["ai_enabled"] = False
            disabled_count += 1

        await session.commit()

        msg = f"""✅ 批量禁用NPC AI对话完成

📊 统计信息:
- 总NPC数: {len(npcs)} (已排除鬼怪)
- ✅ 成功禁用: {disabled_count}
- ⏭️ 未启用跳过: {skipped_count}"""

        if location_filter:
            msg += f"\n- 地点过滤: {location_filter}"

        await batch_disable_npc_ai.finish(msg)
