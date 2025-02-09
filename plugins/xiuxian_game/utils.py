from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from typing import Optional
from .config import Config

# 创建全局配置实例
config = Config()

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
        return int(base + current_level * curve["early_multiplier"])
    else:
        # 后期：二次函数
        level_diff = current_level - curve["curve_change_level"]
        return int(base + (level_diff ** 2) * curve["late_multiplier"])


