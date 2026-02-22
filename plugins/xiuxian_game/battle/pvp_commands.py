"""
PVP切磋系统命令模块

提供玩家间自由切磋的功能，不造成任何损失，不需要双方同意
"""

import base64

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .integration_helper import BattleIntegrationHelper
from .battle_image import get_battle_image_generator
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
        # 使用跨平台工具获取挑战者信息
        from ..platform_utils import get_unified_player, is_guild_message
        challenger = await get_unified_player(session, event)
        if not challenger:
            if is_guild_message(event):
                await pvp_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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

        # 执行PVP战斗（使用简洁格式）
        try:
            victory, battle_log, challenger_damage, target_damage = await BattleIntegrationHelper.compact_player_vs_player_battle(
                challenger, target_player, session, seed=seed, max_rounds=30
            )

            # 计算最终血量
            p1_final_hp = max(0, challenger.hp - challenger_damage)
            p2_final_hp = max(0, target_player.hp - target_damage)

            # 判断胜负
            if p2_final_hp == 0 and p1_final_hp > 0:
                winner_name = challenger.nickname
            elif p1_final_hp == 0:
                winner_name = target_player.nickname
            else:
                winner_name = None  # 平局

            # 生成战斗图片
            gen = get_battle_image_generator()
            img_bytes = gen.generate_battle_image(
                battle_log=battle_log,
                player1_name=f"{challenger.nickname}[{challenger.uid}]",
                player2_name=f"{target_player.nickname}[{target_player.uid}]",
                player1_level=challenger.level,
                player2_level=target_player.level,
                player1_hp=p1_final_hp,
                player1_max_hp=challenger.max_hp,
                player2_hp=p2_final_hp,
                player2_max_hp=target_player.max_hp,
                winner_name=winner_name,
            )

            img_b64 = base64.b64encode(img_bytes).decode()
            msg = message_add_head("⚔️ 战斗结束，查看图片获取详情", event)
            msg.append(MessageSegment.file_image(img_b64))
            await pvp_cmd.finish(msg)

        except ValueError as e:
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

        # 执行模拟战斗（使用简洁格式）
        try:
            _, battle_log, p1_damage, p2_damage = await BattleIntegrationHelper.compact_player_vs_player_battle(
                player1, player2, session, seed=seed, max_rounds=30
            )

            # 计算最终血量
            p1_final_hp = max(0, player1.hp - p1_damage)
            p2_final_hp = max(0, player2.hp - p2_damage)

            # 判断胜负
            if p2_final_hp == 0 and p1_final_hp > 0:
                winner_name = player1.nickname
            elif p1_final_hp == 0:
                winner_name = player2.nickname
            else:
                winner_name = None  # 平局

            # 生成战斗图片
            gen = get_battle_image_generator()
            img_bytes = gen.generate_battle_image(
                battle_log=battle_log,
                player1_name=f"{player1.nickname}[{player1.uid}]",
                player2_name=f"{player2.nickname}[{player2.uid}]",
                player1_level=player1.level,
                player2_level=player2.level,
                player1_hp=p1_final_hp,
                player1_max_hp=player1.max_hp,
                player2_hp=p2_final_hp,
                player2_max_hp=player2.max_hp,
                winner_name=winner_name,
            )

            img_b64 = base64.b64encode(img_bytes).decode()
            msg = message_add_head("🎮 模拟战斗结束，查看图片获取详情", event)
            msg.append(MessageSegment.file_image(img_b64))
            await simulate_cmd.finish(msg)

        except ValueError as e:
            await simulate_cmd.finish(f"⛔ 模拟战斗过程中发生错误：{str(e)}")
