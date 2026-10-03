"""
称号配图管理命令
玩家（等级>50）可以为自己拥有的称号提交横幅配图，佩戴该称号时展示在面板最上方
管理员可以覆盖和删除配图
"""
from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import yaml
from pathlib import Path
import aiohttp
import asyncio
from io import BytesIO
from PIL import Image

from ..image_dimensions import parse_image_dimensions, scale_image_dimensions
from ..utils import message_add_head
from ..models.db import safe_session
from ..platform_utils import require_player
from ..ai_guide import is_admin


# 配置文件路径
TITLE_IMAGES_CONFIG = Path(__file__).parent.parent / "data" / "title_images.yaml"
# 图片尺寸缓存路径
TITLE_IMAGE_DIMENSIONS_CACHE = Path(__file__).parent.parent / "data" / "title_image_dimensions.yaml"

# 横幅最大宽度（按宽度等比缩放，适配面板顶部展示）
BANNER_MAX_WIDTH = 360


def _load_title_images() -> dict:
    """加载称号配图配置 {称号名: 图片URL}"""
    if not TITLE_IMAGES_CONFIG.exists():
        return {}

    try:
        with open(TITLE_IMAGES_CONFIG, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except (OSError, yaml.YAMLError) as e:
        print(f"加载称号配图配置失败: {e}")
        return {}


def _save_title_images(data: dict) -> bool:
    """保存称号配图配置"""
    try:
        TITLE_IMAGES_CONFIG.parent.mkdir(parents=True, exist_ok=True)

        with open(TITLE_IMAGES_CONFIG, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except (OSError, yaml.YAMLError) as e:
        print(f"保存称号配图配置失败: {e}")
        return False


def _load_dimensions_cache() -> dict:
    """加载图片尺寸缓存 {称号名: {"url": "...", "width": 360, "height": 113}}"""
    if not TITLE_IMAGE_DIMENSIONS_CACHE.exists():
        return {}

    try:
        with open(TITLE_IMAGE_DIMENSIONS_CACHE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except (OSError, yaml.YAMLError) as e:
        print(f"加载称号配图尺寸缓存失败: {e}")
        return {}


def _save_dimensions_cache(data: dict) -> bool:
    """保存图片尺寸缓存"""
    try:
        TITLE_IMAGE_DIMENSIONS_CACHE.parent.mkdir(parents=True, exist_ok=True)

        with open(TITLE_IMAGE_DIMENSIONS_CACHE, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except (OSError, yaml.YAMLError) as e:
        print(f"保存称号配图尺寸缓存失败: {e}")
        return False


def _clear_dimensions_cache(title: str) -> None:
    """清除指定称号的图片尺寸缓存"""
    cache = _load_dimensions_cache()
    if title in cache:
        del cache[title]
        _save_dimensions_cache(cache)


def get_title_image(title: str) -> tuple[str, int, int] | None:
    """获取称号配图信息，供玩家面板渲染

    Returns:
        (url, width, height)，未配置返回 None
    """
    images = _load_title_images()
    image_url = images.get(title)
    if not image_url:
        return None

    # URL中的括号会提前闭合Markdown的![](...)语法，返回前需百分号编码
    # 注意尺寸缓存里存的是原始URL，比对须用编码前的值
    safe_url = image_url.replace("(", "%28").replace(")", "%29")

    dimensions = parse_image_dimensions(image_url)
    if dimensions is not None:
        width, height = scale_image_dimensions(*dimensions, BANNER_MAX_WIDTH)
        return safe_url, width, height

    cache = _load_dimensions_cache()
    cached = cache.get(title, {})
    if cached.get("url") == image_url:
        return safe_url, cached.get("width", BANNER_MAX_WIDTH), cached.get("height", 113)

    # 缓存缺失时使用默认横幅比例（提交时会预取，正常不会走到这里）
    return safe_url, BANNER_MAX_WIDTH, 113


def _get_all_owned_titles(player) -> list[str]:
    """获取玩家拥有的全部称号（活动称号+赞助自定义称号）"""
    from ..event.knocker_event import KnockerEventService
    from ..sponsor.service import SponsorShopService

    event_titles = KnockerEventService.get_owned_titles(player)
    sponsor_titles = SponsorShopService.get_owned_custom_titles(player)
    return event_titles + [t for t in sponsor_titles if t not in event_titles]


def _validate_image_url(image_url: str) -> bool:
    """验证图片URL格式"""
    return image_url.startswith("https://") or image_url.startswith("http://")


async def _prefetch_image_dimensions(title: str, image_url: str) -> tuple[bool, str]:
    """预先获取图片尺寸并缓存（按宽度等比缩放至 BANNER_MAX_WIDTH）

    Returns:
        (是否成功, 错误信息)
    """
    try:
        dimensions = parse_image_dimensions(image_url)
        if dimensions is not None:
            width, height = scale_image_dimensions(*dimensions, BANNER_MAX_WIDTH)
            cache = _load_dimensions_cache()
            cache[title] = {"url": image_url, "width": width, "height": height}
            _save_dimensions_cache(cache)
            return True, ""

        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status != 200:
                    return False, f"获取图片失败: HTTP {response.status}"

                image_data = await response.read()

                image = Image.open(BytesIO(image_data))
                original_width, original_height = image.size

                if original_width > BANNER_MAX_WIDTH:
                    scale = BANNER_MAX_WIDTH / original_width
                    new_width = BANNER_MAX_WIDTH
                    new_height = max(1, int(original_height * scale))
                else:
                    new_width = original_width
                    new_height = original_height

                cache = _load_dimensions_cache()
                cache[title] = {
                    "url": image_url,
                    "width": new_width,
                    "height": new_height
                }
                _save_dimensions_cache(cache)
                print(f"已缓存称号配图尺寸: {title} -> {new_width}x{new_height}")

                return True, ""

    except asyncio.TimeoutError:
        return False, "获取图片尺寸超时（10秒）"
    except (aiohttp.ClientError, OSError, ValueError, Image.DecompressionBombError) as e:
        return False, f"获取图片尺寸失败: {str(e)}"


# 玩家提交称号配图（等级>50，需拥有该称号）
submit_title_image_cmd = on_command("提交称号图片", aliases={"上传称号图片", "提交称号配图"}, priority=4, block=True)

@submit_title_image_cmd.handle()
async def handle_submit_title_image(event: MessageEvent, args: Message = CommandArg()):
    """玩家提交称号配图URL（等级>50，需拥有该称号，只能为没有配图的称号提供，管理员可覆盖）

    格式：提交称号图片 称号名 图片URL
    """
    params = args.extract_plain_text().strip().split(maxsplit=1)

    if len(params) != 2:
        await submit_title_image_cmd.finish("⛔ 格式错误\n正确格式：提交称号图片 称号名 图片URL")

    title_name, image_url = params

    if not _validate_image_url(image_url):
        await submit_title_image_cmd.finish(
            "⛔ 图片链接不符合要求\n"
            "━━━━━━━━━━━━━\n"
            "请提供有效的图片URL（以http://或https://开头）\n"
            "━━━━━━━━━━━━━\n"
            "💡 请确保链接可以直接访问到图片"
        )

    admin = is_admin(event.get_user_id())

    # 获取玩家信息
    async with safe_session() as session:
        player = await require_player(session, event, submit_title_image_cmd)

        # 检查等级限制（管理员跳过）
        if not admin and player.level <= 50:
            await submit_title_image_cmd.finish(
                f"⛔ 等级限制\n当前等级：{player.level}\n需要等级：>50\n💡 继续修炼提升等级后即可提交配图"
            )

        # 检查是否拥有该称号（管理员跳过）
        if not admin:
            owned_titles = _get_all_owned_titles(player)
            if title_name not in owned_titles:
                owned_text = "、".join(owned_titles) if owned_titles else "无"
                await submit_title_image_cmd.finish(
                    f"⛔ 你没有该称号：{title_name}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"你拥有的称号：{owned_text}\n"
                    f"💡 只能为自己拥有的称号提交配图"
                )

    # 加载配置
    images = _load_title_images()

    # 检查是否已有配图（只有管理员才能覆盖）
    if title_name in images and not admin:
        await submit_title_image_cmd.finish(
            f"⛔ 该称号已有配图\n"
            f"━━━━━━━━━━━━━\n"
            f"称号：{title_name}\n"
            f"💡 只有管理员才能覆盖已有配图\n"
            f"💡 如需修改配图，请联系管理员"
        )

    # 预先获取图片尺寸并缓存
    success, fetch_error = await _prefetch_image_dimensions(title_name, image_url)
    if not success:
        await submit_title_image_cmd.finish(
            f"⛔ 图片验证失败\n"
            f"━━━━━━━━━━━━━\n"
            f"错误信息：{fetch_error}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 请检查图片链接是否正确\n"
            f"💡 确保图片可以正常访问"
        )

    # 设置图片URL
    images[title_name] = image_url

    # 保存配置
    if _save_title_images(images):
        # URL转大写以避免QQ官方的URL检测
        display_url = image_url.upper()
        msg = (
            f"✅ 提交成功\n"
            f"━━━━━━━━━━━━━\n"
            f"称号：{title_name}\n"
            f"图片URL：{display_url}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 佩戴该称号后使用【面板】查看效果\n"
            f"💡 未佩戴？使用【切换称号 {title_name}】\n"
            f"🎉 感谢你为称号系统做出的贡献！"
        )
        await submit_title_image_cmd.finish(message_add_head(msg, event))
    else:
        await submit_title_image_cmd.finish("⛔ 保存配置失败")


# 删除称号配图（超管）
delete_title_image_cmd = on_command("删除称号图片", aliases={"删除称号配图"}, permission=SUPERUSER, priority=4, block=True)

@delete_title_image_cmd.handle()
async def handle_delete_title_image(event: MessageEvent, args: Message = CommandArg()):
    """删除称号配图配置

    格式：删除称号图片 称号名
    """
    title_name = args.extract_plain_text().strip()

    if not title_name:
        await delete_title_image_cmd.finish("⛔ 请提供称号名称")

    images = _load_title_images()

    if title_name not in images:
        await delete_title_image_cmd.finish(f"⛔ 该称号未配置配图：{title_name}")

    del images[title_name]

    if _save_title_images(images):
        _clear_dimensions_cache(title_name)

        msg = (
            f"✅ 删除成功\n"
            f"━━━━━━━━━━━━━\n"
            f"称号：{title_name}"
        )
        await delete_title_image_cmd.finish(message_add_head(msg, event))
    else:
        await delete_title_image_cmd.finish("⛔ 保存配置失败")
