"""
阴宅仓库命令处理器

命令列表：
- 【阴宅仓库】      查看仓库内容和容量
- 【存入阴宅 <物品名> <数量>】  将背包物品存入仓库
- 【取出阴宅 <序号> <数量>】    从仓库取出物品到背包

访问限制：必须在自己的阴宅坐标位置
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..utils import message_add_head
from ..models.db import safe_session
from ..models.player import Player
from ..config import config
from ..platform_utils import require_player

# 命令注册
mansion_warehouse_cmd = on_command("阴宅仓库", aliases={"查看阴宅仓库"}, priority=4, block=True)
deposit_mansion_cmd = on_command("存入阴宅", aliases={"阴宅存入"}, priority=4, block=True)
withdraw_mansion_cmd = on_command("取出阴宅", aliases={"阴宅取出"}, priority=4, block=True)


def _build_service(session):
    """构建 MansionWarehouseService 实例"""
    from ..infrastructure.repositories.mansion_warehouse_item_repository import MansionWarehouseItemRepository
    from ..infrastructure.repositories.item_repository import ItemRepository
    from .mansion_warehouse_service import MansionWarehouseService
    return MansionWarehouseService(
        warehouse_repo=MansionWarehouseItemRepository(session),
        item_repo=ItemRepository(session),
    )


@mansion_warehouse_cmd.handle()
async def handle_mansion_warehouse(event: MessageEvent):
    """查看阴宅仓库"""
    async with safe_session() as session:
        player = await require_player(session, event, mansion_warehouse_cmd)

        if player.mansion_level <= 0:
            await mansion_warehouse_cmd.finish(message_add_head(
                "⛔ 你还没有阴宅\n💡 请先使用【购买阴宅】命令购买阴宅",
                event
            ))

        from ..sponsor.service import SponsorShopService
        has_remote_warehouse = SponsorShopService.is_privilege_active(player, "premium_warehouse_until")

        from .mansion_service import MansionService
        if not has_remote_warehouse and not MansionService.is_at_mansion(player):
            await mansion_warehouse_cmd.finish(message_add_head(
                f"⛔ 你不在自己的阴宅位置\n"
                f"💡 阴宅坐标：({player.mansion_x}, {player.mansion_y})\n"
                f"💡 请移动到阴宅位置后再访问仓库\n"
                f"💡 或购买【远程仓库特权】随时访问",
                event
            ))

        service = _build_service(session)
        display = await service.format_warehouse_display(player.id, player.mansion_level)
        await mansion_warehouse_cmd.finish(message_add_head(display, event))


@deposit_mansion_cmd.handle()
async def handle_deposit_mansion(event: MessageEvent, args: Message = CommandArg()):
    """存入物品到阴宅仓库"""
    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        await deposit_mansion_cmd.finish(message_add_head(
            "用法：【存入阴宅 <物品名> <数量>】\n"
            "例如：【存入阴宅 腐朽尸骸 100】",
            event
        ))

    parts = arg_text.rsplit(maxsplit=1)
    if len(parts) != 2:
        await deposit_mansion_cmd.finish(message_add_head(
            "⛔ 格式错误，请输入：【存入阴宅 <物品名> <数量>】",
            event
        ))

    item_name, qty_str = parts
    try:
        quantity = int(qty_str)
    except ValueError:
        await deposit_mansion_cmd.finish(message_add_head("⛔ 数量必须是正整数", event))

    if quantity <= 0:
        await deposit_mansion_cmd.finish(message_add_head("⛔ 数量必须大于0", event))

    async with safe_session() as session:
        player = await require_player(session, event, deposit_mansion_cmd)

        if player.mansion_level <= 0:
            await deposit_mansion_cmd.finish(message_add_head(
                "⛔ 你还没有阴宅，无法使用仓库", event
            ))

        from ..sponsor.service import SponsorShopService
        has_remote_warehouse = SponsorShopService.is_privilege_active(player, "premium_warehouse_until")

        from .mansion_service import MansionService
        if not has_remote_warehouse and not MansionService.is_at_mansion(player):
            await deposit_mansion_cmd.finish(message_add_head(
                f"⛔ 你不在自己的阴宅位置\n"
                f"💡 阴宅坐标：({player.mansion_x}, {player.mansion_y})\n"
                f"💡 请移动到阴宅位置后再访问仓库\n"
                f"💡 或购买【远程仓库特权】随时访问",
                event
            ))

        # 通过物品名查找 item_id
        item_id = None
        for iid, icfg in config.items_config["by_id"].items():
            if icfg.name == item_name:
                item_id = iid
                break

        if not item_id:
            await deposit_mansion_cmd.finish(message_add_head(
                f"⛔ 找不到名为【{item_name}】的物品", event
            ))

        service = _build_service(session)
        success, msg = await service.deposit_item(player.id, player.mansion_level, item_id, quantity)
        if success:
            await session.commit()
            await deposit_mansion_cmd.finish(message_add_head(f"✅ {msg}", event))
        else:
            await deposit_mansion_cmd.finish(message_add_head(f"⛔ {msg}", event))


@withdraw_mansion_cmd.handle()
async def handle_withdraw_mansion(event: MessageEvent, args: Message = CommandArg()):
    """从阴宅仓库取出物品"""
    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        await withdraw_mansion_cmd.finish(message_add_head(
            "用法：【取出阴宅 <序号> <数量>】\n"
            "例如：【取出阴宅 1 50】\n"
            "💡 序号见【阴宅仓库】命令的列表",
            event
        ))

    parts = arg_text.split()
    if len(parts) != 2:
        await withdraw_mansion_cmd.finish(message_add_head(
            "⛔ 格式错误，请输入：【取出阴宅 <序号> <数量>】", event
        ))

    try:
        item_index = int(parts[0])
        quantity = int(parts[1])
    except ValueError:
        await withdraw_mansion_cmd.finish(message_add_head("⛔ 序号和数量必须是整数", event))

    if quantity <= 0:
        await withdraw_mansion_cmd.finish(message_add_head("⛔ 数量必须大于0", event))

    async with safe_session() as session:
        player = await require_player(session, event, withdraw_mansion_cmd)

        if player.mansion_level <= 0:
            await withdraw_mansion_cmd.finish(message_add_head(
                "⛔ 你还没有阴宅，无法使用仓库", event
            ))

        from ..sponsor.service import SponsorShopService
        has_remote_warehouse = SponsorShopService.is_privilege_active(player, "premium_warehouse_until")

        from .mansion_service import MansionService
        if not has_remote_warehouse and not MansionService.is_at_mansion(player):
            await withdraw_mansion_cmd.finish(message_add_head(
                f"⛔ 你不在自己的阴宅位置\n"
                f"💡 阴宅坐标：({player.mansion_x}, {player.mansion_y})\n"
                f"💡 请移动到阴宅位置后再访问仓库\n"
                f"💡 或购买【远程仓库特权】随时访问",
                event
            ))

        service = _build_service(session)
        success, msg = await service.withdraw_item(player.id, player.mansion_level, item_index, quantity)
        if success:
            await session.commit()
            await withdraw_mansion_cmd.finish(message_add_head(f"✅ {msg}", event))
        else:
            await withdraw_mansion_cmd.finish(message_add_head(f"⛔ {msg}", event))
