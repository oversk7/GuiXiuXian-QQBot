import asyncio
import re

from nonebot import on_command
from nonebot.params import CommandArg, ArgPlainText
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.typing import T_State
from ..models.db import safe_session, AsyncSessionLocal
from ..models.player import Player
from sqlalchemy import select, func
from ..models.player import Gender
from ..utils import message_add_head, calculate_level_up_exp
from ..utils_markdown import cmd, build_markdown, color_text
from datetime import datetime
from ..models.inventory import ItemInstance, ItemType
from collections import defaultdict
from ..models.guild import Guild
import random
import uuid
from ..models.navigation_task import NavigationTask
from ..world.navigation import _update_nav_position, format_navigation_interruption
from ..world.navigation_events import format_navigation_events
from ..notification_service import notify_player
from ..platform_utils import get_event_server_id, get_unified_player, is_guild_message, require_player
from ..infrastructure.cache import player_identity_cache
from ..config import config
from ..server_config import DEFAULT_SERVER_ID, get_server_name, get_servers_config
from ..server_service import ensure_platform_server_binding, format_server, parse_server_id
from ..infrastructure.uow import UnitOfWork
from ..infrastructure.repositories.account_transfer_log_repository import AccountTransferLogRepository
from ..models.account_ownership import AccountOwnership
from ..queries.player_queries import query_player_profile
from ..models.monthly_card import MonthlyCard, CardType
from .title_image import get_title_image


def _format_player_location(player: Player) -> str:
    """格式化玩家位置信息，区分现实世界和诡域坐标"""
    if player.is_in_dungeon():
        dungeon_x, dungeon_y = player.get_current_coordinates()
        real_x = player.real_world_x or 0
        real_y = player.real_world_y or 0
        return f"{player.get_current_region()} ({dungeon_x},{dungeon_y}) | 现实 ({real_x},{real_y})"
    else:
        real_x, real_y = player.get_current_coordinates()
        return f"{player.get_current_region()} ({real_x},{real_y})"


def _format_player_location_cmd(player: Player) -> str:
    """格式化玩家位置信息，返回可点击蓝字（点击导航到该坐标）"""
    if player.is_in_dungeon():
        dungeon_x, dungeon_y = player.get_current_coordinates()
        real_x = player.real_world_x or 0
        real_y = player.real_world_y or 0
        location_text = f"{player.get_current_region()} ({dungeon_x},{dungeon_y}) | 现实 ({real_x},{real_y})"
        return cmd(location_text, f"导航 {real_x} {real_y}")
    else:
        real_x, real_y = player.get_current_coordinates()
        location_text = f"{player.get_current_region()} ({real_x},{real_y})"
        return cmd(location_text, f"导航 {real_x} {real_y}")


def _format_player_location_public(player: Player) -> str:
    """查看他人面板时的位置脱敏显示：仅显示区域名，隐藏具体坐标以防追杀。"""
    if player.is_in_dungeon():
        return f"{player.get_current_region()}（深入诡域中）"
    return f"{player.get_current_region()}"


def _format_monthly_card_badge(card_types: list[CardType]) -> str:
    """格式化面板里的月卡彩色标识。"""
    if CardType.PREMIUM in card_types:
        return color_text("高级月卡", "#FFB000")
    if CardType.BASIC in card_types:
        return color_text("基础月卡", "#35C7FF")
    return ""
def _format_title_badge(title: str) -> str:
    """称号是身份标识，允许少量使用颜色突出。"""
    return color_text(title, "#FFB84D")
from ..config import config
from ..world.message_board import get_unread_message_status

# 从独立模块导入境界相关函数，避免循环导入
from .realm_utils import realm_by_level, realm_by_level_and_reincarnation, number_to_chinese



profile = on_command("角色",aliases={"面板","状态"}, block=True, priority=5)
register = on_command("注册", block=True, priority=5)
change_gender = on_command("改性别", aliases={"修改性别"}, block=True, priority=5)
newbie_guide = on_command("新手指引", aliases={"指令格式", "指令帮助", "新手教程"}, block=True, priority=5)
attribute_guide = on_command("加点帮助", aliases={"属性帮助", "加点指南", "属性说明"}, block=True, priority=5)


@profile.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数：如果提供了 UID，则查询对应玩家面板
    arg_text = args.extract_plain_text().strip()
    target_uid: int | None = None
    if arg_text:
        try:
            target_uid = int(arg_text)
        except ValueError:
            await profile.finish("⛔ UID 必须为数字")

    quest_extra = ""  # 存储任务/成就检查结果

    # ===== 查看他人面板：纯只读路径（跨区可见） =====
    if target_uid is not None:
        profile_data = await query_player_profile(target_uid)
        if not profile_data:
            await profile.finish("⛔ 未找到该 UID")
        player = profile_data.player
        effective_attrs = profile_data.effective_attrs
        bonus = profile_data.equipment_bonus
        guild_name = profile_data.guild_name
        active_monthly_card_types = profile_data.active_monthly_card_types
    else:
        # ===== 查看自己面板：保留 UoW 路径（含导航更新等写操作） =====
        async with UnitOfWork(AsyncSessionLocal) as uow:
            player = await get_unified_player(uow.session, event)

            if not player:
                if is_guild_message(event):
                    await profile.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
                else:
                    await profile.finish("⛔ 你还没有创建角色")

            # 更新坐标（若在自动导航）
            player_upd = await uow.session.get(Player, player.id)
            task = await uow.session.get(NavigationTask, player.id)
            if player_upd and task:
                reached = await _update_nav_position(player_upd, task, uow.session)
                if reached:
                    # 到达时静默应用导航随机事件
                    from ..world.navigation_events import (
                        generate_navigation_events,
                        apply_navigation_events,
                    )
                    nav_events = generate_navigation_events(
                        player_upd,
                        task.initial_distance or 0,
                        task.target_x,
                        task.target_y,
                    )
                    if nav_events:
                        await apply_navigation_events(uow.session, player_upd, nav_events)
                    await uow.session.delete(task)
                await uow.commit()
                if reached.interrupted or reached.events:
                    nav_message = (
                        format_navigation_interruption(player_upd, reached)
                        if reached.interrupted else format_navigation_events(reached.events)
                    )
                    await notify_player(player_upd.id, nav_message, uow.session, markdown=True)
                player.hp = player_upd.hp
                player.dungeon_kill_streak = player_upd.dungeon_kill_streak
                if not player.is_in_dungeon():
                    player.x = player_upd.x
                    player.y = player_upd.y
                if hasattr(player, "real_world_x"):
                    player.real_world_x = player_upd.real_world_x
                    player.real_world_y = player_upd.real_world_y

            effective_attrs = await player.get_effective_attributes(uow.session)

            bonus = defaultdict(int)
            equip_ids = config.items_config["by_type"]["EQUIPMENT"]
            eq_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(equip_ids)
            )
            equiped_list = (await uow.session.execute(eq_stmt)).scalars().all()
            for eq in equiped_list:
                delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
                for k, v in delta.items():
                    bonus[k] += int(v)

            guild_name = "无所属"
            if player.guild_id:
                g_obj = await uow.session.get(Guild, player.guild_id)
                if g_obj:
                    guild_name = g_obj.name

            active_cards = await MonthlyCard.get_all_active_cards(uow.session, player.id)
            active_monthly_card_types = [card.card_type for card in active_cards]

            # 新手任务和成就检查（需要活跃的 session）
            from ..quest.novice_quest_service import NoviceQuestService
            quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
                uow.session, player, "command", {"command": "角色"}
            )
            if quest_completed and quest_msg:
                quest_extra = f"\n\n{quest_msg}"

            from ..achievement.achievement_service import AchievementService
            achievement_msgs = await AchievementService.check_achievements(uow.session, player)
            if achievement_msgs:
                quest_extra += "\n\n" + "\n".join(achievement_msgs)

    # 7. 格式化属性显示
    def fmt(attr_key: str, effective_value: int):
        inc = bonus.get(attr_key, 0)
        return f"{effective_value} (+{inc})" if inc else str(effective_value)

    atk_str = fmt("attack", effective_attrs["attack"])
    def_str = fmt("defense", effective_attrs["defense"])
    agi_str = fmt("agility", effective_attrs["agility"])
    luk_str = fmt("luck", effective_attrs["luck"])
    hp_max_str = fmt("max_hp", effective_attrs["max_hp"])
    mp_max_str = fmt("max_mp", effective_attrs["max_mp"])

    # 若当前 HP/MP 超出新上限，则修正显示
    cur_hp = min(player.hp, effective_attrs["max_hp"])
    cur_mp = min(player.mp, effective_attrs["max_mp"])

    realm_name = realm_by_level_and_reincarnation(player.level, player.reincarnation_level)
    exp_max = calculate_level_up_exp(player.level, player.server_id)

    # 获取活动称号（如有）
    from ..event.knocker_event import KnockerEventService
    player_title = KnockerEventService.get_player_title(player)
    display_name = player.nickname  # 称号不再拼接到昵称，单独展示
    title_line = f"🏅称号 「{_format_title_badge(player_title)}」" if player_title else ""
    monthly_card_badge = _format_monthly_card_badge(active_monthly_card_types)

    # 构建未读消息通知（蓝字可点击）
    has_world_unread, has_private_unread, has_system_unread, has_guild_unread = await get_unread_message_status(player.id)
    notice_parts = []
    if has_private_unread:
        notice_parts.append(f"📬 {cmd('有新的私信！点击查看', '消息 私信')}")
    if has_system_unread:
        notice_parts.append(f"📢 {cmd('有新的系统公告！点击查看', '消息 系统')}")
    if has_guild_unread:
        notice_parts.append(f"🏯 {cmd('公会频道有新消息！点击查看', '消息 公会')}")
    if has_world_unread:
        notice_parts.append(f"🌐 {cmd('有新的世界消息！点击查看', '消息')}")

    # 组装原生 Markdown 面板（保持原版逐行排版）
    # 佩戴称号有配图时，横幅展示在面板最上方并替代文字称号行；没配图则回退到文字
    lines = []
    if player_title:
        title_banner = get_title_image(player_title)
        if title_banner:
            banner_url, banner_w, banner_h = title_banner
            lines.append(f"![{player_title} #{banner_w}px #{banner_h}px]({banner_url})")
            title_line = ""

    lines += [
        f"# 👤 {display_name}",
        f"UID:{player.uid}　{format_server(player.server_id)}　「{player.sex}」",
        f"Lv.**{player.level}** · {realm_name}",
    ]
    if title_line:
        lines.append(title_line)
    if monthly_card_badge:
        lines.append(f"💳 {monthly_card_badge}")
    lines.extend([
        f"☯ {guild_name}",
        f"Exp {player.exp}/{exp_max}",
        "***",
        f"❤️生命 **{cur_hp}**/{hp_max_str}",
        f"🧠理智 **{cur_mp}**/{mp_max_str}",
        f"⚔️力 **{atk_str}**　🛡️防 **{def_str}**",
        f"👟敏 **{agi_str}**　🍀运 **{luk_str}**",
        f"🔮咒抗 **{player.stamina}**",
        "***",
        f"🪙金币 **{player.gold}**",
        f"💎积分 **{player.gold2}**",
        f"💀怨念 **{player.resentment}**　✨点数 **{player.attribute_points}**",
        f"🕯️诡烛 **{player.gui_zhu}**　🙏香火 **{player.incense}**",
        f"📍{_format_player_location_cmd(player) if target_uid is None else _format_player_location_public(player)}",
        "***",
    ])

    if notice_parts:
        lines.extend(notice_parts)
        lines.append("***")

    # 底部快捷按钮
    if target_uid is None:
        lines.append(
            cmd("装备栏") + " | " + cmd("修炼") + " | " + cmd("突破") + " | " +
            cmd("签到") + " | " + cmd("加点帮助")
        )
        lines.append(
            cmd("社交系统") + " | " + cmd("完整面板") + " | " + cmd("帮助")
        )
    else:
        lines.append(cmd("面板") + " | " + cmd("社交系统") + " | " + cmd("帮助"))

    if quest_extra:
        lines.append("***")
        lines.append(quest_extra.strip())

    await profile.finish(build_markdown("\n".join(lines)))


def _get_qq_username(event: MessageEvent) -> str | None:
    """尝试从 QQ 事件中获取用户昵称（username 字段）"""
    author = getattr(event, "author", None)
    if author is None:
        return None
    username = getattr(author, "username", None)
    if username and isinstance(username, str) and username.strip():
        return username.strip()[:24]  # 昵称最长24字符
    return None


_SERVER_PATTERN = re.compile(r"([0-9一二三四五六七八九十]+)\s*[区服]")
_GENDER_PICK = f"{cmd('⚔️ 男修', '男')}　{cmd('🌸 女修', '女')}"


def _extract_gender(text: str) -> Gender | None:
    """从任意文本中提取性别：兼容 男/男生/男孩/女修 等说法，男女同时出现视为无效。"""
    has_male = "男" in text
    has_female = "女" in text
    if has_male and not has_female:
        return Gender.MALE
    if has_female and not has_male:
        return Gender.FEMALE
    return None


def _extract_server_id(text: str) -> int | None:
    """从任意文本中提取区服：支持 2区/二区/2服，兼容旧格式的纯数字。"""
    match = _SERVER_PATTERN.search(text)
    if match:
        return parse_server_id(match.group(1))
    for token in text.split():
        if token.isdigit() and int(token) in get_servers_config():
            return int(token)
    return None


def _parse_register_args(arg_text: str) -> tuple[int | None, Gender | None]:
    """宽容解析注册参数：顺序、空格、多余文字都不影响，提取不到的项返回 None。"""
    text = arg_text.replace("　", " ").strip()
    return _extract_server_id(text), _extract_gender(text)


def _build_register_guide(headline: str = "🀄️ 欢迎来到诡修仙世界！") -> MessageSegment:
    """构建注册引导卡片：每个开放区服一行，点蓝字即完成注册。"""
    lines = [headline, "──────────────", "👇 点击下面的蓝字，马上开始：", ""]
    open_servers = [
        (sid, meta) for sid, meta in sorted(get_servers_config().items())
        if meta.get("open_registration", True)
    ]
    for sid, meta in open_servers:
        name = meta.get("name", f"{sid}区")
        male = cmd("⚔️ 男修", f"注册 {sid}区 男")
        female = cmd("🌸 女修", f"注册 {sid}区 女")
        lines.append(f"【{name}】 {male}　{female}")
    if len(open_servers) > 1:
        newest_name = open_servers[-1][1].get("name", f"{open_servers[-1][0]}区")
        lines.append("")
        lines.append(f"💡 新道友推荐{newest_name}；想和朋友一起玩，就选朋友在的区")
    return build_markdown("\n".join(lines))


@register.handle()
async def _(event: MessageEvent, state: T_State, args: Message = CommandArg()):
    # 检查是否已有角色（通过ownership系统判断，支持转让后重新注册）
    async with safe_session() as session:
        from ..infrastructure.repositories.account_ownership_repository import AccountOwnershipRepository
        ownership_repo = AccountOwnershipRepository(session)
        user_id = event.get_user_id()

        # 检查是否拥有任何账号（借来的号不算，借用人可注册自己的角色）
        owned_accounts = [
            o for o in await ownership_repo.find_all_by_owner(user_id)
            if not o.is_lent_out()
        ]
        if owned_accounts:
            await register.finish("⛔ 你已经拥有游戏账号了\n💡 使用「我的账号」查看")

        # 兼容老玩家：无ownership记录但Player存在且未被转让
        result = await session.execute(
            select(Player).where(Player.id == user_id)
        )
        existing_player = result.scalars().first()
        if existing_player:
            existing_ownership = await ownership_repo.find_by_player_id(existing_player.id)
            if not existing_ownership or existing_ownership.owner_platform_id == user_id:
                await register.finish("⛔ 你已经创建过角色了")

    arg_text = args.extract_plain_text().strip()
    server_id, gender = _parse_register_args(arg_text)

    # 区服号无效（如 5区）：不报错，直接给开放区服的引导卡
    if server_id is not None and server_id not in get_servers_config():
        await register.finish(_build_register_guide("🀄️ 目前开放的区服在下面～"))

    if gender is not None:
        nickname = _get_qq_username(event)
        if not nickname:
            async with safe_session() as session:
                nickname = await generate_random_nickname(session)
        result = await create_player(event, nickname, gender, server_id or DEFAULT_SERVER_ID)
        await register.finish(result)

    # 没提取到任何有效信息（含无参数）：发引导卡，点蓝字一步完成
    if server_id is None:
        await register.finish(_build_register_guide())

    # 只选了区服：进入性别选择
    state["server_id"] = server_id


@register.got("gender", prompt=build_markdown(
    "🀄️ 欢迎来到诡修仙世界！\n"
    "──────────────\n"
    f"⚧️ 最后一步，点击选择性别：\n{_GENDER_PICK}"
))
async def _(event: MessageEvent, state: T_State, gender_input: str = ArgPlainText("gender")):
    gender = _extract_gender(gender_input.strip())
    if gender is None:
        await register.reject(build_markdown(f"⚧️ 点一下蓝字就可以啦：\n{_GENDER_PICK}"))
    nickname = _get_qq_username(event)
    if not nickname:
        async with safe_session() as session:
            nickname = await generate_random_nickname(session)
    result = await create_player(event, nickname, gender, state.get("server_id", DEFAULT_SERVER_ID))
    await register.finish(result)


def _clean_nickname_input(nickname: str) -> str:
    """清理昵称输入，移除常见的误输入前缀"""
    nickname = nickname.strip()

    # 常见的误输入模式
    patterns_to_remove = [
        "/注册",
        "注册",
        "/修炼系统",
        "/世界系统",
        "/帮助",
        "/面板",
        "/修炼"
    ]

    # 移除这些前缀（不区分大小写）
    for pattern in patterns_to_remove:
        if nickname.lower().startswith(pattern.lower()):
            nickname = nickname[len(pattern):].strip()
            break

    # 移除可能的分隔符
    separators = [" ", "　", "\t", "-", "_", ":", "：", "|", "｜"]
    for sep in separators:
        if nickname.startswith(sep):
            nickname = nickname[1:].strip()
            break

    return nickname


async def generate_random_nickname(session) -> str:
    """生成随机修仙风格昵称，保证与数据库现有玩家不重复"""
    SURNAMES = [
        "李", "王", "张", "刘", "陈", "杨", "黄", "周", "吴", "徐",
        "孙", "马", "朱", "林", "何", "郭", "罗", "梁", "宋", "唐",
        "叶", "慕", "夜", "冥", "玄", "凌", "沈", "裴", "顾", "白",
        "苍", "幽", "魂", "灰", "霜", "寒", "暗", "虚", "骸", "煞",
    ]
    DARK_CHARS = [
        "玄", "冥", "幽", "魂", "骸", "殇", "焰", "渊", "墟", "炁",
        "寂", "祸", "蛊", "苍", "枯", "暗", "影", "刃", "戾", "邪",
        "厄", "咒", "逝", "灭", "荒", "孽", "怨", "狱", "伐", "屠",
        "陨", "腐", "瘴", "噩", "孤", "悸", "蛮", "契", "乱", "煞",
    ]
    NORMAL_CHARS = [
        "伟", "明", "强", "敏", "峰", "云", "风", "月", "雪", "星",
        "阳", "龙", "凤", "飞", "涛", "雨", "洁", "文", "武", "晨",
    ]
    for _ in range(10):
        surname = random.choice(SURNAMES)
        r = random.random()
        if r < 0.15:   # 15% 三字名（姓+暗黑字+暗黑字）
            c1 = random.choice(DARK_CHARS)
            c2 = random.choice([c for c in DARK_CHARS if c != c1])
            nickname = surname + c1 + c2
        elif r < 0.35:  # 20% 普通字
            nickname = surname + random.choice(NORMAL_CHARS)
        else:           # 65% 修仙暗黑字
            nickname = surname + random.choice(DARK_CHARS)
        existing = await session.execute(select(Player).where(Player.nickname == nickname))
        if not existing.scalars().first():
            return nickname
    return nickname + str(random.randint(10, 99))  # 兜底：加后缀


# 按钮 data 必须是纯指令文本，emoji 只能放 label（keyboard() 的 data 会原样作为消息发出）
REGISTER_BUTTONS = [[("👁️ 睁开眼", "睁开眼")]]

# 单进程注册：UID 分配需持锁至提交，并先于数据库会话获取锁，避免读取旧事务快照。
_registration_lock = asyncio.Lock()


async def create_player(event: MessageEvent, nickname: str, gender: Gender, server_id: int = DEFAULT_SERVER_ID) -> Message:
    """创建新玩家角色，返回Markdown卡片消息"""
    async with _registration_lock, safe_session() as session:
        user_id = event.get_user_id()

        ok, bind_msg, bound_server_id = await ensure_platform_server_binding(
            session,
            user_id,
            server_id,
        )
        if not ok:
            return Message(bind_msg)

        # 检查是否拥有任何账号（通过ownership系统判断；借来的号不算）
        from ..infrastructure.repositories.account_ownership_repository import AccountOwnershipRepository
        ownership_repo = AccountOwnershipRepository(session)
        owned_accounts = [
            o for o in await ownership_repo.find_all_by_owner(user_id)
            if not o.is_lent_out()
        ]
        if owned_accounts:
            return Message("⛔ 你已经拥有游戏账号了\n💡 使用「我的账号」查看")

        # 兼容老玩家：没有ownership记录但Player表中有记录，且未被转让
        result = await session.execute(
            select(Player).where(Player.id == user_id)
        )
        existing_player = result.scalars().first()
        if existing_player:
            # 检查该角色是否已被转让给他人
            existing_ownership = await ownership_repo.find_by_player_id(existing_player.id)
            if not existing_ownership or existing_ownership.owner_platform_id == user_id:
                # 未被转让，仍属于自己（老玩家无ownership记录的情况）
                return Message("⛔ 你已经创建过角色了")

        # 获取当前最大UID
        max_uid_result = await session.execute(
            select(func.max(Player.uid))
        )
        max_uid = max_uid_result.scalar() or 99

        # 使用UUID作为Player.id，支持转让后重新注册
        player_id = str(uuid.uuid4()).replace("-", "")[:32]

        # 随机选择一个城市作为出生点
        import random as _rng
        from ..economy.merchant_service import MARKETS
        spawn_market = _rng.choice(MARKETS)

        new_player = Player(
            id=player_id,
            uid=max_uid + 1,
            nickname=nickname,
            sex=gender,
            real_world_x=spawn_market.x,
            real_world_y=spawn_market.y,
            server_id=bound_server_id or server_id,
            created_at=datetime.now()
        )

        session.add(new_player)
        await session.flush()

        # 创建账号所有权记录（支持多账号切换和转让系统）
        # 先取消该QQ名下其他激活账号（借用中的号可能处于激活态），保证激活唯一
        await ownership_repo.deactivate_all_accounts(user_id)
        ownership = AccountOwnership(
            owner_platform_id=event.get_user_id(),
            player_id=new_player.id,
            is_active=True,
            display_name=nickname,
            acquired_type="created",
            acquired_at=datetime.now()
        )
        session.add(ownership)
        await session.commit()

        # 清除身份缓存，防止注册前的"无角色"缓存导致后续指令失败
        player_identity_cache.put(user_id, new_player.id)

        # 💡 改名卡由首次签到时赠送，见 entertainment/sign.py

        # 初始化新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        await NoviceQuestService.init_novice_quests(session, new_player)

        card_type = random.choice(('🎲','🀄️','🀃','🀅','🀆','🀀','🀁','🀂','🀒','🀚','🀣'))

        content = (
            f"# ⚰️ 棺盖移位，你醒了\n"
            f"黑暗替你呼吸——欢迎回到人间。\n"
            f"***\n"
            f"{card_type} **{nickname}**　UID:**{new_player.uid}**　{new_player.sex.value}\n"
            f"📍 你在 **{spawn_market.name}**\n"
            f"🪧 区服 **{get_server_name(new_player.server_id)}**\n"
            f"***\n"
            f"你数不清自己躺了多久。棺板内侧有抓痕——是从里面留下的。\n"
            f"远处传来拖拽声。湿的东西，正在靠近。\n"
            f"***\n"
            f"👇 点击按钮，或发送 {cmd('睁开眼')}"
        )

        return build_markdown(content, buttons=REGISTER_BUTTONS)


@change_gender.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """修改角色性别"""
    gender_str = args.extract_plain_text().strip()

    if not gender_str:
        await change_gender.finish("⛔ 请指定性别，格式：改性别 男/女")

    try:
        gender = Gender(gender_str)
    except ValueError:
        await change_gender.finish(f"⛔ 无效的性别，可选：{Gender.MALE.value}/{Gender.FEMALE.value}")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await require_player(session, event, change_gender)

        if player.sex == gender:
            await change_gender.finish(f"⛔ 你的性别已经是{gender.value}了")

        old_gender = player.sex
        player.sex = gender
        session.add(player)
        await session.commit()

        # 获取活动称号（如有）
        from ..event.knocker_event import KnockerEventService
        player_title = KnockerEventService.get_player_title(player)
        display_name = f"{player.nickname}·{player_title}" if player_title else player.nickname

        await change_gender.finish(message_add_head(
            f"✨ 性别修改成功！\n"
            f"🔄 {old_gender} → {gender.value}\n"
            f"👤 {display_name}[UID:{player.uid}]",
            event
        ))


@newbie_guide.handle()
async def _(event: MessageEvent):
    """新手指引 - 教会新手如何正确使用指令格式"""

    # 检查是否已有角色
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await require_player(session, event, newbie_guide)

    GROUP_LINK = (
        "https://qun.qq.com/universal-share/share?"
        "ac=1&authKey=fBfQXvfkDK92gotOtEFTjwLD4R3qKy%2BV79jJCyMLKqTWKmazq23NO3miCxBir7aL"
        "&busi_data=eyJncm91cENvZGUiOiI5NjI0OTQ2NzkiLCJ0b2tlbiI6IjdSUURicDczVGpFclVUUDRF"
        "RFh4R1lYaXdzMmtyTEgvU040UlJyUkhjVUxXUGZyb0NHR3Iwa1VIZnAranpqQTQiLCJ1aW4iOiIy"
        "Njk4NTk1MTE1In0%3D"
        "&data=lTl1gOtgo5gvdmyaAmJGiAZBK6oI7nGH1jr_AuHfsltlCDUTpIdA7qvXh5k5Yj0uidZilU_o"
        "g4nQXsr8cflTzA&svctype=4&tempid=h5_group_info"
    )
    content = (
        "# 📜 新手指引\n"
        "***\n"
        "**🗺️ 先学会走路（最重要！）**\n"
        f"{cmd('观察')} 看看你在哪，周围有什么\n"
        f"{cmd('附近地点')} 附近100格内可去的地方\n"
        f"{cmd('导航 地点名', '导航 ')} 自动导航到目标地点\n"
        f"{cmd('地图')} 查看所有重要地点坐标\n"
        "💡 这个世界靠坐标移动，走到地方才能做事！\n"
        "***\n"
        "**🔰 到地方了，开始变强**\n"
        f"{cmd('修炼')} 获取经验(5分钟冷却)\n"
        f"{cmd('突破')} 经验够了就升级(30级前100%成功)\n"
        f"{cmd('加点 力 5', '加点 ')} 突破后分配属性点\n"
        f"{cmd('签到')} 每日签到领奖励\n"
        f"{cmd('打工')} 赚金币(到工作地点后使用)\n"
        f"💡 加点不会？点 {cmd('加点帮助')} 看推荐方案\n"
        "***\n"
        "**⚔️ 站稳脚跟（1-30级）**\n"
        f"{cmd('进入 1层诡域', '进入 1层诡域')} 进入诡域刷怪获取材料\n"
        f"  └ 诡域内用 {cmd('上')} {cmd('下')} {cmd('左')} {cmd('右')} 移动，{cmd('探索')} 战斗\n"
        f"  └ {cmd('返回')} 回到现实世界\n"
        f"{cmd('每日委托')} 接取缉邪任务赚经验金币\n"
        f"{cmd('锻造列表')} 查看可锻造的装备\n"
        f"{cmd('闭关')} 睡前闭关，离线挂机修炼\n"
        "***\n"
        "**📈 进阶发展（30级+）**\n"
        f"{cmd('市集')} 跑商低买高卖赚差价\n"
        f"{cmd('公会列表')} 加入公会享受建筑加成\n"
        f"{cmd('购买阴宅')} 拥有阴宅大幅提升修炼效率\n"
        f"{cmd('钓鱼')} 钓鱼获取食材\n"
        f"{cmd('投资行情')} 气运投资(高风险高回报)\n"
        "***\n"
        "**💎 核心循环**\n"
        f"探索 = {cmd('观察')} → {cmd('导航 地点名', '导航 ')} → 到达后做事\n"
        f"变强 = {cmd('修炼')}/{cmd('突破')} + {cmd('锻造列表', '锻造列表')} + {cmd('丹方')}\n"
        f"刷材料 = {cmd('进入 1层诡域', '进入 ')} + {cmd('每日委托')}\n"
        f"赚钱 = {cmd('打工')}(稳) + {cmd('跑商推荐', '跑商推荐')}(中) + {cmd('投资行情', '投资行情')}(险)\n"
        "***\n"
        f"> {cmd('帮助')} 查看所有系统"
    )

    await newbie_guide.finish(build_markdown(content))


@attribute_guide.handle()
async def _(event: MessageEvent):
    """加点帮助 - 详细说明各个属性的作用和推荐加点方案"""

    # 检查是否已有角色
    async with safe_session() as session:
        player = await require_player(session, event, attribute_guide)

    content = (
        "# 🔮 加点帮助\n"
        "***\n"
        "**🩸 体力 (体)** ★★★★☆\n"
        "每点+3生命值上限 | 适合：新手、坦克流\n"
        "**🧠 理智 (智)** ★★★★★\n"
        "每点+1理智值上限 | 适合：探索流、副本流\n"
        "理智用于诡域探索移动，讨伐世界boss\n"
        "**⚔️ 力量 (力)** ★★★★☆\n"
        "每点+1攻击力 | 适合：输出流、PVP流\n"
        "**🛡️ 防御 (防)** ★★★☆☆\n"
        "每点+1防御力 | 适合：坦克流、生存流\n"
        "**👟 敏捷 (敏)** ★★★★☆\n"
        "每点+1敏捷度 | 适合：跑商流、探索流\n"
        "影响导航速度和先后手，与闪避无关\n"
        "**🍀 运气 (运)** ★★★☆☆\n"
        "每点+1运气值 | 适合：升阶流\n"
        "影响材料翻倍率、签到翻倍率、升阶成功率(最多+20%)\n"
        "***\n"
        f"{cmd('加点 智 5', '加点 ')} 给理智加5点\n"
        f"{cmd('面板')} 查看当前属性 | {cmd('战力')} 详细战斗属性\n"
        "***\n"
        f"> {cmd('新手指引')} 学习指令 | {cmd('帮助')} 返回"
    )

    await attribute_guide.finish(build_markdown(content))


# 完整面板命令
complete_profile = on_command("完整面板", block=True, priority=5)


@complete_profile.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """查看完整面板（包含战力信息和注册时间）"""
    # 解析参数：如果提供了 UID，则查询对应玩家面板
    arg_text = args.extract_plain_text().strip()
    target_uid: int | None = None
    if arg_text:
        try:
            target_uid = int(arg_text)
        except ValueError:
            await complete_profile.finish("⛔ UID 必须为数字")

    # 使用UnitOfWork统一所有查询，确保事务原子性
    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 1. 获取玩家
        if target_uid is not None:
            server_id = await get_event_server_id(uow.session, event)
            stmt = select(Player).where(Player.uid == target_uid, Player.server_id == server_id)
            result = await uow.session.execute(stmt)
            player = result.scalars().first()
            if not player:
                await complete_profile.finish("⛔ 未找到该 UID")
        else:
            # 使用跨平台工具获取玩家数据
            player = await get_unified_player(uow.session, event)

        if not player:
            if is_guild_message(event):
                await complete_profile.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await complete_profile.finish("⛔ 你还没有创建角色")

        # 2. 更新坐标（若在自动导航）
        player_upd = await uow.session.get(Player, player.id)
        task = await uow.session.get(NavigationTask, player.id)
        if player_upd and task:
            reached = await _update_nav_position(player_upd, task, uow.session)
            if reached:
                # 到达时静默应用导航随机事件
                from ..world.navigation_events import (
                    generate_navigation_events,
                    apply_navigation_events,
                )
                nav_events = generate_navigation_events(
                    player_upd,
                    task.initial_distance or 0,
                    task.target_x,
                    task.target_y,
                )
                if nav_events:
                    await apply_navigation_events(uow.session, player_upd, nav_events)
                await uow.session.delete(task)
            await uow.commit()  # 立即提交导航更新
            if reached.interrupted or reached.events:
                nav_message = (
                    format_navigation_interruption(player_upd, reached)
                    if reached.interrupted else format_navigation_events(reached.events)
                )
                await notify_player(player_upd.id, nav_message, uow.session, markdown=True)
            player.hp = player_upd.hp
            player.dungeon_kill_streak = player_upd.dungeon_kill_streak
            # 同步内存对象用于展示
            if not player.is_in_dungeon():
                player.x = player_upd.x
                player.y = player_upd.y
            # 始终同步现实世界坐标
            if hasattr(player, "real_world_x"):
                player.real_world_x = player_upd.real_world_x
                player.real_world_y = player_upd.real_world_y

        # 3. 获取有效属性（含装备/丹药/临时buff/宠物加成）
        effective_attrs = await player.get_effective_attributes(uow.session)

        # 4. 统计装备加成用于显示
        bonus = defaultdict(int)
        equip_ids = config.items_config["by_type"]["EQUIPMENT"]
        eq_stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(equip_ids)
        )
        equiped_list = (await uow.session.execute(eq_stmt)).scalars().all()
        for eq in equiped_list:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                bonus[k] += int(v)

        # 5. 获取公会信息
        guild_name = "无所属"
        if player.guild_id:
            g_obj = await uow.session.get(Guild, player.guild_id)
            if g_obj:
                guild_name = g_obj.name

        active_cards = await MonthlyCard.get_all_active_cards(uow.session, player.id)
        active_monthly_card_types = [card.card_type for card in active_cards]

        # 6. 获取战斗属性显示
        from ..battle.integration_helper import BattleIntegrationHelper
        battle_attr_display = await BattleIntegrationHelper.get_battle_attribute_display_async(player, uow.session)

        # 7. 检查是否有临时buff
        from ..models.temporary_buff import TemporaryBuff
        active_buffs = await TemporaryBuff.get_active_buffs(uow.session, player.id)

    # 8. 格式化属性显示
    def fmt(attr_key: str, effective_value: int):
        inc = bonus.get(attr_key, 0)
        return f"{effective_value} (+{inc})" if inc else str(effective_value)

    atk_str = fmt("attack", effective_attrs["attack"])
    def_str = fmt("defense", effective_attrs["defense"])
    agi_str = fmt("agility", effective_attrs["agility"])
    luk_str = fmt("luck", effective_attrs["luck"])
    hp_max_str = fmt("max_hp", effective_attrs["max_hp"])
    mp_max_str = fmt("max_mp", effective_attrs["max_mp"])

    # 若当前 HP/MP 超出新上限，则修正显示
    cur_hp = min(player.hp, effective_attrs["max_hp"])
    cur_mp = min(player.mp, effective_attrs["max_mp"])

    realm_name = realm_by_level_and_reincarnation(player.level, player.reincarnation_level)
    exp_max = calculate_level_up_exp(player.level)

    # 获取活动称号（如有）
    from ..event.knocker_event import KnockerEventService
    player_title = KnockerEventService.get_player_title(player)
    display_name_full = player.nickname  # 称号不再拼接到昵称，单独展示
    title_line_full = f"🏅称号 「{_format_title_badge(player_title)}」" if player_title else ""
    monthly_card_badge_full = _format_monthly_card_badge(active_monthly_card_types)

    # 9. 格式化注册时间
    created_at = player.created_at
    if created_at:
        created_str = created_at.strftime("%Y-%m-%d %H:%M")
        # 计算注册天数
        days_since_created = (datetime.now() - created_at).days
        created_info = f"{created_str} ({days_since_created}天)"
    else:
        created_info = "未知"

    # 10. 检查各频道未读状态
    has_world_unread, has_private_unread, has_system_unread, has_guild_unread = await get_unread_message_status(player.id)
    notice_parts_full = []
    if has_private_unread:
        notice_parts_full.append(f"📬 {cmd('查看私信', '消息 私信')}")
    if has_system_unread:
        notice_parts_full.append(f"📢 {cmd('查看公告', '消息 系统')}")
    if has_guild_unread:
        notice_parts_full.append(f"🏯 {cmd('查看公会消息', '消息 公会')}")
    if has_world_unread:
        notice_parts_full.append(f"🌐 {cmd('有新的世界消息！点击查看', '消息')}")

    # 11. 组装完整面板（原生 Markdown，保持原版逐行排版）
    lines = [
        f"# 👤 {display_name_full}",
        f"UID:{player.uid}　「{player.sex}」　🪧{get_server_name(player.server_id)}",
        f"Lv.**{player.level}** · {realm_name}",
    ]
    if title_line_full:
        lines.append(title_line_full)
    if monthly_card_badge_full:
        lines.append(f"💳 {monthly_card_badge_full}")
    lines.extend([
        f"☯ {guild_name}",
        f"Exp {player.exp}/{exp_max}",
        f"📅注册 {created_info}",
        "***",
        f"❤️生命 **{cur_hp}**/{hp_max_str}",
        f"🧠理智 **{cur_mp}**/{mp_max_str}",
        f"⚔️力 **{atk_str}**　🛡️防 **{def_str}**",
        f"👟敏 **{agi_str}**　🍀运 **{luk_str}**",
        f"🔮咒抗 **{player.stamina}**",
        "***",
        "**⚔️ 战斗属性**",
    ])

    # 12. 添加战斗属性（跳过标题行）
    battle_lines = battle_attr_display.strip().split('\n')
    for line in battle_lines[1:]:
        if line.strip():
            lines.append(line.strip())

    lines.extend([
        "***",
        f"🪙金币 **{player.gold}**",
        f"💎积分 **{player.gold2}**",
        f"💀怨念 **{player.resentment}**　✨点数 **{player.attribute_points}**",
        f"🕯️诡烛 **{player.gui_zhu}**　🙏香火 **{player.incense}**",
        f"📍{_format_player_location_cmd(player) if target_uid is None else _format_player_location_public(player)}",
    ])

    # 13. Buff状态
    if active_buffs:
        lines.append(f"✨增益 **{len(active_buffs)}**个　{cmd('增益状态')}")

    lines.append("***")
    if notice_parts_full:
        lines.extend(notice_parts_full)
        lines.append("***")

    lines.append(
        cmd("装备栏") + " | " + cmd("修炼") + " | " + cmd("突破") + " | " +
        cmd("签到") + " | " + cmd("加点帮助")
    )
    lines.append(
        cmd("社交系统") + " | " + cmd("面板") + " | " + cmd("帮助")
    )

    # 14. 检查新手任务
    if target_uid is None:
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            uow.session, player, "command", {"command": "完整面板"}
        )
        if quest_completed and quest_msg:
            lines.append("***")
            lines.append(quest_msg.strip())

    await complete_profile.finish(build_markdown("\n".join(lines)))
