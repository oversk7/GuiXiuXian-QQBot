"""
恶魔轮盘赌游戏主模块
"""
import json
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from ..models.russian_roulette import RoomStatus
from ..models.inventory import ItemInstance
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .russian_roulette_service import RussianRouletteService
from .russian_roulette_core import RussianRouletteCore, ItemType
from .russian_roulette_cleanup import RussianRouletteCleanup


# ==================== 房间管理指令 ====================

# 创建房间
create_room_cmd = on_command("恶魔轮盘", aliases={"轮盘赌", "俄罗斯轮盘"}, block=True, priority=5)

@create_room_cmd.handle()
async def handle_create_room(event: MessageEvent, args: Message = CommandArg()):
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
            "▫️ 【恶魔轮盘 筹码 金币数 [道具ID]】 - 设置筹码\n"
            "▫️ 【恶魔轮盘 开始】 - 开始游戏\n"
            "━━━━━━━━━━━━━\n"
            "🎲 游戏指令：\n"
            "▫️ 【开枪 <自己/对手>】 - 选择射击目标\n"
            "▫️ 【使用道具 <道具名>】 - 使用道具\n"
            "▫️ 【预知】 - 私聊指令，查看预知结果\n"
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
                    f"📝 使用：恶魔轮盘 筹码 [金币数] [道具ID]"
                )
                await create_room_cmd.finish(message_add_head(result_msg, event))
            else:
                await create_room_cmd.finish(message_add_head(f"❌ {msg}", event))
        
        elif args_text.startswith("筹码 "):
            parts = args_text[3:].strip().split()
            if not parts:
                await create_room_cmd.finish("⛔ 格式：恶魔轮盘 筹码 [金币数] [道具ID1] [道具ID2]...")
            
            try:
                gold = int(parts[0])
                items = parts[1:] if len(parts) > 1 else []
            except ValueError:
                await create_room_cmd.finish("⛔ 金币数必须为数字")
            
            # 获取玩家当前房间
            room = await RussianRouletteService.get_player_active_room(session, player.id)
            if not room:
                await create_room_cmd.finish("⛔ 你不在任何房间中")
            
            success, msg = await RussianRouletteService.set_bet(
                session, player.id, room.room_id, gold, items
            )
            
            if success:
                result_msg = (
                    f"💰 筹码设置成功！\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💎 金币：{gold}\n"
                )
                if items:
                    result_msg += f"🎒 道具：{', '.join(items)}\n"
                result_msg += (
                    f"━━━━━━━━━━━━━\n"
                    f"⏳ 等待对手设置筹码...\n"
                    f"📝 双方设置完成后使用：恶魔轮盘 开始"
                )
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
                await create_room_cmd.finish(message_add_head(result_msg, event))
            else:
                await create_room_cmd.finish(message_add_head(f"❌ {msg}", event))
        
        else:
            await create_room_cmd.finish("⛔ 未知指令，使用 '恶魔轮盘 帮助' 查看帮助")


# ==================== 游戏操作指令 ====================

# 开枪指令
shoot_cmd = on_command("开枪", block=True, priority=5)

@shoot_cmd.handle()
async def handle_shoot(event: MessageEvent, args: Message = CommandArg()):
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
        
        # 检查是否被手铐限制
        if game.handcuffed_player_id == player.id:
            # 解除手铐限制
            game.handcuffed_player_id = None
            # 切换到对手回合
            opponent_id = room.get_opponent_id(player.id)
            game.current_player_id = opponent_id
            await session.commit()
            
            await shoot_cmd.finish(message_add_head("⛓️ 你被手铐限制，跳过本回合", event))
        
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
            "handcuffed_player_id": game.handcuffed_player_id
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
                game.current_player_id = opponent_id
                opponent = await session.get(Player, opponent_id)
                result_msg += f"\n🔄 轮到 {opponent.nickname} 行动\n\n{game_display}"
                # 添加推荐指令
                recommended = RussianRouletteCore.get_recommended_commands(display_game_state, opponent_id)
                result_msg += f"\n{recommended}"
        
        await session.commit()
        await shoot_cmd.finish(message_add_head(result_msg, event))


# 使用道具指令
use_item_cmd = on_command("使用道具", aliases={"道具"}, block=True, priority=5)

@use_item_cmd.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
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
        "饮料": ItemType.BEER,
        "肾上腺素": ItemType.ADRENALINE,
        "过期药物": ItemType.EXPIRED_MEDICINE,
        "逆转器": ItemType.INVERTER,
        "电话": ItemType.PHONE
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

        # 检查玩家是否有该道具
        if room.player1_id == player.id:
            player_items = json.loads(game.player1_items or "[]")
        else:
            player_items = json.loads(game.player2_items or "[]")

        if item_type.value not in player_items:
            await use_item_cmd.finish(f"⛔ 你没有{item_name}")

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
            "phone_info": game.phone_info
        }

        # 使用道具
        success = False
        result_msg = ""

        if item_type == ItemType.KNIFE:
            success, result_msg = RussianRouletteCore.use_knife(game_state)
        elif item_type == ItemType.HANDCUFFS:
            opponent_id = room.get_opponent_id(player.id)
            success, result_msg = RussianRouletteCore.use_handcuffs(game_state, opponent_id)
        elif item_type == ItemType.CIGARETTE:
            success, result_msg = RussianRouletteCore.use_cigarette(game_state, player.id, room.max_hp)
        elif item_type == ItemType.MAGNIFIER:
            success, result_msg = RussianRouletteCore.use_magnifier(game_state, player.id)
        elif item_type == ItemType.BEER:
            success, result_msg = RussianRouletteCore.use_beer(game_state)
        elif item_type == ItemType.ADRENALINE:
            # 肾上腺素需要额外参数，这里简化处理 - 随机偷取对手一个道具
            opponent_id = room.get_opponent_id(player.id)
            opponent_items = json.loads(game.player2_items if room.player1_id == player.id else game.player1_items or "[]")

            if not opponent_items:
                await use_item_cmd.finish(message_add_head("⛔ 对手没有道具可以偷取", event))

            # 随机选择一个道具偷取
            import random
            stolen_item_str = random.choice(opponent_items)
            stolen_item = ItemType(stolen_item_str)

            success, result_msg = RussianRouletteCore.use_adrenaline(game_state, player.id, opponent_id, stolen_item)
        elif item_type == ItemType.EXPIRED_MEDICINE:
            success, result_msg = RussianRouletteCore.use_expired_medicine(game_state, player.id, room.max_hp)
        elif item_type == ItemType.INVERTER:
            success, result_msg = RussianRouletteCore.use_inverter(game_state)
        elif item_type == ItemType.PHONE:
            success, result_msg = RussianRouletteCore.use_phone(game_state, player.id)

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
        game.magnifier_info = game_state.get("magnifier_info")
        game.phone_info = game_state.get("phone_info")

        # 检查是否需要重新装弹
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

        await session.commit()

        # 使用道具后只显示简单的结果信息，不显示完整游戏状态避免刷屏
        final_msg = f"🎒 {player.nickname} 使用了{item_name}\n{result_msg}"
        if reload_msg:
            final_msg += f"\n{reload_msg}"
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
            p1_items = json.loads(room.player1_items_bet) if room.player1_items_bet else []
            p1_bet_info = f"💎 {room.player1_gold_bet}金币"
            if p1_items:
                p1_bet_info += f" + {len(p1_items)}个道具"
            status_lines.append(f"  {player1.nickname}: {p1_bet_info}")

            # 玩家2筹码
            if player2:
                p2_items = json.loads(room.player2_items_bet) if room.player2_items_bet else []
                p2_bet_info = f"💎 {room.player2_gold_bet}金币"
                if p2_items:
                    p2_bet_info += f" + {len(p2_items)}个道具"
                status_lines.append(f"  {player2.nickname}: {p2_bet_info}")

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
        if room.status == "playing":
            await leave_room_cmd.finish("⛔ 游戏进行中无法退出房间")

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

                # 返还筹码给原房主
                if room.player1_gold_bet > 0:
                    player.gold += room.player1_gold_bet
                if room.player1_items_bet:
                    items = json.loads(room.player1_items_bet)
                    for item_id in items:
                        await ItemInstance.add_item(session, player.id, item_id, 1)

                await session.commit()
                await leave_room_cmd.finish(message_add_head("✅ 已退出房间，房主权限已转移", event))
            else:
                # 房间只有房主，直接删除房间
                await session.delete(room)
                await session.commit()
                await leave_room_cmd.finish(message_add_head("✅ 已退出并删除房间", event))

        elif room.player2_id == player.id:
            # 玩家2退出
            # 返还筹码
            if room.player2_gold_bet > 0:
                player.gold += room.player2_gold_bet
            if room.player2_items_bet:
                items = json.loads(room.player2_items_bet)
                for item_id in items:
                    await ItemInstance.add_item(session, player.id, item_id, 1)

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
cleanup_rooms_cmd = on_command("清理轮盘房间", block=True, priority=5)

@cleanup_rooms_cmd.handle()
async def handle_cleanup_rooms(event: MessageEvent):
    """手动清理无活动的俄罗斯轮盘房间"""
    user_id = event.get_user_id()

    # 简单的管理员检查（可以根据需要调整）
    admin_users = ["your_admin_qq_id"]  # 替换为实际的管理员QQ号
    if user_id not in admin_users:
        await cleanup_rooms_cmd.finish("⛔ 只有管理员可以使用此命令")

    try:
        await RussianRouletteCleanup.cleanup_inactive_rooms()
        await cleanup_rooms_cmd.finish("✅ 俄罗斯轮盘房间清理完成")
    except Exception as e:
        await cleanup_rooms_cmd.finish(f"❌ 清理失败: {str(e)}")
