"""宠物核心服务 - 获取、喂食、互动、升级、化形、饰品、守田"""
from datetime import datetime
from typing import Tuple, List
from nonebot import logger
from sqlalchemy.orm.attributes import flag_modified

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.pet_instance import PetInstance
from ..models.inventory import ItemInstance, ItemType
from ..domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory
from .config import PetConfigManager, format_bonus


class PetService:
    """宠物核心服务"""

    def __init__(self):
        self.config = PetConfigManager()

    # ==================== 获取宠物 ====================

    async def acquire_pet(
        self, uow: UnitOfWork, player_id: str, beast_item_id: str, nickname: str
    ) -> Tuple[bool, str]:
        """从背包中的诡兽物品转化为宠物实例"""
        count = await uow.pets.count_by_player(player_id)
        max_pets = self.config.settings["max_pets_per_player"]
        if count >= max_pets:
            return False, f"宠物数量已达上限({max_pets}只)"

        beast_count = await uow.items.get_material_total_quantity(player_id, beast_item_id)
        if beast_count < 1:
            return False, "背包中没有该诡兽"

        # 根据item_id找到beast_id
        beast_config = None
        for beast in self.config.get_all_beasts():
            guardian_item_id = f"guardian_{beast.beast_id}"
            if guardian_item_id == beast_item_id:
                beast_config = beast
                break
        if not beast_config:
            return False, "该物品不是可驯化的诡兽"

        await ItemInstance.consume_item(uow.session, player_id, beast_item_id, 1)

        pet = PetInstance(
            player_id=player_id,
            beast_id=beast_config.beast_id,
            nickname=nickname,
            level=1,
            experience=0,
            affection=0,
            mood=80,
            hunger=100,
            is_active=(count == 0),
        )
        await uow.pets.add(pet)

        msg = (
            f"成功驯化【{beast_config.name}】!\n"
            f"昵称: {nickname}\n"
            f"稀有度: {beast_config.rarity}"
        )
        if count == 0:
            msg += "\n已自动设为当前伴侣"
        return True, msg

    # ==================== 切换伴侣 ====================

    async def set_active_pet(
        self, uow: UnitOfWork, player_id: str, pet_id: int
    ) -> Tuple[bool, str]:
        """切换当前伴侣"""
        pet = await uow.pets.get_by_id(pet_id)
        if not pet or pet.player_id != player_id:
            return False, "未找到该宠物"
        if pet.is_active:
            return False, f"【{pet.nickname}】已经是当前伴侣了"

        current = await uow.pets.get_active_pet(player_id)
        if current:
            current.is_active = False
            await uow.pets.update(current)

        pet.is_active = True
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)
        return True, f"【{pet.nickname}】现在是你的伴侣了"

    # ==================== 喂食 ====================

    async def feed_with_resentment(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """用怨念喂食当前伴侣"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        cost = self.config.settings["base_feed_resentment"]
        player = await uow.players.get_by_id(player_id)
        if player.resentment < cost:
            return False, f"怨念不足，喂食需要{cost}点怨念（当前{player.resentment}）"

        player.resentment -= cost
        await uow.players.update(player)

        restore = self.config.settings["feed_hunger_restore"]
        pet.hunger = min(100, pet.hunger + restore)
        pet.mood = min(100, pet.mood + 3)
        pet.last_fed_at = datetime.now()
        exp_gain = 5
        level_up_msg = self._add_experience(pet, exp_gain)
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        msg = (
            f"已喂养【{pet.nickname}】\n"
            f"消耗: {cost}点怨念\n"
            f"饱食度: {pet.hunger}/100\n"
            f"心情: {pet.mood}/100\n"
            f"经验+{exp_gain}"
        )
        if level_up_msg:
            msg += f"\n{level_up_msg}"
        return True, msg

    async def feed_with_dish(
        self, uow: UnitOfWork, player_id: str, dish_name: str
    ) -> Tuple[bool, str]:
        """用菜肴喂食当前伴侣"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        from ..config import config as game_config
        dish_config = game_config.items_config.get("by_name", {}).get(dish_name)
        if not dish_config or dish_config.type != ItemType.DISH:
            return False, f"未找到菜肴【{dish_name}】"

        dish_item_id = dish_config.item_id
        dish_count = await uow.items.get_material_total_quantity(player_id, dish_item_id)
        if dish_count < 1:
            return False, f"背包中没有【{dish_name}】"

        await ItemInstance.consume_item(uow.session, player_id, dish_item_id, 1)

        rarity = getattr(dish_config, "rarity", "white")
        rarity_bonus = {"white": 1, "green": 2, "blue": 3, "purple": 4, "orange": 5}
        multiplier = rarity_bonus.get(rarity, 1)

        restore = self.config.settings["dish_hunger_restore"]
        mood_bonus = self.config.settings["dish_mood_bonus"] * multiplier
        exp_gain = 10 * multiplier

        pet.hunger = min(100, pet.hunger + restore)
        pet.mood = min(100, pet.mood + mood_bonus)
        pet.last_fed_at = datetime.now()
        level_up_msg = self._add_experience(pet, exp_gain)
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        msg = (
            f"用【{dish_name}】喂养了【{pet.nickname}】\n"
            f"饱食度: {pet.hunger}/100\n"
            f"心情+{mood_bonus} → {pet.mood}/100\n"
            f"经验+{exp_gain}"
        )
        if level_up_msg:
            msg += f"\n{level_up_msg}"
        return True, msg

    # ==================== 互动 ====================

    async def interact(
        self, uow: UnitOfWork, player_id: str, action: str
    ) -> Tuple[bool, str]:
        """与宠物互动（摸头、玩耍等）"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        cd_minutes = self.config.settings["interact_cooldown_minutes"]
        if pet.last_interact_at:
            elapsed = (datetime.now() - pet.last_interact_at).total_seconds() / 60
            if elapsed < cd_minutes:
                remaining = int(cd_minutes - elapsed)
                return False, f"互动冷却中，还需等待{remaining}分钟"

        affection_gain = self.config.settings["interact_affection_gain"]
        mood_gain = self.config.settings["interact_mood_gain"]
        exp_gain = 3

        pet.affection = min(1000, pet.affection + affection_gain)
        pet.mood = min(100, pet.mood + mood_gain)
        pet.last_interact_at = datetime.now()
        level_up_msg = self._add_experience(pet, exp_gain)
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        level_name = self.config.get_affection_level_name(pet.affection)
        msg = (
            f"你{action}了【{pet.nickname}】\n"
            f"好感度+{affection_gain} → {pet.affection}({level_name})\n"
            f"心情+{mood_gain} → {pet.mood}/100\n"
            f"经验+{exp_gain}"
        )
        if level_up_msg:
            msg += f"\n{level_up_msg}"
        return True, msg

    # ==================== 化形 ====================

    async def transform(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """宠物化形"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"
        if pet.is_transformed:
            return False, f"【{pet.nickname}】已经化形了"

        req_level = self.config.settings["transform_level"]
        req_affection = self.config.settings["transform_affection"]
        if pet.level < req_level:
            return False, f"化形需要等级{req_level}（当前{pet.level}级）"
        if pet.affection < req_affection:
            return False, f"化形需要好感度{req_affection}（当前{pet.affection}）"

        pet.is_transformed = True
        await uow.pets.update(pet)

        beast = self.config.get_beast(pet.beast_id)
        return True, (
            f"【{pet.nickname}】化形成功!\n"
            f"化形为: {beast.transform_name}\n"
            f"{beast.transform_description}"
        )

    # ==================== 饰品 ====================

    async def equip_accessory(
        self, uow: UnitOfWork, player_id: str, accessory_name: str
    ) -> Tuple[bool, str]:
        """给宠物装备饰品"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        acc = self.config.get_accessory_by_name(accessory_name)
        if not acc:
            return False, f"未找到饰品【{accessory_name}】"

        acc_item_id = f"pet_acc_{acc.accessory_id}"
        acc_count = await uow.items.get_material_total_quantity(player_id, acc_item_id)
        if acc_count < 1:
            return False, f"背包中没有【{accessory_name}】"

        accessories = pet.accessories or {}

        # 替换旧饰品
        if acc.slot in accessories:
            old_id = accessories[acc.slot]
            old_acc = self.config.get_accessory(old_id)
            old_item_id = f"pet_acc_{old_id}"
            await ItemInstance.add_item(uow.session, player_id, old_item_id, 1)

        await ItemInstance.consume_item(uow.session, player_id, acc_item_id, 1)
        accessories[acc.slot] = acc.accessory_id
        pet.accessories = accessories
        flag_modified(pet, "accessories")
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        bonus_text = format_bonus(acc.bonus)
        return True, (
            f"给【{pet.nickname}】装备了【{accessory_name}】\n"
            f"槽位: {acc.slot}\n"
            f"属性: {bonus_text}"
        )

    # ==================== 守田派遣 ====================

    async def dispatch_to_guard(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """派遣当前伴侣去守田"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        guarding = await uow.pets.get_guarding_pet(player_id)
        if guarding:
            return False, f"【{guarding.nickname}】已在守田中，请先召回"

        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        pet.is_guarding = True
        beast = self.config.get_beast(pet.beast_id)
        # 更新灵田的守护记录（兼容偷菜拦截逻辑）
        field.guardian_beast_id = f"guardian_{pet.beast_id}"
        field.guardian_fed_at = datetime.now()
        await uow.pets.update(pet)
        await uow.spirit_fields.update(field)

        return True, (
            f"【{pet.nickname}】已派遣守田!\n"
            f"拦截率: {beast.intercept_rate}%"
        )

    async def recall_from_guard(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """召回守田宠物"""
        guarding = await uow.pets.get_guarding_pet(player_id)
        if not guarding:
            return False, "没有宠物在守田"

        guarding.is_guarding = False
        await uow.pets.update(guarding)

        field = await uow.spirit_fields.get_by_player_id(player_id)
        if field:
            field.guardian_beast_id = None
            field.guardian_fed_at = None
            await uow.spirit_fields.update(field)

        return True, f"已召回【{guarding.nickname}】"

    # ==================== 查看宠物 ====================

    async def get_pet_info(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看当前伴侣信息"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽，使用【驯化诡兽 名称 昵称】获取"

        beast = self.config.get_beast(pet.beast_id)
        level_name = self.config.get_affection_level_name(pet.affection)
        mood_mult = self.config.get_mood_multiplier(pet.mood)

        display_name = beast.transform_name if pet.is_transformed else beast.name

        # 饰品描述前缀
        acc_desc = ""
        if pet.accessories:
            for slot, acc_id in pet.accessories.items():
                acc = self.config.get_accessory(acc_id)
                if acc and acc.description_prefix:
                    acc_desc += acc.description_prefix

        total_bonus = self._calculate_total_bonus(pet)

        current_exp = pet.experience
        next_level_exp = self.config.get_exp_for_level(pet.level + 1)
        exp_progress = f"{current_exp}/{next_level_exp}"

        status = "守田中" if pet.is_guarding else "跟随中"

        msg = (
            f"{'═' * 16}\n"
            f"  {acc_desc}{pet.nickname} ({display_name})\n"
            f"{'═' * 16}\n"
            f"等级: {pet.level} | 经验: {exp_progress}\n"
            f"好感: {pet.affection}({level_name})\n"
            f"心情: {pet.mood}/100 (倍率×{mood_mult:.1f})\n"
            f"饱食: {pet.hunger}/100\n"
            f"状态: {status}"
        )

        if pet.is_transformed:
            msg += " | 已化形"

        msg += (
            f"\n{'─' * 16}\n"
            f"战斗加成:\n"
            f"  攻击+{total_bonus['attack']} 防御+{total_bonus['defense']}\n"
            f"  生命+{total_bonus['hp']}\n"
            f"  暴击+{total_bonus['crit_rate']:.1%} 闪避+{total_bonus['dodge_rate']:.1%}"
        )

        return True, msg

    async def get_pet_list(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看所有宠物"""
        pets = await uow.pets.get_all_by_player(player_id)
        if not pets:
            return False, "你还没有宠物，使用【驯化诡兽 名称 昵称】获取"

        msg = f"诡兽巢穴 ({len(pets)}只)\n{'━' * 16}\n"
        for pet in pets:
            beast = self.config.get_beast(pet.beast_id)
            display_name = beast.transform_name if pet.is_transformed else beast.name
            status = ""
            if pet.is_active:
                status = "[伴侣]"
            if pet.is_guarding:
                status += "[守田]"
            msg += f"  #{pet.id} {pet.nickname}({display_name}) Lv.{pet.level} {status}\n"

        return True, msg

    # ==================== 内部方法 ====================

    def _add_experience(self, pet: PetInstance, amount: int) -> str:
        """增加经验并检查升级，返回升级消息"""
        pet.experience += amount
        max_level = self.config.settings["max_level"]
        old_level = pet.level
        leveled_up = False

        while pet.level < max_level:
            next_exp = self.config.get_exp_for_level(pet.level + 1)
            if pet.experience >= next_exp:
                pet.level += 1
                self._apply_level_up(pet)
                leveled_up = True
            else:
                break

        if leveled_up:
            return f"升级! Lv.{old_level} → Lv.{pet.level}"
        return ""

    def _apply_level_up(self, pet: PetInstance):
        """应用升级属性"""
        beast = self.config.get_beast(pet.beast_id)
        growth = self.config.get_growth(beast.rarity)
        if growth:
            pet.bonus_attack += int(growth.attack)
            pet.bonus_defense += int(growth.defense)
            pet.bonus_hp += int(growth.hp)
            pet.bonus_crit_rate += growth.crit_rate
            pet.bonus_dodge_rate += growth.dodge_rate

    def _calculate_total_bonus(self, pet: PetInstance) -> dict:
        """计算总属性加成（等级+饰品+心情倍率）"""
        mood_mult = self.config.get_mood_multiplier(pet.mood)

        bonus = {
            "attack": pet.bonus_attack,
            "defense": pet.bonus_defense,
            "hp": pet.bonus_hp,
            "crit_rate": pet.bonus_crit_rate,
            "dodge_rate": pet.bonus_dodge_rate,
        }

        # 叠加饰品加成
        if pet.accessories:
            for acc_id in pet.accessories.values():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    for attr, value in acc.bonus.items():
                        if attr in bonus:
                            bonus[attr] += value

        # 应用心情倍率
        bonus["attack"] = int(bonus["attack"] * mood_mult)
        bonus["defense"] = int(bonus["defense"] * mood_mult)
        bonus["hp"] = int(bonus["hp"] * mood_mult)
        bonus["crit_rate"] = round(bonus["crit_rate"] * mood_mult, 4)
        bonus["dodge_rate"] = round(bonus["dodge_rate"] * mood_mult, 4)

        return bonus
