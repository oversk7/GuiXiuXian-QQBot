from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..platform_utils import get_unified_player, require_player
import random
import asyncio
from typing import List, Tuple, Dict
from dataclasses import dataclass
import base64
from .cyberpunk_hacking_image import generate_game_image

# 游戏状态存储
game_sessions: Dict[str, 'ArrayBreakingGame'] = {}

# 阵法破解游戏命令
array_breaking = on_command("阵法破解", aliases={"破阵", "阵法"}, priority=13, block=True)

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
        """生成有解的谜题（先安插答案，再填充干扰）"""
        # 步骤1: 生成目标序列
        self._generate_target_sequences()

        # 步骤2: 创建空矩阵
        self.matrix = [["" for _ in range(self.size)] for _ in range(self.size)]

        # 步骤3: 生成最优序列（包含所有目标）
        optimal_sequence = self._create_optimal_covering_sequence()

        # 步骤4: 生成3-5条保证有效的答案路径
        answer_paths = self._generate_guaranteed_answer_paths(optimal_sequence, count=4)

        # 步骤5: 在答案路径上精确放置符文（确保有解！）
        self._place_answer_on_paths(answer_paths, optimal_sequence)

        # 步骤6: 填充干扰项
        self._fill_interference_runes()
    
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

    def _generate_guaranteed_answer_paths(self, optimal_sequence: List[str], count: int) -> List[List[Tuple[int, int]]]:
        """生成保证有效的答案路径（严格遵循游戏规则）"""
        paths = []
        max_attempts = 50
        path_length = len(optimal_sequence)

        for i in range(count):
            for attempt in range(max_attempts):
                # 从第一行随机选择起点
                start_col = random.randint(0, self.size - 1)

                # 生成严格的行列交替路径
                path = self._generate_valid_alternating_path(path_length, start_col)

                if path:
                    paths.append(path)
                    break

        return paths

    def _generate_valid_alternating_path(self, length: int, start_col: int) -> List[Tuple[int, int]]:
        """生成有效的行列交替路径（严格遵循游戏规则）"""
        path = []
        current_row = 0
        current_col = start_col
        path.append((current_row, current_col))

        is_horizontal = True  # 第一步从第一行开始，下一步必须是横向移动

        for _ in range(1, length):
            if is_horizontal:
                # 横向移动：同行不同列
                available_cols = [c for c in range(self.size) if c != current_col]
                if available_cols:
                    current_col = random.choice(available_cols)
                    path.append((current_row, current_col))
                else:
                    return None
            else:
                # 纵向移动：同列不同行
                available_rows = [r for r in range(self.size) if r != current_row]
                if available_rows:
                    current_row = random.choice(available_rows)
                    path.append((current_row, current_col))
                else:
                    return None

            is_horizontal = not is_horizontal

        return path

    def _place_answer_on_paths(self, paths: List[List[Tuple[int, int]]], optimal_sequence: List[str]):
        """在答案路径上精确放置符文（确保100%有解）"""
        # 所有路径都强制完整放置（确保多条答案路径）
        for path_idx, path in enumerate(paths):
            for i, (row, col) in enumerate(path):
                if i >= len(optimal_sequence):
                    break

                rune = optimal_sequence[i]

                # 第一条路径强制放置
                if path_idx == 0:
                    self.matrix[row][col] = rune
                else:
                    # 其他路径：如果位置为空或已有相同符文，则放置
                    if self.matrix[row][col] == "" or self.matrix[row][col] == rune:
                        self.matrix[row][col] = rune
                    # 如果位置已有不同符文，跳过（避免破坏第一条路径）

    def _fill_interference_runes(self):
        """填充干扰符文（目标符文+随机符文混合）"""
        # 收集目标符文
        target_runes = set()
        for target in self.target_sequences:
            target_runes.update(target.sequence)

        target_runes_list = list(target_runes)

        # 创建干扰符文池（所有符文）
        interference_pool = self.code_chars.copy()

        # 填充所有空位（注意：已有符文的位置不覆盖，保护答案路径）
        for row in range(self.size):
            for col in range(self.size):
                if self.matrix[row][col] == "":
                    # 60%使用目标符文（提高密度），40%使用随机符文（增加干扰）
                    if random.random() < 0.60:
                        self.matrix[row][col] = random.choice(target_runes_list)
                    else:
                        self.matrix[row][col] = random.choice(interference_pool)

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
            # 随机选择一种目标序列组合，增加多样性
            variant = random.randint(1, 4)

            if variant == 1:
                # 组合1: 首尾相连链（最优8步）
                sequences = [
                    (["甲", "子", "丙", "丁"], 110, "木火土聚"),
                    (["丙", "丁", "戊"], 90, "火土相生"),
                    (["戊", "己", "庚", "辛"], 140, "土金水转"),
                ]
            elif variant == 2:
                # 组合2: 部分重叠（最优7步）
                sequences = [
                    (["甲", "子", "丙", "丁"], 110, "四象初成"),
                    (["丁", "戊", "己"], 90, "三元归位"),
                    (["甲", "子", "丙", "丁", "戊", "己", "庚"], 160, "七曜齐明"),
                ]
            elif variant == 3:
                # 组合3: 部分重叠2字符（最优7步）
                sequences = [
                    (["甲", "子", "丙", "丁"], 110, "四柱擎天"),
                    (["丙", "丁", "戊", "己"], 120, "中宫四象"),
                    (["戊", "己", "庚"], 100, "三合归位"),
                ]
            else:
                # 组合4: 混合模式（最优7步）
                sequences = [
                    (["甲", "子", "丙"], 100, "阳极三才"),
                    (["丙", "丁"], 60, "火德双全"),
                    (["甲", "子", "丙", "丁", "戊", "己"], 160, "六合圆满"),
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
        player = await require_player(session, event, array_breaking)
        
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

        # 生成游戏图片（线程池，避免阻塞事件循环）
        image_bytes = await asyncio.to_thread(game.get_status_image)
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

    # 游戏继续，显示当前状态（图片形式，线程池）
    image_bytes = await asyncio.to_thread(game.get_status_image)
    image_b64 = base64.b64encode(image_bytes).decode()
    img = MessageSegment.file_image(image_b64)
    text_msg = message_add_head("", event)
    msg = Message(text_msg).append(img)
    await array_breaking.finish(msg)
