from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from sqlalchemy import select

from datetime import date
import random
import hashlib

from ..config import config
from ..models.db import safe_session
from ..models.player import Player
from ..models.guild import Guild
from ..models.inventory import Inventory
from ..models.equipment import EquipmentInstance
from ..utils import message_add_head

__all__ = [
    "guild_shop_cmd",
    "guild_buy_cmd",
]

# ---------------- 指令注册 ----------------

guild_shop_cmd = on_command(
    "公会商店",
    aliases={"公会商城", "宗门商店"},
    block=True,
    priority=5,
)

guild_buy_cmd = on_command(
    "公会购买",
    aliases={"贡献购买"},
    block=True,
    priority=5,
)


# ---------------- 核心逻辑 ----------------


def _deterministic_rng(guild_id: int) -> random.Random:
    """为同一天同一公会生成确定性的随机数生成器。"""
    seed_str = f"{guild_id}-{date.today().isoformat()}"
    seed_int = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    return random.Random(seed_int)


def _split_equipments():
    """按可锻造 / 不可锻造拆分装备配置。"""
    equip_ids = config.items_config["by_type"].get("EQUIPMENT", [])
    craftable = []
    uncraftable = []
    for eid in equip_ids:
        cfg = config.items_config["by_id"][eid]
        if cfg.recipe:
            craftable.append(cfg)
        else:
            uncraftable.append(cfg)
    return craftable, uncraftable


def generate_guild_shop(guild: Guild) -> list[tuple]:
    """根据公会等级生成公会商店出售列表 [(ItemConfig, price)]"""
    craftable, uncraftable = _split_equipments()

    # 计算展示数量 x = 3 + level
    total_count = 2 + (guild.level if guild.level < 9 else 8)

    # 高级（不可锻造）装备出现比例
    high_ratio = min(0.1 * guild.level, 0.8)  # 每级 +10% 上限 80%
    high_count = max(1, round(total_count * high_ratio)) if uncraftable else 0
    high_count = min(high_count, len(uncraftable))

    normal_count = total_count - high_count
    normal_count = min(normal_count, len(craftable))

    rng = _deterministic_rng(guild.id)

    selected = []
    if high_count:
        selected.extend(rng.sample(uncraftable, k=high_count))
    if normal_count:
        selected.extend(rng.sample(craftable, k=normal_count))

    # 回退策略：当可选不足时补齐
    if len(selected) < total_count:
        remaining_cfgs = [cfg for cfg in craftable + uncraftable if cfg not in selected]
        if remaining_cfgs:
            need = total_count - len(selected)
            selected.extend(rng.sample(remaining_cfgs, k=min(need, len(remaining_cfgs))))

    # 按价格排序
    selected.sort(key=lambda c: c.price)
    return [(cfg, cfg.price) for cfg in selected]


async def format_guild_shop(shop_sell: list, player_points: int, guild: Guild) -> str:
    """公会商店展示格式"""
    content: list[str] = [
        f"🏛️ 公会商店 (Lv.{guild.level})",
        "▃" * 12,
        f"✨ 你的积分：{player_points}",
        "",
        "🛒 可兑换装备：",
    ]

    for idx, (item, price) in enumerate(shop_sell, 1):
        content.append(
            f"{idx}. {item.name} - {price}✨/件"
        )

    content.extend([
        "\n📝 操作指南：",
        "公会购买 [序号|名称] [数量] - 兑换装备",
    ])
    return "\n".join(content)


# ---------------- 指令处理 ----------------


@guild_shop_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await guild_shop_cmd.finish("⛔ 请先创建角色")
        if not player.guild_id:
            await guild_shop_cmd.finish("⛔ 你还未加入任何公会")

        guild = await session.get(Guild, player.guild_id)
        if not guild:
            await guild_shop_cmd.finish("⛔ 公会数据缺失，请联系管理员")

        shop_sell = generate_guild_shop(guild)
        await guild_shop_cmd.finish(
            message_add_head(await format_guild_shop(shop_sell, player.gold2, guild), event)
        )


@guild_buy_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_str = args.extract_plain_text().strip()
    parts = arg_str.split()

    # 参数校验
    if not parts or len(parts) > 2:
        await guild_buy_cmd.finish("⛔ 格式错误，正确示例：公会购买 2 3 或 公会购买 幸运剪刀 1")

    # 解析数量
    try:
        quantity = int(parts[1]) if len(parts) == 2 else 1
        if quantity < 1:
            raise ValueError
    except ValueError:
        await guild_buy_cmd.finish("⛔ 数量必须为正整数")

    is_index_mode = parts[0].isdigit()

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await guild_buy_cmd.finish("⛔ 请先创建角色")
        if not player.guild_id:
            await guild_buy_cmd.finish("⛔ 你还未加入任何公会")

        guild = await session.get(Guild, player.guild_id)
        if not guild:
            await guild_buy_cmd.finish("⛔ 公会数据缺失，请联系管理员")

        sell_list = generate_guild_shop(guild)

        # 查找目标物品
        if is_index_mode:
            try:
                index = int(parts[0]) - 1
                if index < 0:
                    raise ValueError
            except ValueError:
                await guild_buy_cmd.finish("⛔ 无效的商品序号")
            if index >= len(sell_list):
                await guild_buy_cmd.finish("⛔ 无效的商品序号")
            item_cfg, price = sell_list[index]
        else:
            item_name = parts[0]
            match = next(((cfg, pr) for cfg, pr in sell_list if cfg.name == item_name), None)
            if not match:
                await guild_buy_cmd.finish("⛔ 无效的商品名称，或当前未上架")
            item_cfg, price = match

        total_cost = price * quantity
        if player.gold2 < total_cost:
            await guild_buy_cmd.finish(
                f"⛔ 积分不足，需要 {total_cost}✨ 当前拥有 {player.gold2}✨"
            )

        # 扣除积分
        player.gold2 -= total_cost

        if item_cfg.type.value == "EQUIPMENT":
            # 逐件创建装备实例
            for _ in range(quantity):
                session.add(
                    EquipmentInstance(
                        player_id=event.get_user_id(),
                        template_id=item_cfg.item_id,
                        durability=item_cfg.durability,
                    )
                )
        else:
            # 非装备统一存入背包
            inv = (
                await session.execute(
                    select(Inventory).where(
                        Inventory.player_id == event.get_user_id(),
                        Inventory.item_id == item_cfg.item_id,
                    )
                )
            ).scalars().first()
            if inv:
                inv.quantity += quantity
            else:
                session.add(
                    Inventory(
                        player_id=event.get_user_id(),
                        item_id=item_cfg.item_id,
                        quantity=quantity,
                    )
                )

        await session.commit()
        await guild_buy_cmd.finish(
            f"✅ 成功兑换 {item_cfg.name} ✖️{quantity}（单价 {price}✨ 共消耗 {total_cost}✨）"
        ) 