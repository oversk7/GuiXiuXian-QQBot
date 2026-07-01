"""
战斗信息查看命令

提供查看玩家战斗属性的命令
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..battle.integration_helper import BattleIntegrationHelper

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
        battle_attr_display = await BattleIntegrationHelper.get_battle_attribute_display_async(player, session)

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
        await battle_info.finish(full_info)


# 查看属性详情命令
battle_detail = on_command("战力说明", aliases={"战力介绍"}, block=True, priority=5)


@battle_detail.handle()
async def handle_battle_detail(event: MessageEvent, args: Message = CommandArg()):
    """查看战斗属性详细说明"""
    
    detail_info = [
        "⚔️ 诡修仙战斗属性详解 ⚔️",
        "",
        "💥 暴击率",
        "• 普通攻击触发暴击的概率",
        "• 暴击伤害为1.5倍基础伤害",
        "",
        "🔄 连击率",
        "• 在自己回合内连续普攻的概率",
        "• 触发时可连续攻击2-4次",
        "• 每次连击都独立计算暴击等效果",
        "",
        "🛡️ 反击率",
        "• 被攻击时自动反击的概率",
        "• 反击不占用自己的回合",
        "• 反击攻击也可触发暴击等效果",
        "",
        "⚡ 闪避率",
        "• 闪避敌方攻击的概率",
        "• 与敌方命中率对抗",
        "• 最终命中率不低于10%",
        "",
        "🎯 命中率",
        "• 攻击命中敌方的概率",
        "• 敌方闪避率可抵消",
        "",
        "✨ 灵爆率",
        "• 技能攻击的暴击概率",
        "• 独立于普攻暴击率",
        "• 技能暴击伤害同样为1.5倍",
        "",
        "🗡️ 穿透率",
        "• 无视敌方防御的比例",
        "",
        "🛡️ 抗暴率",
        "• 同时降低敌方暴击率和暴击力",
        "• 敌方实际暴击率 = 敌方暴击率 - 我方抗暴率",
        "• 敌方实际暴击力 = 敌方暴击力 - 我方抗暴率",
        "",
        "📿 抗连击率",
        "• 降低敌方连击率的属性",
        "• 敌方实际连击率 = 敌方连击率 - 我方抗连击率",
        "• 可有效减少受到的连击次数",
        "",
        "🔮 抗反击率",
        "• 降低敌方反击率的属性",
        "• 敌方实际反击率 = 敌方反击率 - 我方抗反击率",
        "• 可有效减少被反击的概率",
        "",
        "━━━━━━━━━━━━━",
        "💡 想了解基础属性加点？发送【加点帮助】",
        "💡 查看当前战斗属性？发送【战力】"
    ]

    await battle_detail.finish("\n".join(detail_info))
