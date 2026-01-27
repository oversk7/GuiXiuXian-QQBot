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

from ..config import config
from ..utils import message_add_head
from ..models.db import safe_session
from ..platform_utils import get_unified_player


# 配置文件路径
ITEM_IMAGES_CONFIG = Path(__file__).parent.parent.parent.parent / "data" / "item_images.yaml"


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


# 设置物品图片
set_item_image_cmd = on_command("设置物品图片", permission=SUPERUSER, priority=4, block=True)

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

    # 获取玩家信息
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await submit_item_image_cmd.finish("⛔ 请先使用【我的信息】创建角色")

        # 检查等级限制
        if player.level <= 50:
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

    # 设置图片URL
    images[item_cfg.item_id] = image_url

    # 保存配置
    if _save_item_images(images):
        # 清除旧的尺寸缓存
        _clear_image_dimensions_cache(item_cfg.item_id)

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
