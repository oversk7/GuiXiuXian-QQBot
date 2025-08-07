"""
PVP切磋系统命令模块

提供玩家间自由切磋的功能，不造成任何损失，不需要双方同意
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .integration_helper import BattleIntegrationHelper
import time


# ==================== PVP切磋指令 ====================
pvp_cmd = on_command("切磋", aliases={"pvp", "PVP", "挑战"}, block=True, priority=5)


@pvp_cmd.handle()
async def handle_pvp(event: MessageEvent, args: Message = CommandArg()):
    """处理PVP切磋命令"""
    args_text = args.extract_plain_text().strip()
    
    if not args_text:
        help_msg = (
            "⚔️ PVP切磋系统 ⚔️\n"
            "━━━━━━━━━━━━━\n"
            "🎯 使用方法：\n"
            "【切磋 <UID>】 向指定玩家发起切磋\n"
            "【模拟战斗 <UID1> <UID2>】 观看两个玩家的模拟战斗\n"
            "━━━━━━━━━━━━━\n"
            "💡 特点：\n"
            "• 无需对方同意，立即开始战斗\n"
            "• 不会造成任何损失（血量、物品等）\n"
            "• 不会记录战绩，纯粹切磋交流\n"
            "• 基于双方当前属性进行模拟战斗\n"
            "━━━━━━━━━━━━━\n"
            "⚡ 战斗机制：\n"
            "• 敏捷高的玩家更容易获得先手\n"
            "• 支持暴击、连击、反击、闪避等效果\n"
            "• 最多进行30回合，超时则平局\n"
            "━━━━━━━━━━━━━\n"
            "🌟 示例：切磋 1001"
        )
        await pvp_cmd.finish(message_add_head(help_msg, event))
    
    async with safe_session() as session:
        # 获取挑战者信息
        challenger = await session.get(Player, event.get_user_id())
        if not challenger:
            await pvp_cmd.finish("⛔ 请先创建角色")
        
        # 检查挑战者血量
        if challenger.hp <= 0:
            await pvp_cmd.finish("⛔ 你已经没有血量了，请先恢复后再切磋")
        
        # 解析目标玩家
        target_player = None
        
        # 尝试解析UID
        try:
            target_uid = int(args_text)
            stmt = select(Player).where(Player.uid == target_uid)
            target_player = (await session.execute(stmt)).scalars().first()
        except ValueError:
            # 如果不是数字，可能是@某人或其他格式
            await pvp_cmd.finish("⛔ 请输入正确的UID，例如：切磋 1001")
        
        if not target_player:
            await pvp_cmd.finish("⛔ 找不到指定的玩家")
        
        # 检查是否自己挑战自己
        if target_player.id == challenger.id:
            await pvp_cmd.finish("⛔ 不能挑战自己哦")
        
        # 检查目标玩家血量
        if target_player.hp <= 0:
            await pvp_cmd.finish(f"⛔ {target_player.nickname}[UID:{target_player.uid}]已经没有血量了，无法切磋")
        
        # 创建战斗种子
        battle_timestamp = int(time.time() * 1000)
        seed = f"PVP_{challenger.id}_{target_player.id}_{battle_timestamp}"
        
        # 执行PVP战斗
        try:
            victory, battle_log, challenger_damage, target_damage = BattleIntegrationHelper.enhanced_player_vs_player_battle(
                challenger, target_player, seed=seed, max_rounds=30
            )
            
            # 构建战斗结果消息
            result_lines = [
                "⚔️ PVP切磋结果 ⚔️",
                "━━━━━━━━━━━━━"
            ]
            
            # 添加玩家信息
            from ..player.info import realm_by_level
            challenger_realm = realm_by_level(challenger.level)
            target_realm = realm_by_level(target_player.level)
            
            result_lines.extend([
                f"🔥 {challenger.nickname}[UID:{challenger.uid}] Lv.{challenger.level} {challenger_realm}",
                f"🆚 {target_player.nickname}[UID:{target_player.uid}] Lv.{target_player.level} {target_realm}",
                "━━━━━━━━━━━━━"
            ])
            
            # 添加关键战斗日志（最多显示8条）
            key_logs = [log for log in battle_log if any(keyword in log for keyword in 
                       ["暴击", "连击", "反击", "穿透", "闪避", "胜利", "战败", "回合", "超时", "VS"])]
            
            if len(key_logs) > 10:
                result_lines.extend(key_logs[:4])
                result_lines.append("...")
                result_lines.extend(key_logs[-4:])
            else:
                result_lines.extend(key_logs)
            
            result_lines.extend([
                "━━━━━━━━━━━━━",
                "💡 这只是模拟切磋，不会造成任何实际损失",
            ])
            
            await pvp_cmd.finish(message_add_head("\n".join(result_lines), event))
            
        except Exception as e:
            await pvp_cmd.finish(f"⛔ 战斗过程中发生错误：{str(e)}")


# ==================== 模拟战斗指令 ====================
simulate_cmd = on_command("模拟战斗", aliases={"模拟切磋"}, block=True, priority=5)


@simulate_cmd.handle()
async def handle_simulate(event: MessageEvent, args: Message = CommandArg()):
    """处理模拟战斗命令 - 可以指定两个不同的玩家进行模拟"""
    args_text = args.extract_plain_text().strip()
    
    if not args_text:
        help_msg = (
            "🎮 模拟战斗系统 🎮\n"
            "━━━━━━━━━━━━━\n"
            "🎯 使用方法：\n"
            "【模拟战斗 UID1 UID2】 模拟两个玩家的战斗\n"
            "━━━━━━━━━━━━━\n"
            "💡 特点：\n"
            "• 可以观看任意两个玩家的模拟战斗\n"
            "• 完全模拟，不影响任何玩家\n"
            "• 基于玩家当前属性计算\n"
            "━━━━━━━━━━━━━\n"
            "🌟 示例：模拟战斗 1001 1002"
        )
        await simulate_cmd.finish(message_add_head(help_msg, event))
    
    # 解析两个UID
    parts = args_text.split()
    if len(parts) != 2:
        await simulate_cmd.finish("⛔ 格式：模拟战斗 UID1 UID2")
    
    try:
        uid1 = int(parts[0])
        uid2 = int(parts[1])
    except ValueError:
        await simulate_cmd.finish("⛔ UID必须是数字")
    
    if uid1 == uid2:
        await simulate_cmd.finish("⛔ 不能模拟同一个玩家的战斗")
    
    async with safe_session() as session:
        # 获取两个玩家
        stmt1 = select(Player).where(Player.uid == uid1)
        player1 = (await session.execute(stmt1)).scalars().first()
        
        stmt2 = select(Player).where(Player.uid == uid2)
        player2 = (await session.execute(stmt2)).scalars().first()
        
        if not player1:
            await simulate_cmd.finish(f"⛔ 找不到UID为{uid1}的玩家")
        
        if not player2:
            await simulate_cmd.finish(f"⛔ 找不到UID为{uid2}的玩家")
        
        # 创建战斗种子
        battle_timestamp = int(time.time() * 1000)
        seed = f"SIMULATE_{player1.id}_{player2.id}_{battle_timestamp}"
        
        # 执行模拟战斗
        try:
            victory, battle_log, p1_damage, p2_damage = BattleIntegrationHelper.enhanced_player_vs_player_battle(
                player1, player2, seed=seed, max_rounds=30
            )
            
            # 构建战斗结果消息
            result_lines = [
                "🎮 模拟战斗结果 🎮",
                "━━━━━━━━━━━━━"
            ]
            
            # 添加玩家信息
            from ..player.info import realm_by_level
            p1_realm = realm_by_level(player1.level)
            p2_realm = realm_by_level(player2.level)
            
            result_lines.extend([
                f"🔥 {player1.nickname}[UID:{player1.uid}] Lv.{player1.level} {p1_realm}",
                f"🆚 {player2.nickname}[UID:{player2.uid}] Lv.{player2.level} {p2_realm}",
                "━━━━━━━━━━━━━"
            ])
            
            # 添加关键战斗日志
            key_logs = [log for log in battle_log if any(keyword in log for keyword in 
                       ["暴击", "连击", "反击", "穿透", "闪避", "胜利", "战败", "回合", "超时", "VS"])]
            
            if len(key_logs) > 10:
                result_lines.extend(key_logs[:4])
                result_lines.append("...")
                result_lines.extend(key_logs[-4:])
            else:
                result_lines.extend(key_logs)
            
            result_lines.extend([
                "━━━━━━━━━━━━━",
                "💡 这只是模拟战斗，不影响任何玩家"
            ])
            
            await simulate_cmd.finish(message_add_head("\n".join(result_lines), event))
            
        except Exception as e:
            await simulate_cmd.finish(f"⛔ 模拟战斗过程中发生错误：{str(e)}")
