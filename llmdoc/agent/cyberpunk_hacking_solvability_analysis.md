# cyberpunk_hacking 序列生成可解性深度分析

**调查日期**: 2025-12-04
**对象代码**: `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py`
**调查焦点**: 解题逻辑、序列生成算法、可解性保证机制

---

## Code Sections (The Evidence)

### 游戏解题机制相关
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 346-359, `_can_select_position`): 定义了合法选择的规则，第一步仅第一行可选，之后严格按行列交替（当前为水平时只能选列，为纵向时只能选行）。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 361-379, `make_move`): 玩家移动的核心逻辑，每次移动切换方向，添加符号到选择序列。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 381-389, `_check_completed_sequences`): 完成序列判定使用子串匹配（`in`操作符），无需连续选择。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 431-433, `is_game_over`): 游戏结束条件为达到缓冲区限制（6步）。

### 目标序列定义
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 63-82, `_generate_target_sequences`): 5x5模式固定3个序列，6x6模式固定4个序列，所有信息硬编码。

### 序列生成算法核心流程
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 45-61, `_generate_solvable_puzzle`): 倒推生成流程：先生成目标序列→生成主解决路径→在路径上放置代码→填充剩余。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 84-101, `_generate_main_solution_path`): 尝试50次生成路径，选择覆盖最多序列的方案，失败时使用fallback路径。

### 最优序列组合算法
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 114-135, `_create_optimal_sequence`): 双策略组合，先尝试排列组合（限制6种排列），再用贪心算法。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 143-176, `_combine_sequences`): 寻找重叠连接算法，检查子序列匹配实现重叠。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 178-210, `_greedy_sequence_build`): 贪心算法，每步选择得分最高的字符（能推进最多序列）。

### 路径生成
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 222-253, `_generate_path_for_sequence`): 随机生成交替移动路径，不保证访问特定序列。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 279-301, `_generate_fallback_path`): Fallback路径，仅生成4步（`min(buffer_size, 4)`），确保最少有解。

### 符文放置与填充
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 303-314, `_place_codes_on_path`): 在主路径上放置最优序列符文。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 318-323, `_fill_remaining_cells`): 剩余格子随机填充（`random.choice`），完全无约束。

### 序列覆盖度计算
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 255-277, `_calculate_sequence_coverage`): 模拟路径，计算覆盖度使用字符串包含判定。
- `plugins/xiuxian_game/entertainment/cyberpunk_hacking.py` (lines 212-220, `_count_contained_sequences`): 计算组合序列中包含目标序列数，基于子串匹配。

---

## Report (The Answers)

### Part 1: 游戏解题机制完整描述

#### 1.1 行列交替选择规则

游戏的选择规则严格规定了路径的移动方式：

1. **首步限制** (lines 346-350): 第一步必须在第一行(row == 0)选择任意列
2. **交替约束** (lines 354-359):
   - 水平状态(is_horizontal=True): 必须在同一行选择不同列
   - 纵向状态(is_horizontal=False): 必须在同一列选择不同行
3. **方向切换** (line 374): 每次成功移动自动切换方向

**关键观察**: 这种严格的交替规则意味着：
- 5x5矩阵中，水平移动最多可选4次（从第i行选择5列中的不同列）
- 纵向移动最多可选4次（从第j列选择5行中的不同行）
- 因此6步路径的理论空间是有限的

#### 1.2 序列完成判定逻辑

```
selected_str = "甲乙子丙丁"  # 玩家选择序列
target_str = "甲子丙"       # 目标序列
if target_str in selected_str:  # "甲子丙" in "甲乙子丙丁" = True
    完成!
```

**关键问题**: 子串匹配意味着：
- 玩家不需要连续选择目标序列中的符号
- 只要目标序列作为子串出现即可
- 例如："甲-**乙**-**子**-**丙**-丁" 中，虽然"乙"在"子"和"丙"之间，但"甲子丙"仍然被识别为完成

**实际例子** (5x5模式):
- 目标: ["甲", "子", "丙"], ["子", "丙"], ["丙", "丁"]
- 玩家选择: "甲子丙丁" (4个符号)
- 结果:
  - "甲子丙" in "甲子丙丁" ✓ 完成序列1
  - "子丙" in "甲子丙丁" ✓ 完成序列2
  - "丙丁" in "甲子丙丁" ✓ 完成序列3
  - 所有目标都在6步以内完成！

#### 1.3 游戏结束条件

游戏在两种情况下结束：
1. 缓冲区满: `len(current_path) >= buffer_size` (6步)
2. 玩家主动放弃: `【阵法破解 放弃】`

**关键**: 游戏结束时，无论是否完成所有序列，奖励都是根据已完成序列计算。

### Part 2: 序列生成算法逐步拆解

#### 2.1 出题的倒推生成流程

整个出题过程遵循**倒推模式**：

```
步骤1: _generate_target_sequences()
  └─ 硬编码目标序列集合
     5x5: ["甲子丙"], ["子丙"], ["丙丁"]
     6x6: ["甲子丙丁"], ["子丙"], ["丙丁"], ["丁戊"]

步骤2: _generate_main_solution_path() (lines 84-101)
  ├─ 循环50次调用 _try_generate_solution()
  │  └─ 内部调用 _create_optimal_sequence() 生成"最优序列"
  │  └─ 内部调用 _generate_path_for_sequence() 为其生成路径
  ├─ 对比50条路径，选择覆盖目标序列最多的路径
  └─ 失败时返回 _generate_fallback_path() (4步备用路径)

步骤3: _place_codes_on_path(path) (lines 303-314)
  └─ 在选定的路径上放置最优序列符号

步骤4: _fill_remaining_cells() (lines 318-323)
  └─ 剩余格子随机填充符号
```

**问题1**: 这个流程假设"最优序列"能被某条路径完全包含，但没有验证。

#### 2.2 "最优序列"生成算法分析

`_create_optimal_sequence()`尝试两种策略 (lines 114-135):

**策略1: 排列组合法** (lines 123-129)
```python
for perm in self._get_sequence_permutations(sequences):  # 最多尝试6种排列
    combined = self._combine_sequences(perm)  # 智能重叠连接
    if len(combined) <= self.buffer_size:  # 长度不超过6
        coverage = self._count_contained_sequences(combined, sequences)
        if coverage > best_coverage:
            best_coverage = coverage
            best_sequence = combined
```

关键细节:
- 只尝试 `itertools.permutations(sequences)[:6]` 即最多6种排列
- 对于5x5的3个序列，3!  = 6种排列，全部尝试 ✓
- 对于6x6的4个序列，4! = 24种排列，仅尝试前6种 ✗ **可能遗漏最优解**

**策略2: 贪心算法** (lines 132-133)

若排列组合无结果，使用贪心:

```python
result = []
active_sequences = [(seq, 0) for seq in sequences]  # 追踪每个序列进度

while active_sequences and len(result) < 6:
    char_scores = {}
    for seq, pos in active_sequences:
        if pos < len(seq):
            char = seq[pos]
            char_scores[char] = char_scores.get(char, 0) + 1

    best_char = max(char_scores, key=lambda c: char_scores[c])  # 得分最高的字符
    result.append(best_char)
    # 更新进度...
```

**贪心逻辑的问题**:
- 每步选择"能最多推进多个序列"的字符
- 但这不保证最终能包含所有序列
- 例如，若目标是 ["AB", "CD"]，贪心可能选择"AC"（各推一个），无法同时包含两个序列

**实际例子** (5x5):

目标序列:
1. ["甲", "子", "丙"]
2. ["子", "丙"]
3. ["丙", "丁"]

排列组合法可能产生: "甲子丙丁" (4步)
- 包含所有3个序列 ✓
- 长度 <= 6 ✓

但如果排列组合失败，贪心会如何？
- 第1步: 可选字符及得分 {"甲":1, "子":2, "丙":3, "丁":1}
  贪心选"丙"(得分3) → result = ["丙"]
- 第2步: 更新进度，可能选"丁"
- 最终可能得到"丙丁..."，**遗漏了"甲子"**

#### 2.3 重叠连接算法分析 (`_combine_sequences`)

此函数尝试寻找序列间的重叠来压缩长度 (lines 143-176):

```python
result = sequences[0].copy()  # 以第一个序列开始

for seq in sequences[1:]:
    # 寻找最佳重叠点
    best_overlap = 0
    best_connection = len(result)

    for i in range(len(result)):
        for j in range(len(seq)):
            overlap_len = min(len(result) - i, len(seq) - j)
            if result[i:i+overlap_len] == seq[j:j+overlap_len]:
                if overlap_len > best_overlap:
                    best_overlap = overlap_len
                    best_connection = i

    # 找到最大重叠后连接
    if best_overlap > 0:
        result.extend(seq[j+best_overlap:])
    else:
        result.extend(seq)  # 无重叠，直接连接
```

**问题分析**:

1. **重叠检测的局限性**:
   - 只找"相同子序列"的重叠
   - 对于["甲", "子", "丙"]和["子", "丙"]，重叠应该是["子", "丙"]（2个元素）
   - 但这个算法寻找的是"连续子数组"的相等性，可能不会识别出来

2. **实际测试**:
   - result = ["甲", "子", "丙"]
   - seq = ["子", "丙"]
   - i=0, j=0: result[0:2] = ["甲","子"] vs seq[0:2] = ["子","丙"] → 不相等
   - i=1, j=0: result[1:3] = ["子","丙"] vs seq[0:2] = ["子","丙"] → **相等！overlap_len=2**
   - 所以best_overlap=2, best_connection=1
   - 连接: result.extend(seq[2:]) = result.extend([]) → 无新增，仍是["甲","子","丙"]

   **这是正确的!** 因为目标序列已经完全包含

3. **但对于不同序列顺序的情况**:
   - perm = [["子", "丙"], ["甲", "子", "丙"], ["丙", "丁"]]
   - 结合顺序可能导致更长的结果

#### 2.4 路径生成逻辑 (`_generate_path_for_sequence`)

给定符号序列，生成对应坐标路径 (lines 222-253):

```python
path = []
current_row = 0
current_col = random.randint(0, self.size - 1)
path.append((current_row, current_col))

is_horizontal = True
for _ in range(1, len(sequence)):
    if is_horizontal:
        # 水平移动: 选择不同列
        available_cols = [c for c in range(self.size) if c != current_col]
        if available_cols:
            current_col = random.choice(available_cols)
            path.append((current_row, current_col))
        else:
            return None  # 无法继续
    else:
        # 纵向移动: 选择不同行
        available_rows = [r for r in range(self.size) if r != current_row]
        if available_rows:
            current_row = random.choice(available_rows)
            path.append((current_row, current_col))
        else:
            return None

    is_horizontal = not is_horizontal

return path
```

**关键问题**:

1. **路径与序列的关系**:
   - 此函数生成一条随机的交替路径
   - 但生成的路径位置与"最优序列"内容没有任何关联
   - 只是说："给定一个5符号的序列，我需要5个格子来放置"
   - **最后在矩阵上放置时** (line 314): `self.matrix[row][col] = optimal_sequence[i]`

2. **返回None的情况**:
   - 5x5矩阵，第一步选行0，第二步需选不同列（有4种选择）
   - 第三步回到行0，需选不同列（第二步选过除外，有3种选择）
   - 第四步纵向，需选不同行（有4种选择）
   - 第五步回到某行，需选不同列...
   - **理论上5x5足以支持6步的交替路径**（水平移动最多4次，纵向最多4次）
   - **但6x6也是buffer_size=6，而6x6实际能支持更多**

3. **随机性的风险**:
   - 每次调用生成的路径都随机
   - 同一个最优序列可能被放置在完全不同的位置
   - 这与"规划好的可解路径"的假设矛盾

#### 2.5 Fallback机制分析

当50次尝试都失败时，使用fallback路径 (lines 279-301):

```python
def _generate_fallback_path(self) -> List[Tuple[int, int]]:
    """生成备用路径（确保至少有一个解）"""
    path = []
    current_row = 0
    current_col = random.randint(0, self.size - 1)
    path.append((current_row, current_col))

    is_horizontal = True
    for _ in range(1, min(self.buffer_size, 4)):  # 至少生成4步路径
        # 交替移动...

    return path
```

**关键问题**:

1. **只生成4步** (line 287): `min(self.buffer_size, 4)`
   - 对于5x5和6x6都是4步
   - 这意味着fallback路径上的符文最多4个

2. **符文放置** (line 314):
   ```python
   for i, (row, col) in enumerate(path):
       if i < len(optimal_sequence):
           self.matrix[row][col] = optimal_sequence[i]
   ```
   - 对于4步路径，只放置前4个最优序列符号
   - 剩余2个缓冲区空间留给玩家
   - **剩余格子随机填充** (line 323): `random.choice(self.code_chars)`

3. **可解性风险**:
   - Fallback路径仅4步，可能无法包含所有目标序列
   - 剩余格子随机填充，可能"巧合"帮助完成序列，也可能干扰

---

### Part 3: 可解性问题深度分析

#### 3.1 核心可解性问题陈述

**问题**: 生成的谜题是否100%可解？

最关键的问题在**序列生成与路径生成的脱节**:

```
阶段1: _create_optimal_sequence()
   输出: ["甲", "子", "丙", "丁"]（一个符号序列，长度4）

阶段2: _generate_path_for_sequence(["甲", "子", "丙", "丁"])
   输出: [(0,1), (0,3), (2,3), (2,4), (4,4)]（一个坐标路径，随机生成）

阶段3: _place_codes_on_path()
   操作: matrix[0][1]="甲", matrix[0][3]="子", matrix[2][3]="丙", matrix[2][4]="丁", matrix[4][4]=?

关键: 玩家选择的路径与此路径通常不同！
```

#### 3.2 场景A: 完美情况（理想情况）

**假设条件**:
- 最优序列生成成功: "甲子丙丁" (包含所有目标)
- 路径生成成功: [(0,1), (0,3), (2,3), (2,4), (4,4)]
- 符文放置成功: 按序放在这5个格子上

**玩家游戏**:
- 玩家不知道预设路径，自己探索
- 玩家也选择了5步: (0,1), (0,3), (2,3), (2,4), (4,4)
- 玩家得到: "甲" "子" "丙" "丁" "?" → "甲子丙丁" (加上可能的随机符号)
- 所有目标序列被识别 ✓

**问题**: 概率有多高？
- 第一步: 必须是行0，有size种选择，其中1个是目标列
  概率 = 1/size = 1/5 或 1/6
- 第二步: 必须选目标列，有size-1种可选列，其中1个是目标
  概率 = 1/(size-1) = 1/4 或 1/5
- ...
- **总概率 < 0.2%！**

玩家更可能选择其他路径。

#### 3.3 场景B: 玩家选择不同的路径

**假设条件**:
- 预设路径A: [(0,1), (0,3), (2,3), (2,4), (4,4)] 放置"甲子丙丁"
- 玩家选择路径B: [(0,2), (0,4), (3,4), (3,1), (1,1)] 完全不同的5步

**关键问题**: 路径B上的符文是什么？

答案: **随机填充的符号！** (line 323)

**详细分析**:

1. 路径A(预设): (0,1)=甲, (0,3)=子, (2,3)=丙, (2,4)=丁, 其他随机
2. 路径B(玩家): (0,2), (0,4), (3,4), (3,1), (1,1)
3. 这5个格子中:
   - (0,2): 随机符号，可能是任意22个中的一个
   - (0,4): 随机符号
   - (3,4): 随机符号
   - (3,1): 随机符号
   - (1,1): 随机符号

4. 玩家得到5个随机符号的序列，例如"乙丙辛癸巳"

**可解性评估**:
- 玩家需要"甲子丙丁"出现在"乙丙辛癸巳"中
- 但这5个格子都是随机填充的
- **概率基本为0！**

**结论**: 玩家如果不按预设路径选择，几乎无法完成。

#### 3.4 场景C: Fallback路径的可解性

当主路径生成失败(50次都失败)时:

1. 使用fallback路径(仅4步)
2. 在这4步上放置"前4个最优序列符号"
3. 剩余2步留给玩家自由探索

**例子**:
- 最优序列: ["甲", "子", "丙", "丁", "戊"]（5个，但超过6步上限...实际会截断)
- 实际截断: ["甲", "子", "丙", "丁"]（4个）
- Fallback路径: 4步
- 放置: matrix[...] = "甲", "子", "丙", "丁"
- 剩余2步: 随机填充

**分析**:
- 玩家仍需找到预设的4步路径 (概率同样很低)
- 即使找到，剩余2步的随机符号可能破坏序列

**具体例子** (5x5模式):
- 目标: ["甲", "子", "丙"], ["子", "丙"], ["丙", "丁"]
- Fallback生成的最优序列: 可能只能包含部分目标
- 玩家随机路径: 概率极低能匹配

#### 3.5 符文重复与干扰问题

**符文池**:
- 22个天干地支符号: ["甲", "乙", ..., "亥"]
- 5x5矩阵: 25格
- 6x6矩阵: 36格

**符号重复情况**:
- 5x5: 至少3个符号会重复(22 < 25)
- 6x6: 至少14个符号会重复(22 < 36)

**对可解性的影响**:
- 假设目标是["甲", "子", "丙"]
- 如果矩阵中有多个"甲"，玩家可能误选到错误的"甲"
- 但由于行列交替的约束，这种误选会导致路径不同
- 无法验证这条随机路径上是否真的包含目标序列

**例子**:
```
矩阵示意 (仅相关格子):
(0,1)=甲  (0,3)=乙  (0,5)=丙
(2,1)=甲  (2,3)=子  (2,5)=甲
(4,1)=子  (4,3)=丙  (4,5)=丁

玩家选择: (0,1)甲→(0,3)乙→(2,3)子→(2,5)甲
结果: "甲乙子甲"
目标"甲子丙"在"甲乙子甲"中吗? NO! (因为有"乙"在中间)

如果玩家选择: (0,1)甲→(0,5)丙→(2,5)甲→(2,3)子
但这违反了交替规则! (0,1)水平移动应该选不同列，但(0,5)在同一行) ✓
(0,5)纵向移动选行2 ✓
(2,5)水平移动选列... 但(2,3)不在行2(2,5)的纵向... ✗ 违反

实际上由于交替约束，玩家很难随意组合符号。
```

---

### Part 4: 算法缺陷识别

#### 缺陷1: "最优序列"不保证包含所有目标序列

**问题代码**: lines 114-135 `_create_optimal_sequence`

**缺陷分析**:
1. 排列组合法只尝试6种(line 141)，对于6x6的4个序列可能遗漏
2. 贪心算法不保证全覆盖(lines 178-210)

**实际案例** (6x6):
- 目标: ["甲", "子", "丙", "丁"], ["子", "丙"], ["丙", "丁"], ["丁", "戊"]
- 4! = 24种排列，仅尝试6种
- 最坏情况: 前6种排列都无法包含所有序列
- 贪心算法可能生成: ["甲", "子", "丙", "丁"] (仅包含部分目标)

**风险**: 即使生成了"最优序列"，也不保证玩家能完成所有目标。

#### 缺陷2: 路径生成与最优序列脱节

**问题代码**: lines 222-253 `_generate_path_for_sequence`

**根本原因**:
- `_generate_path_for_sequence()`只看序列长度
- 完全随机生成坐标路径，与最优序列内容无关
- 放置时简单对应: matrix[path[i]] = optimal_sequence[i]

**后果**:
```python
optimal_sequence = ["甲", "子", "丙", "丁"]  # 符号
path = [(0,1), (0,3), (2,3), (2,4)]  # 随机坐标

# 放置
matrix[0][1] = "甲"
matrix[0][3] = "子"
matrix[2][3] = "丙"
matrix[2][4] = "丁"

# 但玩家不知道这个映射！
# 玩家选择的路径多半不同，得到的符号就不是"甲子丙丁"
```

**数学表述**:
- 设生成的预设路径为P_gen(随机)
- 玩家选择的路径为P_player(玩家探索)
- 只有P_gen == P_player时，玩家才能得到预期的符号序列
- 概率 P(P_gen == P_player) 极低 (< 0.2%，见场景A分析)

#### 缺陷3: Fallback路径仅4步，无法覆盖所有目标

**问题代码**: lines 279-301, line 287 `min(self.buffer_size, 4)`

**分析**:
1. Fallback仅生成4步，但目标序列可能需要5-6步才能全覆盖
2. 5x5的目标序列: "甲"(1) + "子"(1) + "丙"(1) + "丁"(1) = 4个不同符号，需要4步
   - 但要同时包含["甲", "子", "丙"]和["丙", "丁"]和["子", "丙"]
   - 最优序列至少需要"甲子丙丁"(4个)，恰好4步
3. 6x6的目标序列: ["甲", "子", "丙", "丁"], ["子", "丙"], ["丙", "丁"], ["丁", "戊"]
   - 最优序列可能需要"甲子丙丁戊"(5个)，但Fallback仅4步
   - **无法覆盖所有目标！**

**问题级别**: P0级，直接导致Fallback情况下无法完成所有目标

#### 缺陷4: 序列覆盖度计算重复调用(性能问题)

**问题代码**: lines 255-277 `_calculate_sequence_coverage`

```python
def _calculate_sequence_coverage(self, path: List[Tuple[int, int]]) -> int:
    ...
    optimal_sequence = self._create_optimal_sequence()  # 每次都调用! (line 262)
    ...
```

**分析**:
- `_generate_main_solution_path()`循环50次(line 90)
- 每次调用`_calculate_sequence_coverage()`(line 93)
- 每次又调用`_create_optimal_sequence()`(line 262)
- `_create_optimal_sequence()`内部尝试排列组合(line 123)
- **结果**: 50 × (排列组合 + 贪心) × 重复计算，性能O(n^3)

**改进**: 应缓存`_create_optimal_sequence()`结果，或在外部计算一次。

#### 缺陷5: 随机填充无约束，可能破坏可解性

**问题代码**: lines 318-323 `_fill_remaining_cells`

```python
def _fill_remaining_cells(self):
    for row in range(self.size):
        for col in range(self.size):
            if self.matrix[row][col] == "":
                self.matrix[row][col] = random.choice(self.code_chars)
```

**问题**:
1. 完全随机填充，不考虑已有符文
2. 可能在预设路径附近放置相同符号，导致玩家困惑
3. 如果Fallback路径只有4格填充，剩余(22或32)格都是随机的
   - 玩家的6步路径中，至少2步会落在随机填充的格子上
   - 这2步的符号完全不可控

**例子**:
```
预设路径A: (0,1)=甲, (0,3)=子, (2,3)=丙, (2,4)=丁, 其他随机
玩家路径B: (0,2)=随机?, (0,4)=随机?, (3,4)=随机?, (3,1)=随机?, (1,1)=随机?

5个随机符号的任意组合，几乎不可能包含目标序列。
```

#### 缺陷6: 难度等级参数与目标序列耦合，可扩展性差

**问题代码**: lines 481-483, lines 63-82

```python
# 命令处理
if args_text in ["开始", "困难"]:
    size = 5 if args_text == "开始" else 6
    cost = 100 if size == 5 else 150

# 在_generate_target_sequences中:
if self.size == 5:
    sequences = [...]  # 硬编码3个
else:
    sequences = [...]  # 硬编码4个
```

**问题**:
- 增加难度需同时修改size和目标序列定义
- 无法独立配置参数
- 符文池全局共享，无法按难度变化

---

### Part 5: 修复建议与方向

#### 根本修复方向: 分离"逻辑设计"与"随机生成"

当前架构的核心缺陷是:
1. **预设路径是随机生成的** (line 222-253)
2. **玩家路径也是随机探索的**
3. **两条随机路径匹配的概率极低**

**修复策略**:

##### 方案A: "约束随机生成"
- 生成预设路径后，验证玩家确实能找到
- 改进: 不是生成随机路径，而是生成"保证可达"的路径

##### 方案B: "多条预设路径"
- 不仅预设1条路径，而是预设3-5条可行路径
- 这些路径都能完成所有目标序列
- 玩家选择任意一条都能赢

##### 方案C: "符文多重布局"
- 对于序列["甲", "子", "丙"]，不仅在预设路径上放置
- 还在其他位置放置"甲"、"子"、"丙"，形成多条可能的完成路径
- 提高玩家碰到的概率

##### 方案D: "降低行列交替的严格性"
- 当前完全严格交替，限制了路径多样性
- 改为: 每3步必须改变一次方向(不是必须每步)
- 提供更多自由度，增加玩家能自己发现的路径

#### 具体优先级建议

**P0 (立即修复 - 确保可解性)**:
1. 验证Fallback路径的可解性
   - 当前Fallback仅4步，6x6模式可能无法包含所有目标
   - 改为: 动态调整Fallback步数，确保至少包含N%的目标
2. 改进排列组合的覆盖率
   - 6x6时从6种扩展到24种(所有排列)

**P1 (第二阶段 - 提升可发现性)**:
1. 实现"多条预设路径"机制
   - 生成3条不同的主路径
   - 都能完成所有目标
   - 提高玩家碰到的概率
2. 添加"路径提示"系统
   - 完成1-2个目标后，给玩家微弱的方向提示
   - 不直接告诉位置，但给出"应该往某方向走"

**P2 (优化体验)**:
1. 配置化目标序列与符文池
2. 数据库持久化游戏状态

---

## Relations (关系映射)

### 代码调用链
```
handle_array_breaking() [命令处理]
└─ ArrayBreakingGame.__init__()
   ├─ _generate_solvable_puzzle()
   │  ├─ _generate_target_sequences() → 硬编码目标
   │  ├─ _generate_main_solution_path()
   │  │  ├─ 循环50次 _try_generate_solution()
   │  │  │  ├─ _create_optimal_sequence() → [核心缺陷1]
   │  │  │  │  ├─ _get_sequence_permutations() → 仅6种 [缺陷1]
   │  │  │  │  ├─ _combine_sequences() → 重叠连接
   │  │  │  │  └─ _greedy_sequence_build() → 贪心
   │  │  │  └─ _generate_path_for_sequence() → [核心缺陷2]
   │  │  ├─ _calculate_sequence_coverage() → [缺陷4]
   │  │  │  └─ _create_optimal_sequence() → 重复调用!
   │  │  └─ _generate_fallback_path() → [缺陷3]
   │  └─ _fill_remaining_cells() → [缺陷5]
   ├─ make_move(row, col) [玩家移动]
   │  └─ _check_completed_sequences() → 子串匹配判定
   └─ calculate_reward() → 计算奖励
```

### 可解性链路
```
生成预设路径 → 放置最优序列符号 → 玩家探索路径 → 匹配检查
   (随机)                              (随机)    (概率<<1%)
     ↓                                   ↓
  可能性极低 ← → 完全脱节 ← → 基本无法匹配
```

### 符号库与矩阵的关系
```
code_chars (22个) ─→ 5x5矩阵 (25格)
                │
                └─ 必然重复 (3+格)

                ─→ 6x6矩阵 (36格)
                │
                └─ 必然重复 (14+格)

随机填充 (22格或32格) ─→ 低概率包含目标序列
```

---

## Conclusions (关键发现)

### 核心结论

**用户反馈"生成的序列有问题"的根本原因**:

序列生成与路径生成在架构上脱节，导致:
1. 预设的"最优序列"符号被放置在随机生成的路径上
2. 玩家通过自己探索的(不同)随机路径
3. 两条路径匹配概率极低(<0.2%)
4. 玩家几乎不可能通过自己的探索得到预设的符号序列
5. 即使Fallback路径也因仅4步而无法保证覆盖所有目标(特别是6x6)

### 可解性评估

| 场景 | 5x5标准 | 6x6困难 | 评估 |
|------|--------|--------|------|
| **完美路径** (玩家选预设路径) | <0.2% | <0.1% | 近乎不可能 |
| **任意路径** (玩家随机探索) | 极低 | 极低 | 除非巧合 |
| **Fallback路径** (无法生成主路径时) | 可勉强解决4步 | 无法覆盖所有 | 高风险 |
| **剩余随机符号** (玩家超过Fallback步数) | 干扰大 | 干扰大 | 不可控 |

### 为什么看起来"有问题"

用户的感受可能来自:
1. **多次游戏难以完成所有目标** (概率底)
2. **看似应该能完成，但没有完成** (算法有缺陷)
3. **游戏的"可解性"不像是精心设计的** (因为确实是随机生成的)

### 修复的优先级

**最紧急的修复** (P0):
1. 确保Fallback路径也能100%包含所有目标序列
2. 改进排列组合覆盖，从6扩展到24(6x6)

**提升体验的修复** (P1):
1. 实现多条预设路径，提高玩家的可发现性
2. 添加路径提示机制

**技术债清理** (P2):
1. 配置化目标序列和符文池
2. 优化性能问题(重复调用_create_optimal_sequence)

