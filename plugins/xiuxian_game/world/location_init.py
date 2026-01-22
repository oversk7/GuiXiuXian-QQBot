"""
地点和NPC初始化系统

初始化游戏中的默认地点和NPC，迁移现有系统数据
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.adapters.qq import Message
from nonebot.params import CommandArg

from nonebot.permission import SUPERUSER

from sqlalchemy.exc import SQLAlchemyError

from ..models.db import safe_session
from ..models.location import Location
from ..models.npc import NPC, NPCType
from ..utils import message_add_head
from .location_service import LocationService
from .npc_service import NPCService


# ==================== 初始化命令 ====================
init_locations_cmd = on_command("初始化地点", block=True, priority=1, permission=SUPERUSER)


@init_locations_cmd.handle()
async def handle_init_locations(event: MessageEvent):
    """初始化地点和NPC系统"""
    try:
        async with safe_session() as session:
            # 初始化市集地点和商人NPC
            market_count = await init_market_locations(session)

            # 初始化打工地点和雇主NPC
            job_count = await init_job_locations(session)

            # 初始化工坊地点和工匠NPC
            workshop_count = await init_workshop_locations(session)

            # 初始化特殊商店和NPC
            special_count = await init_special_locations(session)

            # 初始化社交NPC(月老、结义使者)
            social_count = await init_social_npcs(session)

            # 初始化中立NPC（已禁用 - 2025-12-07）
            # neutral_count = await init_neutral_npcs(session)
            neutral_count = 0  # 不再生成中立NPC

            await session.commit()

            result_msg = (
                "✅ NPC系统初始化完成！\n"
                "━━━━━━━━━━━━━\n"
                f"🏪 市集商人NPC：{market_count}个\n"
                f"💼 打工雇主NPC：{job_count}个\n"
                f"⚒️ 工匠NPC：{workshop_count}个\n"
                f"🏛️ 特殊NPC：{special_count}个\n"
                f"💕 社交NPC：{social_count}个\n"
                f"👤 中立NPC：{neutral_count}个\n"
                "━━━━━━━━━━━━━\n"
                "📍 所有NPC已添加到现有地点中\n"
                "🎯 玩家现在可以使用以下命令：\n"
                "• 【查看】查看当前位置信息\n"
                "• 【交互 <NPC名称>】与NPC交互\n"
                "• 【攻击 <目标>】攻击玩家或NPC\n"
                "• 【NPC列表】查看当前位置NPC\n"
                "━━━━━━━━━━━━━\n"
                "🌟 新增中立NPC具有丰富的怪谈风格对话！"
            )

            await init_locations_cmd.finish(message_add_head(result_msg, event))

    except SQLAlchemyError as e:
        await init_locations_cmd.finish(f"❌ 初始化失败（数据库）：{str(e)}")
    except ValueError as e:
        await init_locations_cmd.finish(f"❌ 初始化失败：{str(e)}")


async def init_market_locations(session) -> int:
    """在现有市集地点添加商人NPC"""
    # 从现有的merchants.py获取市集配置
    from ..economy.merchants import MARKETS

    created_count = 0

    for market in MARKETS:
        # 查找或创建地点（使用现有坐标，不改变地点名称）
        existing_location = await LocationService.get_location_by_coordinates(
            session, market.x, market.y, "大都会"
        )

        if not existing_location:
            # 创建地点，但使用原有的市集名称（不加"市集"后缀）
            location = Location.create_market_location(
                location_id=f"market_{market.id}",
                name=market.name,  # 保持原有名称：上京、北郊等
                x=market.x,
                y=market.y,
                market_items=market.items
            )
            session.add(location)
            await session.flush()
        else:
            location = existing_location
            # 确保functions字段不为None
            if location.functions is None:
                location.functions = {}
            # 为现有地点添加市集功能
            if not location.has_function("market"):
                market_config = {
                    "enabled": True,
                    "items": market.items,
                    "market_id": market.id
                }
                location.add_function("market", market_config)

        # 检查是否已有商人NPC（按名称和npc_id双重检查）
        merchant_name = f"商人{_get_merchant_name(market.name)}"
        merchant_npc_id = f"merchant_{market.id}"

        existing_merchant_by_name = await NPCService.get_npc_by_name(
            session, merchant_name, location.id
        )
        existing_merchant_by_id = await NPCService.get_npc_by_id(
            session, merchant_npc_id
        )

        if not existing_merchant_by_name and not existing_merchant_by_id:
            # 创建商人NPC
            merchant_npc = NPC.create_merchant(
                npc_id=merchant_npc_id,
                name=merchant_name,
                location_id=location.id,
                market_items=market.items
            )
            session.add(merchant_npc)
            created_count += 1

    return created_count


async def init_job_locations(session) -> int:
    """在现有打工地点添加雇主NPC"""
    # 从打工系统获取地点配置
    from ..economy.part_time_job_service import PartTimeJobService

    created_count = 0

    for location_id, location_data in PartTimeJobService.JOB_LOCATIONS.items():
        # 查找或创建地点
        existing_location = await LocationService.get_location_by_coordinates(
            session, location_data['x'], location_data['y'], "大都会"
        )

        if not existing_location:
            # 创建打工地点，保持原有名称
            location = Location.create_job_location(
                location_id=f"job_{location_id}",
                name=location_data['name'],
                x=location_data['x'],
                y=location_data['y'],
                description=location_data['description'],
                available_jobs=location_data.get('available_jobs', {})
            )
            session.add(location)
            await session.flush()
        else:
            location = existing_location
            # 确保functions字段不为None
            if location.functions is None:
                location.functions = {}
            # 为现有地点添加打工功能
            if not location.has_function("part_time_job"):
                job_config = {
                    "enabled": True,
                    "available_jobs": location_data.get('available_jobs', {}),
                    "max_workers": 10
                }
                location.add_function("part_time_job", job_config)

        # 检查是否已有雇主NPC（按名称和npc_id双重检查）
        employer_name = f"雇主{_get_employer_name(location_data['name'])}"
        employer_npc_id = f"employer_{location_id}"

        existing_employer_by_name = await NPCService.get_npc_by_name(
            session, employer_name, location.id
        )
        existing_employer_by_id = await NPCService.get_npc_by_id(
            session, employer_npc_id
        )

        if not existing_employer_by_name and not existing_employer_by_id:
            # 创建雇主NPC
            employer_npc = NPC.create_employer(
                npc_id=employer_npc_id,
                name=employer_name,
                location_id=location.id,
                available_jobs=location_data.get('available_jobs', {})
            )
            session.add(employer_npc)
            created_count += 1

    return created_count


async def init_workshop_locations(session) -> int:
    """为每个城市（市集）添加工匠NPC与城市专属锻造列表"""
    # 从市集配置中获取所有城市
    from ..economy.merchants import MARKETS

    # 城市专属锻造白名单（按世界观/难度系统细分）
    CITY_FORGE_WHITELIST: dict[str, list[str]] = {
        # === 新手区域 (1-30级) - 基础装备，白色/绿色品质 ===
        "北郊": ["bone_armor", "rusty_blade", "broken_glasses"],  # 新手村，基础三件套
        "东郊": ["bone_armor", "ghost_tear_pendant", "rusty_blade"],  # 东部新手区
        "西郊": ["ghost_tear_pendant", "broken_glasses", "bone_armor"],  # 西部新手区
        "南郊": ["rusty_blade", "broken_glasses", "ghost_tear_pendant"],  # 南部新手区

        # === 中级区域 (30-80级) - 进阶装备，蓝色品质为主 ===
        "荔湾镇": ["swim_coat", "self_awareness_key", "corrupted_bandage_wrap", "wedding_photo"],  # 水域主题
        "摩配镇": ["hospital_gown", "kitchen_knife", "school_uniform"],  # 都市恐怖主题
        "郸城": ["old_coat", "funeral_wreath", "music_box"],  # 死亡主题
        "舟山": ["crying_tape", "mirror_shard_armor", "grandfather_clock"],  # 时间/记忆主题
        "大昌市": ["old_coat", "funeral_wreath", "music_box"],  # 综合商埠，继承郸城锻造线

        # === 高级区域 (80-150级) - 高阶装备，紫色品质 ===
        "云岭": ["phantom_cloak", "fog_coat", "soul_flag"],  # 幽灵主题
        "金陵": ["drawer", "wedding_dress", "void_essence_crown", "shock_therapy_device"],  # 心理恐怖主题

        # === 终极区域 (150级+) - 神器级装备，橙色/红色品质 ===
        # 按照“由(0,0)新手村向外辐射、风雪镇最高”的规则：
        # • 上京(0,0)作为首都，可锻造所有基础和中级装备
        # • 风雪镇可锻造最高阶装备
        "上京": [
            # 白色装备
            "bone_armor", "ghost_tear_pendant", "broken_glasses", "rusty_blade",
            # 绿色装备
            "furnace", "wedding_photo", "swim_coat", "hospital_gown", "kitchen_knife",
            "self_awareness_key", "school_uniform", "old_coat", "corrupted_bandage_wrap",
            "music_box", "funeral_wreath"
        ],  # 首都，可锻造所有基础和中级装备
        "风雪镇": ["reality_suicide_note", "god_tear_amulet", "world_fragment_blade", "shroud_of_eternity"],  # 终极地区，最高级装备
    }

    def _get_craftsman_name_by_city(city_name: str) -> str:
        """获取城市对应的工匠名称，按主题风格命名"""
        name_map = {
            # 新手区域工匠 - 朴实名字
            "北郊": "打铁张",
            "东郊": "匠人许",
            "西郊": "工匠周",
            "南郊": "匠师南宫",

            # 中级区域工匠 - 主题化名字
            "荔湾镇": "水鬼匠师",  # 水域主题
            "摩配镇": "疯狂技师",  # 都市恐怖主题
            "郸城": "送葬匠人",  # 死亡主题
            "舟山": "时光工匠",  # 时间/记忆主题
            "大昌市": "大昌匠人",  # 综合商埠主题

            # 高级区域工匠 - 神秘名字
            "云岭": "幽魂锻师",  # 幽灵主题
            "金陵": "心魔巧匠",  # 心理恐怖主题

            # 终极区域工匠 - 传说级名字
            "上京": "百工坊宗师",  # 首都最高级
            "风雪镇": "炼魂大师",  # 特殊地区
        }
        return name_map.get(city_name, f"工匠{city_name}")

    created_count = 0

    for m in MARKETS:
        # 查找城市对应地点（市集地点已在 init_market_locations 中创建/补齐）
        existing_location = await LocationService.get_location_by_coordinates(
            session, m.x, m.y, "大都会"
        )
        if not existing_location:
            # 若异常缺失，则跳过该城市
            continue

        # 确保functions字段不为None
        if existing_location.functions is None:
            existing_location.functions = {}

        # 为地点添加锻造功能，并写入"城市专属锻造白名单"
        if not existing_location.has_function("forge"):
            forge_config = {
                "enabled": True,
                "services": ["forge", "enhance", "gem_socket"],
                "allow_items": CITY_FORGE_WHITELIST.get(m.name, [])
            }
            existing_location.add_function("forge", forge_config)
            # 显式回写以触发 SQLAlchemy MutableDict 变更跟踪
            existing_location.functions["forge"] = forge_config
        else:
            # 已存在锻造功能则补齐白名单字段
            cfg = existing_location.get_function_config("forge")
            cfg.setdefault("allow_items", CITY_FORGE_WHITELIST.get(m.name, []))

        # 查找/创建工匠NPC（每城一个）
        craftsman_name = _get_craftsman_name_by_city(m.name)
        craftsman_npc_id = f"craftsman_{m.id}"

        existing_craftsman_by_name = await NPCService.get_npc_by_name(
            session, craftsman_name, existing_location.id
        )
        existing_craftsman_by_id = await NPCService.get_npc_by_id(
            session, craftsman_npc_id
        )

        if not existing_craftsman_by_name and not existing_craftsman_by_id:
            craftsman_npc = NPC.create_craftsman(
                npc_id=craftsman_npc_id,
                name=craftsman_name,
                location_id=existing_location.id
            )
            session.add(craftsman_npc)
            created_count += 1

    return created_count


# ==================== 刷新工坊清单（覆盖写入） ====================
refresh_workshops_cmd = on_command("刷新工坊清单", block=True, priority=1, permission=SUPERUSER)


@refresh_workshops_cmd.handle()
async def handle_refresh_workshops(event: MessageEvent, args: Message = CommandArg()):
    """覆盖更新所有城市的工坊锻造白名单（按当前规则）。
    使用场景：历史上已初始化过地点，因 setdefault 不会覆盖老配置，导致新规则未生效。
    该命令将强制覆盖 allow_items，仅更新锻造清单，不改动其他功能字段。
    """
    try:
        async with safe_session() as session:
            # 市集（城市）列表
            from ..economy.merchants import MARKETS

            # 与 init_workshop_locations 规则保持一致（含新手村/风雪镇改动）
            CITY_FORGE_WHITELIST: dict[str, list[str]] = {
                # === 新手区域 (1-30级) - 基础装备，白色/绿色品质 ===
                "北郊": ["bone_armor", "rusty_blade", "broken_glasses"],
                "东郊": ["bone_armor", "ghost_tear_pendant", "rusty_blade"],
                "西郊": ["ghost_tear_pendant", "broken_glasses", "bone_armor"],
                "南郊": ["rusty_blade", "broken_glasses", "ghost_tear_pendant"],

                # === 中级区域 (30-80级) - 进阶装备，蓝色品质为主 ===
                "荔湾镇": ["swim_coat", "self_awareness_key", "corrupted_bandage_wrap", "wedding_photo"],
                "摩配镇": ["hospital_gown", "kitchen_knife", "school_uniform"],
                "郸城": ["old_coat", "funeral_wreath", "music_box"],
                "舟山": ["crying_tape", "mirror_shard_armor", "grandfather_clock"],
                "大昌市": ["old_coat", "funeral_wreath", "music_box"],

                # === 高级区域 (80-150级) - 高阶装备，紫色品质 ===
                "云岭": ["phantom_cloak", "fog_coat", "soul_flag"],
                "金陵": ["drawer", "wedding_dress", "void_essence_crown", "shock_therapy_device"],

                # === 终极区域 (150级+) - 最高级装备 ===
                # 上京(0,0)：作为首都，可锻造所有基础和中级装备
                "上京": [
                    # 白色装备
                    "bone_armor", "ghost_tear_pendant", "broken_glasses", "rusty_blade",
                    # 绿色装备
                    "furnace", "wedding_photo", "swim_coat", "hospital_gown", "kitchen_knife",
                    "self_awareness_key", "school_uniform", "old_coat", "corrupted_bandage_wrap",
                    "music_box", "funeral_wreath"
                ],
                # 风雪镇：最强装备
                "风雪镇": ["reality_suicide_note", "god_tear_amulet", "world_fragment_blade", "shroud_of_eternity"],
            }

            # —— 动态规则修正：低品质（白/绿）仅允许在(0,0)“上京”锻造 ——
            # 构建各稀有度物品集合（仅含有配方的装备）
            from ..config import config as _cfg
            by_id = _cfg.items_config["by_id"]
            low_ids = [c.item_id for c in by_id.values() if c.recipe and c.rarity in ("white", "green")]
            orange_ids = [c.item_id for c in by_id.values() if c.recipe and c.rarity == "orange"]

            # 1) 上京覆盖为全部白/绿装备
            CITY_FORGE_WHITELIST["上京"] = sorted(set(low_ids))
            # 2) 非上京城市移除所有白/绿
            for k, v in list(CITY_FORGE_WHITELIST.items()):
                if k == "上京":
                    continue
                CITY_FORGE_WHITELIST[k] = [iid for iid in v if iid not in low_ids]
            # 3) 风雪镇确保拥有全部橙色最高级装备
            existing = set(CITY_FORGE_WHITELIST.get("风雪镇", []))
            CITY_FORGE_WHITELIST["风雪镇"] = sorted(existing.union(orange_ids))


            from ..models.location import Location
            updated = 0
            created_forge = 0

            for m in MARKETS:
                # 查找城市地点
                loc = await LocationService.get_location_by_coordinates(session, m.x, m.y, "大都会")
                if not loc:
                    continue

                # 确保 functions 存在
                if loc.functions is None:
                    loc.functions = {}

                # 若无 forge 功能则添加
                if not loc.has_function("forge"):
                    forge_config = {
                        "enabled": True,
                        "services": ["forge", "enhance", "gem_socket"],
                        "allow_items": []
                    }
                    loc.add_function("forge", forge_config)
                    # 显式回写以触发 SQLAlchemy MutableDict 变更跟踪
                    loc.functions["forge"] = forge_config
                    created_forge += 1

                # 覆盖 allow_items（注意：为触发 SQLAlchemy 变更跟踪，需要回写到 functions）
                cfg = dict(loc.get_function_config("forge") or {})
                cfg["allow_items"] = CITY_FORGE_WHITELIST.get(m.name, [])
                loc.functions["forge"] = cfg  # 回写以触发 MutableDict 变更
                updated += 1

            await session.commit()

            msg = (
                "✅ 工坊清单刷新完成！\n"
                "━━━━━━━━━━━━━\n"
                f"🔧 覆盖城市：{updated} 个\n"
                f"🧰 新增工坊功能：{created_forge} 个\n"
                "━━━━━━━━━━━━━\n"
                "💡 已按当前规则：上京(0,0)仅初级、风雪镇最高级"
            )
            await refresh_workshops_cmd.finish(message_add_head(msg, event))

    except SQLAlchemyError as e:
        await refresh_workshops_cmd.finish(f"❌ 刷新失败（数据库）：{str(e)}")
    except ValueError as e:
        await refresh_workshops_cmd.finish(f"❌ 刷新失败：{str(e)}")
async def init_special_locations(session) -> int:
    """在缉邪司总部添加管理员NPC"""
    # 缉邪司总部
    from ..economy.merchants import HEADQUARTERS_COORD

    created_count = 0

    # 查找缉邪司总部地点
    existing_location = await LocationService.get_location_by_coordinates(
        session, HEADQUARTERS_COORD[0], HEADQUARTERS_COORD[1], "大都会"
    )

    if not existing_location:
        # 创建缉邪司总部地点
        location = Location.create_special_shop_location(
            location_id="headquarters",
            name="缉邪司总部",
            x=HEADQUARTERS_COORD[0],
            y=HEADQUARTERS_COORD[1],
            shop_type="headquarters"
        )
        location.description = "缉邪司总部，这里可以用积分兑换升阶材料"
        session.add(location)
        await session.flush()
    else:
        location = existing_location
        # 确保functions字段不为None
        if location.functions is None:
            location.functions = {}
        # 为现有地点添加特殊商店功能
        if not location.has_function("special_shop"):
            shop_config = {
                "enabled": True,
                "shop_type": "headquarters"
            }
            location.add_function("special_shop", shop_config)

    # 检查是否已有管理员NPC（按名称和npc_id双重检查）
    admin_name = "司长曹延华"
    admin_npc_id = "headquarters_admin"

    existing_admin_by_name = await NPCService.get_npc_by_name(
        session, admin_name, location.id
    )
    existing_admin_by_id = await NPCService.get_npc_by_id(
        session, admin_npc_id
    )

    if not existing_admin_by_name and not existing_admin_by_id:
        # 创建总部管理员NPC
        admin_npc = NPC(
            npc_id=admin_npc_id,
            name=admin_name,
            description="缉邪司司长，负责积分兑换和升阶材料管理",
            npc_type=NPCType.SPECIAL_VENDOR,
            location_id=location.id,
            is_killable=False
        )
        admin_npc.add_function("headquarters_shop", {"enabled": True})
        session.add(admin_npc)
        created_count += 1

    return created_count


async def init_social_npcs(session) -> int:
    """
    初始化社交NPC(月老、结义使者)

    在上京(0,0)添加月老和结义使者
    """
    from ..models.npc import NPC, NPCType
    from ..economy.merchants import MARKETS

    created_count = 0

    # 找到上京市集地点
    shangjing_market = None
    for market in MARKETS:
        if market.name == "上京":
            # 查找上京市集对应的地点
            shangjing_market = await LocationService.get_location_by_coordinates(
                session, market.x, market.y, "大都会"
            )
            break

    if not shangjing_market:
        # 如果找不到上京，就不创建
        return 0

    # 确保functions字段不为None
    if shangjing_market.functions is None:
        shangjing_market.functions = {}

    # 添加社交功能
    if not shangjing_market.has_function("social"):
        shangjing_market.add_function("social", {"enabled": True})

    # 1. 创建月老NPC
    matchmaker_npc_id = "matchmaker_shangjing"
    existing_matchmaker = await NPCService.get_npc_by_id(session, matchmaker_npc_id)

    if not existing_matchmaker:
        matchmaker_npc = NPC(
            npc_id=matchmaker_npc_id,
            name="月老",
            description="掌管天下姻缘的老人，手持红绳，据说能牵起千里良缘",
            npc_type=NPCType.NORMAL,
            location_id=shangjing_market.id,
            is_killable=False,
            is_active=True
        )
        matchmaker_npc.add_function("matchmaker", {"enabled": True})
        session.add(matchmaker_npc)
        created_count += 1

    # 2. 创建结义使者NPC
    sworn_npc_id = "sworn_envoy_shangjing"
    existing_sworn = await NPCService.get_npc_by_id(session, sworn_npc_id)

    if not existing_sworn:
        sworn_npc = NPC(
            npc_id=sworn_npc_id,
            name="结义使者",
            description="负责见证江湖义气的使者，曾为无数英雄豪杰主持结义仪式",
            npc_type=NPCType.NORMAL,
            location_id=shangjing_market.id,
            is_killable=False,
            is_active=True
        )
        sworn_npc.add_function("sworn_ceremony", {"enabled": True})
        session.add(sworn_npc)
        created_count += 1

    return created_count


async def init_neutral_npcs(session) -> int:
    """
    初始化中立NPC，增加世界观深度和怪谈氛围

    注意：此函数已被禁用（2025-12-07）
    原因：清理装饰性NPC，专注于有服务功能的核心NPC
    详见：llmdoc/agent/npc_cleanup_investigation.md
    """
    # 已禁用 - 不再生成32个装饰性中立NPC
    return 0


def _get_merchant_name(market_name: str) -> str:
    """根据市集名称生成商人名称"""
    name_map = {
        "上京": "李掌柜",
        "北郊": "王五",
        "东郊": "赵六",
        "西郊": "钱七",
        "南郊": "孙八",
        "金陵": "周九",
        "云岭": "吴十",
        "郸城": "郑一",
        "荔湾镇": "冯二",
        "摩配镇": "陈三",
        "风雪镇": "褚四"
    }
    return name_map.get(market_name, "老板")


def _get_employer_name(location_name: str) -> str:
    """根据地点名称生成雇主名称"""
    if "商业" in location_name:
        return "刘经理"
    elif "工业" in location_name:
        return "厂长老张"
    elif "娱乐" in location_name:
        return "店长小李"
    elif "配送" in location_name:
        return "主管老陈"
    else:
        return "负责人"


# ==================== 中立NPC初始化命令 ====================
# 已禁用 - 2025-12-07: 不再生成装饰性中立NPC
# init_neutral_cmd = on_command("初始化中立NPC", block=True, priority=1, permission=SUPERUSER)
#
#
# @init_neutral_cmd.handle()
# async def handle_init_neutral_npcs(event: MessageEvent):
#     """单独初始化中立NPC"""
#     try:
#         async with safe_session() as session:
#             # 初始化中立NPC
#             neutral_count = await init_neutral_npcs(session)
#
#             await session.commit()
#
#             result_msg = (
#                 "✅ 中立NPC初始化完成！\n"
#                 "━━━━━━━━━━━━━\n"
#                 f"👤 新增中立NPC：{neutral_count}个\n"
#                 "━━━━━━━━━━━━━\n"
#                 "🌟 特色功能：\n"
#                 "• 丰富的怪谈风格对话\n"
#                 "• 随机/循环对话系统\n"
#                 "• 神秘的世界观背景\n"
#                 "• 诡异的氛围描述\n"
#                 "━━━━━━━━━━━━━\n"
#                 "🎯 使用【交互 <NPC名称>】与他们对话\n"
#                 "👻 每次交互都可能听到不同的故事！"
#             )
#
#             await init_neutral_cmd.finish(message_add_head(result_msg, event))
#
#     except SQLAlchemyError as e:
#         error_msg = f"❌ 中立NPC初始化失败（数据库）：{str(e)}"
#         await init_neutral_cmd.finish(message_add_head(error_msg, event))
#     except ValueError as e:
#         error_msg = f"❌ 中立NPC初始化失败：{str(e)}"
#         await init_neutral_cmd.finish(message_add_head(error_msg, event))


# ==================== 迁移命令 ====================
migrate_data_cmd = on_command("迁移数据", block=True, priority=1, permission=SUPERUSER)


@migrate_data_cmd.handle()
async def handle_migrate_data(event: MessageEvent):
    """迁移现有数据到新系统"""
    try:
        async with safe_session() as session:
            # 迁移打工地点数据
            migrated_count = await LocationService.migrate_from_job_locations(session)

            await session.commit()

            result_msg = (
                "✅ 数据迁移完成！\n"
                "━━━━━━━━━━━━━\n"
                f"📦 迁移地点：{migrated_count}个\n"
                "━━━━━━━━━━━━━\n"
                "💡 原有数据已保留，新系统已集成"
            )

            await migrate_data_cmd.finish(message_add_head(result_msg, event))

    except ValueError as e:
        await migrate_data_cmd.finish(f"❌ 迁移失败：{str(e)}")


# ==================== 清理命令 ====================
cleanup_npcs_cmd = on_command("清理NPC", block=True, priority=1, permission=SUPERUSER)


@cleanup_npcs_cmd.handle()
async def handle_cleanup_npcs(event: MessageEvent):
    """清理过期的动态NPC"""
    try:
        async with safe_session() as session:
            # 检查并复活NPC
            respawned_count = await NPCService.check_and_respawn_npcs(session)

            # 清理过期的动态NPC
            cleaned_count = await NPCService.cleanup_expired_dynamic_npcs(session, max_age_hours=24)

            await session.commit()

            result_msg = (
                "✅ NPC清理完成！\n"
                "━━━━━━━━━━━━━\n"
                f"🔄 复活NPC：{respawned_count}个\n"
                f"🗑️ 清理过期NPC：{cleaned_count}个\n"
                "━━━━━━━━━━━━━\n"
                "💡 系统已自动维护NPC状态"
            )

            await cleanup_npcs_cmd.finish(message_add_head(result_msg, event))

    except ValueError as e:
        await cleanup_npcs_cmd.finish(f"❌ 清理失败：{str(e)}")
