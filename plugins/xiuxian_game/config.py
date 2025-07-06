from pydantic_settings import BaseSettings
from pathlib import Path
import yaml
from functools import lru_cache

class Config(BaseSettings):
    data_dir: Path = Path(__file__).parent / "data"
    config_file: Path = data_dir / "config.yaml"
    items_file: Path = data_dir / "items.yaml"
    map_file: Path = data_dir / "map.yaml"
    elixirs_file: Path = data_dir / "elixirs.yaml"
    
    @property
    def game_config(self) -> dict:
        """获取游戏配置"""
        return _load_config(self.config_file)

    @property
    def items_config(self) -> dict:
        """返回结构化物品配置"""
        from .models.inventory import ItemConfig, ItemType
        items = _load_config(self.items_file)
        # 建立双索引：ID和名称，并按类型分组
        configs = {}
        name_index = {}
        type_index = {t.value: [] for t in ItemType}
        for category in items["items"].values():
            for item in category:
                config = ItemConfig(item)
                configs[item["item_id"]] = config
                name_index[item["name"]] = config  # 名称唯一索引
                # 按类型收集 item_id，便于随机掉落
                type_index[config.type.value].append(config.item_id)
        return {"by_id": configs, "by_name": name_index, "by_type": type_index}

    @property
    def map_config(self) -> dict:
        return _load_config(self.map_file)

    @property
    def elixirs_config(self) -> dict:
        """返回丹方配置"""
        return _load_config(self.elixirs_file)


@lru_cache(maxsize=None)
def _load_config(config_file: Path) -> dict:
    """独立配置加载函数"""
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件 {config_file} 不存在")
    with open(config_file, "r", encoding="utf8") as f:
        return yaml.safe_load(f)
    
config = Config()
        
