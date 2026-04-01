# 宠物定制人设 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许玩家花费50诡烛，用模糊自然语言描述来定制宠物人设，后台AI自动优化为完整提示词并覆盖原默认人设；可免费重置回默认。

**Architecture:** 新建 `personality_customization_service.py` 负责AI调用与诡烛扣除，与现有 `PetDialogueService` 解耦。`PetInstance` 新增 `custom_personality` 文本字段存储AI生成结果。对话时检测该字段，有则注入自定义人设、替换默认人设段落；PetDialogueService 同时重构出 `_build_state_context()` 方法以复用状态上下文。

**Tech Stack:** SQLAlchemy 2.0 Mapped字段、`call_ai_with_fallback`（ai_guide.py）、NoneBot2 on_command

---

## 文件地图

| 操作 | 文件 | 变更内容 |
|------|------|----------|
| 修改 | `plugins/xiuxian_game/models/pet_instance.py` | 新增 `custom_personality` Text字段 |
| 修改 | `plugins/xiuxian_game/models/auto_migrate.py` | 新增迁移条目 |
| **新建** | `plugins/xiuxian_game/pet/personality_customization_service.py` | AI优化+诡烛扣除+存储逻辑 |
| 修改 | `plugins/xiuxian_game/pet/pet_dialogue_service.py` | 提取 `_build_state_context()`，注入自定义人设 |
| 修改 | `plugins/xiuxian_game/pet/commands.py` | 新增 `【定制人设】` 和 `【重置人设】` 命令 |
| 修改 | `plugins/xiuxian_game/player/help.py` | 更新宠物系统帮助文本 |
| 修改 | `plugins/xiuxian_game/data/knowledge/pet_system_help.yaml` | 同步知识库 |

---

## Task 1: 数据模型 — 新增 custom_personality 字段

**Files:**
- Modify: `plugins/xiuxian_game/models/pet_instance.py`
- Modify: `plugins/xiuxian_game/models/auto_migrate.py`

- [ ] **Step 1: 在 PetInstance 模型中添加字段**

在 `pet_instance.py` 的 `gift_last_date` 字段后面加入：

```python
# 定制人设（AI生成的完整人设描述文本，None表示使用默认）
custom_personality: Mapped[str | None] = mapped_column(
    Text, nullable=True, comment="玩家定制的AI人设描述文本"
)
```

注意：需要在文件顶部 import 中加上 `Text`：
```python
from sqlalchemy import String, Integer, Float, DateTime, Boolean, ForeignKey, Index, JSON, Text
```

- [ ] **Step 2: 在 auto_migrate.py 中添加迁移条目**

在 `pet_instance` 字典的 `gift_last_date` 行后面加入：

```python
"custom_personality": "TEXT NULL COMMENT '玩家定制的AI人设描述文本'",
```

- [ ] **Step 3: 验证**

重启 Bot，观察启动日志确认 `custom_personality` 字段被自动添加到 `pet_instance` 表，无报错。

---

## Task 2: 新建 personality_customization_service.py

**Files:**
- Create: `plugins/xiuxian_game/pet/personality_customization_service.py`

- [ ] **Step 1: 创建服务文件**

```python
"""宠物定制人设服务

允许玩家花费诡烛，通过自然语言描述定制宠物人设。
AI将模糊描述优化为完整的角色人设段落并覆盖默认人设。
"""
from nonebot import logger
from ..ai_guide import call_ai_with_fallback
from ..infrastructure.uow.unit_of_work import UnitOfWork

CUSTOM_PERSONALITY_PRICE = 50  # 诡烛

# 禁止词（防止滥用）
_FORBIDDEN_WORDS = ["管理", "系统", "官方", "GM", "色情", "政治", "违禁"]

# AI优化的元提示词模板
_META_PROMPT = """你是一名专业的AI角色设计师，专门为修仙世界的宠物伙伴设计人设。

宠物信息：
- 种族：{beast_name}（{beast_description}）
- 昵称：{pet_nickname}
- 化形形态：{gender_desc}

玩家的人设需求："{player_description}"

请根据玩家的描述，为这只宠物设计完整的角色人设。要求：
1. 保持与宠物种族特性的一致性（{beast_name}的本质特征不能丢失）
2. 明确体现：性格特质、说话方式和自称、口头禅或常用词汇、行为习惯
3. 符合修仙世界风格，可以有仙气、鬼气、野性等气质
4. 人设描述要自然连贯，像一段角色简介
5. 字数控制在120-200字之间

直接输出人设描述文本，不要加任何前缀、解释或标题。"""


async def generate_custom_personality(
    player_description: str,
    pet_nickname: str,
    beast_name: str,
    beast_description: str,
    transform_gender: str,
    transform_name: str,
) -> str:
    """
    调用AI将玩家的模糊描述优化为完整人设段落。

    Returns:
        AI生成的人设描述文本

    Raises:
        ValueError: 描述含禁止词或AI调用失败
    """
    # 基础内容过滤
    for word in _FORBIDDEN_WORDS:
        if word in player_description:
            raise ValueError(f"描述中包含禁止词：{word}")

    gender_desc = f"{transform_name}（{'男性' if transform_gender == 'male' else '女性'}形态）" if transform_name else "未化形"

    prompt = _META_PROMPT.format(
        beast_name=beast_name,
        beast_description=beast_description,
        pet_nickname=pet_nickname,
        gender_desc=gender_desc,
        player_description=player_description,
    )

    messages = [
        {"role": "system", "content": "你是一名专业的AI角色设计师。"},
        {"role": "user", "content": prompt},
    ]

    result = await call_ai_with_fallback(messages)
    choices = result.get("choices", [])
    if not choices:
        raise ValueError("AI未返回有效结果")

    personality_text = choices[0].get("message", {}).get("content", "").strip()
    if len(personality_text) < 20:
        raise ValueError("AI生成的人设过短，请重新尝试")

    return personality_text


async def customize_pet_personality(
    uow: UnitOfWork,
    player_id: str,
    description: str,
) -> tuple[bool, str]:
    """
    为当前伙伴定制人设：检查诡烛 → 调用AI → 扣费 → 保存。

    Returns:
        (success, message)
    """
    if not description:
        return False, "请描述你想要的人设，例如：定制人设 体贴温柔、说话轻声细语的"

    if len(description) > 100:
        return False, "描述不能超过100字"

    # 获取玩家
    player = await uow.players.get_by_id(player_id)
    if not player:
        return False, "玩家不存在"

    # 检查诡烛
    if player.gui_zhu < CUSTOM_PERSONALITY_PRICE:
        return False, (
            f"诡烛不足！定制人设需要 {CUSTOM_PERSONALITY_PRICE} 诡烛\n"
            f"当前持有：{player.gui_zhu} 诡烛"
        )

    # 获取当前伙伴
    pet = await uow.pets.get_active_pet(player_id)
    if not pet:
        return False, "你还没有激活的伙伴诡兽"

    if not pet.is_transformed:
        return False, "宠物尚未化形，无法定制人设\n化形后（需Lv.50 + 好感度100）才能使用此功能"

    # 获取宠物配置
    from .config import PetConfigManager
    pet_config = PetConfigManager()
    beast = pet_config.get_beast(pet.beast_id)
    if not beast:
        return False, "宠物配置异常"

    transform_name = pet_config.get_transform_name(pet.beast_id, pet.transform_gender)

    # 调用AI生成人设
    try:
        personality_text = await generate_custom_personality(
            player_description=description,
            pet_nickname=pet.nickname,
            beast_name=beast.name,
            beast_description=beast.description,
            transform_gender=pet.transform_gender or "",
            transform_name=transform_name,
        )
    except ValueError as e:
        return False, f"人设生成失败：{e}"
    except Exception as e:
        logger.error(f"定制人设AI调用失败: {e}", exc_info=True)
        return False, "AI服务暂时不可用，请稍后重试"

    # 扣除诡烛并更新玩家数据
    player.gui_zhu -= CUSTOM_PERSONALITY_PRICE
    await uow.players.update(player)

    # 保存人设
    pet.custom_personality = personality_text
    await uow.pets.update(pet)

    return True, (
        f"✨ 人设定制成功！消耗 {CUSTOM_PERSONALITY_PRICE} 诡烛\n"
        f"━━━━━━━━━━━━━\n"
        f"🔮 {pet.nickname} 的新人设：\n"
        f"{personality_text}\n"
        f"━━━━━━━━━━━━━\n"
        f"💡 如需恢复默认人设，发送【重置人设】（免费）\n"
        f"🔮 剩余诡烛：{player.gui_zhu}"
    )


async def reset_pet_personality(
    uow: UnitOfWork,
    player_id: str,
) -> tuple[bool, str]:
    """
    免费重置宠物人设为默认。

    Returns:
        (success, message)
    """
    pet = await uow.pets.get_active_pet(player_id)
    if not pet:
        return False, "你还没有激活的伙伴诡兽"

    if not pet.custom_personality:
        return False, f"{pet.nickname} 当前使用的就是默认人设，无需重置"

    pet.custom_personality = None
    await uow.pets.update(pet)

    return True, f"✅ {pet.nickname} 的人设已恢复默认"
```

- [ ] **Step 2: 手动检查**

确认文件创建无语法错误（可在终端运行 `python -c "import ast; ast.parse(open('plugins/xiuxian_game/pet/personality_customization_service.py').read()); print('OK')`）。

---

## Task 3: 重构 PetDialogueService — 提取 _build_state_context 并注入自定义人设

**Files:**
- Modify: `plugins/xiuxian_game/pet/pet_dialogue_service.py`

- [ ] **Step 1: 提取 `_build_state_context()` 方法**

将 `_build_pet_background()` 中除 `personality_data.background` 以外的状态部分提取为独立方法（避免自定义人设路径重复代码）：

```python
def _build_state_context(self, pet, player) -> str:
    """构建宠物当前状态上下文（好感、心情、饥饿、形态、饰品等）"""
    affection_name = self.config.get_affection_level_name(pet.affection)
    mood_desc = self._get_mood_desc(pet.mood)
    hunger_desc = "饥饿" if pet.hunger < 20 else ("微饿" if pet.hunger < 50 else "饱足")
    form = "人形" if pet.is_transformed else "兽形"
    affection_hint = self._get_affection_behavior_hint(pet.affection)

    gender_desc = ""
    if pet.is_transformed and pet.transform_gender:
        transform_name = self.config.get_transform_name(pet.beast_id, pet.transform_gender)
        gender_cn = "男性" if pet.transform_gender == "male" else "女性"
        gender_desc = f"你的化形是{gender_cn}形态——{transform_name}。你必须严格按照{gender_cn}的身份说话和自称，不要使用其他性别的自称或语气。"

    ctx = (
        f"{gender_desc}"
        f"你的主人叫{player.nickname}，是一位{player.level}级的修仙者。"
        f"你和主人的关系是【{affection_name}】（好感度{pet.affection}）。"
        f"{affection_hint}"
        f"你现在的心情{mood_desc}，{hunger_desc}状态。"
        f"你目前是{form}态。"
    )

    if pet.is_guarding:
        ctx += "你正在灵田守田值班。"

    if pet.accessories:
        acc_names = []
        for acc_id in pet.accessories.values():
            acc = self.config.get_accessory(acc_id)
            if acc:
                acc_names.append(acc.name)
        if acc_names:
            ctx += f"你身上穿戴着{'、'.join(acc_names)}。"

    return ctx
```

- [ ] **Step 2: 简化 `_build_pet_background()` 调用 `_build_state_context()`**

`beast` 参数保留以维持调用侧兼容，但函数体已不需要它：

```python
def _build_pet_background(self, pet, beast, personality_data, player) -> str:
    """构建宠物背景上下文（默认人设路径）"""
    return f"{personality_data.background}\n\n{self._build_state_context(pet, player)}"
```

- [ ] **Step 3: 在 `chat()` 中根据 custom_personality 选择人设路径**

找到 `chat()` 方法中构建 `personality` 的代码块，替换为：

```python
# 根据是否有定制人设选择不同的PersonalityTemplate构建路径
if pet.custom_personality:
    # 自定义人设：用玩家定制内容替换background+role，保留状态上下文
    personality = PersonalityTemplate(
        name=pet.nickname,
        role="",
        pronouns=[],
        speech_patterns=[],
        key_words=personality_data.key_words,
        background=pet.custom_personality + "\n\n" + self._build_state_context(pet, player),
        behavioral_rules=[],
    )
else:
    # 默认人设：使用种族配置
    personality = PersonalityTemplate(
        name=pet.nickname,
        role=personality_data.role,
        pronouns=personality_data.pronouns,
        speech_patterns=personality_data.speech_patterns,
        key_words=personality_data.key_words,
        background=self._build_pet_background(pet, beast, personality_data, player),
        behavioral_rules=personality_data.behavioral_rules,
    )
```

- [ ] **Step 4: 验证重构没有破坏现有对话及自定义路径**

启动 Bot：
1. 测试 `【对话 你好】`，确认**默认人设路径**正常返回（role/pronouns 非空）
2. 用管理员命令临时给宠物设置 `custom_personality`，再测试 `【对话 你好】`，确认**自定义路径** prompt 拼接正常、AI 回复风格符合定制内容（role/pronouns 为空时 AIDialogueService 的 prompt 会跳过这些字段，不影响结果）

---

## Task 4: 新增命令 — 定制人设 / 重置人设

**Files:**
- Modify: `plugins/xiuxian_game/pet/commands.py`

- [ ] **Step 1: 在文件顶部导入新服务**

在现有 import 区找到 `from .pet_dialogue_service import PetDialogueService` 行附近加入：

```python
from .personality_customization_service import customize_pet_personality, reset_pet_personality
```

- [ ] **Step 2: 注册并实现 `【定制人设】` 命令**

在 `commands.py` 末尾（或对话命令附近）添加：

```python
# ==================== 定制人设 ====================
customize_personality_cmd = on_command("定制人设", priority=5, block=True)


@customize_personality_cmd.handle()
async def handle_customize_personality(event: MessageEvent, args: Message = CommandArg()):
    """【定制人设 描述】- 花费50诡烛定制宠物人设（需已化形）"""
    description = args.extract_plain_text().strip()
    if not description:
        await customize_personality_cmd.finish(
            "用法：定制人设 <你想要的人设描述>\n"
            "例如：定制人设 傲娇毒舌，表面嫌弃主人实则超在意\n"
            "💰 费用：50诡烛/次（可免费重置）"
        )

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await customize_personality_cmd.finish("请先创建角色")

        success, msg = await customize_pet_personality(uow, player.id, description)
        await customize_personality_cmd.finish(msg)
```

- [ ] **Step 3: 注册并实现 `【重置人设】` 命令**

```python
# ==================== 重置人设 ====================
reset_personality_cmd = on_command("重置人设", priority=5, block=True)


@reset_personality_cmd.handle()
async def handle_reset_personality(event: MessageEvent, args: Message = CommandArg()):
    """【重置人设】- 免费恢复宠物默认人设"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await reset_personality_cmd.finish("请先创建角色")

        success, msg = await reset_pet_personality(uow, player.id)
        await reset_personality_cmd.finish(msg)
```

- [ ] **Step 4: 确认 UnitOfWork 和 AsyncSessionLocal 已在文件顶部导入**

检查 `commands.py` 顶部，确保有：
```python
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
```
如缺少则补充。

---

## Task 5: 更新帮助文档

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`
- Modify: `plugins/xiuxian_game/data/knowledge/pet_system_help.yaml`

- [ ] **Step 1: 更新 help.py 中宠物系统的帮助文本**

在 help.py 中找到宠物相关的帮助内容，加入新命令说明（具体位置取决于 help.py 的组织方式，搜索"对话"或"化形"附近添加）：

```
【定制人设 描述】 花费50诡烛，用自然语言定制宠物人设（AI自动优化，需已化形）
【重置人设】 免费恢复宠物默认人设
```

- [ ] **Step 2: 更新 pet_system_help.yaml**

在 `keywords` 列表中添加：
```yaml
  - 定制人设
  - 重置人设
  - 宠物人设
  - 自定义人设
```

在 `body` 的 `💬 互动与对话` 章节下，`【对话 内容】` 行后面追加（注意 YAML 多行文本中保持两个空格缩进）：

```yaml
  【定制人设 描述】 花费50诡烛，AI优化你的描述为完整人设（需已化形）
  【重置人设】 免费恢复默认人设
```

追加后该章节看起来像：
```
  💬 互动与对话：
  【摸摸】/【摸头】/【玩耍】/【抱抱】 互动（+好感/心情）
  【对话 内容】 与宠物AI对话
  【定制人设 描述】 花费50诡烛，AI优化你的描述为完整人设（需已化形）
  【重置人设】 免费恢复默认人设
```

- [ ] **Step 3: 整体提交**

```bash
git add plugins/xiuxian_game/models/pet_instance.py \
        plugins/xiuxian_game/models/auto_migrate.py \
        plugins/xiuxian_game/pet/personality_customization_service.py \
        plugins/xiuxian_game/pet/pet_dialogue_service.py \
        plugins/xiuxian_game/pet/commands.py \
        plugins/xiuxian_game/player/help.py \
        plugins/xiuxian_game/data/knowledge/pet_system_help.yaml
git commit -m "feat(pet): 宠物定制人设功能，50诡烛/次，AI优化描述为完整人设"
```

---

## 验收检查

- [ ] `【定制人设 傲娇毒舌】` → 诡烛不足时提示余额；足够时显示AI生成人设预览并扣费
- [ ] 玩家没有宠物时 → 提示"还没有激活的伙伴诡兽"
- [ ] 定制后 `【对话 你好】` → 宠物按新人设回复
- [ ] `【重置人设】` → 确认重置，之后对话恢复默认风格
- [ ] 含禁止词的描述（如"色情"）→ 被拦截并提示
- [ ] 描述超过100字 → 提示字数限制
- [ ] 未化形宠物定制 → 提示需先化形
