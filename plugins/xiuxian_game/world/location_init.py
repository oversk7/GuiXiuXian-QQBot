"""
地点和NPC初始化系统

初始化游戏中的默认地点和NPC，迁移现有系统数据
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.adapters.qq import Message
from nonebot.params import CommandArg

from nonebot.permission import SUPERUSER

from sqlalchemy import select
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

            # 初始化驿丞NPC（每城1个）
            station_master_count = await init_station_masters(session)

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
                f"🏛️ 驿丞NPC：{station_master_count}个\n"
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
    """初始化/同步市集地点和商人NPC（支持坐标更新和新城市创建）"""
    from ..economy.merchants import MARKETS

    created_count = 0

    # 收集当前配置的所有城市名
    current_city_names = {market.name for market in MARKETS}

    for market in MARKETS:
        # 优先按名称查找（支持坐标变更后的城市匹配）
        stmt = select(Location).where(
            Location.name == market.name,
            Location.region == "大都会"
        )
        result = await session.execute(stmt)
        existing_by_name = result.scalars().first()

        if existing_by_name:
            location = existing_by_name
            # 同步坐标（城市可能搬迁了）
            if location.x != market.x or location.y != market.y:
                location.x = market.x
                location.y = market.y
            # 确保有市集功能
            if location.functions is None:
                location.functions = {}
            market_config = {
                "enabled": True,
                "items": market.items,
                "market_id": market.id
            }
            location.add_function("market", market_config)
        else:
            # 再按坐标查找（兜底）
            existing_by_coord = await LocationService.get_location_by_coordinates(
                session, market.x, market.y, "大都会"
            )
            if existing_by_coord:
                location = existing_by_coord
                if location.functions is None:
                    location.functions = {}
                if not location.has_function("market"):
                    market_config = {
                        "enabled": True,
                        "items": market.items,
                        "market_id": market.id
                    }
                    location.add_function("market", market_config)
            else:
                # 全新城市，创建 Location
                location = Location.create_market_location(
                    location_id=f"market_{market.id}",
                    name=market.name,
                    x=market.x,
                    y=market.y,
                    market_items=market.items
                )
                session.add(location)
                await session.flush()

        # 检查是否已有商人NPC
        merchant_name = f"商人{_get_merchant_name(market.name)}"
        merchant_npc_id = f"merchant_{market.id}"

        existing_merchant_by_name = await NPCService.get_npc_by_name(
            session, merchant_name, location.id
        )
        existing_merchant_by_id = await NPCService.get_npc_by_id(
            session, merchant_npc_id
        )

        if not existing_merchant_by_name and not existing_merchant_by_id:
            merchant_npc = NPC.create_merchant(
                npc_id=merchant_npc_id,
                name=merchant_name,
                location_id=location.id,
                market_items=market.items
            )
            session.add(merchant_npc)
            created_count += 1

    # 清理已移除城市的 Location 记录（四郊）
    removed_cities = {"北郊", "东郊", "西郊", "南郊"}
    for city_name in removed_cities:
        stmt = select(Location).where(
            Location.name == city_name,
            Location.region == "大都会"
        )
        result = await session.execute(stmt)
        old_location = result.scalars().first()
        if old_location:
            # 删除关联的NPC
            npc_stmt = select(NPC).where(NPC.location_id == old_location.id)
            npc_result = await session.execute(npc_stmt)
            for npc in npc_result.scalars().all():
                await session.delete(npc)
            await session.delete(old_location)

    return created_count


async def init_job_locations(session) -> int:
    """初始化/同步打工地点和雇主NPC（支持坐标更新和新地点创建）"""
    from ..economy.part_time_job_service import PartTimeJobService

    created_count = 0

    for location_id, location_data in PartTimeJobService.JOB_LOCATIONS.items():
        # 优先按名称查找（支持坐标变更后的匹配）
        stmt = select(Location).where(
            Location.name == location_data['name'],
            Location.region == "大都会"
        )
        result = await session.execute(stmt)
        existing_by_name = result.scalars().first()

        if existing_by_name:
            location = existing_by_name
            # 同步坐标
            if location.x != location_data['x'] or location.y != location_data['y']:
                location.x = location_data['x']
                location.y = location_data['y']
            if location.functions is None:
                location.functions = {}
            job_config = {
                "enabled": True,
                "available_jobs": location_data.get('available_jobs', {}),
                "max_workers": 10
            }
            location.add_function("part_time_job", job_config)
        else:
            # 再按坐标查找（兜底）
            existing_by_coord = await LocationService.get_location_by_coordinates(
                session, location_data['x'], location_data['y'], "大都会"
            )
            if existing_by_coord:
                location = existing_by_coord
                if location.functions is None:
                    location.functions = {}
                if not location.has_function("part_time_job"):
                    job_config = {
                        "enabled": True,
                        "available_jobs": location_data.get('available_jobs', {}),
                        "max_workers": 10
                    }
                    location.add_function("part_time_job", job_config)
            else:
                # 全新打工地点
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

        # 检查是否已有雇主NPC
        employer_name = f"雇主{_get_employer_name(location_data['name'])}"
        employer_npc_id = f"employer_{location_id}"

        existing_employer_by_name = await NPCService.get_npc_by_name(
            session, employer_name, location.id
        )
        existing_employer_by_id = await NPCService.get_npc_by_id(
            session, employer_npc_id
        )

        if not existing_employer_by_name and not existing_employer_by_id:
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
        "天海卫": ["bone_armor", "rusty_blade", "broken_glasses"],  # 新手区
        "石关": ["bone_armor", "ghost_tear_pendant", "rusty_blade"],  # 新手区
        "郸城": ["ghost_tear_pendant", "broken_glasses", "bone_armor"],  # 新手区

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
            # 京畿
            "上京": "百工坊宗师",
            "郸城": "送葬匠人",
            "摩配镇": "疯狂技师",
            "天海卫": "打铁张",
            "石关": "匠人许",
            # 江南
            "金陵": "心魔巧匠",
            "姑苏": "织锦匠师",
            "临安": "碧水工匠",
            "海门": "远洋匠人",
            "舟山": "时光工匠",
            # 南海
            "荔湾镇": "水鬼匠师",
            "鹏城": "南洋锻师",
            "鹭岛": "海风匠人",
            "琼崖": "椰林工匠",
            # 蜀地
            "锦官城": "蜀山锻师",
            "大昌市": "大昌匠人",
            "剑阁": "剑门匠人",
            "夜郎": "蛮荒铸师",
            "云岭": "幽魂锻师",
            # 关中
            "长安": "古都宗匠",
            "神都": "洛神锻师",
            "陈仓": "暗仓匠人",
            "金城": "丝路铸师",
            # 中原
            "汴梁": "中原匠人",
            "颍川": "颍水工匠",
            "江夏": "江汉锻师",
            "潭州": "湘楚匠人",
            # 北境
            "辽阳": "北铁匠师",
            "龙城": "寒霜锻师",
            "风雪镇": "炼魂大师",
            "冰原堡": "极寒铸师",
            # 西域
            "玉门": "关外匠人",
            "楼兰": "沙海锻师",
            "龟兹": "异域工匠",
            "轮台": "戍边铸师",
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
                "天海卫": ["bone_armor", "rusty_blade", "broken_glasses"],
                "石关": ["bone_armor", "ghost_tear_pendant", "rusty_blade"],
                "郸城": ["ghost_tear_pendant", "broken_glasses", "bone_armor"],

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

    # 查找缉邪司总部地点（优先按名称匹配）
    stmt = select(Location).where(
        Location.name == "缉邪司总部",
        Location.region == "大都会"
    )
    result = await session.execute(stmt)
    existing_by_name = result.scalars().first()

    if not existing_by_name:
        # 再按坐标查找
        existing_by_name = await LocationService.get_location_by_coordinates(
            session, HEADQUARTERS_COORD[0], HEADQUARTERS_COORD[1], "大都会"
        )

    if not existing_by_name:
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
        location = existing_by_name
        # 同步坐标
        if location.x != HEADQUARTERS_COORD[0] or location.y != HEADQUARTERS_COORD[1]:
            location.x = HEADQUARTERS_COORD[0]
            location.y = HEADQUARTERS_COORD[1]
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
    初始化社交NPC和社交代理

    - 月老 → 临安（姻缘圣地）
    - 结义使者 → 长安（武道义气）
    - 师徒使者 → 金陵（文教传承）
    - 8个集群主城各放一个社交代理（提供全部三种社交功能）
    """
    from ..models.npc import NPC, NPCType
    from ..economy.merchants import MARKETS

    created_count = 0

    # 清理旧版社交NPC（从上京迁出）
    old_npc_ids = ["matchmaker_shangjing", "sworn_envoy_shangjing", "mentor_envoy_shangjing"]
    for old_id in old_npc_ids:
        old_npc = await NPCService.get_npc_by_id(session, old_id)
        if old_npc:
            await session.delete(old_npc)

    # 辅助函数：按城市名找到Location
    async def find_city_location(city_name: str):
        for market in MARKETS:
            if market.name == city_name:
                loc = await LocationService.get_location_by_coordinates(
                    session, market.x, market.y, "大都会"
                )
                return loc
        return None

    # ===== 1. 月老 → 临安 =====
    linan_loc = await find_city_location("临安")
    if linan_loc:
        if not linan_loc.has_function("social"):
            linan_loc.add_function("social", {"enabled": True})
        matchmaker_id = "matchmaker_linan"
        existing = await NPCService.get_npc_by_id(session, matchmaker_id)
        if not existing:
            npc = NPC(
                npc_id=matchmaker_id,
                name="月老",
                description="掌管天下姻缘的老人，手持红绳，据说能牵起千里良缘",
                npc_type=NPCType.NORMAL,
                location_id=linan_loc.id,
                is_killable=False,
                is_active=True
            )
            npc.add_function("matchmaker", {"enabled": True})
            session.add(npc)
            created_count += 1

    # ===== 2. 结义使者 → 长安 =====
    changan_loc = await find_city_location("长安")
    if changan_loc:
        if not changan_loc.has_function("social"):
            changan_loc.add_function("social", {"enabled": True})
        sworn_id = "sworn_envoy_changan"
        existing = await NPCService.get_npc_by_id(session, sworn_id)
        if not existing:
            npc = NPC(
                npc_id=sworn_id,
                name="结义使者",
                description="负责见证江湖义气的使者，曾为无数英雄豪杰主持结义仪式",
                npc_type=NPCType.NORMAL,
                location_id=changan_loc.id,
                is_killable=False,
                is_active=True
            )
            npc.add_function("sworn_ceremony", {"enabled": True})
            session.add(npc)
            created_count += 1

    # ===== 3. 师徒使者 → 金陵 =====
    jinling_loc = await find_city_location("金陵")
    if jinling_loc:
        if not jinling_loc.has_function("social"):
            jinling_loc.add_function("social", {"enabled": True})
        mentor_id = "mentor_envoy_jinling"
        existing = await NPCService.get_npc_by_id(session, mentor_id)
        if not existing:
            npc = NPC(
                npc_id=mentor_id,
                name="师徒使者",
                description="传承之道的见证者，师徒关系的缔结者",
                npc_type=NPCType.NORMAL,
                location_id=jinling_loc.id,
                is_killable=False,
                is_active=True
            )
            npc.add_function("mentorship", {"enabled": True})
            session.add(npc)
            created_count += 1

    # ===== 4. 8个集群主城的社交代理 =====
    social_agent_cities = {
        "上京": "社交代理·京畿",
        "姑苏": "社交代理·江南",
        "荔湾镇": "社交代理·南海",
        "锦官城": "社交代理·蜀地",
        "神都": "社交代理·关中",
        "汴梁": "社交代理·中原",
        "辽阳": "社交代理·北境",
        "楼兰": "社交代理·西域",
    }

    for city_name, agent_name in social_agent_cities.items():
        loc = await find_city_location(city_name)
        if not loc:
            continue
        if not loc.has_function("social"):
            loc.add_function("social", {"enabled": True})

        agent_npc_id = f"social_agent_{city_name}"
        existing = await NPCService.get_npc_by_id(session, agent_npc_id)
        if not existing:
            npc = NPC(
                npc_id=agent_npc_id,
                name=agent_name,
                description="可代办姻缘、结义、师徒等社交事务的官方代理",
                npc_type=NPCType.NORMAL,
                location_id=loc.id,
                is_killable=False,
                is_active=True
            )
            npc.add_function("social_agent", {"enabled": True})
            npc.add_function("matchmaker", {"enabled": True})
            npc.add_function("sworn_ceremony", {"enabled": True})
            npc.add_function("mentorship", {"enabled": True})
            session.add(npc)
            created_count += 1

    return created_count


async def init_station_masters(session) -> int:
    """
    初始化驿丞NPC — 每座城市1个

    驿丞提供：本城NPC列表、集群城市导航、附近城市距离
    """
    from ..models.npc import NPC, NPCType
    from ..economy.merchants import MARKETS

    created_count = 0

    station_master_names = {
        "上京": "驿丞·京畿总驿", "郸城": "驿丞·郸城驿", "摩配镇": "驿丞·摩配驿",
        "天海卫": "驿丞·天海驿", "石关": "驿丞·石关驿",
        "金陵": "驿丞·金陵驿", "姑苏": "驿丞·姑苏驿", "临安": "驿丞·临安驿",
        "海门": "驿丞·海门驿", "舟山": "驿丞·舟山驿",
        "荔湾镇": "驿丞·荔湾驿", "鹏城": "驿丞·鹏城驿", "鹭岛": "驿丞·鹭岛驿",
        "琼崖": "驿丞·琼崖驿",
        "锦官城": "驿丞·锦官驿", "大昌市": "驿丞·大昌驿", "剑阁": "驿丞·剑阁驿",
        "夜郎": "驿丞·夜郎驿", "云岭": "驿丞·云岭驿",
        "长安": "驿丞·长安驿", "神都": "驿丞·神都驿", "陈仓": "驿丞·陈仓驿",
        "金城": "驿丞·金城驿",
        "汴梁": "驿丞·汴梁驿", "颍川": "驿丞·颍川驿", "江夏": "驿丞·江夏驿",
        "潭州": "驿丞·潭州驿",
        "辽阳": "驿丞·辽阳驿", "龙城": "驿丞·龙城驿", "风雪镇": "驿丞·风雪驿",
        "冰原堡": "驿丞·冰原驿",
        "玉门": "驿丞·玉门驿", "楼兰": "驿丞·楼兰驿", "龟兹": "驿丞·龟兹驿",
        "轮台": "驿丞·轮台驿",
    }

    for market in MARKETS:
        loc = await LocationService.get_location_by_coordinates(
            session, market.x, market.y, "大都会"
        )
        if not loc:
            continue

        npc_id = f"station_master_{market.name}"
        existing = await NPCService.get_npc_by_id(session, npc_id)
        if not existing:
            npc_name = station_master_names.get(market.name, f"驿丞·{market.name}驿")
            npc = NPC(
                npc_id=npc_id,
                name=npc_name,
                description="负责驿站事务的官员，熟知各地风土人情和路线",
                npc_type=NPCType.NORMAL,
                location_id=loc.id,
                is_killable=False,
                is_active=True
            )
            npc.add_function("station_master", {"enabled": True})
            session.add(npc)
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
        "郸城": "郸城商客",
        "摩配镇": "孙三",
        "天海卫": "马九",
        "石关": "卫十一",
        "金陵": "金陵商客",
        "姑苏": "范掌柜",
        "临安": "沈掌柜",
        "海门": "顾掌柜",
        "舟山": "舟山鱼商",
        "荔湾镇": "荔湾商客",
        "鹏城": "陈掌柜",
        "鹭岛": "林掌柜",
        "琼崖": "黎掌柜",
        "锦官城": "蜀商张",
        "大昌市": "大昌商客",
        "剑阁": "关商刘",
        "夜郎": "蛮商阿布",
        "云岭": "云岭药商",
        "长安": "秦商白",
        "神都": "洛商周",
        "陈仓": "仓商吕",
        "金城": "河西商客",
        "汴梁": "宋商赵",
        "颍川": "豫商曹",
        "江夏": "楚商黄",
        "潭州": "湘商谭",
        "辽阳": "辽商耶律",
        "龙城": "边商完颜",
        "风雪镇": "褚四",
        "冰原堡": "北商哈达",
        "玉门": "关商李",
        "楼兰": "胡商阿里",
        "龟兹": "龟兹商客",
        "轮台": "轮台戍商"
    }
    return name_map.get(market_name, "老板")


def _get_employer_name(location_name: str) -> str:
    """根据地点名称生成雇主名称"""
    name_map = {
        "商业": "刘经理",
        "工业": "厂长老张",
        "娱乐": "店长小李",
        "物流": "主管老陈",
        "农贸": "老农郭叔",
        "文化": "馆长方先生",
        "采矿": "矿头赵铁柱",
        "修配": "车行老王",
        "哨站": "哨长孙大壮",
        "渔业": "船老大黄三",
        "商贸": "掌柜钱婆婆",
    }
    for keyword, name in name_map.items():
        if keyword in location_name:
            return name
    return "负责人"



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
