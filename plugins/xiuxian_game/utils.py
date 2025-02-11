from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from typing import Optional
from .config import config


def create_rich_message(content: str, event: Optional[MessageEvent] = None) -> Message:
    """
    创建带格式的富文本消息，自动添加@用户
    """
    msg = Message()
    if event:
        msg.append(MessageSegment.at(event.get_user_id()))
    msg.append(MessageSegment.text(f"\n{content.strip()}"))
    return msg



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
    """分页格式化背包物品"""
    # 从配置获取分页大小
    cfg_page_size = config.game_config["game"]["inventory_page_size"]
    page_size = page_size or cfg_page_size
    
    start = (page - 1) * page_size
    end = start + page_size
    current_page_items = items[start:end]
    
    # 计算总页数时使用实际分页大小
    total_pages = (len(items) - 1) // page_size + 1
    page_info = f"\n📖 第 {page} 页（共 {total_pages} 页）"
    
    lines = []
    for idx, item in enumerate(current_page_items, start=1):
        lines.append(
            f"{idx}. {item.config.name} ✖️{item.quantity}\n"
        )
    
    return "🎒 你的背包\n" + "".join(lines) + page_info


