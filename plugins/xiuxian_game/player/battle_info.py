"""
战斗信息查看命令

提供查看玩家战斗属性的命令
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import get_session
from ..models.player import Player
from ..battle.integration_helper import BattleIntegrationHelper
from sqlalchemy import select

# 查看战斗属性命令
battle_info = on_command("战力", aliases={"属性", "我的战力"}, block=True, priority=5)


@battle_info.handle()
async def handle_battle_info(event: MessageEvent, args: Message = CommandArg()):
    """查看战斗属性"""
    user_id = event.get_user_id()
    
    async with get_session() as session:
        # 获取玩家信息
        result = await session.execute(select(Player).where(Player.id == user_id))
        player = result.scalars().first()
        
        if not player:
            await battle_info.send(event, "❌ 你还没有创建角色，请先使用 创建角色 命令")
            return
        
        # 获取战斗属性显示
        battle_attr_display = BattleIntegrationHelper.get_battle_attribute_display(player)
        
        # 基础属性显示
        basic_info = [
            f"👤 {player.nickname} (Lv.{player.level})",
            f"❤️ 血量: {player.hp}/{player.max_hp}",
            f"🧠 理智: {player.mp}/{player.max_mp}",
            f"⚔️ 攻击: {player.attack}",
            f"🛡️ 防御: {player.defense}",
            f"⚡ 敏捷: {player.agility}",
            f"🍀 运气: {player.luck}",
            ""
        ]
        
        # 组合完整信息
        full_info = "\n".join(basic_info) + battle_attr_display
        await battle_info.finish(full_info)


# 查看属性详情命令
battle_detail = on_command("属性说明", aliases={"属性介绍"}, block=True, priority=5)


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
        "• 最终命中率不高于95%",
        "",
        "✨ 灵爆率",
        "• 技能攻击的暴击概率",
        "• 独立于普攻暴击率",
        "• 技能暴击伤害同样为1.5倍",
        "",
        "🗡️ 穿透率",
        "• 无视敌方防御的比例",
    ]
    
    await battle_detail.send(event, "\n".join(detail_info))
