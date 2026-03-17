"""
战斗日志过滤器 - 支持详细/简洁两种日志模式

简洁模式：仅保留攻击主线、关键事件和结果
详细模式：保留所有信息（引擎原始输出）
"""
import re
from typing import List

# 简洁模式保留的行模式（前缀匹配）
_KEEP_PREFIXES = (
    "⚔️",       # 攻击行 / 标题行
    "⚡",        # 闪避
    "━",         # 分割线 / 回合标题
    "🎉",       # 胜利
    "⏰",       # 平局
    "⚰️",       # 处决
    "🪞",       # 镜怨体质
    "💀",       # 死亡
    "😱",       # 恐惧（重要控制）
    "🐅",       # 猛虎标弹激活（重要状态变化）
    "💪",       # 刚气-心触发
)

# 简洁模式保留的行模式（正则匹配）
_KEEP_PATTERNS = [
    re.compile(r"^━━━ 第\d+回合 ━━━$"),              # 回合标题
    re.compile(r"^🔄 连击"),                            # 连击主行（不是子行缩进的）
]

# 简洁模式移除的行模式（子行缩进）
_REMOVE_PREFIXES = (
    "  └",       # 子效果行（护盾吸收、减伤、斩龙拆分等）
    "    ",       # 深缩进（HP条等）
)


def get_player_log_mode(player) -> str:
    """获取玩家的战斗日志模式偏好

    Returns:
        "simple" 或 "detailed"，默认 "simple"
    """
    extra = getattr(player, 'extra_attrs', None) or {}
    return extra.get("battle_log_mode", "simple")


def set_player_log_mode(player, mode: str):
    """设置玩家的战斗日志模式偏好

    Args:
        player: Player对象
        mode: "simple" 或 "detailed"
    """
    import copy
    extra = getattr(player, 'extra_attrs', None) or {}
    new_extra = copy.deepcopy(dict(extra))
    new_extra["battle_log_mode"] = mode
    player.extra_attrs = new_extra


def filter_battle_log(battle_log: List[str], mode: str = "simple") -> List[str]:
    """根据模式过滤战斗日志

    Args:
        battle_log: 原始战斗日志行列表
        mode: "simple" 简洁模式, "detailed" 详细模式

    Returns:
        过滤后的日志行列表
    """
    if mode == "detailed":
        return battle_log

    result = []
    in_result_section = False  # 进入结果区域后全部保留

    for line in battle_log:
        stripped = line.strip()
        if not stripped:
            continue

        # 结果分割线后的内容全部保留（胜负、最终HP条）
        if stripped == "━━━━━━━━━━━━":
            in_result_section = True
            result.append(line)
            continue

        if in_result_section:
            result.append(line)
            continue

        # 移除子行（缩进的效果细节）
        if line.startswith(_REMOVE_PREFIXES):
            continue

        # 检查前缀匹配
        if stripped.startswith(_KEEP_PREFIXES):
            result.append(line)
            continue

        # 检查正则匹配
        if any(p.match(stripped) for p in _KEEP_PATTERNS):
            result.append(line)
            continue

        # 回合中间的HP条行（以玩家名+冒号结尾）- 简洁模式去掉
        # 保留首回合特效日志中的关键信息（灵影体质等变更最大HP的）
        if stripped.startswith("✨ 灵影体质"):
            result.append(line)
            continue

        # 其他行在简洁模式下移除
        # 包括：回血细节、吸血、真伤状态、效果过期、buff触发、骰子buff等

    return result
