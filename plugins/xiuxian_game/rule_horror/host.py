"""NoneBot2 宿主层。

替代原 MaiBot 插件的 `plugin.py`：持有游戏核心单例（状态管理、存档、LLM、
图片生成），并把 `data/config.yaml` 的 `rule_horror` 段桥接到插件自带的
Pydantic 配置模型（不再使用 config.toml）。

移植自 https://github.com/wentaoxian6-svg/MaiBot-rule_horror_plugin (MIT)
"""
from __future__ import annotations

import asyncio
import copy
import os
from typing import Any

from nonebot import logger

from .common import DirectoryNames, resolve_data_dir
from .core import (
    AsyncImageGenerator,
    GameStateManager,
    LLMClient,
    SaveManager,
    apply_plugin_config_overrides,
)

PLUGIN_DIR = os.path.dirname(__file__)


def _load_rule_horror_section() -> dict[str, Any]:
    """读取 data/config.yaml 的 rule_horror 段（含玩法参数与 LLM 配置）。"""
    from ..config import config as game_config

    section = game_config.game_config.get("rule_horror", {}) or {}
    return copy.deepcopy(section) if isinstance(section, dict) else {}


def _build_plugin_overrides(section: dict[str, Any]) -> dict[str, Any]:
    """把 rule_horror 段转换为插件 Config 的覆盖字典。

    注意：插件 Config 默认自带 llm.models / npc_sim.models 示例模型，
    如果用户只配了 model_list，必须显式清空 models，否则默认模型优先生效。
    """
    overrides: dict[str, Any] = {}
    for key in ("plugin", "llm", "npc_sim", "save"):
        value = section.get(key)
        if isinstance(value, dict):
            overrides[key] = copy.deepcopy(value)

    llm = overrides.setdefault("llm", {})
    if "models" not in llm:
        llm["models"] = []
    npc_sim = overrides.setdefault("npc_sim", {})
    if "models" not in npc_sim:
        npc_sim["models"] = []

    # api_key 留空时复用 ai_dialogue 的 DeepSeek 密钥
    if not str(llm.get("api_key", "") or "").strip():
        from ..config import config as game_config

        ai_dialogue = game_config.game_config.get("ai_dialogue", {}) or {}
        deepseek_key = str(
            (ai_dialogue.get("deepseek", {}) or {}).get("api_key", "") or ""
        ).strip()
        if deepseek_key:
            llm["api_key"] = deepseek_key

    return overrides


class RuleHorrorHost:
    """向命令处理层提供原 MaiBot plugin 对象的最小接口。"""

    def __init__(self) -> None:
        self.ctx = None  # 原 MaiBot 上下文；NoneBot 适配层已覆写全部使用点
        self.state_manager: GameStateManager | None = None
        self.save_manager: SaveManager | None = None
        self.llm_client: LLMClient | None = None
        self.image_generator: AsyncImageGenerator | None = None
        self.data_dir: str = ""
        self.temp_images_dir: str = ""
        self._config_data: dict[str, Any] = {}
        self._section: dict[str, Any] = {}
        self._started = False
        self._start_lock = asyncio.Lock()

    # ---- 原 MaiBotPlugin 接口 ----

    def get_plugin_config_data(self) -> dict[str, Any]:
        return self._config_data

    # ---- 玩法参数（rule_horror 段顶层键）----

    def get_game_setting(self, key: str, default: Any = None) -> Any:
        return self._section.get(key, default)

    async def ensure_started(self) -> None:
        if self._started:
            return
        async with self._start_lock:
            if self._started:
                return

            self.data_dir = resolve_data_dir(PLUGIN_DIR, DirectoryNames.DATA)
            self.temp_images_dir = os.path.join(self.data_dir, DirectoryNames.TEMP_IMAGES)
            os.makedirs(self.data_dir, exist_ok=True)
            os.makedirs(self.temp_images_dir, exist_ok=True)

            self._section = _load_rule_horror_section()
            self._config_data = _build_plugin_overrides(self._section)
            self._config_data["plugin_dir"] = PLUGIN_DIR
            apply_plugin_config_overrides(self._config_data)

            self.state_manager = GameStateManager()
            self.save_manager = SaveManager(os.path.join(self.data_dir, DirectoryNames.SAVES))
            self.llm_client = LLMClient()
            self.image_generator = AsyncImageGenerator(self.temp_images_dir)

            await self.state_manager.start()
            await self.save_manager.start()
            self._started = True
            logger.info(f"规则怪谈玩法已加载 (数据目录: {self.data_dir})")


_host: RuleHorrorHost | None = None


def get_host() -> RuleHorrorHost:
    global _host
    if _host is None:
        _host = RuleHorrorHost()
    return _host
