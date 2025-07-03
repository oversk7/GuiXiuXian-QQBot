from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..config import config
from ..utils import message_add_head

# 图鉴命令：查询单个/关键字匹配的物品或装备描述
catalog_cmd = on_command("图鉴", aliases={"物品图鉴", "装备图鉴", "物品列表"}, block=True, priority=5)


@catalog_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """展示 items.yaml 中全部物品与装备的名称和描述，可选参数 name 用于关键字过滤"""
    keyword = args.extract_plain_text().strip()

    # 必须提供关键字，否则提醒
    if not keyword:
        await catalog_cmd.finish("⛔ 请提供要查询的物品名称，例如：图鉴 回春散")

    by_id = config.items_config["by_id"]
    # 1. 先尝试精确匹配名称
    exact_cfg = config.items_config["by_name"].get(keyword)
    matches = []
    if exact_cfg:
        matches.append(exact_cfg)
    else:
        # 2. 子串模糊匹配名称或描述
        for cfg in by_id.values():
            if keyword in cfg.name or keyword in cfg.description:
                matches.append(cfg)

    if not matches:
        await catalog_cmd.finish("⛔ 未找到符合条件的物品/装备")

    # 若匹配过多（>6），让用户缩小范围
    if len(matches) > 6:
        await catalog_cmd.finish(f"⚠️ 匹配到 {len(matches)} 条记录，请输入更精确的名称")

    # 构造回复
    lines = ["📖 物品 & 装备图鉴", "▃▃▃▃▃▃▃▃▃▃"]
    for cfg in matches:
        lines.append(f"{cfg.name} ({cfg.type.value})\n{cfg.description}")

    await catalog_cmd.finish(message_add_head("\n".join(lines), event)) 