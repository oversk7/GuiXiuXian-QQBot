"""
日常API娱乐功能模块
包含抽签、每日一言、吃掉头像、答案之书、驾考题目、微博热搜等功能
"""
import requests
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head, check_action_limit, record_action
from ..ai_guide import call_ai_with_fallback
import json
import base64
import logging
import re

logger = logging.getLogger(__name__)


# 观音灵签抽签功能
draw_fortune = on_command("抽签", aliases={"求签", "占卜", "灵签"}, block=True, priority=5)

@draw_fortune.handle()
async def handle_draw_fortune(event: MessageEvent, args: Message = CommandArg()):
    """观音灵签抽签功能"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "fortune")
    if not allowed:
        await draw_fortune.finish(error_msg)

    try:
        # 获取用户输入的问题（可选）
        question = args.extract_plain_text().strip()

        # 检查玩家是否存在
        async with safe_session() as session:
            player = await session.get(Player, user_id)
            if not player:
                await draw_fortune.finish("您还没有创建角色,请先注册。")

        # 发送等待提示
        if question:
            await draw_fortune.send(message_add_head(f"🙏 正在为你抽取观音灵签,寻找「{question}」的答案...", event))
        else:
            await draw_fortune.send(message_add_head("🙏 正在为你抽取观音灵签...", event))

        # 请求观音灵签API
        api_url = "https://v2.xxapi.cn/api/guanyinrandom"
        headers = {
            'User-Agent': 'xiaoxiaoapi/1.0.0'
        }

        response = requests.get(api_url, headers=headers, timeout=15)

        if response.status_code != 200:
            await draw_fortune.finish(message_add_head(f"❌ API请求失败,状态码: {response.status_code}", event))

        # 解析JSON响应
        data = response.json()
        logger.info(f"观音灵签API响应: {data}")

        if data.get("code") != 200:
            error_msg = data.get("msg", "未知错误")
            await draw_fortune.finish(message_add_head(f"❌ API返回错误: {error_msg}", event))

        # 提取签文数据
        sign_data = data.get("data")
        if not sign_data:
            await draw_fortune.finish(message_add_head("❌ API未返回签文数据", event))

        # 记录操作
        record_action(user_id, "fortune")

        # 提取签文信息
        name = sign_data.get("name", "未知")
        fortune = sign_data.get("fortune", "")
        palace = sign_data.get("palace", "")
        poem_v1 = sign_data.get("poem_version_1", "")
        poem_v2 = sign_data.get("poem_version_2", "")
        meaning = sign_data.get("meaning", "")
        explanation = sign_data.get("explanation", "")
        image_url = sign_data.get("image", "")

        # 格式化签诗（使用版本1）
        poem_lines = []
        if poem_v1:
            # 将签诗按空格分割成四句
            verses = poem_v1.split()
            for verse in verses[:4]:  # 最多取4句
                poem_lines.append(verse)

        # 构建描述文本（用于Markdown模版）
        desc_parts = []

        # 添加问题
        if question:
            desc_parts.append(f"🤔 所问之事: {question}")
            desc_parts.append("")

        # 添加签运和宫位
        if fortune or palace:
            info_line = "🔮 "
            if fortune:
                info_line += f"{fortune}"
            if palace:
                info_line += f" · {palace}"
            desc_parts.append(info_line)
            desc_parts.append("")

        # 添加签诗
        if poem_lines:
            desc_parts.append("📜 签诗:")
            for line in poem_lines:
                desc_parts.append(f"   {line}")
            desc_parts.append("")

        # 添加卦象
        if meaning:
            desc_parts.append(f"💭 卦象: {meaning}")
            desc_parts.append("")

        # 添加解签
        if explanation:
            desc_parts.append(f"🔍 解签: {explanation}")
            desc_parts.append("")

        desc_parts.append("💡 签文仅供娱乐参考,切勿过分迷信")

        # 使用\r换行符（Markdown模版要求）
        desc = "\r".join(desc_parts)

        # 如果没有图片URL，使用默认图片
        if not image_url:
            image_url = "https://cdn.xxhzm.cn/api/guanyin/default.gif"

        # 构建图鉴模版消息
        title = f"🙏 观音灵签 · {name}"
        hint = "💡 点击下方按钮快速操作"

        # 快捷操作按钮
        btn1 = "抽签"
        btn2 = "娱乐系统"
        btn3 = "面板"
        btn4 = "帮助"

        # 导入MessageMarkdown
        from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams

        # 构建模版参数
        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[image_url]),
            MessageMarkdownParams(key="width", values=["300"]),
            MessageMarkdownParams(key="height", values=["300"]),
            MessageMarkdownParams(key="hint", values=[hint]),
            MessageMarkdownParams(key="t1", values=[btn1]),
            MessageMarkdownParams(key="t2", values=[btn2]),
            MessageMarkdownParams(key="t3", values=[btn3]),
            MessageMarkdownParams(key="t4", values=[btn4])
        ]

        # 使用图鉴类Markdown模版
        markdown_msg = MessageMarkdown(
            custom_template_id="102499345_1770445216",
            params=template_params
        )

        await draw_fortune.finish(MessageSegment.markdown(markdown_msg))

    except requests.RequestException as e:
        logger.error(f"观音灵签API请求失败: {e}")
        await draw_fortune.finish(message_add_head("❌ 网络请求失败,请稍后再试", event))
    except json.JSONDecodeError as e:
        logger.error(f"观音灵签JSON解析失败: {e}")
        await draw_fortune.finish(message_add_head("❌ 数据解析失败", event))


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
                await daily_quote.finish("您还没有创建角色,请先注册。")

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
            await daily_quote.finish("❌ 每日一言获取失败,请稍后再试")

    except requests.RequestException as e:
        logger.error(f"每日一言API请求失败: {e}")
        await daily_quote.finish("❌ 网络请求失败,请检查网络连接")
    except json.JSONDecodeError as e:
        logger.error(f"每日一言JSON解析失败: {e}")
        await daily_quote.finish("❌ 数据解析失败")


# 吃掉头像功能
bite_avatar = on_command("吃掉", block=True, priority=5)

@bite_avatar.handle()
async def handle_bite_avatar(event: MessageEvent, args: Message = CommandArg()):
    """吃掉某人的头像生成GIF动图"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await bite_avatar.finish(error_msg)

    # 获取目标QQ号
    target_qq = args.extract_plain_text().strip()

    if not target_qq:
        await bite_avatar.finish("❌ 请输入QQ号,例如:【吃掉 2595557847】")

    # 验证QQ号格式
    if not target_qq.isdigit():
        await bite_avatar.finish("❌ QQ号必须是纯数字")

    # 检查玩家是否存在
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await bite_avatar.finish("您还没有创建角色,请先注册。")

    # 发送等待提示
    await bite_avatar.send(message_add_head(f"🍽️ 正在准备吃掉 {target_qq} 的头像,请稍候...", event))

    try:
        # 请求API获取GIF URL
        api_url = f"https://v2.xxapi.cn/api/bite?qq={target_qq}"
        headers = {
            'User-Agent': 'xiaoxiaoapi/1.0.0'
        }

        response = requests.get(api_url, headers=headers, timeout=15)

        if response.status_code != 200:
            await bite_avatar.finish(message_add_head(f"❌ API请求失败,状态码: {response.status_code}", event))

        # 解析JSON响应
        data = response.json()
        logger.info(f"吃掉头像API响应: {data}")

        if data.get("code") != 200:
            error_msg = data.get("msg", "未知错误")
            await bite_avatar.finish(message_add_head(f"❌ API返回错误: {error_msg}", event))

        # 提取GIF URL
        gif_url = data.get("data")
        if not gif_url:
            await bite_avatar.finish(message_add_head("❌ API未返回图片URL", event))

        # 记录操作
        record_action(user_id, "daily_api")

        # 构建图鉴模版消息
        title = "🍽️ 吃掉头像"
        desc = f"成功吃掉了 {target_qq} 的头像!\r\r啊呜~真好吃! 🤤"
        hint = "💡 点击下方按钮快速操作"

        # 快捷操作按钮
        btn1 = "吃掉"
        btn2 = "娱乐系统"
        btn3 = "面板"
        btn4 = "帮助"

        # 导入MessageMarkdown
        from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams

        # 构建模版参数
        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[gif_url]),
            MessageMarkdownParams(key="width", values=["300"]),
            MessageMarkdownParams(key="height", values=["300"]),
            MessageMarkdownParams(key="hint", values=[hint]),
            MessageMarkdownParams(key="t1", values=[btn1]),
            MessageMarkdownParams(key="t2", values=[btn2]),
            MessageMarkdownParams(key="t3", values=[btn3]),
            MessageMarkdownParams(key="t4", values=[btn4])
        ]

        # 使用图鉴类Markdown模版
        markdown_msg = MessageMarkdown(
            custom_template_id="102499345_1770445216",
            params=template_params
        )

        await bite_avatar.finish(MessageSegment.markdown(markdown_msg))

    except requests.RequestException as e:
        logger.error(f"吃掉头像API请求失败: {e}")
        await bite_avatar.finish(message_add_head("❌ 网络请求失败,请稍后再试", event))
    except json.JSONDecodeError as e:
        logger.error(f"吃掉头像JSON解析失败: {e}")
        await bite_avatar.finish(message_add_head("❌ 数据解析失败", event))


# 答案之书功能
answer_book = on_command("答案之书", aliases={"答案", "问答之书"}, block=True, priority=5)

@answer_book.handle()
async def handle_answer_book(event: MessageEvent, args: Message = CommandArg()):
    """答案之书 - 向宇宙提问获得指引"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "fortune")
    if not allowed:
        await answer_book.finish(error_msg)

    try:
        # 获取用户的问题
        question = args.extract_plain_text().strip()

        if not question:
            await answer_book.finish("❌ 请输入你的问题,例如:【答案之书 我该继续吗】")

        # 检查玩家是否存在
        async with safe_session() as session:
            player = await session.get(Player, user_id)
            if not player:
                await answer_book.finish("您还没有创建角色,请先注册。")

        # 发送等待提示
        await answer_book.send(message_add_head(f"📖 正在翻阅答案之书,寻找关于「{question}」的答案...\n🤖 同时邀请智者解读,请稍候...", event))

        # 请求API
        api_url = f"https://v2.xxapi.cn/api/answers"
        headers = {
            'User-Agent': 'xiaoxiaoapi/1.0.0'
        }
        params = {
            'question': question
        }

        response = requests.get(api_url, headers=headers, params=params, timeout=15)

        if response.status_code != 200:
            await answer_book.finish(message_add_head(f"❌ API请求失败,状态码: {response.status_code}", event))

        # 解析JSON响应
        data = response.json()
        logger.info(f"答案之书API响应: {data}")

        if data.get("code") != 200:
            error_msg = data.get("msg", "未知错误")
            await answer_book.finish(message_add_head(f"❌ API返回错误: {error_msg}", event))

        # 提取答案数据
        answer_data = data.get("data")
        if not answer_data:
            await answer_book.finish(message_add_head("❌ API未返回答案数据", event))

        # 记录操作
        record_action(user_id, "fortune")

        # 提取中文标题和描述
        title_zh = answer_data.get("title_zh", "未知")
        desc_zh = answer_data.get("description_zh", "")
        title_en = answer_data.get("title_en", "")
        desc_en = answer_data.get("description_en", "")

        # 调用AI结合问题和答案进行个性化解读
        ai_insight = ""
        try:
            ai_messages = [
                {
                    "role": "system",
                    "content": (
                        "你是一位神秘的智者，专门解读「答案之书」的指引。"
                        "根据提问者的问题和答案之书给出的答案，用100字以内给出一段富有哲理、"
                        "贴合问题的个性化解读。语气神秘而温和，像在指引迷途的旅人，"
                        "不要重复答案原文，不要使用「答案之书」这个词。"
                    )
                },
                {
                    "role": "user",
                    "content": f"问题：{question}\n答案之书的答案：{title_zh}\n答案说明：{desc_zh}"
                }
            ]
            ai_result = await call_ai_with_fallback(ai_messages)
            ai_insight = ai_result['choices'][0]['message']['content'].strip()
        except Exception as e:
            logger.warning(f"答案之书AI解读失败: {e}")

        # 构建消息内容
        msg_content = (
            "📖✨ 答案之书 ✨📖\n"
            "━━━━━━━━━━━━━\n"
            f"🤔 你的问题: {question}\n"
            "━━━━━━━━━━━━━\n\n"
            f"💡 答案: {title_zh}\n\n"
            f"📝 指引: {desc_zh}\n"
        )

        # 如果有英文内容,也显示出来
        if title_en:
            msg_content += f"\n🌍 {title_en}\n"
        if desc_en:
            msg_content += f"   {desc_en}\n"

        # 附加AI个性化解读
        if ai_insight:
            msg_content += (
                "\n━━━━━━━━━━━━━\n"
                f"🔮 智者解读:\n{ai_insight}\n"
            )

        msg_content += (
            "\n━━━━━━━━━━━━━\n"
            "💭 答案仅供参考,人生由你掌控\n"
            "━━━━━━━━━━━━━"
        )

        await answer_book.finish(message_add_head(msg_content, event))

    except requests.RequestException as e:
        logger.error(f"答案之书API请求失败: {e}")
        await answer_book.finish(message_add_head("❌ 网络请求失败,请稍后再试", event))
    except json.JSONDecodeError as e:
        logger.error(f"答案之书JSON解析失败: {e}")
        await answer_book.finish(message_add_head("❌ 数据解析失败", event))


# 驾考题目功能
driving_test = on_command("驾考题目", aliases={"驾考", "科目一", "科目四"}, block=True, priority=5)

@driving_test.handle()
async def handle_driving_test(event: MessageEvent, args: Message = CommandArg()):
    """随机驾考题目"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await driving_test.finish(error_msg)

    try:
        # 获取用户输入的科目（可选）
        subject_text = args.extract_plain_text().strip()

        # 默认科目1
        subject = "1"
        subject_name = "科目一"

        # 解析科目参数
        if subject_text:
            if "1" in subject_text or "一" in subject_text:
                subject = "1"
                subject_name = "科目一"
            elif "2" in subject_text or "二" in subject_text:
                subject = "2"
                subject_name = "科目二"
            elif "3" in subject_text or "三" in subject_text:
                subject = "3"
                subject_name = "科目三"
            elif "4" in subject_text or "四" in subject_text:
                subject = "4"
                subject_name = "科目四"

        # 检查玩家是否存在
        async with safe_session() as session:
            player = await session.get(Player, user_id)
            if not player:
                await driving_test.finish("您还没有创建角色,请先注册。")

        # 发送等待提示
        await driving_test.send(message_add_head(f"🚗 正在获取{subject_name}随机题目...", event))

        # 请求驾考API
        api_url = f"https://v2.xxapi.cn/api/jiakao?subject={subject}"
        headers = {
            'User-Agent': 'xiaoxiaoapi/1.0.0'
        }

        response = requests.get(api_url, headers=headers, timeout=15)

        if response.status_code != 200:
            await driving_test.finish(message_add_head(f"❌ API请求失败,状态码: {response.status_code}", event))

        # 解析JSON响应
        data = response.json()
        logger.info(f"驾考题目API响应: {data}")

        if data.get("code") != 200:
            error_msg = data.get("msg", "未知错误")
            await driving_test.finish(message_add_head(f"❌ API返回错误: {error_msg}", event))

        # 提取题目数据
        question_data = data.get("data")
        if not question_data:
            await driving_test.finish(message_add_head("❌ API未返回题目数据", event))

        # 记录操作
        record_action(user_id, "daily_api")

        # 提取题目信息
        question = question_data.get("question", "")
        answer = question_data.get("answer", "")
        chapter = question_data.get("chapter", "")
        explain = question_data.get("explain", "")
        option1 = question_data.get("option1", "")
        option2 = question_data.get("option2", "")
        option3 = question_data.get("option3", "")
        option4 = question_data.get("option4", "")
        q_type = question_data.get("type", "")

        # 构建消息内容
        msg_content = (
            f"🚗 驾考题目 · {subject_name}\n"
            "━━━━━━━━━━━━━\n"
            f"📚 章节: {chapter}\n"
            f"📝 适用: {q_type}\n"
            "━━━━━━━━━━━━━\n\n"
            f"❓ 题目:\n{question}\n\n"
        )

        # 添加选项
        options = []
        if option1:
            options.append(option1)
        if option2:
            options.append(option2)
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)

        if options:
            msg_content += "选项:\n"
            for opt in options:
                msg_content += f"  {opt}\n"
            msg_content += "\n"

        # 添加答案和解释
        msg_content += (
            f"✅ 正确答案: {answer}\n\n"
            f"💡 解释:\n{explain}\n"
            "━━━━━━━━━━━━━\n"
            "📖 题目来源: 公安部题库"
        )

        await driving_test.finish(message_add_head(msg_content, event))

    except requests.RequestException as e:
        logger.error(f"驾考题目API请求失败: {e}")
        await driving_test.finish(message_add_head("❌ 网络请求失败,请稍后再试", event))
    except json.JSONDecodeError as e:
        logger.error(f"驾考题目JSON解析失败: {e}")
        await driving_test.finish(message_add_head("❌ 数据解析失败", event))


# 微博热搜功能
weibo_hot = on_command("微博热搜", aliases={"热搜", "微博", "热榜"}, block=True, priority=5)

@weibo_hot.handle()
async def handle_weibo_hot(event: MessageEvent):
    """获取微博热搜榜"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "daily_api")
    if not allowed:
        await weibo_hot.finish(error_msg)

    try:
        # 检查玩家是否存在
        async with safe_session() as session:
            player = await session.get(Player, user_id)
            if not player:
                await weibo_hot.finish("您还没有创建角色,请先注册。")

        # 发送等待提示
        await weibo_hot.send(message_add_head("📱 正在获取微博热搜榜...", event))

        # 请求微博热搜API
        api_url = "https://v2.xxapi.cn/api/weibohot"
        headers = {
            'User-Agent': 'xiaoxiaoapi/1.0.0'
        }

        response = requests.get(api_url, headers=headers, timeout=15)

        if response.status_code != 200:
            await weibo_hot.finish(message_add_head(f"❌ API请求失败,状态码: {response.status_code}", event))

        # 解析JSON响应
        data = response.json()
        logger.info(f"微博热搜API响应数据条数: {len(data.get('data', []))}")

        if data.get("code") != 200:
            error_msg = data.get("msg", "未知错误")
            await weibo_hot.finish(message_add_head(f"❌ API返回错误: {error_msg}", event))

        # 提取热搜数据
        hot_list = data.get("data")
        if not hot_list:
            await weibo_hot.finish(message_add_head("❌ API未返回热搜数据", event))

        # 记录操作
        record_action(user_id, "daily_api")

        # 构建消息内容 - 显示前20条热搜
        msg_content = (
            "🔥 微博热搜榜 TOP20\n"
            "━━━━━━━━━━━━━\n"
        )

        # 只显示前20条
        display_count = min(20, len(hot_list))
        for i in range(display_count):
            item = hot_list[i]
            index = item.get("index", i + 1)
            title = item.get("title", "未知")
            hot = item.get("hot", "")

            # 为前三名添加特殊标记
            if index == 1:
                prefix = "🥇"
            elif index == 2:
                prefix = "🥈"
            elif index == 3:
                prefix = "🥉"
            else:
                prefix = f"{index}."

            msg_content += f"{prefix} {title}"
            if hot:
                msg_content += f" ({hot})"
            msg_content += "\n"

        msg_content += (
            "━━━━━━━━━━━━━\n"
            "💡 数据来源: 微博热搜榜"
        )

        await weibo_hot.finish(message_add_head(msg_content, event))

    except requests.RequestException as e:
        logger.error(f"微博热搜API请求失败: {e}")
        await weibo_hot.finish(message_add_head("❌ 网络请求失败,请稍后再试", event))
    except json.JSONDecodeError as e:
        logger.error(f"微博热搜JSON解析失败: {e}")
        await weibo_hot.finish(message_add_head("❌ 数据解析失败", event))



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



