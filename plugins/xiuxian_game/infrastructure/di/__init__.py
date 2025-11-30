"""
依赖注入模块

提供轻量级的依赖注入容器实现
"""

from .container import DIContainer, ServiceDescriptor, ServiceLifetime
from .setup import setup_di_container, get_container, reset_container

__all__ = [
    'DIContainer',
    'ServiceDescriptor',
    'ServiceLifetime',
    'setup_di_container',
    'get_container',
    'reset_container',
]
