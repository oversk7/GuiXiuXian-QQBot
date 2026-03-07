"""
互动试炼系统 - 基于状态机的恐怖试炼体验
"""
from nonebot import on_command, on_regex
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from sqlalchemy import select
from ..models.db import safe_session
from ..models.player import Player
from ..models.story_session import StorySession
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .engine import StoryEngine
import re
import os
import base64
from pathlib import Path

# 创建试炼引擎实例
story_engine = StoryEngine()

# 命令处理器
story_list_cmd = on_command("试炼列表", aliases={"试炼"}, block=True, priority=5)
completed_trials_cmd = on_command("已通关试炼", aliases={"试炼记录", "通关试炼"}, block=True, priority=5)
start_story_cmd = on_command("开始试炼", block=True, priority=5)
story_status_cmd = on_command("试炼状态", block=True, priority=5)
quit_story_cmd = on_command("退出试炼", block=True, priority=5)

# 数字选择处理器 - 自动识别玩家发送的数字作为试炼选择
choice_handler = on_regex(r"^[1-9]$", block=False, priority=10)

# 任意消息处理器 - 处理普通试炼节点的继续
continue_handler = on_regex(r".*", block=False, priority=15)


@story_list_cmd.handle()
async def handle_story_list(event: MessageEvent):
    """显示可用试炼列表"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await story_list_cmd.finish("⛔ 请先创建角色")

        stories = story_engine.get_story_list()
        if not stories:
            await story_list_cmd.finish(f"📚 暂无可用试炼\n调试信息: 引擎中有 {len(story_engine._story_index)} 个试炼")

        msg_lines = ["📚 可用试炼列表", "━━━━━━━━━━━━━"]
        for i, story in enumerate(stories, 1):
            msg_lines.append(f"{i}. 【{story['title']}】")
            msg_lines.append(f"   {story['description']}")
            msg_lines.append("")

        msg_lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用方法：",
            "▫️ 【开始试炼 <试炼名称>】 - 开始指定试炼",
            "▫️ 【试炼状态】 - 查看当前试炼进度",
            "▫️ 【退出试炼】 - 结束当前试炼"
        ])

        await story_list_cmd.finish(message_add_head("\n".join(msg_lines), event))


@completed_trials_cmd.handle()
async def handle_completed_trials(event: MessageEvent):
    """显示玩家已通关的试炼列表"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await completed_trials_cmd.finish("⛔ 请先创建角色")

        completed_trials = player.get_completed_trials()
        if not completed_trials:
            await completed_trials_cmd.finish(message_add_head("📚 你还没有已通关的试炼记录", event))

        msg_lines = ["📚 已通关试炼", "━━━━━━━━━━━━━"]
        for i, trial_id in enumerate(completed_trials, 1):
            msg_lines.append(f"{i}. {trial_id}")

        await completed_trials_cmd.finish(message_add_head("\n".join(msg_lines), event))


@start_story_cmd.handle()
async def handle_start_story(event: MessageEvent, args: Message = CommandArg()):
    """开始试炼"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await start_story_cmd.finish("⛔ 请先创建角色")
        
        story_id = args.extract_plain_text().strip()
        if not story_id:
            await start_story_cmd.finish("📝 格式：开始试炼 <试炼名称>")
        
        # 检查试炼是否存在
        story = story_engine.get_story(story_id)
        if not story:
            available_stories = list(story_engine._story_index.keys())
            await start_story_cmd.finish(f"❌ 试炼不存在\n可用试炼: {available_stories}\n你输入的: '{story_id}'")
        
        # 检查是否已有活跃试炼
        active_session = await StorySession.get_active_session(session, player.id)
        if active_session:
            await start_story_cmd.finish("⚠️ 你已经在进行试炼中，请先退出当前试炼")
        
        # 创建新的试炼会话
        story_session = await StorySession.create_session(
            session, player.id, story_id, story.get("start_node", "start")
        )

        # 记录story_id到variables,用于通关记录
        story_session.set_variable("current_story_id", story_id)
        
        # 获取起始节点
        current_node = story_engine.get_current_node(story_session, player)
        if not current_node:
            await start_story_cmd.finish("❌ 试炼起始节点不存在")
        
        await session.commit()
        
        # 显示试炼开始信息
        msg = await format_story_node(story, current_node)
        await start_story_cmd.finish(message_add_head(msg, event))


@story_status_cmd.handle()
async def handle_story_status(event: MessageEvent):
    """查看试炼状态"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await story_status_cmd.finish("⛔ 请先创建角色")
        
        # 获取活跃试炼会话
        story_session = await StorySession.get_active_session(session, player.id)
        if not story_session:
            await story_status_cmd.finish("📚 你当前没有进行中的试炼")
        
        story = story_engine.get_story(story_session.story_id)
        if not story:
            await story_status_cmd.finish("❌ 试炼数据异常")
        
        current_node = story_engine.get_current_node(story_session, player)
        if not current_node:
            await story_status_cmd.finish("❌ 当前节点不存在")
        
        # 显示当前试炼状态
        msg = await format_story_node(story, current_node)
        await story_status_cmd.finish(message_add_head(msg, event))


@quit_story_cmd.handle()
async def handle_quit_story(event: MessageEvent):
    """退出试炼"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await quit_story_cmd.finish("⛔ 请先创建角色")
        
        # 获取活跃试炼会话
        story_session = await StorySession.get_active_session(session, player.id)
        if not story_session:
            await quit_story_cmd.finish("📚 你当前没有进行中的试炼")
        
        # 结束试炼会话
        story_session.is_active = False
        session.add(story_session)
        await session.commit()
        
        await quit_story_cmd.finish(message_add_head("🏳️ 已退出当前试炼", event))


@choice_handler.handle()
async def handle_choice(event: MessageEvent):
    """处理数字选择"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            return  # 不是注册玩家，忽略
        
        # 获取活跃试炼会话
        story_session = await StorySession.get_active_session(session, player.id)
        if not story_session:
            return  # 没有活跃试炼，忽略
        
        # 获取选择的数字
        choice_text = event.get_plaintext().strip()
        try:
            choice_id = int(choice_text)
        except ValueError:
            return
        
        # 处理选择
        success, message, next_node = story_engine.process_choice(story_session, player, choice_id)
        
        if not success:
            await choice_handler.finish(message_add_head(f"❌ {message}", event))
        
        # 更新数据库
        session.add(story_session)
        session.add(player)
        await session.commit()
        
        if not next_node:
            await choice_handler.finish(message_add_head("❌ 试炼节点异常", event))
        
        # 显示下一个节点
        story = story_engine.get_story(story_session.story_id)
        msg = await format_story_node(story, next_node)

        # 如果是结束节点，处理试炼结束逻辑
        reward_message = ""
        if next_node.get("type") == "end":
            story_session.is_active = False

            # 应用结束节点的特殊效果（如首次试炼奖励）
            if "effects" in next_node:
                variables = story_session.get_variables()
                player, variables, reward_msg = await story_engine.apply_special_effects(
                    next_node["effects"], player, variables, session
                )
                story_session.set_variables(variables)
                reward_message = reward_msg

        # 更新数据库
        session.add(story_session)
        session.add(player)
        await session.commit()

        # 添加奖励消息到显示内容
        if reward_message:
            msg = Message(str(msg) + reward_message)

        await choice_handler.finish(message_add_head(msg, event))


@continue_handler.handle()
async def handle_continue(event: MessageEvent):
    """处理普通试炼节点的继续"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            return  # 不是注册玩家，忽略

        # 获取活跃试炼会话
        story_session = await StorySession.get_active_session(session, player.id)
        if not story_session:
            return  # 没有活跃试炼，忽略

        # 获取当前节点
        current_node = story_engine.get_current_node(story_session, player)
        if not current_node:
            return

        # 只处理普通试炼节点（非选择节点）
        if current_node.get("type") != "story":
            return

        # 应用当前节点的效果
        variables = story_session.get_variables()
        if "effects" in current_node:
            player, variables = story_engine.apply_effects(current_node["effects"], player, variables)
            story_session.set_variables(variables)

        # 使用条件跳转解析下一个节点
        next_node_id = story_engine.resolve_next(current_node.get("next"), player, variables)
        if not next_node_id:
            return

        # 跳转到下一个节点
        story_session.current_node = next_node_id
        next_node = story_engine.get_current_node(story_session, player)

        if not next_node:
            await continue_handler.finish(message_add_head("❌ 试炼节点异常", event))

        # 显示下一个节点
        story = story_engine.get_story(story_session.story_id)
        msg = await format_story_node(story, next_node)

        # 如果是结束节点，处理试炼结束逻辑
        reward_message = ""
        if next_node.get("type") == "end":
            story_session.is_active = False

            # 应用结束节点的特殊效果（如首次试炼奖励）
            if "effects" in next_node:
                variables = story_session.get_variables()
                player, variables, reward_msg = await story_engine.apply_special_effects(
                    next_node["effects"], player, variables, session
                )
                story_session.set_variables(variables)
                reward_message = reward_msg

        # 更新数据库
        session.add(story_session)
        session.add(player)
        await session.commit()

        # 添加奖励消息到显示内容
        if reward_message:
            msg = Message(str(msg) + reward_message)

        await continue_handler.finish(message_add_head(msg, event))


async def format_story_node(story: dict, node: dict) -> Message:
    """格式化试炼节点显示，支持图片"""
    lines = []

    # 试炼标题
    lines.append(f"📖 {story.get('title', '未命名试炼')}")
    lines.append("━━━━━━━━━━━━━")

    # 节点内容
    content = node.get("content", "")
    if content:
        lines.append(content)
        lines.append("")

    # 根据节点类型显示不同内容
    node_type = node.get("type", "story")

    if node_type == "choice":
        # 选择节点 - 显示选项
        options = node.get("options", [])
        if options:
            lines.append("🎯 请选择：")
            for option in options:
                option_id = option.get("id", 0)
                option_text = option.get("text", "")
                lines.append(f"{option_id}. {option_text}")
            lines.append("")
            lines.append("💡 发送数字序号进行选择")

    elif node_type == "end":
        # 结束节点
        lines.append("🎭 试炼结束")
        effects = node.get("effects", {})
        if "rewards" in effects:
            lines.append("🎁 获得奖励：")
            for reward, amount in effects["rewards"].items():
                lines.append(f"▫️ {reward}: {amount}")

    else:
        # 普通试炼节点
        lines.append("📝 发送任意消息继续...")

    lines.append("━━━━━━━━━━━━━")
    text_content = "\n".join(lines)

    # 构建消息
    message = Message()

    # 检查是否有配图
    image_path = node.get("image")
    if image_path:
        # 处理图片路径
        story_dir = Path(__file__).parent.parent / "data" / "stories"
        full_image_path = os.path.join(story_dir, image_path)
        try:
            with open(full_image_path, "rb") as f:
                base64_img = base64.b64encode(f.read()).decode("utf-8")
            message.append(MessageSegment.file_image(base64_img))
        except Exception as e:
            print(f"❌ 加载故事配图失败 {full_image_path}: {e}")

    # 添加文本内容
    message.append(MessageSegment.text(text_content))

    return message
