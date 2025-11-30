"""
物品效果适配器

将旧的item_effects.py中的效果函数适配到新的IEffect接口
保持向后兼容，支持渐进式迁移
"""

from typing import Callable, Awaitable, Tuple, Any, Dict
from nonebot import logger

from ..interfaces import IEffect, BaseItemEffect, EffectContext, EffectResult, TriggerType


# 旧效果函数的类型签名
LegacyEffectHandler = Callable[
    [Any, Any, int, object, object],  # player, cfg, qty, ctx, session
    Awaitable[Tuple[bool, str]]       # (success, message)
]


class ItemEffectAdapter(BaseItemEffect):
    """
    物品效果适配器基类

    将旧的效果函数签名适配到新的IEffect接口

    旧签名:
        async def handler(player, cfg, qty, ctx, session) -> (bool, str)

    新接口:
        async def execute(context: EffectContext) -> EffectResult

    使用示例:
    ```python
    # 旧效果函数
    async def _restore_hp(player, cfg, qty, ctx, session):
        value = cfg.effect_params.get("value", 0) * qty
        player.hp = min(player.hp + value, player.max_hp)
        return True, f"恢复了{value}点生命值"

    # 包装为新接口
    RestoreHPEffect = wrap_legacy_item_effect(
        effect_id="item_restore_hp",
        legacy_handler=_restore_hp
    )

    # 注册到新系统
    register_effect("item_restore_hp")(RestoreHPEffect)
    ```
    """

    def __init__(
        self,
        effect_id: str,
        legacy_handler: LegacyEffectHandler,
        description: str = ""
    ):
        """
        初始化适配器

        Args:
            effect_id: 效果唯一标识
            legacy_handler: 旧的效果处理函数
            description: 效果描述
        """
        super().__init__(effect_id)
        self._legacy_handler = legacy_handler
        self._description = description

    @property
    def description(self) -> str:
        return self._description or f"Legacy effect: {self.effect_id}"

    def can_trigger(self, context: EffectContext) -> bool:
        """
        判断是否可以触发

        物品效果通常在ON_USE时触发
        """
        return context.trigger_type == TriggerType.ON_USE

    async def execute(self, context: EffectContext) -> EffectResult:
        """
        执行效果（适配旧函数签名）

        Args:
            context: 效果上下文

        Returns:
            EffectResult: 效果执行结果
        """
        # 提取旧函数需要的参数
        player = context.player
        item_cfg = context.item_config
        quantity = context.quantity or 1
        ctx = context.context_type or "world"
        session = context.session

        logger.debug(
            f"[ItemEffectAdapter] 适配旧效果 {self.effect_id}: "
            f"player={player.id}, item={item_cfg.item_id if item_cfg else 'None'}, qty={quantity}"
        )

        try:
            # 调用旧的效果函数
            success, message = await self._legacy_handler(
                player, item_cfg, quantity, ctx, session
            )

            logger.debug(
                f"[ItemEffectAdapter] 旧效果 {self.effect_id} 执行完成: "
                f"success={success}, message={message}"
            )

            # 包装为新的返回格式
            return EffectResult(
                success=success,
                message=message,
                # 旧函数不返回详细的属性变化，只能从message推断
                attribute_changes={},
                status_changes=[],
                extra_data={"legacy": True}
            )

        except Exception as e:
            logger.error(
                f"[ItemEffectAdapter] 旧效果 {self.effect_id} 执行失败: {e}"
            )
            return EffectResult(
                success=False,
                message=f"[ERROR] 效果执行失败: {str(e)}",
                attribute_changes={},
                status_changes=[],
                extra_data={"error": str(e)}
            )


def wrap_legacy_item_effect(
    effect_id: str,
    legacy_handler: LegacyEffectHandler,
    description: str = ""
) -> type[ItemEffectAdapter]:
    """
    工厂函数：将旧的效果函数包装为新的IEffect类

    Args:
        effect_id: 效果唯一标识
        legacy_handler: 旧的效果处理函数
        description: 效果描述

    Returns:
        ItemEffectAdapter子类

    使用示例:
    ```python
    from item.item_effects import _restore_hp
    from domain.effects import register_effect

    # 创建适配器类
    RestoreHPEffect = wrap_legacy_item_effect(
        effect_id="item_restore_hp",
        legacy_handler=_restore_hp,
        description="恢复固定值生命"
    )

    # 注册到新系统
    register_effect("item_restore_hp")(RestoreHPEffect)

    # 使用新接口
    registry = get_effect_registry()
    effect = registry.create("item_restore_hp", legacy_handler=_restore_hp)
    result = await effect.execute(context)
    ```
    """

    class WrappedEffect(ItemEffectAdapter):
        """动态生成的适配器类"""

        def __init__(self):
            super().__init__(effect_id, legacy_handler, description)

    # 设置类名以便调试
    WrappedEffect.__name__ = f"Wrapped{effect_id.replace('_', '').title()}Effect"
    WrappedEffect.__qualname__ = WrappedEffect.__name__

    return WrappedEffect


def create_adapter_for_all_legacy_effects() -> Dict[str, type[ItemEffectAdapter]]:
    """
    批量创建所有旧效果的适配器

    自动扫描item_effects.py中的所有注册效果，为每个效果创建适配器

    Returns:
        Dict[effect_id, AdapterClass]: 效果ID到适配器类的映射

    使用示例:
    ```python
    # 自动创建所有适配器
    adapters = create_adapter_for_all_legacy_effects()

    # 批量注册到新系统
    for effect_id, adapter_class in adapters.items():
        register_effect(effect_id)(adapter_class)
    ```
    """
    from plugins.xiuxian_game.item.item_effects import _REGISTRY
    from plugins.xiuxian_game.models.inventory import ItemEffectType

    adapters = {}

    for effect_type, handler in _REGISTRY.items():
        # 生成effect_id（将枚举名转换为小写下划线格式）
        effect_id = f"item_{effect_type.name.lower()}"

        # 创建适配器
        adapter_class = wrap_legacy_item_effect(
            effect_id=effect_id,
            legacy_handler=handler,
            description=f"Legacy effect: {effect_type.name}"
        )

        adapters[effect_id] = adapter_class

        logger.debug(f"[AdapterFactory] 为旧效果 {effect_type.name} 创建适配器: {effect_id}")

    logger.info(f"[AdapterFactory] 成功创建 {len(adapters)} 个物品效果适配器")

    return adapters
