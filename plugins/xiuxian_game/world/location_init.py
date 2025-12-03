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

            # 初始化中立NPC
            neutral_count = await init_neutral_npcs(session)

            await session.commit()

            result_msg = (
                "✅ NPC系统初始化完成！\n"
                "━━━━━━━━━━━━━\n"
                f"🏪 市集商人NPC：{market_count}个\n"
                f"💼 打工雇主NPC：{job_count}个\n"
                f"⚒️ 工匠NPC：{workshop_count}个\n"
                f"🏛️ 特殊NPC：{special_count}个\n"
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

        # 为地点添加锻造功能，并写入“城市专属锻造白名单”
        if not existing_location.has_function("forge"):
            forge_config = {
                "enabled": True,
                "services": ["forge", "enhance", "gem_socket"],
                "allow_items": CITY_FORGE_WHITELIST.get(m.name, [])
            }
            existing_location.add_function("forge", forge_config)
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


async def init_neutral_npcs(session) -> int:
    """初始化中立NPC，增加世界观深度和怪谈氛围"""
    created_count = 0

    # 定义中立NPC配置 - 全部分布在已有的市集和城镇地点
    neutral_npcs = [
        # === 市集区域的神秘NPC ===
        # 上京 (0, 0) - 商业中心
        {
            "npc_id": "night_watchman",
            "name": "更夫·李四",
            "x": 0, "y": 0,
            "description": "一个打更的老人，总是在深夜出现",
            "dialogues": [
                "🔔 李四：「天干物燥，小心火烛...也要小心那些看不见的东西」",
                "🔔 李四：「我打更几十年，见过太多怪事...有些事不能说」",
                "🔔 李四：「夜里总有人影在街上飘...那不是活人」",
                "🔔 李四：「年轻人，夜深了就别出门...外面不安全」",
                "🔔 李四：「最近缉邪司的人经常出动...看来又有大事要发生了」"
            ]
        },
        {
            "npc_id": "tea_house_owner",
            "name": "茶馆老板·赵掌柜",
            "x": 0, "y": 0,
            "description": "一个和蔼的中年男人，但眼神总是有些飘忽",
            "dialogues": [
                "🍵 赵掌柜：「来杯茶吧...我这茶能压惊，最近很多人需要」",
                "🍵 赵掌柜：「听说又有修士失踪了...这年头修炼真危险」",
                "🍵 赵掌柜：「我这茶馆开了三十年，见过太多奇人异事」",
                "🍵 赵掌柜：「有些客人喝完茶就再也没来过...也不知道去哪了」",
                "🍵 赵掌柜：「夜里总有人敲门要茶喝...但开门一看，什么都没有」"
            ]
        },

        # 北郊 (100, 460)
        {
            "npc_id": "paper_money_seller",
            "name": "纸钱铺老板·孙婆婆",
            "x": 100, "y": 460,
            "description": "一个佝偻的老妇人，专门制作纸钱和冥器",
            "dialogues": [
                "🪙 孙婆婆：「买点纸钱吧...死人也要花钱的」",
                "🪙 孙婆婆：「最近生意特别好...总有人要给死去的亲人烧钱」",
                "🪙 孙婆婆：「我做的纸钱特别灵验...死人收到了会托梦感谢」",
                "🪙 孙婆婆：「有些修炼的人死了，家人都不敢来买纸钱...怕招惹什么」",
                "🪙 孙婆婆：「你知道吗？有些纸钱烧了会变成真钱...但代价很大」"
            ]
        },
        {
            "npc_id": "grave_digger",
            "name": "掘墓人·老黑",
            "x": 100, "y": 460,
            "description": "一个皮肤黝黑的老人，专门负责挖坟掘墓",
            "dialogues": [
                "⚱️ 老黑：「挖了一辈子坟，见过太多不该见的东西...」",
                "⚱️ 老黑：「有些棺材里的人，死了几十年还像活着一样」",
                "⚱️ 老黑：「修炼的人死后不一样...他们的尸体会发光」",
                "⚱️ 老黑：「最怕挖到那种会动的棺材...里面的东西还在修炼」",
                "⚱️ 老黑：「年轻人，别想着长生不老...死了才是解脱」"
            ]
        },

        # 东郊 (390, 50) - 物流中心
        {
            "npc_id": "old_storyteller",
            "name": "说书人·老刘",
            "x": 390, "y": 50,
            "description": "一个满脸皱纹的老人，总是在讲述着古怪的故事",
            "dialogues": [
                "📚 老刘：「想听故事吗？我知道很多...关于那些死而不僵的东西」",
                "📚 老刘：「从前啊，有个修士进了诡域，出来后就变了个人...」",
                "📚 老刘：「你知道为什么有些地方总是阴森森的吗？因为死过太多人了」",
                "📚 老刘：「听说缉邪司最近很忙，到处都有诡异事件...这世道啊」",
                "📚 老刘：「年轻人，修炼虽好，但别太贪心...有些力量是要付出代价的」"
            ]
        },
        {
            "npc_id": "courier_ghost",
            "name": "快递员·阿飘",
            "x": 390, "y": 50,
            "description": "一个面色苍白的快递员，总是在送一些奇怪的包裹",
            "dialogues": [
                "📦 阿飘：「我送的包裹...有些是给活人的，有些是给死人的」",
                "📦 阿飘：「最怕送到那些修炼者家里...他们的房子总是阴森森的」",
                "📦 阿飘：「有一次送包裹，收件人已经死了三天...但还是签收了」",
                "📦 阿飘：「你们修炼的人订的东西都很奇怪...骨头、血液、魂魄...」",
                "📦 阿飘：「我怀疑自己也死了...但还在送快递，这正常吗？」"
            ]
        },

        # 西郊 (-420, 140)
        {
            "npc_id": "herb_collector",
            "name": "采药人·王麻子",
            "x": -420, "y": 140,
            "description": "一个脸上有麻子的中年男人，常年在山里采药",
            "dialogues": [
                "🌿 王麻子：「山里的药材越来越难找了...那些地方总有怪事」",
                "🌿 王麻子：「我见过会动的尸体，还有会说话的骷髅...都在深山里」",
                "🌿 王麻子：「有些草药长在坟地里，药效特别好...但代价也大」",
                "🌿 王麻子：「最近山里总有奇怪的声音，像是有人在哭...」",
                "🌿 王麻子：「你们这些修士啊，总想要好东西，却不知道危险」"
            ]
        },
        {
            "npc_id": "mountain_hermit",
            "name": "隐士·无名老人",
            "x": -420, "y": 140,
            "description": "一个神秘的老人，据说曾经也是修炼者",
            "dialogues": [
                "🏔️ 无名老人：「我曾经也修炼过...但看透了这一切的虚妄」",
                "🏔️ 无名老人：「修炼到最后，你会发现自己变成了怪物」",
                "🏔️ 无名老人：「山里有很多修炼失败的人...他们变成了别的东西」",
                "🏔️ 无名老人：「年轻人，趁早回头吧...这条路没有尽头」",
                "🏔️ 无名老人：「我见过太多天才...最后都疯了，或者死了」"
            ]
        },

        # 南郊 (-100, -480)
        {
            "npc_id": "funeral_director",
            "name": "殡仪师·白无常",
            "x": -100, "y": -480,
            "description": "一个穿着白衣的中年男人，专门处理死者后事",
            "dialogues": [
                "🕯️ 白无常：「死亡是每个人的归宿...包括修炼者」",
                "🕯️ 白无常：「我处理过很多修炼者的尸体...他们死得都很奇怪」",
                "🕯️ 白无常：「有些人死后还在修炼...尸体会自己动」",
                "🕯️ 白无常：「最可怕的是那些炼尸的...把自己变成了不死不活的东西」",
                "🕯️ 白无常：「年轻人，好好活着吧...死了就什么都没有了」"
            ]
        },
        {
            "npc_id": "soul_guide",
            "name": "引魂人·孟婆",
            "x": -100, "y": -480,
            "description": "一个神秘的老妇人，据说能看见死者的灵魂",
            "dialogues": [
                "👻 孟婆：「我能看见死者的灵魂...他们总是不愿意离开」",
                "👻 孟婆：「修炼的人死后灵魂特别执着...很难超度」",
                "👻 孟婆：「有些修炼者的灵魂会分裂...变成很多个鬼」",
                "👻 孟婆：「你身边跟着几个鬼魂...都是你杀死的」",
                "👻 孟婆：「修炼就是在和死神赛跑...但死神总是会赢」"
            ]
        },
        # 金陵 (220, -350)
        {
            "npc_id": "antique_dealer",
            "name": "古董商·钱老板",
            "x": 220, "y": -350,
            "description": "一个戴着眼镜的中年男人，专门收购奇怪的古董",
            "dialogues": [
                "� 钱老板：「我这里有很多好东西...都是从死人手里收来的」",
                "� 钱老板：「有些古董有灵性，会选择自己的主人...」",
                "💎 钱老板：「你见过会哭的玉佩吗？我这里就有一块」",
                "💎 钱老板：「修炼的人总喜欢这些老东西...但要小心被反噬」",
                "💎 钱老板：「最近收到一面镜子，照出来的不是你的脸...」"
            ]
        },
        {
            "npc_id": "jade_appraiser",
            "name": "鉴宝师·石眼",
            "x": 220, "y": -350,
            "description": "一个只有一只眼睛的老人，专门鉴定奇珍异宝",
            "dialogues": [
                "👁️ 石眼：「我这只眼睛能看透一切宝物的来历...」",
                "👁️ 石眼：「有些宝物沾满了血腥...是从死人身上扒下来的」",
                "👁️ 石眼：「修炼者的法器最值钱...但也最危险」",
                "👁️ 石眼：「我见过会吃人的宝石...还有会哭的珍珠」",
                "👁️ 石眼：「年轻人，不是所有宝物都能要...有些会要你的命」"
            ]
        },

        # 云岭 (-250, 490)
        {
            "npc_id": "cloud_watcher",
            "name": "观云者·风无痕",
            "x": -250, "y": 490,
            "description": "一个总是仰望天空的神秘老人",
            "dialogues": [
                "☁️ 风无痕：「云中有异象...预示着大劫将至」",
                "☁️ 风无痕：「我在云中看到了很多死去的修炼者...他们在警告什么」",
                "☁️ 风无痕：「天空中的裂缝越来越多...那是通往诡域的门」",
                "☁️ 风无痕：「修炼者死后会变成云...在天空中游荡」",
                "☁️ 风无痕：「年轻人，抬头看看天空...你会看到自己的未来」"
            ]
        },
        {
            "npc_id": "weather_prophet",
            "name": "天象师·雷鸣",
            "x": -250, "y": 490,
            "description": "一个能预测天气的神秘术士",
            "dialogues": [
                "⚡ 雷鸣：「雷电中藏着天机...我能听到天的声音」",
                "⚡ 雷鸣：「最近雷声很不对劲...像是有什么东西在天上打架」",
                "⚡ 雷鸣：「修炼者渡劫时会引来天雷...但有些雷是来杀人的」",
                "⚡ 雷鸣：「我见过被雷劈死的修炼者...他们的尸体还在冒烟」",
                "⚡ 雷鸣：「天要下雨了...血雨」"
            ]
        },

        # 郸城 (120, 120) - 娱乐街区
        {
            "npc_id": "street_performer",
            "name": "街头艺人·小丑",
            "x": 120, "y": 120,
            "description": "一个画着诡异妆容的街头艺人，总是在表演奇怪的戏法",
            "dialogues": [
                "🎭 小丑：「想看魔术吗？我能让死人复活...」",
                "🎭 小丑：「哈哈哈...这世界本身就是个大戏台，我们都是演员」",
                "🎭 小丑：「我见过真正的鬼怪...它们比我的表演更精彩」",
                "🎭 小丑：「修炼？那也是一种表演...看谁能演到最后」",
                "🎭 小丑：「你想知道真相吗？真相就是...没有真相！」"
            ]
        },
        {
            "npc_id": "puppet_master",
            "name": "木偶师·线无形",
            "x": 120, "y": 120,
            "description": "一个操控木偶的神秘艺人，木偶看起来像真人",
            "dialogues": [
                "🎎 线无形：「我的木偶都是用死人的骨头做的...」",
                "🎎 线无形：「有时候我分不清谁是木偶，谁是真人」",
                "🎎 线无形：「修炼者死后最适合做木偶...他们的魂魄还在」",
                "🎎 线无形：「你想成为我的木偶吗？永远不会死...」",
                "🎎 线无形：「我怀疑自己也是别人的木偶...」"
            ]
        },

        # 荔湾镇 (120, 200) - 工业区
        {
            "npc_id": "factory_ghost",
            "name": "工厂管理员·铁面",
            "x": 120, "y": 200,
            "description": "一个戴着铁面具的工厂管理员，从不摘下面具",
            "dialogues": [
                "🏭 铁面：「这个工厂死过很多人...机器里还有他们的血」",
                "🏭 铁面：「夜班的时候总能听到机器自己在运转...」",
                "🏭 铁面：「有些工人死了还在上班...他们不知道自己已经死了」",
                "🏭 铁面：「修炼者的血能让机器运转得更快...」",
                "🏭 铁面：「我的面具下面...已经没有脸了」"
            ]
        },
        {
            "npc_id": "machine_whisperer",
            "name": "机械师·齿轮",
            "x": 120, "y": 200,
            "description": "一个能和机器对话的神秘技师",
            "dialogues": [
                "⚙️ 齿轮：「机器会说话...它们告诉我很多秘密」",
                "⚙️ 齿轮：「这些机器吃过人肉...它们变得有灵性了」",
                "⚙️ 齿轮：「修炼者的法器和机器很像...都有自己的意识」",
                "⚙️ 齿轮：「我把自己的一部分换成了机器...现在分不清哪里是人哪里是机器」",
                "⚙️ 齿轮：「机器告诉我，人类很快就要被替代了...」"
            ]
        },

        # 摩配镇 (80, 140)
        {
            "npc_id": "motorcycle_mechanic",
            "name": "摩托修理工·轰鸣",
            "x": 80, "y": 140,
            "description": "一个满身机油的修理工，专门修理各种奇怪的载具",
            "dialogues": [
                "🏍️ 轰鸣：「我修过很多奇怪的车...有些是用骨头做的」",
                "🏍️ 轰鸣：「修炼者的飞行法器坏了也会来找我修...」",
                "🏍️ 轰鸣：「有一次修车，发现油箱里装的是血...」",
                "🏍️ 轰鸣：「最怕修那些会自己动的车...它们有自己的意识」",
                "🏍️ 轰鸣：「我的手已经变成了扳手...再也变不回来了」"
            ]
        },
        {
            "npc_id": "speed_demon",
            "name": "车手·疾风",
            "x": 80, "y": 140,
            "description": "一个神秘的赛车手，据说能开着车穿越诡域",
            "dialogues": [
                "🏁 疾风：「我开车去过诡域...那里的路都是用骨头铺的」",
                "🏁 疾风：「速度够快就能逃脱死神...但总有一天会被追上」",
                "🏁 疾风：「我见过很多修炼者在路上死掉...他们跑得不够快」",
                "🏁 疾风：「我的车里坐着很多鬼魂...他们都是我撞死的」",
                "🏁 疾风：「想要真正的速度？把灵魂卖给恶魔...」"
            ]
        },

        # 风雪镇 (-5, 390)
        {
            "npc_id": "mysterious_fortune_teller",
            "name": "算命婆·陈瞎子",
            "x": -5, "y": 390,
            "description": "一个双目失明的老妇人，总是喃喃自语着什么",
            "dialogues": [
                "👁️ 陈瞎子：「我虽双目失明，却能看见你看不见的东西...」",
                "👁️ 陈瞎子：「这世间的诡异，远比你想象的要多...最近总有死人托梦给我」",
                "👁️ 陈瞎子：「年轻人，你身上有股阴气...是不是最近去过什么不该去的地方？」",
                "👁️ 陈瞎子：「缉邪司的人啊...你们以为能管得住这些东西？呵呵...」",
                "👁️ 陈瞎子：「我听说最近又有人失踪了，都是些修炼的年轻人...小心啊」"
            ]
        },
        {
            "npc_id": "ice_sculptor",
            "name": "冰雕师·寒无痕",
            "x": -5, "y": 390,
            "description": "一个专门雕刻冰雕的艺术家，作品栩栩如生",
            "dialogues": [
                "🧊 寒无痕：「我雕的都是死人...他们在冰中永远不会腐烂」",
                "🧊 寒无痕：「有些冰雕会在夜里动...它们想要复活」",
                "🧊 寒无痕：「修炼者的尸体最适合做冰雕...他们的表情很生动」",
                "🧊 寒无痕：「我把自己的心也冻成了冰...现在感受不到任何温暖」",
                "🧊 寒无痕：「冰雕会说话...它们告诉我生前的秘密」"
            ]
        },

        # 舟山 (200, -200)
        {
            "npc_id": "fisherman_ghost",
            "name": "渔夫·老海",
            "x": 200, "y": -200,
            "description": "一个常年在海边捕鱼的老人，身上总是湿漉漉的",
            "dialogues": [
                "🎣 老海：「海里的鱼越来越少了...但死人越来越多」",
                "🎣 老海：「我钓上来的不只是鱼...还有很多奇怪的东西」",
                "🎣 老海：「修炼者死在海里会变成海怪...我见过很多」",
                "🎣 老海：「海底有一座城市...住着所有溺死的人」",
                "🎣 老海：「我怀疑自己也淹死了...但还在钓鱼」"
            ]
        },
        {
            "npc_id": "lighthouse_keeper",
            "name": "灯塔守护者·明灯",
            "x": 200, "y": -200,
            "description": "一个守护灯塔的神秘老人，灯塔的光很奇怪",
            "dialogues": [
                "🗼 明灯：「我的灯塔能照亮死者的灵魂...」",
                "🗼 明灯：「每天晚上都有鬼魂来敲门...它们想要光明」",
                "🗼 明灯：「修炼者死后会变成光...在灯塔里游荡」",
                "🗼 明灯：「我已经守了一百年的灯塔...但我不记得自己是什么时候死的」",
                "🗼 明灯：「灯塔的光能指引迷路的灵魂...包括活人的灵魂」"
            ]
        }
    ]


    # 创建中立NPC
    for npc_config in neutral_npcs:
        # 检查坐标处是否已有地点
        location = await LocationService.get_location_by_coordinates(
            session, npc_config["x"], npc_config["y"], "大都会"
        )

        if not location:
            # 如果没有地点，跳过这个NPC（因为要求必须在已有地点）
            print(f"警告：坐标 ({npc_config['x']}, {npc_config['y']}) 没有找到已有地点，跳过NPC {npc_config['name']}")
            continue

        # 检查是否已有该NPC（按名称和npc_id双重检查）
        existing_npc_by_name = await NPCService.get_npc_by_name(
            session, npc_config["name"], location.id
        )
        existing_npc_by_id = await NPCService.get_npc_by_id(
            session, npc_config["npc_id"]
        )

        if not existing_npc_by_name and not existing_npc_by_id:
            # 创建中立NPC
            neutral_npc = NPC(
                npc_id=npc_config["npc_id"],
                name=npc_config["name"],
                description=npc_config["description"],
                npc_type=NPCType.NORMAL,
                location_id=location.id,
                is_killable=False,
                extra_data={
                    "dialogues": npc_config["dialogues"],
                    "dialogue_index": 0,
                    "is_neutral": True,
                    "mystery_level": "high"
                }
            )
            session.add(neutral_npc)
            created_count += 1

    return created_count


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
init_neutral_cmd = on_command("初始化中立NPC", block=True, priority=1, permission=SUPERUSER)


@init_neutral_cmd.handle()
async def handle_init_neutral_npcs(event: MessageEvent):
    """单独初始化中立NPC"""
    try:
        async with safe_session() as session:
            # 初始化中立NPC
            neutral_count = await init_neutral_npcs(session)

            await session.commit()

            result_msg = (
                "✅ 中立NPC初始化完成！\n"
                "━━━━━━━━━━━━━\n"
                f"👤 新增中立NPC：{neutral_count}个\n"
                "━━━━━━━━━━━━━\n"
                "🌟 特色功能：\n"
                "• 丰富的怪谈风格对话\n"
                "• 随机/循环对话系统\n"
                "• 神秘的世界观背景\n"
                "• 诡异的氛围描述\n"
                "━━━━━━━━━━━━━\n"
                "🎯 使用【交互 <NPC名称>】与他们对话\n"
                "👻 每次交互都可能听到不同的故事！"
            )

            await init_neutral_cmd.finish(message_add_head(result_msg, event))

    except SQLAlchemyError as e:
        error_msg = f"❌ 中立NPC初始化失败（数据库）：{str(e)}"
        await init_neutral_cmd.finish(message_add_head(error_msg, event))
    except ValueError as e:
        error_msg = f"❌ 中立NPC初始化失败：{str(e)}"
        await init_neutral_cmd.finish(message_add_head(error_msg, event))


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
