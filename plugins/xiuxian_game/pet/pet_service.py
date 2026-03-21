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
            msg += "\n已自动设为当前伙伴"
        return True, msg

    # ==================== 切换伙伴 ====================

    async def set_active_pet(
        self, uow: UnitOfWork, player_id: str, pet_id_or_name: str
    ) -> Tuple[bool, str]:
        """切换当前伙伴（支持ID或昵称）"""
        pet = None
        # 尝试按数字ID查找
        try:
            pet_id = int(pet_id_or_name)
            pet = await uow.pets.get_by_id(pet_id)
            if pet and pet.player_id != player_id:
                pet = None
        except ValueError:
            pass
        # 按昵称查找
        if not pet:
            all_pets = await uow.pets.get_all_by_player(player_id)
            for p in all_pets:
                if p.nickname == pet_id_or_name:
                    pet = p
                    break
        if not pet:
            return False, "未找到该宠物，请使用【宠物列表】查看"
        if pet.is_active:
            return False, f"【{pet.nickname}】已经是当前伙伴了"

        current = await uow.pets.get_active_pet(player_id)
        if current:
            current.is_active = False
            await uow.pets.update(current)

        pet.is_active = True
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)
        return True, f"【{pet.nickname}】现在是你的伙伴了"

    # ==================== 喂食 ====================

    def _calc_diminished_rewards(self, already_fed: int, quantity: int) -> Tuple[int, int, str]:
        """根据当日已喂次数计算递减后的经验和心情总收益

        Returns: (total_exp, total_mood, 收益提示文本)
        """
        tier1 = self.config.settings["feed_diminish_tier1"]       # 50
        tier2 = self.config.settings["feed_diminish_tier2"]       # 150
        t3_exp = self.config.settings["feed_diminish_tier3_exp"]  # 1
        t3_mood = self.config.settings["feed_diminish_tier3_mood"]  # 0

        total_exp = 0
        total_mood = 0
        for i in range(quantity):
            count = already_fed + i + 1
            if count <= tier1:
                total_exp += 5
                total_mood += 3
            elif count <= tier2:
                total_exp += 2
                total_mood += 1
            else:
                total_exp += t3_exp
                total_mood += t3_mood

        # 生成收益提示
        final_count = already_fed + quantity
        hint = ""
        if final_count > tier2:
            hint = f"（已超{tier2}次，经验大幅递减）"
        elif final_count > tier1:
            hint = f"（已超{tier1}次，经验减半）"

        return total_exp, total_mood, hint

    async def feed_with_resentment(
        self, uow: UnitOfWork, player_id: str, quantity: int = 1
    ) -> Tuple[bool, str]:
        """用怨念喂食当前伙伴（支持批量，每次随机消耗50-200怨念，每日递减收益）"""
        import random

        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

        player = await uow.players.get_by_id(player_id)

        # 每次喂食随机消耗怨念
        r_min = self.config.settings["feed_resentment_min"]
        r_max = self.config.settings["feed_resentment_max"]
        costs = [random.randint(r_min, r_max) for _ in range(quantity)]
        total_cost = sum(costs)
        if player.resentment < total_cost:
            return False, f"怨念不足，喂食{quantity}次预计需要{r_min * quantity}~{r_max * quantity}点怨念（当前{player.resentment}）"

        player.resentment -= total_cost
        await uow.players.update(player)

        # 每日喂食计数（跨日自动重置）
        today = datetime.now().strftime("%Y-%m-%d")
        if pet.daily_feed_date != today:
            pet.daily_feed_count = 0
            pet.daily_feed_date = today
        already_fed = pet.daily_feed_count

        # 递减收益计算
        total_exp, total_mood, diminish_hint = self._calc_diminished_rewards(already_fed, quantity)

        restore = self.config.settings["feed_hunger_restore"]
        pet.hunger = min(100, pet.hunger + restore * quantity)
        pet.mood = min(100, pet.mood + total_mood)
        pet.daily_feed_count = already_fed + quantity
        pet.last_fed_at = datetime.now()
        level_up_msg = self._add_experience(pet, total_exp)
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        qty_text = f"×{quantity}" if quantity > 1 else ""
        msg = (
            f"已喂养【{pet.nickname}】{qty_text}\n"
            f"消耗: {total_cost}点怨念\n"
            f"饱食度: {pet.hunger}/100\n"
            f"心情: {pet.mood}/100\n"
            f"经验+{total_exp}{diminish_hint}\n"
            f"今日已喂: {pet.daily_feed_count}次"
        )
        if level_up_msg:
            msg += f"\n{level_up_msg}"
        return True, msg

    async def feed_with_dish(
        self, uow: UnitOfWork, player_id: str, dish_name: str, quantity: int = 1
    ) -> Tuple[bool, str]:
        """用菜肴喂食当前伙伴（支持批量）"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

        from ..config import config as game_config
        dish_config = game_config.items_config.get("by_name", {}).get(dish_name)
        if not dish_config or dish_config.type != ItemType.DISH:
            return False, f"未找到菜肴【{dish_name}】"

        dish_item_id = dish_config.item_id
        dish_count = await uow.items.get_material_total_quantity(player_id, dish_item_id)
        if dish_count < quantity:
            return False, f"背包中【{dish_name}】不足（需要{quantity}，拥有{dish_count}）"

        await ItemInstance.consume_item(uow.session, player_id, dish_item_id, quantity)

        rarity = getattr(dish_config, "rarity", "white")
        rarity_bonus = {"white": 1, "green": 2, "blue": 3, "purple": 4, "orange": 5}
        multiplier = rarity_bonus.get(rarity, 1)

        restore = self.config.settings["dish_hunger_restore"]
        mood_bonus_per = self.config.settings["dish_mood_bonus"] * multiplier
        exp_per = 10 * multiplier

        total_mood_bonus = mood_bonus_per * quantity
        total_exp = exp_per * quantity

        pet.hunger = min(100, pet.hunger + restore * quantity)
        pet.mood = min(100, pet.mood + total_mood_bonus)
        pet.last_fed_at = datetime.now()
        level_up_msg = self._add_experience(pet, total_exp)
        await uow.pets.update(pet)
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        qty_text = f"×{quantity}" if quantity > 1 else ""
        msg = (
            f"用【{dish_name}】{qty_text}喂养了【{pet.nickname}】\n"
            f"饱食度: {pet.hunger}/100\n"
            f"心情+{total_mood_bonus} → {pet.mood}/100\n"
            f"经验+{total_exp}"
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
            return False, "你还没有伙伴诡兽"

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
        self, uow: UnitOfWork, player_id: str, gender: str = "female"
    ) -> Tuple[bool, str]:
        """宠物化形"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

        beast = self.config.get_beast(pet.beast_id)

        # 已化形：不可再次化形
        if pet.is_transformed:
            return False, f"【{pet.nickname}】已经化形了，无法再次变更"

        req_level = self.config.settings["transform_level"]
        req_affection = self.config.settings["transform_affection"]
        if pet.level < req_level:
            return False, f"化形需要等级{req_level}（当前{pet.level}级）"
        if pet.affection < req_affection:
            return False, f"化形需要好感度{req_affection}（当前{pet.affection}）"

        pet.is_transformed = True
        pet.transform_gender = gender
        await uow.pets.update(pet)

        transform_name = self.config.get_transform_name(pet.beast_id, gender)
        transform_desc = self.config.get_transform_description(pet.beast_id, gender)
        gender_cn = "男" if gender == "male" else "女"
        return True, (
            f"【{pet.nickname}】化形成功!\n"
            f"化形为: {transform_name}（{gender_cn}）\n"
            f"{transform_desc}"
        )

    # ==================== 饰品 ====================

    async def equip_accessory(
        self, uow: UnitOfWork, player_id: str, accessory_name: str
    ) -> Tuple[bool, str]:
        """给宠物装备饰品"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

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
        """派遣当前伙伴去守田"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

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
        """召回守田宠物（兼容旧系统遗留的诡兽）"""
        guarding = await uow.pets.get_guarding_pet(player_id)

        if guarding:
            # 新系统宠物召回
            guarding.is_guarding = False
            await uow.pets.update(guarding)

            field = await uow.spirit_fields.get_by_player_id(player_id)
            if field:
                field.guardian_beast_id = None
                field.guardian_fed_at = None
                await uow.spirit_fields.update(field)

            return True, f"已召回【{guarding.nickname}】"

        # 兼容旧系统：灵田上有guardian_beast_id但没有pet_instance
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if field and field.guardian_beast_id:
            old_beast_id = field.guardian_beast_id
            # 把旧诡兽物品还回背包
            try:
                await ItemInstance.add_item(uow.session, player_id, old_beast_id, 1)
            except ValueError:
                pass  # 背包满也继续清除守田状态

            from .config import PetConfigManager
            config = PetConfigManager()
            # 从item_id反查名称
            beast_name = old_beast_id
            for beast in config.get_all_beasts():
                if f"guardian_{beast.beast_id}" == old_beast_id:
                    beast_name = beast.name
                    break

            field.guardian_beast_id = None
            field.guardian_fed_at = None
            await uow.spirit_fields.update(field)

            return True, (
                f"已召回旧系统的【{beast_name}】到背包\n"
                f"提示: 使用【驯化诡兽 {beast_name} 昵称】将其升级为宠物伙伴"
            )

        return False, "没有宠物在守田"

    # ==================== 宠物进化 ====================

    RARITY_CN = {"white": "普通", "green": "优秀", "blue": "稀有", "purple": "史诗", "orange": "传说"}
    RARITY_EMOJI = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}

    async def evolve_pet(
        self, uow: UnitOfWork, player_id: str, confirm: bool = False
    ) -> Tuple[bool, str]:
        """宠物进化 — 提升稀有度"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽"

        beast = self.config.get_beast(pet.beast_id)
        current_rarity = pet.evolved_rarity or beast.rarity
        next_rarity = self.config.get_next_rarity(current_rarity)

        if not next_rarity:
            return False, f"【{pet.nickname}】已是{self.RARITY_EMOJI.get(current_rarity, '')}最高稀有度，无法继续进化"

        evo_cfg = self.config.get_evolution_config(current_rarity, next_rarity)
        if not evo_cfg:
            return False, "⛔ 进化配置缺失，请联系管理员"

        min_level = evo_cfg["min_level"]
        cost_item = evo_cfg["cost_item"]
        cost_qty = evo_cfg["cost_quantity"]
        cost_resentment = evo_cfg["cost_resentment"]

        from ..config import config as gcfg
        item_cfg = gcfg.items_config["by_id"].get(cost_item)
        item_name = item_cfg.name if item_cfg else cost_item

        cur_emoji = self.RARITY_EMOJI.get(current_rarity, "")
        next_emoji = self.RARITY_EMOJI.get(next_rarity, "")
        cur_cn = self.RARITY_CN.get(current_rarity, current_rarity)
        next_cn = self.RARITY_CN.get(next_rarity, next_rarity)

        # 不确认时：显示进化条件
        if not confirm:
            from ..models.inventory import ItemInstance
            from sqlalchemy import func, select
            stmt = select(func.coalesce(func.sum(ItemInstance.quantity), 0)).where(
                ItemInstance.player_id == player_id,
                ItemInstance.item_id == cost_item
            )
            result = await uow.session.execute(stmt)
            have_qty = result.scalar() or 0

            from ..models.player import Player
            player = await uow.session.get(Player, player_id)
            have_resentment = player.resentment if player else 0

            level_ok = "✅" if pet.level >= min_level else "❌"
            item_ok = "✅" if have_qty >= cost_qty else "❌"
            resentment_ok = "✅" if have_resentment >= cost_resentment else "❌"

            old_growth = self.config.get_growth(current_rarity)
            new_growth = self.config.get_growth(next_rarity)

            msg = (
                f"🔮 宠物进化 — {pet.nickname}\n"
                f"━━━━━━━━━━━━━\n"
                f"{cur_emoji}{cur_cn} → {next_emoji}{next_cn}\n"
                f"━━━ 进化条件 ━━━\n"
                f"{level_ok} 等级 ≥ {min_level}（当前 Lv.{pet.level}）\n"
                f"{item_ok} {item_name} ×{cost_qty}（拥有 {have_qty}）\n"
                f"{resentment_ok} 怨念 ≥ {cost_resentment:,}（拥有 {have_resentment:,}）\n"
                f"━━━ 成长变化 ━━━\n"
                f"⚔攻击 {old_growth.attack}→{new_growth.attack}/级\n"
                f"🛡防御 {old_growth.defense}→{new_growth.defense}/级\n"
                f"❤生命 {old_growth.hp}→{new_growth.hp}/级\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 输入【进化宠物 确认】执行进化"
            )
            return True, msg

        # 确认进化：校验条件
        if pet.level < min_level:
            return False, f"⛔ 等级不足，需要 Lv.{min_level}（当前 Lv.{pet.level}）"

        from ..models.inventory import ItemInstance
        from sqlalchemy import func, select
        stmt = select(func.coalesce(func.sum(ItemInstance.quantity), 0)).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == cost_item
        )
        result = await uow.session.execute(stmt)
        have_qty = result.scalar() or 0
        if have_qty < cost_qty:
            return False, f"⛔ {item_name}不足，需要 {cost_qty} 个（拥有 {have_qty}）"

        from ..models.player import Player
        player = await uow.session.get(Player, player_id)
        if not player or player.resentment < cost_resentment:
            return False, f"⛔ 怨念不足，需要 {cost_resentment:,}"

        # 扣除材料
        await ItemInstance.consume_item(uow.session, player_id, cost_item, cost_qty)
        player.resentment -= cost_resentment

        # 执行进化：重算属性
        new_growth = self.config.get_growth(next_rarity)
        levels_gained = pet.level - 1  # 从Lv.1到当前等级的升级次数

        pet.bonus_attack = int(new_growth.attack * levels_gained)
        pet.bonus_defense = int(new_growth.defense * levels_gained)
        pet.bonus_hp = int(new_growth.hp * levels_gained)
        pet.bonus_crit_rate = new_growth.crit_rate * levels_gained
        pet.bonus_dodge_rate = new_growth.dodge_rate * levels_gained
        pet.evolved_rarity = next_rarity

        await uow.pets.update(pet)

        # 使宠物属性缓存失效
        from ..domain.attributes.attribute_calculator_factory import AttributeCalculatorFactory
        AttributeCalculatorFactory.invalidate_pet_cache(player_id)

        # 计算属性变化展示
        total_bonus = self._calculate_total_bonus(pet)

        msg = (
            f"🎉 进化成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"{cur_emoji}{cur_cn} → {next_emoji}{next_cn}\n"
            f"🐾 {pet.nickname} 的力量觉醒了！\n"
            f"━━━ 当前属性 ━━━\n"
            f"⚔攻击+{total_bonus['attack']} 🛡防御+{total_bonus['defense']}\n"
            f"❤生命+{total_bonus['hp']}\n"
            f"💥暴击+{total_bonus['crit_rate']:.1%} 👟闪避+{total_bonus['dodge_rate']:.1%}\n"
            f"━━━━━━━━━━━━━\n"
            f"📈 成长值已按{next_cn}标准重算"
        )
        return True, msg

    # ==================== 查看宠物 ====================

    @staticmethod
    def _progress_bar(value: int, max_val: int = 100, length: int = 10) -> str:
        """生成进度条"""
        filled = round(value / max_val * length) if max_val > 0 else 0
        filled = max(0, min(length, filled))
        return "▰" * filled + "▱" * (length - filled)

    @staticmethod
    def _mood_emoji(mood: int) -> str:
        """根据心情值返回表情"""
        if mood >= 80:
            return "😆"
        if mood >= 60:
            return "😊"
        if mood >= 40:
            return "😐"
        if mood >= 20:
            return "😟"
        return "😢"

    RARITY_DISPLAY = {
        "white": ("⚪", "普通"),
        "green": ("🟢", "优秀"),
        "blue": ("🔵", "稀有"),
        "purple": ("🟣", "史诗"),
        "orange": ("🟠", "传说"),
        "red": ("🔴", "神话"),
    }

    async def get_pet_info(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看当前伙伴信息"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伙伴诡兽，使用【驯化诡兽 名称 昵称】获取"

        beast = self.config.get_beast(pet.beast_id)
        level_name = self.config.get_affection_level_name(pet.affection)
        mood_mult = self.config.get_mood_multiplier(pet.mood)

        if pet.is_transformed:
            display_name = self.config.get_transform_name(pet.beast_id, pet.transform_gender)
        else:
            display_name = beast.name

        # 饰品展示行（分行显示，带slot emoji）
        SLOT_EMOJI = {"head": "👑", "neck": "📿", "body": "👗"}
        acc_line = ""
        if pet.accessories:
            acc_parts = []
            for slot, acc_id in pet.accessories.items():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    emoji = SLOT_EMOJI.get(slot, "✨")
                    acc_parts.append(f"{emoji}{acc.name}")
            if acc_parts:
                acc_line = f"  {' · '.join(acc_parts)}\n"

        total_bonus = self._calculate_total_bonus(pet)

        current_exp = pet.experience
        next_level_exp = self.config.get_exp_for_level(pet.level + 1)

        # 使用进化后稀有度（如有）
        current_rarity = pet.evolved_rarity or beast.rarity
        rarity_emoji, rarity_name = self.RARITY_DISPLAY.get(
            current_rarity, ("⚪", "普通")
        )
        status_icon = "🌾" if pet.is_guarding else "🐾"
        status_text = "守田中" if pet.is_guarding else "跟随中"
        if pet.is_transformed:
            status_text += " · ✨已化形"

        mood_emoji = self._mood_emoji(pet.mood)
        mood_bar = self._progress_bar(pet.mood)
        hunger_bar = self._progress_bar(pet.hunger)
        exp_bar = self._progress_bar(current_exp, next_level_exp)

        # 构建属性加成行
        bonus_parts = []
        if total_bonus['attack'] > 0:
            bonus_parts.append(f"⚔攻击+{total_bonus['attack']}")
        if total_bonus['defense'] > 0:
            bonus_parts.append(f"🛡防御+{total_bonus['defense']}")
        if total_bonus['hp'] > 0:
            bonus_parts.append(f"❤生命+{total_bonus['hp']}")

        rate_parts = []
        if total_bonus['crit_rate'] > 0:
            rate_parts.append(f"💥暴击+{total_bonus['crit_rate']:.1%}")
        if total_bonus['dodge_rate'] > 0:
            rate_parts.append(f"👟闪避+{total_bonus['dodge_rate']:.1%}")

        msg = (
            f"🐾 {pet.nickname}\n"
            f"{acc_line}"
            f"{rarity_emoji}{display_name} · Lv.{pet.level}\n"
            f"━━━━━━━━━━━━━\n"
            f"⭐ 经验 {exp_bar} {current_exp}/{next_level_exp}\n"
            f"{mood_emoji} 心情 {mood_bar} {pet.mood} (×{mood_mult:.1f})\n"
            f"🍖 饱食 {hunger_bar} {pet.hunger}\n"
            f"❤️ 好感 {pet.affection} · {level_name}\n"
            f"{status_icon} {status_text}\n"
            f"━━━ 战斗加成 ━━━\n"
            f"  {' '.join(bonus_parts)}\n"
            f"  {' '.join(rate_parts)}"
        )

        return True, msg

    async def get_pet_list(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看所有宠物"""
        pets = await uow.pets.get_all_by_player(player_id)
        if not pets:
            return False, "你还没有宠物，使用【驯化诡兽 名称 昵称】获取"

        msg = f"🐾 诡兽巢穴 ({len(pets)}只)\n━━━━━━━━━━━━━"
        for pet in pets:
            beast = self.config.get_beast(pet.beast_id)
            display_name = beast.transform_name if pet.is_transformed else beast.name
            rarity_emoji = self.RARITY_DISPLAY.get(beast.rarity, ("⚪",))[0]
            tags = []
            if pet.is_active:
                tags.append("💖伙伴")
            if pet.is_guarding:
                tags.append("🌾守田")
            tag_str = " ".join(tags)
            mood_emoji = self._mood_emoji(pet.mood)
            msg += (
                f"\n{rarity_emoji}#{pet.id} {pet.nickname}({display_name})"
                f" Lv.{pet.level} {mood_emoji}"
            )
            if tag_str:
                msg += f" {tag_str}"

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
        # 优先使用进化后的稀有度
        current_rarity = pet.evolved_rarity or beast.rarity
        growth = self.config.get_growth(current_rarity)
        if growth:
            pet.bonus_attack += int(growth.attack)
            pet.bonus_defense += int(growth.defense)
            pet.bonus_hp += int(growth.hp)
            pet.bonus_crit_rate += growth.crit_rate
            pet.bonus_dodge_rate += growth.dodge_rate

    def _calculate_total_bonus(self, pet: PetInstance) -> dict:
        """计算总属性加成（等级×心情倍率 + 饰品固定值）"""
        mood_mult = self.config.get_mood_multiplier(pet.mood)

        # 等级基础加成 × 心情倍率
        bonus = {
            "attack": int(pet.bonus_attack * mood_mult),
            "defense": int(pet.bonus_defense * mood_mult),
            "hp": int(pet.bonus_hp * mood_mult),
            "crit_rate": round(pet.bonus_crit_rate * mood_mult, 4),
            "dodge_rate": round(pet.bonus_dodge_rate * mood_mult, 4),
        }

        # 饰品加成（固定值，不受心情倍率影响）
        if pet.accessories:
            for acc_id in pet.accessories.values():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    for attr, value in acc.bonus.items():
                        if attr in bonus:
                            bonus[attr] += value

        return bonus
