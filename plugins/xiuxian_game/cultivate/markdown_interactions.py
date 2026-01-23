"""
修炼系统Markdown交互优化
提供便捷的快捷操作按钮
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageMarkdown
from nonebot.adapters.qq.models import MessageMarkdownParams
from nonebot.params import CommandArg


def create_cultivation_markdown(player_nickname: str = "道友") -> MessageMarkdown:
    """
    创建修炼系统的快捷操作Markdown模版
    """
    template_params = [
        MessageMarkdownParams(key="t1", values=["修炼"]),  # 主要操作
        MessageMarkdownParams(key="t2", values=["突破"]),  # 突破
        MessageMarkdownParams(key="t3", values=["闭关"]),  # 闭关
        MessageMarkdownParams(key="t4", values=["出关"]),  # 出关
        MessageMarkdownParams(key="t5", values=["加点 力 1"]),  # 快速加点示例
        MessageMarkdownParams(key="t6", values=["加点 运 1"]),  # 快速加点示例
        MessageMarkdownParams(key="t7", values=["加点帮助"]),  # 帮助
        MessageMarkdownParams(key="t8", values=["献祭 病历单 1"]),  # 献祭示例
        MessageMarkdownParams(key="t9", values=["面板"]),  # 查看面板
        MessageMarkdownParams(key="t10", values=["修炼系统"]),  # 详细帮助
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    return markdown


def create_breakthrough_markdown() -> MessageMarkdown:
    """
    创建突破系统的快捷操作Markdown模版
    """
    template_params = [
        MessageMarkdownParams(key="t1", values=["突破"]),  # 普通突破
        MessageMarkdownParams(key="t2", values=["突破 镇厄"]),  # 使用怨念
        MessageMarkdownParams(key="t3", values=["突破 棺材钉"]),  # 使用棺材钉
        MessageMarkdownParams(key="t4", values=["连续突破"]),  # 连续突破
        MessageMarkdownParams(key="t5", values=["连续突破 镇厄"]),  # 连续+怨念
        MessageMarkdownParams(key="t6", values=["修炼"]),  # 返回修炼
        MessageMarkdownParams(key="t7", values=["面板"]),  # 查看属性
        MessageMarkdownParams(key="t8", values=["加点"]),  # 查看加点
        MessageMarkdownParams(key="t9", values=["冥返"]),  # 冥返
        MessageMarkdownParams(key="t10", values=["修炼系统"]),  # 帮助
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    return markdown


def create_attribute_points_markdown(attribute_points: int) -> MessageMarkdown:
    """
    创建加点系统的快捷操作Markdown模版
    """
    template_params = [
        MessageMarkdownParams(key="t1", values=["加点 力 1"]),  # 力+1
        MessageMarkdownParams(key="t2", values=["加点 体 1"]),  # 体+1
        MessageMarkdownParams(key="t3", values=["加点 敏 1"]),  # 敏+1
        MessageMarkdownParams(key="t4", values=["加点 防 1"]),  # 防+1
        MessageMarkdownParams(key="t5", values=["加点 智 1"]),  # 智+1
        MessageMarkdownParams(key="t6", values=["加点 运 1"]),  # 运+1
        MessageMarkdownParams(key="t7", values=["加点 力 5"]),  # 力+5
        MessageMarkdownParams(key="t8", values=["加点 运 5"]),  # 运+5
        MessageMarkdownParams(key="t9", values=["加点帮助"]),  # 帮助
        MessageMarkdownParams(key="t10", values=["修炼系统"]),  # 系统帮助
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    return markdown


# 修炼快捷操作
cultivate_quick_cmd = on_command("修炼快捷", aliases={"修炼菜单"}, priority=4, block=True)

@cultivate_quick_cmd.handle()
async def handle_cultivate_quick(event: MessageEvent, args: Message = CommandArg()):
    """显示修炼快捷操作菜单"""
    from ..platform_utils import get_unified_player

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await cultivate_quick_cmd.finish("⛔ 请先创建角色")

        player_nickname = player.nickname if player.nickname else "道友"

    # 创建快捷操作菜单
    markdown = create_cultivation_markdown(player_nickname)

    msg = Message(
        f"🧘‍♂️ {player_nickname}的修炼快捷菜单\n"
        f"━━━━━━━━━━━━━\n"
        f"💡 点击下方蓝色按钮快速执行操作"
    )
    msg.append(MessageSegment.markdown(markdown))

    await cultivate_quick_cmd.finish(msg)


# 突破快捷操作
breakthrough_quick_cmd = on_command("突破快捷", aliases={"突破菜单"}, priority=4, block=True)

@breakthrough_quick_cmd.handle()
async def handle_breakthrough_quick(event: MessageEvent, args: Message = CommandArg()):
    """显示突破快捷操作菜单"""
    from ..platform_utils import get_unified_player
    from ..models.db import safe_session

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await breakthrough_quick_cmd.finish("⛔ 请先创建角色")

    # 创建突破快捷菜单
    markdown = create_breakthrough_markdown()

    msg = Message(
        "⛓️‍💥 突破快捷菜单\n"
        "━━━━━━━━━━━━━\n"
        "💡 选择突破方式\n"
        "⚠️ 突破失败会损失修为"
    )
    msg.append(MessageSegment.markdown(markdown))

    await breakthrough_quick_cmd.finish(msg)


# 加点快捷操作
assign_points_quick_cmd = on_command("加点快捷", aliases={"加点菜单"}, priority=4, block=True)

@assign_points_quick_cmd.handle()
async def handle_assign_points_quick(event: MessageEvent, args: Message = CommandArg()):
    """显示加点快捷操作菜单"""
    from ..platform_utils import get_unified_player
    from ..models.db import safe_session

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await assign_points_quick_cmd.finish("⛔ 请先创建角色")

        if player.attribute_points <= 0:
            await assign_points_quick_cmd.finish(
                "⛔ 当前没有可用属性点\n"
                "💡 通过【突破】获得属性点"
            )

    # 创建加点快捷菜单
    markdown = create_attribute_points_markdown(player.attribute_points)

    msg = Message(
        f"✨ 属性点分配菜单\n"
        f"━━━━━━━━━━━━━\n"
        f"🎯 当前可用属性点: {player.attribute_points}\n"
        f"💡 点击下方按钮快速加点"
    )
    msg.append(MessageSegment.markdown(markdown))

    await assign_points_quick_cmd.finish(msg)
