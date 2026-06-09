"""
灵田系统 - 指令处理器

包含所有灵田相关指令:
- 开辟灵田、查看灵田、升级灵田
- 种植、一键种植
- 灌溉、一键灌溉
- 收菜
- 偷菜(偷菜)
- 诡兽守田管理
- 灵种商店
- 灵田记录
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import require_player
from ..utils_markdown import cmd, build_markdown
from .spirit_field_service import SpiritFieldService
from .steal_service import StealService
from .config import (
    CropManager, GuardianBeastManager,
    FIELD_LEVEL_PLOTS, FIELD_UPGRADE_COST, FIELD_LEVEL_UNLOCK_RARITY,
)

# ==================== 服务实例 ====================

field_service = SpiritFieldService()
steal_service = StealService()
crop_manager = CropManager()
beast_manager = GuardianBeastManager()

# ==================== 开辟灵田 ====================

create_field_cmd = on_command("开辟灵田", aliases={"开田"}, priority=13, block=True)


@create_field_cmd.handle()
async def handle_create_field(event: MessageEvent):
    """【开辟灵田】- 创建灵田"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, create_field_cmd)

        success, msg = await field_service.create_field(uow, player.id)
        await create_field_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('种子商店')}"))


# ==================== 查看灵田 ====================

view_field_cmd = on_command("灵田", aliases={"我的灵田"}, priority=13, block=True)


@view_field_cmd.handle()
async def handle_view_field(event: MessageEvent):
    """【灵田】- 查看灵田状态"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, view_field_cmd)

        success, msg = await field_service.get_field_status(uow, player.id)
        await view_field_cmd.finish(build_markdown(msg + f"\n***\n{cmd('收菜')} | {cmd('一键浇水')} | {cmd('种子商店')} | {cmd('偷菜')}"))


# ==================== 升级灵田 ====================

upgrade_field_cmd = on_command("灵田升级", aliases={"升级灵田"}, priority=13, block=True)


@upgrade_field_cmd.handle()
async def handle_upgrade_field(event: MessageEvent):
    """【灵田升级】- 升级灵田等级"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, upgrade_field_cmd)

        success, msg = await field_service.upgrade_field(uow, player.id)
        await upgrade_field_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('种子商店')}"))


# ==================== 种植 ====================

plant_cmd = on_command("种植", aliases={"种"}, priority=13, block=True)


@plant_cmd.handle()
async def handle_plant(event: MessageEvent, args: Message = CommandArg()):
    """【种植 作物名 [地块号]】- 指定地块种植"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await plant_cmd.finish("用法: 种植 <作物名> [地块号]\n例如: 种植 碧冥芹 1")

    parts = args_text.split()
    crop_name = parts[0]
    plot_index = None

    if len(parts) > 1:
        try:
            plot_index = int(parts[1])
            if plot_index <= 0:
                await plant_cmd.finish("地块号必须大于0")
        except ValueError:
            await plant_cmd.finish("地块号必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, plant_cmd)

        success, msg = await field_service.plant(uow, player.id, crop_name, plot_index)
        await plant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('一键浇水')} | {cmd('收菜')}"))


# ==================== 一键种植 ====================

plant_all_cmd = on_command("一键种植", aliases={"全种"}, priority=13, block=True)


@plant_all_cmd.handle()
async def handle_plant_all(event: MessageEvent, args: Message = CommandArg()):
    """【一键种植 作物名】- 全部空地块种植"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await plant_all_cmd.finish("用法: 一键种植 <作物名>\n例如: 一键种植 碧冥芹")

    crop_name = args_text.split()[0]

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, plant_all_cmd)

        success, msg = await field_service.plant_all(uow, player.id, crop_name)
        await plant_all_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('一键浇水')} | {cmd('收菜')}"))


# ==================== 灌溉 ====================

water_cmd = on_command("浇水", priority=13, block=True)


@water_cmd.handle()
async def handle_water(event: MessageEvent, args: Message = CommandArg()):
    """【灌溉 [地块号]】- 灌溉指定地块"""
    args_text = args.extract_plain_text().strip()
    plot_index = None

    if args_text:
        try:
            plot_index = int(args_text)
            if plot_index <= 0:
                await water_cmd.finish("地块号必须大于0")
        except ValueError:
            await water_cmd.finish("地块号必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, water_cmd)

        success, msg = await field_service.water_plot(uow, player.id, plot_index)
        await water_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('收菜')}"))


# ==================== 一键灌溉 ====================

water_all_cmd = on_command("一键浇水", aliases={"全部浇水"}, priority=13, block=True)


@water_all_cmd.handle()
async def handle_water_all(event: MessageEvent):
    """【一键灌溉】- 灌溉所有已种地块"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, water_all_cmd)

        success, msg = await field_service.water_all(uow, player.id)
        await water_all_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('收菜')}"))


# ==================== 收菜 ====================

harvest_cmd = on_command("收菜", aliases={"收获"}, priority=13, block=True)


@harvest_cmd.handle()
async def handle_harvest(event: MessageEvent):
    """【收菜】- 收获所有成熟作物"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, harvest_cmd)

        success, msg = await field_service.harvest(uow, player.id)
        await harvest_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('一键种植 作物', '一键种植 ')} | {cmd('种子商店')}"))


# ==================== 偷菜(偷菜) ====================

steal_cmd = on_command("偷菜", priority=13, block=True)


@steal_cmd.handle()
async def handle_steal(event: MessageEvent, args: Message = CommandArg()):
    """【偷菜】查看目标 / 【偷菜 UID】执行偷菜"""
    args_text = args.extract_plain_text().strip()

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, steal_cmd)

        if not args_text:
            # 查看可偷目标
            success, msg = await steal_service.get_steal_targets(uow, player.id)
            await steal_cmd.finish(build_markdown(msg + f"\n***\n{cmd('偷菜 UID', '偷菜 ')} | {cmd('灵田')} | {cmd('偷菜记录')}"))
        else:
            # 执行偷菜
            try:
                victim_uid = int(args_text)
            except ValueError:
                await steal_cmd.finish("用法: 偷菜 <UID>\n使用【偷菜】查看可偷目标")

            success, msg = await steal_service.steal_from(uow, player.id, victim_uid)
            await steal_cmd.finish(build_markdown(msg + f"\n***\n{cmd('偷菜 UID', '偷菜 ')} | {cmd('灵田')} | {cmd('偷菜记录')}"))


# ==================== 旧诡兽命令（引导到宠物伙伴系统） ====================

place_guardian_cmd = on_command("放置诡兽", priority=13, block=True)


@place_guardian_cmd.handle()
async def handle_place_guardian_redirect(event: MessageEvent):
    msg = (
        "# 诡兽系统已升级\n***\n"
        "诡兽系统已升级为宠物伙伴系统!\n"
        f"{cmd('驯化诡兽 名称 昵称', '驯化诡兽 ')} 驯化\n"
        f"{cmd('派遣守田')} 守田\n"
        f"{cmd('宠物')} 查看"
    )
    await place_guardian_cmd.finish(build_markdown(msg))


remove_guardian_cmd = on_command("收回诡兽", aliases={"撤回诡兽"}, priority=13, block=True)


@remove_guardian_cmd.handle()
async def handle_remove_guardian_redirect(event: MessageEvent):
    msg = (
        "# 诡兽系统已升级\n***\n"
        f"使用 {cmd('召回宠物')} 召回守田中的宠物\n"
        f"{cmd('宠物')} | {cmd('灵田')}"
    )
    await remove_guardian_cmd.finish(build_markdown(msg))


feed_guardian_cmd = on_command("喂养诡兽", aliases={"喂诡兽"}, priority=13, block=True)


@feed_guardian_cmd.handle()
async def handle_feed_guardian_redirect(event: MessageEvent):
    msg = (
        "# 诡兽系统已升级\n***\n"
        f"使用 {cmd('喂食')} 喂养你的宠物伙伴\n"
        f"{cmd('宠物')} | {cmd('灵田')}"
    )
    await feed_guardian_cmd.finish(build_markdown(msg))


# ==================== 灵种商店 ====================

seed_shop_cmd = on_command("种子商店", aliases={"灵种商店"}, priority=13, block=True)


@seed_shop_cmd.handle()
async def handle_seed_shop(event: MessageEvent):
    """【灵种商店】- 查看可购买的种子"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, seed_shop_cmd)

        field = await uow.spirit_fields.get_by_player_id(player.id)
        if not field:
            await seed_shop_cmd.finish("你还没有灵田，使用【开辟灵田】创建")

        # 获取已解锁的稀有度
        allowed = FIELD_LEVEL_UNLOCK_RARITY.get(field.level, ["white"])

        all_crops = crop_manager.get_all_crops()
        rarity_names = {"white": "白色", "green": "绿色", "blue": "蓝色", "purple": "紫色", "orange": "橙色"}
        rarity_icons = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}

        msg = f"# 🌱 灵种商店 (灵田{field.level}级)\n***\n"

        # 按稀有度分组显示
        for rarity in ["white", "green", "blue", "purple", "orange"]:
            crops = [c for c in all_crops if c.rarity == rarity]
            if not crops:
                continue

            is_locked = rarity not in allowed
            icon = rarity_icons.get(rarity, "⚪")
            label = rarity_names.get(rarity, rarity)

            if is_locked:
                msg += f"\n**{icon} {label}灵种** (未解锁)\n"
            else:
                msg += f"\n**{icon} {label}灵种**\n"
                for crop in crops:
                    type_tag = "蔬" if crop.type == "VEGETABLE" else "药"
                    msg += f"▫️ {cmd(crop.name, f'买种子 {crop.name} ')} [{type_tag}] **{crop.seed_price}**金 ({crop.grow_hours}h)\n"

        # 诡兽商店
        shop_beasts = beast_manager.get_shop_beasts()
        if shop_beasts:
            msg += f"\n**🐾 守田诡兽**\n"
            for beast in shop_beasts:
                icon = rarity_icons.get(beast.rarity, "⚪")
                msg += f"▫️ {icon} {cmd(beast.name, f'买诡兽 {beast.name} ')} **{beast.shop_price:,}**金 (拦截{beast.intercept_rate}%)\n"

        msg += f"\n***\n💰 金币: **{player.gold:,}**\n"
        msg += f"{cmd('灵田')} | {cmd('收菜')} | {cmd('一键种植 作物', '一键种植 ')}"

        await seed_shop_cmd.finish(build_markdown(msg))


# ==================== 购买灵种 ====================

buy_seed_cmd = on_command("买种子", priority=13, block=True)


@buy_seed_cmd.handle()
async def handle_buy_seed(event: MessageEvent, args: Message = CommandArg()):
    """【买种子 名称 数量】- 购买种子"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await buy_seed_cmd.finish("用法: 买种子 <名称> [数量]\n例如: 买种子 碧冥芹 5")

    parts = args_text.split()
    item_name = parts[0]
    quantity = 1

    if len(parts) > 1:
        try:
            quantity = int(parts[1])
            if quantity <= 0 or quantity > 99:
                await buy_seed_cmd.finish("数量必须在 1-99 之间")
        except ValueError:
            await buy_seed_cmd.finish("数量必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, buy_seed_cmd)

        field = await uow.spirit_fields.get_by_player_id(player.id)
        if not field:
            await buy_seed_cmd.finish("你还没有灵田")

        # 购买种子
        crop = crop_manager.get_crop_by_name(item_name)
        if not crop:
            await buy_seed_cmd.finish(f"未找到【{item_name}】\n使用【种子商店】查看可购买列表")

        allowed = FIELD_LEVEL_UNLOCK_RARITY.get(field.level, ["white"])
        if crop.rarity not in allowed:
            await buy_seed_cmd.finish(f"灵田等级不足，无法购买{crop.rarity}品质种子")

        total_cost = crop.seed_price * quantity
        if player.gold < total_cost:
            await buy_seed_cmd.finish(f"金币不足，需要{total_cost:,}金币")

        player.gold -= total_cost
        await uow.players.update(player)

        from ..models.inventory import ItemInstance
        try:
            await ItemInstance.add_item(uow.session, player.id, crop.seed_id, quantity)
        except ValueError as e:
            await buy_seed_cmd.finish(f"⚠️ {e}")

        await buy_seed_cmd.finish(build_markdown(
            f"购买成功!\n"
            f"{crop.name}种子 x{quantity}\n"
            f"消耗: {total_cost:,}金币"
            f"\n***\n{cmd('灵田')} | {cmd('种子商店')}"
        ))


# ==================== 买诡兽 ====================

buy_beast_cmd = on_command("买诡兽", priority=13, block=True)


@buy_beast_cmd.handle()
async def handle_buy_beast(event: MessageEvent, args: Message = CommandArg()):
    """【买诡兽 名称 [数量]】- 购买守田诡兽"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await buy_beast_cmd.finish("用法: 买诡兽 <名称> [数量]\n例如: 买诡兽 冥犬")

    parts = args_text.split()
    beast_name = parts[0]
    quantity = 1

    if len(parts) > 1:
        try:
            quantity = int(parts[1])
            if quantity <= 0 or quantity > 10:
                await buy_beast_cmd.finish("数量必须在 1-10 之间")
        except ValueError:
            await buy_beast_cmd.finish("数量必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, buy_beast_cmd)

        field = await uow.spirit_fields.get_by_player_id(player.id)
        if not field:
            await buy_beast_cmd.finish("你还没有灵田")

        beast = beast_manager.get_beast_by_name(beast_name)
        if not beast:
            await buy_beast_cmd.finish(f"未找到诡兽【{beast_name}】\n使用【种子商店】查看可购买列表")

        if beast.shop_price <= 0:
            await buy_beast_cmd.finish(f"【{beast.name}】无法在商店购买，需要诡域掉落")

        total_cost = beast.shop_price * quantity
        if player.gold < total_cost:
            await buy_beast_cmd.finish(f"金币不足，需要{total_cost:,}金币")

        player.gold -= total_cost
        await uow.players.update(player)

        from ..models.inventory import ItemInstance
        try:
            await ItemInstance.add_item(uow.session, player.id, beast.item_id, quantity)
        except ValueError as e:
            await buy_beast_cmd.finish(f"⚠️ {e}")

        await buy_beast_cmd.finish(build_markdown(
            f"购买成功!\n"
            f"{beast.name} x{quantity}\n"
            f"消耗: {total_cost:,}金币"
            f"\n***\n{cmd('灵田')} | {cmd('种子商店')}"
        ))


# ==================== 拜访灵田 ====================

visit_other_field_cmd = on_command("拜访灵田", aliases={"查看灵田"}, priority=13, block=True)


@visit_other_field_cmd.handle()
async def handle_visit_other_field(event: MessageEvent, args: Message = CommandArg()):
    """【拜访灵田 UID】- 查看他人灵田状态，包括作物剩余成熟时间"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await visit_other_field_cmd.finish("用法: 拜访灵田 <UID>\n例如: 拜访灵田 12345")

    try:
        target_uid = int(args_text.strip())
    except ValueError:
        await visit_other_field_cmd.finish("UID必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, visit_other_field_cmd)

        success, msg = await field_service.visit_field(uow, player.id, target_uid)
        await visit_other_field_cmd.finish(build_markdown(msg + f"\n***\n{cmd('偷菜 UID', '偷菜 ')} | {cmd('灵田')}"))


# ==================== 灵田记录 ====================

field_log_cmd = on_command("偷菜记录", priority=13, block=True)


@field_log_cmd.handle()
async def handle_field_log(event: MessageEvent, args: Message = CommandArg()):
    """【灵田记录】- 查看偷菜日志，支持分页"""
    args_text = args.extract_plain_text().strip()
    page = 1
    if args_text:
        try:
            page = int(args_text)
            if page < 1:
                page = 1
        except ValueError:
            await field_log_cmd.finish("页码请输入数字，例如：偷菜记录 2")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, field_log_cmd)

        success, msg = await steal_service.get_steal_logs(uow, player.id, page)
        await field_log_cmd.finish(build_markdown(msg + f"\n***\n{cmd('灵田')} | {cmd('偷菜')}"))
