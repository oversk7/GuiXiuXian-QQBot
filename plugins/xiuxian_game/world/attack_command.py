"""
攻击命令

处理玩家攻击其他玩家或NPC的功能，集成现有战斗系统
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import time

from ..models.db import safe_session
from ..models.player import Player
from ..models.npc import NPCType, NPCStatus
from ..utils import message_add_head
from .location_service import LocationService
from .npc_service import NPCService
from ..battle.integration_helper import BattleIntegrationHelper


# ==================== 攻击命令 ====================
attack_cmd = on_command("攻击", aliases={"死斗"}, block=True, priority=5)


@attack_cmd.handle()
async def handle_attack(event: MessageEvent, args: Message = CommandArg()):
    """处理攻击命令"""
    args_text = args.extract_plain_text().strip()
    
    if not args_text:
        help_msg = (
            "⚔️ 攻击系统\n"
            "━━━━━━━━━━━━━\n"
            "🎯 使用方法：\n"
            "【攻击 <目标名称>】攻击指定目标\n"
            "【攻击 <UID>】攻击指定UID的玩家\n"
            "━━━━━━━━━━━━━\n"
            "💡 可攻击目标：\n"
            "• 其他玩家（PVP切磋）\n"
            "• 鬼怪NPC（真实战斗）\n"
            "• 可击杀的NPC\n"
            "━━━━━━━━━━━━━\n"
            "🔍 智能匹配：\n"
            "• 支持部分名称匹配\n"
            "• 【攻击 乔强】可匹配【邪教徒·乔强】\n"
            "• 【攻击 邪教徒】可匹配【邪教徒·乔强】\n"
            "━━━━━━━━━━━━━\n"
            "⚠️ 注意事项：\n"
            "• 攻击玩家不会造成真实损失\n"
            "• 攻击NPC可能导致其死亡\n"
            "• 死亡的NPC会在一定时间后复活\n"
            "━━━━━━━━━━━━━\n"
            "🌟 示例：攻击 1001 或 攻击 乔强"
        )
        await attack_cmd.finish(message_add_head(help_msg, event))
    
    async with safe_session() as session:
        player: Player = await session.get(Player, event.get_user_id())
        if not player:
            await attack_cmd.finish("⛔ 请先创建角色")
        
        if player.is_in_dungeon():
            await attack_cmd.finish("⛔ 你在诡域中，无法攻击现实世界的目标")
        
        if player.hp <= 0:
            await attack_cmd.finish("⛔ 你已死亡，无法发起攻击")
        
        # 获取当前位置
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()
        
        # 尝试解析目标
        target_player, target_npc = await parse_attack_target(session, args_text, current_x, current_y, current_region)
        
        if target_player:
            await handle_player_attack(session, player, target_player, event)
        elif target_npc:
            await handle_npc_attack(session, player, target_npc, event)
        else:
            # 检查是否有多个匹配结果
            location = await LocationService.get_location_by_coordinates(session, current_x, current_y, current_region)
            if location:
                possible_npcs = await find_npc_by_smart_match(session, args_text, location.id)
                if len(possible_npcs) > 1:
                    npc_list = []
                    for npc in possible_npcs[:5]:  # 最多显示5个
                        npc_list.append(f"• {npc.name}")

                    msg = (
                        f"🔍 找到多个匹配'{args_text}'的目标：\n"
                        "━━━━━━━━━━━━━\n" +
                        "\n".join(npc_list) +
                        ("\n..." if len(possible_npcs) > 5 else "") +
                        "\n━━━━━━━━━━━━━\n"
                        "💡 请使用更具体的名称，如：\n"
                        f"• 【攻击 {possible_npcs[0].name.split('·')[-1]}】\n"
                        f"• 【攻击 {possible_npcs[0].name}】"
                    )
                    await attack_cmd.finish(message_add_head(msg, event))

            await attack_cmd.finish(f"⛔ 找不到目标'{args_text}'，请确认目标在当前位置")


async def parse_attack_target(session, target_name: str, x: int, y: int, region: str):
    """解析攻击目标"""
    target_player = None
    target_npc = None

    # 尝试按UID查找玩家
    if target_name.isdigit():
        uid = int(target_name)
        # 查找附近的玩家
        nearby_players = await LocationService.get_nearby_players(
            session, x, y, region, max_distance=0
        )
        for p in nearby_players:
            if p.uid == uid:
                target_player = p
                break
    else:
        # 按名称查找玩家
        nearby_players = await LocationService.get_nearby_players(
            session, x, y, region, max_distance=0
        )
        for p in nearby_players:
            if p.nickname == target_name:
                target_player = p
                break

        # 如果没找到玩家，查找NPC
        if not target_player:
            location = await LocationService.get_location_by_coordinates(session, x, y, region)
            if location:
                # 先尝试精确匹配
                target_npc = await NPCService.get_npc_by_name(session, target_name, location.id)

                if not target_npc:
                    # 尝试智能匹配（支持带点号的名字）
                    possible_npcs = await find_npc_by_smart_match(session, target_name, location.id)
                    if len(possible_npcs) == 1:
                        target_npc = possible_npcs[0]
                    elif len(possible_npcs) > 1:
                        # 多个匹配结果，尝试更精确的匹配
                        exact_matches = [npc for npc in possible_npcs if target_name.lower() in npc.name.lower()]
                        if len(exact_matches) == 1:
                            target_npc = exact_matches[0]

    return target_player, target_npc


async def find_npc_by_smart_match(session, target_name: str, location_id: int):
    """智能匹配NPC名称，支持带点号的名字"""
    from sqlalchemy import select, and_, or_
    from ..models.npc import NPC, NPCStatus

    # 清理输入的目标名称
    clean_target = target_name.strip()

    # 构建多种匹配条件
    conditions = [
        NPC.location_id == location_id,
        NPC.is_active == True,
        NPC.status != NPCStatus.DEAD
    ]

    # 匹配策略：
    # 1. 包含目标名称的NPC
    # 2. 点号后面部分匹配（如"乔强"匹配"邪教徒·乔强"）
    # 3. 点号前面部分匹配（如"邪教徒"匹配"邪教徒·乔强"）
    name_conditions = or_(
        NPC.name.like(f"%{clean_target}%"),  # 基础模糊匹配
        NPC.name.like(f"%·{clean_target}"),  # 匹配点号后的部分
        NPC.name.like(f"{clean_target}·%"),  # 匹配点号前的部分
    )

    conditions.append(name_conditions)

    stmt = select(NPC).where(and_(*conditions))
    result = await session.execute(stmt)
    npcs = result.scalars().all()

    # 按匹配优先级排序
    def match_priority(npc):
        name = npc.name.lower()
        target = clean_target.lower()

        # 精确匹配优先级最高
        if name == target:
            return 0
        # 完整包含目标名称
        elif target in name:
            return 1
        # 点号后匹配
        elif f"·{target}" in name:
            return 2
        # 点号前匹配
        elif f"{target}·" in name:
            return 3
        # 其他模糊匹配
        else:
            return 4

    return sorted(npcs, key=match_priority)


async def handle_player_attack(session, attacker: Player, target: Player, event: MessageEvent):
    """处理玩家vs玩家攻击（PVP切磋）"""
    if attacker.id == target.id:
        await attack_cmd.finish("⛔ 你不能攻击自己")
    
    # 检查目标是否在同一位置
    if attacker.x != target.x or attacker.y != target.y or attacker.region != target.region:
        await attack_cmd.finish("⛔ 目标不在当前位置")
    
    # 执行PVP战斗
    battle_timestamp = int(time.time() * 1000)
    seed = f"PVP_{attacker.id}_{target.id}_{battle_timestamp}"
    
    try:
        victory, battle_log, attacker_damage, target_damage = BattleIntegrationHelper.compact_player_vs_player_battle(
            attacker, target, seed=seed, max_rounds=30
        )
        
        # 构建战斗结果消息
        result_lines = [
            "⚔️ PVP切磋结果 ⚔️",
            "━━━━━━━━━━━━━"
        ]
        
        # 添加玩家信息
        from ..player.info import realm_by_level
        attacker_realm = realm_by_level(attacker.level)
        target_realm = realm_by_level(target.level)
        
        result_lines.extend([
            f"🔥 {attacker.nickname}[UID:{attacker.uid}] Lv.{attacker.level} {attacker_realm}",
            f"🆚 {target.nickname}[UID:{target.uid}] Lv.{target.level} {target_realm}",
            "━━━━━━━━━━━━━"
        ])
        
        # 显示简洁的战斗日志
        result_lines.extend(battle_log)
        
        result_lines.extend([
            "━━━━━━━━━━━━━",
            "💡 这只是模拟切磋，不会造成任何实际损失",
        ])
        
        await attack_cmd.finish(message_add_head("\n".join(result_lines), event))
        
    except ValueError as e:
        await attack_cmd.finish(f"⛔ 战斗系统错误：{str(e)}")


async def handle_npc_attack(session, attacker: Player, target_npc, event: MessageEvent):
    """处理玩家vs NPC攻击"""
    # 检查NPC状态
    if target_npc.is_dead():
        await attack_cmd.finish(f"⛔ {target_npc.name}已经死亡")
    
    if target_npc.is_respawning():
        remaining = target_npc.respawn_time - target_npc.death_time
        minutes = int(remaining.total_seconds() / 60)
        await attack_cmd.finish(f"⛔ {target_npc.name}正在复活中，还需{minutes}分钟")
    
    # 检查是否可以攻击
    if not target_npc.is_killable and target_npc.npc_type != NPCType.GHOST:
        await attack_cmd.finish(f"⛔ {target_npc.name}是友善的NPC，无法攻击")
    
    # 构建NPC战斗属性
    npc_stats = {
        "hp": target_npc.hp,
        "attack": target_npc.attack,
        "defense": target_npc.defense,
        "agility": target_npc.agility
    }
    
    # 执行战斗
    battle_timestamp = int(time.time() * 1000)
    seed = f"NPC_{attacker.id}_{target_npc.npc_id}_{battle_timestamp}"
    
    try:
        victory, battle_log, damage_taken = BattleIntegrationHelper.enhanced_player_vs_monster_battle(
            attacker, npc_stats, target_npc.name, seed=seed, max_rounds=50
        )
        
        # 更新玩家血量
        attacker.hp = max(0, attacker.hp - damage_taken)
        
        # 构建战斗结果
        result_lines = [
            f"⚔️ {attacker.nickname} VS {target_npc.name}",
            "━━━━━━━━━━━━━"
        ]
        
        # 显示战斗日志
        result_lines.extend(battle_log)
        
        if victory:
            # 玩家胜利，NPC死亡
            if target_npc.is_killable:
                target_npc.kill()
                result_lines.append(f"💀 {target_npc.name}被击杀")
                if target_npc.respawn_duration_minutes > 0:
                    result_lines.append(f"⏰ {target_npc.respawn_duration_minutes}分钟后复活")
            
            # 鬼怪特殊奖励
            if target_npc.npc_type == NPCType.GHOST:
                exp_gain = target_npc.level * 10
                gold_gain = target_npc.level * 5
                attacker.exp += exp_gain
                attacker.gold += gold_gain
                result_lines.append(f"🎉 击杀鬼怪获得 {exp_gain} EXP，{gold_gain} 金币")
        else:
            # 玩家失败
            if attacker.hp <= 0:
                result_lines.append("💀 你被击败了")
            else:
                result_lines.append("⏰ 战斗超时，平局")
        
        await session.commit()
        await attack_cmd.finish(message_add_head("\n".join(result_lines), event))
        
    except ValueError as e:
        await attack_cmd.finish(f"⛔ 战斗系统错误：{str(e)}")


# ==================== 击杀统计命令 ====================
kill_stats_cmd = on_command("击杀统计", aliases={"战斗统计"}, block=True, priority=5)


@kill_stats_cmd.handle()
async def handle_kill_stats(event: MessageEvent):
    """显示击杀统计"""
    async with safe_session() as session:
        player: Player = await session.get(Player, event.get_user_id())
        if not player:
            await kill_stats_cmd.finish("⛔ 请先创建角色")
        
        # 这里可以添加击杀统计的逻辑
        # 目前先显示基本信息
        lines = [
            f"⚔️ {player.nickname} 的战斗统计",
            "━━━━━━━━━━━━━",
            f"👤 玩家：{player.nickname} [UID:{player.uid}]",
            f"⚡ 等级：{player.level}",
            f"❤️ 血量：{player.hp}/{player.max_hp}",
            f"⚔️ 攻击：{player.attack}",
            f"🛡️ 防御：{player.defense}",
            f"💨 敏捷：{player.agility}",
            "",
            "📊 战斗记录：",
            "• 击杀鬼怪：暂未统计",
            "• PVP切磋：暂未统计",
            "• 战斗胜率：暂未统计",
            "",
            "💡 提示：击杀统计功能正在开发中"
        ]
        
        await kill_stats_cmd.finish(message_add_head("\n".join(lines), event))
