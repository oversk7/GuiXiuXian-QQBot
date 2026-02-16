# Models Layer - 数据模型

**文件数:** 50 | **核心模型:** Player (532行)

## OVERVIEW

SQLAlchemy 2.0 ORM模型层。Mapped[T]类型注解，JSON字段灵活存储，Enum类型安全。

## WHERE TO LOOK

| 模型 | 文件 | 关键字段 |
|------|------|----------|
| Player | `player.py` | 70+字段: 属性/坐标/社交/境界/转生 |
| ItemInstance | `inventory.py` | item_id/owner_id/自定义属性 |
| Guild | `guild.py` | name/level/members/buildings |
| NPC | `npc.py` | personality/location/dialogue_state |
| WorldTile | `world.py` | coords/type/resources |
| Restaurant | `restaurant.py` | owner/chefs/menu |
| InnerRealmSession | `inner_realm.py` | depth/floor/loot |

## CONVENTIONS

```python
# 字段定义
class Player(Base):
    __tablename__ = "player"

    uid: Mapped[str] = mapped_column(primary_key=True)
    spirit_stones: Mapped[int] = mapped_column(default=0)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 关系
    guild: Mapped[Guild | None] = relationship(back_populates="members")
```

## ANTI-PATTERNS

- **禁止手动Alembic** → 用 `auto_migrate.py`
- **禁止在模型中写业务逻辑** → 用Service层

## 添加新字段

```python
# models/auto_migrate.py
REQUIRED_FIELDS = {
    "player": {
        "new_field": ("INTEGER", 0),
        "new_str": ("VARCHAR(255)", None),
    }
}
# 重启bot自动迁移
```
