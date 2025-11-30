"""
物品效果适配器独立测试

使用动态导入绕过NoneBot依赖
"""

import sys
import asyncio
import importlib.util
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ============ 动态加载模块 ============

def load_module_from_file(module_name, file_path):
    """动态加载模块，绕过包的__init__.py"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 加载效果系统模块
effects_dir = project_root / "plugins" / "xiuxian_game" / "domain" / "effects"

# 加载interfaces模块
interfaces = load_module_from_file(
    "effects.interfaces",
    effects_dir / "interfaces.py"
)

# 加载registry模块（需要修改相对导入）
with open(effects_dir / "registry.py", "r", encoding="utf-8") as f:
    registry_code = f.read()
registry_code = registry_code.replace(
    "from .interfaces import",
    "from effects.interfaces import"
)
registry_module = type(sys)("effects.registry")
exec(compile(registry_code, str(effects_dir / "registry.py"), "exec"), registry_module.__dict__)
sys.modules["effects.registry"] = registry_module

# 加载适配器模块
adapters_dir = effects_dir / "adapters"
with open(adapters_dir / "item_effect_adapter.py", "r", encoding="utf-8") as f:
    adapter_code = f.read()
adapter_code = adapter_code.replace(
    "from ..interfaces import",
    "from effects.interfaces import"
)
# 移除nonebot日志导入
adapter_code = adapter_code.replace(
    "from nonebot import logger",
    "# logger disabled"
)
adapter_code = adapter_code.replace(
    "logger.debug(",
    "print("
)
adapter_code = adapter_code.replace(
    "logger.info(",
    "print("
)
adapter_code = adapter_code.replace(
    "logger.error(",
    "print("
)

adapter_module = type(sys)("effects.adapters.item_effect_adapter")
exec(compile(adapter_code, str(adapters_dir / "item_effect_adapter.py"), "exec"), adapter_module.__dict__)
sys.modules["effects.adapters.item_effect_adapter"] = adapter_module

# 导入需要的类
IEffect = interfaces.IEffect
BaseItemEffect = interfaces.BaseItemEffect
EffectContext = interfaces.EffectContext
EffectResult = interfaces.EffectResult
TriggerType = interfaces.TriggerType
get_effect_registry = registry_module.get_effect_registry
register_effect = registry_module.register_effect
ItemEffectAdapter = adapter_module.ItemEffectAdapter
wrap_legacy_item_effect = adapter_module.wrap_legacy_item_effect


# ============ Mock对象 ============

@dataclass
class MockPlayer:
    """模拟Player对象"""
    id: str = "test_player_123"
    hp: int = 50
    max_hp: int = 100


@dataclass
class MockItemConfig:
    """模拟ItemConfig对象"""
    item_id: str
    effect_params: Dict[str, Any]


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
    assert player.hp == 90, f"HP应该增加40 (20 * 2), 实际是{player.hp}"
    assert "测试效果生效" in result.message, "消息应该包含旧函数返回的文本"

    print("[OK] 测试1通过: wrap_legacy_item_effect 工作正常\n")


async def test_multiple_adapters():
    """测试2: 创建多个适配器"""
    print("=" * 60)
    print("测试2: 创建多个适配器实例")
    print("=" * 60)

    # 创建多个不同的旧效果函数
    async def _restore_hp(player, cfg, qty, ctx, session):
        value = cfg.effect_params.get("value", 0) * qty
        player.hp = min(player.hp + value, player.max_hp)
        return True, f"恢复了{value}点生命值"

    async def _restore_mp(player, cfg, qty, ctx, session):
        value = cfg.effect_params.get("value", 0) * qty
        # 假设player有mp属性
        return True, f"恢复了{value}点理智值"

    # 包装为适配器
    RestoreHPAdapter = wrap_legacy_item_effect("item_restore_hp", _restore_hp)
    RestoreMPAdapter = wrap_legacy_item_effect("item_restore_mp", _restore_mp)

    # 注册到系统
    register_effect("item_restore_hp")(RestoreHPAdapter)
    register_effect("item_restore_mp")(RestoreMPAdapter)

    registry = get_effect_registry()
    all_effects = registry.list_all()

    print(f"\n[OK] 已注册效果:")
    for effect_id in all_effects:
        print(f"  - {effect_id}")

    assert "item_restore_hp" in all_effects
    assert "item_restore_mp" in all_effects

    # 测试创建实例
    hp_effect = registry.create("item_restore_hp")
    mp_effect = registry.create("item_restore_mp")

    print(f"\n[OK] 创建实例成功:")
    print(f"  - HP效果: {hp_effect.effect_id}")
    print(f"  - MP效果: {mp_effect.effect_id}")

    print("[OK] 测试2通过: 多个适配器创建成功\n")


async def test_adapter_error_handling():
    """测试3: 适配器错误处理"""
    print("=" * 60)
    print("测试3: 适配器错误处理")
    print("=" * 60)

    # 创建一个会抛出异常的旧效果函数
    async def _error_effect(player, cfg, qty, ctx, session):
        raise ValueError("测试异常")

    ErrorAdapter = wrap_legacy_item_effect("test_error", _error_effect)
    error_effect = ErrorAdapter()

    # 创建上下文
    player = MockPlayer()
    item_cfg = MockItemConfig(item_id="error_item", effect_params={})

    context = EffectContext(
        player=player,
        session=None,
        trigger_type=TriggerType.ON_USE,
        item_config=item_cfg,
        quantity=1
    )

    # 执行效果
    result = await error_effect.execute(context)

    print(f"\n执行结果:")
    print(f"  - Success: {result.success} (应该是False)")
    print(f"  - Message: {result.message}")
    print(f"  - Extra Data: {result.extra_data}")

    assert result.success is False, "异常时应该返回失败"
    assert "测试异常" in str(result.extra_data.get("error", "")), "应该记录异常信息"

    print("[OK] 测试3通过: 错误处理正确\n")


# ============ 主测试函数 ============

async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("[TEST] 物品效果适配器独立测试")
    print("=" * 60)
    print("测试范围: ItemEffectAdapter适配器")
    print("=" * 60)

    try:
        await test_wrap_legacy_effect()
        await test_multiple_adapters()
        await test_adapter_error_handling()

        # 总结
        print("=" * 60)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 60)
        print("\n[OK] ItemEffectAdapter 适配器工作正常")
        print("[OK] 旧效果函数成功适配到新接口")
        print("[OK] 错误处理正确")
        print("\n[READY] 可以继续集成到生产代码")

        return True

    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"[FAIL] 测试失败: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
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
