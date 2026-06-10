"""
NPC管理服务（DI重构版本）

基于 REFACTORING_PLAN_v4.md 的DI架构重构
支持AI Agent NPC接口预留
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..infrastructure.repositories.npc_repository import NPCRepository
from ..models.npc import NPC, NPCType, NPCStatus


class NPCService:
    """
    NPC管理服务类（重构后的DI版本）

    改进点：
    1. 使用依赖注入，接收NPCRepository而非直接操作Session
    2. 移除内部commit()，遵循事务边界控制原则
    3. 所有数据访问方法转为instance方法
    4. 纯工具函数保留为@staticmethod
    5. 预留AI Agent NPC接口
    """

    def __init__(
        self,
        session: AsyncSession,
        npc_repo: NPCRepository = None,
    ):
        """
        初始化NPC服务

        Args:
            session: 数据库会话（由safe_session()或UnitOfWork传入）
            npc_repo: NPC仓储（若无则自动创建）
        """
        self._session = session
        self._npc_repo = npc_repo or NPCRepository(session)

    # ==================== 查询方法 ====================

    async def get_npc_by_id(self, npc_id: str) -> Optional[NPC]:
        """
        根据ID获取NPC

        Args:
            npc_id: NPC唯一标识

        Returns:
            NPC对象，如果不存在则返回None
        """
        return await self._npc_repo.get_by_id(npc_id)

    async def get_npc_by_name(self, name: str, location_id: int = None) -> Optional[NPC]:
        """
        根据名称获取NPC（可指定地点）

        Args:
            name: NPC名称
            location_id: 可选，限定地点ID

        Returns:
            NPC对象，如果不存在则返回None
        """
        return await self._npc_repo.get_by_name(name, location_id)

    async def get_npcs_by_location(
        self,
        location_id: int,
        npc_type: NPCType = None,
        include_dead: bool = False
    ) -> List[NPC]:
        """
        获取指定地点的NPC

        Args:
            location_id: 地点ID
            npc_type: 可选，NPC类型过滤
            include_dead: 是否包含死亡NPC，默认False

        Returns:
            NPC列表
        """
        return await self._npc_repo.get_by_location(location_id, npc_type, include_dead)

    async def get_npcs_by_type(
        self,
        npc_type: NPCType,
        region: str = None
    ) -> List[NPC]:
        """
        根据类型获取NPC

        Args:
            npc_type: NPC类型
            region: 可选，区域过滤

        Returns:
            NPC列表
        """
        return await self._npc_repo.get_by_type(npc_type, region)

    async def find_npc_by_partial_name(
        self,
        partial_name: str,
        location_id: int = None
    ) -> List[NPC]:
        """
        根据部分名称查找NPC

        Args:
            partial_name: 部分名称（模糊匹配）
            location_id: 可选，限定地点ID

        Returns:
            匹配的NPC列表
        """
        return await self._npc_repo.find_by_partial_name(partial_name, location_id)

    async def get_dynamic_npcs(self, location_id: int = None) -> List[NPC]:
        """
        获取动态生成的NPC

        Args:
            location_id: 可选，限定地点ID

        Returns:
            动态NPC列表
        """
        return await self._npc_repo.get_dynamic_npcs(location_id)

    # ==================== 创建方法 ====================

    async def create_npc(
        self,
        npc_id: str,
        name: str,
        npc_type: NPCType,
        location_id: int,
        description: str = None,
        **kwargs
    ) -> NPC:
        """
        创建新NPC

        Args:
            npc_id: NPC唯一标识
            name: NPC名称
            npc_type: NPC类型
            location_id: 地点ID
            description: 描述
            **kwargs: 其他属性

        Returns:
            创建的NPC对象
        """
        npc = NPC(
            npc_id=npc_id,
            name=name,
            npc_type=npc_type,
            location_id=location_id,
            description=description or f"{name}，一个{npc_type.value}",
            **kwargs
        )
        return await self._npc_repo.create(npc)

    async def create_merchant_npc(
        self,
        npc_id: str,
        name: str,
        location_id: int,
        market_items: List[str] = None
    ) -> NPC:
        """
        创建商人NPC

        Args:
            npc_id: NPC唯一标识
            name: NPC名称
            location_id: 地点ID
            market_items: 可选，出售的物品列表

        Returns:
            创建的商人NPC
        """
        npc = NPC.create_merchant(npc_id, name, location_id, market_items)
        return await self._npc_repo.create(npc)

    async def create_craftsman_npc(
        self,
        npc_id: str,
        name: str,
        location_id: int
    ) -> NPC:
        """
        创建工匠NPC

        Args:
            npc_id: NPC唯一标识
            name: NPC名称
            location_id: 地点ID

        Returns:
            创建的工匠NPC
        """
        npc = NPC.create_craftsman(npc_id, name, location_id)
        return await self._npc_repo.create(npc)

    async def create_employer_npc(
        self,
        npc_id: str,
        name: str,
        location_id: int,
        available_jobs: Dict = None
    ) -> NPC:
        """
        创建雇主NPC

        Args:
            npc_id: NPC唯一标识
            name: NPC名称
            location_id: 地点ID
            available_jobs: 可选，可提供的工作配置

        Returns:
            创建的雇主NPC
        """
        npc = NPC.create_employer(npc_id, name, location_id, available_jobs)
        return await self._npc_repo.create(npc)

    async def create_ghost_npc(
        self,
        npc_id: str,
        name: str,
        location_id: int,
        level: int,
        hp: int,
        attack: int,
        defense: int,
        agility: int
    ) -> NPC:
        """
        创建鬼怪NPC

        Args:
            npc_id: NPC唯一标识
            name: NPC名称
            location_id: 地点ID
            level: 等级
            hp: 血量
            attack: 攻击力
            defense: 防御力
            agility: 敏捷

        Returns:
            创建的鬼怪NPC
        """
        npc = NPC.create_ghost(npc_id, name, location_id, level, hp, attack, defense, agility)
        return await self._npc_repo.create(npc)

    # ==================== 操作方法 ====================

    async def kill_npc(self, npc_id: str) -> bool:
        """
        击杀NPC

        Args:
            npc_id: NPC唯一标识

        Returns:
            是否击杀成功
        """
        return await self._npc_repo.kill(npc_id)

    async def respawn_npc(self, npc_id: str) -> bool:
        """
        复活NPC

        Args:
            npc_id: NPC唯一标识

        Returns:
            是否复活成功
        """
        return await self._npc_repo.respawn(npc_id)

    async def check_and_respawn_npcs(self) -> int:
        """
        检查并复活到期的NPC

        Returns:
            复活的NPC数量
        """
        npcs = await self._npc_repo.get_respawning_npcs()

        respawned_count = 0
        for npc in npcs:
            if npc.respawn():
                respawned_count += 1

        return respawned_count

    async def update_npc(self, npc_id: str, **kwargs) -> Optional[NPC]:
        """
        更新NPC信息

        Args:
            npc_id: NPC唯一标识
            **kwargs: 要更新的属性

        Returns:
            更新后的NPC，如果不存在则返回None
        """
        npc = await self._npc_repo.get_by_id(npc_id)
        if not npc:
            return None

        for key, value in kwargs.items():
            if hasattr(npc, key):
                setattr(npc, key, value)

        return await self._npc_repo.update(npc)

    async def delete_npc(self, npc_id: str) -> bool:
        """
        删除NPC（软删除）

        Args:
            npc_id: NPC唯一标识

        Returns:
            是否删除成功
        """
        return await self._npc_repo.delete(npc_id)

    async def cleanup_expired_dynamic_npcs(self, max_age_hours: int = 24) -> int:
        """
        清理过期的动态NPC

        Args:
            max_age_hours: 最大存活时间（小时），默认24小时

        Returns:
            清理的NPC数量
        """
        return await self._npc_repo.cleanup_expired_dynamic(max_age_hours)

    # ==================== 交互方法 ====================

    async def get_npc_interaction_info(self, npc: NPC) -> Dict[str, Any]:
        """
        获取NPC交互信息

        Args:
            npc: NPC对象

        Returns:
            交互信息字典
        """
        if npc.is_dead() or npc.is_respawning():
            return {
                "can_interact": False,
                "status": "unavailable",
                "message": f"{npc.name}当前不可用"
            }

        interaction_info = {
            "can_interact": True,
            "status": "available",
            "npc": npc,
            "functions": []
        }

        # 根据NPC类型添加可用功能
        if npc.npc_type == NPCType.MERCHANT:
            interaction_info["functions"].append({
                "name": "trade",
                "display": "交易",
                "description": "与商人进行物品交易"
            })
        elif npc.npc_type == NPCType.CRAFTSMAN:
            interaction_info["functions"].extend([
                {
                    "name": "forge",
                    "display": "锻造",
                    "description": "锻造新装备"
                },
                {
                    "name": "enhance",
                    "display": "强化",
                    "description": "强化现有装备"
                },
                {
                    "name": "gem_socket",
                    "display": "镶嵌",
                    "description": "镶嵌宝石"
                }
            ])
        elif npc.npc_type == NPCType.EMPLOYER:
            interaction_info["functions"].append({
                "name": "part_time_job",
                "display": "打工",
                "description": "寻找工作机会"
            })
        elif npc.npc_type == NPCType.GHOST:
            interaction_info["functions"].append({
                "name": "battle",
                "display": "战斗",
                "description": "与鬼怪战斗"
            })

        return interaction_info

    # ==================== AI Agent NPC相关预留方法 ====================

    def is_ai_enabled(self, npc: NPC) -> bool:
        """
        检查NPC是否启用AI对话（预留）

        Args:
            npc: NPC对象

        Returns:
            是否启用AI
        """
        if not npc.extra_data:
            return False
        return npc.extra_data.get("ai_enabled", False)

    def get_ai_personality(self, npc: NPC) -> Optional[Dict[str, Any]]:
        """
        获取NPC的AI性格配置（预留）

        Args:
            npc: NPC对象

        Returns:
            AI性格配置字典，如果未启用AI则返回None
        """
        if not npc.extra_data or not self.is_ai_enabled(npc):
            return None
        return npc.extra_data.get("ai_personality")

    def get_ai_model(self, npc: NPC) -> str:
        """
        获取NPC使用的AI模型（预留）

        Args:
            npc: NPC对象

        Returns:
            AI模型名称，默认为"glm-4.5-flash"
        """
        if not npc.extra_data:
            return "glm-4.5-flash"  # 默认模型
        return npc.extra_data.get("ai_model", "glm-4.5-flash")

    def get_ai_forbidden_topics(self, npc: NPC) -> List[str]:
        """
        获取NPC的禁忌话题列表（预留）

        Args:
            npc: NPC对象

        Returns:
            禁忌话题列表
        """
        if not npc.extra_data:
            return []
        return npc.extra_data.get("ai_forbidden_topics", [])

    async def enable_ai_for_npc(
        self,
        npc_id: str,
        ai_config: Dict[str, Any]
    ) -> bool:
        """
        为NPC启用AI对话（预留）

        Args:
            npc_id: NPC唯一标识
            ai_config: AI配置字典，包含:
                - ai_model: AI模型名称
                - ai_personality: 性格配置
                - ai_forbidden_topics: 禁忌话题列表
                - ai_response_style: 响应风格配置

        Returns:
            是否启用成功
        """
        npc = await self._npc_repo.get_by_id(npc_id)
        if not npc:
            return False

        if not npc.extra_data:
            npc.extra_data = {}

        npc.extra_data["ai_enabled"] = True
        npc.extra_data.update(ai_config)

        await self._npc_repo.update(npc)
        return True

    # ==================== 纯工具函数（保留@staticmethod） ====================

    @staticmethod
    def format_npc_list(npcs: List[NPC]) -> str:
        """
        格式化NPC列表显示

        Args:
            npcs: NPC列表

        Returns:
            格式化后的字符串
        """
        if not npcs:
            return "暂无NPC"

        lines = []
        for npc in npcs:
            status_info = ""
            if npc.is_dead():
                status_info = "[已死亡]"
            elif npc.is_respawning():
                remaining = npc.respawn_time - datetime.now()
                minutes = int(remaining.total_seconds() / 60)
                status_info = f"[复活中:{minutes}分钟]"

            hint = npc.get_interaction_hint()
            lines.append(f"{npc.name}{status_info}{hint}")

        return "\n".join(lines)
