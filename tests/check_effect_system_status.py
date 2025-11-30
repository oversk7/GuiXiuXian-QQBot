"""
新效果系统状态检查脚本

简单检查当前效果系统的注册状态
不需要完整初始化NoneBot

运行方式:
    cd D:/QQbot/GuiXiuXian2
    .venv/Scripts/python.exe tests/check_effect_system_status.py
"""

import sys
from pathlib import Path

# 设置UTF-8输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("\n" + "=" * 80)
print("新效果系统状态检查")
print("=" * 80)

# 检查注册状态
try:
    # 这些模块应该不会触发NoneBot初始化
    from plugins.xiuxian_game.domain.effects.adapters.register_all import (
        get_registered_adapters
    )
    from plugins.xiuxian_game.domain.effects.adapters.battle_effect_register import (
        get_registered_bridges,
        get_bridge_count,
        get_equipment_bridge_mapping,
        get_bridge_statistics
    )

    print("\n[1] 物品效果适配器状态")
    print("-" * 80)
    adapters = get_registered_adapters()
    print(f"注册数量: {len(adapters)} 个")
    print("已注册适配器ID:")
    for effect_id in sorted(adapters.keys()):
        print(f"  - {effect_id}")

    print("\n[2] 战斗效果桥接器状态")
    print("-" * 80)
    bridges = get_registered_bridges()
    bridge_count = get_bridge_count()
    print(f"注册数量: {bridge_count} 个")

    print("\n装备到桥接器映射:")
    equipment_mapping = get_equipment_bridge_mapping()
    for item_id, effect_ids in sorted(equipment_mapping.items()):
        print(f"  {item_id} ({len(effect_ids)}个效果):")
        for effect_id in effect_ids:
            print(f"    - {effect_id}")

    print("\n统计信息:")
    stats = get_bridge_statistics()
    print(f"  总桥接器数: {stats['total_bridges']}")
    print(f"  总装备数: {stats['total_equipment']}")
    print(f"  平均效果数/装备: {stats['avg_effects_per_equipment']}")

    print("\n[3] Feature Flag状态")
    print("-" * 80)
    try:
        from plugins.xiuxian_game.domain.effects.adapters.integration import (
            USE_NEW_EFFECT_SYSTEM
        )
        print(f"USE_NEW_EFFECT_SYSTEM = {USE_NEW_EFFECT_SYSTEM}")

        if USE_NEW_EFFECT_SYSTEM:
            print("状态: [已启用] 新效果系统")
        else:
            print("状态: [未启用] 使用旧效果系统")
    except Exception as e:
        print(f"无法获取Feature Flag状态: {e}")

    print("\n" + "=" * 80)
    print("[成功] 效果系统状态检查完成")
    print("=" * 80)
    print(f"\n总结:")
    print(f"  ✓ 物品效果适配器: {len(adapters)} 个")
    print(f"  ✓ 战斗效果桥接器: {bridge_count} 个")
    print(f"  ✓ 涉及装备: {stats['total_equipment']} 个")
    print(f"  ✓ Feature Flag: {'已启用' if USE_NEW_EFFECT_SYSTEM else '未启用'}")
    print()

except Exception as e:
    print(f"\n[错误] 状态检查失败:")
    print(f"  {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
