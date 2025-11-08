"""
恶魔轮盘赌游戏主模块
"""
import json
from nonebot import on_command
from nonebot.adapters.qq import Bot, MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from sqlalchemy import select
from ..models.russian_roulette import RoomStatus

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .russian_roulette_service import RussianRouletteService
from .russian_roulette_core import RussianRouletteCore, ItemType
from .russian_roulette_cleanup import RussianRouletteCleanup


def _format_player_items(items_json: str, player_name: str) -> str:
    """格式化玩家道具信息"""
    items = json.loads(items_json or "[]")
    if not items:
        return f"🎒 {player_name} 没有道具"

    # 统计道具数量
    from collections import Counter
    item_counts = Counter(items)

    # 构建道具列表
    item_lines = [f"🎒 {player_name} 的道具", "━━━━━━━━━━━━━"]

    for item_str, count in item_counts.items():
        try:
            item_type = ItemType(item_str)
            item_config = RussianRouletteCore.ITEM_CONFIGS[item_type]
            if count > 1:
                item_lines.append(f"{item_config['name']} x{count}")
            else:
                item_lines.append(f"{item_config['name']}")
            item_lines.append(f"  └ {item_config['description']}")
        except (ValueError, KeyError):
            item_lines.append(f"❓ 未知道具: {item_str} x{count}")

    return "\n".join(item_lines)


# ==================== 房间管理指令 ====================

# 创建房间
create_room_cmd = on_command("恶魔轮盘", aliases={"轮盘赌", "俄罗斯轮盘"}, block=True, priority=5)

@create_room_cmd.handle()
async def handle_create_room(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """创建恶魔轮盘赌房间"""
    # 检查是否为群聊
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await create_room_cmd.finish("⛔ 恶魔轮盘赌只能在群聊中进行")
    
    # 提取群ID
    group_id = session_id.split("_")[1]
    
    args_text = args.extract_plain_text().strip()
    
    # 显示帮助信息
    if not args_text or args_text == "帮助":
        help_msg = (
            "🎮 恶魔轮盘赌游戏\n"
            "━━━━━━━━━━━━━\n"
            "🎯 游戏规则：\n"
            "▫️ 两名玩家轮流使用霰弹枪\n"
            "▫️ 枪内有实弹和空包弹\n"
            "▫️ 将对手血量降为0即获胜\n"
            "▫️ 可使用道具增加战术性\n"
            "━━━━━━━━━━━━━\n"
            "📝 房间指令：\n"
            "▫️ 【恶魔轮盘 创建】 - 创建游戏房间\n"
            "▫️ 【恶魔轮盘 加入 <房间ID>】 - 加入房间\n"
            "▫️ 【退出房间】 - 游戏开始前退出房间\n"
            "▫️ 【恶魔轮盘 开始】 - 开始游戏\n"
            "▫️ 【房间状态】 - 查看房间状态\n"
            "━━━━━━━━━━━━━\n"
            "💰 筹码设置：\n"
            "▫️ 【恶魔轮盘 筹码 <金币数>】 - 只能投注金币\n"
            "▫️ 示例：恶魔轮盘 筹码 1000\n"
            "▫️ 第二位下注者的金额需 ≥ 第一位下注者\n"
            "▫️ 注意：系统将抽取3%税收\n"
            "━━━━━━━━━━━━━\n"
            "🎲 游戏指令：\n"
            "▫️ 【开枪 <自己/对手>】 - 选择射击目标\n"
            "▫️ 【查看道具】 - 查看可用道具\n"
            "▫️ 【使用道具 <道具名>】 - 使用道具\n"
            "▫️ 【使用道具 肾上腺素 <道具名>】 - 偷取指定道具并立刻使用\n"
            "▫️ 【预知】 - 私聊指令，查看预知结果\n"
            "━━━━━━━━━━━━━\n"
            "🎒 道具说明：\n"
            "▫️ 🔪小刀 - 下次射击伤害翻倍\n"
            "▫️ ⛓️手铐 - 限制对手下回合行动\n"
            "▫️ 🚬香烟 - 恢复1点血量\n"
            "▫️ 🔍放大镜 - 查看当前弹药类型\n"
            "▫️ 🍺啤酒 - 退掉当前弹药\n"
            "▫️ 💉肾上腺素 - 偷取对手道具并立刻使用\n"
            "▫️ 💊过期药物 - 40%恢复2血量，否则扣1血量\n"
            "▫️ 🔄逆转器 - 转换当前弹药类型\n"
            "▫️ 📞电话 - 随机预知一发弹药位置\n"
            "▫️ 🎲骰子 - 打乱剩余子弹顺序，使预知失效\n"
            "━━━━━━━━━━━━━\n"
            "💡 注意：预知类道具需要私聊机器人查看结果"
        )
        await create_room_cmd.finish(message_add_head(help_msg, event))
    
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await create_room_cmd.finish("⛔ 请先创建角色")
        
        if args_text == "创建":
            success, msg, room = await RussianRouletteService.create_room(
                session, player.id, group_id
            )
            
            if success:
                result_msg = (
                    f"🎮 恶魔轮盘赌房间创建成功！\n"
                    f"━━━━━━━━━━━━━\n"
                    f"🏠 房间ID：{room.room_id}\n"
                    f"👤 房主：{player.nickname}[UID:{player.uid}]\n"
                    f"📍 绑定群聊：当前群\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💡 等待其他玩家加入...\n"
                    f"📝 使用：恶魔轮盘 加入 {room.room_id}"
                )
                await create_room_cmd.finish(message_add_head(result_msg, event))
            else:
                await create_room_cmd.finish(message_add_head(f"❌ {msg}", event))
        
        elif args_text.startswith("加入 "):
            room_id = args_text[3:].strip()
            if not room_id:
                await create_room_cmd.finish("⛔ 请输入房间ID")
            
            success, msg = await RussianRouletteService.join_room(
                session, player.id, room_id, group_id
            )
            
            if success:
                result_msg = (
                    f"✅ 成功加入房间 {room_id}！\n"
                    f"━━━━━━━━━━━━━\n"
                    f"👤 玩家：{player.nickname}[UID:{player.uid}]\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💰 现在可以设置筹码\n"
                    f"📝 使用：恶魔轮盘 筹码 [金币数]\n"
                    f"📝 示例：恶魔轮盘 筹码 1000\n"
                    f"💸 注意：系统将抽取3%税收"
                )
                await create_room_cmd.finish(message_add_head(result_msg, event))
            else:
                await create_room_cmd.finish(message_add_head(f"❌ {msg}", event))
        
        elif args_text.startswith("筹码 "):
            parts = args_text[3:].strip().split()
            if not parts:
                await create_room_cmd.finish("⛔ 格式：恶魔轮盘 筹码 [金币数]\n例如：恶魔轮盘 筹码 1000\n💸 注意：系统将抽取3%税收")

            # 检查是否尝试使用道具
            if len(parts) > 1:
                await create_room_cmd.finish("⛔ 恶魔轮盘已取消道具和装备筹码，只能使用金币作为筹码\n📝 正确格式：恶魔轮盘 筹码 [金币数]")

            try:
                gold = int(parts[0])
                item_bets = []  # 不再支持道具筹码

            except ValueError:
                await create_room_cmd.finish("⛔ 金币数必须为数字")

            # 获取玩家当前房间
            room = await RussianRouletteService.get_player_active_room(session, player.id)
            if not room:
                await create_room_cmd.finish("⛔ 你不在任何房间中")

            success, msg, bet_details = await RussianRouletteService.set_bet(
                session, player.id, room.room_id, gold, item_bets
            )

            if success:
                opponent_gold = bet_details.get("opponent_gold", 0)
                both_ready = bet_details.get("both_ready", False)
                total_pool = bet_details.get("total_pool", gold + opponent_gold)

                result_lines = [
                    "💰 筹码设置成功！",
                    "━━━━━━━━━━━━━",
                    f"💎 你的投注：{gold}金币"
                ]

                if opponent_gold:
                    result_lines.append(f"🎲 对手投注：{opponent_gold}金币")
                else:
                    result_lines.append("🎲 对手投注：尚未设置")

                if both_ready:
                    tax_amount = bet_details.get("tax_amount", 0)
                    final_reward = bet_details.get("final_reward", total_pool - tax_amount)
                    result_lines.extend([
                        "━━━━━━━━━━━━━",
                        f"💰 奖池总额：{total_pool}金币",
                        f"💸 系统税收：{tax_amount}金币 (3%)",
                        f"🏆 获胜可得：{final_reward}金币"
                    ])
                else:
                    result_lines.extend([
                        "━━━━━━━━━━━━━",
                        f"💰 当前奖池：{total_pool}金币",
                        "⏳ 等待对手设置筹码..."
                    ])

                result_lines.append("📝 双方设置完成后使用：恶魔轮盘 开始")

                result_msg = "\n".join(result_lines)
                await create_room_cmd.finish(message_add_head(result_msg, event))
            else:
                await create_room_cmd.finish(message_add_head(f"❌ {msg}", event))
        
        elif args_text == "开始":
            # 获取玩家当前房间
            room = await RussianRouletteService.get_player_active_room(session, player.id)
            if not room:
                await create_room_cmd.finish("⛔ 你不在任何房间中")
            
            success, msg, game = await RussianRouletteService.start_game(
                session, room.room_id
            )
            
            if success:
                # 获取游戏状态显示
                game_state = {
                    "bullets": game.bullets,
                    "current_bullet_index": game.current_bullet_index,
                    f"{room.player1_id}_hp": game.player1_hp,
                    f"{room.player2_id}_hp": game.player2_hp,
                    "is_sawed_off": game.is_sawed_off,
                    "handcuffed_player_id": game.handcuffed_player_id,
                    f"{room.player1_id}_items": game.player1_items,
                    f"{room.player2_id}_items": game.player2_items
                }

                # 获取玩家信息
                player1 = await session.get(Player, room.player1_id)
                player2 = await session.get(Player, room.player2_id)
                player_names = {
                    room.player1_id: player1.nickname,
                    room.player2_id: player2.nickname
                }

                room_info = {
                    "player1_id": room.player1_id,
                    "player2_id": room.player2_id
                }

                display = RussianRouletteCore.get_game_display(game_state, room_info, player_names)
                recommended = RussianRouletteCore.get_recommended_commands(game_state, room.player1_id)

                # 显示初始弹药配置
                bullets = json.loads(game.bullets)
                live_count = sum(1 for b in bullets if b)
                blank_count = sum(1 for b in bullets if not b)

                result_msg = (
                    f"{display}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"👥 对战双方：\n"
                    f"  🔴 {player1.nickname}[UID:{player1.uid}]\n"
                    f"  🔵 {player2.nickname}[UID:{player2.uid}]\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💥 本轮配置：{live_count}发实弹 + {blank_count}发空包弹\n"
                    f"🎯 {player1.nickname} 先手！\n"
                    f"{recommended}"
                )

                # 先发送游戏开始消息
                await bot.send(event, message_add_head(result_msg, event))

                # 延迟一下，然后分两次发送道具信息
                import asyncio
                await asyncio.sleep(1)

                # 发送玩家1的道具
                player1_items_msg = _format_player_items(game.player1_items, player1.nickname)
                await bot.send(event, message_add_head(player1_items_msg, event))

                await asyncio.sleep(1)

                # 发送玩家2的道具
                player2_items_msg = _format_player_items(game.player2_items, player2.nickname)
                await bot.send(event, message_add_head(player2_items_msg, event))

                return  # 使用return而不是finish，因为已经发送了消息
            else:
                await create_room_cmd.finish(message_add_head(f"❌ {msg}", event))
        
        else:
            await create_room_cmd.finish("⛔ 未知指令，使用 '恶魔轮盘 帮助' 查看帮助")


# ==================== 游戏操作指令 ====================

# 开枪指令
shoot_cmd = on_command("开枪", block=True, priority=5)

@shoot_cmd.handle()
async def handle_shoot(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """处理开枪指令"""
    # 检查是否为群聊
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await shoot_cmd.finish("⛔ 游戏指令只能在群聊中使用")
    
    target = args.extract_plain_text().strip()
    if target not in ["自己", "对手"]:
        await shoot_cmd.finish("⛔ 请指定射击目标：开枪 自己/对手")
    
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await shoot_cmd.finish("⛔ 请先创建角色")
        
        # 获取玩家当前房间和游戏
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room:
            await shoot_cmd.finish("⛔ 你不在任何游戏房间中")
        
        game = await RussianRouletteService.get_game_by_room_id(session, room.room_id)
        if not game:
            await shoot_cmd.finish("⛔ 游戏尚未开始")
        
        # 检查是否轮到该玩家
        if game.current_player_id != player.id:
            await shoot_cmd.finish("⛔ 还没轮到你行动")

        # 如果玩家已经重新获得行动权，清除手铐冷却状态
        if getattr(game, "handcuffs_cooldown_player_id", None) == player.id and game.handcuffed_player_id != player.id:
            game.handcuffs_cooldown_player_id = None

        # 检查是否被手铐限制
        if game.handcuffed_player_id == player.id:
            # 解除手铐限制
            game.handcuffed_player_id = None
            # 切换回使用手铐的玩家（对手）
            opponent_id = room.get_opponent_id(player.id)
            game.current_player_id = opponent_id
            await session.commit()

            # 获取对手信息
            opponent = await session.get(Player, opponent_id)
            await shoot_cmd.finish(message_add_head(f"⛓️ 你被手铐限制，跳过本回合\n🔄 轮到 {opponent.nickname} 继续行动", event))
        
        # 确定射击目标
        if target == "自己":
            target_id = player.id
        else:
            target_id = room.get_opponent_id(player.id)
        
        # 构建游戏状态
        game_state = {
            "bullets": game.bullets,
            "current_bullet_index": game.current_bullet_index,
            f"{room.player1_id}_hp": game.player1_hp,
            f"{room.player2_id}_hp": game.player2_hp,
            "is_sawed_off": game.is_sawed_off,
            "handcuffed_player_id": game.handcuffed_player_id,
            "handcuffs_skip_turn": getattr(game, 'handcuffs_skip_turn', False),
            "handcuffs_cooldown_player_id": getattr(game, "handcuffs_cooldown_player_id", None)
        }
        
        # 执行射击
        hit, shoot_msg, game_over = RussianRouletteCore.shoot(
            game_state, player.id, target_id
        )
        
        # 更新游戏状态
        game.bullets = game_state["bullets"]
        game.current_bullet_index = game_state["current_bullet_index"]
        game.player1_hp = game_state[f"{room.player1_id}_hp"]
        game.player2_hp = game_state[f"{room.player2_id}_hp"]
        game.is_sawed_off = game_state["is_sawed_off"]
        game.handcuffed_player_id = game_state.get("handcuffed_player_id")
        game.handcuffs_cooldown_player_id = game_state.get("handcuffs_cooldown_player_id")

        # 检查是否需要重新装弹（在游戏未结束的情况下）
        reload_msg = ""
        if not game_over:
            reloaded, reload_msg = RussianRouletteCore.check_and_reload(
                game_state, room.player1_id, room.player2_id
            )
            if reloaded:
                # 更新重新装弹后的游戏状态
                game.bullets = game_state["bullets"]
                game.current_bullet_index = game_state["current_bullet_index"]
                game.player1_items = game_state[f"{room.player1_id}_items"]
                game.player2_items = game_state[f"{room.player2_id}_items"]
                game.is_sawed_off = game_state["is_sawed_off"]
                game.handcuffed_player_id = game_state.get("handcuffed_player_id")
                game.handcuffs_cooldown_player_id = game_state.get("handcuffs_cooldown_player_id")
                game.magnifier_info = game_state.get("magnifier_info")
                game.phone_info = game_state.get("phone_info")
        
        # 获取玩家信息用于显示
        player1 = await session.get(Player, room.player1_id)
        player2 = await session.get(Player, room.player2_id)
        player_names = {
            room.player1_id: player1.nickname,
            room.player2_id: player2.nickname
        }

        room_info = {
            "player1_id": room.player1_id,
            "player2_id": room.player2_id
        }

        # 构建基础消息
        result_msg = f"🎯 {player.nickname} 对{target}开枪\n{shoot_msg}"

        # 检查是否重新装弹，如果是则需要分别发送道具信息
        reloaded = bool(reload_msg)
        if reload_msg:
            result_msg += f"\n{reload_msg}"

        if game_over:
            # 游戏结束
            winner_id = game_state[f"{room.player1_id}_hp"] > 0 and room.player1_id or room.player2_id
            winner = await session.get(Player, winner_id)

            _, reward_msg = await RussianRouletteService.finish_game(
                session, room.room_id, winner_id
            )

            result_msg += f"\n🏆 {winner.nickname} 获胜！\n{reward_msg}"
        else:
            # 游戏继续 - 构建完整的游戏状态用于显示
            display_game_state = {
                "bullets": game.bullets,
                "current_bullet_index": game.current_bullet_index,
                f"{room.player1_id}_hp": game.player1_hp,
                f"{room.player2_id}_hp": game.player2_hp,
                "is_sawed_off": game.is_sawed_off,
                "handcuffed_player_id": game.handcuffed_player_id,
                f"{room.player1_id}_items": game.player1_items,
                f"{room.player2_id}_items": game.player2_items
            }

            game_display = RussianRouletteCore.get_game_display(display_game_state, room_info, player_names)

            if target == "自己" and not hit:
                # 对自己开空包弹，继续行动
                result_msg += f"\n🔄 {player.nickname} 继续行动\n\n{game_display}"
                # 添加推荐指令
                recommended = RussianRouletteCore.get_recommended_commands(display_game_state, player.id)
                result_msg += f"\n{recommended}"
            else:
                # 切换回合
                opponent_id = room.get_opponent_id(player.id)

                # 检查对手是否被手铐限制
                if game.handcuffed_player_id == opponent_id:
                    # 对手被手铐限制，跳过其回合，当前玩家继续行动
                    game.handcuffed_player_id = None  # 解除手铐限制
                    # 不切换回合，当前玩家继续
                    opponent = await session.get(Player, opponent_id)
                    result_msg += f"\n⛓️ {opponent.nickname} 被手铐限制，跳过回合"
                    result_msg += f"\n🔄 {player.nickname} 继续行动\n\n{game_display}"
                    # 添加推荐指令
                    recommended = RussianRouletteCore.get_recommended_commands(display_game_state, player.id)
                    result_msg += f"\n{recommended}"
                else:
                    # 正常切换回合
                    game.current_player_id = opponent_id
                    opponent = await session.get(Player, opponent_id)
                    result_msg += f"\n🔄 轮到 {opponent.nickname} 行动\n\n{game_display}"
                    # 添加推荐指令
                    recommended = RussianRouletteCore.get_recommended_commands(display_game_state, opponent_id)
                    result_msg += f"\n{recommended}"

        await session.commit()

        # 如果重新装弹了，需要分别发送道具信息
        if reloaded:
            # 先发送基础消息
            await bot.send(event, message_add_head(result_msg, event))

            # 延迟一下，然后分两次发送道具信息
            import asyncio
            await asyncio.sleep(1)

            # 发送玩家1的道具
            player1_items_msg = _format_player_items(game.player1_items, player1.nickname)
            await bot.send(event, message_add_head(player1_items_msg, event))

            await asyncio.sleep(1)

            # 发送玩家2的道具
            player2_items_msg = _format_player_items(game.player2_items, player2.nickname)
            await bot.send(event, message_add_head(player2_items_msg, event))

            return  # 使用return而不是finish，因为已经发送了消息
        else:
            # 没有重新装弹，正常发送消息
            await shoot_cmd.finish(message_add_head(result_msg, event))


# 使用道具指令
use_item_cmd = on_command("使用道具", aliases={"道具"}, block=True, priority=5)

# 使用肾上腺素指令（带参数）
use_adrenaline_cmd = on_command("使用道具 肾上腺素", block=True, priority=4)

@use_adrenaline_cmd.handle()
async def handle_use_adrenaline(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """处理使用肾上腺素指令"""
    # 检查是否为群聊
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await use_adrenaline_cmd.finish("⛔ 游戏指令只能在群聊中使用")

    target_item_name = args.extract_plain_text().strip()
    if not target_item_name:
        await use_adrenaline_cmd.finish("⛔ 请指定要偷取的道具名称\n📝 示例：使用道具 肾上腺素 小刀")

    # 道具名称映射（肾上腺素不能偷取肾上腺素）
    item_mapping = {
        "小刀": ItemType.KNIFE,
        "手铐": ItemType.HANDCUFFS,
        "香烟": ItemType.CIGARETTE,
        "放大镜": ItemType.MAGNIFIER,
        "啤酒": ItemType.BEER,
        "过期药物": ItemType.EXPIRED_MEDICINE,
        "逆转器": ItemType.INVERTER,
        "电话": ItemType.PHONE,
        "骰子": ItemType.DICE
    }

    if target_item_name not in item_mapping:
        available_items = "、".join(item_mapping.keys())
        await use_adrenaline_cmd.finish(f"⛔ 未知道具。可偷取道具：{available_items}")

    target_item_type = item_mapping[target_item_name]

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await use_adrenaline_cmd.finish("⛔ 请先创建角色")

        # 获取玩家当前房间和游戏
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room:
            await use_adrenaline_cmd.finish("⛔ 你不在任何游戏房间中")

        game = await RussianRouletteService.get_game_by_room_id(session, room.room_id)
        if not game:
            await use_adrenaline_cmd.finish("⛔ 游戏尚未开始")

        # 检查是否轮到该玩家
        if game.current_player_id != player.id:
            await use_adrenaline_cmd.finish("⛔ 还没轮到你行动")

        # 如果玩家已经重新获得行动权，清除手铐冷却状态
        if getattr(game, "handcuffs_cooldown_player_id", None) == player.id and game.handcuffed_player_id != player.id:
            game.handcuffs_cooldown_player_id = None

        # 检查是否被手铐限制
        if game.handcuffed_player_id == player.id:
            # 解除手铐限制
            game.handcuffed_player_id = None
            # 切换回使用手铐的玩家（对手）
            opponent_id = room.get_opponent_id(player.id)
            game.current_player_id = opponent_id
            await session.commit()

            # 获取对手信息
            opponent = await session.get(Player, opponent_id)
            await use_adrenaline_cmd.finish(message_add_head(f"⛓️ 你被手铐限制，跳过本回合\n🔄 轮到 {opponent.nickname} 继续行动", event))



        # 构建游戏状态
        game_state = {
            "bullets": game.bullets,
            "current_bullet_index": game.current_bullet_index,
            f"{room.player1_id}_hp": game.player1_hp,
            f"{room.player2_id}_hp": game.player2_hp,
            "is_sawed_off": game.is_sawed_off,
            "handcuffed_player_id": game.handcuffed_player_id,
            f"{room.player1_id}_items": game.player1_items,
            f"{room.player2_id}_items": game.player2_items,
            "magnifier_info": game.magnifier_info,
            "phone_info": game.phone_info,
            "handcuffs_skip_turn": getattr(game, 'handcuffs_skip_turn', False),
            "handcuffs_cooldown_player_id": getattr(game, "handcuffs_cooldown_player_id", None)
        }

        # 使用肾上腺素偷取指定道具
        opponent_id = room.get_opponent_id(player.id)
        success, result_msg = RussianRouletteCore.use_adrenaline(game_state, player.id, opponent_id, target_item_type, room.max_hp)

        if not success:
            await use_adrenaline_cmd.finish(message_add_head(f"❌ {result_msg}", event))

        # 更新游戏状态（偷到的道具可能会改变游戏状态）
        game.bullets = game_state["bullets"]
        game.current_bullet_index = game_state["current_bullet_index"]
        game.player1_hp = game_state[f"{room.player1_id}_hp"]
        game.player2_hp = game_state[f"{room.player2_id}_hp"]
        game.is_sawed_off = game_state["is_sawed_off"]
        game.handcuffed_player_id = game_state.get("handcuffed_player_id")
        game.player1_items = game_state[f"{room.player1_id}_items"]
        game.player2_items = game_state[f"{room.player2_id}_items"]
        game.magnifier_info = game_state.get("magnifier_info")
        game.phone_info = game_state.get("phone_info")
        game.handcuffs_cooldown_player_id = game_state.get("handcuffs_cooldown_player_id")

        # 检查使用肾上腺素后是否有玩家血量降为0（游戏结束）
        game_over = False
        winner_id = None
        if game.player1_hp <= 0:
            game_over = True
            winner_id = room.player2_id
        elif game.player2_hp <= 0:
            game_over = True
            winner_id = room.player1_id

        # 如果游戏未结束，检查是否需要重新装弹（偷到的道具可能会影响弹药）
        reloaded = False
        reload_msg = ""
        if not game_over:
            reloaded, reload_msg = RussianRouletteCore.check_and_reload(
                game_state, room.player1_id, room.player2_id
            )
            if reloaded:
                # 更新重新装弹后的游戏状态
                game.bullets = game_state["bullets"]
                game.current_bullet_index = game_state["current_bullet_index"]
                game.player1_items = game_state[f"{room.player1_id}_items"]
                game.player2_items = game_state[f"{room.player2_id}_items"]
                game.is_sawed_off = game_state["is_sawed_off"]
                game.handcuffed_player_id = game_state.get("handcuffed_player_id")
                game.magnifier_info = game_state.get("magnifier_info")
                game.phone_info = game_state.get("phone_info")
                game.handcuffs_cooldown_player_id = game_state.get("handcuffs_cooldown_player_id")

        await session.commit()

        # 构建基础消息
        final_msg = f"🎒 {player.nickname} 使用了肾上腺素\n{result_msg}"
        if reload_msg:
            final_msg += f"\n{reload_msg}"

        # 如果游戏结束，处理胜负
        if game_over:
            winner = await session.get(Player, winner_id)
            _, reward_msg = await RussianRouletteService.finish_game(
                session, room.room_id, winner_id
            )
            final_msg += f"\n🏆 {winner.nickname} 获胜！\n{reward_msg}"

        # 如果重新装弹了且游戏未结束，需要分别发送道具信息
        if reloaded and not game_over:
            # 先发送基础消息
            await bot.send(event, message_add_head(final_msg, event))

            # 延迟一下，然后分两次发送道具信息
            import asyncio
            await asyncio.sleep(1)

            # 获取玩家信息用于显示
            player1 = await session.get(Player, room.player1_id)
            player2 = await session.get(Player, room.player2_id)

            # 发送玩家1的道具
            player1_items_msg = _format_player_items(game.player1_items, player1.nickname)
            await bot.send(event, message_add_head(player1_items_msg, event))

            await asyncio.sleep(1)

            # 发送玩家2的道具
            player2_items_msg = _format_player_items(game.player2_items, player2.nickname)
            await bot.send(event, message_add_head(player2_items_msg, event))

            return  # 使用return而不是finish，因为已经发送了消息
        else:
            # 没有重新装弹或游戏已结束，正常发送消息
            await use_adrenaline_cmd.finish(message_add_head(final_msg, event))


@use_item_cmd.handle()
async def handle_use_item(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """处理使用道具指令"""
    # 检查是否为群聊
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await use_item_cmd.finish("⛔ 游戏指令只能在群聊中使用")

    item_name = args.extract_plain_text().strip()
    if not item_name:
        await use_item_cmd.finish("⛔ 请指定道具名称，如：使用道具 小刀")

    # 道具名称映射
    item_mapping = {
        "小刀": ItemType.KNIFE,
        "手铐": ItemType.HANDCUFFS,
        "香烟": ItemType.CIGARETTE,
        "放大镜": ItemType.MAGNIFIER,
        "啤酒": ItemType.BEER,
        "肾上腺素": ItemType.ADRENALINE,
        "过期药物": ItemType.EXPIRED_MEDICINE,
        "逆转器": ItemType.INVERTER,
        "电话": ItemType.PHONE,
        "骰子": ItemType.DICE
    }

    if item_name not in item_mapping:
        available_items = "、".join(item_mapping.keys())
        await use_item_cmd.finish(f"⛔ 未知道具。可用道具：{available_items}")

    item_type = item_mapping[item_name]

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await use_item_cmd.finish("⛔ 请先创建角色")

        # 获取玩家当前房间和游戏
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room:
            await use_item_cmd.finish("⛔ 你不在任何游戏房间中")

        game = await RussianRouletteService.get_game_by_room_id(session, room.room_id)
        if not game:
            await use_item_cmd.finish("⛔ 游戏尚未开始")

        # 检查是否轮到该玩家
        if game.current_player_id != player.id:
            await use_item_cmd.finish("⛔ 还没轮到你行动")

        # 如果玩家已经重新获得行动权，清除手铐冷却状态
        if getattr(game, "handcuffs_cooldown_player_id", None) == player.id and game.handcuffed_player_id != player.id:
            game.handcuffs_cooldown_player_id = None

        # 检查是否被手铐限制
        if game.handcuffed_player_id == player.id:
            # 解除手铐限制
            game.handcuffed_player_id = None
            # 切换回使用手铐的玩家（对手）
            opponent_id = room.get_opponent_id(player.id)
            game.current_player_id = opponent_id
            await session.commit()

            # 获取对手信息
            opponent = await session.get(Player, opponent_id)
            await use_item_cmd.finish(message_add_head(f"⛓️ 你被手铐限制，跳过本回合\n🔄 轮到 {opponent.nickname} 继续行动", event))

        # 检查玩家是否有该道具
        if room.player1_id == player.id:
            player_items = json.loads(game.player1_items or "[]")
        else:
            player_items = json.loads(game.player2_items or "[]")

        if item_type.value not in player_items:
            await use_item_cmd.finish(f"⛔ 你没有{item_name}")

        opponent_id = room.get_opponent_id(player.id)
        if item_type == ItemType.HANDCUFFS:
            if game.handcuffed_player_id == opponent_id:
                await use_item_cmd.finish(message_add_head("⛔ 对手已被手铐限制，等待其行动一次后再使用", event))
            cooldown_target = getattr(game, "handcuffs_cooldown_player_id", None)
            if cooldown_target == opponent_id:
                await use_item_cmd.finish(message_add_head("⛔ 对手刚刚被手铐限制，需其行动一次后才能再次使用", event))

        # 构建游戏状态
        game_state = {
            "bullets": game.bullets,
            "current_bullet_index": game.current_bullet_index,
            f"{room.player1_id}_hp": game.player1_hp,
            f"{room.player2_id}_hp": game.player2_hp,
            "is_sawed_off": game.is_sawed_off,
            "handcuffed_player_id": game.handcuffed_player_id,
            f"{room.player1_id}_items": game.player1_items,
            f"{room.player2_id}_items": game.player2_items,
            "magnifier_info": game.magnifier_info,
            "phone_info": game.phone_info,
            "handcuffs_skip_turn": getattr(game, 'handcuffs_skip_turn', False),
            "handcuffs_cooldown_player_id": getattr(game, "handcuffs_cooldown_player_id", None)
        }

        # 使用道具
        success = False
        result_msg = ""

        if item_type == ItemType.KNIFE:
            success, result_msg = RussianRouletteCore.use_knife(game_state)
        elif item_type == ItemType.HANDCUFFS:
            success, result_msg = RussianRouletteCore.use_handcuffs(game_state, opponent_id)
            # 使用手铐后，设置特殊标记，表示下次回合切换时应该跳过对手
            if success:
                game_state["handcuffs_used_by"] = player.id
        elif item_type == ItemType.CIGARETTE:
            success, result_msg = RussianRouletteCore.use_cigarette(game_state, player.id, room.max_hp)
        elif item_type == ItemType.MAGNIFIER:
            success, result_msg = RussianRouletteCore.use_magnifier(game_state, player.id)
        elif item_type == ItemType.BEER:
            success, result_msg = RussianRouletteCore.use_beer(game_state)
        elif item_type == ItemType.ADRENALINE:
            # 肾上腺素需要指定偷取的道具，这里提示用户使用正确格式
            await use_item_cmd.finish(message_add_head("⛔ 肾上腺素需要指定偷取的道具\n📝 使用格式：使用道具 肾上腺素 [道具名]\n📝 示例：使用道具 肾上腺素 小刀", event))
        elif item_type == ItemType.EXPIRED_MEDICINE:
            success, result_msg = RussianRouletteCore.use_expired_medicine(game_state, player.id, room.max_hp)
        elif item_type == ItemType.INVERTER:
            success, result_msg = RussianRouletteCore.use_inverter(game_state)
        elif item_type == ItemType.PHONE:
            success, result_msg = RussianRouletteCore.use_phone(game_state, player.id)
        elif item_type == ItemType.DICE:
            success, result_msg = RussianRouletteCore.use_dice(game_state)

        if not success:
            await use_item_cmd.finish(message_add_head(f"❌ {result_msg}", event))

        # 消耗道具
        player_items.remove(item_type.value)
        if room.player1_id == player.id:
            game.player1_items = json.dumps(player_items)
        else:
            game.player2_items = json.dumps(player_items)

        # 更新游戏状态
        game.bullets = game_state["bullets"]
        game.current_bullet_index = game_state["current_bullet_index"]
        game.player1_hp = game_state[f"{room.player1_id}_hp"]
        game.player2_hp = game_state[f"{room.player2_id}_hp"]
        game.is_sawed_off = game_state["is_sawed_off"]
        game.handcuffed_player_id = game_state.get("handcuffed_player_id")
        game.handcuffs_cooldown_player_id = game_state.get("handcuffs_cooldown_player_id")
        game.magnifier_info = game_state.get("magnifier_info")
        game.phone_info = game_state.get("phone_info")

        # 检查使用道具后是否有玩家血量降为0（游戏结束）
        game_over = False
        winner_id = None
        if game.player1_hp <= 0:
            game_over = True
            winner_id = room.player2_id
        elif game.player2_hp <= 0:
            game_over = True
            winner_id = room.player1_id

        # 如果游戏未结束，检查是否需要重新装弹
        reloaded = False
        reload_msg = ""
        if not game_over:
            reloaded, reload_msg = RussianRouletteCore.check_and_reload(
                game_state, room.player1_id, room.player2_id
            )
            if reloaded:
                # 更新重新装弹后的游戏状态
                game.bullets = game_state["bullets"]
                game.current_bullet_index = game_state["current_bullet_index"]
                game.player1_items = game_state[f"{room.player1_id}_items"]
                game.player2_items = game_state[f"{room.player2_id}_items"]
                game.is_sawed_off = game_state["is_sawed_off"]
                game.handcuffed_player_id = game_state.get("handcuffed_player_id")
                game.handcuffs_cooldown_player_id = game_state.get("handcuffs_cooldown_player_id")
                game.magnifier_info = game_state.get("magnifier_info")
                game.phone_info = game_state.get("phone_info")

        await session.commit()

        # 构建基础消息
        final_msg = f"🎒 {player.nickname} 使用了{item_name}\n{result_msg}"
        if reload_msg:
            final_msg += f"\n{reload_msg}"

        # 如果游戏结束，处理胜负
        if game_over:
            winner = await session.get(Player, winner_id)
            _, reward_msg = await RussianRouletteService.finish_game(
                session, room.room_id, winner_id
            )
            final_msg += f"\n🏆 {winner.nickname} 获胜！\n{reward_msg}"
        elif item_type == ItemType.HANDCUFFS and success:
            # 如果使用了手铐且游戏未结束，添加连续行动提示
            final_msg += f"\n🔄 {player.nickname} 可以继续行动"

        # 如果重新装弹了且游戏未结束，需要分别发送道具信息
        if reloaded and not game_over:
            # 先发送基础消息
            await bot.send(event, message_add_head(final_msg, event))

            # 延迟一下，然后分两次发送道具信息
            import asyncio
            await asyncio.sleep(1)

            # 获取玩家信息用于显示
            player1 = await session.get(Player, room.player1_id)
            player2 = await session.get(Player, room.player2_id)

            # 发送玩家1的道具
            player1_items_msg = _format_player_items(game.player1_items, player1.nickname)
            await bot.send(event, message_add_head(player1_items_msg, event))

            await asyncio.sleep(1)

            # 发送玩家2的道具
            player2_items_msg = _format_player_items(game.player2_items, player2.nickname)
            await bot.send(event, message_add_head(player2_items_msg, event))

            return  # 使用return而不是finish，因为已经发送了消息
        else:
            # 没有重新装弹或游戏已结束，正常发送消息
            await use_item_cmd.finish(message_add_head(final_msg, event))


# 查看预知结果（私聊指令）
check_prediction_cmd = on_command("查看预知", aliases={"预知结果", "预知"}, block=True, priority=5)

@check_prediction_cmd.handle()
async def handle_check_prediction(event: MessageEvent):
    """处理查看预知结果指令（私聊）"""
    # 检查是否为私聊
    session_id = event.get_session_id()
    if not session_id.startswith("friend_"):
        await check_prediction_cmd.finish("⛔ 预知结果只能私聊查看")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await check_prediction_cmd.finish("⛔ 请先创建角色")

        # 获取玩家当前房间和游戏
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room:
            await check_prediction_cmd.finish("⛔ 你不在任何游戏房间中")

        game = await RussianRouletteService.get_game_by_room_id(session, room.room_id)
        if not game:
            await check_prediction_cmd.finish("⛔ 游戏尚未开始")

        result_msgs = []

        # 检查放大镜结果
        if game.magnifier_info:
            magnifier_data = json.loads(game.magnifier_info)
            if magnifier_data.get("player_id") == player.id:
                bullet_type = magnifier_data["bullet_type"]
                result_msgs.append(f"🔍 放大镜结果：当前弹药是{bullet_type}")

        # 检查电话结果
        if game.phone_info:
            phone_data = json.loads(game.phone_info)
            if phone_data.get("player_id") == player.id:
                position = phone_data["bullet_position"]
                bullet_type = phone_data["bullet_type"]
                result_msgs.append(f"📞 电话结果：第{position}发弹药是{bullet_type}")

        if not result_msgs:
            await check_prediction_cmd.finish("⛔ 暂无预知结果")

        final_msg = "🔮 预知结果\n━━━━━━━━━━━━━\n" + "\n".join(result_msgs)
        await check_prediction_cmd.finish(final_msg)


# 查看房间状态
room_status_cmd = on_command("房间状态", aliases={"轮盘状态"}, block=True, priority=5)

@room_status_cmd.handle()
async def handle_room_status(event: MessageEvent):
    """查看当前房间状态"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await room_status_cmd.finish("⛔ 请先创建角色")

        # 获取玩家当前房间
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room:
            await room_status_cmd.finish("⛔ 你不在任何游戏房间中")

        # 获取玩家信息
        player1 = await session.get(Player, room.player1_id)
        player2 = await session.get(Player, room.player2_id) if room.player2_id else None

        status_lines = [
            f"🏠 房间状态 - {room.room_id}",
            "━━━━━━━━━━━━━",
            f"📍 状态：{room.status}",
            f"👤 玩家1：{player1.nickname}[UID:{player1.uid}]"
        ]

        if player2:
            status_lines.append(f"👤 玩家2：{player2.nickname}[UID:{player2.uid}]")
        else:
            status_lines.append("👤 玩家2：等待加入...")

        # 显示筹码信息
        if room.status in ["betting", "playing", "finished"]:
            status_lines.extend([
                "━━━━━━━━━━━━━",
                "💰 筹码设置："
            ])

            # 玩家1筹码
            p1_bet_info = f"💎 {room.player1_gold_bet}金币"
            status_lines.append(f"  {player1.nickname}: {p1_bet_info}")

            # 玩家2筹码
            if player2:
                p2_bet_info = f"💎 {room.player2_gold_bet}金币"
                status_lines.append(f"  {player2.nickname}: {p2_bet_info}")

            # 显示奖池和税收信息
            if room.player1_gold_bet > 0 and room.player2_gold_bet > 0:
                total_pool = room.player1_gold_bet + room.player2_gold_bet
                tax_amount = int(total_pool * 0.03)
                final_reward = total_pool - tax_amount
                status_lines.extend([
                    f"💰 奖池总额：{total_pool}金币",
                    f"💸 系统税收：{tax_amount}金币 (3%)",
                    f"🏆 获胜奖励：{final_reward}金币"
                ])

        # 显示游戏状态
        if room.status == "playing":
            game = await RussianRouletteService.get_game_by_room_id(session, room.room_id)
            if game:
                status_lines.extend([
                    "━━━━━━━━━━━━━",
                    "🎮 游戏状态：",
                    f"❤️ {player1.nickname}: {'❤️' * game.player1_hp}{'🖤' * (room.max_hp - game.player1_hp)}",
                    f"❤️ {player2.nickname}: {'❤️' * game.player2_hp}{'🖤' * (room.max_hp - game.player2_hp)}"
                ])

                # 显示当前回合
                current_player = await session.get(Player, game.current_player_id)
                status_lines.append(f"🎯 当前回合：{current_player.nickname}")

                # 显示剩余弹药（不显示具体实弹和空包弹数量，防止逆转器漏洞）
                bullets = json.loads(game.bullets)
                remaining = bullets[game.current_bullet_index:]
                total_remaining = len(remaining)
                status_lines.append(f"🔫 剩余弹药：{total_remaining}发")

                # 显示已打出子弹统计
                fired_bullets = bullets[:game.current_bullet_index]
                if fired_bullets:  # 只有在有已打出子弹时才显示
                    fired_live_count = sum(1 for b in fired_bullets if b)
                    fired_blank_count = sum(1 for b in fired_bullets if not b)
                    status_lines.append(f"📊 已打出：{fired_live_count}发实弹 + {fired_blank_count}发空包弹")

        await room_status_cmd.finish(message_add_head("\n".join(status_lines), event))


# 退出房间
leave_room_cmd = on_command("退出房间", aliases={"离开房间"}, block=True, priority=5)

@leave_room_cmd.handle()
async def handle_leave_room(event: MessageEvent):
    """退出当前房间"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await leave_room_cmd.finish("⛔ 请先创建角色")

        # 获取玩家当前房间
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room:
            await leave_room_cmd.finish("⛔ 你不在任何游戏房间中")

        # 检查房间状态
        if room.status not in {RoomStatus.WAITING.value, RoomStatus.BETTING.value}:
            await leave_room_cmd.finish("⛔ 只有在游戏开始前才能退出房间")

        # 退出房间逻辑
        if room.player1_id == player.id:
            if room.player2_id:
                # 房主退出，转移房主权限给玩家2
                room.creator_id = room.player2_id
                room.player1_id = room.player2_id
                room.player2_id = None
                room.player1_gold_bet = room.player2_gold_bet
                room.player1_items_bet = room.player2_items_bet
                room.player2_gold_bet = 0
                room.player2_items_bet = None
                room.status = RoomStatus.WAITING.value

                # 返还筹码给原房主（只返还金币）
                if room.player1_gold_bet > 0:
                    player.gold += room.player1_gold_bet

                await session.commit()
                await leave_room_cmd.finish(message_add_head("✅ 已退出房间，房主权限已转移", event))
            else:
                # 房间只有房主，直接删除房间
                await session.delete(room)
                await session.commit()
                await leave_room_cmd.finish(message_add_head("✅ 已退出并删除房间", event))

        elif room.player2_id == player.id:
            # 玩家2退出
            # 返还筹码（只返还金币）
            if room.player2_gold_bet > 0:
                player.gold += room.player2_gold_bet

            room.player2_id = None
            room.player2_gold_bet = 0
            room.player2_items_bet = None
            room.status = RoomStatus.WAITING.value

            await session.commit()
            await leave_room_cmd.finish(message_add_head("✅ 已退出房间", event))


# 查看道具列表
view_items_cmd = on_command("查看道具", aliases={"道具列表", "我的道具"}, block=True, priority=5)

@view_items_cmd.handle()
async def handle_view_items(event: MessageEvent):
    """查看当前游戏中的道具"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await view_items_cmd.finish("⛔ 请先创建角色")

        # 获取玩家当前房间和游戏
        room = await RussianRouletteService.get_player_active_room(session, player.id)
        if not room or room.status != "playing":
            await view_items_cmd.finish("⛔ 你不在进行中的游戏中")

        game = await RussianRouletteService.get_game_by_room_id(session, room.room_id)
        if not game:
            await view_items_cmd.finish("⛔ 游戏状态异常")

        # 获取玩家道具
        if room.player1_id == player.id:
            player_items = json.loads(game.player1_items or "[]")
        else:
            player_items = json.loads(game.player2_items or "[]")

        if not player_items:
            await view_items_cmd.finish(message_add_head("🎒 你没有任何道具", event))

        # 构建道具列表
        item_lines = ["🎒 你的道具", "━━━━━━━━━━━━━"]

        # 统计道具数量
        from collections import Counter
        item_counts = Counter(player_items)

        for item_str, count in item_counts.items():
            try:
                item_type = ItemType(item_str)
                item_config = RussianRouletteCore.ITEM_CONFIGS[item_type]
                item_lines.append(f"{item_config['name']} x{count}")
                item_lines.append(f"  └ {item_config['description']}")
            except (ValueError, KeyError):
                item_lines.append(f"❓ 未知道具: {item_str} x{count}")

        item_lines.append("━━━━━━━━━━━━━")
        item_lines.append("📝 使用：使用道具 [道具名]")

        await view_items_cmd.finish(message_add_head("\n".join(item_lines), event))


# 手动清理房间（管理员指令）
cleanup_rooms_cmd = on_command("清理轮盘房间", block=True, priority=5, permission=SUPERUSER)

@cleanup_rooms_cmd.handle()
async def handle_cleanup_rooms(_event: MessageEvent):
    """手动清理无活动的俄罗斯轮盘房间"""
    try:
        await RussianRouletteCleanup.cleanup_inactive_rooms()
        await cleanup_rooms_cmd.finish("✅ 俄罗斯轮盘房间清理完成")
    except Exception as e:
        await cleanup_rooms_cmd.finish(f"❌ 清理失败: {str(e)}")
