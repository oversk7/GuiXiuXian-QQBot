"""
今天吃什么功能模块
使用TheMealDB API获取随机食谱推荐
"""
import requests
import json
import logging
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head, check_action_limit, record_action
from ..platform_utils import get_unified_player

logger = logging.getLogger(__name__)


def _format_meal_description(meal_data: dict) -> str:
    """
    格式化食谱描述信息
    """
    lines = []

    # 菜名
    meal_name = meal_data.get("strMeal", "未知菜谱")
    lines.append(f"🍽️ {meal_name}")

    # 分类和地区标签
    tags = []
    if meal_data.get("strCategory"):
        tags.append(f"{meal_data['strCategory']}")
    if meal_data.get("strArea"):
        tags.append(f"{meal_data['strArea']}")
    if tags:
        lines.append(f"🏷️ {' | '.join(tags)}")

    # 标签（如果有）
    if meal_data.get("strTags"):
        tags_list = meal_data['strTags'].split(',')
        if tags_list:
            lines.append(f"🏷️ 标签: {' '.join(tags_list)}")

    lines.append("")

    return "\r".join(lines)  # 使用\r换行符以适配Markdown模版


async def _get_random_meal() -> tuple[bool, dict, str]:
    """
    获取随机食谱

    Returns:
        (成功标志, 食谱数据, 错误信息)
    """
    try:
        api_url = "https://www.themealdb.com/api/json/v1/1/random.php"

        logger.info(f"请求随机食谱API: {api_url}")
        response = requests.get(api_url, timeout=15)

        if response.status_code == 200:
            data = response.json()

            if data.get("meals") and len(data["meals"]) > 0:
                meal_data = data["meals"][0]
                logger.info(f"成功获取食谱: {meal_data.get('strMeal', 'Unknown')}")
                return True, meal_data, ""
            else:
                return False, {}, "API未返回食谱数据"
        else:
            return False, {}, f"API请求失败: HTTP {response.status_code}"

    except requests.RequestException as e:
        logger.error(f"网络请求异常: {e}")
        return False, {}, f"网络请求失败: {str(e)}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        return False, {}, "数据解析失败"


# 今天吃什么指令
today_meal_cmd = on_command("今天吃什么", aliases={"吃什么", "今日食谱", "推荐菜谱"}, block=True, priority=5)


@today_meal_cmd.handle()
async def handle_today_meal(event: MessageEvent):
    """处理今天吃什么指令"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "today_meal")
    if not allowed:
        await today_meal_cmd.finish(error_msg)

    # 检查玩家是否存在
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await today_meal_cmd.finish("您还没有创建角色，请先注册。")

    await today_meal_cmd.send("🍽️ 正在为您寻找今日食谱...")

    # 获取随机食谱
    success, meal_data, error_msg = await _get_random_meal()

    if not success:
        await today_meal_cmd.finish(f"❌ 获取食谱失败: {error_msg}")

    # 记录操作
    record_action(user_id, "today_meal")

    # 构建图鉴模版消息
    title = "🍽️ 今天吃什么"
    desc = _format_meal_description(meal_data)

    # 获取食谱图片
    meal_image_url = meal_data.get("strMealThumb", "")
    if not meal_image_url:
        # 使用默认图片
        meal_image_url = "https://www.themealdb.com/images/ingredients/lime.png"

    # 快捷操作提示
    hint = "💡 点击下方按钮快速操作"

    # 快捷操作按钮（4个）
    btn1 = "今天吃什么"
    btn2 = "娱乐系统"
    btn3 = "面板"
    btn4 = "帮助"

    # 清理所有参数中的\n换行符，确保只使用\r
    title = title.replace('\n', '\r')
    desc = desc.replace('\n', '\r')
    hint = hint.replace('\n', '\r')

    # 构建模版参数（使用带按钮的图鉴类模版）
    template_params = [
        MessageMarkdownParams(key="title", values=[title]),
        MessageMarkdownParams(key="desc", values=[desc]),
        MessageMarkdownParams(key="imgurl", values=[meal_image_url]),
        MessageMarkdownParams(key="width", values=["200"]),
        MessageMarkdownParams(key="height", values=["200"]),
        MessageMarkdownParams(key="hint", values=[hint]),
        MessageMarkdownParams(key="t1", values=[btn1]),
        MessageMarkdownParams(key="t2", values=[btn2]),
        MessageMarkdownParams(key="t3", values=[btn3]),
        MessageMarkdownParams(key="t4", values=[btn4])
    ]

    # 使用带按钮的图鉴类Markdown模版
    markdown_msg = MessageMarkdown(
        custom_template_id="102499345_1770445216",
        params=template_params
    )

    await today_meal_cmd.finish(MessageSegment.markdown(markdown_msg))


# 注册频率限制配置
from ..utils import rate_limiter, RateLimitConfig

# 注册API调用限制 - 防止频繁调用外部API
rate_limiter.register_action("today_meal", RateLimitConfig(
    max_requests=5,  # 5分钟内最多5次
    time_window=300.0,
    cooldown=0.3  # 每次调用间隔30秒
))
