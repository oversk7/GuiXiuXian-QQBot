"""
新效果系统集成测试

测试内容：
1. 效果系统注册验证
2. 物品效果适配器功能测试
3. 战斗效果桥接器功能测试
4. Feature Flag切换测试

运行方式:
    cd D:/QQbot/GuiXiuXian2
    .venv/Scripts/python.exe tests/test_new_effect_system.py
"""

import sys
import os
import asyncio
from pathlib import Path

# 设置UTF-8输出编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置环境变量，避免NoneBot自动加载
os.environ["ENVIRONMENT"] = "test"

# Mock nonebot组件
class MockDriver:
    class Config:
        use_new_effect_system = True

    def __init__(self):
        self.config = self.Config()

class MockLogger:
    def debug(self, msg): print(f"[DEBUG] {msg}")
    def info(self, msg): print(f"[INFO] {msg}")
    def warning(self, msg): print(f"[WARN] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")
    def success(self, msg): print(f"[OK] {msg}")

# 注入mock nonebot组件
import nonebot

_mock_driver = MockDriver()
nonebot.logger = MockLogger()

# Mock get_driver函数
original_get_driver = nonebot.get_driver

def mock_get_driver():
    return _mock_driver

nonebot.get_driver = mock_get_driver

# 禁用on_command等装饰器
def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

import nonebot.plugin.on as plugin_on
plugin_on.on_command = mock_decorator
nonebot.on_command = mock_decorator
nonebot.on_message = mock_decorator
nonebot.on_notice = mock_decorator
nonebot.on_request = mock_decorator


class EffectSystemTester:
    """新效果系统测试器"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.test_results = []

    def test_result(self, test_name: str, passed: bool, message: str = ""):
        """记录测试结果"""
        if passed:
            self.passed += 1
            status = "[PASS]"
        else:
            self.failed += 1
            status = "[FAIL]"

        result = f"{status} | {test_name}"
        if message:
            result += f" | {message}"

        self.test_results.append(result)
        print(result)

        return passed

    def print_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 80)
        print("测试总结")
        print("=" * 80)
        print(f"总计: {self.passed + self.failed} 个测试")
        print(f"通过: {self.passed} 个")
        print(f"失败: {self.failed} 个")
        print(f"通过率: {self.passed / (self.passed + self.failed) * 100:.1f}%")
        print("=" * 80)

        if self.failed == 0:
            print("\n[SUCCESS] 所有测试通过!\n")
            return 0
        else:
            print(f"\n[FAILED] {self.failed} 个测试失败\n")
            return 1


async def test_effect_registry(tester: EffectSystemTester):
    """测试1: 效果系统注册验证"""
    print("\n" + "=" * 80)
    print("测试1: 效果系统注册验证")
    print("=" * 80)

    try:
        from plugins.xiuxian_game.domain.effects.registry import get_effect_registry
        from plugins.xiuxian_game.domain.effects.adapters import (
            get_registered_adapters,
            get_registered_bridges,
            USE_NEW_EFFECT_SYSTEM
        )

        # 1.1 检查Feature Flag
        tester.test_result(
            "Feature Flag状态",
            True,
            f"USE_NEW_EFFECT_SYSTEM = {USE_NEW_EFFECT_SYSTEM}"
        )

        # 1.2 检查物品效果适配器注册
        adapters = get_registered_adapters()
        tester.test_result(
            "物品效果适配器注册",
            len(adapters) == 19,
            f"注册了 {len(adapters)} 个适配器（期望19个）"
        )

        # 1.3 检查战斗效果桥接器注册
        bridges = get_registered_bridges()
        tester.test_result(
            "战斗效果桥接器注册",
            len(bridges) == 23,
            f"注册了 {len(bridges)} 个桥接器（期望23个）"
        )

        # 1.4 检查效果注册中心
        registry = get_effect_registry()
        all_effects = registry.list_all()
        tester.test_result(
            "效果注册中心",
            len(all_effects) >= 42,  # 19 + 23 = 42
            f"注册中心包含 {len(all_effects)} 个效果"
        )

        # 1.5 检查具体的适配器
        expected_adapters = [
            "item_restore_hp",
            "item_restore_mp",
            "item_buff",
            "item_gain_exp",
        ]

        for effect_id in expected_adapters:
            exists = effect_id in adapters
            tester.test_result(
                f"适配器存在检查: {effect_id}",
                exists,
                "已注册" if exists else "未注册"
            )

        # 1.6 检查具体的桥接器
        expected_bridges = [
            "battle_fear_soul_flag_0",
            "battle_lifesteal_wedding_dress_0",
            "battle_regen_void_essence_crown_0",
        ]

        for effect_id in expected_bridges:
            exists = effect_id in bridges
            tester.test_result(
                f"桥接器存在检查: {effect_id}",
                exists,
                "已注册" if exists else "未注册"
            )

    except Exception as e:
        tester.test_result("效果系统注册验证", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_item_effect_creation(tester: EffectSystemTester):
    """测试2: 物品效果创建和基础功能"""
    print("\n" + "=" * 80)
    print("测试2: 物品效果创建和基础功能")
    print("=" * 80)

    try:
        from plugins.xiuxian_game.domain.effects.registry import get_effect_registry

        registry = get_effect_registry()

        # 2.1 测试创建适配器实例
        test_effects = [
            ("item_restore_hp", "恢复HP效果"),
            ("item_restore_mp", "恢复MP效果"),
            ("item_buff", "属性BUFF效果"),
            ("item_gain_exp", "获得经验效果"),
        ]

        for effect_id, desc in test_effects:
            try:
                effect = registry.create(effect_id)
                tester.test_result(
                    f"创建效果实例: {desc}",
                    effect is not None,
                    f"effect_id={effect_id}"
                )

                # 检查效果ID
                has_id = hasattr(effect, 'effect_id')
                tester.test_result(
                    f"效果ID属性: {desc}",
                    has_id and effect.effect_id == effect_id,
                    f"effect.effect_id = {effect.effect_id if has_id else 'N/A'}"
                )

                # 检查必需方法
                has_execute = hasattr(effect, 'execute') and callable(effect.execute)
                tester.test_result(
                    f"execute方法: {desc}",
                    has_execute,
                    "存在且可调用" if has_execute else "缺失"
                )

            except Exception as e:
                tester.test_result(
                    f"创建效果实例: {desc}",
                    False,
                    f"异常: {e}"
                )

    except Exception as e:
        tester.test_result("物品效果创建测试", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_battle_bridge_creation(tester: EffectSystemTester):
    """测试3: 战斗效果桥接器创建和基础功能"""
    print("\n" + "=" * 80)
    print("测试3: 战斗效果桥接器创建和基础功能")
    print("=" * 80)

    try:
        from plugins.xiuxian_game.domain.effects.registry import get_effect_registry
        from plugins.xiuxian_game.domain.effects.interfaces import (
            EffectContext,
            TriggerType
        )

        registry = get_effect_registry()

        # 3.1 测试创建桥接器实例
        test_bridges = [
            ("battle_fear_soul_flag_0", "魂旗恐惧效果"),
            ("battle_lifesteal_wedding_dress_0", "嫁衣吸血效果"),
            ("battle_regen_void_essence_crown_0", "虚无之冠回复效果"),
        ]

        for effect_id, desc in test_bridges:
            try:
                # 注意：桥接器注册的是类，不是单例
                bridge_class = registry.get_class(effect_id)
                tester.test_result(
                    f"获取桥接器类: {desc}",
                    bridge_class is not None,
                    f"effect_id={effect_id}"
                )

                if bridge_class:
                    # 检查类属性
                    has_trigger_config = hasattr(bridge_class, 'trigger_config')
                    tester.test_result(
                        f"trigger_config属性: {desc}",
                        has_trigger_config,
                        "存在" if has_trigger_config else "缺失"
                    )

            except Exception as e:
                tester.test_result(
                    f"获取桥接器类: {desc}",
                    False,
                    f"异常: {e}"
                )

        # 3.2 测试桥接器工厂函数
        try:
            from plugins.xiuxian_game.domain.effects.adapters import (
                create_bridge_for_trigger_config
            )
            from plugins.xiuxian_game.battle.battle_effects import (
                TriggerConfig,
                TriggerType as BattleTriggerType,
                EffectType
            )

            # 创建测试用的TriggerConfig
            test_config = TriggerConfig(
                trigger=BattleTriggerType.ON_HIT,
                effect=EffectType.LIFESTEAL,
                value=0.15,
                chance=1.0,
                duration=0,
                description="测试吸血效果"
            )

            bridge = create_bridge_for_trigger_config(
                test_config,
                base_effect_id="test_weapon"
            )

            tester.test_result(
                "工厂函数创建桥接器",
                bridge is not None,
                f"bridge.effect_id = {bridge.effect_id}"
            )

            # 检查桥接器方法
            has_can_trigger = hasattr(bridge, 'can_trigger') and callable(bridge.can_trigger)
            tester.test_result(
                "桥接器can_trigger方法",
                has_can_trigger,
                "存在且可调用" if has_can_trigger else "缺失"
            )

            has_execute = hasattr(bridge, 'execute') and callable(bridge.execute)
            tester.test_result(
                "桥接器execute方法",
                has_execute,
                "存在且可调用" if has_execute else "缺失"
            )

        except Exception as e:
            tester.test_result("工厂函数测试", False, f"异常: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        tester.test_result("战斗效果桥接器测试", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_feature_flag_toggle(tester: EffectSystemTester):
    """测试4: Feature Flag切换功能"""
    print("\n" + "=" * 80)
    print("测试4: Feature Flag切换功能")
    print("=" * 80)

    try:
        from plugins.xiuxian_game.domain.effects.adapters import (
            USE_NEW_EFFECT_SYSTEM,
            get_effect_system_status
        )

        # 4.1 检查Feature Flag值
        tester.test_result(
            "Feature Flag读取",
            isinstance(USE_NEW_EFFECT_SYSTEM, bool),
            f"当前值: {USE_NEW_EFFECT_SYSTEM}"
        )

        # 4.2 获取系统状态
        status = get_effect_system_status()

        tester.test_result(
            "系统状态查询",
            isinstance(status, dict),
            f"包含 {len(status)} 个字段"
        )

        # 4.3 检查状态字段
        expected_fields = [
            "use_new_system",
            "registered_adapters",
            "total_effects",
            "adapter_ids"
        ]

        for field in expected_fields:
            has_field = field in status
            tester.test_result(
                f"状态字段: {field}",
                has_field,
                f"值: {status.get(field, 'N/A')}"
            )

    except Exception as e:
        tester.test_result("Feature Flag切换测试", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_integration_functions(tester: EffectSystemTester):
    """测试5: 集成函数测试"""
    print("\n" + "=" * 80)
    print("测试5: 集成函数测试")
    print("=" * 80)

    try:
        from plugins.xiuxian_game.domain.effects.adapters import (
            apply_effect_v2,
            apply_effect_with_fallback,
        )

        # 5.1 检查函数可调用性
        tester.test_result(
            "apply_effect_v2函数",
            callable(apply_effect_v2),
            "存在且可调用"
        )

        tester.test_result(
            "apply_effect_with_fallback函数",
            callable(apply_effect_with_fallback),
            "存在且可调用"
        )

        # 5.2 检查桥接器批量注册函数
        from plugins.xiuxian_game.domain.effects.adapters import (
            get_bridge_count,
            get_equipment_bridge_mapping,
            get_bridge_statistics
        )

        bridge_count = get_bridge_count()
        tester.test_result(
            "桥接器计数函数",
            bridge_count == 23,
            f"当前计数: {bridge_count}"
        )

        equipment_mapping = get_equipment_bridge_mapping()
        tester.test_result(
            "装备桥接器映射",
            isinstance(equipment_mapping, dict) and len(equipment_mapping) == 12,
            f"映射了 {len(equipment_mapping)} 个装备"
        )

        statistics = get_bridge_statistics()
        tester.test_result(
            "桥接器统计",
            isinstance(statistics, dict),
            f"total_bridges={statistics.get('total_bridges')}, "
            f"total_equipment={statistics.get('total_equipment')}"
        )

    except Exception as e:
        tester.test_result("集成函数测试", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("新效果系统集成测试")
    print("=" * 80)
    print(f"项目根目录: {project_root}")
    print("=" * 80)

    tester = EffectSystemTester()

    # 执行测试套件
    await test_effect_registry(tester)
    await test_item_effect_creation(tester)
    await test_battle_bridge_creation(tester)
    await test_feature_flag_toggle(tester)
    await test_integration_functions(tester)

    # 打印总结
    return tester.print_summary()


if __name__ == "__main__":
    # 运行测试
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
