"""
厨师服务 - 厨师招募和管理

提供:
- 随机生成厨师候选
- 雇佣和解雇厨师
- 厨师属性生成
"""

import random
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.chef import Chef, ChefCandidate, ChefTier, CookingCategory, ChefPersonality


class ChefService:
    """
    厨师服务 - 管理厨师招募、雇佣、解雇

    职责:
    - 生成随机厨师候选
    - 雇佣厨师到餐厅
    - 解雇厨师
    - 厨师属性生成和名字随机化
    - 招募冷却和费用管理
    """

    # 招募冷却时间配置（秒）
    BASE_RECRUIT_COOLDOWN = 4 * 60 * 60  # 4小时
    BASIC_CARD_REDUCTION = 1 * 60 * 60   # 基础月卡减少1小时
    PREMIUM_CARD_REDUCTION = 2 * 60 * 60 # 高级月卡减少2小时

    # 招募费用配置
    BASE_RECRUIT_COST = 500     # 基础费用
    RECRUIT_COST_SCALING = {    # 当日第N次招募费用
        0: 500,    # 首次
        1: 1000,   # 第2次(2倍)
        2: 2000,   # 第3次(4倍)
        3: 5000    # 第4次及以上(10倍)
    }

    # 候选过期时间
    CANDIDATE_EXPIRE_HOURS = 24  # 24小时后过期

    # 厨师等级配置
    CHEF_TIER_CONFIG = {
        ChefTier.APPRENTICE: {  # 学徒厨师
            "rarity": "white",
            "success_rate": 70,
            "fine_rate": 10,
            "perfect_rate": 2,
            "speed": 2,
            "salary": 20,
            "hire_cost": 500,
            "skill_range": (65, 75),
        },
        ChefTier.HELPER: {  # 帮厨
            "rarity": "green",
            "success_rate": 80,
            "fine_rate": 18,
            "perfect_rate": 5,
            "speed": 3,
            "salary": 50,
            "hire_cost": 2000,
            "skill_range": (75, 85),
        },
        ChefTier.COOK: {  # 厨师
            "rarity": "blue",
            "success_rate": 88,
            "fine_rate": 25,
            "perfect_rate": 10,
            "speed": 4,
            "salary": 120,
            "hire_cost": 8000,
            "skill_range": (83, 93),
        },
        ChefTier.HEAD_CHEF: {  # 大厨
            "rarity": "purple",
            "success_rate": 94,
            "fine_rate": 35,
            "perfect_rate": 18,
            "speed": 5,
            "salary": 300,
            "hire_cost": 30000,
            "skill_range": (89, 99),
        },
        ChefTier.MASTER_CHEF: {  # 特级厨师
            "rarity": "orange",
            "success_rate": 98,
            "fine_rate": 45,
            "perfect_rate": 28,
            "speed": 6,
            "salary": 800,
            "hire_cost": 100000,
            "skill_range": (93, 103),
        },
    }

    # 招募稀有度概率
    RECRUIT_RARITY_WEIGHTS = {
        ChefTier.APPRENTICE: 60,
        ChefTier.HELPER: 25,
        ChefTier.COOK: 10,
        ChefTier.HEAD_CHEF: 4,
        ChefTier.MASTER_CHEF: 1,
    }

    # 餐厅等级 → 可招募的最高厨师等级
    RECRUIT_TIER_CAP = {
        1: ChefTier.APPRENTICE,    # Lv.1-2: 最高学徒
        2: ChefTier.APPRENTICE,
        3: ChefTier.HELPER,        # Lv.3-4: 最高帮厨
        4: ChefTier.HELPER,
        5: ChefTier.COOK,          # Lv.5-6: 最高厨师
        6: ChefTier.COOK,
        7: ChefTier.HEAD_CHEF,     # Lv.7-8: 最高大厨
        8: ChefTier.HEAD_CHEF,
        9: ChefTier.MASTER_CHEF,   # Lv.9-10: 可招特级厨师
        10: ChefTier.MASTER_CHEF,
    }

    # 厨师等级顺序(用于比较和升级)
    TIER_ORDER = [
        ChefTier.APPRENTICE, ChefTier.HELPER, ChefTier.COOK,
        ChefTier.HEAD_CHEF, ChefTier.MASTER_CHEF
    ]

    # 厨师成长配置: {当前等级: 升级所需经验}
    PROMOTION_EXP = {
        ChefTier.APPRENTICE: 500,      # 学徒→帮厨
        ChefTier.HELPER: 1500,         # 帮厨→厨师
        ChefTier.COOK: 4000,           # 厨师→大厨
        ChefTier.HEAD_CHEF: 10000,     # 大厨→特级厨师
    }

    # 培训费用: {目标等级: 金币}
    PROMOTION_COST = {
        ChefTier.HELPER: 1000,
        ChefTier.COOK: 5000,
        ChefTier.HEAD_CHEF: 20000,
        ChefTier.MASTER_CHEF: 80000,
    }

    # 每次烹饪获得的经验
    EXP_PER_DISH_SUCCESS = 10   # 成功
    EXP_PER_DISH_PERFECT = 25   # 完美品质
    EXP_PER_DISH_FAIL = 3       # 失败也给少量经验

    # 厨师名字库
    CHEF_NAMES = [
        # 致敬神厨小福贵
        "小福贵", "阿旺", "陈大厨", "老王", "小李",
        # 经典厨师名
        "张师傅", "刘大厨", "王掌勺", "赵主厨", "李厨神",
        "孙帮厨", "周学徒", "吴大师", "郑烹饪", "钱煮饭",
        # 有趣的名字
        "火候王", "翻锅仙", "切菜侠", "调味精", "摆盘艺",
        "炒勺圣", "煎炸王", "蒸煮仙", "烤肉侠", "汤羹师",
    ]

    def __init__(self):
        pass

    async def check_recruit_cooldown(
        self,
        uow: UnitOfWork,
        restaurant_id: int,
        player_id: str
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        检查招募冷却时间

        Args:
            uow: 工作单元
            restaurant_id: 餐厅ID
            player_id: 玩家ID

        Returns:
            (是否可招募, 错误消息, 剩余冷却秒数)
        """
        restaurant = await uow.restaurants.get_by_id(restaurant_id)
        if not restaurant:
            return False, "⛔ 餐厅不存在", None

        # 如果从未招募过，可以招募
        if not restaurant.last_recruit_time:
            return True, None, None

        # 计算冷却时间（考虑月卡加成）
        from ..models.monthly_card import get_player_card_benefits

        benefits = await get_player_card_benefits(uow.session, player_id)
        cooldown_reduction = 0

        if benefits["premium_active"]:
            # 高级月卡：减少2小时
            cooldown_reduction = self.PREMIUM_CARD_REDUCTION
        elif benefits["basic_active"]:
            # 基础月卡：减少1小时
            cooldown_reduction = self.BASIC_CARD_REDUCTION

        effective_cooldown = self.BASE_RECRUIT_COOLDOWN - cooldown_reduction

        # 计算剩余冷却时间
        now = datetime.now()
        elapsed = (now - restaurant.last_recruit_time).total_seconds()
        remaining = int(effective_cooldown - elapsed)

        if remaining > 0:
            # 格式化剩余时间
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

            return False, f"⏰ 招募冷却中，剩余{time_str}", remaining
        else:
            return True, None, None

    def calculate_recruit_cost(self, restaurant) -> int:
        """
        计算本次招募费用（考虑当日招募次数）

        Args:
            restaurant: 餐厅实体

        Returns:
            招募费用
        """
        # 检查是否需要重置当日计数
        today = datetime.now().strftime("%Y-%m-%d")
        if restaurant.last_recruit_date != today:
            # 新的一天，重置计数
            return self.BASE_RECRUIT_COST

        # 根据当日招募次数计算费用
        count = restaurant.daily_recruit_count
        if count in self.RECRUIT_COST_SCALING:
            return self.RECRUIT_COST_SCALING[count]
        else:
            # 超过3次，使用最高档费用
            return self.RECRUIT_COST_SCALING[3]

    async def clean_expired_candidates(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> int:
        """
        清理过期的候选厨师

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            清理的数量
        """
        candidates = await uow.chef_candidates.get_by_player_id(player_id)
        if not candidates:
            return 0

        now = datetime.now()
        expired_count = 0

        for candidate in candidates:
            # 检查是否过期（24小时）
            if (now - candidate.created_at).total_seconds() > self.CANDIDATE_EXPIRE_HOURS * 3600:
                await uow.chef_candidates.delete(candidate)
                expired_count += 1

        if expired_count > 0:
            await uow.commit()

        return expired_count

    async def recruit_chefs(
        self,
        uow: UnitOfWork,
        player_id: str,
        restaurant_id: int,
        count: int = 4
    ) -> Tuple[bool, str, List[ChefCandidate]]:
        """
        招募厨师候选(生成随机候选列表)

        Args:
            uow: 工作单元
            player_id: 玩家ID
            restaurant_id: 餐厅ID
            count: 生成候选数量(3-5)

        Returns:
            (是否成功, 消息, 候选列表)
        """

        # 清除玩家旧的候选（包括过期的）
        await uow.chef_candidates.clear_by_player(player_id)

        # 获取餐厅等级用于限制可招募厨师等级
        restaurant = await uow.restaurants.get_by_id(restaurant_id)
        restaurant_level = restaurant.level if restaurant else 1

        # 生成新候选
        candidates = []
        for i in range(count):
            tier = self._roll_chef_tier(restaurant_level)
            candidate = self._generate_chef_candidate(player_id, tier)
            await uow.chef_candidates.add(candidate)
            candidates.append(candidate)

        # 更新餐厅招募状态
        restaurant = await uow.restaurants.get_by_id(restaurant_id)
        if restaurant:
            today = datetime.now().strftime("%Y-%m-%d")

            # 检查是否需要重置当日计数
            if restaurant.last_recruit_date != today:
                restaurant.daily_recruit_count = 0
                restaurant.last_recruit_date = today

            # 更新招募时间和次数
            restaurant.last_recruit_time = datetime.now()
            restaurant.daily_recruit_count += 1
            await uow.restaurants.update(restaurant)

        await uow.commit()

        # 生成展示消息
        max_tier = self.RECRUIT_TIER_CAP.get(restaurant_level, ChefTier.MASTER_CHEF)
        max_tier_name = self._get_tier_name(max_tier)
        msg = "🎲 厨师招募中...\n"
        msg += f"📍 餐厅Lv.{restaurant_level}，最高可招募: {max_tier_name}\n\n"
        msg += "以下是本次候选厨师:\n\n"

        for idx, candidate in enumerate(candidates, 1):
            config = self.CHEF_TIER_CONFIG[candidate.tier]
            tier_name = self._get_tier_name(candidate.tier)
            specialty_name = self._get_category_name(candidate.specialty)
            personality_name = self._get_personality_name(candidate.personality)

            msg += f"【{idx}】 {candidate.name} ({tier_name})\n"
            msg += f"  🔹 厨艺: {candidate.skill} | 速度: {candidate.speed}道/时\n"
            msg += f"  🔹 擅长: {specialty_name} | 性格: {personality_name}\n"
            msg += f"  💰 时薪: {candidate.salary}金 | 签约费: {config['hire_cost']}金\n\n"

        msg += "⏰ 候选有效期: 24小时\n"
        msg += "使用【雇佣 编号】来选择雇佣"

        return True, msg, candidates

    async def hire_chef(
        self,
        uow: UnitOfWork,
        player_id: str,
        candidate_index: int,
        restaurant_id: int
    ) -> Tuple[bool, str]:
        """
        雇佣候选厨师

        Args:
            uow: 工作单元
            player_id: 玩家ID
            candidate_index: 候选编号(1-based)
            restaurant_id: 餐厅ID

        Returns:
            (是否成功, 消息)
        """

        # 获取候选列表
        candidates = await uow.chef_candidates.get_by_player_id(player_id)

        if not candidates:
            return False, "⛔ 当前没有待雇佣的候选厨师，请先使用【招募厨师】"

        if candidate_index < 1 or candidate_index > len(candidates):
            return False, f"⛔ 编号无效，请选择 1~{len(candidates)} 之间的编号"

        candidate = candidates[candidate_index - 1]

        # 检查餐厅是否存在
        restaurant = await uow.restaurants.get_by_id(restaurant_id)
        if not restaurant:
            return False, "⛔ 餐厅不存在"

        # 检查厨师上限
        current_chef_count = await uow.chefs.count_by_restaurant(restaurant_id)
        if current_chef_count >= restaurant.max_chefs:
            return False, f"⛔ 厨师已达上限 ({restaurant.max_chefs}人)，请先解雇或升级餐厅"

        # 检查是否已有同名厨师
        existing_chef = await uow.chefs.get_by_name(restaurant_id, candidate.name)
        if existing_chef:
            return False, f"⛔ 餐厅已有名为【{candidate.name}】的厨师"

        # 检查玩家金币
        player = await uow.players.get_by_id(player_id)
        hire_cost = self.CHEF_TIER_CONFIG[candidate.tier]["hire_cost"]

        if player.gold < hire_cost:
            return False, f"⛔ 签约费不足! 需要 {hire_cost}金币"

        # 扣除签约费
        player.gold -= hire_cost
        await uow.players.update(player)

        # 创建厨师
        chef = Chef(
            restaurant_id=restaurant_id,
            name=candidate.name,
            tier=candidate.tier,
            skill=candidate.skill,
            speed=candidate.speed,
            specialty=candidate.specialty,
            personality=candidate.personality,
            salary=candidate.salary,
            hired_at=datetime.now()
        )
        await uow.chefs.add(chef)

        # 清除候选列表
        await uow.chef_candidates.clear_by_player(player_id)

        await uow.commit()

        tier_name = self._get_tier_name(chef.tier)
        return True, f"✅ 成功雇佣【{chef.name}】({tier_name})! 支付签约费 {hire_cost}金币"

    async def fire_chef(
        self,
        uow: UnitOfWork,
        restaurant_id: int,
        chef_name: str
    ) -> Tuple[bool, str]:
        """
        解雇厨师

        Args:
            uow: 工作单元
            restaurant_id: 餐厅ID
            chef_name: 厨师名字

        Returns:
            (是否成功, 消息)
        """

        chef = await uow.chefs.get_by_name(restaurant_id, chef_name)
        if not chef:
            return False, f"⛔ 未找到名为【{chef_name}】的厨师"

        await uow.chefs.delete(chef)
        await uow.commit()

        return True, f"✅ 已解雇【{chef_name}】(不退还签约费)"

    async def get_restaurant_chefs(
        self,
        uow: UnitOfWork,
        restaurant_id: int
    ) -> List[Chef]:
        """
        获取餐厅的所有厨师

        Args:
            uow: 工作单元
            restaurant_id: 餐厅ID

        Returns:
            厨师列表
        """
        return await uow.chefs.get_by_restaurant_id(restaurant_id)

    async def promote_chef(
        self,
        uow: UnitOfWork,
        player_id: str,
        restaurant_id: int,
        chef_name: str
    ) -> Tuple[bool, str]:
        """
        培训厨师(升级到下一等级)

        需要满足:
        - 经验值达到要求
        - 玩家金币足够支付培训费

        Returns:
            (是否成功, 消息)
        """
        chef = await uow.chefs.get_by_name(restaurant_id, chef_name)
        if not chef:
            return False, f"⛔ 未找到名为【{chef_name}】的厨师"

        current_tier = ChefTier(chef.tier)
        current_idx = self.TIER_ORDER.index(current_tier)

        # 已是最高等级
        if current_idx >= len(self.TIER_ORDER) - 1:
            return False, f"⛔ 【{chef_name}】已是特级厨师，无法再升级"

        # 检查经验是否足够
        required_exp = self.PROMOTION_EXP.get(current_tier)
        if required_exp is None:
            return False, f"⛔ 【{chef_name}】无法升级"

        if chef.experience < required_exp:
            return False, (
                f"⛔ 【{chef_name}】经验不足\n"
                f"当前经验: {chef.experience}/{required_exp}\n"
                f"💡 厨师在营业中做菜可积累经验"
            )

        # 检查金币
        next_tier = self.TIER_ORDER[current_idx + 1]
        cost = self.PROMOTION_COST.get(next_tier, 0)

        player = await uow.players.get_by_id(player_id)
        if not player:
            return False, "⛔ 玩家不存在"

        if player.gold < cost:
            return False, f"⛔ 培训费不足! 需要 {cost}金币"

        # 执行升级
        player.gold -= cost
        await uow.players.update(player)

        old_tier_name = self._get_tier_name(current_tier)
        new_tier_name = self._get_tier_name(next_tier)

        # 更新厨师属性
        new_config = self.CHEF_TIER_CONFIG[next_tier]
        chef.tier = next_tier
        chef.experience = 0  # 重置经验
        chef.skill = max(chef.skill, new_config["skill_range"][0])  # 技能至少达到新等级下限
        chef.speed = new_config["speed"]
        chef.salary = new_config["salary"]
        await uow.chefs.update(chef)

        await uow.commit()

        return True, (
            f"🎉 培训成功!\n"
            f"【{chef_name}】 {old_tier_name} → {new_tier_name}\n"
            f"  厨艺: {chef.skill} | 速度: {chef.speed}道/时\n"
            f"  时薪: {chef.salary}金\n"
            f"💰 支付培训费: {cost}金币"
        )

    def add_chef_experience(self, chef, exp_amount: int) -> Tuple[int, bool]:
        """
        给厨师增加经验值

        Args:
            chef: 厨师对象
            exp_amount: 经验值

        Returns:
            (实际增加的经验, 是否可以升级)
        """
        current_tier = ChefTier(chef.tier)
        chef.experience += exp_amount

        # 检查是否可以升级
        required_exp = self.PROMOTION_EXP.get(current_tier)
        can_promote = required_exp is not None and chef.experience >= required_exp

        return exp_amount, can_promote

    # ==================== 私有方法 ====================

    def _roll_chef_tier(self, restaurant_level: int = 10) -> str:
        """随机roll厨师等级(根据稀有度权重，受餐厅等级限制)"""
        max_tier = self.RECRUIT_TIER_CAP.get(restaurant_level, ChefTier.MASTER_CHEF)
        max_idx = self.TIER_ORDER.index(max_tier)

        # 只保留不超过上限的等级
        tiers = []
        weights = []
        for tier, weight in self.RECRUIT_RARITY_WEIGHTS.items():
            if self.TIER_ORDER.index(tier) <= max_idx:
                tiers.append(tier)
                weights.append(weight)

        return random.choices(tiers, weights=weights, k=1)[0]

    def _generate_chef_candidate(self, player_id: str, tier: str) -> ChefCandidate:
        """生成随机厨师候选"""
        config = self.CHEF_TIER_CONFIG[tier]

        # 随机名字
        name = random.choice(self.CHEF_NAMES)

        # 随机厨艺(同等级内有浮动)
        skill = random.randint(*config["skill_range"])

        # 随机擅长类别
        specialty = random.choice([
            CookingCategory.FISH,
            CookingCategory.SOUP,
            CookingCategory.GRILL,
            CookingCategory.STEAM,
            CookingCategory.DESSERT
        ])

        # 随机性格
        personality = random.choice([
            ChefPersonality.DILIGENT,
            ChefPersonality.LAZY,
            ChefPersonality.PERFECTIONIST,
            ChefPersonality.FRUGAL,
            ChefPersonality.TALKATIVE
        ])

        return ChefCandidate(
            player_id=player_id,
            name=name,
            tier=tier,
            skill=skill,
            speed=config["speed"],
            specialty=specialty,
            personality=personality,
            salary=config["salary"],
            created_at=datetime.now()
        )

    def _get_tier_name(self, tier: str) -> str:
        """获取厨师等级中文名"""
        names = {
            ChefTier.APPRENTICE: "学徒厨师",
            ChefTier.HELPER: "帮厨",
            ChefTier.COOK: "厨师",
            ChefTier.HEAD_CHEF: "大厨",
            ChefTier.MASTER_CHEF: "特级厨师"
        }
        return names.get(tier, tier)

    def _get_category_name(self, category: str) -> str:
        """获取烹饪类别中文名"""
        names = {
            CookingCategory.FISH: "鱼鲜类",
            CookingCategory.SOUP: "汤煲类",
            CookingCategory.GRILL: "烤制类",
            CookingCategory.STEAM: "蒸煮类",
            CookingCategory.DESSERT: "甜点类"
        }
        return names.get(category, category)

    def _get_personality_name(self, personality: str) -> str:
        """获取性格中文名"""
        names = {
            ChefPersonality.DILIGENT: "勤劳",
            ChefPersonality.LAZY: "懒散",
            ChefPersonality.PERFECTIONIST: "完美主义",
            ChefPersonality.FRUGAL: "节俭",
            ChefPersonality.TALKATIVE: "话痨"
        }
        return names.get(personality, personality)
