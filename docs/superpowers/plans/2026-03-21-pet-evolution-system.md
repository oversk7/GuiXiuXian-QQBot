# 宠物进化系统 & 化形性别自选 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许任何宠物通过进化提升稀有度（⚪→🟢→🔵→🟣→🟠），消除外观偏好的属性惩罚；化形时支持选择性别并配置对应 AI 人设。

**Architecture:** 在 PetInstance 模型新增 `evolved_rarity` 和 `transform_gender` 字段。进化逻辑在 PetService 中实现，通过重算 `bonus_*` 属性补齐差值。新增「诡兽精魄」掉落物品，复用诡域宝箱掉落机制。化形命令扩展为接受性别参数，人设 YAML 新增 `human_form_male` 配置。

**Tech Stack:** Python 3.11 / SQLAlchemy 2.0 / NoneBot2 / YAML 配置

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| Modify | `plugins/xiuxian_game/models/pet_instance.py` | 新增 evolved_rarity, transform_gender 字段 |
| Modify | `plugins/xiuxian_game/models/auto_migrate.py` | 注册自动迁移字段 |
| Modify | `plugins/xiuxian_game/data/pet_config.yaml` | 新增 evolution 配置段 |
| Modify | `plugins/xiuxian_game/data/items.yaml` | 新增「诡兽精魄」物品定义 |
| Modify | `plugins/xiuxian_game/data/pet_personalities.yaml` | 新增 human_form_male 人设 |
| Modify | `plugins/xiuxian_game/pet/config.py` | 加载进化配置、get_personality 支持性别 |
| Modify | `plugins/xiuxian_game/pet/pet_service.py` | 新增 evolve_pet()、修改 transform()、修改 _apply_level_up() |
| Modify | `plugins/xiuxian_game/pet/commands.py` | 新增「进化宠物」命令、修改「化形」命令 |
| Modify | `plugins/xiuxian_game/world/dungeon_battle.py` | 宝箱掉落诡兽精魄 |
| Modify | `plugins/xiuxian_game/player/help.py` | 更新宠物系统帮助 |
| Modify | `plugins/xiuxian_game/data/knowledge/pet_system_help.yaml` | 同步 AI 知识库 |

---

### Task 1: 数据模型 — PetInstance 新增字段

**Files:**
- Modify: `plugins/xiuxian_game/models/pet_instance.py`
- Modify: `plugins/xiuxian_game/models/auto_migrate.py`

- [ ] **Step 1: PetInstance 模型新增字段**

在 `PetInstance` 类中，`is_transformed` 字段后面新增两个字段：

```python
evolved_rarity: Mapped[str] = mapped_column(
    String(16), default="", server_default="",
    comment="进化后的稀有度(空=使用种族默认)"
)
transform_gender: Mapped[str] = mapped_column(
    String(8), default="", server_default="",
    comment="化形性别(male/female, 空=未选择)"
)
```

- [ ] **Step 2: 注册自动迁移**

在 `auto_migrate.py` 的 `REQUIRED_FIELDS` 中添加：

```python
"pet_instance": {
    "evolved_rarity": "VARCHAR(16) DEFAULT '' COMMENT '进化后的稀有度'",
    "transform_gender": "VARCHAR(8) DEFAULT '' COMMENT '化形性别'",
},
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/models/pet_instance.py plugins/xiuxian_game/models/auto_migrate.py
git commit -m "feat(pet): PetInstance 新增 evolved_rarity 和 transform_gender 字段"
```

---

### Task 2: 配置 — 进化表 & 诡兽精魄物品

**Files:**
- Modify: `plugins/xiuxian_game/data/pet_config.yaml`
- Modify: `plugins/xiuxian_game/data/items.yaml`

- [ ] **Step 1: pet_config.yaml 新增进化配置段**

在 `affection_levels` 后面追加：

```yaml
# 宠物进化配置
# rarity_order 定义稀有度升级路径
rarity_order: ["white", "green", "blue", "purple", "orange"]

evolution:
  white_to_green:
    min_level: 10
    cost_item: "pet_evolution_stone"
    cost_quantity: 3
    cost_resentment: 200000
  green_to_blue:
    min_level: 20
    cost_item: "pet_evolution_stone"
    cost_quantity: 5
    cost_resentment: 500000
  blue_to_purple:
    min_level: 35
    cost_item: "pet_evolution_stone"
    cost_quantity: 8
    cost_resentment: 1200000
  purple_to_orange:
    min_level: 50
    cost_item: "pet_evolution_stone"
    cost_quantity: 12
    cost_resentment: 3000000
```

- [ ] **Step 2: items.yaml 新增诡兽精魄**

在 items.yaml 的 materials 区块中添加（遵循现有物品格式）：

```yaml
pet_evolution_stone:
  name: "诡兽精魄"
  type: MATERIAL
  rarity: purple
  description: "蕴含诡兽本源之力的结晶，可用于宠物进化突破"
  price: 0
  stackable: true
  max_stack: 99
  tags: ["pet", "evolution"]
```

> **注意**：查看 items.yaml 中现有 MATERIAL 物品的格式，确保字段名和缩进完全一致。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/data/pet_config.yaml plugins/xiuxian_game/data/items.yaml
git commit -m "feat(pet): 新增进化配置表和诡兽精魄物品定义"
```

---

### Task 3: 配置加载 — PetConfigManager 支持进化查询

**Files:**
- Modify: `plugins/xiuxian_game/pet/config.py`

- [ ] **Step 1: 加载进化配置**

在 `PetConfigManager._load_all()` 方法中，`self.accessory_slots` 赋值之后添加：

```python
# 加载进化配置
self.rarity_order: List[str] = config.get("rarity_order", ["white", "green", "blue", "purple", "orange"])
self._evolution: Dict[str, dict] = config.get("evolution", {})
```

- [ ] **Step 2: 新增进化查询方法**

在 `PetConfigManager` 类末尾添加：

```python
def get_next_rarity(self, current_rarity: str) -> Optional[str]:
    """获取下一个稀有度，已是最高则返回 None"""
    try:
        idx = self.rarity_order.index(current_rarity)
        if idx + 1 < len(self.rarity_order):
            return self.rarity_order[idx + 1]
    except ValueError:
        pass
    return None

def get_evolution_config(self, from_rarity: str, to_rarity: str) -> Optional[dict]:
    """获取进化配置"""
    key = f"{from_rarity}_to_{to_rarity}"
    return self._evolution.get(key)

RARITY_CN = {
    "white": "普通", "green": "优秀", "blue": "稀有",
    "purple": "史诗", "orange": "传说",
}

RARITY_EMOJI = {
    "white": "⚪", "green": "🟢", "blue": "🔵",
    "purple": "🟣", "orange": "🟠",
}
```

- [ ] **Step 3: 修改 get_personality 支持性别**

将 `get_personality` 方法修改为：

```python
def get_personality(self, beast_id: str, is_transformed: bool, gender: str = "") -> Optional[PetPersonality]:
    forms = self._personalities.get(beast_id)
    if not forms:
        return None
    if not is_transformed:
        return forms["beast"]
    # 化形后优先使用对应性别人设
    if gender == "male" and "human_male" in forms:
        return forms["human_male"]
    return forms["human"]  # 默认女性或无性别指定
```

- [ ] **Step 4: 修改 _load_all 中人设解析，支持 human_form_male**

找到 `self._personalities` 的解析代码块，修改为：

```python
self._personalities: Dict[str, Dict[str, PetPersonality]] = {}
for beast_id, forms in pers_config["personalities"].items():
    parsed = {
        "beast": PetPersonality(**forms["beast_form"]),
        "human": PetPersonality(**forms["human_form"]),
    }
    if "human_form_male" in forms:
        parsed["human_male"] = PetPersonality(**forms["human_form_male"])
    self._personalities[beast_id] = parsed
```

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/pet/config.py
git commit -m "feat(pet): PetConfigManager 支持进化配置查询和性别人设"
```

---

### Task 4: 人设 YAML — 新增男性化形人设

**Files:**
- Modify: `plugins/xiuxian_game/data/pet_personalities.yaml`

- [ ] **Step 1: 为每种诡兽添加 human_form_male**

在每个诡兽的 `human_form` 后面追加 `human_form_male` 配置。以下是5种诡兽的男性人设：

**冥犬 (guard_dog) — 犬灵少年**：
```yaml
    human_form_male:
      role: "化形为人的犬灵少年"
      pronouns: ["我", "本犬"]
      speech_patterns: ["元气", "忠诚", "热血"]
      key_words: ["主人!", "嘿嘿", "交给我吧"]
      background: "你是一只修炼有成的冥犬，已经化形为银发犬耳少年。虽然外形是人类少年，但骨子里还是那只忠诚的冥犬。你热血而直爽，看到球想追、听到异响会立刻警觉。对主人非常忠诚和依赖。"
      behavioral_rules:
        - "偶尔会暴露犬的习性"
        - "对主人极其忠诚，遇到危险会第一时间挡在前面"
        - "说话热血直爽，偶尔犯傻"
```

**诡猫 (ghost_cat) — 猫少爷**：
```yaml
    human_form_male:
      role: "化形为人的猫少爷"
      pronouns: ["本喵", "我"]
      speech_patterns: ["慵懒", "毒舌", "偶尔温柔"]
      key_words: ["喵~", "无聊", "你好吵"]
      background: "你是一只修炼化形的诡猫，外形是一位慵懒的猫耳少年。你保持着猫的高傲和随性，喜欢在暖和的地方打盹，对大多数事情提不起兴趣。嘴很毒但关键时刻靠得住。"
      behavioral_rules:
        - "慵懒毒舌，嘴上不饶人但行动很诚实"
        - "装作对一切都不在意，其实偷偷关注主人"
        - "对鱼类食物有明显兴趣但要装作淡定"
```

**鬼隼 (ghost_hawk) — 隼羽武者**：
```yaml
    human_form_male:
      role: "化形为人的隼羽武者"
      pronouns: ["我"]
      speech_patterns: ["冷静", "寡言", "可靠"]
      key_words: ["了解", "交给我", "注意安全"]
      background: "你是化形为背生双翼青年武者的鬼隼。化形后话依然不多，但多了几分人情味。你像一位沉默寡言的护卫，用行动守护主人。偶尔露出温和的笑容。"
      behavioral_rules:
        - "话少但每句都有分量"
        - "像守护骑士一样默默保护主人"
        - "不善言辞但会用行动表达关心"
```

**噩梦狼 (nightmare_wolf) — 狼灵少年**：
```yaml
    human_form_male:
      role: "化形为人的狼灵少年"
      pronouns: ["我", "本狼"]
      speech_patterns: ["傲气", "忠诚", "外冷内热"]
      key_words: ["哼", "遵命", "...别误会"]
      background: "你是化形为狼耳少年的噩梦狼。化形后你是一位傲气的少年，嘴上总是一副不在乎的样子，其实比谁都关心主人。你外冷内热，偶尔的温柔会让人措手不及。"
      behavioral_rules:
        - "傲气十足但掩盖不住对主人的关心"
        - "嘴上说着'随便你'但身体很诚实"
        - "被夸奖时会不自在地移开视线"
```

**虚空蟒 (void_serpent) — 蛇君**：
```yaml
    human_form_male:
      role: "化形为人的蛇君"
      pronouns: ["吾", "我"]
      speech_patterns: ["从容", "优雅", "深沉"]
      key_words: ["呵...", "有趣", "过来"]
      background: "你是化形为蛇瞳青年的虚空蟒。你是所有诡兽中最古老、最有智慧的存在。说话从容优雅，带着看透世间万物的深沉。你享受逗弄主人，但在关键时刻是最可靠的存在。"
      behavioral_rules:
        - "说话从容优雅，带着上位者的气度"
        - "用智慧而非蛮力解决问题"
        - "对主人有保护欲，会在暗中排除危险"
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/data/pet_personalities.yaml
git commit -m "feat(pet): 新增5种诡兽男性化形人设"
```

---

### Task 5: pet_config.yaml 新增男性化形名和描述

**Files:**
- Modify: `plugins/xiuxian_game/data/pet_config.yaml`

- [ ] **Step 1: 为每种诡兽新增 transform_name_male 和 transform_description_male**

在每种诡兽配置的 `transform_description` 后面追加两个字段：

```yaml
  guard_dog:
    # ... 现有字段 ...
    transform_name_male: "犬灵少年"
    transform_description_male: "化形为一位银发犬耳少年，尾巴会在高兴时摇个不停，热血而直爽"

  ghost_cat:
    # ... 现有字段 ...
    transform_name_male: "猫少爷"
    transform_description_male: "化形为一位慵懒的猫耳少年，眯着眼打盹的样子让人想揉"

  ghost_hawk:
    # ... 现有字段 ...
    transform_name_male: "隼羽武者"
    transform_description_male: "化形为一位背生双翼的青年武者，眼神锐利而可靠"

  nightmare_wolf:
    # ... 现有字段 ...
    transform_name_male: "狼灵少年"
    transform_description_male: "化形为一位傲气的狼耳少年，外冷内热，嘴硬心软"

  void_serpent:
    # ... 现有字段 ...
    transform_name_male: "蛇君"
    transform_description_male: "化形为一位蛇瞳青年，从容优雅，带着看透一切的深沉"
```

- [ ] **Step 2: 更新 BeastConfig dataclass**

在 `plugins/xiuxian_game/pet/config.py` 的 `BeastConfig` 中新增两个可选字段：

```python
@dataclass
class BeastConfig:
    beast_id: str
    name: str
    rarity: str
    intercept_rate: int
    description: str
    transform_name: str
    transform_description: str
    transform_name_male: str = ""
    transform_description_male: str = ""
```

- [ ] **Step 3: 新增方法获取化形名**

在 `PetConfigManager` 中新增：

```python
def get_transform_name(self, beast_id: str, gender: str = "") -> str:
    """根据性别获取化形名"""
    beast = self.get_beast(beast_id)
    if not beast:
        return "未知"
    if gender == "male" and beast.transform_name_male:
        return beast.transform_name_male
    return beast.transform_name

def get_transform_description(self, beast_id: str, gender: str = "") -> str:
    """根据性别获取化形描述"""
    beast = self.get_beast(beast_id)
    if not beast:
        return ""
    if gender == "male" and beast.transform_description_male:
        return beast.transform_description_male
    return beast.transform_description
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/data/pet_config.yaml plugins/xiuxian_game/pet/config.py
git commit -m "feat(pet): 新增男性化形名/描述配置和查询方法"
```

---

### Task 6: 核心逻辑 — 进化和化形改造

**Files:**
- Modify: `plugins/xiuxian_game/pet/pet_service.py`

- [ ] **Step 1: 修改 _apply_level_up 使用进化后稀有度**

找到 `_apply_level_up` 方法，改为：

```python
def _apply_level_up(self, pet: PetInstance):
    """应用升级属性"""
    beast = self.config.get_beast(pet.beast_id)
    # 优先使用进化后的稀有度
    current_rarity = pet.evolved_rarity or beast.rarity
    growth = self.config.get_growth(current_rarity)
    if growth:
        pet.bonus_attack += int(growth.attack)
        pet.bonus_defense += int(growth.defense)
        pet.bonus_hp += int(growth.hp)
        pet.bonus_crit_rate += growth.crit_rate
        pet.bonus_dodge_rate += growth.dodge_rate
```

- [ ] **Step 2: 新增 evolve_pet 方法**

在 `PetService` 类中（`get_pet_info` 之前）添加：

```python
# 稀有度中文名映射
RARITY_CN = {"white": "普通", "green": "优秀", "blue": "稀有", "purple": "史诗", "orange": "传说"}
RARITY_EMOJI = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}

async def evolve_pet(
    self, uow: UnitOfWork, player_id: str, confirm: bool = False
) -> Tuple[bool, str]:
    """宠物进化 — 提升稀有度"""
    pet = await uow.pets.get_active_pet(player_id)
    if not pet:
        return False, "你还没有伴侣诡兽"

    beast = self.config.get_beast(pet.beast_id)
    current_rarity = pet.evolved_rarity or beast.rarity
    next_rarity = self.config.get_next_rarity(current_rarity)

    if not next_rarity:
        return False, f"【{pet.nickname}】已是{self.RARITY_EMOJI.get(current_rarity, '')}最高稀有度，无法继续进化"

    evo_cfg = self.config.get_evolution_config(current_rarity, next_rarity)
    if not evo_cfg:
        return False, "⛔ 进化配置缺失，请联系管理员"

    min_level = evo_cfg["min_level"]
    cost_item = evo_cfg["cost_item"]
    cost_qty = evo_cfg["cost_quantity"]
    cost_resentment = evo_cfg["cost_resentment"]

    from ..config import config as gcfg
    item_cfg = gcfg.items_config["by_id"].get(cost_item)
    item_name = item_cfg.name if item_cfg else cost_item

    cur_emoji = self.RARITY_EMOJI.get(current_rarity, "")
    next_emoji = self.RARITY_EMOJI.get(next_rarity, "")
    cur_cn = self.RARITY_CN.get(current_rarity, current_rarity)
    next_cn = self.RARITY_CN.get(next_rarity, next_rarity)

    # 不确认时：显示进化条件
    if not confirm:
        # 检查当前状态
        from ..models.inventory import ItemInstance
        from sqlalchemy import func, select
        stmt = select(func.coalesce(func.sum(ItemInstance.quantity), 0)).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == cost_item
        )
        result = await uow.session.execute(stmt)
        have_qty = result.scalar() or 0

        player = await uow.session.get(Player, player_id)
        have_resentment = player.resentment if player else 0

        level_ok = "✅" if pet.level >= min_level else "❌"
        item_ok = "✅" if have_qty >= cost_qty else "❌"
        resentment_ok = "✅" if have_resentment >= cost_resentment else "❌"

        old_growth = self.config.get_growth(current_rarity)
        new_growth = self.config.get_growth(next_rarity)

        msg = (
            f"🔮 宠物进化 — {pet.nickname}\n"
            f"━━━━━━━━━━━━━\n"
            f"{cur_emoji}{cur_cn} → {next_emoji}{next_cn}\n"
            f"━━━ 进化条件 ━━━\n"
            f"{level_ok} 等级 ≥ {min_level}（当前 Lv.{pet.level}）\n"
            f"{item_ok} {item_name} ×{cost_qty}（拥有 {have_qty}）\n"
            f"{resentment_ok} 怨念 ≥ {cost_resentment:,}（拥有 {have_resentment:,}）\n"
            f"━━━ 成长变化 ━━━\n"
            f"⚔攻击 {old_growth.attack}→{new_growth.attack}/级\n"
            f"🛡防御 {old_growth.defense}→{new_growth.defense}/级\n"
            f"❤生命 {old_growth.hp}→{new_growth.hp}/级\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 输入【进化宠物 确认】执行进化"
        )
        return True, msg

    # 确认进化：校验条件
    if pet.level < min_level:
        return False, f"⛔ 等级不足，需要 Lv.{min_level}（当前 Lv.{pet.level}）"

    from ..models.inventory import ItemInstance
    from sqlalchemy import func, select
    stmt = select(func.coalesce(func.sum(ItemInstance.quantity), 0)).where(
        ItemInstance.player_id == player_id,
        ItemInstance.item_id == cost_item
    )
    result = await uow.session.execute(stmt)
    have_qty = result.scalar() or 0
    if have_qty < cost_qty:
        return False, f"⛔ {item_name}不足，需要 {cost_qty} 个（拥有 {have_qty}）"

    from ..models.player import Player
    player = await uow.session.get(Player, player_id)
    if not player or player.resentment < cost_resentment:
        return False, f"⛔ 怨念不足，需要 {cost_resentment:,}"

    # 扣除材料
    await ItemInstance.consume_item(uow.session, player_id, cost_item, cost_qty)
    player.resentment -= cost_resentment

    # 执行进化：重算属性
    old_growth = self.config.get_growth(current_rarity)
    new_growth = self.config.get_growth(next_rarity)
    levels_gained = pet.level - 1  # 从Lv.1到当前等级的升级次数

    pet.bonus_attack = int(new_growth.attack * levels_gained)
    pet.bonus_defense = int(new_growth.defense * levels_gained)
    pet.bonus_hp = int(new_growth.hp * levels_gained)
    pet.bonus_crit_rate = new_growth.crit_rate * levels_gained
    pet.bonus_dodge_rate = new_growth.dodge_rate * levels_gained
    pet.evolved_rarity = next_rarity

    await uow.pets.update(pet)

    # 使宠物属性缓存失效
    from ..domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory
    AttributeCalculatorFactory.invalidate_pet_cache(player_id)

    # 计算属性变化展示
    total_bonus = self._calculate_total_bonus(pet)

    msg = (
        f"🎉 进化成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"{cur_emoji}{cur_cn} → {next_emoji}{next_cn}\n"
        f"🐾 {pet.nickname} 的力量觉醒了！\n"
        f"━━━ 当前属性 ━━━\n"
        f"⚔攻击+{total_bonus['attack']} 🛡防御+{total_bonus['defense']}\n"
        f"❤生命+{total_bonus['hp']}\n"
        f"💥暴击+{total_bonus['crit_rate']:.1%} 👟闪避+{total_bonus['dodge_rate']:.1%}\n"
        f"━━━━━━━━━━━━━\n"
        f"📈 成长值已按{next_cn}标准重算"
    )
    return True, msg
```

- [ ] **Step 3: 修改 transform 方法支持性别参数**

将 `transform` 方法改为：

```python
async def transform(
    self, uow: UnitOfWork, player_id: str, gender: str = "female"
) -> Tuple[bool, str]:
    """宠物化形"""
    pet = await uow.pets.get_active_pet(player_id)
    if not pet:
        return False, "你还没有伴侣诡兽"

    beast = self.config.get_beast(pet.beast_id)

    # 已化形：允许切换性别
    if pet.is_transformed:
        if pet.transform_gender == gender:
            gender_cn = "男" if gender == "male" else "女"
            return False, f"【{pet.nickname}】当前已是{gender_cn}性化形"
        pet.transform_gender = gender
        await uow.pets.update(pet)
        transform_name = self.config.get_transform_name(pet.beast_id, gender)
        transform_desc = self.config.get_transform_description(pet.beast_id, gender)
        gender_cn = "男" if gender == "male" else "女"
        return True, (
            f"【{pet.nickname}】切换化形！\n"
            f"化形为: {transform_name}（{gender_cn}）\n"
            f"{transform_desc}"
        )

    req_level = self.config.settings["transform_level"]
    req_affection = self.config.settings["transform_affection"]
    if pet.level < req_level:
        return False, f"化形需要等级{req_level}（当前{pet.level}级）"
    if pet.affection < req_affection:
        return False, f"化形需要好感度{req_affection}（当前{pet.affection}）"

    pet.is_transformed = True
    pet.transform_gender = gender
    await uow.pets.update(pet)

    transform_name = self.config.get_transform_name(pet.beast_id, gender)
    transform_desc = self.config.get_transform_description(pet.beast_id, gender)
    gender_cn = "男" if gender == "male" else "女"
    return True, (
        f"【{pet.nickname}】化形成功!\n"
        f"化形为: {transform_name}（{gender_cn}）\n"
        f"{transform_desc}"
    )
```

- [ ] **Step 4: 修改 get_pet_info 显示进化稀有度**

在 `get_pet_info` 方法中，找到获取 `rarity_emoji, rarity_name` 的代码行，改为使用进化后稀有度：

```python
# 使用进化后稀有度（如有）
current_rarity = pet.evolved_rarity or beast.rarity
rarity_emoji, rarity_name = self.RARITY_DISPLAY.get(
    current_rarity, ("⚪", "普通")
)
```

同时更新 `display_name` 逻辑，考虑化形性别：

```python
if pet.is_transformed:
    display_name = self.config.get_transform_name(pet.beast_id, pet.transform_gender)
else:
    display_name = beast.name
```

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/pet/pet_service.py
git commit -m "feat(pet): 实现进化逻辑、化形性别选择、属性重算"
```

---

### Task 7: 命令注册 — 进化宠物 & 化形改造

**Files:**
- Modify: `plugins/xiuxian_game/pet/commands.py`

- [ ] **Step 1: 新增进化宠物命令**

```python
# ==================== 宠物进化 ====================
evolve_cmd = on_command("进化宠物", aliases={"宠物进化", "进化"}, priority=5, block=True)

@evolve_cmd.handle()
async def handle_evolve(event: MessageEvent, args: Message = CommandArg()):
    """【进化宠物】- 提升宠物稀有度"""
    args_text = args.extract_plain_text().strip()
    confirm = args_text == "确认"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await evolve_cmd.finish("请先创建角色")

        success, msg = await pet_service.evolve_pet(uow, player.id, confirm)
        await evolve_cmd.finish(msg)
```

- [ ] **Step 2: 修改化形命令支持性别参数**

找到现有的化形命令（搜索 `化形`），修改 handler：

```python
# ==================== 化形 ====================
transform_cmd = on_command("化形", priority=5, block=True)

@transform_cmd.handle()
async def handle_transform(event: MessageEvent, args: Message = CommandArg()):
    """【化形 男/女】- 宠物化形（可选性别）"""
    args_text = args.extract_plain_text().strip()

    # 解析性别参数
    gender = "female"  # 默认女性
    if args_text in ("男", "male", "男性"):
        gender = "male"
    elif args_text in ("女", "female", "女性"):
        gender = "female"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await transform_cmd.finish("请先创建角色")

        success, msg = await pet_service.transform(uow, player.id, gender)
        await transform_cmd.finish(msg)
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/pet/commands.py
git commit -m "feat(pet): 新增进化宠物命令和化形性别参数"
```

---

### Task 8: 宝箱掉落 — 诡兽精魄

**Files:**
- Modify: `plugins/xiuxian_game/world/dungeon_battle.py`

- [ ] **Step 1: 在 _handle_treasure 中添加精魄掉落**

在 `_handle_treasure` 函数中，现有诡兽掉落代码（`if rng.random() < 0.005:`）之后，添加诡兽精魄掉落：

```python
    # 低概率掉落诡兽精魄（0.5%，与稀有诡兽相同概率）
    if rng.random() < 0.005:
        try:
            await ItemInstance.add_item(session, player.id, "pet_evolution_stone", 1)
            msg += "\n\n✨ 宝箱角落闪烁着幽光...你获得了【诡兽精魄】×1！"
        except ValueError:
            pass
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/world/dungeon_battle.py
git commit -m "feat(pet): 诡域宝箱低概率掉落诡兽精魄"
```

---

### Task 9: 帮助信息 & AI 知识库同步

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`
- Modify: `plugins/xiuxian_game/data/knowledge/pet_system_help.yaml`

- [ ] **Step 1: 更新 help.py 宠物系统帮助**

在宠物系统帮助区块中追加进化和化形相关指令：

```python
"【进化宠物】 查看进化条件和属性变化",
"【进化宠物 确认】 消耗材料执行进化",
"【化形 男/女】 化形时选择性别（可切换）",
```

- [ ] **Step 2: 更新 pet_system_help.yaml**

在 keywords 中添加 `进化宠物`、`宠物进化`、`进化`、`诡兽精魄`。

在 body 的 `✨ 化形：` 部分追加：

```yaml
  🔮 进化：
  【进化宠物】 查看进化条件（等级+精魄+怨念）
  【进化宠物 确认】 消耗材料提升稀有度
    • 进化后属性按新稀有度重算并补齐
    • 进化路径：⚪普通→🟢优秀→🔵稀有→🟣史诗→🟠传说
    • 材料「诡兽精魄」从诡域宝箱中低概率获取
```

在 `✨ 化形：` 部分修改为：

```yaml
  ✨ 化形：
  【化形 男/女】 宠物化形为人形态（可选性别）
    • 需要等级50 + 好感度500
    • 化形后解锁新的AI对话人设
    • 已化形后再次使用可切换性别
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/player/help.py plugins/xiuxian_game/data/knowledge/pet_system_help.yaml
git commit -m "docs(pet): 同步进化系统和化形性别的帮助信息"
```

---

### Task 10: 宠物对话服务适配性别人设

**Files:**
- Modify: `plugins/xiuxian_game/pet/pet_dialogue_service.py`

- [ ] **Step 1: 修改对话服务中获取人设的调用**

找到调用 `config.get_personality(pet.beast_id, pet.is_transformed)` 的地方，改为传入性别参数：

```python
personality = config.get_personality(
    pet.beast_id, pet.is_transformed, pet.transform_gender
)
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/pet/pet_dialogue_service.py
git commit -m "feat(pet): AI对话服务适配化形性别人设"
```
