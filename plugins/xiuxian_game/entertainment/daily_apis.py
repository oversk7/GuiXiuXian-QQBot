"""
日常API娱乐功能模块
包含摸鱼日历、摸鱼日报、抽签等功能
"""
import requests
from nonebot import on_command, get_driver
from nonebot.adapters.qq import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg
from nonebot_plugin_apscheduler import scheduler
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head, check_action_limit, record_action
import json
import os
import base64
import logging
from datetime import datetime, date
from pathlib import Path
import re

logger = logging.getLogger(__name__)
driver = get_driver()


class DailyImageCache:
    """每日图片缓存服务"""

    def __init__(self):
        # 缓存目录
        self.cache_dir = Path(__file__).parent.parent / "data" / "cache"
        self.cache_dir.mkdir(exist_ok=True)

        # 缓存文件路径
        self.calendar_cache_path = self.cache_dir / "moyu_calendar.jpg"
        self.daily_cache_path = self.cache_dir / "moyu_daily.jpg"

        # 缓存状态
        self._calendar_cached_date = None
        self._daily_cached_date = None

    async def cache_daily_images(self) -> dict:
        """缓存当天的摸鱼日历和日报图片"""
        today = date.today()
        results = {"calendar": False, "daily": False, "errors": []}

        try:
            # 缓存摸鱼日历
            calendar_success = await self._cache_image(
                "https://www.yviii.com/moyu/moyu.php",
                self.calendar_cache_path,
                "摸鱼日历"
            )
            if calendar_success:
                self._calendar_cached_date = today
                results["calendar"] = True

            # 缓存摸鱼日报
            daily_success = await self._cache_image(
                "https://www.yviii.com/moyu/moyu2.php",
                self.daily_cache_path,
                "摸鱼日报"
            )
            if daily_success:
                self._daily_cached_date = today
                results["daily"] = True

        except Exception as e:
            error_msg = f"缓存过程中发生错误: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

        return results

    async def _cache_image(self, url: str, cache_path: Path, name: str) -> bool:
        """缓存单个图片"""
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                with open(cache_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"✅ {name}缓存成功")
                return True
            else:
                logger.error(f"❌ {name}请求失败，状态码: {response.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"❌ {name}缓存失败: {e}")
            return False

    def get_cached_images(self) -> tuple[str, str]:
        """获取缓存的图片base64数据"""
        today = date.today()
        calendar_b64 = None
        daily_b64 = None

        # 检查日历缓存
        if (self.calendar_cache_path.exists() and
            self._calendar_cached_date == today):
            try:
                with open(self.calendar_cache_path, "rb") as f:
                    calendar_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logger.error(f"读取日历缓存失败: {e}")

        # 检查日报缓存
        if (self.daily_cache_path.exists() and
            self._daily_cached_date == today):
            try:
                with open(self.daily_cache_path, "rb") as f:
                    daily_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logger.error(f"读取日报缓存失败: {e}")

        return calendar_b64, daily_b64

    def is_cache_valid(self) -> tuple[bool, bool]:
        """检查缓存是否有效（是否为当天的缓存）"""
        today = date.today()
        calendar_valid = (self._calendar_cached_date == today and
                         self.calendar_cache_path.exists())
        daily_valid = (self._daily_cached_date == today and
                      self.daily_cache_path.exists())
        return calendar_valid, daily_valid


# 全局缓存实例
daily_cache = DailyImageCache()


def _format_fortune_result(fortune_text: str, draw_time: str, question: str = "") -> str:
    """
    格式化抽签结果，提供专业的排版
    """
    # 解析签文内容
    parts = _parse_fortune_text(fortune_text)

    # 构建消息头部
    msg_lines = [
        "🔮✨ 抽签占卜 ✨🔮",
        "━━━━━━━━━━━━━",
    ]

    # 添加问题（如果有）
    if question:
        msg_lines.extend([
            f"🤔 所问之事：{question}",
            "━━━━━━━━━━━━━",
            ""
        ])

    # 添加卦象信息
    if parts.get("gua_name"):
        msg_lines.extend([
            f"📿 卦象：{parts['gua_name']}",
            f"🔸 符号：{parts.get('level', '未知')}",
            ""
        ])

    # 添加签诗
    if parts.get("poem"):
        msg_lines.extend([
            "📜 签诗：",
            f"   {parts['poem']}",
            ""
        ])

    # 添加演义（在解签前面）
    if parts.get("interpretation"):
        msg_lines.extend([
            "💭 演义：",
            f"   {parts['interpretation']}",
            ""
        ])

    # 添加解释
    if parts.get("explanation"):
        msg_lines.extend([
            "🔍 解签：",
            f"   {parts['explanation']}",
            ""
        ])

    # 添加时间和提示
    msg_lines.extend([
        "━━━━━━━━━━━━━",
        f"⏰ {draw_time}",
        "",
        "💡 签文仅供娱乐参考，切勿过分迷信",
        "━━━━━━━━━━━━━"
    ])

    return "\n".join(msg_lines)


def _parse_fortune_text(text: str) -> dict:
    """
    解析签文内容，提取各个部分
    """
    result = {}

    # 提取卦名和等级
    gua_match = re.search(r'※\s*([^◎]+)', text)
    if gua_match:
        result["gua_name"] = gua_match.group(1).strip()

    # 提取等级符号，直接显示原文符号
    level_match = re.search(r'◎+', text)
    if level_match:
        level_symbols = level_match.group()
        result["level"] = level_symbols

    # 提取签诗（四句诗）
    # 先找到◎符号后的内容，然后提取四句诗
    poem_start = text.find('◎')
    if poem_start != -1:
        # 从◎符号后开始查找诗句
        poem_section = text[poem_start:]
        # 匹配四句诗的模式：每句以，结尾，最后一句以。结尾
        poem_match = re.search(r'◎+\s*([^演]+?)(?=演：)', poem_section)
        if poem_match:
            poem_raw = poem_match.group(1).strip()
            # 按标点符号分割并格式化
            sentences = re.split(r'[，。]', poem_raw)
            # 过滤空字符串并重新组合
            sentences = [s.strip() for s in sentences if s.strip()]
            if len(sentences) >= 4:
                result["poem"] = f"{sentences[0]}，\n   {sentences[1]}，\n   {sentences[2]}，\n   {sentences[3]}。"

    # 提取演义部分（去掉其中的解签内容）
    interpretation_match = re.search(r'演：(.+?)(?:\(解签：|$)', text)
    if interpretation_match:
        interpretation_text = interpretation_match.group(1).strip()
        # 去掉演义末尾可能存在的解签引用
        interpretation_text = re.sub(r'[（(]解签[：:].*?[）)]', '', interpretation_text).strip()
        result["interpretation"] = interpretation_text

    # 提取解签部分 - 处理括号内的解签
    explanation_match = re.search(r'\(解签：(.+?)\)', text)
    if explanation_match:
        explanation_text = explanation_match.group(1).strip()
        # 如果解签内容很长，可以考虑分段显示
        result["explanation"] = explanation_text
    else:
        # 如果没有括号格式，尝试查找其他解签格式
        explanation_match2 = re.search(r'解签[：:](.+?)(?:\(|$|。)', text)
        if explanation_match2:
            result["explanation"] = explanation_match2.group(1).strip()

    return result


# 摸鱼日历（合并日历和日报）
moyu_calendar = on_command("摸鱼日历", aliases={"摸鱼", "日历", "摸鱼日报", "日报"}, block=True, priority=5)

@moyu_calendar.handle()
async def handle_moyu_calendar(event: MessageEvent):
    """获取摸鱼日历和日报图片"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await moyu_calendar.finish(error_msg)

    try:
        # 记录操作
        record_action(user_id, "daily_api")

        # 尝试从缓存获取图片
        calendar_b64, daily_b64 = daily_cache.get_cached_images()
        calendar_valid, daily_valid = daily_cache.is_cache_valid()

        messages = []

        # 处理日历图片
        if calendar_valid and calendar_b64:
            # 使用缓存的日历
            calendar_img = MessageSegment.file_image(calendar_b64)
            messages.append(Message("📅 今日摸鱼日历来啦！").append(calendar_img))
        else:
            # 实时获取日历
            try:
                response = requests.get("https://www.yviii.com/moyu/moyu.php", timeout=10)
                if response.status_code == 200:
                    calendar_b64_new = base64.b64encode(response.content).decode("utf-8")
                    calendar_img = MessageSegment.file_image(calendar_b64_new)
                    messages.append(Message("📅 今日摸鱼日历来啦！").append(calendar_img))
                else:
                    messages.append(Message("❌ 摸鱼日历获取失败"))
            except requests.RequestException:
                messages.append(Message("❌ 摸鱼日历网络请求失败"))

        # 处理日报图片
        if daily_valid and daily_b64:
            # 使用缓存的日报
            daily_img = MessageSegment.file_image(daily_b64)
            messages.append(Message("📰 今日摸鱼日报新鲜出炉！").append(daily_img))
        else:
            # 实时获取日报
            try:
                response = requests.get("https://www.yviii.com/moyu/moyu2.php", timeout=10)
                if response.status_code == 200:
                    daily_b64_new = base64.b64encode(response.content).decode("utf-8")
                    daily_img = MessageSegment.file_image(daily_b64_new)
                    messages.append(Message("📰 今日摸鱼日报新鲜出炉！").append(daily_img))
                else:
                    messages.append(Message("❌ 摸鱼日报获取失败"))
            except requests.RequestException:
                messages.append(Message("❌ 摸鱼日报网络请求失败"))

        # 发送所有消息
        if messages:
            for msg in messages:
                await moyu_calendar.send(msg)
            await moyu_calendar.finish()
        else:
            await moyu_calendar.finish("❌ 摸鱼内容获取失败，请稍后再试")

    except ValueError as e:
        logger.error(f"摸鱼功能处理失败: {e}")
        await moyu_calendar.finish("❌ 处理失败，请稍后再试")


# 抽签功能
draw_fortune = on_command("抽签", aliases={"求签", "占卜"}, block=True, priority=5)

@draw_fortune.handle()
async def handle_draw_fortune(event: MessageEvent, args: Message = CommandArg()):
    """抽签占卜功能"""
    user_id = event.get_user_id()
    
    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "fortune")
    if not allowed:
        await draw_fortune.finish(error_msg)
    
    try:
        # 获取用户输入的问题（可选）
        question = args.extract_plain_text().strip()
        
        # 请求抽签API
        api_key = "***REMOVED***"
        api_url = f"https://api.t1qq.com/api/tool/cg?key={api_key}"

        response = requests.get(api_url, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == 200:
                # 记录操作
                record_action(user_id, "fortune")

                # 解析返回数据
                fortune_text = data.get("g", "签文获取失败")
                draw_time = data.get("time", "")

                # 构建回复消息
                msg_content = _format_fortune_result(fortune_text, draw_time, question)

                await draw_fortune.finish(message_add_head(msg_content, event))
            else:
                await draw_fortune.finish("❌ 抽签失败：" + data.get("msg", "未知错误"))
        else:
            await draw_fortune.finish("❌ 抽签服务暂时不可用，请稍后再试")
            
    except requests.RequestException:
        await draw_fortune.finish("❌ 网络请求失败，请检查网络连接")
    except json.JSONDecodeError:
        await draw_fortune.finish("❌ 抽签数据解析失败")


# 每日一言
daily_quote = on_command("每日一言", aliases={"一言", "名言"}, block=True, priority=5)

@daily_quote.handle()
async def handle_daily_quote(event: MessageEvent):
    """获取每日一言"""
    user_id = event.get_user_id()
    
    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await daily_quote.finish(error_msg)
    
    try:
        # 检查玩家是否存在
        async with safe_session() as session:
            player = await session.get(Player, user_id)
            if not player:
                await daily_quote.finish("您还没有创建角色，请先注册。")
        
        # 请求一言API
        response = requests.get("https://v1.hitokoto.cn/", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # 记录操作
            record_action(user_id, "daily_api")
            
            # 解析数据
            content = data.get("hitokoto", "获取失败")
            author = data.get("from_who", "")
            source = data.get("from", "")
            
            # 构建回复消息
            msg_content = "✨ 每日一言\n"
            msg_content += "=" * 15 + "\n"
            msg_content += f"💭 {content}\n\n"
            
            if author and source:
                msg_content += f"📖 —— {author}《{source}》"
            elif source:
                msg_content += f"📖 —— 《{source}》"
            elif author:
                msg_content += f"📖 —— {author}"
            
            await daily_quote.finish(message_add_head(msg_content, event))
        else:
            await daily_quote.finish("❌ 每日一言获取失败，请稍后再试")
            
    except requests.RequestException:
        await daily_quote.finish("❌ 网络请求失败，请检查网络连接")
    except json.JSONDecodeError:
        await daily_quote.finish("❌ 数据解析失败")


# 手动刷新缓存命令（管理员专用）
refresh_cache_cmd = on_command("刷新摸鱼缓存", block=True, priority=1)

@refresh_cache_cmd.handle()
async def handle_refresh_cache(event: MessageEvent):
    """手动刷新摸鱼图片缓存"""
    user_id = event.get_user_id()

    try:
        # 检查玩家是否存在
        async with safe_session() as session:
            player = await session.get(Player, user_id)
            if not player:
                await refresh_cache_cmd.finish("您还没有创建角色，请先注册。")

        await refresh_cache_cmd.send("🔄 开始刷新摸鱼图片缓存...")

        # 执行缓存刷新
        results = await daily_cache.cache_daily_images()

        # 构建结果消息
        msg_lines = ["📋 缓存刷新结果", "━━━━━━━━━━━━━"]

        if results["calendar"]:
            msg_lines.append("✅ 摸鱼日历缓存成功")
        else:
            msg_lines.append("❌ 摸鱼日历缓存失败")

        if results["daily"]:
            msg_lines.append("✅ 摸鱼日报缓存成功")
        else:
            msg_lines.append("❌ 摸鱼日报缓存失败")

        if results["errors"]:
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("⚠️ 错误信息：")
            for error in results["errors"]:
                msg_lines.append(f"• {error}")

        success_count = sum([results["calendar"], results["daily"]])
        if success_count == 2:
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("🎉 所有图片缓存完成！")
        elif success_count > 0:
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append(f"⚠️ 部分缓存成功 ({success_count}/2)")
        else:
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("❌ 缓存刷新失败")

        result_msg = "\n".join(msg_lines)
        await refresh_cache_cmd.finish(message_add_head(result_msg, event))

    except Exception as e:
        logger.error(f"手动刷新缓存失败: {e}")
        await refresh_cache_cmd.finish("❌ 缓存刷新失败，请稍后再试")


# 注册频率限制配置
from ..utils import rate_limiter, RateLimitConfig

# 注册API调用限制 - 防止频繁调用外部API
rate_limiter.register_action("daily_api", RateLimitConfig(
    max_requests=10,  # 10分钟内最多10次
    time_window=600.0,
    cooldown=0.3  # 每次调用间隔30秒
))

# 抽签限制更严格一些
rate_limiter.register_action("fortune", RateLimitConfig(
    max_requests=3,   # 1小时内最多3次
    time_window=3600.0,
    cooldown=0.3
))


# ==================== 定时任务设置 ====================

async def cache_daily_images_task():
    """定时缓存每日图片的任务"""
    try:
        logger.info("🔄 开始缓存每日摸鱼图片...")
        results = await daily_cache.cache_daily_images()

        success_count = sum([results["calendar"], results["daily"]])
        total_count = 2

        if success_count == total_count:
            logger.info("✅ 每日摸鱼图片缓存完成 - 日历和日报都已缓存")
        elif success_count > 0:
            logger.warning(f"⚠️ 每日摸鱼图片部分缓存成功 - {success_count}/{total_count}")
            if results["errors"]:
                for error in results["errors"]:
                    logger.error(f"缓存错误: {error}")
        else:
            logger.error("❌ 每日摸鱼图片缓存失败")
            if results["errors"]:
                for error in results["errors"]:
                    logger.error(f"缓存错误: {error}")

    except Exception as e:
        logger.error(f"❌ 缓存任务执行失败: {e}")


@driver.on_startup
async def setup_daily_cache_scheduler():
    """设置每日图片缓存定时任务"""
    try:
        # 检查任务是否已存在，避免重复设置
        existing_job = scheduler.get_job("daily_image_cache")
        if existing_job:
            logger.info("⚠️ 每日图片缓存定时任务已存在，跳过设置")
            return

        # 添加每天早上执行的缓存任务
        scheduler.add_job(
            func=cache_daily_images_task,
            trigger="cron",
            hour=7,
            minute=30,
            id="daily_image_cache",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        logger.info("✅ 每日图片缓存定时任务已设置 - 每天8点执行")

        # 启动时立即执行一次缓存（如果当天还没有缓存）
        calendar_valid, daily_valid = daily_cache.is_cache_valid()
        if not (calendar_valid and daily_valid):
            logger.info("💡 检测到缓存不完整，立即执行一次缓存...")
            await cache_daily_images_task()

    except Exception as e:
        logger.error(f"❌ 设置每日图片缓存定时任务失败: {e}")


@driver.on_shutdown
async def cleanup_daily_cache_scheduler():
    """清理每日图片缓存调度器"""
    try:
        if scheduler.get_job("daily_image_cache"):
            scheduler.remove_job("daily_image_cache")
            logger.info("🧹 每日图片缓存定时任务已清理")
    except Exception as e:
        logger.error(f"❌ 清理每日图片缓存定时任务失败: {e}")
