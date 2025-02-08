from pydantic_settings import BaseSettings
import os
import yaml

class GameConfig(BaseSettings):
    max_level: int = 100
    exp_curve: list = [10, 20, 40, 80, 160]

class CultivateConfig(BaseSettings):
    base_exp: int = 10
    cooldown: int = 3600

class Config(BaseSettings):
    cultivate: CultivateConfig = CultivateConfig()