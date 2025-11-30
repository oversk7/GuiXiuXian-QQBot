"""
物品效果服务 - DI架构版本

提供物品效果执行的统一入口，支持依赖注入和Repository抽象
"""

from typing import Tuple, Dict, Any, Optional
from ..models.player import Player
from ..models.inventory import ItemConfig, ItemEffectType
from ..domain.effects import EffectContext, EffectResult, TriggerType
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.buff_repository import BuffRepository
from ..infrastructure.repositories.elixir_usage_repository import ElixirUsageRepository
from ..infrastructure.repositories.vip_equipment_bonus_repository import (
    VIPEquipmentBonusRepository,
)

# 导入旧的注册表（向后兼容）
from .item_effects import _REGISTRY

# 导入复杂效果Service
from .sweep_dungeon_service import SweepDungeonService
from .reset_attr_service import ResetAttrService
from .world_boss_chest_service import WorldBossChestService


class ItemEffectService:
    """
    物品效果服务类（DI架构）

    设计原则：
    1. 通过构造函数注入Repository依赖
    2. 为复杂效果（SWEEP_DUNGEON、RESET_ATTR、WORLD_BOSS_CHEST）提供Service集成点
    3. 简单效果暂时保持调用旧的效果处理函数（渐进式迁移）
    4. 使用EffectContext和EffectResult统一接口
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        item_repo: ItemRepository,
        buff_repo: BuffRepository,
        elixir_usage_repo: ElixirUsageRepository,
        vip_equipment_bonus_repo: VIPEquipmentBonusRepository,
    ):
        """
        初始化物品效果服务

        Args:
            player_repo: 玩家仓储
            item_repo: 物品仓储
            buff_repo: Buff仓储
            elixir_usage_repo: 丹药使用记录仓储
            vip_equipment_bonus_repo: VIP装备加成仓储
        """
        self._player_repo = player_repo
        self._item_repo = item_repo
        self._buff_repo = buff_repo
        self._elixir_usage_repo = elixir_usage_repo
        self._vip_equipment_bonus_repo = vip_equipment_bonus_repo

        # 复杂效果Service（构造函数注入，自动创建）
        # 注：EquipmentService需要在运行时创建，因为它可能依赖Feature Flag
        from .equipment_service_new import EquipmentService
        equipment_service = EquipmentService(
            item_repo=item_repo,
            player_repo=player_repo
        )

        self._sweep_dungeon_service = SweepDungeonService(
            player_repo=player_repo,
            item_repo=item_repo,
            equipment_service=equipment_service
        )
        self._reset_attr_service = ResetAttrService(
            player_repo=player_repo,
            item_repo=item_repo,
            elixir_usage_repo=elixir_usage_repo,
            vip_equipment_bonus_repo=vip_equipment_bonus_repo
        )
        self._world_boss_chest_service = WorldBossChestService(
            player_repo=player_repo,
            item_repo=item_repo
        )

    async def apply_effect(
        self,
        player: Player,
        item_cfg: ItemConfig,
        quantity: int = 1,
        ctx: object = "world",
    ) -> EffectResult:
        """
        执行物品效果（DI架构入口）

        Args:
            player: 目标玩家实例
            item_cfg: 物品配置
            quantity: 使用数量
            ctx: 使用场景或额外参数（"world"、"battle"，或字典）

        Returns:
            EffectResult: 效果执行结果

        Note:
            - 复杂效果（SWEEP_DUNGEON等）调用独立Service
            - 简单效果暂时调用旧的效果处理函数（通过_REGISTRY）
            - 后续将逐步迁移所有效果到Repository架构
        """
        # 检查是否为复杂效果，调用对应Service
        if item_cfg.effect_type == ItemEffectType.SWEEP_DUNGEON:
            return await self._sweep_dungeon_service.execute(
                player, item_cfg, quantity, str(ctx)
            )
        elif item_cfg.effect_type == ItemEffectType.RESET_ATTR:
            return await self._reset_attr_service.execute(
                player, item_cfg, quantity, str(ctx)
            )
        elif item_cfg.effect_type == ItemEffectType.WORLD_BOSS_CHEST:
            return await self._world_boss_chest_service.execute(
                player, item_cfg, quantity, str(ctx)
            )

        # 简单效果：查找旧的效果处理函数
        handler = _REGISTRY.get(item_cfg.effect_type)
        if not handler:
            return EffectResult(
                success=False,
                message="❓ 该道具效果尚未实现",
            )

        # 调用旧的效果处理函数（需要session参数）
        # 临时方案：从Repository获取session
        session = self._player_repo._session

        # 执行旧的效果处理函数
        success, message = await handler(player, item_cfg, quantity, ctx, session)

        # 转换为EffectResult格式
        return EffectResult(
            success=success,
            message=message,
        )

    async def apply_effect_with_context(
        self, context: EffectContext
    ) -> EffectResult:
        """
        使用EffectContext执行物品效果（统一接口）

        Args:
            context: 效果执行上下文

        Returns:
            EffectResult: 效果执行结果

        Note:
            此方法提供统一的IEffect接口兼容入口
        """
        return await self.apply_effect(
            player=context.player,
            item_cfg=context.item_config,
            quantity=context.quantity,
            ctx=context.context_type,
        )
