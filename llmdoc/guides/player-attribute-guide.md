# 如何使用和扩展属性系统

## 1. 获取玩家有效属性（展示/业务判定）

获取包含所有加成（基础+装备+丹药+VIP+临时buff+宠物）的有效属性，**全量真源**：

```python
attrs = await player.get_effective_attributes(session)
# attrs = {'max_hp': 150, 'attack': 25, 'critical_rate': 12, ...} 共19项，键名=Player字段名
```

- 不传 session 时只返回存储字段值（不查 buff/宠物），仅用于无法拿到 session 的场景
- 禁止再造并行的属性计算框架（历史上 v2 框架因字段名映射错位丢失 buff 加成，已于 2026-06-10 删除）

## 2. 获取战斗属性（含上限收口）

战斗与战力面板用**战斗档**，在真源基础上叠加 T1 词缀并应用 `ATTRIBUTE_CAPS`：

```python
from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator

# 异步版（推荐，含临时buff/宠物/词缀）
battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(
    player, session, equipment_bonus=affix_bonus
)

# 同步版（无 session 场景：引擎内部、怪物判定；不含临时buff/宠物）
battle_attrs = BattleAttributeCalculator.calculate_effective_attributes(player)
```

属性上限单源在 `BattleAttributeCalculator.ATTRIBUTE_CAPS`，新增战斗属性时记得补上限。

## 3. 修改玩家属性

**永久变更必须走唯一写入口**（详见 coding-conventions.md §6.3）：

```python
from plugins.xiuxian_game.domain.attributes.permanent_change import apply_permanent_change

await apply_permanent_change(session, player, {"attack": 5, "max_hp": 20},
                             ledger_item_id=item_id, quantity=1)
# 原子完成: 改字段 + 记账(ElixirUsageLog) + 装备重算 + hp/mp收口
```

**临时buff**（不改 player 字段，时效性加成）：

```python
from plugins.xiuxian_game.models.temporary_buff import TemporaryBuff

await TemporaryBuff.create_buff(session, player.id, buff_id, buff_name,
                                attribute_bonuses={"attack": 10},  # 键名=Player字段名
                                duration_minutes=30)
```

**装备加成**：由 `EquipmentService.recalc_equipment_attributes` 统一重算（_persist_bonus 机制），
不要手工修改装备相关属性。

## 4. 添加新的属性字段

**步骤1**: 在 Player 模型中添加字段（`plugins/xiuxian_game/models/player.py`）：
```python
new_attribute: Mapped[int] = mapped_column(default=0, server_default="0", comment="新属性描述")
```

**步骤2**: 在 auto_migrate 中注册（`plugins/xiuxian_game/models/auto_migrate.py` REQUIRED_FIELDS）

**步骤3**: 重启 Bot 自动迁移

**步骤4**: 如属于初始属性，补充 `Player.INIT_ATTRS`；如属于战斗属性，
补充 `BattleAttributeCalculator.ATTRIBUTE_CAPS` 上限并接入 `get_effective_attributes` 返回字典

## 5. 添加新的属性来源（如称号、坐骑加成）

属性来源分两类，按持久化策略选择：

**持久化型**（推荐，类比装备/VIP）：发放时通过 `apply_permanent_change` 写入字段并记账，
或建专表（参考 `VIPEquipmentBonus`）并接入轮回重建逻辑。

**动态型**（类比宠物）：参考 `domain/attributes/attribute_sources/pet_source.py`——
单例 + TTL 缓存 + 失效接口，然后在 `Player.get_effective_attributes` 与
`get_attribute_breakdown` 中叠加。注意键名必须用 Player 字段名直通，禁止中间映射层。

## 6. 调试属性

**来源分解**（增益状态命令同款）：
```python
breakdown = await player.get_attribute_breakdown(session)
# {'base': {...}, 'equipment': {...}, 'permanent': {...}, 'vip_equipment': {...},
#  'temporary': {...}, 'pet': {...}, 'total': {...}}
```

**生产对账**：`scripts/check_attribute_consistency.py`（只读），
漂移核销用 `scripts/calibrate_attribute_ledger.py`（先 dry-run）。

## 7. 最佳实践

- **读属性用真源** `player.get_effective_attributes(session)`，战斗数值用 `BattleAttributeCalculator`
- **永久变更走 apply_permanent_change**，禁止直接 setattr（账实漂移且轮回时被吞）
- **键名直通**：buff/宠物等动态加成的字典键必须是 Player 字段名，禁止引入字段名映射层
- **回归锁**：`tests/test_effective_attributes_passthrough.py` 锁定加成直通行为
