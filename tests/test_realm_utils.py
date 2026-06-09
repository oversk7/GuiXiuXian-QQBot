"""境界名称计算单元测试

realm_utils 零依赖，但 player/__init__.py 会导入 nonebot 命令模块，
故通过 importlib 按文件路径加载，绕开包初始化。
"""

import importlib.util
from pathlib import Path

_path = Path(__file__).parent.parent / "plugins" / "xiuxian_game" / "player" / "realm_utils.py"
_spec = importlib.util.spec_from_file_location("realm_utils", _path)
realm_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(realm_utils)

realm_by_level = realm_utils.realm_by_level
realm_by_level_and_reincarnation = realm_utils.realm_by_level_and_reincarnation
REALM_NAMES = realm_utils.REALM_NAMES
REALM_THRESHOLDS = realm_utils.REALM_THRESHOLDS


def test_names_thresholds_aligned():
    # 每个阈值对应一个境界名，错位会导致全部境界显示错乱
    assert len(REALM_NAMES) == len(REALM_THRESHOLDS)


def test_realm_boundaries():
    assert realm_by_level(1) == "凡人"
    assert realm_by_level(20) == "凡人"      # 阈值含端点
    assert realm_by_level(21) == "腐体境"
    assert realm_by_level(300) == "灾厄境"   # 一转门槛
    assert realm_by_level(301) == "冥返境"
    assert realm_by_level(3000) == "无上境"  # 最后一个预设境界


def test_transcendent_realms():
    # 超过 3000 级后每 500 级一个超越境界
    assert realm_by_level(3001) == "破天境"
    assert realm_by_level(3500) == "破天境"
    assert realm_by_level(3501) == "逆天境"


def test_reincarnation_prefix():
    assert realm_by_level_and_reincarnation(100, 0) == "阴祟境"
    assert realm_by_level_and_reincarnation(100, 1) == "一转·阴祟境"
    assert realm_by_level_and_reincarnation(100, 5) == "五转·阴祟境"
    assert realm_by_level_and_reincarnation(100, 12) == "轮回12世·阴祟境"
