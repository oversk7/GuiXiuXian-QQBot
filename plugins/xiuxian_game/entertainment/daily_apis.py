"""
日常API娱乐功能模块
包含摸鱼日历、摸鱼日报、抽签等功能
"""
import requests
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head, check_action_limit, record_action
import json
import base64
import logging
import re

logger = logging.getLogger(__name__)


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

async def _get_moyu_calendar_from_backup() -> tuple[bool, str]:
    """
    从备用源获取摸鱼日历
    返回: (成功标志, base64图片数据或错误信息)
    """
    try:
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded;charset:utf-8;'
        }
        api_url = "https://www.52api.cn/api/moyu"
        params = {
            'key': '3VgDmAiNNGpjLRvjhvmLMTDGxk'
        }

        logger.info(f"请求备用源: {api_url} with params: {params}")
        response = requests.get(api_url, params=params, headers=headers, timeout=15)

        logger.info(f"备用源响应状态: {response.status_code}")
        logger.info(f"备用源响应Content-Type: {response.headers.get('content-type', 'unknown')}")

        if response.status_code == 200:
            # 检查Content-Type，如果是图片则直接处理
            content_type = response.headers.get('content-type', '').lower()

            if 'image/' in content_type:
                # 直接返回图片的base64编码
                logger.info("备用源直接返回图片数据")
                if response.content:
                    calendar_b64 = base64.b64encode(response.content).decode("utf-8")
                    return True, calendar_b64
                else:
                    return False, "备用源返回空图片数据"

            elif 'application/json' in content_type:
                # 如果是JSON格式，按原逻辑处理
                try:
                    data = response.json()
                    logger.info(f"备用源JSON解析成功: {data}")

                    if data.get("code") == 200:
                        # 备用API返回的是图片URL，需要再次请求获取图片
                        image_url = data.get("data")
                        if image_url:
                            logger.info(f"获取到图片URL: {image_url}")
                            img_response = requests.get(image_url, timeout=15)
                            if img_response.status_code == 200:
                                calendar_b64 = base64.b64encode(img_response.content).decode("utf-8")
                                return True, calendar_b64
                            else:
                                return False, f"备用源图片下载失败: {img_response.status_code}"
                        else:
                            return False, "备用源未返回图片URL"
                    else:
                        return False, f"备用源API错误: {data.get('msg', '未知错误')}"
                except json.JSONDecodeError as e:
                    logger.error(f"备用源JSON解析失败: {e}")
                    return False, f"备用源数据解析失败: {str(e)}"

            else:
                # 未知的Content-Type
                logger.warning(f"备用源返回未知Content-Type: {content_type}")
                return False, f"备用源返回未知格式: {content_type}"
        else:
            return False, f"备用源请求失败: {response.status_code}"

    except requests.RequestException as e:
        logger.error(f"备用源网络请求异常: {e}")
        return False, f"备用源网络请求失败: {str(e)}"


@moyu_calendar.handle()
async def handle_moyu_calendar(event: MessageEvent):
    """获取摸鱼日历和日报图片"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await moyu_calendar.finish(error_msg)
    await moyu_calendar.send("📅 正在获取摸鱼日历与日报，请耐心等待10s...")
    try:
        # 记录操作
        record_action(user_id, "daily_api")

        messages = []

        # 获取日历图片 - 主源 + 备用源
        calendar_success = False
        try:
            # 尝试主源
            response = requests.get("https://www.yviii.com/moyu/moyu.php", timeout=15)
            if response.status_code == 200:
                calendar_b64 = base64.b64encode(response.content).decode("utf-8")
                calendar_img = MessageSegment.file_image(calendar_b64)
                messages.append(Message("📅 今日摸鱼日历来啦！").append(calendar_img))
                calendar_success = True
            else:
                logger.warning(f"主源摸鱼日历获取失败: {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"主源摸鱼日历网络请求失败: {e}")

        # 如果主源失败，尝试备用源
        if not calendar_success:
            logger.info("尝试使用备用源获取摸鱼日历")
            backup_success, backup_result = await _get_moyu_calendar_from_backup()
            if backup_success:
                calendar_img = MessageSegment.file_image(backup_result)
                messages.append(Message("📅 今日摸鱼日历来啦！").append(calendar_img))
                calendar_success = True
            else:
                logger.error(f"备用源摸鱼日历获取失败: {backup_result}")
                messages.append(Message("❌ 摸鱼日历获取失败"))

        # 获取日报图片 - 仅主源
        try:
            response = requests.get("https://www.yviii.com/moyu/moyu2.php", timeout=10)
            if response.status_code == 200:
                daily_b64 = base64.b64encode(response.content).decode("utf-8")
                daily_img = MessageSegment.file_image(daily_b64)
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



