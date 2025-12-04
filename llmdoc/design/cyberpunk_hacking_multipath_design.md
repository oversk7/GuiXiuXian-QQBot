# cyberpunk_hacking 多路径机制设计方案

**日期**: 2025-12-04
**目标**: 解决序列生成可解性问题，实现多路径机制
**优先级**: P0（紧急）

---

## 1. 问题回顾

当前问题：
- 生成的预设路径是随机的
- 玩家探索的路径也是随机的
- 两条路径匹配概率 < 0.2%
- 玩家几乎无法完成游戏

**根本原因**: 单一路径设计，玩家发现概率极低

---

## 2. 方案A：多路径机制

### 2.1 核心设计

**目标**: 生成3-5条不同的可行路径，每条都能完成所有目标序列

**关键改进**:
1. 不再生成单一预设路径
2. 生成多条互不相同的可行路径
3. 在所有路径上同时放置目标符文
4. 玩家选择任意一条都能完成

### 2.2 算法流程

```
步骤1: 生成最优序列
  └─ 改进排列组合（6→24种）
  └─ 确保包含所有目标序列

步骤2: 生成多条可行路径（3-5条）
  ├─ 第1条: 从行0随机起点，交替移动
  ├─ 第2条: 不同起点，避免与第1条完全重叠
  ├─ 第3条: 再次不同起点
  └─ 确保路径多样性（重叠度<40%）

步骤3: 在多条路径上放置符文
  ├─ 路径1: matrix[path1[i]] = optimal_sequence[i]
  ├─ 路径2: matrix[path2[i]] = optimal_sequence[i]
  └─ 路径3: matrix[path3[i]] = optimal_sequence[i]
  注意: 处理路径交叉点（多条路径可能经过同一格）

步骤4: 智能填充剩余格子
  ├─ 优先填充"接近目标序列"的符文
  └─ 避免在关键路径附近放置干扰符文
```

### 2.3 路径多样性策略

**目标**: 确保3条路径不完全重叠，提高玩家发现概率

**策略**:
1. **起点分散**: 第1条起点=(0, 0-2)，第2条=(0, 3-4)，第3条=(0, 中间随机)
2. **方向偏好**: 第1条偏左移动，第2条偏右，第3条混合
3. **重叠度检查**: 任意两条路径重叠格子数 < 40%

**伪代码**:
```python
def generate_diverse_paths(optimal_seq_length: int, target_count: int) -> List[List[Tuple[int, int]]]:
    paths = []
    target_path_count = min(target_count + 1, 5)  # 3-5条路径

    for i in range(target_path_count):
        max_attempts = 50
        for attempt in range(max_attempts):
            # 根据索引选择不同起点
            if i == 0:
                start_col = random.randint(0, size // 2)  # 左侧起点
            elif i == 1:
                start_col = random.randint(size // 2 + 1, size - 1)  # 右侧起点
            else:
                start_col = random.randint(0, size - 1)  # 随机起点

            path = _generate_single_path(optimal_seq_length, start_col)

            # 检查路径多样性
            if _is_diverse_enough(path, paths):
                paths.append(path)
                break

        if len(paths) <= i:
            # 如果生成失败，使用fallback
            paths.append(_generate_fallback_path())

    return paths

def _is_diverse_enough(new_path: List[Tuple], existing_paths: List[List[Tuple]]) -> bool:
    """检查新路径与已有路径的多样性"""
    for existing in existing_paths:
        overlap = set(new_path) & set(existing)
        overlap_ratio = len(overlap) / len(new_path)
        if overlap_ratio > 0.4:  # 重叠超过40%，拒绝
            return False
    return True
```

---

## 3. 关键改进点

### 3.1 改进1: 扩展排列组合覆盖率

**问题**: 当前仅尝试6种排列，6x6的4!  = 24种只覆盖25%

**修复**:
```python
def _get_sequence_permutations(self, sequences: List[List[str]]) -> List[List[List[str]]]:
    """获取序列的所有排列组合"""
    import itertools
    # 移除限制，尝试所有排列
    return list(itertools.permutations(sequences))  # 全部尝试
```

**改进后**:
- 5x5: 3! = 6种 → 6种（无变化，已完整）
- 6x6: 4! = 24种 → 24种（100%覆盖）

### 3.2 改进2: Fallback路径动态化

**问题**: Fallback固定4步，6x6无法覆盖所有目标

**修复**:
```python
def _generate_fallback_path(self) -> List[Tuple[int, int]]:
    """生成备用路径，确保覆盖所有目标"""
    # 动态计算需要的最小步数
    min_steps = len(self._create_optimal_sequence())
    min_steps = min(min_steps, self.buffer_size)  # 不超过缓冲区

    path = []
    current_row = 0
    current_col = random.randint(0, self.size - 1)
    path.append((current_row, current_col))

    is_horizontal = True
    for _ in range(1, min_steps):  # 使用动态步数
        # 交替移动...

    return path
```

### 3.3 改进3: 智能符文填充

**问题**: 随机填充可能干扰玩家

**修复**:
```python
def _fill_remaining_cells_smart(self, paths: List[List[Tuple[int, int]]]):
    """智能填充剩余格子，避免过度干扰"""
    # 收集所有路径上的位置
    path_positions = set()
    for path in paths:
        path_positions.update(path)

    # 收集目标序列中使用的符文
    used_runes = set()
    for target in self.target_sequences:
        used_runes.update(target.sequence)

    # 创建"安全符文池"（不在目标中的符文）
    safe_runes = [r for r in self.code_chars if r not in used_runes]

    for row in range(self.size):
        for col in range(self.size):
            if self.matrix[row][col] == "":
                # 检查是否接近路径（距离<2格）
                is_near_path = any(
                    abs(row - pr) + abs(col - pc) <= 2
                    for pr, pc in path_positions
                )

                if is_near_path and safe_runes:
                    # 接近路径，使用安全符文
                    self.matrix[row][col] = random.choice(safe_runes)
                else:
                    # 远离路径，随机填充
                    self.matrix[row][col] = random.choice(self.code_chars)
```

---

## 4. 多路径符文放置策略

### 4.1 路径交叉处理

**问题**: 多条路径可能经过同一格子

**策略**:
- 优先保留第一条路径的符文
- 记录冲突位置
- 在其他路径上跳过冲突格

```python
def _place_codes_on_multiple_paths(self, paths: List[List[Tuple]], optimal_sequence: List[str]):
    """在多条路径上放置符文"""
    placed_positions = {}  # {(row, col): rune}

    for path_idx, path in enumerate(paths):
        for i, (row, col) in enumerate(path):
            if i >= len(optimal_sequence):
                break

            expected_rune = optimal_sequence[i]

            if (row, col) in placed_positions:
                # 位置已被占用
                if placed_positions[(row, col)] == expected_rune:
                    # 符文相同，完美！继续
                    continue
                else:
                    # 符文冲突，标记但继续尝试
                    # 这条路径在这个位置的符文将不同
                    # 但后续位置仍然尝试放置
                    continue
            else:
                # 新位置，放置符文
                self.matrix[row][col] = expected_rune
                placed_positions[(row, col)] = expected_rune
```

### 4.2 完整可解性验证

**目标**: 确保每条路径都能真正完成所有目标序列

```python
def _verify_path_solvability(self, path: List[Tuple], target_sequences: List[TargetSequence]) -> bool:
    """验证路径可解性"""
    # 提取路径上的符文序列
    rune_sequence = "".join([self.matrix[row][col] for row, col in path])

    # 检查所有目标序列
    for target in target_sequences:
        target_str = "".join(target.sequence)
        if target_str not in rune_sequence:
            return False  # 无法完成所有目标

    return True
```

---

## 5. 完整的重构代码结构

### 5.1 新增方法列表

```python
class ArrayBreakingGame:
    # 新增方法
    def _generate_diverse_paths(self, optimal_seq_length: int) -> List[List[Tuple[int, int]]]:
        """生成多条多样化路径"""

    def _is_diverse_enough(self, new_path: List[Tuple], existing_paths: List[List[Tuple]]) -> bool:
        """检查路径多样性"""

    def _place_codes_on_multiple_paths(self, paths: List[List[Tuple]], optimal_sequence: List[str]):
        """在多条路径上放置符文"""

    def _fill_remaining_cells_smart(self, paths: List[List[Tuple]]):
        """智能填充剩余格子"""

    def _verify_path_solvability(self, path: List[Tuple]) -> bool:
        """验证单条路径的可解性"""

    def _verify_all_paths(self, paths: List[List[Tuple]]) -> int:
        """验证所有路径，返回可解路径数"""

    # 修改的现有方法
    def _get_sequence_permutations(self, sequences: List[List[str]]) -> List[List[List[str]]]:
        """扩展到全部排列"""

    def _generate_fallback_path(self) -> List[Tuple[int, int]]:
        """动态化fallback步数"""

    def _generate_solvable_puzzle(self):
        """主流程改为多路径"""
```

### 5.2 主流程修改

```python
def _generate_solvable_puzzle(self):
    """生成有解的谜题（多路径版本）"""
    # 步骤1: 生成目标序列（不变）
    self._generate_target_sequences()

    # 步骤2: 创建最优序列（改进排列组合）
    optimal_sequence = self._create_optimal_sequence()

    # 步骤3: 生成多条路径（核心改进）
    paths = self._generate_diverse_paths(len(optimal_sequence))

    # 步骤4: 在多条路径上放置符文（新方法）
    self.matrix = [["" for _ in range(self.size)] for _ in range(self.size)]
    self._place_codes_on_multiple_paths(paths, optimal_sequence)

    # 步骤5: 验证可解性
    solvable_count = self._verify_all_paths(paths)
    if solvable_count == 0:
        # 所有路径都不可解，使用fallback
        fallback_path = self._generate_fallback_path()
        self._place_codes_on_path(fallback_path)

    # 步骤6: 智能填充剩余格子（改进）
    self._fill_remaining_cells_smart(paths)
```

---

## 6. 预期效果

### 6.1 可解性提升

| 场景 | 当前概率 | 多路径后 | 提升倍数 |
|------|---------|---------|---------|
| 5x5 (3条路径) | 0.2% | 15-20% | **75-100倍** |
| 6x6 (4条路径) | 0.1% | 20-30% | **200-300倍** |

### 6.2 玩家体验改善

- ✅ 玩家更容易完成至少部分目标序列
- ✅ 多次尝试后能发现不同的可行路径
- ✅ 游戏不再是"纯运气"，有探索价值
- ✅ 社交讨论价值提升（"我发现了一条新路径！"）

### 6.3 技术债清理

- ✅ 修复排列组合不完整问题（P0）
- ✅ 修复Fallback路径过短问题（P0）
- ✅ 优化符文填充算法（P1）
- ✅ 为后续配置化打下基础（P1）

---

## 7. 实施优先级

**Phase 1 (立即实施，2-3小时)**:
1. 扩展排列组合到全部（改1行代码）
2. 动态化Fallback步数（改5行代码）
3. 实现多路径生成核心逻辑（新增50行代码）

**Phase 2 (第二阶段，1-2小时)**:
4. 实现多路径符文放置（新增30行代码）
5. 实现智能填充算法（新增40行代码）

**Phase 3 (验证测试，1小时)**:
6. 添加可解性验证逻辑（新增20行代码）
7. 测试多种场景的可解性

**总工作量**: 4-6小时

---

## 8. 风险与注意事项

### 8.1 路径冲突处理

**风险**: 多条路径可能在同一格子放置不同符文

**缓解**:
- 优先保留第一条路径的符文
- 记录冲突，后续路径绕开
- 或者在冲突点放置两条路径都需要的符文（如果存在）

### 8.2 性能影响

**风险**: 生成多条路径增加计算量

**缓解**:
- 从尝试50次减少到30次（多路径后不需要太多尝试）
- 缓存最优序列结果，避免重复计算

### 8.3 向后兼容

**风险**: 修改后可能影响现有游戏逻辑

**缓解**:
- 保持命令接口不变
- 保持奖励计算逻辑不变
- 只修改内部生成算法

---

## 9. 后续优化方向

完成多路径机制后，可以继续优化：

1. **配置化改造** (P1):
   - 将目标序列移到YAML配置
   - 支持热更新

2. **难度扩展** (P1):
   - 增加到4-5个难度等级
   - 根据难度调整路径数量

3. **统计功能** (P2):
   - 记录玩家完成路径
   - 分析哪些路径更容易被发现

4. **提示系统** (P2):
   - 完成部分序列后给予方向提示
   - 引导玩家探索

---

## 10. 总结

**方案A（多路径机制）核心优势**:
- ✅ 直接解决可解性问题（提升75-300倍）
- ✅ 无需改变游戏规则
- ✅ 实施成本可控（4-6小时）
- ✅ 为后续优化打下基础

**关键改进点**:
1. 从单一路径改为3-5条路径
2. 扩展排列组合覆盖率到100%
3. 动态化Fallback步数
4. 智能符文填充算法

**下一步**: 开始实施代码修改
