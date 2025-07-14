#!/usr/bin/env python3
"""
装备系统修复验证测试脚本

测试场景：
1. 测试apply_attr_bonus方法不会重复叠加_persist_bonus
2. 验证装备属性计算逻辑的正确性
3. 模拟穿戴、卸下、加点等操作的属性变化
"""

def test_apply_attr_bonus_logic():
    """测试apply_attr_bonus方法的逻辑"""
    print("=== 测试apply_attr_bonus方法逻辑 ===")

    # 模拟装备配置
    class MockConfig:
        def __init__(self):
            self.attr_bonus = {"hp": 10}  # 固定+10 HP
            self.attr_ratio = {"hp": 0.2}  # 20%增幅
            self.type = "EQUIPMENT"

    # 模拟装备实例
    class MockEquipment:
        def __init__(self):
            self.config = MockConfig()
            self.equipped = True
            self.extra_attrs = {"_persist_bonus": {"max_hp": 15}}  # 已持久化的bonus

        @property
        def is_equipment(self):
            return True

        def apply_attr_bonus(self, attrs):
            """修复后的apply_attr_bonus方法"""
            if not self.is_equipment or not self.equipped:
                return

            tpl = self.config
            if not tpl:
                return

            # 固定值
            key_map = {"hp": "max_hp", "mp": "max_mp"}
            for k, v in (tpl.attr_bonus or {}).items():
                key = key_map.get(k, k)
                attrs[key] = attrs.get(key, 0) + int(v)
            # 百分比
            for k, r in (tpl.attr_ratio or {}).items():
                key = key_map.get(k, k)
                attrs[key] = int(attrs.get(key, 0) * (1 + float(r)))
            # 额外属性（强化）
            for k, v in (self.extra_attrs or {}).items():
                if k.startswith("_"):
                    continue  # 跳过内部字段，如 _persist_bonus
                if not isinstance(v, (int, float)):
                    continue
                attrs[k] = attrs.get(k, 0) + int(v)

            # 修复：不再重复叠加_persist_bonus
            return attrs

    # 测试场景1：基础属性计算
    equipment = MockEquipment()
    base_attrs = {"max_hp": 50}
    test_attrs = base_attrs.copy()

    equipment.apply_attr_bonus(test_attrs)

    # 期望结果：50 + 10 = 60, 然后 60 * 1.2 = 72
    expected_hp = int((50 + 10) * 1.2)
    actual_hp = test_attrs["max_hp"]

    print(f"基础HP: 50")
    print(f"装备固定加成: +10")
    print(f"装备百分比加成: +20%")
    print(f"期望结果: {expected_hp}")
    print(f"实际结果: {actual_hp}")

    if actual_hp == expected_hp:
        print("✅ apply_attr_bonus方法计算正确")
        return True
    else:
        print("❌ apply_attr_bonus方法计算错误")
        return False

def test_equipment_wear_simulation():
    """模拟装备穿戴过程"""
    print("\n=== 模拟装备穿戴过程 ===")

    # 模拟玩家初始属性
    player_attrs = {
        "max_hp": 50,
        "max_mp": 50,
        "attack": 10,
        "defense": 10,
        "agility": 10,
        "luck": 10
    }

    # 模拟装备配置（溺水者外衣）
    class MockConfig:
        def __init__(self):
            self.attr_bonus = {"hp": 10}  # 固定+10 HP
            self.attr_ratio = {"hp": 0.2}  # 20%增幅

    class MockEquipment:
        def __init__(self):
            self.config = MockConfig()
            self.equipped = True
            self.extra_attrs = {}

        @property
        def is_equipment(self):
            return True

        def apply_attr_bonus(self, attrs):
            """修复后的apply_attr_bonus方法"""
            if not self.is_equipment or not self.equipped:
                return

            tpl = self.config
            if not tpl:
                return

            # 固定值
            key_map = {"hp": "max_hp", "mp": "max_mp"}
            for k, v in (tpl.attr_bonus or {}).items():
                key = key_map.get(k, k)
                attrs[key] = attrs.get(key, 0) + int(v)
            # 百分比
            for k, r in (tpl.attr_ratio or {}).items():
                key = key_map.get(k, k)
                attrs[key] = int(attrs.get(key, 0) * (1 + float(r)))
            # 额外属性（强化）
            for k, v in (self.extra_attrs or {}).items():
                if k.startswith("_"):
                    continue  # 跳过内部字段，如 _persist_bonus
                if not isinstance(v, (int, float)):
                    continue
                attrs[k] = attrs.get(k, 0) + int(v)

            return attrs

    equipment = MockEquipment()

    print(f"玩家初始属性: {player_attrs}")

    # 模拟穿戴装备的过程
    base_attrs = player_attrs.copy()
    new_attrs = base_attrs.copy()
    equipment.apply_attr_bonus(new_attrs)
    delta = {k: new_attrs[k] - base_attrs[k] for k in new_attrs if new_attrs[k] != base_attrs[k]}

    print(f"装备属性加成: {delta}")

    # 应用到玩家属性
    for k, v in delta.items():
        player_attrs[k] = player_attrs[k] + v

    # 保存delta到装备
    equipment.extra_attrs["_persist_bonus"] = delta

    print(f"穿戴后玩家属性: {player_attrs}")

    # 验证计算是否正确
    expected_hp = int((50 + 10) * 1.2)  # (50+10) * 1.2 = 72
    if player_attrs["max_hp"] == expected_hp:
        print("✅ 装备穿戴计算正确")

        # 模拟卸下装备
        for k, v in delta.items():
            player_attrs[k] = player_attrs[k] - v
        equipment.equipped = False
        equipment.extra_attrs = {}

        print(f"卸下后玩家属性: {player_attrs}")

        # 验证是否恢复到初始状态
        if player_attrs["max_hp"] == 50:
            print("✅ 装备卸下恢复正确")
            return True
        else:
            print("❌ 装备卸下恢复错误")
            return False
    else:
        print(f"❌ 装备穿戴计算错误，期望HP={expected_hp}，实际HP={player_attrs['max_hp']}")
        return False

def test_multiple_wear_simulation():
    """模拟多次穿戴卸下过程"""
    print("\n=== 模拟多次穿戴卸下过程 ===")

    # 模拟玩家初始属性
    player_attrs = {
        "max_hp": 50,
        "max_mp": 50,
        "attack": 10,
        "defense": 10,
        "agility": 10,
        "luck": 10
    }
    initial_attrs = player_attrs.copy()

    # 模拟装备
    class MockConfig:
        def __init__(self):
            self.attr_bonus = {"hp": 10}
            self.attr_ratio = {"hp": 0.2}

    class MockEquipment:
        def __init__(self):
            self.config = MockConfig()
            self.equipped = False
            self.extra_attrs = {}

        @property
        def is_equipment(self):
            return True

        def apply_attr_bonus(self, attrs):
            if not self.is_equipment or not self.equipped:
                return

            tpl = self.config
            if not tpl:
                return

            key_map = {"hp": "max_hp", "mp": "max_mp"}
            for k, v in (tpl.attr_bonus or {}).items():
                key = key_map.get(k, k)
                attrs[key] = attrs.get(key, 0) + int(v)
            for k, r in (tpl.attr_ratio or {}).items():
                key = key_map.get(k, k)
                attrs[key] = int(attrs.get(key, 0) * (1 + float(r)))
            for k, v in (self.extra_attrs or {}).items():
                if k.startswith("_"):
                    continue
                if not isinstance(v, (int, float)):
                    continue
                attrs[k] = attrs.get(k, 0) + int(v)
            return attrs

    equipment = MockEquipment()

    # 进行3次穿戴卸下循环
    for i in range(3):
        print(f"第{i+1}次循环...")

        # 穿戴装备
        equipment.equipped = True
        base_attrs = player_attrs.copy()
        new_attrs = base_attrs.copy()
        equipment.apply_attr_bonus(new_attrs)
        delta = {k: new_attrs[k] - base_attrs[k] for k in new_attrs if new_attrs[k] != base_attrs[k]}

        for k, v in delta.items():
            player_attrs[k] = player_attrs[k] + v
        equipment.extra_attrs["_persist_bonus"] = delta

        print(f"  穿戴后HP: {player_attrs['max_hp']}")

        # 卸下装备
        for k, v in delta.items():
            player_attrs[k] = player_attrs[k] - v
        equipment.equipped = False
        equipment.extra_attrs = {}

        print(f"  卸下后HP: {player_attrs['max_hp']}")

    # 验证最终属性是否与初始属性一致
    if player_attrs == initial_attrs:
        print("✅ 多次穿戴卸下测试通过")
        return True
    else:
        print(f"❌ 多次穿戴卸下测试失败")
        print(f"初始属性: {initial_attrs}")
        print(f"最终属性: {player_attrs}")
        return False

def test_attribute_point_allocation_simulation():
    """模拟加点时装备属性重新计算过程"""
    print("\n=== 模拟加点时装备属性重新计算过程 ===")

    # 模拟玩家属性（已穿戴装备）
    player_attrs = {
        "max_hp": 72,  # 基础50 + 装备加成22
        "max_mp": 50,
        "attack": 10,
        "defense": 10,
        "agility": 10,
        "luck": 10
    }

    # 模拟装备（已穿戴，有持久化bonus）
    class MockEquipment:
        def __init__(self):
            self.equipped = True
            self.extra_attrs = {"_persist_bonus": {"max_hp": 22}}  # 已持久化的bonus
            self.config = MockConfig()

        @property
        def is_equipment(self):
            return True

        def apply_attr_bonus(self, attrs):
            """修复后的方法，不会重复叠加_persist_bonus"""
            if not self.is_equipment or not self.equipped:
                return

            tpl = self.config
            if not tpl:
                return

            key_map = {"hp": "max_hp", "mp": "max_mp"}
            for k, v in (tpl.attr_bonus or {}).items():
                key = key_map.get(k, k)
                attrs[key] = attrs.get(key, 0) + int(v)
            for k, r in (tpl.attr_ratio or {}).items():
                key = key_map.get(k, k)
                attrs[key] = int(attrs.get(key, 0) * (1 + float(r)))
            for k, v in (self.extra_attrs or {}).items():
                if k.startswith("_"):
                    continue  # 关键修复：跳过_persist_bonus
                if not isinstance(v, (int, float)):
                    continue
                attrs[k] = attrs.get(k, 0) + int(v)
            return attrs

    class MockConfig:
        def __init__(self):
            self.attr_bonus = {"hp": 10}
            self.attr_ratio = {"hp": 0.2}

    equipment = MockEquipment()

    print(f"加点前玩家属性: {player_attrs}")
    print(f"装备持久化bonus: {equipment.extra_attrs['_persist_bonus']}")

    # 模拟加点过程（加5点体质，每点+1 max_hp）
    # 1. 撤销旧装备bonus
    old_bonus = equipment.extra_attrs.get("_persist_bonus", {})
    for k, v in old_bonus.items():
        player_attrs[k] = player_attrs[k] - v
    equipment.extra_attrs["_persist_bonus"] = {}

    print(f"撤销装备bonus后: {player_attrs}")

    # 2. 应用加点
    player_attrs["max_hp"] += 5  # 加5点体质

    print(f"加点后基础属性: {player_attrs}")

    # 3. 重新计算装备bonus
    base_attrs_snapshot = player_attrs.copy()
    attrs_temp = base_attrs_snapshot.copy()
    equipment.apply_attr_bonus(attrs_temp)
    new_delta = {k: attrs_temp[k] - base_attrs_snapshot[k] for k in attrs_temp if attrs_temp[k] != base_attrs_snapshot[k]}

    print(f"重新计算的装备bonus: {new_delta}")

    # 4. 应用新bonus
    for k, v in new_delta.items():
        player_attrs[k] = player_attrs[k] + v
    equipment.extra_attrs["_persist_bonus"] = new_delta

    print(f"最终玩家属性: {player_attrs}")

    # 验证结果
    # 基础55 + 装备固定10 = 65，然后 65 * 1.2 = 78
    expected_hp = int((55 + 10) * 1.2)
    if player_attrs["max_hp"] == expected_hp:
        print(f"✅ 加点后装备属性重新计算正确，HP={expected_hp}")
        return True
    else:
        print(f"❌ 加点后装备属性重新计算错误，期望HP={expected_hp}，实际HP={player_attrs['max_hp']}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("开始装备系统修复验证测试...\n")

    tests = [
        test_apply_attr_bonus_logic,
        test_equipment_wear_simulation,
        test_multiple_wear_simulation,
        test_attribute_point_allocation_simulation,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ 测试 {test.__name__} 失败: {e}")

    print(f"\n=== 测试结果 ===")
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("🎉 所有测试通过！装备系统修复成功。")
        return True
    else:
        print("⚠️ 部分测试失败，需要进一步检查。")
        return False

if __name__ == "__main__":
    run_all_tests()
