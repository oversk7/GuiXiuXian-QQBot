"""
物品图片管理命令
管理员可以设置、删除和查看物品图片配置
"""
from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import yaml
from pathlib import Path

from ..config import config
from ..utils import message_add_head


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
