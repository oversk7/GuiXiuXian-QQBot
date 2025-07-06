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

    # 类型映射
    TYPE_NAME_MAP = {
        "CONSUMABLE": "消耗品",
        "MATERIAL": "材料",
        "EQUIPMENT": "装备",
    }

    lines = ["📖 物品 & 装备图鉴 ✨", "━━━━━━━━━━"]

    for cfg in matches:
        type_cn = TYPE_NAME_MAP.get(cfg.type.value, cfg.type.value)

        extra_info = ""
        # 若为装备，附加属性加成信息
        if cfg.type.value == "EQUIPMENT":
            ATTR_CN = {
                "attack": "力",
                "defense": "防",
                "agility": "敏",
                "luck": "运",
                "max_hp": "体",
                "max_mp": "智",
                "hp": "体",
                "mp": "智",
            }

            bonus_parts = []
            if cfg.attr_bonus:
                for k, v in cfg.attr_bonus.items():
                    cn = ATTR_CN.get(k, k)
                    bonus_parts.append(f"{cn}+{v}")
            if cfg.attr_ratio:
                for k, v in cfg.attr_ratio.items():
                    if v:
                        cn = ATTR_CN.get(k, k)
                        bonus_parts.append(f"{cn}+{int(v*100)}%")
            if bonus_parts:
                extra_info = "\n🔧 属性加成：" + " 、".join(bonus_parts)

        # 若为材料，展示价格和怨念值
        elif cfg.type.value == "MATERIAL":
            price_info = f"💰 市场价：{cfg.price} 金币"
            grudge_info = f"😈 怨念值：{cfg.grudge_value}" if cfg.grudge_value else ""
            extra_info = "\n" + "  ".join(filter(bool, [price_info, grudge_info]))

        lines.append(f"✨ {cfg.name} ✨  [{type_cn}]\n{cfg.description}{extra_info}\n")

    await catalog_cmd.finish(message_add_head("\n".join(lines), event)) 