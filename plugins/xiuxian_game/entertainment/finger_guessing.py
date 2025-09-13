from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
import random

# 猜拳功能
guess_fist = on_command("猜拳", priority=5, block=True)

@guess_fist.handle()
async def handle_fist_game(event: MessageEvent, args: Message = CommandArg()):
    """处理猜拳游戏"""
    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await guess_fist.finish("⛔ 请先创建角色")

        args_text = args.extract_plain_text().strip()
        parts = args_text.split()
        
        # 参数校验
        if len(parts) != 2:
            await guess_fist.finish("⚠️ 格式：/猜拳 [石头/剪刀/布] [金币数]\n例：猜拳 石头 100")
        
        player_choice, bet_str = parts
        if player_choice not in ["石头", "剪刀", "布"]:
            await guess_fist.finish("⚠️ 请选择：石头、剪刀 或 布")

        try:
            bet = int(bet_str)
            if bet < 1 or bet > 1000000:
                raise ValueError
        except ValueError:
            await guess_fist.finish("⚠️ 金币数必须为1-1000000之间的整数")

        # 金币检查
        if player.gold < bet:
            await guess_fist.finish(f"❌ 金币不足 | 需要 {bet}💰 当前 {player.gold}💰")
        
        # 生成对手选择
        opponent_choice = random.choice(["石头", "剪刀", "布"])
        
        # 判断胜负
        win_map = {"石头": "剪刀", "剪刀": "布", "布": "石头"}
        gold_change = 0
        if player_choice == opponent_choice:
            # 平局不扣金币
            result_msg = f"🤝 平局！双方都出了 {player_choice}"
            result_icon = "🔄"
            gold_change = 0
        elif win_map[player_choice] == opponent_choice:
            # 赢了得到赌注的两倍
            reward = bet
            player.gold += reward
            result_msg = f"🎉 胜利！{player_choice} 击败了 {opponent_choice}"
            result_icon = "✨"
            gold_change = reward
        else:
            # 输了赌注就没了
            player.gold -= bet
            result_msg = f"💔 失败！{opponent_choice} 击败了 {player_choice}"
            result_icon = "💸"
            gold_change = -bet
        
        session.add(player)

        await session.commit()
        
        # 格式化结果消息
        result_lines = [
            f"{result_icon} 猜拳结果",
            f"▫️ 你的选择：{player_choice}",
            f"▫️ 对手选择：{opponent_choice}",
            f"▫️ 结果：{result_msg}",
        ]
        
        # 添加金币变化信息
        if gold_change > 0:
            result_lines.append(f"💰 获得金币：+{gold_change}")
        elif gold_change < 0:
            result_lines.append(f"💰 损失金币：{gold_change}")
        else:
            result_lines.append(f"💰 金币无变化")
        
        result_lines.append(f"💰 当前金币：{player.gold}")

        result = "\n".join(result_lines)
        await guess_fist.finish(message_add_head(result, event)) 