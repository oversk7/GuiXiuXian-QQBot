"""
测试DI容器

验证依赖注入容器的基本功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from plugins.xiuxian_game.infrastructure.di import DIContainer, ServiceLifetime


def pytest_raises(expected_exception, match_pattern=None):
    """简单的异常捕获上下文管理器"""
    class ExceptionContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                raise AssertionError(f"Expected {expected_exception.__name__} but no exception was raised")
            if not issubclass(exc_type, expected_exception):
                return False  # 让异常继续传播
            if match_pattern and match_pattern not in str(exc_val):
                raise AssertionError(f"Exception message '{exc_val}' does not contain '{match_pattern}'")
            return True  # 抑制异常

    return ExceptionContext()


# 替换pytest.raises
raises = pytest_raises


def test_di_container_singleton():
    """测试单例服务"""
    container = DIContainer()

    # 注册单例服务
    container.register_singleton(str, lambda c: "singleton_instance")

    # 解析两次，应该返回同一个实例
    instance1 = container.resolve(str)
    instance2 = container.resolve(str)

    assert instance1 == instance2
    assert instance1 is instance2


def test_di_container_transient():
    """测试瞬时服务"""
    container = DIContainer()

    # 注册瞬时服务（每次都创建新对象）
    counter = {"value": 0}

    def create_instance(c):
        counter["value"] += 1
        return f"instance_{counter['value']}"

    container.register_transient(str, create_instance)

    # 解析两次，应该返回不同的实例
    instance1 = container.resolve(str)
    instance2 = container.resolve(str)

    assert instance1 != instance2
    assert instance1 == "instance_1"
    assert instance2 == "instance_2"


def test_di_container_scoped():
    """测试作用域服务"""
    container = DIContainer()

    # 注册作用域服务
    container.register_scoped(str, lambda c: "scoped_instance")

    # 在同一个作用域内，应该返回同一个实例
    instance1 = container.resolve(str)
    instance2 = container.resolve(str)

    assert instance1 == instance2
    assert instance1 is instance2


def test_di_container_dependency_injection():
    """测试依赖注入"""
    container = DIContainer()

    # 定义服务接口
    class IService:
        def get_name(self):
            pass

    class Service(IService):
        def get_name(self):
            return "ServiceImpl"

    class Consumer:
        def __init__(self, service: IService):
            self.service = service

        def get_message(self):
            return f"Using: {self.service.get_name()}"

    # 注册服务
    container.register_singleton(IService, lambda c: Service())
    container.register_transient(Consumer, lambda c: Consumer(c.resolve(IService)))

    # 解析消费者（自动注入依赖）
    consumer = container.resolve(Consumer)

    assert consumer.get_message() == "Using: ServiceImpl"


def test_di_container_unregistered_service():
    """测试未注册的服务"""
    container = DIContainer()

    # 尝试解析未注册的服务，应该抛出异常
    with raises(ValueError, "服务"):
        container.resolve(str)


def test_di_container_create_scope():
    """测试创建作用域"""
    parent_container = DIContainer()

    # 在父容器中注册单例
    parent_container.register_singleton(str, lambda c: "parent_singleton")

    # 创建子作用域
    scoped_container = parent_container.create_scope()

    # 子作用域应该共享父容器的单例
    parent_instance = parent_container.resolve(str)
    scoped_instance = scoped_container.resolve(str)

    assert parent_instance == scoped_instance
    assert parent_instance is scoped_instance


if __name__ == "__main__":
    # 运行测试
    print("运行DI容器测试...")

    test_di_container_singleton()
    print("✅ 单例服务测试通过")

    test_di_container_transient()
    print("✅ 瞬时服务测试通过")

    test_di_container_scoped()
    print("✅ 作用域服务测试通过")

    test_di_container_dependency_injection()
    print("✅ 依赖注入测试通过")

    test_di_container_unregistered_service()
    print("✅ 未注册服务测试通过")

    test_di_container_create_scope()
    print("✅ 创建作用域测试通过")

    print("\n🎉 所有测试通过！")
