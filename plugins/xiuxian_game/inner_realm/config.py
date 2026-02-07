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
