"""宠物伙伴系统 - 命令处理器"""
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message

from ..models.db import AsyncSessionLocal
from ..models.inventory import ItemInstance
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import get_unified_player
from .pet_service import PetService
from .pet_dialogue_service import PetDialogueService
from .config import PetConfigManager, format_bonus
from .personality_customization_service import customize_pet_personality, reset_pet_personality
from ..utils_markdown import cmd, build_markdown

pet_service = PetService()
dialogue_service = PetDialogueService()
pet_config = PetConfigManager()


# ==================== 驯化诡兽 ====================
tame_cmd = on_command("驯化诡兽", aliases={"驯化"}, priority=5, block=True)


@tame_cmd.handle()
async def handle_tame(event: MessageEvent, args: Message = CommandArg()):
    """【驯化诡兽 诡兽名 昵称】- 将背包中的诡兽驯化为宠物"""
    args_text = args.extract_plain_text().strip()
    parts = args_text.split(maxsplit=1)
    if len(parts) < 2:
        content = (
            f"用法: {cmd('驯化诡兽 诡兽名 昵称', '驯化诡兽 ')}\n"
            f"例如: 驯化诡兽 冥犬 小黑"
        )
        await tame_cmd.finish(build_markdown(content))

    beast_name, nickname = parts[0], parts[1]

    # 昵称长度检查
    if len(nickname) > 12:
        await tame_cmd.finish("昵称最长12个字符")

    # 敏感词检测
    from ..player.nickname_validator import validate_nickname
    is_valid, error_msg = await validate_nickname(nickname)
    if not is_valid:
        await tame_cmd.finish(f"⛔ {error_msg}")

    beast = pet_config.get_beast_by_name(beast_name)
    if not beast:
        await tame_cmd.finish(f"未找到诡兽【{beast_name}】")

    beast_item_id = f"guardian_{beast.beast_id}"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await tame_cmd.finish("请先创建角色")

        success, msg = await pet_service.acquire_pet(uow, player.id, beast_item_id, nickname)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('喂食')} | {cmd('摸摸')}"
            await tame_cmd.finish(build_markdown(content))
        await tame_cmd.finish(msg)


# ==================== 宠物信息 ====================
pet_info_cmd = on_command("宠物", aliases={"我的宠物", "诡兽伙伴"}, priority=5, block=True)


@pet_info_cmd.handle()
async def handle_pet_info(event: MessageEvent):
    """【宠物】- 查看当前伙伴状态"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await pet_info_cmd.finish("请先创建角色")

        success, msg = await pet_service.get_pet_info(uow, player.id)
        if success and msg:
            content = f"{msg}\n***\n{cmd('喂食')} | {cmd('摸摸')} | {cmd('宠物列表')} | {cmd('宠物装扮')}"
            await pet_info_cmd.finish(build_markdown(content))
        await pet_info_cmd.finish(msg)


# ==================== 宠物列表 ====================
nest_cmd = on_command("宠物列表", aliases={"诡兽巢穴"}, priority=5, block=True)


@nest_cmd.handle()
async def handle_nest(event: MessageEvent):
    """【宠物列表】- 查看所有宠物"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await nest_cmd.finish("请先创建角色")

        success, msg = await pet_service.get_pet_list(uow, player.id)
        if success and msg:
            content = f"{msg}\n***\n{cmd('切换伙伴 ID', '切换伙伴 ')} | {cmd('宠物')}"
            await nest_cmd.finish(build_markdown(content))
        await nest_cmd.finish(msg)


# ==================== 切换伙伴 ====================
switch_cmd = on_command("切换伙伴", aliases={"切换宠物"}, priority=5, block=True)


@switch_cmd.handle()
async def handle_switch(event: MessageEvent, args: Message = CommandArg()):
    """【切换伙伴 ID或昵称】- 切换当前伙伴"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await switch_cmd.finish("用法: 切换伙伴 <ID或昵称>\n使用【宠物列表】查看")
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await switch_cmd.finish("请先创建角色")

        success, msg = await pet_service.set_active_pet(uow, player.id, args_text)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('喂食')} | {cmd('摸摸')}"
            await switch_cmd.finish(build_markdown(content))
        await switch_cmd.finish(msg)


# ==================== 喂食 ====================
feed_cmd = on_command("喂食", aliases={"喂宠物"}, priority=5, block=True)


@feed_cmd.handle()
async def handle_feed(event: MessageEvent, args: Message = CommandArg()):
    """【喂食 怨念/菜肴名 [数量]】- 统一喂食指令"""
    args_text = args.extract_plain_text().strip()

    if not args_text:
        # 无参数：显示宠物状态 + 用法提示
        async with UnitOfWork(AsyncSessionLocal) as uow:
            player = await get_unified_player(uow.session, event)
            if not player:
                await feed_cmd.finish("请先创建角色")
            pet = await uow.pets.get_active_pet(player.id)
            if not pet:
                await feed_cmd.finish("你还没有伙伴诡兽\n💡 使用【驯化诡兽 诡兽名 昵称】驯化一只")
            content = (
                f"# 🐾 {pet.nickname}\n"
                f"饱食度: **{pet.hunger}**/100 | 心情: **{pet.mood}**/100\n"
                f"***\n"
                f"{cmd('喂食 怨念', '喂食 怨念 ')} 消耗怨念喂养\n"
                f"{cmd('喂食 菜肴名', '喂食 ')} 用菜肴喂养\n"
                f"***\n"
                f"{cmd('宠物')} | {cmd('摸摸')} | {cmd('食谱')}"
            )
            await feed_cmd.finish(build_markdown(content))

    # 解析参数：名称 [数量]
    parts = args_text.rsplit(maxsplit=1)
    name = args_text
    quantity = 1
    if len(parts) == 2 and parts[1].isdigit():
        name = parts[0]
        quantity = int(parts[1])
        if quantity <= 0 or quantity > 99:
            await feed_cmd.finish("数量必须在1-99之间")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await feed_cmd.finish("请先创建角色")

        if name == "怨念":
            success, msg = await pet_service.feed_with_resentment(uow, player.id, quantity)
        else:
            success, msg = await pet_service.feed_with_dish(uow, player.id, name, quantity)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('摸摸')}"
            await feed_cmd.finish(build_markdown(content))
        await feed_cmd.finish(msg)


# ==================== 互动 ====================
interact_cmd = on_command("摸摸", aliases={"摸头", "玩耍", "抱抱"}, priority=5, block=True)

# 中文别名 → action_key
_INTERACT_ACTION_MAP = {
    "摸摸": "pat",
    "摸头": "headpat",
    "玩耍": "play",
    "抱抱": "hug",
}


@interact_cmd.handle()
async def handle_interact(event: MessageEvent):
    """【摸摸】/【摸头】/【玩耍】/【抱抱】- 与宠物互动（4种动作各有偏向）"""
    raw_msg = event.get_plaintext().strip()
    action_key = "pat"
    for alias, key in _INTERACT_ACTION_MAP.items():
        if raw_msg.startswith(alias):
            action_key = key
            break

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await interact_cmd.finish("请先创建角色")

        success, msg = await pet_service.interact(uow, player.id, action_key)
        if success and msg:
            # 推荐另一种互动作为快捷按钮，引导玩家尝试不同动作
            others = [a for a in ("摸摸", "摸头", "玩耍", "抱抱")
                      if _INTERACT_ACTION_MAP[a] != action_key]
            content = (
                f"{msg}\n***\n"
                f"{cmd(others[0])} | {cmd(others[1])} | {cmd(others[2])}\n"
                f"{cmd('宠物')} | {cmd('喂食')} | {cmd('对话 内容', '对话 ')}"
            )
            await interact_cmd.finish(build_markdown(content))
        await interact_cmd.finish(msg)


# ==================== 对话 ====================
chat_cmd = on_command("对话", aliases={"和宠物说", "跟宠物说"}, priority=5, block=True)


@chat_cmd.handle()
async def handle_chat(event: MessageEvent, args: Message = CommandArg()):
    """【对话 内容】- 与宠物AI对话"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await chat_cmd.finish("用法: 对话 <你想说的话>\n例如: 对话 你今天心情怎么样？")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await chat_cmd.finish("请先创建角色")

        success, msg = await dialogue_service.chat(uow, player.id, args_text)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('摸摸')} | {cmd('喂食')}"
            await chat_cmd.finish(build_markdown(content))
        await chat_cmd.finish(msg)


# ==================== 化形 ====================
transform_cmd = on_command("化形", priority=5, block=True)


@transform_cmd.handle()
async def handle_transform(event: MessageEvent, args: Message = CommandArg()):
    """【化形 男/女】- 宠物化形（可选性别）"""
    args_text = args.extract_plain_text().strip()

    # 解析性别参数
    gender = "female"  # 默认女性
    if args_text in ("男", "male", "男性"):
        gender = "male"
    elif args_text in ("女", "female", "女性"):
        gender = "female"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await transform_cmd.finish("请先创建角色")

        success, msg = await pet_service.transform(uow, player.id, gender)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('定制人设 描述', '定制人设 ')}"
            await transform_cmd.finish(build_markdown(content))
        await transform_cmd.finish(msg)


# ==================== 宠物进化 ====================
evolve_cmd = on_command("进化宠物", aliases={"宠物进化", "进化"}, priority=5, block=True)


@evolve_cmd.handle()
async def handle_evolve(event: MessageEvent, args: Message = CommandArg()):
    """【进化宠物】- 提升宠物稀有度"""
    args_text = args.extract_plain_text().strip()
    confirm = args_text == "确认"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await evolve_cmd.finish("请先创建角色")

        success, msg = await pet_service.evolve_pet(uow, player.id, confirm)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('宠物列表')}"
            await evolve_cmd.finish(build_markdown(content))
        await evolve_cmd.finish(msg)


# ==================== 饰品 ====================
equip_acc_cmd = on_command("宠物装扮", aliases={"给宠物穿", "宠物饰品"}, priority=5, block=True)


@equip_acc_cmd.handle()
async def handle_equip_accessory(event: MessageEvent, args: Message = CommandArg()):
    """【宠物装扮 饰品名】- 给宠物装备饰品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        # 显示饰品商店
        rarity_names = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}
        msg = "# 🎀 宠物饰品商店\n***\n"
        for slot in pet_config.accessory_slots:
            slot_names = {"head": "头饰", "neck": "颈饰", "body": "服饰"}
            msg += f"\n**{slot_names.get(slot, slot)}**\n"
            for acc in pet_config.get_accessories_by_slot(slot):
                icon = rarity_names.get(acc.rarity, "⚪")
                bonus_text = format_bonus(acc.bonus)
                currency = "诡烛" if acc.rarity in ("purple", "orange") else "金"
                msg += f"▫️ {icon} {cmd(acc.name, f'买饰品 {acc.name}')} **{acc.price}**{currency} ({bonus_text})\n"
        msg += f"\n***\n{cmd('宠物')} | {cmd('宠物装扮 名称', '宠物装扮 ')}"
        await equip_acc_cmd.finish(build_markdown(msg))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await equip_acc_cmd.finish("请先创建角色")

        success, msg = await pet_service.equip_accessory(uow, player.id, args_text)
        if success and msg:
            content = f"{msg}\n***\n{cmd(f'宠物装扮 {args_text}', f'宠物装扮 ')} | {cmd('宠物')}"
            await equip_acc_cmd.finish(build_markdown(content))
        await equip_acc_cmd.finish(msg)


# ==================== 买饰品 ====================
buy_acc_cmd = on_command("买饰品", aliases={"购买饰品"}, priority=5, block=True)


@buy_acc_cmd.handle()
async def handle_buy_accessory(event: MessageEvent, args: Message = CommandArg()):
    """【买饰品 名称】- 购买宠物饰品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await buy_acc_cmd.finish("用法: 买饰品 <饰品名>\n使用【宠物装扮】查看可购买饰品")

    acc = pet_config.get_accessory_by_name(args_text)
    if not acc:
        await buy_acc_cmd.finish(f"未找到饰品【{args_text}】")

    # 紫色/橙色饰品使用诡烛购买
    use_gui_zhu = acc.rarity in ("purple", "orange")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await buy_acc_cmd.finish("请先创建角色")

        if use_gui_zhu:
            if player.gui_zhu < acc.price:
                await buy_acc_cmd.finish(f"诡烛不足，需要{acc.price}诡烛（当前{player.gui_zhu}）")
            player.gui_zhu -= acc.price
        else:
            if player.gold < acc.price:
                await buy_acc_cmd.finish(f"金币不足，需要{acc.price}金（当前{player.gold:,}）")
            player.gold -= acc.price

        await uow.players.update(player)

        acc_item_id = f"pet_acc_{acc.accessory_id}"
        try:
            await ItemInstance.add_item(uow.session, player.id, acc_item_id, 1)
        except ValueError as e:
            await buy_acc_cmd.finish(f"购买失败: {e}")

        currency = "诡烛" if use_gui_zhu else "金"
        content = (
            f"# ✅ 成功购买【{acc.name}】\n"
            f"***\n"
            f"消耗: **{acc.price}**{currency}\n"
            f"***\n"
            f"{cmd(f'宠物装扮 {acc.name}')} 装备 | {cmd('宠物')}"
        )
        await buy_acc_cmd.finish(build_markdown(content))


# ==================== 派遣守田 ====================
guard_cmd = on_command("派遣守田", aliases={"守田"}, priority=5, block=True)


@guard_cmd.handle()
async def handle_guard(event: MessageEvent):
    """【派遣守田】- 派遣当前伙伴去灵田守田"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await guard_cmd.finish("请先创建角色")

        success, msg = await pet_service.dispatch_to_guard(uow, player.id)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('灵田')}"
            await guard_cmd.finish(build_markdown(content))
        await guard_cmd.finish(msg)


# ==================== 召回守田 ====================
recall_cmd = on_command("召回宠物", aliases={"召回守田"}, priority=5, block=True)


@recall_cmd.handle()
async def handle_recall(event: MessageEvent):
    """【召回宠物】- 召回正在守田的宠物"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await recall_cmd.finish("请先创建角色")

        success, msg = await pet_service.recall_from_guard(uow, player.id)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('灵田')}"
            await recall_cmd.finish(build_markdown(content))
        await recall_cmd.finish(msg)


# ==================== 定制人设 ====================
customize_personality_cmd = on_command("定制人设", priority=5, block=True)


@customize_personality_cmd.handle()
async def handle_customize_personality(event: MessageEvent, args: Message = CommandArg()):
    """【定制人设 描述】- 花费50诡烛定制宠物人设（需已化形）"""
    description = args.extract_plain_text().strip()
    if not description:
        await customize_personality_cmd.finish(
            "用法：定制人设 <你想要的人设描述>\n"
            "例如：定制人设 傲娇毒舌，表面嫌弃主人实则超在意\n"
            "费用：50诡烛/次（可免费重置）"
        )

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await customize_personality_cmd.finish("请先创建角色")

        success, msg = await customize_pet_personality(uow, player.id, description)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('对话 内容', '对话 ')}"
            await customize_personality_cmd.finish(build_markdown(content))
        await customize_personality_cmd.finish(msg)


# ==================== 放生宠物 ====================
release_pet_cmd = on_command("放生", aliases={"放生宠物"}, priority=5, block=True)


@release_pet_cmd.handle()
async def handle_release_pet(event: MessageEvent, args: Message = CommandArg()):
    """【放生 宠物ID或昵称】- 永久放生一只宠物"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await release_pet_cmd.finish("用法：放生 宠物ID或昵称\n⚠️ 放生后宠物将永久消失，无法恢复！")

    # 需要确认：参数末尾带"确认"才执行
    if not args_text.endswith("确认"):
        await release_pet_cmd.finish(
            f"⚠️ 确定要放生【{args_text}】吗？此操作不可撤销！\n"
            f"确认请输入：放生 {args_text} 确认"
        )

    pet_name = args_text.rsplit("确认", 1)[0].strip()
    if not pet_name:
        await release_pet_cmd.finish("请指定要放生的宠物ID或昵称")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await release_pet_cmd.finish("请先创建角色")

        success, msg = await pet_service.release_pet(uow, player.id, pet_name)
        await uow.commit()
        await release_pet_cmd.finish(msg)


# ==================== 重置人设 ====================
reset_personality_cmd = on_command("重置人设", priority=5, block=True)


@reset_personality_cmd.handle()
async def handle_reset_personality(event: MessageEvent):
    """【重置人设】- 免费恢复宠物默认人设"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await reset_personality_cmd.finish("请先创建角色")

        success, msg = await reset_pet_personality(uow, player.id)
        if success and msg:
            content = f"{msg}\n***\n{cmd('宠物')} | {cmd('对话 内容', '对话 ')}"
            await reset_personality_cmd.finish(build_markdown(content))
        await reset_personality_cmd.finish(msg)
