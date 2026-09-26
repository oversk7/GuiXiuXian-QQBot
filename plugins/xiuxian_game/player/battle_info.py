"""
战斗信息查看命令

提供查看玩家战斗属性的命令
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..battle.integration_helper import BattleIntegrationHelper
from ..utils_markdown import build_markdown, cmd

# 查看战斗属性命令
battle_info = on_command("战力", aliases={"属性", "我的战力"}, block=True, priority=5)


@battle_info.handle()
async def handle_battle_info(event: MessageEvent, args: Message = CommandArg()):
    """查看战斗属性"""
    from ..platform_utils import get_unified_player, is_guild_message
    from ..models.db import safe_session

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)

        if not player:
            if is_guild_message(event):
                await battle_info.send("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await battle_info.send("❌ 你还没有创建角色，请先使用 创建角色 命令")
            return

        # 获取包含装备/丹药/临时buff/宠物加成的有效属性
        effective_attrs = await player.get_effective_attributes(session)

        # 获取战斗属性显示（包含临时buff）
        battle_attr_display = await BattleIntegrationHelper.get_battle_attribute_display_async(player, session, effective_attrs=effective_attrs)

        # 基础属性显示（使用有效属性）
        basic_info = [
            f"👤 {player.nickname} (Lv.{player.level})",
            f"❤️ 血量: {player.hp}/{effective_attrs['max_hp']}",
            f"🧠 理智: {player.mp}/{effective_attrs['max_mp']}",
            f"⚔️ 攻击: {effective_attrs['attack']}",
            f"🛡️ 防御: {effective_attrs['defense']}",
            f"⚡ 敏捷: {effective_attrs['agility']}",
            f"🍀 运气: {effective_attrs['luck']}",
            ""
        ]

        # 检查是否有临时buff
        from ..models.temporary_buff import TemporaryBuff
        active_buffs = await TemporaryBuff.get_active_buffs(session, player.id)

        buff_info = ""
        if active_buffs:
            buff_info = f"\n\n✨ 当前增益状态: {len(active_buffs)}个\n💡 输入【增益状态】查看详情"

        # 组合完整信息
        full_info = "\n".join(basic_info) + battle_attr_display + buff_info
        full_info += f"\n***\n{cmd('属性分解')} | {cmd('战力说明')} | {cmd('装备栏')}"
    await battle_info.finish(build_markdown(full_info))
