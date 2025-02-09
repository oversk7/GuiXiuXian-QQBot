from pydantic_settings import BaseSettings
from pathlib import Path
import yaml
from functools import lru_cache

class Config(BaseSettings):
    data_dir: Path = Path(__file__).parent / "data"
    config_file: Path = data_dir / "config.yaml"
    items_file: Path = data_dir / "items.yaml"
    
    @property
    def game_config(self) -> dict:
        """获取游戏配置"""
        return _load_config(self.config_file)

    @property
    def items_config(self) -> dict:
        return _load_config(self.items_file)

@lru_cache(maxsize=None)
def _load_config(config_file: Path) -> dict:
    """独立配置加载函数"""
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件 {config_file} 不存在")
    with open(config_file, "r", encoding="utf8") as f:
        return yaml.safe_load(f)
    
config = Config()
        
