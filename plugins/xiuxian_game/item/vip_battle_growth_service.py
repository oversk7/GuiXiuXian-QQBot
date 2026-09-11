"""VIP 战后永久成长；调用方负责事务，成长记入 VIP 独立账本。"""
from dataclasses import dataclass, replace
from datetime import datetime
import random

from sqlalchemy.ext.asyncio import AsyncSession

from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.vip_equipment_bonus_repository import VIPEquipmentBonusRepository
from ..models.inventory import ItemInstance
from ..models.player import Player


BLADE_ID = "vip_blade_zhanlongshan"
ATTRIBUTE_NAMES = {
    "attack": "攻击", "defense": "防御", "agility": "敏捷",
    "luck": "幸运", "max_hp": "生命上限", "max_mp": "理智上限",
}


@dataclass(frozen=True)
class GrowthRule:
    item_ids: tuple[str, ...]
    attribute: str
    counter: str
    message: str
    limit_message: str | None = None
    multiplier: int = 1
    daily_limit: int = 20
    default_value: int = 2


BLADE_HP = GrowthRule(
    (BLADE_ID,), "max_hp", "blade_kill",
    "🩸 噬灵者：击杀吞噬，生命上限+{value}（今日{count}/20）",
    multiplier=3, default_value=0,
)
# 死斗的斩龙闪成长为理智，和 PVE 共用 blade_kill 每日计数。
BLADE_MP = replace(
    BLADE_HP, attribute="max_mp", multiplier=1, default_value=2,
    message="🩸 噬灵者：击杀吞噬，理智上限+{value}（今日{count}/20）",
    limit_message="🩸 噬灵者：今日已达上限（{count}/20）",
)
ROBE_ATTACK = GrowthRule(
    ("vip_robe_jingyuanzhiyi", "vip_robe_jingyuan_legacy"), "attack", "robe_die",
    "🪞 镜怨自噬：死亡化怨，攻击+{value}（今日{count}/20）",
    "🪞 镜怨自噬：今日已达上限（{count}/20）",
)
GUI_YU_AGILITY = GrowthRule(
    ("vip_gui_yu",), "agility", "gy_kill",
    "👣 夺伞步：脚步更轻，敏捷+{value}（今日+{points}/40）",
    "👣 夺伞步：今日已达上限（+40/40）",
)
CHRONO_HP = GrowthRule(
    ("vip_chrono_watch",), "max_hp", "cw_hp",
    "⏱️ 时间掠夺：夺取寿命，生命上限+{value}（今日{count}/20）",
    "⏱️ 时间掠夺：今日已达上限（+120/120）",
    multiplier=3,
)
CHRONO_ATTACK = GrowthRule(
    ("vip_chrono_watch",), "attack", "cw_atk",
    "⏱️ 终焉铭刻：铭刻终结，攻击力+{value}（今日{count}/20）",
    "⏱️ 终焉铭刻：今日已达上限（+40/40）",
)
DICE_ATTACK = GrowthRule(
    ("vip_ghost_dice",), "attack", "dice_atk",
    "🎲 骰相·噬：骰纹加深，攻击力+{value}（今日{count}/20）",
    "🎲 骰相·噬：今日已达上限（+40/40）",
)
PVE_RULES = {
    (BLADE_ID, "gain_max_hp"): BLADE_HP,
    ("vip_gui_yu", "gain_agility"): GUI_YU_AGILITY,
    ("vip_chrono_watch", "gain_max_hp"): CHRONO_HP,
    ("vip_chrono_watch", "gain_attack"): CHRONO_ATTACK,
    ("vip_ghost_dice", "gain_attack"): DICE_ATTACK,
}


class VIPBattleGrowthService:
    def __init__(
        self,
        item_repo: ItemRepository,
        player_repo: PlayerRepository,
        bonus_repo: VIPEquipmentBonusRepository,
    ):
        self._items = item_repo
        self._players = player_repo
        self._bonuses = bonus_repo

    async def _grant(self, player: Player, attribute: str, value: int) -> None:
        current = getattr(player, attribute)
        await self._bonuses.add_bonus(player.id, attribute, value)
        setattr(player, attribute, current + value)
        await self._players.update(player)

    async def _apply_counter(
        self, player: Player, items: list[ItemInstance], rule: GrowthRule, value: int = 2,
    ) -> str | None:
        item = next((item for item in items if item.item_id in rule.item_ids), None)
        if item is None:
            return None
        extra = dict(item.extra_attrs or {})
        day_key, count_key = f"{rule.counter}_day", f"{rule.counter}_cnt"
        today = datetime.now().strftime("%Y%m%d")
        if extra.get(day_key) != today:
            extra[day_key] = today
            extra[count_key] = 0
        count = int(extra.get(count_key, 0))
        if count >= rule.daily_limit:
            return rule.limit_message.format(count=count) if rule.limit_message else None

        actual_value = value * rule.multiplier
        await self._grant(player, rule.attribute, actual_value)
        count += 1
        extra[count_key] = count
        item.extra_attrs = extra
        await self._items.update(item)
        return rule.message.format(value=actual_value, count=count, points=count * 2)

    async def _apply_random(
        self, player: Player, items: list[ItemInstance], *,
        attribute: str | None = None, value: int = 40, include_name: bool = False,
    ) -> str | None:
        item = next((item for item in items if item.item_id == BLADE_ID), None)
        if item is None:
            return None
        extra = dict(item.extra_attrs or {})
        today = datetime.now().strftime("%Y%m%d")
        if extra.get("blade_rand_day") == today:
            return None
        attribute = attribute if attribute is not None else random.choice(list(ATTRIBUTE_NAMES))
        attribute_name = ATTRIBUTE_NAMES[attribute]
        await self._grant(player, attribute, value)
        extra["blade_rand_day"] = today
        item.extra_attrs = extra
        await self._items.update(item)
        name = f"{player.nickname} " if include_name else ""
        return f"✨ 刃之魔灵：{name}今日首战恩赐，{attribute_name}+{value}（永久）"

    async def apply_pve_effects(self, player: Player, effects: list[dict]) -> list[str]:
        """只结算实际触发的来源装备，保持装备分组的回显顺序。"""
        if not effects:
            return []
        items = await self._items.get_equipped_items(player.id)
        messages = []
        for item_id in dict.fromkeys(source for source, _ in PVE_RULES):
            for effect in effects:
                if effect.get("source_item_id") != item_id:
                    continue
                effect_type = effect.get("type")
                if item_id == BLADE_ID and effect_type == "gain_random_attr":
                    message = await self._apply_random(
                        player, items, attribute=effect["attr"], value=int(effect.get("value", 0) or 0),
                    )
                else:
                    rule = PVE_RULES.get((item_id, effect_type))
                    if rule is None:
                        continue
                    message = await self._apply_counter(
                        player, items, rule,
                        int(effect.get("value", rule.default_value) or rule.default_value),
                    )
                if message and (item_id != "vip_gui_yu" or message not in messages):
                    messages.append(message)
        return messages

    async def apply_daily_random(self, player: Player, *, include_name: bool = False) -> str | None:
        items = await self._items.get_equipped_items(player.id)
        return await self._apply_random(player, items, include_name=include_name)

    async def apply_pvp_kill(self, player: Player) -> list[str]:
        items = await self._items.get_equipped_items(player.id)
        messages = []
        for rule in (BLADE_MP, GUI_YU_AGILITY):
            message = await self._apply_counter(player, items, rule)
            if message:
                messages.append(message)
        return messages

    async def apply_robe_death(self, player: Player) -> str | None:
        items = await self._items.get_equipped_items(player.id)
        return await self._apply_counter(player, items, ROBE_ATTACK)

    async def apply_dungeon_defeat(self, player: Player) -> list[str]:
        """诡域失败分支仍结算首战、镜怨自噬与斩龙闪生命成长。"""
        items = await self._items.get_equipped_items(player.id)
        messages = []
        message = await self._apply_random(player, items)
        if message:
            messages.append(message)
        for rule in (ROBE_ATTACK, replace(BLADE_HP, limit_message="(噬灵者今日上限已满)")):
            message = await self._apply_counter(player, items, rule)
            if message:
                messages.append(message)
        return messages


def _service(session: AsyncSession) -> VIPBattleGrowthService:
    return VIPBattleGrowthService(
        ItemRepository(session), PlayerRepository(session), VIPEquipmentBonusRepository(session),
    )


async def settle_pve_victory(
    session: AsyncSession, player: Player, post_effects: list[dict],
) -> list[str]:
    """普通攻击与诡域共用的 PVE 胜利成长入口。"""
    from .vip_huihai_xinyuan_skill import apply_kill_max_mp

    messages = []
    message = await apply_kill_max_mp(session, player)
    if message:
        messages.append(message)
    messages.extend(await _service(session).apply_pve_effects(player, post_effects))
    return messages


async def settle_pvp_growth(
    session: AsyncSession, attacker: Player, target: Player, *, victory: bool,
) -> list[str]:
    """死斗成长入口；城镇切磋由调用方排除，胜负沿用战斗入口判定。"""
    from .vip_huihai_xinyuan_skill import apply_kill_max_mp

    service = _service(session)
    messages = []
    for player in (attacker, target):
        message = await service.apply_daily_random(player, include_name=True)
        if message:
            messages.append(message)
    winner, loser = (attacker, target) if victory else (target, attacker)
    messages.extend(await service.apply_pvp_kill(winner))
    message = await apply_kill_max_mp(session, winner)
    if message:
        messages.append(message)
    message = await service.apply_robe_death(loser)
    if message:
        messages.append(message)
    return messages


async def settle_dungeon_defeat(session: AsyncSession, player: Player) -> list[str]:
    return await _service(session).apply_dungeon_defeat(player)
