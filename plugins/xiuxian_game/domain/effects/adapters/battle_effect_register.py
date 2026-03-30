"""
战斗效果桥接器批量注册

从装备配置中自动创建和注册所有战斗效果桥接器
"""

from typing import Dict, List, Type
from nonebot import logger

from .battle_effect_bridge import BattleEffectBridge, create_bridge_for_trigger_config
from ..registry import get_effect_registry
from plugins.xiuxian_game.battle.battle_effects import (
    parse_triggers_from_yaml,
    TriggerConfig,
)


# 全局注册表：保存已注册的桥接器
_registered_bridges: Dict[str, Type[BattleEffectBridge]] = {}


def create_bridges_from_equipment_config(
    item_id: str,
    item_name: str,
    special_effects: List[Dict]
) -> List[BattleEffectBridge]:
    """
    从单个装备配置创建战斗效果桥接器

    Args:
        item_id: 装备ID（如"drawer", "wedding_dress"）
        item_name: 装备名称（如"抽屉", "嫁衣"）
        special_effects: 特殊效果配置列表（来自YAML）

    Returns:
        List[BattleEffectBridge]: 创建的桥接器列表

    示例：
        ```python
        # 从YAML配置
        special_effects = [
            {
                "trigger": "on_attack",
                "chance": 30,
                "effect": "lifesteal",
                "value": 12,
                "duration": 0,
                "description": "吸血12%"
            }
        ]

        # 创建桥接器
        bridges = create_bridges_from_equipment_config(
            "wedding_dress",
            "嫁衣",
            special_effects
        )
        # bridges[0].effect_id = "battle_lifesteal_wedding_dress_0"
        ```
    """
    if not special_effects:
        return []

    # 使用现有的parse_triggers_from_yaml解析配置
    trigger_configs = parse_triggers_from_yaml(special_effects)

    # 为每个TriggerConfig创建桥接器
    bridges = []
    for i, trigger_config in enumerate(trigger_configs):
        # 生成效果ID：格式为 "{item_id}_{index}"
        base_effect_id = f"{item_id}_{i}"

        # 创建桥接器
        bridge = create_bridge_for_trigger_config(
            trigger_config,
            base_effect_id=base_effect_id
        )

        bridges.append(bridge)

    return bridges


def register_all_battle_effect_bridges() -> Dict[str, Type[BattleEffectBridge]]:
    """
    批量注册所有战斗效果桥接器

    功能：
    1. 遍历所有装备配置
    2. 提取special_effects字段
    3. 创建BattleEffectBridge实例
    4. 注册到效果注册中心

    Returns:
        Dict[effect_id, BattleEffectBridge类型]: 已注册的桥接器映射

    使用示例：
        ```python
        # 在bot启动时调用
        from plugins.xiuxian_game.domain.effects.adapters import (
            register_all_battle_effect_bridges
        )

        @driver.on_startup
        async def _():
            await init_db()

            # 注册战斗效果桥接器
            bridges = register_all_battle_effect_bridges()
            logger.success(f"成功注册 {len(bridges)} 个战斗效果桥接器")
        ```
    """
    global _registered_bridges

    # 如果已经注册过，直接返回
    if _registered_bridges:
        logger.info(
            f"[BattleEffectRegister] 战斗效果桥接器已注册 "
            f"({len(_registered_bridges)} 个)，跳过重复注册"
        )
        return _registered_bridges

    logger.info("[BattleEffectRegister] 开始批量注册战斗效果桥接器...")

    # 导入配置
    from plugins.xiuxian_game.config import config

    # 获取效果注册中心
    registry = get_effect_registry()

    # 统计
    total_equipment = 0
    total_bridges = 0
    equipment_with_effects = 0

    # 遍历所有装备配置（使用by_id索引）
    items_by_id = config.items_config.get("by_id", {})
    for item_id, item_config in items_by_id.items():
        total_equipment += 1

        # 检查是否有special_effects
        special_effects = getattr(item_config, "special_effects", None)
        if not special_effects:
            continue

        equipment_with_effects += 1

        # 创建桥接器
        bridges = create_bridges_from_equipment_config(
            item_id=item_id,
            item_name=item_config.name,
            special_effects=special_effects
        )

        # 注册到效果注册中心
        for bridge in bridges:
            # 注册为单例（同一装备的效果可复用）
            registry.register_class(
                bridge.effect_id,
                BattleEffectBridge,
                singleton=False  # 不使用单例，每次战斗创建新实例
            )

            # 保存到全局注册表
            _registered_bridges[bridge.effect_id] = type(bridge)

            total_bridges += 1

    logger.success(
        f"[BattleEffectRegister] 批量注册完成: "
        f"扫描 {total_equipment} 个装备配置, "
        f"发现 {equipment_with_effects} 个装备有特殊效果, "
        f"成功注册 {total_bridges} 个战斗效果桥接器"
    )

    return _registered_bridges


def get_equipment_bridge_mapping() -> Dict[str, List[str]]:
    """
    获取装备到桥接器的映射关系

    Returns:
        Dict[item_id, List[effect_id]]: 装备ID到效果ID列表的映射

    示例：
        ```python
        mapping = get_equipment_bridge_mapping()
        # {
        #     "wedding_dress": [
        #         "battle_lifesteal_wedding_dress_0",
        #         "battle_fear_wedding_dress_1"
        #     ],
        #     ...
        # }
        ```
    """
    mapping: Dict[str, List[str]] = {}

    for effect_id in _registered_bridges.keys():
        # 从effect_id提取装备ID
        # 格式: "battle_{effect_type}_{item_id}_{index}"
        parts = effect_id.split("_")
        if len(parts) >= 4:
            # 提取item_id部分（可能包含下划线）
            item_id = "_".join(parts[2:-1])  # 排除前2个和最后1个
            if item_id not in mapping:
                mapping[item_id] = []
            mapping[item_id].append(effect_id)

    return mapping
