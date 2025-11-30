"""
属性计算器简化测试

不依赖数据库和nonebot环境，只测试核心数据结构和逻辑
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
plugins_path = project_root / "plugins" / "xiuxian_game"
sys.path.insert(0, str(plugins_path))

# 直接导入核心类（不导入BuffAttributeSource，避免sqlalchemy依赖）
from domain.attributes.interfaces import AttributeBonus, AttributeBreakdown


def test_attribute_bonus_add():
    """测试AttributeBonus加法运算"""
    print("\n测试1: AttributeBonus加法运算")

    bonus1 = AttributeBonus(attack=10, defense=5, hp=50)
    bonus2 = AttributeBonus(attack=20, defense=10, hp=100)

    result = bonus1 + bonus2

    assert result.attack == 30, f"期望attack=30，实际是{result.attack}"
    assert result.defense == 15, f"期望defense=15，实际是{result.defense}"
    assert result.hp == 150, f"期望hp=150，实际是{result.hp}"

    print("   [OK] AttributeBonus加法运算测试通过")


def test_attribute_bonus_dict_conversion():
    """测试AttributeBonus字典转换"""
    print("\n测试2: AttributeBonus字典转换")

    bonus = AttributeBonus(attack=100, defense=80, hp=1000, max_hp=1000)
    bonus_dict = bonus.to_dict()

    assert bonus_dict["attack"] == 100
    assert bonus_dict["defense"] == 80
    assert bonus_dict["hp"] == 1000

    # 从字典重建
    bonus2 = AttributeBonus.from_dict(bonus_dict)
    assert bonus2.attack == 100
    assert bonus2.defense == 80
    assert bonus2.hp == 1000

    print("   [OK] AttributeBonus字典转换测试通过")


def test_attribute_breakdown():
    """测试AttributeBreakdown"""
    print("\n测试3: AttributeBreakdown属性分解")

    base = AttributeBonus(attack=100, defense=80)
    equipment = AttributeBonus(attack=50, defense=40)
    buff = AttributeBonus(attack=20, defense=15)

    breakdown = AttributeBreakdown(
        base=base,
        equipment=equipment,
        buff=buff
    )

    breakdown.calculate_total()

    assert breakdown.total.attack == 170
    assert breakdown.total.defense == 135

    print("   [OK] AttributeBreakdown属性分解测试通过")


def test_attribute_bonus_multiplication():
    """测试multiplier属性"""
    print("\n测试4: Multiplier倍率属性")

    bonus1 = AttributeBonus(gold_multiplier=1.5, exp_multiplier=2.0)
    bonus2 = AttributeBonus(gold_multiplier=1.2, exp_multiplier=1.5)

    result = bonus1 + bonus2

    # 倍率属性应该相乘
    # 1.5 * 1.2 = 1.8，但需要考虑浮点数精度
    assert abs(result.gold_multiplier - 1.8) < 0.0001, f"期望1.8，实际是{result.gold_multiplier}"
    assert abs(result.exp_multiplier - 3.0) < 0.0001, f"期望3.0，实际是{result.exp_multiplier}"

    print("   [OK] Multiplier倍率属性测试通过")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print(">> 开始测试属性计算器核心数据结构...")
    print("=" * 60)

    try:
        test_attribute_bonus_add()
        test_attribute_bonus_dict_conversion()
        test_attribute_breakdown()
        test_attribute_bonus_multiplication()

        print("\n" + "=" * 60)
        print(">> 所有核心数据结构测试通过！")
        print("=" * 60)
        print("\n测试总结:")
        print("[OK] AttributeBonus加法运算")
        print("[OK] AttributeBonus字典转换（兼容旧代码）")
        print("[OK] AttributeBreakdown属性分解")
        print("[OK] Multiplier倍率属性（相乘）")
        print("\n重构成果:")
        print("1. 定义了清晰的AttributeBonus数据类")
        print("2. 支持+运算符组合属性加成")
        print("3. 提供to_dict/from_dict兼容旧代码")
        print("4. AttributeBreakdown支持详细分解展示")
        print("\n下一步:")
        print("- 在实际运行环境测试BuffAttributeSource缓存")
        print("- 集成到Player.get_effective_attributes")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
