"""
昵称验证工具模块

提供昵称的违禁词检查和游戏名称过滤功能
"""
import re
from typing import Tuple

# 不允许出现在昵称中的粗俗/辱骂性称谓词列表
_VULGAR_TERMS = [
    "爸爸", "爹爹", "你爸", "你爹", "老爸", "老爹", "我爸", "我爹",
    "儿子", "你儿", "我儿", "干儿", "义儿",
    "妈妈", "你妈", "老妈", "我妈",
    "爷爷", "你爷", "老爷", "孙子", "你孙", "我孙",
    "奴隶", "狗奴", "狗腿",
]


async def validate_nickname(nickname: str) -> Tuple[bool, str]:
    """
    验证昵称是否合法

    检查项：
    1. 是否包含空格、制表符等空白字符
    2. 是否包含粗俗/辱骂性称谓词
    3. 是否包含违禁词（使用外部API）
    4. 是否包含游戏名称"诡修仙"

    Args:
        nickname: 待验证的昵称

    Returns:
        (is_valid, error_message): 是否合法，错误信息（合法时为空）
    """
    if not nickname or not nickname.strip():
        return False, "昵称不能为空"

    nickname = nickname.strip()

    # 检查是否包含空白字符（空格、制表符、全角空格等）
    if re.search(r'[\s\u3000\u00a0\u200b\u200c\u200d\ufeff]', nickname):
        return False, "昵称不能包含空格、制表符等空白字符"

    # 检查是否包含粗俗/辱骂性称谓词
    for term in _VULGAR_TERMS:
        if term in nickname:
            return False, f"昵称不能包含「{term}」等粗俗字眼"

    # 检查是否包含游戏名称
    if "诡修仙" in nickname:
        return False, "昵称不能包含游戏名称「诡修仙」"

    # 使用外部API检测违禁词
    from ..world.message_board import check_prohibited_content

    is_prohibited, words, label_desc, sub_label_desc = await check_prohibited_content(nickname)

    if is_prohibited:
        # 构造错误信息
        words_info = f"违禁词: {', '.join(words[:3])}" if words else ""  # 最多显示3个
        label_info = f"\n类型: {label_desc}" if label_desc else ""
        sub_label_info = f" - {sub_label_desc}" if sub_label_desc else ""

        error_msg = f"昵称包含违规内容\n{words_info}{label_info}{sub_label_info}\n请修改后重试"
        return False, error_msg

    return True, ""
