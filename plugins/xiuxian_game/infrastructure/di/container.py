"""
依赖注入容器实现

基于 REFACTORING_PLAN_v4.md 第2.1节的设计
"""

from typing import Dict, Type, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ServiceLifetime(Enum):
    """服务生命周期"""
    SINGLETON = "singleton"  # 单例：整个应用生命周期内只创建一次
    SCOPED = "scoped"        # 作用域：每个作用域（如每个请求）创建一次
    TRANSIENT = "transient"  # 瞬时：每次解析都创建新实例


@dataclass
class ServiceDescriptor:
    """服务描述符"""
    service_type: Type          # 服务类型（通常是接口或抽象类）
    implementation: Callable    # 实现工厂函数
    lifetime: ServiceLifetime   # 生命周期


class DIContainer:
    """
    依赖注入容器

    负责管理服务的注册、解析和生命周期。

    使用示例:
    ```python
    # 创建容器
    container = DIContainer()

    # 注册服务
    container.register_singleton(IPlayerRepository, lambda c: PlayerRepository(c.resolve(AsyncSession)))
    container.register_scoped(AsyncSession, lambda c: create_session())

    # 解析服务
    player_repo = container.resolve(IPlayerRepository)
    ```
    """

    def __init__(self):
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scoped_instances: Dict[Type, Any] = {}  # 当前作用域的实例

    def register_singleton(self, service_type: Type, factory: Callable[[Any], Any]):
        """
        注册单例服务

        Args:
            service_type: 服务类型（接口）
            factory: 工厂函数，接收容器作为参数，返回服务实例
        """
        self._services[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation=factory,
            lifetime=ServiceLifetime.SINGLETON
        )

    def register_scoped(self, service_type: Type, factory: Callable[[Any], Any]):
        """
        注册作用域服务

        Args:
            service_type: 服务类型（接口）
            factory: 工厂函数，接收容器作为参数，返回服务实例
        """
        self._services[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation=factory,
            lifetime=ServiceLifetime.SCOPED
        )

    def register_transient(self, service_type: Type, factory: Callable[[Any], Any]):
        """
        注册瞬时服务

        Args:
            service_type: 服务类型（接口）
            factory: 工厂函数，接收容器作为参数，返回服务实例
        """
        self._services[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation=factory,
            lifetime=ServiceLifetime.TRANSIENT
        )

    def resolve(self, service_type: Type) -> Any:
        """
        解析服务实例

        Args:
            service_type: 服务类型

        Returns:
            服务实例

        Raises:
            ValueError: 如果服务未注册
        """
        descriptor = self._services.get(service_type)
        if not descriptor:
            raise ValueError(
                f"服务 {service_type.__name__} 未注册。"
                f"请先调用 register_singleton/register_scoped/register_transient 注册服务。"
            )

        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            # 单例：全局唯一实例
            if service_type not in self._singletons:
                self._singletons[service_type] = descriptor.implementation(self)
            return self._singletons[service_type]

        elif descriptor.lifetime == ServiceLifetime.SCOPED:
            # 作用域：当前作用域内唯一实例
            if service_type not in self._scoped_instances:
                self._scoped_instances[service_type] = descriptor.implementation(self)
            return self._scoped_instances[service_type]

        else:  # TRANSIENT
            # 瞬时：每次都创建新实例
            return descriptor.implementation(self)

    def create_scope(self) -> 'DIContainer':
        """
        创建新的作用域容器

        Returns:
            新的作用域容器，继承父容器的服务注册
        """
        scoped_container = DIContainer()
        scoped_container._services = self._services.copy()
        scoped_container._singletons = self._singletons  # 单例共享
        return scoped_container

    def clear_scope(self):
        """清除当前作用域的实例（用于作用域结束时）"""
        self._scoped_instances.clear()

    def is_registered(self, service_type: Type) -> bool:
        """检查服务是否已注册"""
        return service_type in self._services

    def get_descriptor(self, service_type: Type) -> Optional[ServiceDescriptor]:
        """获取服务描述符"""
        return self._services.get(service_type)
