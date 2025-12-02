"""
新效果系统集成模块

提供便捷的函数，将旧的apply_effect调用替换为新系统
支持Feature Flag控制切换
"""

import os
from typing import Tuple, Any, Dict
from nonebot import logger, get_driver

from ..registry import get_effect_registry
from ..interfaces import EffectContext, TriggerType


# Feature Flag: 控制是否使用新效果系统
# 从 NoneBot 配置中读取，支持 .env 文件配置
def _get_feature_flag() -> bool:
    """从配置中读取 Feature Flag"""
    try:
        config = get_driver().config
        # NoneBot会自动将USE_NEW_EFFECT_SYSTEM转换为use_new_effect_system
        return getattr(config, "use_new_effect_system", False)
    except:
        # 降级到环境变量读取
        return os.getenv("USE_NEW_EFFECT_SYSTEM", "false").lower() == "true"

# 导出 Feature Flag（供其他模块使用）
USE_NEW_EFFECT_SYSTEM = _get_feature_flag()



async def apply_effect_v2(
    player: Any,
    item_config: Any,
    quantity: int = 1,
    ctx: object = "world",
    session=None
) -> Tuple[bool, str]:
    """
    使用新效果系统执行物品效果（与旧接口兼容）

    这是apply_effect的v2版本，使用新的IEffect接口执行效果

    Args:
        player: Player实例
        item_config: ItemConfig实例
        quantity: 使用数量
        ctx: 使用场景（"world"、"battle"或自定义dict）
        session: 数据库会话

    Returns:
        Tuple[bool, str]: (success, message) 与旧版本格式相同

    使用示例:
    ```python
    # 替换旧代码
    # success, msg = await apply_effect(player, item_cfg, qty, ctx, session)

    # 新代码
    success, msg = await apply_effect_v2(player, item_cfg, qty, ctx, session)
    ```
    """
    from plugins.xiuxian_game.models.inventory import ItemEffectType

    # 生成effect_id
    effect_id = f"item_{item_config.effect_type.name.lower()}"

    logger.debug(
        f"[EffectSystem v2] 执行物品效果: "
        f"effect_id={effect_id}, item={item_config.item_id}, qty={quantity}"
    )

    # 获取注册中心
    registry = get_effect_registry()

    # 检查是否已注册
    if registry.get_class(effect_id) is None:
        logger.warning(
            f"[EffectSystem v2] 效果 {effect_id} 未注册，回退到旧系统"
        )
        # 回退到旧系统
        from plugins.xiuxian_game.item.item_effects import apply_effect as apply_effect_legacy
        return await apply_effect_legacy(player, item_config, quantity, ctx, session)

    try:
        # 创建效果实例
        effect = registry.create(effect_id)

        # 构建上下文
        context = EffectContext(
            player=player,
            session=session,
            trigger_type=TriggerType.ON_USE,
            item_config=item_config,
            quantity=quantity,
            context_type=ctx if isinstance(ctx, str) else "world",
            metadata=ctx if isinstance(ctx, dict) else {}
        )

        # 执行效果
        result = await effect.execute(context)

        logger.debug(
            f"[EffectSystem v2] 效果执行完成: "
            f"success={result.success}, message={result.message}"
        )

        # 返回与旧版本兼容的格式
        return result.success, result.message

    except Exception as e:
        logger.error(f"[EffectSystem v2] 效果执行失败: {e}")
        # 发生异常时回退到旧系统
        from plugins.xiuxian_game.item.item_effects import apply_effect as apply_effect_legacy
        logger.warning("[EffectSystem v2] 异常，回退到旧系统")
        return await apply_effect_legacy(player, item_config, quantity, ctx, session)


async def apply_effect_with_fallback(
    player: Any,
    item_config: Any,
    quantity: int = 1,
    ctx: object = "world",
    session=None
) -> Tuple[bool, str]:
    """
    智能选择新旧效果系统（带Feature Flag）

    根据环境变量 USE_NEW_EFFECT_SYSTEM 决定使用新系统还是旧系统
    - true: 优先使用新系统，失败时回退到旧系统
    - false: 直接使用旧系统

    Args:
        player: Player实例
        item_config: ItemConfig实例
        quantity: 使用数量
        ctx: 使用场景
        session: 数据库会话

    Returns:
        Tuple[bool, str]: (success, message)

    使用示例:
    ```python
    # 在inventory.py中替换
    success, msg = await apply_effect_with_fallback(
        player, item_config, quantity, ctx_payload, session
    )
    ```
    """
    if USE_NEW_EFFECT_SYSTEM:
        # 使用新系统
        logger.debug("[EffectSystem] Feature Flag: 使用新效果系统")
        return await apply_effect_v2(player, item_config, quantity, ctx, session)
    else:
        # 使用旧系统
        logger.debug("[EffectSystem] Feature Flag: 使用旧效果系统")
        from plugins.xiuxian_game.item.item_effects import apply_effect as apply_effect_legacy
        return await apply_effect_legacy(player, item_config, quantity, ctx, session)


def get_effect_system_status() -> Dict[str, Any]:
    """
    获取效果系统状态信息（用于监控和调试）

    Returns:
        Dict: 状态信息
        {
            "use_new_system": bool,
            "registered_effects": int,
            "registry_status": str
        }
    """
    from .register_all import get_registered_adapters

    adapters = get_registered_adapters()
    registry = get_effect_registry()
    all_effects = registry.list_all()

    return {
        "use_new_system": USE_NEW_EFFECT_SYSTEM,
        "registered_adapters": len(adapters),
        "total_effects": len(all_effects),
        "adapter_ids": list(adapters.keys()) if adapters else [],
        "feature_flag_env": os.getenv("USE_NEW_EFFECT_SYSTEM", "not set")
    }
