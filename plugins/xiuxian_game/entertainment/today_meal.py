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

    # 食材清单
    ingredients = _extract_ingredients(meal_data)
    if ingredients:
        lines.append("📋 食材清单:")
        for ing, measure in ingredients:
            lines.append(f"   • {ing}: {measure}")
        lines.append("")

    # 制作说明
    instructions = meal_data.get("strInstructions", "")
    if instructions:
        # 清理和格式化制作步骤
        lines.append("👨‍🍳 制作步骤:")
        # 按句子分割，每句前面加序号
        sentences = [s.strip() for s in instructions.split('.') if s.strip()]
        for idx, sentence in enumerate(sentences[:8], 1):  # 限制显示前8步
            lines.append(f"   {idx}. {sentence}.")

        if len(sentences) > 8:
            lines.append(f"   ... (还有{len(sentences)-8}步)")

        lines.append("")

    # 来源信息
    lines.append("")
    lines.append("📖 数据来源: TheMealDB")

    return "\r".join(lines)  # 使用\r换行符以适配Markdown模版


def _extract_ingredients(meal_data: dict) -> list:
    """
    提取食材和用量

    Returns:
        list of tuples: [(ingredient_name, measurement), ...]
    """
    ingredients = []

    # TheMealDB API返回20个食材字段
    for i in range(1, 21):
        ing_key = f"strIngredient{i}"
        measure_key = f"strMeasure{i}"

        ingredient = meal_data.get(ing_key, "").strip()
        measure = meal_data.get(measure_key, "").strip()

        if ingredient:  # 只要有食材就添加
            if not measure:
                measure = "适量"
            ingredients.append((ingredient, measure))

    return ingredients


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
        player = await session.get(Player, user_id)
        if not player:
            await today_meal_cmd.finish("您还没有创建角色，请先注册。")

    try:
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
        hint = "🔄 换一个: 今天吃什么 | ☞【娱乐系统】查看更多娱乐功能"

        # 清理所有参数中的\n换行符，确保只使用\r
        title = title.replace('\n', '\r')
        desc = desc.replace('\n', '\r')
        hint = hint.replace('\n', '\r')

        # 构建模版参数
        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[meal_image_url]),
            MessageMarkdownParams(key="width", values=["200"]),
            MessageMarkdownParams(key="height", values=["200"]),
            MessageMarkdownParams(key="hint", values=[hint])
        ]

        # 使用图鉴类Markdown模版
        markdown_msg = MessageMarkdown(
            custom_template_id="102499345_1769178984",
            params=template_params
        )

        await today_meal_cmd.finish(MessageSegment.markdown(markdown_msg))

    except Exception as e:
        logger.error(f"今天吃什么功能处理失败: {e}")
        await today_meal_cmd.finish("❌ 处理失败，请稍后再试")


# 注册频率限制配置
from ..utils import rate_limiter, RateLimitConfig

# 注册API调用限制 - 防止频繁调用外部API
rate_limiter.register_action("today_meal", RateLimitConfig(
    max_requests=5,  # 5分钟内最多5次
    time_window=300.0,
    cooldown=0.3  # 每次调用间隔30秒
))
