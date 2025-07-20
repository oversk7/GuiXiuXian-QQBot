"""鬼怪相关工具函数"""

from ..config import config


class GhostUtils:
    """鬼怪相关工具函数"""
    
    @staticmethod
    def get_ghost_config(ghost_id: str) -> dict:
        """获取鬼怪配置"""
        return config.ghosts_config["by_id"].get(ghost_id, {})
    
    @staticmethod
    def calculate_prestige_level(ghost_config: dict, player_attribute_value: int) -> int:
        """根据玩家属性值计算该鬼在玩家手中的威压等级"""
        if not ghost_config:
            return 1
        
        base_level = ghost_config.get("base_prestige_level", 1)
        attr_per_level = ghost_config.get("attribute_per_level", 50)
        bonus_levels = player_attribute_value // attr_per_level
        return base_level + bonus_levels
    
    @staticmethod
    def calculate_ghost_attributes(ghost_config: dict, ghost_level: int) -> dict:
        """根据鬼怪等级计算实际属性"""
        if not ghost_config:
            return {"hp": 100, "attack": 10, "defense": 10, "agility": 10}
        
        # 基础属性
        base_hp = ghost_config.get("hp", 100)
        base_attack = ghost_config.get("attack", 10)
        base_defense = ghost_config.get("defense", 10)
        base_agility = ghost_config.get("agility", 10)
        
        # 等级加成：每级增加10%基础属性
        level_multiplier = 1 + (ghost_level - 1) * 0.1
        
        return {
            "hp": int(base_hp * level_multiplier),
            "attack": int(base_attack * level_multiplier),
            "defense": int(base_defense * level_multiplier),
            "agility": int(base_agility * level_multiplier)
        }
    
    @staticmethod
    def get_upgrade_cost(ghost_level: int, rarity: str = "common") -> int:
        """计算鬼怪升级所需怨念值"""
        # 基础升级成本
        base_cost = ghost_level * 10
        
        # 稀有度影响升级成本
        rarity_multiplier = {
            "common": 1.0,
            "rare": 1.5,
            "epic": 2.0,
            "legendary": 3.0
        }
        
        multiplier = rarity_multiplier.get(rarity, 1.0)
        return int(base_cost * multiplier)
    
    @staticmethod
    def get_fragment_drop_count(rarity: str) -> int:
        """获取掉落的碎片数量（根据稀有度调整）"""
        import random
        
        if rarity == "rare":
            return random.randint(1, 2)
        elif rarity == "epic":
            return random.randint(2, 3)
        elif rarity == "legendary":
            return random.randint(3, 5)
        else:  # common
            return 1
