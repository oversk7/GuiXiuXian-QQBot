from pydantic_settings import BaseSettings
import os
import yaml

class CultivateConfig(BaseSettings):
    base_exp: int = 10
    hp_recovery: int = 50
    max_duration: int = 8

class Config(BaseSettings):
    cultivate: CultivateConfig = CultivateConfig()
    
    class Config:
        env_nested_delimiter = "__"
        extra = "ignore"

        @classmethod
        def customise_sources(cls, init_settings, env_settings, file_secret_settings):
            # 尝试从插件目录下的 xiuxian_config.yaml 文件加载配置
            yaml_file = os.path.join(os.path.dirname(__file__), "xiuxian_config.yaml")
            if os.path.exists(yaml_file):
                with open(yaml_file, "r", encoding="utf8") as f:
                    yaml_settings = yaml.safe_load(f) or {}
            else:
                yaml_settings = {}
            # 优先级：默认初始化 > YAML文件 > 环境变量 > 文件密钥
            return (
                init_settings,
                lambda settings: yaml_settings,
                env_settings,
                file_secret_settings
            ) 