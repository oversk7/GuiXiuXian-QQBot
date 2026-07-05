"""
今天吃什么功能模块
使用TheMealDB API获取随机食谱推荐
"""
import aiohttp
import json
import logging
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head, check_action_limit, record_action
from ..utils_markdown import build_markdown, cmd
from ..platform_utils import require_player

logger = logging.getLogger(__name__)


def _format_meal_description(meal_data: dict) -> str:
    """
    格式化食谱描述信息（原生 Markdown 排版）
    """
    lines = []

    # 菜名
    meal_name = meal_data.get("strMeal", "未知菜谱")
    lines.append(f"## {meal_name}")

    # 分类和地区标签
    tags = []
    if meal_data.get("strCategory"):
        tags.append(f"`{meal_data['strCategory']}`")
    if meal_data.get("strArea"):
        tags.append(f"`{meal_data['strArea']}`")
    if tags:
        lines.append(f"🏷️ {' '.join(tags)}")

    # 标签（如果有）
    if meal_data.get("strTags"):
        tags_list = [t.strip() for t in meal_data['strTags'].split(',') if t.strip()]
        if tags_list:
            lines.append("*" + " · ".join(tags_list) + "*")

    return "\n".join(lines)


async def _get_random_meal() -> tuple[bool, dict, str]:
    """
    获取随机食谱

    Returns:
        (成功标志, 食谱数据, 错误信息)
    """
    try:
        api_url = "https://www.themealdb.com/api/json/v1/1/random.php"

        logger.info(f"请求随机食谱API: {api_url}")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http_session:
            async with http_session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get("meals") and len(data["meals"]) > 0:
                        meal_data = data["meals"][0]
                        logger.info(f"成功获取食谱: {meal_data.get('strMeal', 'Unknown')}")
                        return True, meal_data, ""
                    else:
                        return False, {}, "API未返回食谱数据"
                else:
                    return False, {}, f"API请求失败: HTTP {response.status}"

    except aiohttp.ClientError as e:
        logger.error(f"网络请求异常: {e}")
        return False, {}, f"网络请求失败: {str(e)}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        return False, {}, "数据解析失败"


# 今天吃什么指令
today_meal_cmd = on_command("今天吃什么", aliases={"吃什么", "今日食谱", "推荐菜谱"}, block=True, priority=13)


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
        player = await require_player(session, event, today_meal_cmd)

    await today_meal_cmd.send("🍽️ 正在为您寻找今日食谱...")

    # 获取随机食谱
    success, meal_data, error_msg = await _get_random_meal()

    if not success:
        await today_meal_cmd.finish(f"❌ 获取食谱失败: {error_msg}")

    # 记录操作
    record_action(user_id, "today_meal")

    # 获取食谱图片
    meal_image_url = meal_data.get("strMealThumb", "")
    if not meal_image_url:
        # 使用默认图片
        meal_image_url = "https://www.themealdb.com/images/ingredients/lime.png"

    # 构建原生 Markdown 卡片
    content = "\n".join([
        "# 🍽️ 今天吃什么",
        "***",
        _format_meal_description(meal_data),
        f"![今日食谱 #200px #200px]({meal_image_url})",
        "***",
        "> 💡 点击蓝字快捷操作",
        " | ".join([
            cmd("换一道", "今天吃什么"),
            cmd("娱乐系统"),
            cmd("面板"),
            cmd("帮助"),
        ]),
    ])

    await today_meal_cmd.finish(build_markdown(content))


# 注册频率限制配置
from ..utils import rate_limiter, RateLimitConfig

# 注册API调用限制 - 防止频繁调用外部API
rate_limiter.register_action("today_meal", RateLimitConfig(
    max_requests=5,  # 5分钟内最多5次
    time_window=300.0,
    cooldown=0.3  # 每次调用间隔30秒
))
