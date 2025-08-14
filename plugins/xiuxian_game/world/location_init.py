"""
地点和NPC初始化系统

初始化游戏中的默认地点和NPC，迁移现有系统数据
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.permission import SUPERUSER

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
            
            await session.commit()
            
            result_msg = (
                "✅ NPC系统初始化完成！\n"
                "━━━━━━━━━━━━━\n"
                f"🏪 市集商人NPC：{market_count}个\n"
                f"💼 打工雇主NPC：{job_count}个\n"
                f"⚒️ 工匠NPC：{workshop_count}个\n"
                f"🏛️ 特殊NPC：{special_count}个\n"
                "━━━━━━━━━━━━━\n"
                "📍 所有NPC已添加到现有地点中\n"
                "🎯 玩家现在可以使用以下命令：\n"
                "• 【查看】查看当前位置信息\n"
                "• 【交互 <NPC名称>】与NPC交互\n"
                "• 【攻击 <目标>】攻击玩家或NPC\n"
                "• 【NPC列表】查看当前位置NPC"
            )
            
            await init_locations_cmd.finish(message_add_head(result_msg, event))
            
    except Exception as e:
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

        # 检查是否已有商人NPC
        existing_merchant = await NPCService.get_npc_by_name(
            session, f"商人{_get_merchant_name(market.name)}", location.id
        )

        if not existing_merchant:
            # 创建商人NPC
            merchant_npc = NPC.create_merchant(
                npc_id=f"merchant_{market.id}",
                name=f"商人{_get_merchant_name(market.name)}",
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

        # 检查是否已有雇主NPC
        employer_name = f"雇主{_get_employer_name(location_data['name'])}"
        existing_employer = await NPCService.get_npc_by_name(
            session, employer_name, location.id
        )

        if not existing_employer:
            # 创建雇主NPC
            employer_npc = NPC.create_employer(
                npc_id=f"employer_{location_id}",
                name=employer_name,
                location_id=location.id,
                available_jobs=location_data.get('available_jobs', {})
            )
            session.add(employer_npc)
            created_count += 1

    return created_count


async def init_workshop_locations(session) -> int:
    """在现有地点添加工匠NPC"""
    # 在一些现有的市集地点添加工匠NPC，而不是创建新地点
    workshops = [
        {
            "x": -5,
            "y": 390,
            "craftsman_name": "风雪大师"
        },
        {
            "x": 390,
            "y": 50,
            "craftsman_name": "铁匠老王"
        },
        {
            "x": -420,
            "y": 140,
            "craftsman_name": "锻造师李三"
        }
    ]

    created_count = 0

    for workshop in workshops:
        # 查找现有地点
        existing_location = await LocationService.get_location_by_coordinates(
            session, workshop['x'], workshop['y'], "大都会"
        )

        if existing_location:
            # 确保functions字段不为None
            if existing_location.functions is None:
                existing_location.functions = {}
            # 为现有地点添加锻造功能
            if not existing_location.has_function("forge"):
                forge_config = {
                    "enabled": True,
                    "services": ["forge", "enhance", "gem_socket"]
                }
                existing_location.add_function("forge", forge_config)

            # 检查是否已有工匠NPC
            existing_craftsman = await NPCService.get_npc_by_name(
                session, workshop['craftsman_name'], existing_location.id
            )

            if not existing_craftsman:
                # 创建工匠NPC
                craftsman_npc = NPC.create_craftsman(
                    npc_id=f"craftsman_{workshop['x']}_{workshop['y']}",
                    name=workshop['craftsman_name'],
                    location_id=existing_location.id
                )
                session.add(craftsman_npc)
                created_count += 1

    return created_count


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

    # 检查是否已有管理员NPC
    existing_admin = await NPCService.get_npc_by_name(
        session, "司长曹延华", location.id
    )

    if not existing_admin:
        # 创建总部管理员NPC
        admin_npc = NPC(
            npc_id="headquarters_admin",
            name="司长曹延华",
            description="缉邪司司长，负责积分兑换和升阶材料管理",
            npc_type=NPCType.SPECIAL_VENDOR,
            location_id=location.id,
            is_killable=False
        )
        admin_npc.add_function("headquarters_shop", {"enabled": True})
        session.add(admin_npc)
        created_count += 1

    return created_count


def _get_merchant_name(market_name: str) -> str:
    """根据市集名称生成商人名称"""
    name_map = {
        "上京": "李四",
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
        return "主管老王"
    else:
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
            
    except Exception as e:
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
            
    except Exception as e:
        await cleanup_npcs_cmd.finish(f"❌ 清理失败：{str(e)}")
