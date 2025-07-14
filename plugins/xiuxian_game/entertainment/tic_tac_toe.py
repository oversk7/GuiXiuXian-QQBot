from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
import random

# 简单的游戏状态存储（实际项目中应该用数据库）
game_sessions = {}

# 井字棋功能
tic_tac_toe = on_command("井字棋", priority=5, block=True)

class TicTacToeGame:
    def __init__(self):
        # 棋盘状态：0=空，1=玩家(❌)，2=AI(⭕)
        self.board = [0] * 9
        self.player_symbol = "❌"
        self.ai_symbol = "⭕"
        self.empty_symbol = "⬜"
    
    def display_board(self) -> str:
        """显示棋盘"""
        symbols = []
        for i in range(9):
            if self.board[i] == 0:
                symbols.append(f"{i+1}️⃣")  # 显示位置编号
            elif self.board[i] == 1:
                symbols.append(self.player_symbol)
            else:
                symbols.append(self.ai_symbol)
        
        board_display = (
            f"┃  {symbols[0]}  ┃  {symbols[1]}  ┃  {symbols[2]}  ┃\n"
            "━━━━━━━━━━━━━\n"
            f"┃  {symbols[3]}  ┃  {symbols[4]}  ┃  {symbols[5]}  ┃\n"
            "━━━━━━━━━━━━━\n"
            f"┃  {symbols[6]}  ┃  {symbols[7]}  ┃  {symbols[8]}  ┃"
        )
        return board_display
    
    def make_move(self, position: int, player: int) -> bool:
        """下棋，position: 1-9，player: 1=玩家，2=AI"""
        if position < 1 or position > 9 or self.board[position-1] != 0:
            return False
        self.board[position-1] = player
        return True
    
    def check_winner(self) -> int:
        """检查胜负，返回：0=继续，1=玩家胜，2=AI胜，3=平局"""
        # 胜利条件
        win_patterns = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # 横
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # 竖
            [0, 4, 8], [2, 4, 6]              # 斜
        ]
        
        for pattern in win_patterns:
            if (self.board[pattern[0]] == self.board[pattern[1]] == 
                self.board[pattern[2]] != 0):
                return self.board[pattern[0]]
        
        # 检查平局
        if 0 not in self.board:
            return 3
        
        return 0
    
    def ai_move(self) -> int:
        """AI下棋，返回选择的位置(1-9)"""
        # 简单AI策略：
        # 1. 如果能获胜，直接获胜
        # 2. 如果玩家下一步能获胜，阻止
        # 3. 优先选择中心
        # 4. 随机选择
        
        # 检查AI是否能获胜
        for i in range(9):
            if self.board[i] == 0:
                self.board[i] = 2
                if self.check_winner() == 2:
                    self.board[i] = 0
                    return i + 1
                self.board[i] = 0
        
        # 检查是否需要阻止玩家获胜
        for i in range(9):
            if self.board[i] == 0:
                self.board[i] = 1
                if self.check_winner() == 1:
                    self.board[i] = 0
                    return i + 1
                self.board[i] = 0
        
        # 优先选择中心
        if self.board[4] == 0:
            return 5
        
        # 选择角落
        corners = [0, 2, 6, 8]
        available_corners = [i for i in corners if self.board[i] == 0]
        if available_corners:
            return random.choice(available_corners) + 1
        
        # 随机选择剩余位置
        available = [i for i in range(9) if self.board[i] == 0]
        return random.choice(available) + 1

@tic_tac_toe.handle()
async def handle_tic_tac_toe(event: MessageEvent, args: Message = CommandArg()):
    """处理井字棋游戏"""
    async with safe_session() as session:
        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await tic_tac_toe.finish("⛔ 请先创建角色")

        args_text = args.extract_plain_text().strip()
        
        # 如果没有参数，显示游戏说明
        if not args_text:
            help_msg = (
                "🎮 井字棋游戏\n"
                "━━━━━━━━━━━━━\n"
                "🎯 游戏规则：\n"
                "▫️ 你是 ❌，AI是 ⭕\n"
                "▫️ 三个相同符号连成一线即获胜\n"
                "▫️ 胜利奖励100~300💰，失败扣除50💰\n"
                "▫️ 平局不扣除金币\n"
                "━━━━━━━━━━━━━\n"
                "📝 使用方法：\n"
                "▫️ 井字棋 开始 - 开始新游戏\n"
                "▫️ 井字棋 [1-9] - 选择位置下棋\n"
                "▫️ 井字棋 放弃 - 放弃当前游戏\n"
                "━━━━━━━━━━━━━\n"
                "💡 位置编号参考：\n"
                "┃  1️⃣  ┃  2️⃣  ┃  3️⃣  ┃\n"
                "┃  4️⃣  ┃  5️⃣  ┃  6️⃣  ┃\n"
                "┃  7️⃣  ┃  8️⃣  ┃  9️⃣  ┃\n"
                "━━━━━━━━━━━━━\n"
            )
            await tic_tac_toe.finish(message_add_head(help_msg, event))
        
        # 检查金币（失败时需要扣除50金币）
        if player.gold < 50:
            await tic_tac_toe.finish("❌ 金币不足！需要至少50💰才能开始游戏")

        user_id = event.get_user_id()

        # 开始新游戏
        if args_text == "开始":
            game = TicTacToeGame()
            game_sessions[user_id] = game

            result_msg = (
                "🎮 井字棋游戏开始！\n"
                "━━━━━━━━━━━━━\n"
                f"{game.display_board()}\n"
                "━━━━━━━━━━━━━\n"
                "💡 你是 ❌，请选择位置 1-9\n"
                "📝 使用：井字棋 [数字] 下棋"
            )
            await tic_tac_toe.finish(message_add_head(result_msg, event))

        # 处理放弃游戏
        if args_text == "放弃":
            if user_id in game_sessions:
                del game_sessions[user_id]
                await tic_tac_toe.finish(message_add_head("🏳️ 已放弃当前游戏", event))
            else:
                await tic_tac_toe.finish(message_add_head("❌ 没有进行中的游戏", event))

        # 处理下棋
        try:
            position = int(args_text)
            if position < 1 or position > 9:
                raise ValueError
        except ValueError:
            await tic_tac_toe.finish("⚠️ 请输入 1-9 的数字选择位置")

        # 获取当前游戏状态
        if user_id not in game_sessions:
            await tic_tac_toe.finish("❌ 没有进行中的游戏，请先使用 '井字棋 开始' 开始新游戏")

        game = game_sessions[user_id]
        
        # 玩家下棋
        if not game.make_move(position, 1):
            await tic_tac_toe.finish("❌ 该位置已被占用，请选择其他位置")
        
        # 检查玩家是否获胜
        winner = game.check_winner()
        if winner == 1:
            gold_gain = random.randint(100, 300)
            player.gold += gold_gain
            session.add(player)
            await session.commit()

            # 清除游戏状态
            del game_sessions[user_id]

            result_msg = (
                "🎉 恭喜获胜！\n"
                "━━━━━━━━━━━━━\n"
                f"{game.display_board()}\n"
                "━━━━━━━━━━━━━\n"
                f"✨ 奖励：+{gold_gain}💰\n"
                f"💰 当前金币：{player.gold}"
            )
            await tic_tac_toe.finish(message_add_head(result_msg, event))
        
        if winner == 3:
            # 清除游戏状态
            del game_sessions[user_id]

            result_msg = (
                "🤝 平局！\n"
                "━━━━━━━━━━━━━\n"
                f"{game.display_board()}\n"
                "━━━━━━━━━━━━━\n"
                "💰 金币无变化"
            )
            await tic_tac_toe.finish(message_add_head(result_msg, event))
        
        # AI下棋
        ai_position = game.ai_move()
        game.make_move(ai_position, 2)
        
        # 检查AI是否获胜
        winner = game.check_winner()
        if winner == 2:
            player.gold -= 50
            session.add(player)
            await session.commit()

            # 清除游戏状态
            del game_sessions[user_id]

            result_msg = (
                "💔 AI获胜！\n"
                "━━━━━━━━━━━━━\n"
                f"{game.display_board()}\n"
                "━━━━━━━━━━━━━\n"
                f"💸 扣除：-50💰 (AI选择了位置{ai_position})\n"
                f"💰 当前金币：{player.gold}"
            )
            await tic_tac_toe.finish(message_add_head(result_msg, event))
        
        if winner == 3:
            # 清除游戏状态
            del game_sessions[user_id]

            result_msg = (
                "🤝 平局！\n"
                "━━━━━━━━━━━━━\n"
                f"{game.display_board()}\n"
                "━━━━━━━━━━━━━\n"
                f"🤖 AI选择了位置{ai_position}\n"
                "💰 金币无变化"
            )
            await tic_tac_toe.finish(message_add_head(result_msg, event))
        
        # 游戏继续
        result_msg = (
            "🎮 游戏继续\n"
            "━━━━━━━━━━━━━\n"
            f"{game.display_board()}\n"
            "━━━━━━━━━━━━━\n"
            f"🤖 AI选择了位置{ai_position}\n"
            "💡 轮到你了，请选择位置 1-9\n"
            "📝 使用：井字棋 [数字] 下棋"
        )
        await tic_tac_toe.finish(message_add_head(result_msg, event))
