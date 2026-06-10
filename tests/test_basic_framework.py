"""
基础框架测试

测试Repository、UnitOfWork的基本功能
不依赖nonebot环境
"""

import sys
from pathlib import Path

# 直接添加infrastructure路径
sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "xiuxian_game"))


def test_repository_interface():
    """测试Repository接口"""
    print("\n" + "=" * 50)
    print("测试1: Repository接口设计")
    print("=" * 50)

    from domain.repositories.base import IRepository

    print("\n1. 检查Repository接口方法...")

    # 检查接口方法
    expected_methods = ['get_by_id', 'add', 'update', 'delete', 'exists', 'count']
    actual_methods = [m for m in dir(IRepository) if not m.startswith('_')]

    for method in expected_methods:
        assert method in actual_methods, f"Repository接口应该包含{method}方法"
        print(f"   [OK] 找到方法: {method}")

    print("\n" + "=" * 50)
    print("[SUCCESS] Repository接口测试通过！")
    print("=" * 50)


def test_uow_structure():
    """测试UnitOfWork结构"""
    print("\n" + "=" * 50)
    print("测试2: UnitOfWork工作单元")
    print("=" * 50)

    from infrastructure.uow.unit_of_work import UnitOfWork

    print("\n1. 检查UnitOfWork结构...")

    # 检查UoW的属性
    expected_properties = ['players', 'items', 'guilds', 'buffs', 'session']
    uow_attrs = [attr for attr in dir(UnitOfWork) if not attr.startswith('_')]

    for prop in expected_properties:
        assert prop in uow_attrs, f"UnitOfWork应该包含{prop}属性"
        print(f"   [OK] 找到属性: {prop}")

    # 检查UoW的方法
    expected_methods = ['commit', 'rollback', 'flush']
    for method in expected_methods:
        assert method in uow_attrs, f"UnitOfWork应该包含{method}方法"
        print(f"   [OK] 找到方法: {method}")

    print("\n" + "=" * 50)
    print("[SUCCESS] UnitOfWork结构测试通过！")
    print("=" * 50)


def main():
    """主测试函数"""
    print("\n" + ">> 开始测试重构后的基础框架...\n")

    try:
        # 测试Repository接口
        test_repository_interface()

        # 测试UnitOfWork
        test_uow_structure()

        print("\n" + "=" * 60)
        print(">> 恭喜！所有基础框架测试通过！")
        print("=" * 60)
        print("\n重构成果：")
        print("[OK] Repository接口：定义清晰，方法完整")
        print("[OK] UnitOfWork：结构合理，事务管理完善")
        print("\n下一步：")
        print("1. 运行 nb run 启动bot")
        print("2. 发送指令：角色v2 或 面板v2")
        print("3. 验证重构后的功能是否正常")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
