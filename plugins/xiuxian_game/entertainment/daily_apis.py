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
from datetime import datetime

# 摸鱼日历
moyu_calendar = on_command("摸鱼日历", aliases={"摸鱼", "日历"}, block=True, priority=5)

@moyu_calendar.handle()
async def handle_moyu_calendar(event: MessageEvent):
    """获取摸鱼日历图片"""
    user_id = event.get_user_id()
    
    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await moyu_calendar.finish(error_msg)
    
    try:
        # 请求摸鱼日历API
        response = requests.get("https://www.yviii.com/moyu/moyu.php", timeout=10)
        
        if response.status_code == 200:
            # 记录操作
            record_action(user_id, "daily_api")

            # 将图片内容转换为base64格式发送
            import base64
            base64_img = base64.b64encode(response.content).decode("utf-8")
            img_segment = MessageSegment.file_image(base64_img)
            msg = Message("📅 今日摸鱼日历来啦！\n").append(img_segment)
            await moyu_calendar.finish(msg)
        else:
            await moyu_calendar.finish("❌ 摸鱼日历获取失败，请稍后再试")
            
    except requests.RequestException:
        await moyu_calendar.finish("❌ 网络请求失败，请检查网络连接")


# 摸鱼日报
moyu_daily = on_command("摸鱼日报", aliases={"日报"}, block=True, priority=5)

@moyu_daily.handle()
async def handle_moyu_daily(event: MessageEvent):
    """获取摸鱼日报图片"""
    user_id = event.get_user_id()
    
    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await moyu_daily.finish(error_msg)
    
    try:
        # 请求摸鱼日报API
        response = requests.get("https://www.yviii.com/moyu/moyu2.php", timeout=10)
        
        if response.status_code == 200:
            # 记录操作
            record_action(user_id, "daily_api")

            # 将图片内容转换为base64格式发送
            import base64
            base64_img = base64.b64encode(response.content).decode("utf-8")
            img_segment = MessageSegment.file_image(base64_img)
            msg = Message("📰 今日摸鱼日报新鲜出炉！\n").append(img_segment)
            await moyu_daily.finish(msg)
        else:
            await moyu_daily.finish("❌ 摸鱼日报获取失败，请稍后再试")
            
    except requests.RequestException:
        await moyu_daily.finish("❌ 网络请求失败，请检查网络连接")


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
                msg_content = "🔮 抽签结果\n"
                msg_content += "=" * 20 + "\n"

                if question:
                    msg_content += f"🤔 所问之事：{question}\n\n"

                msg_content += f"📜 签文：\n{fortune_text}\n\n"
                msg_content += f"⏰ {draw_time}\n"
                msg_content += "=" * 20 + "\n"
                msg_content += "💡 提示：签文仅供娱乐，切勿过分迷信"

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
