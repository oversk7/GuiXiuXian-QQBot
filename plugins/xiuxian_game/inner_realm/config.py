"""
里界系统配置加载器
"""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from nonebot import logger


class InnerRealmConfig:
    """里界配置管理器"""

    _config: Optional[Dict[str, Any]] = None
    _config_path = Path(__file__).parent.parent / "data" / "inner_realms.yaml"

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """
        加载里界配置文件

        Returns:
            配置字典
        """
        if cls._config is None:
            try:
                if not cls._config_path.exists():
                    raise FileNotFoundError(f"里界配置文件不存在: {cls._config_path}")

                with open(cls._config_path, 'r', encoding='utf-8') as f:
                    cls._config = yaml.safe_load(f)

                if not cls._config:
                    raise ValueError("里界配置文件为空")

                logger.info(f"✅ 成功加载里界配置: {cls._config_path}")

            except Exception as e:
                logger.error(f"❌ 加载里界配置失败: {e}")
                cls._config = {"global": {}, "time_system": {}, "realms": {}}

        return cls._config

    @classmethod
    def get_realm_config(cls, realm_name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定里界的配置

        Args:
            realm_name: 里界名称（如 "third_ward"）

        Returns:
            里界配置字典，不存在则返回None
        """
        config = cls.load_config()
        return config.get("realms", {}).get(realm_name)

    @classmethod
    def get_all_realms(cls) -> Dict[str, Dict[str, Any]]:
        """
        获取所有里界配置

        Returns:
            所有里界的配置字典
        """
        config = cls.load_config()
        return config.get("realms", {})

    @classmethod
    def get_global_config(cls) -> Dict[str, Any]:
        """
        获取全局配置

        Returns:
            全局配置字典
        """
        config = cls.load_config()
        return config.get("global", {})

    @classmethod
    def get_time_system_config(cls) -> Dict[str, Any]:
        """
        获取时间系统配置

        Returns:
            时间系统配置字典
        """
        config = cls.load_config()
        return config.get("time_system", {})

    @classmethod
    def get_attribute_modifiers(cls) -> Dict[str, Dict[str, Any]]:
        """
        获取属性修正配置

        Returns:
            属性修正配置字典
        """
        config = cls.load_config()
        return config.get("attribute_modifiers", {})

    @classmethod
    def get_dice_results_config(cls) -> Dict[str, Dict[str, Any]]:
        """
        获取骰子判定结果配置

        Returns:
            骰子判定结果配置字典
        """
        config = cls.load_config()
        return config.get("dice_results", {})

    @classmethod
    def reload_config(cls):
        """重新加载配置文件（用于动态更新配置）"""
        cls._config = None
        cls.load_config()
        logger.info("🔄 里界配置已重新加载")

    @classmethod
    def get_scenes_config(cls, realm_name: str) -> Dict[str, Any]:
        """获取指定里界的场景节点配置"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return {}
        return realm.get("scenes", {})

    @classmethod
    def get_npcs_config(cls, realm_name: str) -> list:
        """获取指定里界的NPC配置列表"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return []
        return realm.get("npcs", [])

    @classmethod
    def get_clues_config(cls, realm_name: str) -> list:
        """获取指定里界的线索配置列表"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return []
        return realm.get("clues", [])

    @classmethod
    def get_endings_config(cls, realm_name: str) -> Dict[str, Any]:
        """获取指定里界的结局配置"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return {}
        return realm.get("endings", {})

    @classmethod
    def get_phases_config(cls, realm_name: str) -> Dict[str, Any]:
        """获取指定里界的阶段配置（黄昏/入夜）"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return {}
        return realm.get("phases", {})

    @classmethod
    def get_key_items_config(cls, realm_name: str) -> Dict[str, Any]:
        """获取指定里界的关键道具配置"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return {}
        return realm.get("key_items", {})

    @classmethod
    def is_realm_suppress_cultivation(cls, realm_name: str) -> bool:
        """检查里界是否压制修为"""
        realm = cls.get_realm_config(realm_name)
        if not realm:
            return False
        return realm.get("suppress_cultivation", False)
