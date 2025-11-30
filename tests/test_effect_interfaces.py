"""
效果系统接口测试

快速验证第1阶段的IEffect接口、注册中心等基础设施是否正常工作
"""

import sys
import asyncio
from pathlib import Path
import importlib.util

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 直接加载effects模块，完全绕过xiuxian_game包的__init__.py
effects_dir = project_root / "plugins" / "xiuxian_game" / "domain" / "effects"

# 加载interfaces模块
interfaces_spec = importlib.util.spec_from_file_location(
    "effects.interfaces",
    effects_dir / "interfaces.py"
)
interfaces_module = importlib.util.module_from_spec(interfaces_spec)
sys.modules["effects.interfaces"] = interfaces_module
interfaces_spec.loader.exec_module(interfaces_module)

# 创建一个假的包模块，让相对导入能够工作
effects_package = type(sys)("effects")
effects_package.interfaces = interfaces_module
sys.modules["effects"] = effects_package

# 加载registry模块（需要修改其相对导入）
# 先读取文件内容
with open(effects_dir / "registry.py", "r", encoding="utf-8") as f:
    registry_code = f.read()

# 替换相对导入为绝对导入
registry_code = registry_code.replace(
    "from .interfaces import IEffect, TriggerType",
    "from effects.interfaces import IEffect, TriggerType"
)

# 编译并执行
registry_module = type(sys)("effects.registry")
exec(compile(registry_code, str(effects_dir / "registry.py"), "exec"), registry_module.__dict__)
sys.modules["effects.registry"] = registry_module

# 导入需要的类和函数
IEffect = interfaces_module.IEffect
BaseItemEffect = interfaces_module.BaseItemEffect
BaseBattleEffect = interfaces_module.BaseBattleEffect
EffectContext = interfaces_module.EffectContext
EffectResult = interfaces_module.EffectResult
TriggerType = interfaces_module.TriggerType
get_effect_registry = registry_module.get_effect_registry
register_effect = registry_module.register_effect


# 测试1: 创建简单的物品效果
@register_effect("test_restore_hp")
class TestRestoreHPEffect(BaseItemEffect):
    """测试：恢复生命值效果"""

    def __init__(self):
        super().__init__("test_restore_hp")

    async def execute(self, context: EffectContext) -> EffectResult:
        # 模拟恢复生命值
        restore_amount = 100
        return EffectResult(
            success=True,
            message=f"恢复了{restore_amount}点生命值",
            attribute_changes={"hp": restore_amount}
        )


# 测试2: 创建战斗效果
@register_effect("test_lifesteal")
class TestLifestealEffect(BaseBattleEffect):
    """测试：吸血效果"""

    def __init__(self, lifesteal_percent: float = 0.2, duration: int = 3):
        super().__init__(
            effect_id="test_lifesteal",
            trigger_type=TriggerType.ON_ATTACK,
            duration=duration,
            max_stacks=2
        )
        self.lifesteal_percent = lifesteal_percent

    async def execute(self, context: EffectContext) -> EffectResult:
        # 模拟吸血
        damage = 50
        heal_amount = int(damage * self.lifesteal_percent)
        return EffectResult(
            success=True,
            message=f"吸血{heal_amount}点生命值",
            attribute_changes={"hp": heal_amount}
        )


class MockPlayer:
    """模拟Player对象"""
    def __init__(self):
        self.hp = 100
        self.max_hp = 1000
        self.name = "测试玩家"


async def test_basic_interface():
    """测试1: 基础接口功能"""
    print("=" * 60)
    print("测试1: 基础接口功能")
    print("=" * 60)

    # 创建模拟对象
    player = MockPlayer()

    # 测试物品效果
    print("\n1.1 测试物品效果:")
    effect = TestRestoreHPEffect()
    print(f"  - 效果ID: {effect.effect_id}")

    context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_USE
    )

    can_trigger = effect.can_trigger(context)
    print(f"  - 可以触发: {can_trigger}")

    result = await effect.execute(context)
    print(f"  - 执行结果: {result.message}")
    print(f"  - 属性变化: {result.attribute_changes}")

    assert can_trigger is True, "物品效果应该可以触发"
    assert result.success is True, "执行应该成功"
    assert result.attribute_changes.get("hp") == 100, "应该恢复100点生命值"
    print("  ✅ 物品效果测试通过")

    # 测试战斗效果
    print("\n1.2 测试战斗效果:")
    battle_effect = TestLifestealEffect(lifesteal_percent=0.2, duration=3)
    print(f"  - 效果ID: {battle_effect.effect_id}")
    print(f"  - 触发类型: {battle_effect.trigger_type}")
    print(f"  - 持续回合: {battle_effect.duration}")
    print(f"  - 最大叠加: {battle_effect._max_stacks}")

    battle_context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_ATTACK
    )

    can_trigger_battle = battle_effect.can_trigger(battle_context)
    print(f"  - 可以触发: {can_trigger_battle}")

    result_battle = await battle_effect.execute(battle_context)
    print(f"  - 执行结果: {result_battle.message}")

    assert can_trigger_battle is True, "战斗效果应该可以触发"
    assert result_battle.success is True, "执行应该成功"
    print("  ✅ 战斗效果测试通过")

    # 测试持续性效果
    print("\n1.3 测试持续性效果:")
    print(f"  - 初始持续时间: {battle_effect.duration}")

    # 第1回合
    still_active_1 = battle_effect.tick()
    print(f"  - 第1回合后: duration={battle_effect.duration}, active={still_active_1}")

    # 第2回合
    still_active_2 = battle_effect.tick()
    print(f"  - 第2回合后: duration={battle_effect.duration}, active={still_active_2}")

    # 第3回合
    still_active_3 = battle_effect.tick()
    print(f"  - 第3回合后: duration={battle_effect.duration}, active={still_active_3}")

    assert still_active_1 is True, "第1回合后应该仍然有效"
    assert still_active_2 is True, "第2回合后应该仍然有效"
    assert still_active_3 is False, "第3回合后应该失效"
    print("  ✅ 持续性效果测试通过")

    # 测试叠加
    print("\n1.4 测试效果叠加:")
    print(f"  - 初始层数: {battle_effect.current_stacks}")

    added_1 = battle_effect.add_stack()
    print(f"  - 叠加1次: success={added_1}, stacks={battle_effect.current_stacks}")

    added_2 = battle_effect.add_stack()
    print(f"  - 叠加2次: success={added_2}, stacks={battle_effect.current_stacks}")

    assert added_1 is True, "第1次叠加应该成功"
    assert added_2 is False, "第2次叠加应该失败（达到上限）"
    assert battle_effect.current_stacks == 2, "应该有2层"
    print("  ✅ 效果叠加测试通过")


async def test_registry():
    """测试2: 注册中心功能"""
    print("\n" + "=" * 60)
    print("测试2: 注册中心功能")
    print("=" * 60)

    registry = get_effect_registry()

    # 测试列出所有效果
    print("\n2.1 已注册效果列表:")
    all_effects = registry.list_all()
    for effect_id in all_effects:
        print(f"  - {effect_id}")

    assert "test_restore_hp" in all_effects, "应该包含test_restore_hp"
    assert "test_lifesteal" in all_effects, "应该包含test_lifesteal"
    print("  ✅ 效果列表测试通过")

    # 测试获取效果类
    print("\n2.2 获取效果类:")
    restore_hp_class = registry.get_class("test_restore_hp")
    print(f"  - test_restore_hp 类: {restore_hp_class.__name__}")

    assert restore_hp_class is TestRestoreHPEffect, "应该返回正确的类"
    print("  ✅ 获取效果类测试通过")

    # 测试创建效果实例
    print("\n2.3 创建效果实例:")
    instance1 = registry.create("test_restore_hp")
    print(f"  - 实例1 ID: {instance1.effect_id}")

    instance2 = registry.create("test_lifesteal", lifesteal_percent=0.3, duration=5)
    print(f"  - 实例2 ID: {instance2.effect_id}")
    print(f"  - 实例2 吸血率: {instance2.lifesteal_percent}")
    print(f"  - 实例2 持续: {instance2.duration}")

    assert instance1.effect_id == "test_restore_hp", "应该创建正确的实例"
    assert instance2.lifesteal_percent == 0.3, "应该传递参数"
    assert instance2.duration == 5, "应该传递参数"
    print("  ✅ 创建实例测试通过")

    # 测试触发类型索引
    print("\n2.4 测试触发类型索引:")
    # 首先建立索引
    registry.index_by_trigger("test_lifesteal", TriggerType.ON_ATTACK)

    on_attack_effects = registry.get_by_trigger(TriggerType.ON_ATTACK)
    print(f"  - ON_ATTACK 触发的效果: {on_attack_effects}")

    assert "test_lifesteal" in on_attack_effects, "应该包含test_lifesteal"
    print("  ✅ 触发类型索引测试通过")


async def test_context_and_result():
    """测试3: 上下文和结果数据结构"""
    print("\n" + "=" * 60)
    print("测试3: 上下文和结果数据结构")
    print("=" * 60)

    player = MockPlayer()

    # 测试EffectContext
    print("\n3.1 测试EffectContext:")
    context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config={"name": "测试物品"},
        quantity=3,
        context_type="world",
        metadata={"custom_data": 123}
    )

    print(f"  - 玩家: {context.player.name}")
    print(f"  - 触发类型: {context.trigger_type}")
    print(f"  - 物品配置: {context.item_config}")
    print(f"  - 数量: {context.quantity}")
    print(f"  - 上下文类型: {context.context_type}")
    print(f"  - 元数据: {context.metadata}")

    assert context.player.name == "测试玩家", "应该包含正确的player"
    assert context.trigger_type == TriggerType.ON_USE, "应该包含正确的触发类型"
    assert context.quantity == 3, "应该包含正确的数量"
    print("  ✅ EffectContext测试通过")

    # 测试EffectResult
    print("\n3.2 测试EffectResult:")
    result = EffectResult(
        success=True,
        message="效果生效",
        attribute_changes={"hp": 100, "mp": 50},
        status_changes=["添加buff: 攻击力+10%"],
        extra_data={"duration": 3}
    )

    print(f"  - 成功: {result.success}")
    print(f"  - 消息: {result.message}")
    print(f"  - 属性变化: {result.attribute_changes}")
    print(f"  - 状态变化: {result.status_changes}")
    print(f"  - 额外数据: {result.extra_data}")

    assert result.success is True, "应该标记为成功"
    assert result.attribute_changes["hp"] == 100, "应该包含正确的属性变化"
    assert len(result.status_changes) == 1, "应该包含状态变化"
    print("  ✅ EffectResult测试通过")


async def test_inheritance():
    """测试4: 继承和多态"""
    print("\n" + "=" * 60)
    print("测试4: 继承和多态")
    print("=" * 60)

    # 测试多态
    print("\n4.1 测试多态:")
    effects: list[IEffect] = [
        TestRestoreHPEffect(),
        TestLifestealEffect()
    ]

    for effect in effects:
        print(f"  - 效果ID: {effect.effect_id}")
        print(f"    类型: {type(effect).__name__}")
        print(f"    是否IEffect: {isinstance(effect, IEffect)}")

        assert isinstance(effect, IEffect), f"{effect.effect_id}应该是IEffect实例"

    print("  ✅ 多态测试通过")


async def main():
    """运行所有测试"""
    print("\n🧪 效果系统接口测试")
    print("=" * 60)
    print("测试范围: IEffect接口、注册中心、基类")
    print("=" * 60)

    try:
        # 运行测试
        await test_basic_interface()
        await test_registry()
        await test_context_and_result()
        await test_inheritance()

        # 总结
        print("\n" + "=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
        print("\n✅ 第1阶段接口验证成功")
        print("✅ IEffect接口工作正常")
        print("✅ EffectRegistry注册中心工作正常")
        print("✅ BaseItemEffect/BaseBattleEffect基类工作正常")
        print("✅ EffectContext/EffectResult数据结构正常")
        print("\n🚀 可以继续第2阶段：物品效果适配器实现")

    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"❌ 测试失败: {e}")
        print("=" * 60)
        return False
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ 发生错误: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
