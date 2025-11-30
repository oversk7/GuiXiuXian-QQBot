from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..platform_utils import get_unified_player
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
        # 重新设计序列，包含不同长度的挑战
        if self.size == 5:
            sequences = [
                (["甲", "子", "丙"], 120, "三才归一"),
                (["子", "丙"], 60, "阴阳相合"),
                (["丙", "丁"], 50, "火木相生"),
            ]
        else:  # 6x6
            sequences = [
                (["甲", "子", "丙", "丁"], 150, "四象轮转"),
                (["子", "丙"], 60, "阴阳相合"),
                (["丙", "丁"], 50, "火木相生"),
                (["丁", "戊"], 40, "土火相克"),
            ]

        self.target_sequences = []
        for seq, reward, name in sequences:
            self.target_sequences.append(TargetSequence(seq, reward, name))

    def _generate_main_solution_path(self) -> List[Tuple[int, int]]:
        """生成一条包含所有目标序列的主要解决路径"""
        # 尝试多次生成，找到最优解
        best_solution = None
        best_coverage = 0

        for _ in range(50):  # 尝试50次
            solution = self._try_generate_solution()
            if solution:
                coverage = self._calculate_sequence_coverage(solution)
                if coverage > best_coverage:
                    best_coverage = coverage
                    best_solution = solution
                    # 如果找到了包含所有序列的解，直接返回
                    if coverage == len(self.target_sequences):
                        break

        return best_solution if best_solution else self._generate_fallback_path()

    def _try_generate_solution(self) -> List[Tuple[int, int]]:
        """尝试生成一个解决方案"""
        # 创建一个包含所有目标序列的最优符文序列
        optimal_sequence = self._create_optimal_sequence()

        if len(optimal_sequence) > self.buffer_size:
            return None

        # 生成对应的路径
        return self._generate_path_for_sequence(optimal_sequence)

    def _create_optimal_sequence(self) -> List[str]:
        """创建包含尽可能多目标序列的最优符文序列"""
        sequences = [target.sequence for target in self.target_sequences]

        # 尝试多种组合策略
        best_sequence = None
        best_coverage = 0

        # 策略1: 尝试直接连接序列
        for perm in self._get_sequence_permutations(sequences):
            combined = self._combine_sequences(perm)
            if len(combined) <= self.buffer_size:
                coverage = self._count_contained_sequences(combined, sequences)
                if coverage > best_coverage:
                    best_coverage = coverage
                    best_sequence = combined

        # 策略2: 如果没有找到好的组合，使用贪心算法
        if not best_sequence:
            best_sequence = self._greedy_sequence_build(sequences)

        return best_sequence[:self.buffer_size]

    def _get_sequence_permutations(self, sequences: List[List[str]]) -> List[List[List[str]]]:
        """获取序列的不同排列组合（限制数量避免过度计算）"""
        import itertools
        # 只尝试前几种排列，避免计算量过大
        return list(itertools.permutations(sequences))[:6]

    def _combine_sequences(self, sequences: List[List[str]]) -> List[str]:
        """尝试智能组合多个序列，寻找重叠部分"""
        if not sequences:
            return []

        result = sequences[0].copy()

        for seq in sequences[1:]:
            # 寻找最佳连接点
            best_overlap = 0
            best_connection = len(result)

            # 检查是否可以重叠连接
            for i in range(len(result)):
                for j in range(len(seq)):
                    overlap_len = min(len(result) - i, len(seq) - j)
                    if result[i:i+overlap_len] == seq[j:j+overlap_len]:
                        if overlap_len > best_overlap:
                            best_overlap = overlap_len
                            best_connection = i

            # 如果找到重叠，智能连接
            if best_overlap > 0:
                # 找到seq中对应的位置
                for j in range(len(seq)):
                    if seq[j:j+best_overlap] == result[best_connection:best_connection+best_overlap]:
                        # 添加seq中重叠部分之后的内容
                        result.extend(seq[j+best_overlap:])
                        break
            else:
                # 没有重叠，直接连接
                result.extend(seq)

        return result

    def _greedy_sequence_build(self, sequences: List[List[str]]) -> List[str]:
        """使用贪心算法构建序列"""
        result = []
        active_sequences = [(seq, 0) for seq in sequences]  # (序列, 当前位置)

        while active_sequences and len(result) < self.buffer_size:
            # 统计每个字符能推进多少个序列
            char_scores = {}
            for seq, pos in active_sequences:
                if pos < len(seq):
                    char = seq[pos]
                    char_scores[char] = char_scores.get(char, 0) + 1

            if not char_scores:
                break

            # 选择得分最高的字符
            best_char = max(char_scores.keys(), key=lambda c: char_scores[c])
            result.append(best_char)

            # 更新活跃序列
            new_active = []
            for seq, pos in active_sequences:
                if pos < len(seq) and seq[pos] == best_char:
                    new_pos = pos + 1
                    if new_pos < len(seq):  # 序列还没完成
                        new_active.append((seq, new_pos))
                else:
                    new_active.append((seq, pos))  # 保持原位置

            active_sequences = new_active

        return result

    def _count_contained_sequences(self, combined: List[str], sequences: List[List[str]]) -> int:
        """计算组合序列中包含多少个目标序列"""
        combined_str = "".join(combined)
        count = 0
        for seq in sequences:
            seq_str = "".join(seq)
            if seq_str in combined_str:
                count += 1
        return count

    def _generate_path_for_sequence(self, sequence: List[str]) -> List[Tuple[int, int]]:
        """为给定的符文序列生成路径"""
        if not sequence:
            return []

        path = []
        current_row = 0
        current_col = random.randint(0, self.size - 1)
        path.append((current_row, current_col))

        is_horizontal = True
        for _ in range(1, len(sequence)):
            if is_horizontal:
                # 水平移动
                available_cols = [c for c in range(self.size) if c != current_col]
                if available_cols:
                    current_col = random.choice(available_cols)
                    path.append((current_row, current_col))
                else:
                    return None  # 无法继续
            else:
                # 垂直移动
                available_rows = [r for r in range(self.size) if r != current_row]
                if available_rows:
                    current_row = random.choice(available_rows)
                    path.append((current_row, current_col))
                else:
                    return None  # 无法继续

            is_horizontal = not is_horizontal

        return path

    def _calculate_sequence_coverage(self, path: List[Tuple[int, int]]) -> int:
        """计算路径能覆盖多少个目标序列"""
        if not path:
            return 0

        # 模拟在路径上放置符文
        temp_matrix = [["" for _ in range(self.size)] for _ in range(self.size)]
        optimal_sequence = self._create_optimal_sequence()

        for i, (row, col) in enumerate(path):
            if i < len(optimal_sequence):
                temp_matrix[row][col] = optimal_sequence[i]

        # 检查能匹配多少个目标序列
        path_sequence = "".join(optimal_sequence[:len(path)])
        coverage = 0

        for target in self.target_sequences:
            target_str = "".join(target.sequence)
            if target_str in path_sequence:
                coverage += 1

        return coverage

    def _generate_fallback_path(self) -> List[Tuple[int, int]]:
        """生成备用路径（确保至少有一个解）"""
        path = []
        current_row = 0
        current_col = random.randint(0, self.size - 1)
        path.append((current_row, current_col))

        is_horizontal = True
        for _ in range(1, min(self.buffer_size, 4)):  # 至少生成4步路径
            if is_horizontal:
                available_cols = [c for c in range(self.size) if c != current_col]
                if available_cols:
                    current_col = random.choice(available_cols)
                    path.append((current_row, current_col))
            else:
                available_rows = [r for r in range(self.size) if r != current_row]
                if available_rows:
                    current_row = random.choice(available_rows)
                    path.append((current_row, current_col))

            is_horizontal = not is_horizontal

        return path

    def _place_codes_on_path(self, path: List[Tuple[int, int]]):
        """在路径上放置符文，确保包含尽可能多的目标序列"""
        if not path:
            return

        # 生成最优符文序列
        optimal_sequence = self._create_optimal_sequence()

        # 在路径上放置符文
        for i, (row, col) in enumerate(path):
            if i < len(optimal_sequence):
                self.matrix[row][col] = optimal_sequence[i]
    

    
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
        header = "      " + "".join(f"  {i+1:2} " for i in range(self.size))
        lines.append(header)
        lines.append("━━━━━━━━━━━━━")

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
        lines.append("━━━━━━━━━━━━━")
        lines.append(self.display_matrix())
        lines.append("━━━━━━━━━━━━━")

        # 显示目标序列
        lines.append("🎯 破阵目标:")
        for i, target in enumerate(self.target_sequences):
            status = "✅" if i in self.completed_sequences else "⭕"
            seq_str = " → ".join(target.sequence)
            lines.append(f"  {status} {target.name}: {seq_str} (+{target.reward}💰)")

        lines.append("━━━━━━━━━━━━━")

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
        player = await get_unified_player(session, event)
        if not player:
            await array_breaking.finish("⛔ 请先创建角色")
        
        player_gold = player.gold

    args_text = args.extract_plain_text().strip()
    user_id = event.get_user_id()

    # 显示帮助
    if not args_text:
        help_msg = (
            "� 天干地支阵法破解\n"
            "━━━━━━━━━━━━━\n"
            "🎮 游戏规则：\n"
            "▫️ 在天干地支阵中寻找目标符文序列\n"
            "▫️ 只能按行列交替选择（横纵交替）\n"
            "▫️ 第一步只能选择第一行\n"
            "▫️ 有限的灵力步数（6步）\n"
            "▫️ 完成更多符文序列获得更多奖励\n"
            "━━━━━━━━━━━━━\n"
            "📝 使用方法：\n"
            "▫️ 【阵法破解 开始】 - 开始5x5阵法\n"
            "▫️ 【阵法破解 困难】 - 开始6x6阵法\n"
            "▫️ 【阵法破解 <行> <列>】 - 选择位置\n"
            "▫️ 【阵法破解 放弃】 - 放弃当前游戏\n"
            "━━━━━━━━━━━━━\n"
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
            player = await get_unified_player(session, event)
            player.gold += net_gain
            session.add(player)
            await session.commit()
            new_gold = player.gold

        # 清除游戏状态
        del game_sessions[user_id]

        # 生成结果消息
        result_lines = []
        result_lines.append("� 阵法破解完成！")
        result_lines.append("━━━━━━━━━━━━━")

        if game.completed_sequences:
            result_lines.append("✅ 成功破解的符文序列：")
            for i in game.completed_sequences:
                target = game.target_sequences[i]
                result_lines.append(f"▫️ {target.name}: +{target.reward}💰")
        else:
            result_lines.append("❌ 未能破解任何符文序列")
        
        result_lines.append("━━━━━━━━━━━━━")
        result_lines.append(f"💰 总奖励: {reward}💰")
        result_lines.append(f"💸 阵法成本: -{cost}💰")
        result_lines.append(f"📊 净收益: {net_gain:+d}💰")
        result_lines.append(f"💰 当前金币: {new_gold}")

        result_msg = "\n".join(result_lines)
        await array_breaking.finish(message_add_head(result_msg, event))

    # 游戏继续，显示当前状态
    result_msg = game.get_status()
    await array_breaking.finish(message_add_head(result_msg, event))
