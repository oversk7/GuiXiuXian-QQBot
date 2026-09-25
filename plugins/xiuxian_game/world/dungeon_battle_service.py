from __future__ import annotations

"""诡域战斗服务
探索事件处理、战斗结算、装备耐久检查、俯瞰图渲染（纯业务逻辑）
"""

import asyncio
import io
import random
from datetime import datetime, date, timedelta

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select, and_

from ..config import config
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.world_tile import WorldTile
from ..utils import luck_prob
from ..utils_markdown import cmd
from ..item.equipment_service import recalc_equipment_attributes
from ..item.vip_battle_growth_service import settle_pve_victory, settle_dungeon_defeat
from ..battle.battle_log_filter import filter_battle_log, get_player_log_mode
from .dungeon_generation_service import handle_monster_drops

# Feature Flag（在文件顶部靠近其他导入的位置）
async def check_equipment_durability(session, player_id: str) -> str:
    """检查玩家装备耐久度，如果有装备耐久度低于10，返回提醒消息"""
    # 查询玩家所有已装备的装备
    result_eq = await session.execute(
        select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
        )
    )
    equipped_items = result_eq.scalars().all()

    low_durability_items = []
    for eq in equipped_items:
        if eq.durability < 10:
            low_durability_items.append(f"{eq.config.name}(ID:{eq.id}, 耐久:{eq.durability}/{eq.config.durability})")

    if low_durability_items:
        warning_msg = "⚠️ 装备耐久度警告！以下装备耐久度过低，建议及时修理：\n"
        warning_msg += "\n".join([f"🔧 {item}" for item in low_durability_items])
        warning_msg += "\n💡 使用【修理 装备ID/名称】命令进行修理"
        return warning_msg

    return ""


# 诡域坐标边界 (-5,-5) 到 (5,5)
_DUNGEON_MIN = -5
_DUNGEON_MAX = 5


class BattleResult:
    """诡域战斗结果。log_lines 是过程日志（bash 代码块内），result_lines 是战果行（代码块外前置展示）。"""

    __slots__ = ("log_lines", "victory", "monster_display", "result_lines")

    def __init__(self, log_lines: list[str], victory: bool, monster_display: str,
                 result_lines: list[str] | None = None):
        self.log_lines = log_lines
        self.victory = victory
        self.monster_display = monster_display
        self.result_lines = result_lines if result_lines is not None else []


async def _query_explored_coords(session, region: str, server_id: int = 1) -> set[tuple[int, int]]:
    """查询当前诡域 region 今天已生成的所有格子坐标（视为已探索）。"""
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    stmt = select(WorldTile.x, WorldTile.y).where(
        and_(
            WorldTile.region == region,
            WorldTile.server_id == server_id,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start,
        )
    )
    rows = (await session.execute(stmt)).all()
    return {(r[0], r[1]) for r in rows}


def _build_dungeon_minimap(
    x: int,
    y: int,
    explored: set[tuple[int, int]],
    radius: int = 2,
) -> str:
    """生成以 (x,y) 为中心的诡域小地图（默认 5x5）。

    🟨 你、🟩 今日已探索、⬜ 未探索、⬛ 边界
    """
    rows = []
    # 北(y+) 在上，南(y-) 在下
    for dy in range(radius, -radius - 1, -1):
        cy = y + dy
        cells = []
        for dx in range(-radius, radius + 1):
            cx = x + dx
            if cx < _DUNGEON_MIN or cx > _DUNGEON_MAX or cy < _DUNGEON_MIN or cy > _DUNGEON_MAX:
                cells.append("⬛")
            elif cx == x and cy == y:
                cells.append("🟨")
            elif (cx, cy) in explored:
                cells.append("🟩")
            else:
                cells.append("⬜")
        rows.append("".join(cells))
    return "\n".join(rows)


# ==================== 格子描述（移动/传送/换层共用单一来源） ====================

def _format_special_attrs(state: dict) -> str:
    """格式化诡异特殊属性提示（200级+才有这些字段），无则返回空串。"""
    attrs = []
    if state.get("crit_rate", 0) > 0:
        attrs.append(f"💥暴击{state['crit_rate']:.1f}%")
    if state.get("combo_rate", 0) > 0:
        attrs.append(f"🔄连击{state['combo_rate']:.1f}%")
    if state.get("counter_rate", 0) > 0:
        attrs.append(f"⚡反击{state['counter_rate']:.1f}%")
    if state.get("anti_crit_rate", 0) > 0:
        attrs.append(f"🛡️抗暴{state['anti_crit_rate']:.1f}%")
    if state.get("defense", 0) > 0:
        attrs.append(f"🪨防{state['defense']}")
    if state.get("true_damage_rate", 0) > 0:
        attrs.append(f"🗡️真伤{state['true_damage_rate']:.1f}%")
    return f"\n🔥 特殊能力：{' '.join(attrs)}" if attrs else ""


# 文案池：怪谈亲历口吻，第二人称现在时。同一格子当天文案固定（按 tile.seed 确定性选取）。
# 深层（30重+）的诡异/精英切换更癫狂的池子。
_DESC_MATERIAL = [
    "✨ 墙角堆着 {name} ✖️{qty}，摆得太整齐了，像是特意留给你的。\n⬇️ 【收集】 拿走它",
    "✨ 你踩到了什么——{name} ✖️{qty} 散落在脚边，上面还带着体温。\n⬇️ 【收集】 拿走它",
    "✨ 有人在这里留下了 {name} ✖️{qty}。你环顾四周。没有人，从来没有人。\n⬇️ 【收集】 拿走它",
]
_DESC_MATERIAL_LOOTED = [
    "🪨 这里曾经放着 {name}，现在只剩拖拽的痕迹。是你拿走的，你记得吗？",
    "🪨 空了。地上的压痕说明这里放过东西——它现在在你的包里。",
    "🪨 你又路过这个角落。材料已经被搜刮一空，起码在你的视角是这样。",
]
_DESC_TREASURE = [
    "🎁 一尊龟裂的神像立在前方，腹部的暗格微微鼓起。里面有东西在等你。\n⬇️ 【探索】 撬开它",
    "🎁 墙里嵌着一个尘封的匣子，灰尘上有新鲜的指印——不是你的。\n⬇️ 【探索】 打开它",
    "🎁 神像缺了一只眼睛，另一只正看着你。它的暗格没有上锁。\n⬇️ 【探索】 掏出里面的东西",
]
_DESC_TREASURE_LOOTED = [
    "🪨 神像的暗格已被掏空，徒留潮湿指印。",
    "🪨 破碎的匣子躺在尘埃里。你来晚了——或者说，你已经来过了。",
]
_DESC_MONSTER_SHALLOW = [
    "🌫️ 空间扭曲中传来异响，{monster} 在附近游荡，它还没发现你。",
    "🌫️ 雾里传来脚步声，和你的步频一模一样，只是慢半拍。是 {monster}。",
    "🌫️ 前方立着一个影子。它不动。你走近一步，它清晰一分——{monster}。",
]
_DESC_MONSTER_DEEP = [
    "🌫️ 这里的墙在轻轻起伏，像在呼吸。{monster} 贴在暗处，用你熟人的声音喊你的名字。",
    "🌫️ 你低头数自己的影子，多了一条。多出来的那条属于 {monster}。",
    "🌫️ {monster} 早就看见你了。从你踏进这一重开始，它就跟在你身后。",
]
_DESC_MONSTER_DEFEATED = [
    "🪨 这里只剩下诡异的残骸，散发着淡淡的血腥味。",
    "🪨 残骸还保持着死前的姿势。你绕开它，它空洞的眼窝跟着你转。",
    "🪨 你杀过它了。地上的痕迹提醒你，这件事确实发生过。",
]
_DESC_REST = [
    "🏮 雾里亮着一盏灯。一家驿站，门开着，柜台后没有人，但床铺是暖的。\n⬇️ 【探索】 睡一觉，恢复生命",
    "🏮 你看见一家驿站。在这种地方开门做生意的东西，至少今晚对你没有恶意。\n⬇️ 【探索】 住下，恢复生命",
]
_DESC_MERCHANT = [
    "🏪 摊位上点着一盏绿灯。卖货郎冲你笑，牙齿很整齐，数量不太对。\n⬇️ 【探索】 看看他的货",
    "🏪 神秘卖货郎坐在摊后。你始终没看清他的脸，但他显然认得你。\n⬇️ 【探索】 上前交谈",
]
_DESC_MERCHANT_GONE = [
    "🏪 卖货郎走了，摊位还在。灰尘的厚度像是隔了十年。",
    "🏪 空荡荡的摊位，地上留着一枚不属于任何年代的铜钱。",
]
_DESC_ELITE_SHALLOW = [
    "⚔️ 空气凝住了。{monster}——这重诡域的主人——正从高处俯视你，它等你很久了。",
    "⚔️ 雾向四周退去，{monster} 立在正中央。这一重归它管。",
]
_DESC_ELITE_DEEP = [
    "⚔️ 所有声音同时停了。{monster} 从你的影子里缓缓站起来，这一重的规则由它书写。",
    "⚔️ 你意识到刚才路过的每一双眼睛都是它的。{monster} 不再躲了。",
]
_DESC_ELITE_DEFEATED = [
    "⚰️ 精英诡异的残骸散落一地。这一重安静下来了——安静得不太自然。",
    "⚰️ 它的残骸还冒着黑烟。你赢了，但总觉得有什么东西记住了你。",
]


# 每10重一个 tier 主题：进层时的氛围引子（纯文案，不影响数值）
_TIER_THEMES = {
    1: ("湿雾巷", "雾贴着地面爬，像是有什么在雾里匍匐前进。"),
    2: ("回音病房", "走廊尽头传来仪器的滴答声。这里早就停电了。"),
    3: ("倒悬钟楼", "钟摆在你头顶晃，每一下都比上一下更近。"),
    4: ("无人婚宴", "长桌上的喜宴还冒着热气，所有椅子都朝向你。"),
    5: ("腐潮码头", "潮水退下去的时候，带走了一些本该留下的东西。"),
    6: ("剥皮画廊", "画框里的肖像都缺了脸。颜料还是湿的。"),
    7: ("蛀空图书馆", "四面八方都是翻书声，但没有一本书是打开的。"),
    8: ("锈血机房", "机器还在运转。润滑它们的不是机油。"),
    9: ("失名墓园", "每块墓碑都刻着同一个名字。你越看越觉得眼熟。"),
    10: ("终渊", "这里的黑暗有重量。它记得每一个来过的人。"),
}


def get_tier_theme(level: int) -> tuple[str, str]:
    """按诡域深度返回 (主题名, 氛围引子)，每10重一换，100重后沿用终渊。"""
    tier = min(10, (level - 1) // 10 + 1)
    return _TIER_THEMES[tier]


def describe_tile(tile: WorldTile, player: Player) -> str:
    """根据格子类型生成描述，是移动/传送/换层三处共用的单一文案来源。"""
    state = tile.state or {}
    rng = random.Random(f"desc:{tile.seed}:{tile.event_type}")
    deep = (player.dungeon_level or 0) >= 30

    if tile.event_type == "MATERIAL":
        item_cfg = config.items_config["by_id"].get(state.get("item_id"))
        item_name = item_cfg.get_display_name() if item_cfg else "未知材料"
        qty = state.get("quantity", "?")
        if player.id in state.get("looted_by", []) or state.get("looted"):
            return rng.choice(_DESC_MATERIAL_LOOTED).format(name=item_name)
        return rng.choice(_DESC_MATERIAL).format(name=item_name, qty=qty)

    elif tile.event_type == "TREASURE":
        if state.get("looted"):
            return rng.choice(_DESC_TREASURE_LOOTED)
        return rng.choice(_DESC_TREASURE)

    elif tile.event_type == "EMPTY":
        if player.id in state.get("defeated_by", []):
            return rng.choice(_DESC_MONSTER_DEFEATED)
        monster = f"{state.get('name')}(Lv{state.get('level', 1)})"
        pool = _DESC_MONSTER_DEEP if deep else _DESC_MONSTER_SHALLOW
        return f"{rng.choice(pool).format(monster=monster)}{_format_special_attrs(state)}\n⬇️ 【探索】 主动出击"

    elif tile.event_type == "REST":
        return rng.choice(_DESC_REST)

    elif tile.event_type == "MERCHANT":
        if player.id in state.get("visited_by", []):
            return rng.choice(_DESC_MERCHANT_GONE)
        return rng.choice(_DESC_MERCHANT)

    elif tile.event_type == "ELITE":
        if player.id in state.get("defeated_by", []):
            return rng.choice(_DESC_ELITE_DEFEATED)
        monster = f"{state.get('name', '精英诡异')}(Lv{state.get('level', 1)})"
        pool = _DESC_ELITE_DEEP if deep else _DESC_ELITE_SHALLOW
        return f"{rng.choice(pool).format(monster=monster)}{_format_special_attrs(state)}\n⬇️ 【探索】 迎战"

    return "🌫️ 这里空无一物，只有你自己的回声。"


# 事件处理器映射
async def _handle_material(session, tile: WorldTile, player: Player) -> str:
    # 个人事件：仅当当前玩家已拾取时才视为已搜刮
    if player.id in tile.state.get("looted_by", []) or tile.state.get("looted"):
        return "🪨 这的材料已经被拿了，起码在你的视角是这样。"

    # 获取物品配置
    item_id = tile.state.get("item_id")
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return "⚠️ 错误：未知的物品。"

    quantity = tile.state.get("quantity", 1)

    # Luck: 采集加成判定
    luck_bonus = 0
    if random.random() < luck_prob(player.luck):
        luck_bonus = quantity  # 翻倍
        quantity *= 2

    # 更新或创建物品记录
    try:
        await ItemInstance.add_item(session, player.id, item_id, quantity)
    except ValueError as e:
        return f"⚠️ 错误：{e}"

    # 标记为已拾取（个人事件）
    tile.state.setdefault("looted_by", []).append(player.id)
    session.add(tile)
    await session.flush()

    base_msg = f"✨ 你采集到了 {item_cfg.get_display_name()} ✖️{quantity}!"
    if luck_bonus:
        base_msg += "\n🍀 幸运闪现！材料翻倍。"
    base_msg += "\n⬇️ 【图鉴 物品名】 查看描述"
    return base_msg


async def _handle_treasure(session, tile: WorldTile, player: Player) -> str:
    if tile.state.get("looted"):
        return "🪨 雕塑的暗格已被掏空，徒留潮湿指印。"
    # 添加时间戳确保每次开启宝箱都有不同的奖励
    import time
    treasure_timestamp = int(time.time() * 1000)
    rng = random.Random(hash(f"{tile.seed}:{player.id}:{treasure_timestamp}"))
    base_gold = rng.randint(2000, 8000)
    from ..utils import luck_prob
    multiplier = 1 + luck_prob(player.luck)  # 1~2 倍区间
    gold_gain = int(base_gold * multiplier)
    player.gold += gold_gain
    # 更新财富成就统计
    from ..achievement.achievement_service import AchievementService
    await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=gold_gain, auto_commit=False)
    tile.state["looted"] = True
    session.add_all([player, tile])
    await session.flush()
    msg = f"🔑 你在龟裂神像内抠出 {base_gold}💰！"
    if multiplier > 1.01:
        msg += f"\n🍀幸运改写中...金币变为{gold_gain}！"
    # 极低概率掉落稀有诡兽（0.5%，鼓励手动探索）
    if rng.random() < 0.005:
        beast_id = rng.choice(["guardian_void_serpent", "guardian_nightmare_wolf"])
        try:
            await ItemInstance.add_item(session, player.id, beast_id, 1)
            beast_cfg = config.items_config["by_id"].get(beast_id)
            if beast_cfg:
                msg += f"\n\n🎊 奇迹降临！宝箱深处竟藏着一只【{beast_cfg.name}】！"
                msg += f"\n✨ {beast_cfg.description}"
                msg += f"\n⚠️ 此诡兽极为罕见，请妥善保管！"
        except ValueError:
            pass
    # 低概率掉落诡兽精魄（与图鉴共用独立奖励定义）
    from .dungeon_generation_service import TREASURE_MATERIAL_ITEM_ID, TREASURE_MATERIAL_CHANCE
    if rng.random() < TREASURE_MATERIAL_CHANCE:
        try:
            await ItemInstance.add_item(session, player.id, TREASURE_MATERIAL_ITEM_ID, 1)
            msg += "\n\n✨ 宝箱角落闪烁着幽光...你获得了【诡兽精魄】×1！"
        except ValueError:
            pass
    return msg


async def _handle_empty(session, tile: WorldTile, player: Player):
    # 检查玩家是否已经击败过这个小怪
    if player.id in tile.state.get("defeated_by", []):
        return "🪨 这里只剩下诡异的残骸，散发着淡淡的血腥味。"
    # empty格有遇到个人的诡异，但不会影响公共事件
    return await _handle_personal_monster(session, tile, player)


async def _handle_personal_monster(session, tile: WorldTile, player: Player) -> "BattleResult":
    """诡异属于个人事件，使用新战斗系统进行战斗。"""
    # 获取诡异信息
    monster_stats = {
        "hp": tile.state.get("hp", 0),
        "attack": tile.state.get("attack", 0),
        "agility": tile.state.get("agility", 0),
        "defense": tile.state.get("defense", 0),
    }

    # 为200级以后的诡异添加特殊属性
    monster_level = tile.state.get("level", 1)
    if monster_level >= 200:
        monster_stats.update({
            "crit_rate": tile.state.get("crit_rate", 0),
            "combo_rate": tile.state.get("combo_rate", 0),
            "counter_rate": tile.state.get("counter_rate", 0),
            "anti_crit_rate": tile.state.get("anti_crit_rate", 0),
            "true_damage_rate": tile.state.get("true_damage_rate", 0),
            "accuracy_rate": tile.state.get("accuracy_rate", 80),
        })

    monster_name = tile.state.get("name", "未知诡影")
    monster_base_display = f"{monster_name}(Lv{monster_level})"
    monster_full_display = monster_base_display

    # 为200级以后的诡异显示特殊属性信息
    if monster_level >= 200:
        special_attrs = []
        if monster_stats.get("crit_rate", 0) > 0:
            special_attrs.append(f"💥{monster_stats['crit_rate']:.1f}%")
        if monster_stats.get("combo_rate", 0) > 0:
            special_attrs.append(f"🔄{monster_stats['combo_rate']:.1f}%")
        if monster_stats.get("counter_rate", 0) > 0:
            special_attrs.append(f"⚡{monster_stats['counter_rate']:.1f}%")
        if monster_stats.get("anti_crit_rate", 0) > 0:
            special_attrs.append(f"🛡️{monster_stats['anti_crit_rate']:.1f}%")
        if monster_stats.get("defense", 0) > 0:
            special_attrs.append(f"🪨防{monster_stats['defense']}")
        if monster_stats.get("true_damage_rate", 0) > 0:
            special_attrs.append(f"🗡️真伤{monster_stats['true_damage_rate']:.1f}%")

        if special_attrs:
            monster_full_display += f" [{' '.join(special_attrs)}]"

    # 使用新战斗系统
    from ..battle.integration_helper import BattleIntegrationHelper

    # 创建战斗种子 - 添加时间戳确保每次战斗都有不同的随机序列
    import time
    battle_timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    seed = f"P_{tile.seed}:{player.id}:{battle_timestamp}"

    # 执行增强战斗V2 - 支持装备特殊效果
    victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
        player, monster_stats, monster_base_display, session, seed=seed, max_rounds=100,
        monster_full_display=monster_full_display
    )

    # 更新玩家血量
    player.hp = max(0, player.hp - damage_taken)

    # 根据玩家偏好过滤战斗日志；战果行单独收集，卡片上前置展示（不进代码块）
    dungeon_log_mode = get_player_log_mode(player)
    battle_summary = filter_battle_log(battle_log, dungeon_log_mode)
    result_lines: list[str] = []

    # 处理战斗结果
    if victory:
        # 胜利处理 - 使用新的时间戳确保每次掉落都不同
        import random
        drop_timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        rng = random.Random(hash(f"P_{tile.seed}:{player.id}:{drop_timestamp}"))
        exp_gain = rng.randint(1, 4) * monster_level
        player.exp += exp_gain
        result_lines.append(f"🎉 获得 **{exp_gain}** EXP")

        # 诡异掉落材料机制
        is_elite = tile.state.get("is_elite", False)
        drop_result = await handle_monster_drops(
            session, player, monster_level, player.region, rng, is_elite
        )
        if drop_result:
            result_lines.append(drop_result)

        # 无伤连杀：每满5杀返还少量理智（受伤清零，死亡清零，返回现实清零）
        if damage_taken > 0:
            if (player.dungeon_kill_streak or 0) > 0:
                result_lines.append(f"🕯️ 你受了伤，无伤连杀在第 {player.dungeon_kill_streak} 杀戛然而止。")
            player.dungeon_kill_streak = 0
        else:
            player.dungeon_kill_streak = (player.dungeon_kill_streak or 0) + 1
        streak = player.dungeon_kill_streak
        if streak > 0 and streak % 5 == 0:
            _lvl_cfg = config.map_config.get("dungeon_levels", {}).get(player.dungeon_level)
            if not _lvl_cfg:
                _lvl_cfg = config._generate_dungeon_level_config(
                    player.dungeon_level, config.map_config.get("dungeon_generation_rules", {})
                )
            before_mp = player.mp
            player.mp = min(player.max_mp, player.mp + _lvl_cfg.get("mp_cost", 1) * 2)
            mp_gained = player.mp - before_mp
            if mp_gained > 0:
                result_lines.append(f"🔥 无伤连杀 {streak}：恐惧反哺神智，理智+{mp_gained}")
            else:
                result_lines.append(f"🔥 无伤连杀 {streak}")

        # 更新战斗胜利统计（用于公会任务）
        if player.guild_id:
            from ..guild.guild_task_service import GuildTaskService
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
            from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
            from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            task_service = GuildTaskService(
                player_repo=PlayerRepository(session),
                guild_repo=GuildRepository(session),
                player_task_stats_repo=PlayerTaskStatsRepository(session),
                guild_task_record_repo=GuildTaskRecordRepository(session),
                player_donation_log_repo=PlayerDonationLogRepository(session),
                guild_building_repo=GuildBuildingRepository(session),
            )
            await task_service.update_combat_victory_stats(player.id)

        # 更新成就统计（诡域战斗胜利）
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "total_battles", auto_commit=False)
        await AchievementService.update_stat(session, player.id, "total_wins", auto_commit=False)
        await AchievementService.update_stat(session, player.id, "total_kills", auto_commit=False)

        # 检查并解锁成就
        achievement_msgs = await AchievementService.check_achievements(session, player)
        if achievement_msgs:
            result_lines.extend([""] + achievement_msgs)

        result_lines.extend(await settle_pve_victory(session, player, post_effects))

        # 标记为已击败（玩家胜利后）
        tile.state.setdefault("defeated_by", []).append(player.id)

        # 爬塔系统：击败诡异后解锁下一层
        if player.is_in_dungeon():
            old_max_level = player.max_dungeon_level or 0
            player.unlock_next_dungeon_level()
            new_max_level = player.max_dungeon_level or 0

            # 如果解锁了新的诡域，给予提示
            if new_max_level > old_max_level:
                result_lines.append(f"🎉 恭喜！解锁了第{new_max_level + 1}重诡域")
                result_lines.append(f"🔓 现在可以探索更深层的诡域了！")

                # 检查是否可以领取深渊探索者宝箱
                if new_max_level % 10 == 0:
                    from ..models.dungeon_chest_record import DungeonChestRecord

                    stmt = select(DungeonChestRecord).where(
                        DungeonChestRecord.player_id == player.id,
                        DungeonChestRecord.dungeon_level == new_max_level
                    )
                    existing_record = (await session.execute(stmt)).scalar_one_or_none()

                    if not existing_record:
                        result_lines.append("***")
                        result_lines.append("🎁 恭喜！你可以领取深渊探索者宝箱了！")
                        result_lines.append(f"💎 {cmd('领取宝箱')} 一键领取所有可领取的宝箱")

    else:
        result_lines.extend(await settle_dungeon_defeat(session, player))

        if player.hp <= 0:
            result_lines.append(f"💀 你被 {monster_full_display} 击败，很遗憾，你已死亡")
            if (player.dungeon_kill_streak or 0) > 0:
                result_lines.append(f"🕯️ 无伤连杀在第 {player.dungeon_kill_streak} 杀戛然而止。")
                player.dungeon_kill_streak = 0

    # ---------------- 扣除装备耐久 ----------------
    result_eq = await session.execute(
        select(ItemInstance).where(
            ItemInstance.player_id == player.id, ItemInstance.equipped == True,
            ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
        )
    )
    equipped_items = result_eq.scalars().all()
    broken_msgs = []
    hp_loss_from_equipment = 0  # 记录因装备损坏导致的HP损失
    mp_loss_from_equipment = 0  # 记录因装备损坏导致的MP损失

    for eq in equipped_items:
        if eq.lose_durability(1):
            # 耐久耗尽：自动卸下且不可穿戴，保留物品
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - v))
            # 清除 _persist_bonus，防止修复后重穿时 recalc 重复扣减属性
            if "_persist_bonus" in (eq.extra_attrs or {}):
                eq.extra_attrs = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
            eq.equipped = False
            broken_msgs.append(
                f"***\n"
                f"💔 **{eq.config.name}** 耐久耗尽已自动卸下\n"
                f"⚠️ 需修理后才能再次穿戴"
            )
            # 不再删除装备实例，遵循“耐久归零自动卸下且无法穿戴”的规则

            # 记录因装备损坏导致的属性损失，并在战报中显示
            if "max_hp" in delta and player.hp > player.max_hp:
                hp_before_adjust = player.hp
                player.hp = player.max_hp
                hp_loss = hp_before_adjust - player.hp
                hp_loss_from_equipment += hp_loss

            if "max_mp" in delta and player.mp > player.max_mp:
                mp_before_adjust = player.mp
                player.mp = player.max_mp
                mp_loss = mp_before_adjust - player.mp
                mp_loss_from_equipment += mp_loss

    # 如果有装备损坏，添加到战报中
    if broken_msgs:
        result_lines.extend(broken_msgs)

        # 如果有因装备损坏导致的HP/MP损失，在战报中显示
        if hp_loss_from_equipment > 0:
            result_lines.append(f"   ⚡ 体质下降，失去 {hp_loss_from_equipment} 生命值")
        if mp_loss_from_equipment > 0:
            result_lines.append(f"   ⚡ 智力下降，失去 {mp_loss_from_equipment} 理智值")

        # 重新计算剩余装备的属性加成（确保百分比加成正确）
        await recalc_equipment_attributes(session, player)

    # ---------------- 检查装备耐久度并提醒 ----------------
    durability_warning = await check_equipment_durability(session, player.id)
    if durability_warning:
        result_lines.append(durability_warning)

    session.add_all([player, tile])
    await session.flush()
    return BattleResult(battle_summary, victory, monster_full_display, result_lines)

async def _handle_rest(session, tile: WorldTile, player: Player) -> str:
    effective_attrs = await player.get_effective_attributes(session)
    effective_max_hp = effective_attrs.get('max_hp', player.max_hp)
    player.hp = effective_max_hp
    session.add(player)
    await session.flush()
    return "🏮 你在驿站睡了一觉。梦里有人一直在数数，数到你的伤口全部愈合为止。生命完全恢复。"

async def _handle_merchant(session, tile: WorldTile, player: Player) -> str:
    """处理卖货郎事件"""
    if player.id in tile.state.get("visited_by", []):
        return "🏪 卖货郎已经离开了，只留下空荡荡的摊位。"

    goods = tile.state.get("goods", [])
    if not goods:
        return "🏪 卖货郎的货物已经售罄。"

    # 显示商品列表
    goods_display = []
    for i, good in enumerate(goods, 1):
        item_config = config.items_config["by_id"].get(good["item_id"])
        if item_config:
            goods_display.append(
                f"{i}. {item_config.get_display_name()} ✖️{good['quantity']} - {good['price']}💰"
            )

    if not goods_display:
        return "🏪 卖货郎的货物已经售罄。"

    goods_display_md = []
    for i, good in enumerate(goods, 1):
        item_config_md = config.items_config["by_id"].get(good["item_id"])
        if item_config_md:
            goods_display_md.append(
                f"{i}. {cmd(item_config_md.get_display_name(), f'购买 {i}')} ×{good['quantity']}　💰{good['price']}"
            )

    msg = (
        "🏪 **神秘卖货郎**\n"
        "「旅者，需要些稀有材料吗？」\n"
        + "\n".join(goods_display_md if goods_display_md else goods_display) +
        "\n💡 点击物品名直接购买　⚠️ 每人只能访问一次"
    )

    # 标记玩家已访问
    tile.state.setdefault("visited_by", []).append(player.id)
    session.add(tile)
    await session.flush()

    return msg

async def _handle_elite(session, tile: WorldTile, player: Player):
    """处理精英怪事件"""
    if player.id in tile.state.get("defeated_by", []):
        return "⚰️ 精英诡异的残骸散落一地，散发着不祥的气息。"

    # 使用与普通诡异相同的战斗逻辑，但精英诡异更强
    return await _handle_personal_monster(session, tile, player)


EVENT_HANDLERS = {
    "MATERIAL": _handle_material,
    "TREASURE": _handle_treasure,
    "EMPTY": _handle_empty,
    "REST": _handle_rest,
    "MERCHANT": _handle_merchant,
    "ELITE": _handle_elite,
}


def _render_dungeon_overview(tile_data: list[tuple[int, int, str, bool]],
                            min_x: int, max_x: int, min_y: int, max_y: int,
                            player_x: int | None, player_y: int | None) -> bytes:
    """纯CPU渲染诡域俯瞰图（在线程池中执行，不阻塞事件循环）
    tile_data: [(x, y, event_type, is_preview), ...]
    """
    margin = 40
    img_width = 1000
    img_height = 1000
    img = Image.new('RGB', (img_width, img_height), color='#1a1a1a')
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    grid_width = max(max_x - min_x + 1, 1)
    grid_height = max(max_y - min_y + 1, 1)
    available_width = img_width - 2 * margin
    available_height = img_height - 2 * margin

    cell_width = max(available_width // grid_width, 2)
    cell_height = max(available_height // grid_height, 2)

    event_colors = {
        'MATERIAL': (76, 175, 80),
        'TREASURE': (255, 215, 0),
        'EMPTY': (244, 67, 54),
        'REST': (33, 150, 243),
        'MERCHANT': (156, 39, 176),
        'ELITE': (255, 87, 34),
    }

    tile_map = {(x, y): (evt, preview) for x, y, evt, preview in tile_data}

    # 绘制格子
    for grid_x in range(grid_width):
        for grid_y in range(grid_height):
            world_x = min_x + grid_x
            world_y = max_y - grid_y

            pixel_x = margin + grid_x * cell_width
            pixel_y = margin + grid_y * cell_height

            tile_info = tile_map.get((world_x, world_y))
            if tile_info:
                evt_type, is_preview = tile_info
                base_color = event_colors.get(evt_type, (102, 102, 102))
                if is_preview:
                    color = (base_color[0] // 3, base_color[1] // 3, base_color[2] // 3)
                else:
                    color = base_color
            else:
                color = (51, 51, 51)

            x1, y1 = pixel_x, pixel_y
            x2, y2 = pixel_x + cell_width, pixel_y + cell_height
            if x2 > x1 and y2 > y1:
                draw.rectangle([x1, y1, x2, y2], fill=color, outline=(85, 85, 85))

    # 绘制玩家位置标记
    if player_x is not None and player_y is not None:
        if min_x <= player_x <= max_x and min_y <= player_y <= max_y:
            pg_x = player_x - min_x
            pg_y = max_y - player_y
            pp_x = margin + pg_x * cell_width
            pp_y = margin + pg_y * cell_height

            cx = pp_x + cell_width // 2
            cy = pp_y + cell_height // 2
            radius = min(cell_width, cell_height) // 3

            draw.ellipse([cx - radius - 2, cy - radius - 2,
                         cx + radius + 2, cy + radius + 2],
                        fill=(255, 255, 255), outline=(255, 255, 255))
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                        fill=(255, 255, 0), outline=(255, 215, 0))

    # 绘制坐标轴十字线
    if min_x <= 0 <= max_x and min_y <= 0 <= max_y:
        og_x = 0 - min_x
        og_y = max_y - 0
        op_x = margin + og_x * cell_width
        op_y = margin + og_y * cell_height
        draw.line([(op_x + cell_width // 2, margin),
                   (op_x + cell_width // 2, img_height - margin)], fill=(128, 128, 128), width=1)
        draw.line([(margin, op_y + cell_height // 2),
                   (img_width - margin, op_y + cell_height // 2)], fill=(128, 128, 128), width=1)

    # 绘制坐标轴数字
    if font:
        step_x = max(1, grid_width // 10)
        for i in range(0, grid_width, step_x):
            wx = min_x + i
            px = margin + i * cell_width + cell_width // 2
            draw.text((px, 5), str(wx), fill=(255, 255, 255), font=font, anchor='mt')
            draw.text((px, img_height - 20), str(wx), fill=(255, 255, 255), font=font, anchor='mb')

        step_y = max(1, grid_height // 10)
        for i in range(0, grid_height, step_y):
            wy = max_y - i
            py = margin + i * cell_height + cell_height // 2
            draw.text((5, py), str(wy), fill=(255, 255, 255), font=font, anchor='lm')
            draw.text((img_width - 5, py), str(wy), fill=(255, 255, 255), font=font, anchor='rm')

    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return img_buffer.getvalue()


async def generate_player_centered_overview_image(region: str, session, center_x: int, center_y: int, width: int, height: int, player_x: int = None, player_y: int = None, server_id: int = 1) -> tuple[bytes, tuple[int, int, int, int]]:
    """生成以玩家为中心的固定大小俯瞰图片，只显示今日刷新的格子"""
    half_width = width // 2
    half_height = height // 2
    min_x = center_x - half_width
    max_x = center_x + half_width
    min_y = center_y - half_height
    max_y = center_y + half_height

    from sqlalchemy import and_
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    stmt = select(WorldTile).where(
        and_(
            WorldTile.region == region,
            WorldTile.server_id == server_id,
            WorldTile.x >= min_x, WorldTile.x <= max_x,
            WorldTile.y >= min_y, WorldTile.y <= max_y,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start
        )
    )
    result = await session.execute(stmt)
    tiles = result.scalars().all()

    # 提取纯数据，脱离ORM session
    tile_data = [(t.x, t.y, t.event_type, bool((t.state or {}).get("preview"))) for t in tiles]

    if player_x is None or player_y is None:
        player_x, player_y = center_x, center_y

    # 线程池渲染
    img_bytes = await asyncio.to_thread(
        _render_dungeon_overview, tile_data, min_x, max_x, min_y, max_y, player_x, player_y
    )
    return img_bytes, (min_x, max_x, min_y, max_y)


async def generate_region_overview_image(region: str, session, player_x: int = None, player_y: int = None, server_id: int = 1) -> tuple[bytes, tuple[int, int, int, int]]:
    """生成指定诡域的今日探索概览图片"""
    today = date.today()
    from sqlalchemy import and_

    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    stmt = select(WorldTile).where(
        and_(
            WorldTile.region == region,
            WorldTile.server_id == server_id,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start
        )
    )
    result = await session.execute(stmt)
    today_tiles = result.scalars().all()

    # 过滤掉x或y绝对值大于500的格子
    today_tiles = [tile for tile in today_tiles if abs(tile.x) <= 500 and abs(tile.y) <= 500]

    if not today_tiles:
        center_x, center_y = 0, 0
        if player_x is not None and player_y is not None:
            center_x, center_y = player_x, player_y
        min_x, max_x = center_x - 2, center_x + 2
        min_y, max_y = center_y - 2, center_y + 2
        tile_data = []
    else:
        # 提取纯数据
        tile_data = [(t.x, t.y, t.event_type, bool((t.state or {}).get("preview"))) for t in today_tiles]
        min_x = min(t[0] for t in tile_data)
        max_x = max(t[0] for t in tile_data)
        min_y = min(t[1] for t in tile_data)
        max_y = max(t[1] for t in tile_data)

    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y

    if tile_data:
        if max_x - min_x + 1 < 20:
            cx = (min_x + max_x) // 2
            min_x, max_x = cx - 10, cx + 10
        if max_y - min_y + 1 < 20:
            cy = (min_y + max_y) // 2
            min_y, max_y = cy - 10, cy + 10

    if min_x >= max_x:
        max_x = min_x + 20
    if min_y >= max_y:
        max_y = min_y + 20

    # 线程池渲染（复用共享渲染函数）
    img_bytes = await asyncio.to_thread(
        _render_dungeon_overview, tile_data, min_x, max_x, min_y, max_y, player_x, player_y
    )
    return img_bytes, (min_x, max_x, min_y, max_y)
