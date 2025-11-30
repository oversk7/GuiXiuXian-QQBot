"""
仓储基础接口

基于 REFACTORING_PLAN_v4.md 第2.2节的设计
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Any


T = TypeVar('T')  # 实体类型


class IRepository(ABC, Generic[T]):
    """
    仓储接口（抽象基类）

    定义了所有仓储的通用操作。
    具体的仓储接口应继承此接口并添加特定的查询方法。

    类型参数:
        T: 实体类型（如 Player, Guild, ItemInstance 等）

    使用示例:
    ```python
    class IPlayerRepository(IRepository[Player]):
        @abstractmethod
        async def get_by_uid(self, uid: str) -> Optional[Player]:
            pass

        @abstractmethod
        async def get_nearby_players(
            self, x: int, y: int, region: str, max_distance: int
        ) -> List[Player]:
            pass
    ```
    """

    @abstractmethod
    async def get_by_id(self, id: Any) -> Optional[T]:
        """
        根据ID获取实体

        Args:
            id: 实体ID

        Returns:
            实体对象，如果不存在则返回 None
        """
        pass

    @abstractmethod
    async def add(self, entity: T) -> T:
        """
        添加新实体

        Args:
            entity: 要添加的实体

        Returns:
            添加后的实体（可能包含自动生成的ID）
        """
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:
        """
        更新实体

        Args:
            entity: 要更新的实体

        Returns:
            更新后的实体
        """
        pass

    @abstractmethod
    async def delete(self, id: Any) -> bool:
        """
        删除实体

        Args:
            id: 要删除的实体ID

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    async def exists(self, id: Any) -> bool:
        """
        检查实体是否存在

        Args:
            id: 实体ID

        Returns:
            是否存在
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """
        获取实体总数

        Returns:
            实体数量
        """
        pass
