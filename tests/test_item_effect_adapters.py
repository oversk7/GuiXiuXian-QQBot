"""
物品效果适配器测试

验证ItemEffectAdapter能正确将旧效果适配到新接口
"""

import sys
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============ Mock对象 ============

@dataclass
class MockPlayer:
    """模拟Player对象"""
    id: str = "test_player_123"
    hp: int = 50
    max_hp: int = 100
    mp: int = 30
    max_mp: int = 50
    exp: int = 0
    level: int = 1
    attribute_points: int = 0

    def __post_init__(self):
        # 添加get_effective_attributes方法
        async def get_effective_attributes(session):
            return {
                "max_hp": self.max_hp,
                "max_mp": self.max_mp,
                "attack": 10,
                "defense": 5,
                "agility": 3,
                "luck": 1
            }
        self.get_effective_attributes = get_effective_attributes


@dataclass
class MockItemConfig:
    """模拟ItemConfig对象"""
    item_id: str
    effect_params: Dict[str, Any]


class MockSession:
    """模拟数据库会话"""
    def __init__(self):
        self.added_objects = []
        self.committed = False

    def add(self, obj):
        self.added_objects.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True


# ============ 测试用例 ============

async def test_wrap_legacy_effect():
    """测试1: wrap_legacy_item_effect工厂函数"""
    print("\n" + "=" * 60)
    print("测试1: wrap_legacy_item_effect 工厂函数")
    print("=" * 60)

    # 定义一个简单的旧效果函数
    async def _test_effect(player, cfg, qty, ctx, session):
        """测试用的旧效果函数"""
        value = cfg.effect_params.get("value", 10) * qty
        player.hp += value
        return True, f"测试效果生效: HP +{value}"

    # 使用工厂函数包装
    from plugins.xiuxian_game.domain.effects.adapters import wrap_legacy_item_effect
    from plugins.xiuxian_game.domain.effects import EffectContext, TriggerType

    TestEffect = wrap_legacy_item_effect(
        effect_id="test_legacy_effect",
        legacy_handler=_test_effect,
        description="测试旧效果包装"
    )

    # 创建实例
    effect = TestEffect()
    print(f"[OK] 效果ID: {effect.effect_id}")
    print(f"[OK] 效果描述: {effect.description}")

    # 创建上下文
    player = MockPlayer(hp=50)
    item_cfg = MockItemConfig(item_id="test_item", effect_params={"value": 20})

    context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=2
    )

    # 执行效果
    result = await effect.execute(context)

    print(f"\n执行结果:")
    print(f"  - Success: {result.success}")
    print(f"  - Message: {result.message}")
    print(f"  - Player HP: {player.hp} (应该是90)")

    assert result.success is True, "效果应该成功"
    assert player.hp == 90, "HP应该增加40 (20 * 2)"
    assert "测试效果生效" in result.message, "消息应该包含旧函数返回的文本"

    print("[OK] 测试1通过: wrap_legacy_item_effect 工作正常\n")


async def test_example_restore_hp():
    """测试2: 示例 - 恢复生命值效果"""
    print("=" * 60)
    print("测试2: ExampleRestoreHPEffect (恢复生命值)")
    print("=" * 60)

    from plugins.xiuxian_game.domain.effects import get_effect_registry, EffectContext, TriggerType

    registry = get_effect_registry()

    # 创建mock对象
    player = MockPlayer(hp=50, max_hp=100)
    item_cfg = MockItemConfig(item_id="hp_potion", effect_params={"value": 30})

    context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=1
    )

    # 执行效果
    effect = registry.create("example_restore_hp")
    print(f"[OK] 创建效果实例: {effect.effect_id}")

    result = await effect.execute(context)

    print(f"\n执行结果:")
    print(f"  - Success: {result.success}")
    print(f"  - Message: {result.message}")
    print(f"  - Player HP: {player.hp} (应该是80)")
    print(f"  - Attribute Changes: {result.attribute_changes}")
    print(f"  - Extra Data: {result.extra_data}")

    assert result.success is True, "恢复生命应该成功"
    assert player.hp == 80, "HP应该恢复到80"
    assert result.attribute_changes.get("hp") == 30, "属性变化应该记录+30"
    assert result.extra_data.get("old_hp") == 50, "应该记录旧HP值"
    assert result.extra_data.get("new_hp") == 80, "应该记录新HP值"

    print("[OK] 测试2通过: 恢复生命值效果工作正常\n")


async def test_example_restore_hp_edge_cases():
    """测试3: 恢复生命值 - 边界情况"""
    print("=" * 60)
    print("测试3: ExampleRestoreHPEffect - 边界情况")
    print("=" * 60)

    from plugins.xiuxian_game.domain.effects import get_effect_registry, EffectContext, TriggerType

    registry = get_effect_registry()
    effect = registry.create("example_restore_hp")

    # 测试3.1: 玩家已死亡
    print("\n3.1 测试: 玩家已死亡")
    player_dead = MockPlayer(hp=0, max_hp=100)
    item_cfg = MockItemConfig(item_id="hp_potion", effect_params={"value": 30})

    context = EffectContext(
        player=player_dead,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=1
    )

    result = await effect.execute(context)
    print(f"  - Success: {result.success} (应该是False)")
    print(f"  - Message: {result.message}")

    assert result.success is False, "死亡时使用药水应该失败"
    assert "死亡" in result.message, "消息应该提示玩家已死亡"
    print("  [OK] 死亡检查通过")

    # 测试3.2: 玩家HP已满
    print("\n3.2 测试: 玩家HP已满")
    player_full = MockPlayer(hp=100, max_hp=100)

    context = EffectContext(
        player=player_full,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=1
    )

    result = await effect.execute(context)
    print(f"  - Success: {result.success} (应该是False)")
    print(f"  - Message: {result.message}")

    assert result.success is False, "HP已满时使用药水应该失败"
    assert "已满" in result.message, "消息应该提示HP已满"
    print("  [OK] 满血检查通过")

    # 测试3.3: 恢复量超过上限
    print("\n3.3 测试: 恢复量超过上限")
    player_near_full = MockPlayer(hp=90, max_hp=100)
    item_cfg_big = MockItemConfig(item_id="big_potion", effect_params={"value": 50})

    context = EffectContext(
        player=player_near_full,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg_big,
        quantity=1
    )

    result = await effect.execute(context)
    print(f"  - Success: {result.success}")
    print(f"  - Player HP: {player_near_full.hp} (应该是100，不超过上限)")
    print(f"  - Attribute Changes: {result.attribute_changes.get('hp')} (实际恢复量)")

    assert player_near_full.hp == 100, "HP应该恢复到上限"
    assert result.attribute_changes.get("hp") == 10, "实际恢复量应该是10，不是50"
    print("  [OK] 上限检查通过")

    print("[OK] 测试3通过: 所有边界情况处理正确\n")


async def test_create_adapter_for_all():
    """测试4: 批量创建适配器"""
    print("=" * 60)
    print("测试4: create_adapter_for_all_legacy_effects (批量创建)")
    print("=" * 60)

    from plugins.xiuxian_game.domain.effects.adapters.item_effect_adapter import create_adapter_for_all_legacy_effects

    # 批量创建适配器
    adapters = create_adapter_for_all_legacy_effects()

    print(f"\n[OK] 成功创建 {len(adapters)} 个适配器:")
    for idx, (effect_id, adapter_class) in enumerate(adapters.items(), 1):
        print(f"  {idx:2d}. {effect_id:30s} -> {adapter_class.__name__}")

    # 验证关键效果
    expected_effects = [
        "item_restore_hp",
        "item_restore_mp",
        "item_buff",
        "item_temporary_buff",
        "item_gain_exp"
    ]

    for effect_id in expected_effects:
        assert effect_id in adapters, f"应该包含 {effect_id}"

    print(f"\n[OK] 所有预期效果均已创建适配器")
    print("[OK] 测试4通过: 批量创建适配器工作正常\n")


async def test_adapter_with_session():
    """测试5: 带数据库会话的适配器"""
    print("=" * 60)
    print("测试5: 适配器处理数据库会话")
    print("=" * 60)

    from plugins.xiuxian_game.domain.effects import get_effect_registry, EffectContext, TriggerType

    # 模拟带有会话的上下文
    player = MockPlayer(hp=50, max_hp=100)
    item_cfg = MockItemConfig(item_id="hp_potion", effect_params={"value": 30})
    session = MockSession()

    context = EffectContext(
        player=player,
        session=session,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=1
    )

    # 执行效果
    registry = get_effect_registry()
    effect = registry.create("example_restore_hp")
    result = await effect.execute(context)

    print(f"\n执行结果:")
    print(f"  - Success: {result.success}")
    print(f"  - Player HP: {player.hp}")
    print(f"  - Session committed: {session.committed}")

    assert result.success is True, "效果应该成功"
    assert player.hp == 80, "HP应该恢复"

    print("[OK] 测试5通过: 适配器正确处理数据库会话\n")


# ============ 主测试函数 ============

async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("[TEST] 物品效果适配器测试套件")
    print("=" * 60)
    print("测试范围: ItemEffectAdapter适配器")
    print("=" * 60)

    try:
        await test_wrap_legacy_effect()
        await test_example_restore_hp()
        await test_example_restore_hp_edge_cases()
        await test_create_adapter_for_all()
        await test_adapter_with_session()

        # 总结
        print("=" * 60)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 60)
        print("\n[OK] ItemEffectAdapter 适配器工作正常")
        print("[OK] 旧效果函数成功适配到新接口")
        print("[OK] 边界情况处理正确")
        print("[OK] 批量创建适配器成功")
        print("[OK] 数据库会话处理正确")
        print("\n[READY] 可以继续集成到生产代码")

        return True

    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"[FAIL] 测试失败: {e}")
        print("=" * 60)
        return False
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[ERROR] 发生错误: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
