from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..platform_utils import get_unified_player
import random
from typing import List, Tuple, Dict
from dataclasses import dataclass
import base64
from .cyberpunk_hacking_image import generate_game_image

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
        self.buffer_size = 8 if size == 7 else 6  # 7x7困难模式8步，5x5标准模式6步
        self.current_path: List[Tuple[int, int]] = []  # 当前路径
        self.selected_codes: List[str] = []  # 已选择的代码
        self.is_horizontal = True  # 当前是否在水平方向选择
        self.completed_sequences: List[int] = []  # 已完成的序列索引
        self.game_cost = 100  # 游戏成本，默认100
        
        # 可用的天干地支符号
        self.code_chars = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸", "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
        
        self._generate_solvable_puzzle()
    
    def _generate_solvable_puzzle(self):
        """生成有解的谜题（路径簇+高密度混合策略）"""
        # 步骤1: 生成目标序列
        self._generate_target_sequences()

        # 步骤2: 创建空矩阵
        self.matrix = [["" for _ in range(self.size)] for _ in range(self.size)]

        # 步骤3: 生成最优序列（包含所有目标）
        optimal_sequence = self._create_optimal_covering_sequence()

        # 步骤4: 生成多条可行路径簇（5-8条，确保可解性）
        target_path_count = min(self.size, 8)  # 5x5生成5条，7x7生成7条
        paths = self._generate_solvable_path_clusters(optimal_sequence, target_path_count)

        # 步骤5: 在路径簇上按顺序放置符文（关键！）
        self._place_sequences_on_paths(paths, optimal_sequence)

        # 步骤6: 填充剩余格子（高密度策略）
        self._fill_remaining_with_high_density()
    
    def _create_optimal_covering_sequence(self) -> List[str]:
        """创建包含所有目标序列的最优符文序列（强制100%覆盖）"""
        sequences = [target.sequence for target in self.target_sequences]

        # 按长度降序排序
        sorted_seqs = sorted(sequences, key=len, reverse=True)
        result = sorted_seqs[0].copy()

        # 逐个添加剩余序列
        for seq in sorted_seqs[1:]:
            seq_str = "".join(seq)
            result_str = "".join(result)

            # 检查是否已包含
            if seq_str in result_str:
                continue

            # 尝试找到最佳连接点（从后往前查找重叠）
            best_overlap = 0
            for overlap_len in range(min(len(result), len(seq)), 0, -1):
                if result[-overlap_len:] == seq[:overlap_len]:
                    best_overlap = overlap_len
                    break

            # 添加序列（去除重叠部分）
            if best_overlap > 0:
                result.extend(seq[best_overlap:])
            else:
                result.extend(seq)

        return result[:self.buffer_size]  # 不超过缓冲区大小

    def _generate_solvable_path_clusters(self, optimal_sequence: List[str], count: int) -> List[List[Tuple[int, int]]]:
        """生成多条可行路径簇（确保多样性）"""
        paths = []
        max_attempts = 50

        for i in range(count):
            for attempt in range(max_attempts):
                # 生成路径（长度=最优序列长度，不超过缓冲区）
                path_length = min(len(optimal_sequence), self.buffer_size)

                # 根据索引选择不同起点
                if i == 0:
                    start_col = random.randint(0, self.size // 2)
                elif i == 1:
                    start_col = random.randint(self.size // 2, self.size - 1)
                else:
                    start_col = random.randint(0, self.size - 1)

                # 生成单条路径
                path = self._generate_single_alternating_path(path_length, start_col)

                if path and self._is_path_diverse(path, paths):
                    paths.append(path)
                    break

        return paths

    def _generate_single_alternating_path(self, length: int, start_col: int) -> List[Tuple[int, int]]:
        """生成单条行列交替路径"""
        path = []
        current_row = 0
        current_col = start_col
        path.append((current_row, current_col))

        is_horizontal = True
        for _ in range(1, length):
            if is_horizontal:
                # 水平移动：选择不同列
                available_cols = [c for c in range(self.size) if c != current_col]
                if available_cols:
                    current_col = random.choice(available_cols)
                    path.append((current_row, current_col))
                else:
                    return None
            else:
                # 垂直移动：选择不同行
                available_rows = [r for r in range(self.size) if r != current_row]
                if available_rows:
                    current_row = random.choice(available_rows)
                    path.append((current_row, current_col))
                else:
                    return None

            is_horizontal = not is_horizontal

        return path

    def _is_path_diverse(self, new_path: List[Tuple[int, int]], existing_paths: List[List[Tuple[int, int]]]) -> bool:
        """检查路径多样性（重叠<30%）"""
        if not existing_paths:
            return True

        for existing in existing_paths:
            overlap = set(new_path) & set(existing)
            overlap_ratio = len(overlap) / len(new_path) if new_path else 0
            if overlap_ratio > 0.3:
                return False

        return True

    def _place_sequences_on_paths(self, paths: List[List[Tuple[int, int]]], optimal_sequence: List[str]):
        """在多条路径上按顺序放置符文（关键方法！）"""
        for path in paths:
            for i, (row, col) in enumerate(path):
                if i >= len(optimal_sequence):
                    break

                rune = optimal_sequence[i]

                # 如果位置已占用且符文相同，跳过
                if self.matrix[row][col] == rune:
                    continue
                # 如果位置为空，放置符文
                elif self.matrix[row][col] == "":
                    self.matrix[row][col] = rune
                # 如果位置已占用但符文不同，优先保留（避免覆盖）
                # 注：这可能导致某些路径不完整，但多条路径能保证整体可解性

    def _fill_remaining_with_high_density(self):
        """高密度填充剩余格子（目标符文为主）"""
        # 收集目标符文
        target_runes = set()
        for target in self.target_sequences:
            target_runes.update(target.sequence)

        # 创建安全符文池
        safe_runes = [r for r in self.code_chars if r not in target_runes]
        if not safe_runes:
            safe_runes = self.code_chars

        # 填充所有空位
        for row in range(self.size):
            for col in range(self.size):
                if self.matrix[row][col] == "":
                    # 70%使用目标符文，30%使用安全符文（增加巧合概率）
                    if random.random() < 0.70:
                        self.matrix[row][col] = random.choice(list(target_runes))
                    else:
                        self.matrix[row][col] = random.choice(safe_runes)

    def _generate_target_sequences(self):
        """生成目标序列"""
        # 重新设计序列，包含不同长度的挑战
        if self.size == 5:
            # 5x5标准模式：6步缓冲区
            sequences = [
                (["甲", "子", "丙"], 120, "三才归一"),
                (["子", "丙"], 60, "阴阳相合"),
                (["丙", "丁"], 50, "火木相生"),
            ]
        elif self.size == 7:
            # 7x7困难模式：8步缓冲区
            # 设计思路：首尾相连链，需要8步刚好完成，无容错空间（高难度）
            sequences = [
                (["甲", "子", "丙"], 100, "木火相生"),
                (["丙", "丁", "戊"], 100, "火土相生"),
                (["戊", "己", "庚", "辛"], 140, "土金相生"),
            ]
        else:
            # 其他大小使用默认
            sequences = [
                (["甲", "子", "丙", "丁"], 150, "四象轮转"),
                (["子", "丙"], 60, "阴阳相合"),
                (["丙", "丁"], 50, "火木相生"),
                (["丁", "戊"], 40, "土火相克"),
            ]

        self.target_sequences = []
        for seq, reward, name in sequences:
            self.target_sequences.append(TargetSequence(seq, reward, name))

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
    
    def get_status_image(self) -> bytes:
        """获取游戏状态图片"""
        return generate_game_image(self)

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
            "▫️ 有限的灵力步数（标准6步 / 困难8步）\n"
            "▫️ 完成更多符文序列获得更多奖励\n"
            "━━━━━━━━━━━━━\n"
            "📝 使用方法：\n"
            "▫️ 【阵法破解 开始】 - 开始5x5标准阵法（6步）\n"
            "▫️ 【阵法破解 困难】 - 开始7x7困难阵法（8步）\n"
            "▫️ 【阵法破解 <行> <列>】 - 选择位置\n"
            "▫️ 【阵法破解 放弃】 - 放弃当前游戏\n"
            "━━━━━━━━━━━━━\n"
            "💰 费用：100💰 (5x5) / 200💰 (7x7)\n"
            "💡 例如：【阵法破解 1 3】选择第1行第3列\n"
            "🎯 目标：在灵力用完前完成尽可能多的符文序列"
        )
        await array_breaking.finish(message_add_head(help_msg, event))

    # 开始新游戏
    if args_text in ["开始", "困难"]:
        size = 5 if args_text == "开始" else 7  # 困难模式改为7x7
        cost = 100 if size == 5 else 200  # 7x7成本提高到200

        # 检查金币
        if player_gold < cost:
            await array_breaking.finish(f"❌ 金币不足！需要至少{cost}💰才能开始游戏")

        game = ArrayBreakingGame(size)
        game.game_cost = cost  # 记录游戏成本
        game_sessions[user_id] = game

        difficulty_text = "标准(5x5/6步)" if size == 5 else "困难(7x7/8步)"

        # 生成游戏图片
        image_bytes = game.get_status_image()
        image_b64 = base64.b64encode(image_bytes).decode()

        # 发送图片和说明
        img = MessageSegment.file_image(image_b64)
        text_msg = message_add_head(f"🎮 已开始{difficulty_text}阵法\n💡 输入【阵法破解 行号 列号】选择符文", event)
        msg = Message(text_msg).append(img)
        await array_breaking.finish(msg)

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

    # 游戏继续，显示当前状态（图片形式）
    image_bytes = game.get_status_image()
    image_b64 = base64.b64encode(image_bytes).decode()
    img = MessageSegment.file_image(image_b64)
    text_msg = message_add_head("", event)
    msg = Message(text_msg).append(img)
    await array_breaking.finish(msg)
