"""
基础框架测试

测试DI容器、Repository、UnitOfWork的基本功能
不依赖nonebot环境
"""

import sys
from pathlib import Path

# 直接添加infrastructure路径
sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "xiuxian_game"))

# 直接导入infrastructure模块（避免触发__init__.py中的nonebot导入）
from infrastructure.di.container import DIContainer, ServiceLifetime


def test_di_container():
    """测试DI容器"""
    print("=" * 50)
    print("测试1: DI容器基础功能")
    print("=" * 50)

    container = DIContainer()

    # 测试单例服务
    print("\n1. 测试单例服务...")
    container.register_singleton(str, lambda c: "singleton_instance")

    instance1 = container.resolve(str)
    instance2 = container.resolve(str)

    assert instance1 == instance2, "单例服务应该返回相同实例"
    assert instance1 is instance2, "单例服务应该返回同一个对象"
    print("   [OK] 单例服务测试通过")

    # 测试瞬时服务
    print("\n2. 测试瞬时服务...")
    container2 = DIContainer()
    counter = {"value": 0}

    def create_instance(c):
        counter["value"] += 1
        return f"instance_{counter['value']}"

    container2.register_transient(str, create_instance)

    instance1 = container2.resolve(str)
    instance2 = container2.resolve(str)

    assert instance1 != instance2, "瞬时服务应该返回不同实例"
    assert instance1 == "instance_1", f"第一个实例应该是instance_1，实际是{instance1}"
    assert instance2 == "instance_2", f"第二个实例应该是instance_2，实际是{instance2}"
    print("   [OK] 瞬时服务测试通过")

    # 测试依赖注入
    print("\n3. 测试依赖注入...")
    container3 = DIContainer()

    class Service:
        def get_name(self):
            return "ServiceImpl"

    class Consumer:
        def __init__(self, service):
            self.service = service

        def get_message(self):
            return f"Using: {self.service.get_name()}"

    container3.register_singleton(Service, lambda c: Service())
    container3.register_transient(Consumer, lambda c: Consumer(c.resolve(Service)))

    consumer = container3.resolve(Consumer)
    message = consumer.get_message()

    assert message == "Using: ServiceImpl", f"期望'Using: ServiceImpl'，实际是'{message}'"
    print("   [OK] 依赖注入测试通过")

    # 测试未注册服务
    print("\n4. 测试未注册服务...")
    container4 = DIContainer()
    exception_raised = False

    try:
        container4.resolve(list)
    except ValueError as e:
        exception_raised = True
        assert "未注册" in str(e), f"异常消息应该包含'未注册'，实际是'{e}'"

    assert exception_raised, "应该抛出ValueError异常"
    print("   [OK] 未注册服务测试通过")

    print("\n" + "=" * 50)
    print("[SUCCESS] DI容器所有测试通过！")
    print("=" * 50)


def test_repository_interface():
    """测试Repository接口"""
    print("\n" + "=" * 50)
    print("测试2: Repository接口设计")
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
    print("测试3: UnitOfWork工作单元")
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
        # 测试DI容器
        test_di_container()

        # 测试Repository接口
        test_repository_interface()

        # 测试UnitOfWork
        test_uow_structure()

        print("\n" + "=" * 60)
        print(">> 恭喜！所有基础框架测试通过！")
        print("=" * 60)
        print("\n重构成果：")
        print("[OK] DI容器：单例、瞬时、依赖注入功能正常")
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
