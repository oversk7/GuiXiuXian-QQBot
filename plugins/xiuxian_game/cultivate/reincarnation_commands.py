"""
冥返系统命令模块
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .reincarnation import ReincarnationService


reincarnate_cmd = on_command("冥返", aliases={"轮回", "重生"}, block=True, priority=5)
reincarnation_info_cmd = on_command("冥返信息", aliases={"转数信息", "轮回信息"}, block=True, priority=5)


@reincarnate_cmd.handle()
async def handle_reincarnate(event: MessageEvent):
    """处理冥返命令"""
    from ..platform_utils import get_unified_player, is_guild_message
    
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await reincarnate_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await reincarnate_cmd.finish("⛔ 请先使用【注册】命令创建角色")
        
        # 检查是否可以冥返
        if not await ReincarnationService.can_reincarnate(player):
            required_level = ReincarnationService.get_required_level_for_reincarnation(player.reincarnation_level)
            reincarnation_count = player.reincarnation_level + 1
            await reincarnate_cmd.finish(
                f"⛔ 冥返条件不足！\n"
                f"━━━━━━━━━━━━━\n"
                f"✧ 当前等级：Lv.{player.level}\n"
                f"✧ 需要等级：Lv.{required_level} (第{reincarnation_count}次冥返)\n"
                f"━━━━━━━━━━━━━\n"
                "⬇️ 【修炼】【突破】提升等级"
            )
        
        # 执行冥返
        result_msg = await ReincarnationService.perform_reincarnation(session, player)
        await reincarnate_cmd.finish(message_add_head(result_msg, event))


@reincarnation_info_cmd.handle()
async def handle_reincarnation_info(event: MessageEvent):
    """处理冥返信息查询命令"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await reincarnation_info_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await reincarnation_info_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        current_level = player.level
        current_reincarnation = player.reincarnation_level
        required_level = ReincarnationService.get_required_level_for_reincarnation(current_reincarnation)
        next_reincarnation = current_reincarnation + 1

        # 计算当前转数的加成
        attr_points_per_level = ReincarnationService.get_attribute_points_per_level(current_reincarnation)
        cultivation_bonus = ReincarnationService.get_cultivation_efficiency_bonus(current_reincarnation)
        seclusion_bonus = ReincarnationService.get_seclusion_efficiency_bonus(current_reincarnation)

        # 计算下次转数的加成
        next_attr_points = ReincarnationService.get_attribute_points_per_level(next_reincarnation)
        next_cultivation_bonus = ReincarnationService.get_cultivation_efficiency_bonus(next_reincarnation)
        next_seclusion_bonus = ReincarnationService.get_seclusion_efficiency_bonus(next_reincarnation)

        # 构建信息消息
        msg_lines = [
            "🌟 冥返轮回信息",
            "━━━━━━━━━━━━━",
            f"✧ 当前转数：{current_reincarnation}转",
            f"✧ 当前等级：Lv.{current_level}",
            "",
            "【当前转数加成】",
            f"✧ 每级属性点：{attr_points_per_level}",
            f"✧ 修炼效率：+{cultivation_bonus:.0%}",
            f"✧ 闭关效率：+{seclusion_bonus:.0%}",
            "",
            "【下次冥返要求】",
            f"✧ 需要等级：Lv.{required_level} (第{next_reincarnation}次冥返)",
            f"✧ 距离目标：{max(0, required_level - current_level)} 级",
            "",
            "【下次转数加成】",
            f"✧ 每级属性点：{next_attr_points} (+{next_attr_points - attr_points_per_level})",
            f"✧ 修炼效率：+{next_cultivation_bonus:.0%} (+{next_cultivation_bonus - cultivation_bonus:.0%})",
            f"✧ 闭关效率：+{next_seclusion_bonus:.0%} (+{next_seclusion_bonus - seclusion_bonus:.0%})",
            "━━━━━━━━━━━━━"
        ]

        # 如果已经可以冥返，添加提示
        if current_level >= required_level:
            msg_lines.append("🎉 已达到冥返要求！使用【冥返】命令进行轮回")
        else:
            msg_lines.append("⬇️ 【修炼】【突破】提升等级")

        await reincarnation_info_cmd.finish(message_add_head("\n".join(msg_lines), event))
