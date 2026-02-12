"""
攻击命令

处理玩家攻击其他玩家或NPC的功能，集成现有战斗系统
支持荒野PvP和城镇切磋两种模式
"""

from nonebot import on_command
# 所有命令均需block=True（在命令注册处已统一配置）

from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import time
import random
from datetime import datetime


from ..models.db import safe_session
from ..models.player import Player
from ..models.npc import NPCType
from ..models.inventory import ItemInstance
from ..utils import message_add_head
from .location_service import LocationService
from .npc_service import NPCService
from ..player.realm_utils import realm_by_level_and_reincarnation
from ..battle.integration_helper import BattleIntegrationHelper
from ..config import config
from ..models.pvp_log import PvpLog
from sqlalchemy.exc import SQLAlchemyError



# 掉落保护（短期内避免重复劫掠）
DROP_PROTECTION_SECONDS = 60
_last_pvp_drop_time: dict[str, float] = {}


# ==================== 城镇判断函数 ====================
def is_in_town(x: int, y: int, region: str = "大都会") -> bool:
    """判断玩家是否在城镇（安全区域）中"""
    # 诡域中允许死斗，不算城镇
    if region != "大都会":
        return False

    # 市集坐标（安全区域）
    from ..economy.merchants import MARKETS, HEADQUARTERS_COORD

    # 检查是否在市集附近（5格内算安全区域）
    for market in MARKETS:
        distance = abs(x - market.x) + abs(y - market.y)
        if distance <= 5:
            return True

    # 检查是否在缉邪司总部附近（5格内算安全区域）
    hq_distance = abs(x - HEADQUARTERS_COORD[0]) + abs(y - HEADQUARTERS_COORD[1])
    if hq_distance <= 5:
        return True

    # 检查是否在打工地点附近（5格内算安全区域）
    try:
        from ..economy.part_time_job_service import PartTimeJobService
        for location_data in PartTimeJobService.JOB_LOCATIONS.values():
            distance = abs(x - location_data['x']) + abs(y - location_data['y'])
            if distance <= 5:
                return True
    except ImportError:
        # 如果导入失败，使用默认坐标（已整合到城镇中）
        default_job_coords = [(0, 0), (120, 200), (120, 120), (390, 50)]
        for job_x, job_y in default_job_coords:
            distance = abs(x - job_x) + abs(y - job_y)
            if distance <= 5:
                return True

    return False


# ==================== 荒野掉落处理 ====================
async def handle_wilderness_drops(session, loser: Player, winner: Player) -> str:
    """处理荒野死斗的物品掉落

    Args:
        session: 数据库会话
        loser: 败者玩家
        winner: 胜者玩家（击杀者）

    Returns:
        掉落信息字符串
    """
    from sqlalchemy import select
    from ..models.inventory import ItemType

    # 获取败者的所有背包物品，排除装备
    result = await session.execute(
        select(ItemInstance).where(
            ItemInstance.player_id == loser.id,
            ItemInstance.quantity > 0
        )
    )
    all_items = result.scalars().all()

    # 过滤掉装备，只掉落消耗品、材料、商品等
    droppable_items = []
    for item in all_items:
        item_config = config.items_config["by_id"].get(item.item_id)
        if not item_config:
            continue

        # 只允许掉落非装备物品
        if item_config.type in [ItemType.CONSUMABLE, ItemType.MATERIAL, ItemType.GOODS, ItemType.GHOST_FRAGMENT]:
            # 进一步过滤：不掉落珍贵材料（紫色及以上稀有度）
            if hasattr(item_config, 'rarity') and item_config.rarity in ['purple', 'orange', 'red']:
                continue  # 跳过珍贵材料
            droppable_items.append(item)

    if not droppable_items:
        return f"💀 {loser.nickname} 没有可掉落的物品"

    # 计算掉落数量（可掉落物品的10%-25%）
    total_stacks = len(droppable_items)
    drop_rate = random.uniform(0.1, 0.25)  # 10%-25%的掉落率
    drop_count = max(1, int(total_stacks * drop_rate))  # 至少掉落1个物品堆叠

    # 随机选择要掉落的物品
    dropped_items = random.sample(droppable_items, min(drop_count, len(droppable_items)))
    obtained_items = []  # 成功获得的物品
    discarded_items = []  # 因背包满而丢弃的物品

    for item in dropped_items:
        item_config = config.items_config["by_id"].get(item.item_id)
        if not item_config:
            continue

        # 计算掉落数量（该堆叠的20%-50%，比之前更温和）
        drop_quantity = max(1, int(item.quantity * random.uniform(0.2, 0.5)))
        drop_quantity = min(drop_quantity, item.quantity)

        # 从败者身上扣除物品
        item.quantity -= drop_quantity
        if item.quantity <= 0:
            await session.delete(item)

        # 尝试将物品给予击杀者
        try:
            await ItemInstance.add_item(session, winner.id, item.item_id, drop_quantity)
            obtained_items.append(f"{item_config.name} ✖️{drop_quantity}")
        except ValueError:
            # 背包满了，物品丢弃
            discarded_items.append(f"{item_config.name} ✖️{drop_quantity}")

    # 构建掉落信息
    result_msg = []
    if obtained_items:
        result_msg.append(f"💎 {winner.nickname} 获得了：{', '.join(obtained_items)}")
    if discarded_items:
        result_msg.append(f"📦 背包已满，丢弃了：{', '.join(discarded_items)}")

    if not obtained_items and not discarded_items:
        return f"💀 {loser.nickname} 没有掉落任何物品"

    return "\n".join(result_msg)


# ==================== 攻击命令 ====================
attack_cmd = on_command("攻击", aliases={"死斗"}, block=True, priority=5)


@attack_cmd.handle()
async def handle_attack(event: MessageEvent, args: Message = CommandArg()):
    """处理攻击命令"""
    user_id = event.get_user_id()

    args_text = args.extract_plain_text().strip()

    if not args_text:
        help_msg = (
            "⚔️ 攻击系统\n"
            "━━━━━━━━━━━━━\n"
            "🎯 使用方法：\n"
            "【攻击 <目标名称>】攻击指定目标\n"
            "【攻击 <UID>】攻击指定UID的玩家\n"
            "━━━━━━━━━━━━━\n"
            "💡 可攻击目标：\n"
            "• 其他玩家（城镇切磋/荒野死斗）\n"
            "• 鬼怪NPC（真实战斗）\n"
            "• 可击杀的NPC\n"
            "━━━━━━━━━━━━━\n"
            "🏘️ 城镇 vs 荒野/诡域：\n"
            "• 城镇（市集/总部/打工地点附近5格）：安全切磋，无损失\n"
            "• 荒野/诡域（其他区域）：真实死斗，双方都会受伤，败者掉落物品\n"
            "━━━━━━━━━━━━━\n"
            "🔍 智能匹配：\n"
            "• 支持部分名称匹配\n"
            "• 【攻击 乔强】可匹配【邪教徒·乔强】\n"
            "• 【攻击 邪教徒】可匹配【邪教徒·乔强】\n"
            "━━━━━━━━━━━━━\n"
            "⚠️ 注意事项：\n"
            "• 攻击距离：最多允许2格距离（已修复坐标系统问题）\n"
            "• 荒野/诡域攻击有真实风险，请谨慎选择！\n"
            "• 死斗中双方都会根据战斗伤害损失血量\n"
            "• 败者只掉落消耗品、材料、商品，不掉落装备\n"
            "• 不会掉落珍贵材料（紫色及以上稀有度）\n"
            "• 攻击NPC可能导致其死亡\n"
            "• 死亡的NPC会在一定时间后复活\n"
            "━━━━━━━━━━━━━\n"
            "🌟 示例：攻击 1001 或 攻击 乔强"
        )
        await attack_cmd.finish(message_add_head(help_msg, event))

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await attack_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await attack_cmd.finish("⛔ 请先创建角色")

        # 在诡域内允许攻击；跨世界目标会在区域一致性与距离校验中被拦截
        if player.hp <= 0:
            await attack_cmd.finish("⛔ 你已死亡，无法发起攻击")

        # 获取当前位置
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()

        # 尝试解析目标（传入player.id用于任务关联优先匹配）
        target_player, target_npc = await parse_attack_target(session, args_text, current_x, current_y, current_region, player.id)

        if target_player:
            await handle_player_attack(session, player, target_player, event)
        elif target_npc:
            await handle_npc_attack(session, player, target_npc, event)
        else:
            # 检查是否有多个匹配结果
            location = await LocationService.get_location_by_coordinates(session, current_x, current_y, current_region)
            if location:
                possible_npcs = await find_npc_by_smart_match(session, args_text, location.id)
                if len(possible_npcs) > 1:
                    npc_list = []
                    for npc in possible_npcs[:5]:  # 最多显示5个
                        npc_list.append(f"• {npc.name}")

                    msg = (
                        f"🔍 找到多个匹配'{args_text}'的目标：\n"
                        "━━━━━━━━━━━━━\n" +
                        "\n".join(npc_list) +
                        ("\n..." if len(possible_npcs) > 5 else "") +
                        "\n━━━━━━━━━━━━━\n"
                        "💡 请使用更具体的名称，如：\n"
                        f"• 【攻击 {possible_npcs[0].name.split('·')[-1]}】\n"
                        f"• 【攻击 {possible_npcs[0].name}】"
                    )
                    await attack_cmd.finish(message_add_head(msg, event))

            await attack_cmd.finish(f"⛔ 找不到目标'{args_text}'，请确认目标在当前位置")


async def parse_attack_target(session, target_name: str, x: int, y: int, region: str, player_id: str = None):
    """解析攻击目标"""
    from sqlalchemy import select, and_

    target_player = None
    target_npc = None

    # 尝试按UID查找玩家
    if target_name.isdigit():
        uid = int(target_name)
        # 查找所有同区域的玩家，然后手动筛选距离
        stmt = select(Player).where(Player.uid == uid)
        result = await session.execute(stmt)
        candidate = result.scalar_one_or_none()

        if candidate:
            # 检查是否在同一区域且距离合适
            candidate_region = candidate.get_current_region()
            if candidate_region == region:
                candidate_x, candidate_y = candidate.get_current_coordinates()
                distance = abs(candidate_x - x) + abs(candidate_y - y)
                if distance <= 2:  # 攻击距离限制
                    target_player = candidate
    else:
        # 按名称查找玩家 - 查找所有同区域的玩家
        if region == "大都会":
            # 现实世界中的玩家
            stmt = select(Player).where(
                and_(
                    Player.nickname == target_name,
                    Player.dungeon_level == 0  # 在现实世界
                )
            )
        else:
            # 诡域中的玩家 - 需要解析层级
            if "层诡域" in region:
                try:
                    dungeon_level = int(region.replace("层诡域", ""))
                    stmt = select(Player).where(
                        and_(
                            Player.nickname == target_name,
                            Player.dungeon_level == dungeon_level
                        )
                    )
                except ValueError:
                    stmt = select(Player).where(Player.nickname == target_name)
            else:
                stmt = select(Player).where(Player.nickname == target_name)

        result = await session.execute(stmt)
        candidates = result.scalars().all()

        # 从候选者中找到距离合适的
        for candidate in candidates:
            candidate_region = candidate.get_current_region()
            if candidate_region == region:
                candidate_x, candidate_y = candidate.get_current_coordinates()
                distance = abs(candidate_x - x) + abs(candidate_y - y)
                if distance <= 2:  # 攻击距离限制
                    target_player = candidate
                    break

        # 如果没找到玩家，查找NPC
        if not target_player:
            location = await LocationService.get_location_by_coordinates(session, x, y, region)
            if location:
                # 先尝试精确匹配
                try:
                    target_npc = await NPCService.get_npc_by_name(session, target_name, location.id)
                except Exception as e:
                    # 捕获MultipleResultsFound异常（多个重名NPC）
                    # 这种情况下直接进入智能匹配逻辑
                    if "Multiple rows were found" in str(e):
                        target_npc = None
                    else:
                        raise  # 其他异常继续抛出

                if not target_npc:
                    # 尝试智能匹配（支持带点号的名字）
                    possible_npcs = await find_npc_by_smart_match(session, target_name, location.id)
                    if len(possible_npcs) == 1:
                        target_npc = possible_npcs[0]
                    elif len(possible_npcs) > 1:
                        # 多个匹配结果时，优先匹配玩家自己的任务NPC（方案4：任务关联优先匹配）
                        if player_id:
                            from ..models.daily_task import DailyTask
                            # 查询玩家的已接取任务
                            stmt = select(DailyTask).where(
                                and_(
                                    DailyTask.player_id == player_id,
                                    DailyTask.status == "accepted"
                                )
                            )
                            result = await session.execute(stmt)
                            player_tasks = result.scalars().all()

                            # 检查是否有NPC与玩家任务关联
                            if player_tasks:
                                task_ids = {task.id for task in player_tasks}
                                for npc in possible_npcs:
                                    # 检查NPC的extra_data中是否有task_id，且与玩家任务匹配
                                    if npc.extra_data and npc.extra_data.get("task_id") in task_ids:
                                        target_npc = npc
                                        break  # 找到玩家任务的NPC，优先返回

                        # 如果没有找到任务关联的NPC，尝试更精确的匹配
                        if not target_npc:
                            exact_matches = [npc for npc in possible_npcs if target_name.lower() in npc.name.lower()]
                            if len(exact_matches) == 1:
                                target_npc = exact_matches[0]

    return target_player, target_npc


async def find_npc_by_smart_match(session, target_name: str, location_id: int):
    """智能匹配NPC名称，支持带点号的名字"""
    from sqlalchemy import select, and_, or_
    from ..models.npc import NPC, NPCStatus

    # 清理输入的目标名称
    clean_target = target_name.strip()

    # 构建多种匹配条件
    conditions = [
        NPC.location_id == location_id,
        NPC.is_active == True,
        NPC.status != NPCStatus.DEAD
    ]

    # 匹配策略：
    # 1. 包含目标名称的NPC
    # 2. 点号后面部分匹配（如"乔强"匹配"邪教徒·乔强"）
    # 3. 点号前面部分匹配（如"邪教徒"匹配"邪教徒·乔强"）
    name_conditions = or_(
        NPC.name.like(f"%{clean_target}%"),  # 基础模糊匹配
        NPC.name.like(f"%·{clean_target}"),  # 匹配点号后的部分
        NPC.name.like(f"{clean_target}·%"),  # 匹配点号前的部分
    )

    conditions.append(name_conditions)

    stmt = select(NPC).where(and_(*conditions))
    result = await session.execute(stmt)
    npcs = result.scalars().all()

    # 按匹配优先级排序
    def match_priority(npc):
        name = npc.name.lower()
        target = clean_target.lower()

        # 精确匹配优先级最高
        if name == target:
            return 0
        # 完整包含目标名称
        elif target in name:
            return 1
        # 点号后匹配
        elif f"·{target}" in name:
            return 2
        # 点号前匹配
        elif f"{target}·" in name:
            return 3
        # 其他模糊匹配
        else:
            return 4

    return sorted(npcs, key=match_priority)


async def handle_player_attack(session, attacker: Player, target: Player, event: MessageEvent):
    """处理玩家vs玩家攻击（城镇切磋或荒野死斗）"""
    if attacker.id == target.id:
        await attack_cmd.finish("⛔ 你不能攻击自己")

    # 检查目标是否在同一区域
    attacker_region = attacker.get_current_region()
    target_region = target.get_current_region()
    if target.hp <= 0:
        await attack_cmd.finish("⛔ 对方已濒死，无法继续劫掠\n💡 等其复活后再试")

    if attacker_region != target_region:
        await attack_cmd.finish("⛔ 目标不在同一区域")

    # 获取正确的当前坐标并计算距离（曼哈顿距离）
    attacker_x, attacker_y = attacker.get_current_coordinates()
    target_x, target_y = target.get_current_coordinates()
    distance = abs(attacker_x - target_x) + abs(attacker_y - target_y)
    if distance > 2:
        await attack_cmd.finish(f"⛔ 目标距离过远（{distance}格），最多允许2格距离")

    # 判断是否在城镇中
    current_x, current_y = attacker.get_current_coordinates()
    current_region = attacker.get_current_region()
    in_town = is_in_town(current_x, current_y, current_region)
    # 阴宅作为安全区
    try:
        from ..cultivate.mansion_service_new import MansionService
        if MansionService.is_at_mansion(attacker) or MansionService.is_at_mansion(target):
            in_town = True
    except ImportError:
        pass

    # 荒野死斗不允许对子管理员发起
    if not in_town:
        from ..ai_guide import is_sub_admin
        if is_sub_admin(target.id):
            await attack_cmd.finish("⛔ 不允许对子管理员发起荒野死斗")

    # 死斗前镜怨体质（自保）判定：仅在荒野/诡域且为被动防御方触发
    if not in_town:
        # 检查目标是否穿戴镜怨之衣
        from sqlalchemy import select
        try:
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == target.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id == "vip_robe_jingyuanzhiyi"
            )
            target_robe = (await session.execute(stmt)).scalars().first()
        except SQLAlchemyError:
            target_robe = None
        if target_robe:
            # 镜怨体质触发：反杀来犯者
            loser = attacker
            winner = target
            result_lines = [
                "⚠️ 死斗触发前置判定",
                "━━━━━━━━━━━━━",
                f"🪞 {target.nickname}的『镜怨之衣』[镜怨体质]映照来犯之人",
                f"⚰️ {attacker.nickname}当场毙命！(镜怨体质·自保)",
                "━━━━━━━━━━━━━",
            ]
            # 立即结算死亡与掉落
            attacker_damage = attacker.hp  # 全部生命归零
            target_damage = 0
            attacker.hp = 0
            # 掉落（含保护）
            now_ts = time.time()
            last_ts = _last_pvp_drop_time.get(loser.id, 0)
            if now_ts - last_ts < DROP_PROTECTION_SECONDS:
                result_lines.append("🛡️ 掉落保护生效：短时间内不再掉落物品")
                drop_summary = "🛡️ 掉落保护生效"
            else:
                drop_msg = await handle_wilderness_drops(session, loser, winner)
                _last_pvp_drop_time[loser.id] = now_ts
                if drop_msg:
                    result_lines.append(drop_msg)
                    drop_summary = drop_msg.replace("\n", "；")
                else:
                    drop_summary = "无掉落"

            # 镜怨之衣自噬：自身死亡+2攻击（日上限20）——此处未触发（因目标未死），仅保留为战后通用处理
            # 记录死斗日志
            try:
                bt_simple = "诡域" if current_region != "大都会" else "荒野"
                log = PvpLog(
                    ts=int(time.time()),
                    region=current_region,
                    x=attacker_x,
                    y=attacker_y,
                    attacker_id=attacker.id,
                    defender_id=target.id,
                    attacker_uid=attacker.uid,
                    defender_uid=target.uid,
                    attacker_name=attacker.nickname,
                    defender_name=target.nickname,
                    battle_type=bt_simple,
                    attacker_victory=0,
                    attacker_damage=attacker_damage,
                    defender_damage=target_damage,
                    drop_summary=drop_summary,
                )
                session.add(log)
            except (ValueError, SQLAlchemyError):
                pass

            await session.commit()

            # 检查新手任务
            from ..quest.novice_quest_service import NoviceQuestService
            quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
                session, attacker, "command", {"command": "攻击"}
            )

            if quest_completed and quest_msg:
                result_lines.append("")
                result_lines.append(quest_msg)

            await attack_cmd.finish(message_add_head("\n".join(result_lines), event))


    # 执行PVP战斗
    battle_timestamp = int(time.time() * 1000)
    seed = f"PVP_{attacker.id}_{target.id}_{battle_timestamp}"

    try:
        victory, battle_log, attacker_damage, target_damage = await BattleIntegrationHelper.enhanced_player_vs_player_battle(
            attacker, target, session, seed=seed, max_rounds=30
        )

        # 构建战斗结果消息
        if in_town:
            battle_type = "🏘️ 城镇切磋"
            battle_desc = "💡 这只是模拟切磋，不会造成任何实际损失"
        else:
            if current_region == "大都会":
                battle_type = "⚔️ 荒野死斗"
                battle_desc = "💀 这是真实的荒野死斗！"
            else:
                battle_type = "👹 诡域死斗"
                battle_desc = "💀 这是真实的诡域死斗！"

        result_lines = [
            f"{battle_type} 结果",
            "━━━━━━━━━━━━━"
        ]

        # 添加玩家信息
        attacker_realm = realm_by_level_and_reincarnation(attacker.level, attacker.reincarnation_level)
        target_realm = realm_by_level_and_reincarnation(target.level, target.reincarnation_level)

        # 战后：处理VIP装备的永久与每日加成（仅死斗生效）
        if not in_town:
            from sqlalchemy import select
            from datetime import datetime
            from ..models.vip_equipment_bonus import VIPEquipmentBonus
            def _today_key() -> str:
                return datetime.now().strftime("%Y%m%d")

            async def _apply_blade_daily_random(player: Player):
                stmt = select(ItemInstance).where(
                    ItemInstance.player_id == player.id,
                    ItemInstance.equipped == True,
                    ItemInstance.item_id == "vip_blade_zhanlongshan"
                )
                inst = (await session.execute(stmt)).scalars().first()
                if not inst:
                    return None
                extra = inst.extra_attrs or {}
                day = _today_key()
                if extra.get("blade_rand_day") == day:
                    return None
                # 首次触发：+40随机属性
                import random as _r
                attr_map = {
                    "attack": "攻击", "defense": "防御", "agility": "敏捷",
                    "luck": "幸运", "max_hp": "生命上限", "max_mp": "理智上限"
                }
                attrs = list(attr_map.keys())
                chosen = _r.choice(attrs)
                # 使用VIPEquipmentBonus表持久化，确保冥返后不会丢失
                vip_bonus = await VIPEquipmentBonus.get_or_create(session, player.id)
                vip_bonus.add_bonus(chosen, 40)
                setattr(player, chosen, getattr(player, chosen) + 40)
                extra["blade_rand_day"] = day
                inst.extra_attrs = extra
                return f"✨ 刃之魔灵：{player.nickname} 今日首战恩赐，{attr_map[chosen]}+40（永久）"

            async def _apply_blade_kill_mp(winner: Player):
                stmt = select(ItemInstance).where(
                    ItemInstance.player_id == winner.id,
                    ItemInstance.equipped == True,
                    ItemInstance.item_id == "vip_blade_zhanlongshan"
                )
                inst = (await session.execute(stmt)).scalars().first()
                if not inst:
                    return None
                extra = inst.extra_attrs or {}
                day = _today_key()
                if extra.get("blade_kill_day") != day:
                    extra["blade_kill_day"] = day
                    extra["blade_kill_cnt"] = 0
                current_cnt = int(extra.get("blade_kill_cnt", 0))
                if current_cnt >= 20:
                    return f"🩸 噬灵者：今日已达上限（{current_cnt}/20）"
                # 使用VIPEquipmentBonus表持久化，确保冥返后不会丢失
                vip_bonus = await VIPEquipmentBonus.get_or_create(session, winner.id)
                vip_bonus.add_bonus("max_mp", 2)
                # +2最大理智
                winner.max_mp = winner.max_mp + 2
                extra["blade_kill_cnt"] = current_cnt + 1
                inst.extra_attrs = extra
                return f"🩸 噬灵者：击杀吞噬，理智上限+2（今日{extra['blade_kill_cnt']}/20）"

            async def _apply_robe_self_siphon(dead_player: Player):
                stmt = select(ItemInstance).where(
                    ItemInstance.player_id == dead_player.id,
                    ItemInstance.equipped == True,
                    ItemInstance.item_id == "vip_robe_jingyuanzhiyi"
                )
                inst = (await session.execute(stmt)).scalars().first()
                if not inst:
                    return None
                extra = inst.extra_attrs or {}
                day = _today_key()
                if extra.get("robe_die_day") != day:
                    extra["robe_die_day"] = day
                    extra["robe_die_cnt"] = 0
                current_cnt = int(extra.get("robe_die_cnt", 0))
                if current_cnt >= 20:
                    return f"🪞 镜怨自噬：今日已达上限（{current_cnt}/20）"
                # 使用VIPEquipmentBonus表持久化，确保冥返后不会丢失
                vip_bonus = await VIPEquipmentBonus.get_or_create(session, dead_player.id)
                vip_bonus.add_bonus("attack", 2)
                dead_player.attack = dead_player.attack + 2
                extra["robe_die_cnt"] = current_cnt + 1
                inst.extra_attrs = extra
                return f"🪞 镜怨自噬：死亡化怨，攻击+2（今日{extra['robe_die_cnt']}/20）"

            # 每日随机属性（双方）
            msg_a = await _apply_blade_daily_random(attacker)
            if msg_a:
                result_lines.append(msg_a)
            msg_b = await _apply_blade_daily_random(target)
            if msg_b:
                result_lines.append(msg_b)

            # 击杀与自噬收益
            if victory:
                gain_msg = await _apply_blade_kill_mp(attacker)
                if gain_msg:
                    result_lines.append(gain_msg)
                # 败者死亡自噬
                robemsg = await _apply_robe_self_siphon(target)
                if robemsg:
                    result_lines.append(robemsg)
            else:
                gain_msg = await _apply_blade_kill_mp(target)
                if gain_msg:
                    result_lines.append(gain_msg)
                robemsg = await _apply_robe_self_siphon(attacker)
                if robemsg:
                    result_lines.append(robemsg)

        result_lines.extend([
            f"🔥 {attacker.nickname}[UID:{attacker.uid}] Lv.{attacker.level} {attacker_realm}",
            f"🆚 {target.nickname}[UID:{target.uid}] Lv.{target.level} {target_realm}",
            "━━━━━━━━━━━━━"
        ])

        # 显示简洁的战斗日志
        result_lines.extend(battle_log)

        result_lines.append("━━━━━━━━━━━━━")

        # 处理死斗的状态损耗和物品掉落
        if not in_town:
            # 双方都会受到战斗伤害（状态损耗）
            attacker.hp = max(0, attacker.hp - attacker_damage)
            target.hp = max(0, target.hp - target_damage)

            # 显示状态损耗信息
            damage_info = []
            if attacker_damage > 0:
                damage_info.append(f"💔 {attacker.nickname} 损失 {attacker_damage} 血量")
            if target_damage > 0:
                damage_info.append(f"💔 {target.nickname} 损失 {target_damage} 血量")

            if damage_info:
                result_lines.extend(damage_info)

            # 处理败者的物品掉落（掉落保护）
            loser = target if victory else attacker
            winner = attacker if victory else target
            now_ts = time.time()
            last_ts = _last_pvp_drop_time.get(loser.id, 0)
            drop_summary = ""
            if now_ts - last_ts < DROP_PROTECTION_SECONDS:
                result_lines.append("🛡️ 掉落保护生效：短时间内不再掉落物品")
                drop_summary = "🛡️ 掉落保护生效"
            else:
                drop_msg = await handle_wilderness_drops(session, loser, winner)
                _last_pvp_drop_time[loser.id] = now_ts
                if drop_msg:
                    result_lines.append(drop_msg)
                    # 压缩为单行摘要便于列表展示
                    drop_summary = drop_msg.replace("\n", "；")
                else:
                    drop_summary = "无掉落"

            # 记录死斗日志（仅非城镇）
            try:
                bt_simple = "诡域" if "诡域" in battle_type else "荒野"
                log = PvpLog(
                    ts=int(time.time()),
                    region=current_region,
                    x=attacker_x,
                    y=attacker_y,
                    attacker_id=attacker.id,
                    defender_id=target.id,
                    attacker_uid=attacker.uid,
                    defender_uid=target.uid,
                    attacker_name=attacker.nickname,
                    defender_name=target.nickname,
                    battle_type=bt_simple,
                    attacker_victory=1 if victory else 0,
                    attacker_damage=attacker_damage,
                    defender_damage=target_damage,
                    drop_summary=drop_summary,
                )
                session.add(log)
            except (ValueError, SQLAlchemyError):
                # 忽略日志记录/表未创建等问题，不影响战斗流程
                pass

        result_lines.append(battle_desc)

        await session.commit()

        # 战斗胜利后更新成就统计
        if victory:
            from ..achievement.achievement_service import AchievementService
            await AchievementService.update_stat(session, attacker.id, "total_battles", auto_commit=False)
            await AchievementService.update_stat(session, attacker.id, "total_wins", auto_commit=False)
            await AchievementService.update_stat(session, attacker.id, "total_kills", auto_commit=True)
        else:
            from ..achievement.achievement_service import AchievementService
            await AchievementService.update_stat(session, attacker.id, "total_battles", auto_commit=True)

        # 检查新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, attacker, "command", {"command": "攻击"}
        )

        if quest_completed and quest_msg:
            result_lines.append("")
            result_lines.append(quest_msg)

        # 检查成就
        from ..achievement.achievement_service import AchievementService
        achievement_msgs = await AchievementService.check_achievements(session, attacker)
        if achievement_msgs:
            result_lines.append("")
            result_lines.extend(achievement_msgs)

        await attack_cmd.finish(message_add_head("\n".join(result_lines), event))

    except ValueError as e:
        await attack_cmd.finish(f"⛔ 战斗系统错误：{str(e)}")


async def handle_npc_attack(session, attacker: Player, target_npc, event: MessageEvent):
    """处理玩家vs NPC攻击"""
    # 检查是否为活动鬼怪（个人事件模式：鬼怪不会真正死亡，每人只能打一次）
    from ..event.knocker_event import KnockerEventService
    is_knocker = KnockerEventService.is_knocker_npc(target_npc)

    if is_knocker:
        # 活动鬼怪：检查玩家是否已击杀过
        extra = target_npc.extra_data or {}
        knocker_event_id = extra.get("knocker_event_id", "")
        if KnockerEventService.has_player_killed(attacker, knocker_event_id):
            await attack_cmd.finish(f"⛔ 你已经解决过{target_npc.name}了，去寻找其他诡事点吧！")
    else:
        # 非活动鬼怪：检查NPC状态
        if target_npc.is_dead():
            await attack_cmd.finish(f"⛔ {target_npc.name}已经死亡")

        if target_npc.is_respawning():
            remaining = target_npc.respawn_time - target_npc.death_time
            minutes = int(remaining.total_seconds() / 60)
            await attack_cmd.finish(f"⛔ {target_npc.name}正在复活中，还需{minutes}分钟")

    # 检查是否可以攻击
    if not target_npc.is_killable and target_npc.npc_type != NPCType.GHOST:
        await attack_cmd.finish(f"⛔ {target_npc.name}是友善的NPC，无法攻击")

    # 构建NPC战斗属性
    npc_stats = {
        "hp": target_npc.hp,
        "attack": target_npc.attack,
        "defense": target_npc.defense,
        "agility": target_npc.agility
    }

    # 执行战斗
    battle_timestamp = int(time.time() * 1000)
    seed = f"NPC_{attacker.id}_{target_npc.npc_id}_{battle_timestamp}"

    try:
        victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
            attacker, npc_stats, target_npc.name, session, seed=seed, max_rounds=50
        )

        # 更新玩家血量
        attacker.hp = max(0, attacker.hp - damage_taken)

        # 构建战斗结果
        result_lines = [
            f"⚔️ {attacker.nickname} VS {target_npc.name}",
            "━━━━━━━━━━━━━"
        ]

        # 展示战斗过程，方便玩家了解每一回合的战况
        result_lines.extend(battle_log)

        result_lines.append("━━━━━━━━━━━━━")

        if victory:
            # 玩家胜利，NPC死亡
            if target_npc.is_killable:
                # 活动鬼怪不真正死亡（个人事件模式：其他玩家仍可攻击）
                if not is_knocker:
                    target_npc.kill()
                result_lines.append(f"💀 {target_npc.name}被击杀")
                if not is_knocker and target_npc.respawn_duration_minutes > 0:
                    result_lines.append(f"⏰ {target_npc.respawn_duration_minutes}分钟后复活")

            # 鬼怪特殊奖励
            if target_npc.npc_type == NPCType.GHOST:
                # 先检查是否为活动鬼怪
                if is_knocker:
                    # 活动鬼怪: 使用活动奖励系统
                    knocker_lines = await KnockerEventService.on_ghost_killed(
                        session, attacker, target_npc
                    )
                    if knocker_lines:
                        result_lines.extend(knocker_lines)

                    # 检查是否为Boss级, 生成全服播报
                    boss_broadcast = KnockerEventService.get_boss_kill_broadcast(
                        attacker, target_npc
                    )
                    if boss_broadcast:
                        result_lines.append("")
                        result_lines.append(boss_broadcast)
                        # 发送系统消息到留言板（全服播报）
                        await KnockerEventService._send_system_message(session, boss_broadcast)
                else:
                    # 普通鬼怪: 原有奖励逻辑
                    exp_gain = target_npc.level * 10
                    gold_gain = target_npc.level * 5
                    attacker.exp += exp_gain
                    attacker.gold += gold_gain
                    result_lines.append(f"🎉 击杀鬼怪获得 {exp_gain} EXP，{gold_gain} 金币")
            # 结算VIP定制装备（斩龙闪）的战后永久加成（如“噬灵者”）
            if victory and post_effects:
                from sqlalchemy import select as _select
                from ..models.inventory import ItemInstance as _ItemInstance
                from ..models.vip_equipment_bonus import VIPEquipmentBonus as _VIPBonus
                from datetime import datetime as _dt

                def _today_key() -> str:
                    return _dt.now().strftime("%Y%m%d")

                # 仅处理已穿戴的斩龙闪
                stmt = _select(_ItemInstance).where(
                    _ItemInstance.player_id == attacker.id,
                    _ItemInstance.equipped == True,
                    _ItemInstance.item_id == "vip_blade_zhanlongshan",
                )
                inst = (await session.execute(stmt)).scalars().first()
                if inst:
                    extra = dict(inst.extra_attrs or {})
                    vip_bonus = await _VIPBonus.get_or_create(session, attacker.id)
                    day = _today_key()

                    cn_map = {
                        "attack": "攻击",
                        "defense": "防御",
                        "agility": "敏捷",
                        "luck": "幸运",
                        "max_hp": "生命上限",
                        "max_mp": "理智上限",
                    }

                    for eff in post_effects:
                        et = eff.get("type")
                        if et == "gain_random_attr":
                            if extra.get("blade_rand_day") != day:
                                attr = eff.get("attr")
                                val = int(eff.get("value", 0) or 0)
                                vip_bonus.add_bonus(attr, val)
                                setattr(attacker, attr, getattr(attacker, attr) + val)
                                extra["blade_rand_day"] = day
                                result_lines.append(f"✨ 刃之魔灵：今日首战恩赐，{cn_map.get(attr, attr)}+{val}（永久）")
                        elif et == "gain_max_hp":
                            # 击杀永久+2属性点（每日最多20次），1属性点=3生命值，所以实际+6生命值
                            if extra.get("blade_kill_day") != day:
                                extra["blade_kill_day"] = day
                                extra["blade_kill_cnt"] = 0
                            cnt = int(extra.get("blade_kill_cnt", 0))
                            if cnt < 20:
                                attr_points = int(eff.get("value", 0) or 0)
                                actual_hp = attr_points * 3
                                vip_bonus.add_bonus("max_hp", actual_hp)
                                attacker.max_hp = attacker.max_hp + actual_hp
                                extra["blade_kill_cnt"] = cnt + 1
                                result_lines.append(
                                    f"🩸 噬灵者：击杀吞噬，生命上限+{actual_hp}（今日{extra['blade_kill_cnt']}/20）"
                                )

                    inst.extra_attrs = extra
                    session.add(inst)
                    session.add(attacker)

        else:
            # 玩家失败
            if attacker.hp <= 0:
                result_lines.append("💀 你被击败了")
            else:
                result_lines.append("⏰ 战斗超时，平局")

        await session.commit()

        # 战斗胜利后更新成就统计
        if victory:
            from ..achievement.achievement_service import AchievementService
            await AchievementService.update_stat(session, attacker.id, "total_battles", auto_commit=False)
            await AchievementService.update_stat(session, attacker.id, "total_wins", auto_commit=False)
            await AchievementService.update_stat(session, attacker.id, "total_kills", auto_commit=True)
        else:
            from ..achievement.achievement_service import AchievementService
            await AchievementService.update_stat(session, attacker.id, "total_battles", auto_commit=True)

        # 检查新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, attacker, "command", {"command": "攻击"}
        )

        if quest_completed and quest_msg:
            result_lines.append("")
            result_lines.append(quest_msg)

        # 检查成就
        from ..achievement.achievement_service import AchievementService
        achievement_msgs = await AchievementService.check_achievements(session, attacker)
        if achievement_msgs:
            result_lines.append("")
            result_lines.extend(achievement_msgs)

        await attack_cmd.finish(message_add_head("\n".join(result_lines), event))

    except ValueError as e:
        await attack_cmd.finish(f"⛔ 战斗系统错误：{str(e)}")


# ==================== 击杀统计命令 ====================
kill_stats_cmd = on_command("击杀统计", aliases={"战斗统计"}, block=True, priority=5)


@kill_stats_cmd.handle()
async def handle_kill_stats(event: MessageEvent):
    """显示击杀统计"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await kill_stats_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await kill_stats_cmd.finish("⛔ 请先创建角色")

        # 这里可以添加击杀统计的逻辑
        # 目前先显示基本信息
        lines = [
            f"⚔️ {player.nickname} 的战斗统计",
            "━━━━━━━━━━━━━",
            f"👤 玩家：{player.nickname} [UID:{player.uid}]",
            f"⚡ 等级：{player.level}",
            f"❤️ 血量：{player.hp}/{player.max_hp}",
            f"⚔️ 攻击：{player.attack}",
            f"🛡️ 防御：{player.defense}",
            f"💨 敏捷：{player.agility}",
            "",
            "📊 战斗记录：",
            "• 击杀鬼怪：暂未统计",
            "• PVP切磋：暂未统计",
            "• 战斗胜率：暂未统计",
            "",
            "💡 提示：击杀统计功能正在开发中"
        ]

        await kill_stats_cmd.finish(message_add_head("\n".join(lines), event))

# ==================== 死斗日志查看 ====================
pvp_log_cmd = on_command("死斗日志", aliases={"PVP日志", "战斗日志"}, block=True, priority=5)


@pvp_log_cmd.handle()
async def handle_pvp_log(event: MessageEvent, args: Message = CommandArg()):
    """查看个人死斗日志（包含被袭击与主动进攻）"""
    async with safe_session() as session:
        # 获取玩家
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await pvp_log_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await pvp_log_cmd.finish("⛔ 请先创建角色")

        # 解析页码
        text = args.extract_plain_text().strip()
        page = 1
        if text.isdigit() and int(text) >= 1:
            page = int(text)
        page_size = 5
        offset = (page - 1) * page_size

        from sqlalchemy import select, or_, desc
        stmt = (
            select(PvpLog)
            .where(or_(PvpLog.attacker_uid == player.uid, PvpLog.defender_uid == player.uid))
            .order_by(desc(PvpLog.ts))
            .offset(offset)
            .limit(page_size)
        )
        logs = (await session.execute(stmt)).scalars().all()

        if not logs:
            await pvp_log_cmd.finish(
                message_add_head("📜 死斗日志\n━━━━━━━━━━━━━\n暂无记录\n💡 使用【攻击】进行荒野/诡域死斗，或当被袭击后查看此处", event)
            )

        import time as _t
        lines = [f"📜 死斗日志 第{page}页", "━━━━━━━━━━━━━"]
        for rec in logs:
            ts_str = _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(rec.ts))
            you_are_attacker = rec.attacker_uid == player.uid
            if you_are_attacker:
                role_tag = "🟩 你进攻"
                opponent = f"{rec.defender_name}[UID:{rec.defender_uid}]"
                result = "你 胜" if rec.attacker_victory == 1 else "你 败"
                dmg = f"你-{rec.attacker_damage}HP 对方-{rec.defender_damage}HP"
            else:
                role_tag = "🟥 被袭击"
                opponent = f"{rec.attacker_name}[UID:{rec.attacker_uid}]"
                result = "你 败" if rec.attacker_victory == 1 else "你 胜"
                dmg = f"你-{rec.defender_damage}HP 对方-{rec.attacker_damage}HP"

            where = f"{rec.battle_type} {rec.region} ({rec.x},{rec.y})"
            drop = rec.drop_summary or "无掉落"
            lines.extend([
                f"{role_tag} | {ts_str} | {where}",
                f"对手：{opponent}",
                f"结果：{result}  •  伤害：{dmg}",
                f"掉落：{drop}",
                "━━━━━━━━━━━━━",
            ])

        await pvp_log_cmd.finish(message_add_head("\n".join(lines), event))

