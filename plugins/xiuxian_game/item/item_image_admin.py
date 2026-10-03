"""
物品图片管理命令
管理员可以设置、删除和查看物品图片配置
玩家（等级>50）可以为没有图片的物品提供图片
"""
from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import yaml
from pathlib import Path
from sqlalchemy import select
import aiohttp
import asyncio
from io import BytesIO
from PIL import Image

from ..config import config
from ..image_dimensions import parse_image_dimensions, scale_image_dimensions
from ..utils import message_add_head
from ..models.db import safe_session
from ..platform_utils import require_player
from ..ai_guide import is_admin


# 配置文件路径
ITEM_IMAGES_CONFIG = Path(__file__).parent.parent / "data" / "item_images.yaml"

# 允许的图床URL前缀（不再限制特定图床，只要求HTTPS）
ALLOWED_IMAGE_PREFIXES = [
    "https://",  # 允许所有HTTPS链接
    "http://",   # 允许所有HTTP链接
]


def _load_item_images() -> dict:
    """加载物品图片配置"""
    if not ITEM_IMAGES_CONFIG.exists():
        return {}

    try:
        with open(ITEM_IMAGES_CONFIG, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception as e:
        print(f"加载物品图片配置失败: {e}")
        return {}


def _save_item_images(data: dict) -> bool:
    """保存物品图片配置"""
    try:
        # 确保目录存在
        ITEM_IMAGES_CONFIG.parent.mkdir(parents=True, exist_ok=True)

        with open(ITEM_IMAGES_CONFIG, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception as e:
        print(f"保存物品图片配置失败: {e}")
        return False


def _clear_image_dimensions_cache(item_id: str) -> None:
    """清除指定物品的图片尺寸缓存

    Args:
        item_id: 物品ID
    """
    try:
        cache_path = ITEM_IMAGES_CONFIG.parent / "item_image_dimensions.yaml"

        if not cache_path.exists():
            return

        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = yaml.safe_load(f)

        if not cache:
            return

        # 删除该物品的缓存
        if item_id in cache:
            del cache[item_id]

            # 保存更新后的缓存
            with open(cache_path, 'w', encoding='utf-8') as f:
                yaml.dump(cache, f, allow_unicode=True, default_flow_style=False)
            print(f"已清除物品 {item_id} 的图片尺寸缓存")
    except Exception as e:
        print(f"清除图片尺寸缓存失败: {e}")


def _validate_image_url(image_url: str) -> tuple[bool, str]:
    """验证图片URL是否符合白名单要求

    Args:
        image_url: 图片URL

    Returns:
        (是否有效, 错误信息)
    """
    # 检查是否以允许的前缀开头
    for prefix in ALLOWED_IMAGE_PREFIXES:
        if image_url.startswith(prefix):
            return True, ""

    # 如果不匹配任何前缀（不是有效的URL）
    error_msg = (
        f"⛔ 图片链接不符合要求\n"
        f"━━━━━━━━━━━━━\n"
        f"请提供有效的图片URL（以http://或https://开头）\n"
        f"━━━━━━━━━━━━━\n"
        f"💡 请确保链接可以直接访问到图片"
    )
    return False, error_msg


def _load_image_dimensions_cache() -> dict:
    """加载图片尺寸缓存

    Returns:
        物品ID到图片信息的映射字典 {item_id: {"url": "...", "width": 300, "height": 200}}
    """
    cache_path = ITEM_IMAGES_CONFIG.parent / "item_image_dimensions.yaml"

    if not cache_path.exists():
        return {}

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception as e:
        print(f"加载图片尺寸缓存失败: {e}")
        return {}


def _save_image_dimensions_cache(data: dict) -> bool:
    """保存图片尺寸缓存

    Args:
        data: 缓存数据字典

    Returns:
        是否保存成功
    """
    try:
        cache_path = ITEM_IMAGES_CONFIG.parent / "item_image_dimensions.yaml"
        # 确保目录存在
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception as e:
        print(f"保存图片尺寸缓存失败: {e}")
        return False


async def _prefetch_image_dimensions(item_id: str, image_url: str, max_size: int = 300) -> tuple[bool, str]:
    """预先获取并缓存图片尺寸

    Args:
        item_id: 物品ID
        image_url: 图片URL
        max_size: 最大尺寸限制（宽度或高度的最大值）

    Returns:
        (是否成功, 错误信息)
    """
    try:
        dimensions = parse_image_dimensions(image_url)
        if dimensions is not None:
            width, height = scale_image_dimensions(*dimensions, max_size, max_size)
            cache = _load_image_dimensions_cache()
            cache[item_id] = {"url": image_url, "width": width, "height": height}
            _save_image_dimensions_cache(cache)
            return True, ""

        print(f"预先获取图片尺寸: {image_url}")

        # 设置超时时间
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status != 200:
                    error_msg = f"获取图片失败: HTTP {response.status}"
                    print(error_msg)
                    return False, error_msg

                # 读取图片数据
                image_data = await response.read()

                # 使用PIL解析图片尺寸
                image = Image.open(BytesIO(image_data))
                original_width, original_height = image.size

                # 计算等比缩放
                if original_width > max_size or original_height > max_size:
                    # 需要缩放
                    if original_width > original_height:
                        # 宽度更大，以宽度为基准
                        scale = max_size / original_width
                    else:
                        # 高度更大，以高度为基准
                        scale = max_size / original_height

                    new_width = int(original_width * scale)
                    new_height = int(original_height * scale)
                else:
                    # 不需要缩放
                    new_width = original_width
                    new_height = original_height

                # 保存到缓存
                cache = _load_image_dimensions_cache()
                cache[item_id] = {
                    "url": image_url,
                    "width": new_width,
                    "height": new_height
                }
                _save_image_dimensions_cache(cache)
                print(f"已缓存图片尺寸: {item_id} -> {new_width}x{new_height}")

                return True, ""

    except asyncio.TimeoutError:
        error_msg = f"获取图片尺寸超时（10秒）"
        print(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"获取图片尺寸失败: {str(e)}"
        print(error_msg)
        return False, error_msg


# 设置物品图片
set_item_image_cmd = on_command("设置物品图片", priority=4, block=True)

@set_item_image_cmd.handle()
async def handle_set_item_image(event: MessageEvent, args: Message = CommandArg()):
    """设置物品图片URL

    格式：设置物品图片 物品名 图片URL
    """
    params = args.extract_plain_text().strip().split(maxsplit=1)

    if len(params) != 2:
        await set_item_image_cmd.finish("⛔ 格式错误\n正确格式：设置物品图片 物品名 图片URL")

    item_name, image_url = params

    # 查找物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await set_item_image_cmd.finish(f"⛔ 未找到物品：{item_name}")

    # 加载配置
    images = _load_item_images()

    # 检查是否已有图片（只有管理员才能覆盖）
    user_id = event.get_user_id()
    if item_cfg.item_id in images and not is_admin(user_id):
        await set_item_image_cmd.finish(
            f"⛔ 该物品已有图片配置\n"
            f"━━━━━━━━━━━━━\n"
            f"物品：{item_cfg.name}\n"
            f"💡 只有管理员才能覆盖已有图片\n"
            f"💡 如需修改图片，请联系管理员"
        )

    # 设置图片URL
    images[item_cfg.item_id] = image_url

    # 保存配置
    if _save_item_images(images):
        # 清除旧的尺寸缓存（因为URL可能变化了）
        _clear_image_dimensions_cache(item_cfg.item_id)

        # URL转大写以避免QQ官方的URL检测
        display_url = image_url.upper()
        msg = (
            f"✅ 设置成功\n"
            f"━━━━━━━━━━━━━\n"
            f"物品：{item_cfg.name}\n"
            f"物品ID：{item_cfg.item_id}\n"
            f"图片URL：{display_url}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 使用【图鉴 {item_name}】查看效果"
        )
        await set_item_image_cmd.finish(message_add_head(msg, event))
    else:
        await set_item_image_cmd.finish("⛔ 保存配置失败")


# 删除物品图片
delete_item_image_cmd = on_command("删除物品图片", permission=SUPERUSER, priority=4, block=True)

@delete_item_image_cmd.handle()
async def handle_delete_item_image(event: MessageEvent, args: Message = CommandArg()):
    """删除物品图片配置

    格式：删除物品图片 物品名
    """
    item_name = args.extract_plain_text().strip()

    if not item_name:
        await delete_item_image_cmd.finish("⛔ 请提供物品名称")

    # 查找物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await delete_item_image_cmd.finish(f"⛔ 未找到物品：{item_name}")

    # 加载配置
    images = _load_item_images()

    # 检查是否存在
    if item_cfg.item_id not in images:
        await delete_item_image_cmd.finish(f"⛔ 该物品未配置图片")

    # 删除配置
    del images[item_cfg.item_id]

    # 保存配置
    if _save_item_images(images):
        # 清除尺寸缓存
        _clear_image_dimensions_cache(item_cfg.item_id)

        msg = (
            f"✅ 删除成功\n"
            f"━━━━━━━━━━━━━\n"
            f"物品：{item_cfg.name}\n"
            f"物品ID：{item_cfg.item_id}"
        )
        await delete_item_image_cmd.finish(message_add_head(msg, event))
    else:
        await delete_item_image_cmd.finish("⛔ 保存配置失败")


# 物品图片列表
item_images_list_cmd = on_command("物品图片列表", permission=SUPERUSER, priority=4, block=True)

@item_images_list_cmd.handle()
async def handle_item_images_list(event: MessageEvent, args: Message = CommandArg()):
    """查看所有已配置的物品图片"""
    images = _load_item_images()

    if not images:
        await item_images_list_cmd.finish(message_add_head("📝 暂无物品图片配置", event))

    lines = [
        "📝 物品图片配置列表",
        "━━━━━━━━━━━━━",
        f"总计：{len(images)} 个物品"
    ]

    # 按物品类型分组
    by_id = config.items_config["by_id"]

    for item_id, image_url in images.items():
        item_cfg = by_id.get(item_id)
        if item_cfg:
            # 截断URL显示
            display_url = image_url if len(image_url) <= 40 else image_url[:37] + "..."
            lines.append(f"• {item_cfg.name} ({item_id})")
            lines.append(f"  {display_url}")
        else:
            lines.append(f"• [未知物品] ({item_id})")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【设置物品图片 物品名 URL】添加配置")
    lines.append("💡 使用【删除物品图片 物品名】删除配置")

    await item_images_list_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 玩家命令 ====================

# 玩家提交物品图片（等级>50）
submit_item_image_cmd = on_command("提交物品图片", aliases={"上传物品图片"}, priority=4, block=True)

@submit_item_image_cmd.handle()
async def handle_submit_item_image(event: MessageEvent, args: Message = CommandArg()):
    """玩家提交物品图片URL（等级>50，只能为没有图片的物品提供）

    格式：提交物品图片 物品名 图片URL
    """
    params = args.extract_plain_text().strip().split(maxsplit=1)

    if len(params) != 2:
        await submit_item_image_cmd.finish("⛔ 格式错误\n正确格式：提交物品图片 物品名 图片URL")

    item_name, image_url = params

    # 验证图片URL
    is_valid, error_msg = _validate_image_url(image_url)
    if not is_valid:
        await submit_item_image_cmd.finish(error_msg)

    # 获取玩家信息
    async with safe_session() as session:
        player = await require_player(session, event, submit_item_image_cmd)

        # 检查等级限制（管理员跳过）
        if not is_admin(event.get_user_id()) and player.level <= 50:
            await submit_item_image_cmd.finish(f"⛔ 等级限制\n当前等级：{player.level}\n需要等级：>50\n💡 继续修炼提升等级后即可提交图片")

    # 查找物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await submit_item_image_cmd.finish(f"⛔ 未找到物品：{item_name}")

    # 加载配置
    images = _load_item_images()

    # 检查是否已有图片（玩家只能为没有图片的物品提供）
    if item_cfg.item_id in images:
        await submit_item_image_cmd.finish(
            f"⛔ 该物品已有图片配置\n"
            f"━━━━━━━━━━━━━\n"
            f"物品：{item_cfg.name}\n"
            f"💡 如需修改图片，请联系管理员"
        )

    # 预先获取图片尺寸并缓存
    success, fetch_error = await _prefetch_image_dimensions(item_cfg.item_id, image_url)
    if not success:
        await submit_item_image_cmd.finish(
            f"⛔ 图片验证失败\n"
            f"━━━━━━━━━━━━━\n"
            f"错误信息：{fetch_error}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 请检查图片链接是否正确\n"
            f"💡 确保图片可以正常访问"
        )

    # 设置图片URL
    images[item_cfg.item_id] = image_url

    # 保存配置
    if _save_item_images(images):
        # URL转大写以避免QQ官方的URL检测
        display_url = image_url.upper()
        msg = (
            f"✅ 提交成功\n"
            f"━━━━━━━━━━━━━\n"
            f"物品：{item_cfg.name}\n"
            f"物品ID：{item_cfg.item_id}\n"
            f"图片URL：{display_url}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 使用【图鉴 {item_name}】查看效果\n"
            f"🎉 感谢你为图鉴系统做出的贡献！"
        )
        await submit_item_image_cmd.finish(message_add_head(msg, event))
    else:
        await submit_item_image_cmd.finish("⛔ 保存配置失败")
