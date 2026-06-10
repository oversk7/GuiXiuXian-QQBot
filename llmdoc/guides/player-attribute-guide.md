# 如何使用和扩展属性系统

## 1. 获取玩家有效属性

获取包含所有加成(基础+装备+丹药+VIP+临时buff)的有效属性:

```python
from plugins.xiuxian_game.domain.attributes.player_attributes_integration import get_effective_attributes_v2
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork

async with UnitOfWork(session_factory) as uow:
    player = await uow.players.get_by_id(player_id)
    attrs = await get_effective_attributes_v2(player)
    # attrs = {'max_hp': 150, 'max_mp': 120, 'attack': 25, ...}
```

## 2. 添加新的属性来源

如果需要添加新的属性来源(如称号加成、坐骑加成等):

**步骤1**: 创建新的Source类,实现IAttributeSource接口 (`plugins/xiuxian_game/domain/attributes/attribute_sources/your_source.py`):
```python
from plugins.xiuxian_game.domain.attributes.interfaces import IAttributeSource, AttributeBonus

class YourAttributeSource(IAttributeSource):
    async def calculate_bonus(self, player_id: str) -> AttributeBonus:
        # 计算属性加成
        return AttributeBonus(
            max_hp=10,
            attack=5,
            is_persisted=False  # 如果加成已持久化到player属性,设为True
        )
```

**步骤2**: 在AttributeCalculatorFactory中注册 (`plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py:60-75`):
```python
from plugins.xiuxian_game.domain.attributes.attribute_sources.your_source import YourAttributeSource

def _create_calculator() -> AttributeCalculator:
    sources = [
        BuffAttributeSource(),
        EquipmentAttributeSource(),
        YourAttributeSource(),  # 添加新来源
    ]
    return AttributeCalculator(sources)
```

**步骤3**: 如果新来源需要缓存失效机制,添加invalidate方法 (`plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py:80-90`):
```python
def invalidate_your_source_cache(player_id: str):
    # 失效缓存逻辑
    pass
```

## 3. 修改玩家属性

**直接修改并持久化**:
```python
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork

async with UnitOfWork(session_factory) as uow:
    player = await uow.players.get_by_id(player_id)

    # 修改属性
    player.max_hp += 10
    player.attack += 5

    # 自动提交
```

**通过装备系统修改** (推荐):
```python
from plugins.xiuxian_game.item.equipment_service import EquipmentService
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork

async with UnitOfWork(session_factory) as uow:
    service = EquipmentService(uow.items, uow.players)
    await service.recalc_equipment_attributes(player_id)
    # 自动处理装备加成、mp_from_hp特效、血蓝上限
```

**通过物品效果修改**:
```python
from plugins.xiuxian_game.item.item_effects import apply_item_effect

# 永久属性加成 (持久化到player属性)
await apply_item_effect(player, item, effect_type="BUFF")

# 临时buff (创建TemporaryBuff记录)
await apply_item_effect(player, item, effect_type="TEMP_BUFF")
```

## 4. 添加新的属性字段

**步骤1**: 在Player模型中添加字段 (`plugins/xiuxian_game/models/player.py:250-260`):
```python
class Player(Base):
    # ...existing fields...
    new_attribute: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
        comment="新属性描述"
    )
```

**步骤2**: 在auto_migrate中注册 (`plugins/xiuxian_game/models/auto_migrate.py:30-40`):
```python
REQUIRED_FIELDS = {
    "player": {
        "new_attribute": "INT DEFAULT 0 COMMENT '新属性描述'"
    }
}
```

**步骤3**: 重启Bot,自动添加字段到数据库

**步骤4**: 在AttributeBonus中添加字段 (`plugins/xiuxian_game/domain/attributes/interfaces.py:20-30`):
```python
@dataclass
class AttributeBonus:
    # ...existing fields...
    new_attribute: int = 0
```

## 5. 使用战斗属性计算器

计算战斗相关属性(暴击率、闪避率等):
```python
from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator
from plugins.xiuxian_game.domain.attributes.player_attributes_integration import get_effective_attributes_v2

async def get_battle_attributes(player):
    base_attrs = await get_effective_attributes_v2(player)
    battle_attrs = BattleAttributeCalculator.calculate_effective_attributes(
        player, base_attrs
    )
    # battle_attrs = {
    #     'critical_rate': 15.0,  # 暴击率15%
    #     'dodge_rate': 10.0,     # 闪避率10%
    #     ...
    # }
```

## 6. 处理装备特殊效果

**mp_from_hp特效** (百分比HP转MP):
```python
from plugins.xiuxian_game.item.equipment_service import EquipmentService

async with UnitOfWork(session_factory) as uow:
    service = EquipmentService(uow.items, uow.players)
    # recalc_equipment_attributes会自动处理mp_from_hp特效
    await service.recalc_equipment_attributes(player_id)
```

**其他特效** (吸血、反伤、真伤等):
```python
from plugins.xiuxian_game.battle.battle_effects import BattleEffectManager

# 战斗开始时,加载装备特效
effect_manager = BattleEffectManager()
await effect_manager.load_equipment_effects(player)

# 战斗中应用特效
damage = effect_manager.apply_vampiric(damage, player)
```

## 7. 属性来源持久化策略

**持久化到player属性** (装备、丹药、VIP):
- 优点: 查询快,无需每次计算
- 缺点: 修改复杂,需要重新计算
- 适用: 高频查询、低频修改的属性

**动态计算** (临时buff):
- 优点: 灵活,支持时效性
- 缺点: 每次查询数据库
- 适用: 低频查询、高频变化的属性,配合缓存使用

**混合策略** (推荐):
- 装备/丹药/VIP: 持久化到player属性
- 临时buff: 动态计算+60秒缓存
- 最终属性 = 基础属性(含持久化) + 临时buff

## 8. 调试属性计算

**查看属性来源分解**:
```python
from plugins.xiuxian_game.domain.attributes.attribute_calculator import AttributeCalculator
from plugins.xiuxian_game.domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory

calculator = AttributeCalculatorFactory.get_instance()
breakdown = await calculator.calculate_with_breakdown(player_id)
# breakdown = {
#     'base': {'max_hp': 100, 'attack': 10, ...},
#     'equipment': {'max_hp': 20, 'attack': 5, ...},
#     'buff': {'max_hp': 10, 'attack': 0, ...},
#     'final': {'max_hp': 130, 'attack': 15, ...}
# }
```

**查看缓存统计**:
```python
from plugins.xiuxian_game.domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory

stats = AttributeCalculatorFactory.get_cache_stats()
# stats = {'hit_count': 900, 'miss_count': 100, 'hit_rate': 0.9}
```

## 9. 最佳实践

- **优先使用get_effective_attributes_v2()**: 而非直接读取player属性
- **装备加成修改后失效缓存**: 确保buff数据一致性
- **新属性来源实现IAttributeSource**: 保持架构一致性
- **使用UnitOfWork管理事务**: 避免连接泄漏
- **测试时Mock Repository**: 而非真实数据库
- **属性字段添加到REQUIRED_FIELDS**: 确保自动迁移
