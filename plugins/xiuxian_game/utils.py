from nonebot.adapters.qq import Message, MessageSegment, MessageEvent
from typing import Optional
from .config import config
import math
import re  # 用于正则匹配域名


def message_add_head(content: str, event: Optional[MessageEvent] = None) -> Message:
    """
    后续可能添加统一的消息头
    """
    head = "『诡修仙』\n"
    return Message(head + content)



def calculate_level_up_exp(current_level: int) -> int:
    """
    根据配置计算升级所需经验
    使用混合曲线：前期线性增长，后期指数增长
    """
    cfg = config.game_config["game"]
    base = cfg["base_exp"]
    curve = cfg["exp_curve"]
    
    if current_level < curve["curve_change_level"]:
        # 前期：一次函数
        return int(base + (current_level-1) * curve["early_multiplier"])
    else:
        # 后期：二次函数
        level_diff = current_level - curve["curve_change_level"]
        return int(calculate_level_up_exp(curve["curve_change_level"]-1) + (level_diff ** 1.8) * curve["late_multiplier"])



async def generate_exp_table(max_level: int = 100) -> str:
    """
    生成经验表格并保存到文件
    返回文件路径
    """
    import csv
    from pathlib import Path
    
    cfg = config.game_config["game"]
    table = []
    total_exp = 0
    
    for level in range(1, max_level + 1):
        required = calculate_level_up_exp(level)
        total_exp += required
        table.append({
            "等级": level,
            "升级所需经验": required,
            "累计总经验": total_exp
        })
    
    # 确保数据目录存在
    output_path = config.data_dir / "level_exp_table.csv"
    with open(output_path, "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=["等级", "升级所需经验", "累计总经验"])
        writer.writeheader()
        writer.writerows(table)
    
    return str(output_path)


async def paginate_items(items: list, page: int, page_size: Optional[int] = None) -> str:
    """分页格式化背包物品

    • 普通物品显示数量：✖️{qty}
    • 装备显示耐久：🛠️ {cur}/{max}
    """
    # 从配置获取分页大小
    cfg_page_size = config.game_config["game"]["inventory_page_size"]
    page_size = page_size or cfg_page_size
    start = (page - 1) * page_size
    end = start + page_size
    current_page_items = items[start:end]

    # 计算总页数时使用实际分页大小
    total_pages = (len(items) - 1) // page_size + 1
    page_info = f"\n📖 第 {page} 页（共 {total_pages} 页)"

    lines: list[str] = []
    for offset, inst in enumerate(current_page_items, start=1):
        global_idx = start + offset  # 背包全局序号 (从1开始)
        if getattr(inst, "is_equipment", False):
            tpl = inst.config
            lines.append(
                f"{global_idx}. {tpl.name} 🛠️ {inst.durability}/{tpl.durability}\n"
            )
        else:
            lines.append(
                f"{global_idx}. {inst.config.name} ✖️{inst.quantity}\n"
            )

    return "🎒 你的背包\n" + "".join(lines) + page_info


# ---------------- Luck 概率曲线 ----------------

# Luck 值采用 S 型（Logistic）曲线：
# 先稳增长 → 急剧提升 → 最后趋于平缓
#
#   prob = 1 / (1 + e ^(-(luck - midpoint) / steepness))
#
# • midpoint  决定曲线中点（Luck≈midpoint 时概率≈0.5）
# • steepness 控制斜率，值越小曲线越陡
#
# 默认参数以 Luck≈60 达到 50% 触发率，Luck≈90 时≈88%，Luck≈120 时>98%。

def luck_prob(
    luck_value: int | float,
    midpoint: float = 60,
    steepness: float = 30,
) -> float:
    """根据 *Luck* 值返回 0‒1 之间的触发概率，符合“先稳后急再缓”的 S 型。

    参数
    ------
    luck_value : int | float
        玩家当前 Luck 值。
    midpoint : float, 可选
        曲线的中点，Luck≈midpoint 时概率≈0.5。
    steepness : float, 可选
        斜率参数，数值越小，中段上升越陡。
    """

    # 基础保护
    lv = float(luck_value)
    if lv <= 0:
        return 0.0

    # Logistic 曲线
    prob = 1.0 / (1.0 + math.exp(-(lv - midpoint) / steepness))

    # 理论上已在 (0,1) 内，这里做硬裁剪避免浮点误差
    return max(0.0, min(prob, 1.0))


# ---------------- URL 转义工具 ----------------

def bypass_urls(
    text: str,
    mode: str = "unicode",
    whitelist: list[str] | None = None,
) -> str:
    """在文本中查找英文域名并根据不同 *mode* 进行转义。

    参数说明
    ----------
    text: str
        待处理文本。
    mode: str
        转义模式，可选值
        ``unicode``      : 在点号前插入不可见字符 ``\u200E``（默认）
        ``space``        : 在点号前插入空格
        ``fullStop``     : 将半角点号替换为中文句号 ``。``
        ``remove``       : 直接删除匹配到的域名
        ``uppercase``    : 整个域名转为大写
        ``tldUppercase`` : 仅将顶级域名 TLD 转为大写
    whitelist: list[str] | None
        白名单域名列表，命中后将保持原样，不做任何处理。

    返回值
    -------
    str
        处理后的文本。

    Notes
    -----
    1. 为了保持依赖最小化，这里并未引入第三方库获取 "全部" 顶级域名列表，而是使用
       一个正则 ``([A-Za-z0-9-]+\.)+[A-Za-z]{2,63}`` 来粗略匹配"看起来像"域名的串。
       在大多数常见场景下已足够；如需严格匹配，可替换为公开的 TLD 列表。
    2. 该函数 **不会** 主动发送消息，也不包含任何异步操作，可安全在任何上下文中调用。
    """

    whitelist = whitelist or []

    # 点号替换映射
    dot_replacer_map: dict[str, str] = {
        "unicode": "\u200E.",  # U+200E (LRM) + '.'
        "space": " .",
        "fullStop": "。",
    }

    # 用于匹配英文域名的正则表达式：<sub>.<domain>.<tld>
    domain_pattern = re.compile(r"((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63})(?=[^A-Za-z0-9-]|$)")

    def _replace(match: re.Match[str]) -> str:
        domain = match.group(1)

        # 白名单直接放行
        if domain in whitelist:
            return domain

        # 各模式处理
        if mode == "remove":
            return ""
        if mode == "uppercase":
            return domain.upper()
        if mode == "tldUppercase":
            parts = domain.split(".")
            if len(parts) > 1:
                parts[-1] = parts[-1].upper()
            return ".".join(parts)
        # 默认走点号替换类模式（unicode / space / fullStop）
        replacer = dot_replacer_map.get(mode, "\u200E.")
        return domain.replace(".", replacer)

    return domain_pattern.sub(_replace, text)


