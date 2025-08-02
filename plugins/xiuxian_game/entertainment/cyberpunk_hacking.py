from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
import random
from typing import List, Tuple, Dict
from dataclasses import dataclass

# 游戏状态存储
game_sessions: Dict[str, 'ArrayBreakingGame'] = {}

# 阵法破解游戏命令
array_breaking = on_command("阵法破解", aliases={"破阵", "阵法"}, priority=5, block=True)

@dataclass
class TargetSequence:
    """目标序列"""
    sequence: List[str]
    reward: int
    name: str

class ArrayBreakingGame:
    """天干地支阵法破解游戏"""
    
    def __init__(self, size: int = 5):
        self.size = size  # 矩阵大小
        self.matrix: List[List[str]] = []
        self.target_sequences: List[TargetSequence] = []
        self.buffer_size = 6  # 缓冲区大小
        self.current_path: List[Tuple[int, int]] = []  # 当前路径
        self.selected_codes: List[str] = []  # 已选择的代码
        self.is_horizontal = True  # 当前是否在水平方向选择
        self.completed_sequences: List[int] = []  # 已完成的序列索引
        self.game_cost = 100  # 游戏成本，默认100
        
        # 可用的天干地支符号
        self.code_chars = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸", "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        
        self._generate_solvable_puzzle()
    
    def _generate_solvable_puzzle(self):
        """生成有解的谜题（倒推生成）"""
        # 先生成目标序列
        self._generate_target_sequences()

        # 创建空矩阵
        self.matrix = [["" for _ in range(self.size)] for _ in range(self.size)]

        # 生成一条主要的解决路径，包含所有目标序列
        main_path = self._generate_main_solution_path()

        # 在主路径上放置代码
        if main_path:
            self._place_codes_on_path(main_path)

        # 填充剩余空位
        self._fill_remaining_cells()
    
    def _generate_target_sequences(self):
        """生成目标序列"""
        # 根据矩阵大小调整序列难度
        if self.size == 5:
            sequences = [
                (["甲", "子", "丙"], 120, "五行生克"),
                (["乙", "丑"], 60, "阴阳调和"),
                (["丁", "寅", "己"], 100, "天地人合"),
            ]
        else:  # 6x6
            sequences = [
                (["甲", "子", "丙", "午"], 150, "四象归位"),
                (["乙", "丑"], 60, "阴阳调和"),
                (["丁", "寅", "己", "申"], 180, "八卦演化"),
                (["庚", "辰"], 40, "金木相克"),
            ]

        self.target_sequences = []
        for seq, reward, name in sequences:
            self.target_sequences.append(TargetSequence(seq, reward, name))

    def _generate_main_solution_path(self) -> List[Tuple[int, int]]:
        """生成一条包含所有目标序列的主要解决路径"""
        # 将所有目标序列合并成一个长序列
        all_codes = []
        for target in self.target_sequences:
            all_codes.extend(target.sequence)

        # 去重但保持顺序
        seen = set()
        unique_codes = []
        for code in all_codes:
            if code not in seen:
                unique_codes.append(code)
                seen.add(code)

        # 确保路径长度不超过缓冲区
        if len(unique_codes) > self.buffer_size:
            unique_codes = unique_codes[:self.buffer_size]

        # 生成路径
        path = []
        current_row = 0  # 从第一行开始
        current_col = random.randint(0, self.size - 1)
        path.append((current_row, current_col))

        is_horizontal = True
        for _ in range(1, len(unique_codes)):
            if is_horizontal:
                # 水平移动：在同一行选择不同列
                available_cols = [c for c in range(self.size) if c != current_col]
                if available_cols:
                    current_col = random.choice(available_cols)
                    path.append((current_row, current_col))
            else:
                # 垂直移动：在同一列选择不同行
                available_rows = [r for r in range(self.size) if r != current_row]
                if available_rows:
                    current_row = random.choice(available_rows)
                    path.append((current_row, current_col))

            is_horizontal = not is_horizontal

        return path

    def _place_codes_on_path(self, path: List[Tuple[int, int]]):
        """在路径上放置代码，确保包含所有目标序列"""
        # 将所有目标序列合并
        all_codes = []
        for target in self.target_sequences:
            all_codes.extend(target.sequence)

        # 去重但保持顺序
        seen = set()
        unique_codes = []
        for code in all_codes:
            if code not in seen:
                unique_codes.append(code)
                seen.add(code)

        # 在路径上放置代码
        for i, (row, col) in enumerate(path):
            if i < len(unique_codes):
                self.matrix[row][col] = unique_codes[i]
    

    
    def _fill_remaining_cells(self):
        """填充剩余的空单元格"""
        for row in range(self.size):
            for col in range(self.size):
                if self.matrix[row][col] == "":
                    self.matrix[row][col] = random.choice(self.code_chars)
    
    def display_matrix(self) -> str:
        """显示矩阵"""
        lines = []

        # 添加列标题
        header = "    " + "".join(f" {i+1:2} " for i in range(self.size))
        lines.append(header)
        lines.append("   " + "━" * (self.size * 4 + 1))

        for i, row in enumerate(self.matrix):
            # 高亮当前可选择的行或列
            row_display = f"{i+1:2} ┃"
            for j, code in enumerate(row):
                if self._can_select_position(i, j):
                    row_display += f"[{code}]"
                else:
                    row_display += f" {code} "
            row_display += "┃"
            lines.append(row_display)

        lines.append("   " + "━" * (self.size * 4 + 1))
        return "\n".join(lines)
    
    def _can_select_position(self, row: int, col: int) -> bool:
        """检查是否可以选择指定位置"""
        if not self.current_path:
            # 第一步，只能选择第一行
            return row == 0
        
        last_row, last_col = self.current_path[-1]
        
        if self.is_horizontal:
            # 水平选择：必须在同一行，不同列
            return row == last_row and col != last_col
        else:
            # 垂直选择：必须在同一列，不同行
            return col == last_col and row != last_row
    
    def make_move(self, row: int, col: int) -> Tuple[bool, str]:
        """执行移动"""
        if not self._can_select_position(row, col):
            return False, "❌ 无效的位置选择"
        
        if len(self.current_path) >= self.buffer_size:
            return False, "❌ 缓冲区已满"
        
        # 添加到路径
        self.current_path.append((row, col))
        self.selected_codes.append(self.matrix[row][col])
        
        # 切换方向
        self.is_horizontal = not self.is_horizontal
        
        # 检查是否完成了新的序列
        self._check_completed_sequences()
        
        return True, "✅ 移动成功"
    
    def _check_completed_sequences(self):
        """检查是否完成了新的目标序列"""
        selected_str = "".join(self.selected_codes)
        
        for i, target in enumerate(self.target_sequences):
            if i not in self.completed_sequences:
                target_str = "".join(target.sequence)
                if target_str in selected_str:
                    self.completed_sequences.append(i)
    
    def get_status(self) -> str:
        """获取游戏状态"""
        lines = []
        lines.append("� 阵法破解 - 天干地支阵")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(self.display_matrix())
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 显示目标序列
        lines.append("🎯 破阵目标:")
        for i, target in enumerate(self.target_sequences):
            status = "✅" if i in self.completed_sequences else "⭕"
            seq_str = " → ".join(target.sequence)
            lines.append(f"  {status} {target.name}: {seq_str} (+{target.reward}💰)")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 显示当前状态
        if self.selected_codes:
            lines.append(f"📝 当前符文: {' → '.join(self.selected_codes)}")
        else:
            lines.append("📝 当前符文: (空)")

        lines.append(f"⚡ 灵力: {len(self.current_path)}/{self.buffer_size}")

        if self.current_path:
            direction = "横向" if self.is_horizontal else "纵向"
            lines.append(f"🧭 下一步: {direction}移动")
            if self.is_horizontal:
                last_row, _ = self.current_path[-1]
                lines.append(f"💡 提示: 在第{last_row+1}行选择不同列")
            else:
                _, last_col = self.current_path[-1]
                lines.append(f"💡 提示: 在第{last_col+1}列选择不同行")
        else:
            lines.append("🧭 下一步: 选择第一行任意位置")
            lines.append("💡 提示: 输入【阵法破解 1 <列号>】")

        return "\n".join(lines)
    
    def is_game_over(self) -> bool:
        """检查游戏是否结束"""
        return len(self.current_path) >= self.buffer_size
    
    def calculate_reward(self) -> int:
        """计算奖励"""
        total_reward = 0
        for i in self.completed_sequences:
            total_reward += self.target_sequences[i].reward
        return total_reward

@array_breaking.handle()
async def handle_array_breaking(event: MessageEvent, args: Message = CommandArg()):
    """处理阵法破解游戏"""
    # 获取玩家信息
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await array_breaking.finish("⛔ 请先创建角色")
        
        player_gold = player.gold

    args_text = args.extract_plain_text().strip()
    user_id = event.get_user_id()

    # 显示帮助
    if not args_text:
        help_msg = (
            "� 天干地支阵法破解\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎮 游戏规则：\n"
            "▫️ 在天干地支阵中寻找目标符文序列\n"
            "▫️ 只能按行列交替选择（横纵交替）\n"
            "▫️ 第一步只能选择第一行\n"
            "▫️ 有限的灵力步数（6步）\n"
            "▫️ 完成更多符文序列获得更多奖励\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📝 使用方法：\n"
            "▫️ 【阵法破解 开始】 - 开始5x5阵法\n"
            "▫️ 【阵法破解 困难】 - 开始6x6阵法\n"
            "▫️ 【阵法破解 <行> <列>】 - 选择位置\n"
            "▫️ 【阵法破解 放弃】 - 放弃当前游戏\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💰 费用：100💰 (5x5) / 150💰 (6x6)\n"
            "💡 例如：【阵法破解 1 3】选择第1行第3列\n"
            "🎯 目标：在灵力用完前完成尽可能多的符文序列"
        )
        await array_breaking.finish(message_add_head(help_msg, event))

    # 开始新游戏
    if args_text in ["开始", "困难"]:
        size = 5 if args_text == "开始" else 6
        cost = 100 if size == 5 else 150

        # 检查金币
        if player_gold < cost:
            await array_breaking.finish(f"❌ 金币不足！需要至少{cost}💰才能开始游戏")

        game = ArrayBreakingGame(size)
        game.game_cost = cost  # 记录游戏成本
        game_sessions[user_id] = game

        difficulty_text = "标准(5x5)" if size == 5 else "困难(6x6)"
        result_msg = f"🎮 已开始{difficulty_text}阵法\n" + game.get_status()
        await array_breaking.finish(message_add_head(result_msg, event))

    # 放弃游戏
    if args_text == "放弃":
        if user_id in game_sessions:
            del game_sessions[user_id]
            await array_breaking.finish(message_add_head("🏳️ 已放弃当前阵法", event))
        else:
            await array_breaking.finish(message_add_head("❌ 没有进行中的阵法", event))

    # 检查是否有进行中的游戏
    if user_id not in game_sessions:
        await array_breaking.finish("❌ 没有进行中的阵法，请先使用【阵法破解 开始】")

    game = game_sessions[user_id]

    # 处理位置选择
    try:
        parts = args_text.split()
        if len(parts) != 2:
            raise ValueError
        row = int(parts[0]) - 1  # 转换为0索引
        col = int(parts[1]) - 1
        
        if row < 0 or row >= game.size or col < 0 or col >= game.size:
            raise ValueError
    except ValueError:
        await array_breaking.finish("⚠️ 请输入正确的行列坐标，例如：【阵法破解 1 3】")

    # 执行移动
    success, message = game.make_move(row, col)
    if not success:
        await array_breaking.finish(message_add_head(message, event))

    # 检查游戏是否结束
    if game.is_game_over():
        reward = game.calculate_reward()
        cost = game.game_cost  # 使用动态游戏成本
        net_gain = reward - cost
        
        # 更新玩家金币
        async with safe_session() as session:
            player = await session.get(Player, event.get_user_id())
            player.gold += net_gain
            session.add(player)
            await session.commit()
            new_gold = player.gold

        # 清除游戏状态
        del game_sessions[user_id]

        # 生成结果消息
        result_lines = []
        result_lines.append("� 阵法破解完成！")
        result_lines.append("━━━━━━━━━━━━━━━━━━━━")

        if game.completed_sequences:
            result_lines.append("✅ 成功破解的符文序列：")
            for i in game.completed_sequences:
                target = game.target_sequences[i]
                result_lines.append(f"▫️ {target.name}: +{target.reward}💰")
        else:
            result_lines.append("❌ 未能破解任何符文序列")
        
        result_lines.append("━━━━━━━━━━━━━━━━━━━━")
        result_lines.append(f"💰 总奖励: {reward}💰")
        result_lines.append(f"💸 阵法成本: -{cost}💰")
        result_lines.append(f"📊 净收益: {net_gain:+d}💰")
        result_lines.append(f"💰 当前金币: {new_gold}")

        result_msg = "\n".join(result_lines)
        await array_breaking.finish(message_add_head(result_msg, event))

    # 游戏继续，显示当前状态
    result_msg = game.get_status()
    await array_breaking.finish(message_add_head(result_msg, event))
