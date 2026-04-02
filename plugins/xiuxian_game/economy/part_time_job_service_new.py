"""打工系统核心服务 - DI重构版本

功能：
1. 工作地点管理
2. 工作执行和奖励计算（含评级、熟练度、道具掉落）
3. 玩家打工状态管理
4. 特殊事件处理（加班/摸鱼/同事求助等）
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.part_time_job_repository import PartTimeJobRepository
from ..infrastructure.repositories.job_location_repository import JobLocationRepository
from ..infrastructure.repositories.player_job_stats_repository import PlayerJobStatsRepository
from ..models.player import Player
from ..models.part_time_job import PartTimeJob, JobLocation, PlayerJobStats
from ..utils import luck_prob


class PartTimeJobService:
    """打工系统核心服务类 - DI版本"""

    # ==================== 熟练度系统 ====================
    PROFICIENCY_LEVELS = [
        {"name": "学徒", "icon": "🔰", "threshold": 0, "bonus": 0.0},
        {"name": "熟手", "icon": "⭐", "threshold": 5, "bonus": 0.15},
        {"name": "专家", "icon": "🌟", "threshold": 15, "bonus": 0.35},
        {"name": "大师", "icon": "👑", "threshold": 30, "bonus": 0.60},
    ]

    # ==================== 评级系统 ====================
    # 评级概率基础权重 (会被熟练度和运气修正)
    RATING_CONFIG = {
        "S": {"icon": "🏆S", "multiplier": 3.0, "base_weight": 3},
        "A": {"icon": "⭐A", "multiplier": 2.0, "base_weight": 12},
        "B": {"icon": "✅B", "multiplier": 1.5, "base_weight": 30},
        "C": {"icon": "📋C", "multiplier": 1.0, "base_weight": 40},
        "D": {"icon": "💤D", "multiplier": 0.7, "base_weight": 15},
    }

    # ==================== 道具掉落表 ====================
    ITEM_DROP_TABLE = [
        # (item_id, name, quantity, weight, proficiency_min)
        ("inscription_fragment", "铭文碎片", 1, 15, 0),
        ("bone_fragment", "骨片", 3, 25, 0),
        ("ash_powder", "灰烬", 3, 25, 0),
        ("ghost_tears", "鬼泪", 2, 20, 1),
        ("spirit_bone", "灵骨", 2, 15, 1),
        ("rotten_core", "腐坏的内丹", 1, 12, 2),
        ("life_recovery_elixir", "回生丹", 1, 8, 2),
        ("soul_recovery_elixir", "凝魂丹", 1, 8, 2),
        ("spirit_elixir", "升灵丹", 1, 5, 3),
    ]

    # 工作类型配置 - 基础报酬已提升50%
    JOB_TYPES = {
        "cashier": {
            "name": "便利店收银员",
            "description": "在便利店负责收银和简单服务工作",
            "base_reward": 120,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🏪",
            "special_events": [
                {"name": "遇到好心顾客", "probability": 0.15, "bonus": 50, "description": "顾客给了小费"},
                {"name": "找到遗失钱包", "probability": 0.05, "bonus": 150, "description": "在店里找到钱包，老板奖励了你"},
                {"name": "收银出错", "probability": 0.08, "bonus": -30, "description": "找错钱被扣了工资"},
                {"name": "加班请求", "probability": 0.12, "bonus": 100, "description": "同事请假，老板让你顶班，额外加了工资"},
            ]
        },
        "delivery_sorter": {
            "name": "快递分拣员",
            "description": "在快递站负责包裹分拣工作",
            "base_reward": 180,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 1,
            "emoji": "📦",
            "special_events": [
                {"name": "效率奖励", "probability": 0.2, "bonus": 60, "description": "工作效率很高，获得效率奖金"},
                {"name": "加班费", "probability": 0.1, "bonus": 120, "description": "主动加班获得额外报酬"},
                {"name": "摸鱼被抓", "probability": 0.06, "bonus": -40, "description": "偷偷刷手机被主管逮到，扣了绩效"},
                {"name": "双十一爆单", "probability": 0.08, "bonus": 160, "description": "快递爆仓！加班分拣赚了双倍"},
            ]
        },
        "coffee_server": {
            "name": "咖啡店服务员",
            "description": "在咖啡店为顾客提供服务",
            "base_reward": 150,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 5,
            "emoji": "☕",
            "special_events": [
                {"name": "制作完美咖啡", "probability": 0.18, "bonus": 80, "description": "拉花完美，顾客赞不绝口"},
                {"name": "遇到网红", "probability": 0.03, "bonus": 300, "description": "网红打卡你的咖啡，老板大方发了奖金"},
                {"name": "打翻咖啡", "probability": 0.07, "bonus": -50, "description": "手滑打翻了一杯，赔了材料费"},
                {"name": "同事求助", "probability": 0.10, "bonus": 100, "description": "帮同事顶了半小时班，拿到感谢费"},
            ]
        },
        "factory_worker": {
            "name": "工厂流水线工人",
            "description": "在工厂流水线上进行重复性工作",
            "base_reward": 220,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 1,
            "emoji": "🔧",
            "special_events": [
                {"name": "零缺陷奖励", "probability": 0.12, "bonus": 90, "description": "工作零缺陷，获得质量奖金"},
                {"name": "技能提升", "probability": 0.08, "bonus": 150, "description": "掌握了新技能，获得技能奖金"},
                {"name": "机器故障", "probability": 0.06, "bonus": -30, "description": "机器突然坏了，等维修耽误了时间"},
                {"name": "赶工加班", "probability": 0.10, "bonus": 180, "description": "订单催得急，老板开了三倍加班费"},
            ]
        },
        "cargo_handler": {
            "name": "安全屋建造",
            "description": "负责使用黄金建造安全屋，隔绝灵异力量，用于临时避难",
            "base_reward": 270,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 3,
            "emoji": "🚛",
            "special_events": [
                {"name": "体力奖励", "probability": 0.15, "bonus": 100, "description": "体力充沛，完成额外工作"},
                {"name": "安全奖励", "probability": 0.1, "bonus": 130, "description": "工作期间零事故，获得安全奖金"},
                {"name": "好评奖励", "probability": 0.1, "bonus": 160, "description": "买你安全屋的都默认打了好评"},
                {"name": "材料短缺", "probability": 0.05, "bonus": -50, "description": "材料不够只好返工，白忙活半天"},
            ]
        },
        "quality_inspector": {
            "name": "质检员",
            "description": "负责产品质量检查工作",
            "base_reward": 210,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 8,
            "emoji": "🔍",
            "special_events": [
                {"name": "发现重大问题", "probability": 0.1, "bonus": 180, "description": "发现了重大质量问题，避免了损失"},
                {"name": "专业认可", "probability": 0.12, "bonus": 120, "description": "专业能力获得认可"},
                {"name": "误判罚款", "probability": 0.05, "bonus": -60, "description": "把合格品误判了，被扣了奖金"},
            ]
        },
        "internet_cafe_manager": {
            "name": "网吧管理员",
            "description": "负责网吧的日常管理工作",
            "base_reward": 135,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🎮",
            "special_events": [
                {"name": "维护设备", "probability": 0.2, "bonus": 50, "description": "成功维护了设备"},
                {"name": "调解纠纷", "probability": 0.08, "bonus": 90, "description": "成功调解了顾客纠纷，老板夸了你"},
                {"name": "偷玩游戏", "probability": 0.08, "bonus": -25, "description": "忍不住开了一把游戏，被监控拍到了"},
                {"name": "通宵值守", "probability": 0.10, "bonus": 110, "description": "通宵班没人愿意上，你顶了上去"},
            ]
        },
        "cinema_usher": {
            "name": "电影院检票员",
            "description": "在电影院负责检票和引导工作",
            "base_reward": 128,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 1,
            "emoji": "🍿",
            "special_events": [
                {"name": "明星签名", "probability": 0.02, "bonus": 400, "description": "遇到明星首映，签名转手卖了大价钱"},
                {"name": "优质服务", "probability": 0.15, "bonus": 60, "description": "服务态度获得好评"},
                {"name": "蹭电影", "probability": 0.10, "bonus": -20, "description": "偷偷看了半场电影，被经理发现扣了钱"},
            ]
        },
        "street_performer_assistant": {
            "name": "街头表演助手",
            "description": "协助街头艺人进行表演",
            "base_reward": 90,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🎪",
            "special_events": [
                {"name": "表演成功", "probability": 0.25, "bonus": 120, "description": "表演大获成功，收入丰厚"},
                {"name": "观众打赏", "probability": 0.3, "bonus": 60, "description": "观众额外打赏"},
                {"name": "表演失败", "probability": 0.1, "bonus": -30, "description": "表演效果不佳，收入减少"},
                {"name": "富豪打赏", "probability": 0.03, "bonus": 350, "description": "一位富豪路过，随手扔了一大把钱"},
            ]
        },
        "delivery_driver": {
            "name": "配送司机",
            "description": "负责货物配送和运输工作",
            "base_reward": 240,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 5,
            "emoji": "🚚",
            "special_events": [
                {"name": "准时送达", "probability": 0.2, "bonus": 80, "description": "准时送达获得时效奖金"},
                {"name": "客户好评", "probability": 0.15, "bonus": 100, "description": "服务态度好获得客户好评奖励"},
                {"name": "交通罚单", "probability": 0.05, "bonus": -60, "description": "为了赶时间闯了红灯，罚单自付"},
                {"name": "顺风单", "probability": 0.08, "bonus": 140, "description": "捎了个顺风单，白赚一笔"},
            ]
        },
        "warehouse_keeper": {
            "name": "仓库管理员",
            "description": "负责仓库货物管理和盘点工作",
            "base_reward": 195,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 3,
            "emoji": "📋",
            "special_events": [
                {"name": "盘点准确", "probability": 0.18, "bonus": 90, "description": "盘点工作准确无误"},
                {"name": "发现问题", "probability": 0.12, "bonus": 120, "description": "发现库存问题并及时处理"},
                {"name": "效率提升", "probability": 0.15, "bonus": 70, "description": "工作效率高获得效率奖金"},
                {"name": "货物损坏", "probability": 0.05, "bonus": -40, "description": "搬货的时候不小心摔了一箱"},
            ]
        }
    }

    # 工作地点配置 - 整合到相应城镇中
    JOB_LOCATIONS = {
        "business_center": {
            "location_id": "business_center",
            "name": "上京商业中心",
            "description": "繁华的商业区，有各种服务业工作机会",
            "x": 0,  # 上京
            "y": 0,
            "available_jobs": ["cashier", "coffee_server", "cinema_usher"],
            "required_level": 1
        },
        "industrial_zone": {
            "location_id": "industrial_zone",
            "name": "荔湾镇工业区",
            "description": "工厂集中的工业区，体力劳动较多",
            "x": 120,  # 荔湾镇
            "y": 200,
            "available_jobs": ["factory_worker", "cargo_handler", "quality_inspector"],
            "required_level": 1
        },
        "entertainment_district": {
            "location_id": "entertainment_district",
            "name": "郸城娱乐街区",
            "description": "充满活力的娱乐区，工作轻松有趣",
            "x": 120,  # 郸城
            "y": 120,
            "available_jobs": ["internet_cafe_manager", "cinema_usher", "street_performer_assistant"],
            "required_level": 1
        },
        "logistics_center": {
            "location_id": "logistics_center",
            "name": "东郊物流中心",
            "description": "物流配送中心，负责货物运输和仓储",
            "x": 390,  # 东郊
            "y": 50,
            "available_jobs": ["delivery_driver", "warehouse_keeper", "cargo_handler"],
            "required_level": 1
        }
    }

    def __init__(
        self,
        player_repo: PlayerRepository,
        part_time_job_repo: PartTimeJobRepository,
        job_location_repo: JobLocationRepository,
        player_job_stats_repo: PlayerJobStatsRepository
    ):
        """
        初始化打工服务

        Args:
            player_repo: 玩家仓储
            part_time_job_repo: 打工记录仓储
            job_location_repo: 工作地点仓储
            player_job_stats_repo: 玩家打工统计仓储
        """
        self._player_repo = player_repo
        self._part_time_job_repo = part_time_job_repo
        self._job_location_repo = job_location_repo
        self._player_job_stats_repo = player_job_stats_repo

    async def initialize_job_locations(self) -> None:
        """初始化工作地点数据"""
        for location_data in self.JOB_LOCATIONS.values():
            # 检查是否已存在
            existing = await self._job_location_repo.get_by_location_id(
                location_data["location_id"]
            )

            if not existing:
                # 创建新的工作地点
                location = JobLocation(
                    location_id=location_data["location_id"],
                    name=location_data["name"],
                    description=location_data["description"],
                    x=location_data["x"],
                    y=location_data["y"],
                    required_level=location_data["required_level"],
                    available_jobs={
                        job_type: self.JOB_TYPES[job_type] for job_type in location_data["available_jobs"]
                    }
                )
                await self._job_location_repo.add(location)

    async def get_available_jobs_at_location(self, player: Player) -> Tuple[bool, str, List[Dict]]:
        """获取玩家当前位置可用的工作（含熟练度信息）"""
        if player.region != "大都会":
            return False, "只有在大都会才能打工", []

        current_x, current_y = player.get_current_coordinates()
        location = await self._job_location_repo.get_by_coordinates(current_x, current_y)

        if not location:
            return False, "当前位置没有工作机会", []

        if player.level < location.required_level:
            return False, f"等级不足，需要{location.required_level}级", []

        # 获取熟练度数据
        stats = await self._player_job_stats_repo.get_or_create(player.id)
        proficiency = stats.job_proficiency or {}

        available_jobs = []
        for job_type, job_config in location.available_jobs.items():
            if player.level >= job_config.get("required_level", 1):
                job_prof = proficiency.get(job_type, {"count": 0, "level": 0})
                prof_info = self.get_proficiency_level(job_prof.get("count", 0))
                next_level = None
                prof_idx = self.get_proficiency_level_index(job_prof.get("count", 0))
                if prof_idx < len(self.PROFICIENCY_LEVELS) - 1:
                    next_level = self.PROFICIENCY_LEVELS[prof_idx + 1]

                available_jobs.append({
                    "job_type": job_type,
                    "name": job_config["name"],
                    "description": job_config["description"],
                    "base_reward": job_config["base_reward"],
                    "duration_hours": job_config["duration_hours"],
                    "emoji": job_config["emoji"],
                    "proficiency": prof_info,
                    "proficiency_count": job_prof.get("count", 0),
                    "next_level": next_level,
                })

        return True, f"在{location.name}找到{len(available_jobs)}个工作机会", available_jobs

    async def start_job(self, player: Player, job_type: str) -> Tuple[bool, str, Optional[PartTimeJob]]:
        """开始工作"""
        # 检查是否已在工作
        current_job = await self._part_time_job_repo.get_current_working_job(player.id)

        if current_job:
            remaining = current_job.get_remaining_time()
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return False, f"你正在工作中，剩余时间：{hours}小时{minutes}分钟", None

        # 检查工作类型是否存在
        if job_type not in self.JOB_TYPES:
            return False, "工作类型不存在", None

        job_config = self.JOB_TYPES[job_type]

        # 检查等级要求
        if player.level < job_config["required_level"]:
            return False, f"等级不足，需要{job_config['required_level']}级", None

        # 检查当前位置是否有这个工作
        success, msg, available_jobs = await self.get_available_jobs_at_location(player)
        if not success:
            return False, msg, None

        job_available = any(job["job_type"] == job_type for job in available_jobs)
        if not job_available:
            return False, "当前位置没有这个工作", None

        # 获取工作地点 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        location = await self._job_location_repo.get_by_coordinates(current_x, current_y)

        # 创建工作记录
        now = datetime.now()
        end_time = now + timedelta(hours=job_config["duration_hours"])

        # 如果有未完成的工作记录，先完成它
        if current_job:
            current_job.is_working = False
            current_job.completed_time = now
            await self._part_time_job_repo.update(current_job)

        new_job = PartTimeJob(
            player_id=player.id,
            job_location_id=location.location_id,
            job_type=job_type,
            is_working=True,
            start_time=now,
            end_time=end_time,
            work_duration_hours=job_config["duration_hours"]
        )

        new_job = await self._part_time_job_repo.add(new_job)

        # 格式化时间显示
        duration = job_config['duration_hours']
        if duration < 1:
            minutes = round(duration * 60, 1)
            if minutes == int(minutes):
                time_str = f"{int(minutes)}分钟"
            else:
                time_str = f"{minutes}分钟"
        else:
            time_str = f"{duration}小时"

        return True, f"开始工作：{job_config['name']}，预计{time_str}后完成", new_job

    # ==================== 熟练度辅助方法 ====================

    @classmethod
    def get_proficiency_level(cls, count: int) -> Dict:
        """根据完成次数返回熟练度等级信息"""
        result = cls.PROFICIENCY_LEVELS[0]
        for level in cls.PROFICIENCY_LEVELS:
            if count >= level["threshold"]:
                result = level
        return result

    @classmethod
    def get_proficiency_level_index(cls, count: int) -> int:
        """返回熟练度等级索引 (0~3)"""
        idx = 0
        for i, level in enumerate(cls.PROFICIENCY_LEVELS):
            if count >= level["threshold"]:
                idx = i
        return idx

    @classmethod
    def calculate_rating(cls, proficiency_idx: int, luck_value: int) -> Tuple[str, Dict]:
        """根据熟练度和运气计算评级"""
        weights = {}
        for rating, cfg in cls.RATING_CONFIG.items():
            weights[rating] = cfg["base_weight"]

        # 熟练度提升高评级概率: 每级 +3 S权重, +5 A权重
        weights["S"] += proficiency_idx * 3
        weights["A"] += proficiency_idx * 5
        weights["D"] = max(1, weights["D"] - proficiency_idx * 4)

        # 运气加成: luck_prob 返回 0~1
        luck_bonus = luck_prob(luck_value)
        weights["S"] += int(luck_bonus * 8)
        weights["A"] += int(luck_bonus * 10)
        weights["D"] = max(1, weights["D"] - int(luck_bonus * 8))

        # 加权随机选择
        total = sum(weights.values())
        roll = random.randint(1, total)
        cumulative = 0
        for rating, w in weights.items():
            cumulative += w
            if roll <= cumulative:
                return rating, cls.RATING_CONFIG[rating]
        # fallback
        return "C", cls.RATING_CONFIG["C"]

    @classmethod
    def roll_item_drop(cls, proficiency_idx: int, luck_value: int) -> Optional[Dict]:
        """掉落道具判定"""
        # 基础掉落率 12%, 每级熟练度 +4%, 运气额外 +0~8%
        drop_chance = 0.12 + proficiency_idx * 0.04 + luck_prob(luck_value) * 0.08
        if random.random() > drop_chance:
            return None

        # 筛选当前熟练度可掉落的物品
        eligible = [item for item in cls.ITEM_DROP_TABLE if proficiency_idx >= item[4]]
        if not eligible:
            return None

        # 加权随机
        total_weight = sum(item[3] for item in eligible)
        roll = random.randint(1, total_weight)
        cumulative = 0
        for item_id, name, qty, weight, _ in eligible:
            cumulative += weight
            if roll <= cumulative:
                return {"item_id": item_id, "name": name, "quantity": qty}
        return None

    async def complete_job(self, player: Player) -> Tuple[bool, str, Optional[Dict]]:
        """
        完成工作并获得奖励（带行锁，防止并发领取）
        包含: 熟练度升级、评级翻倍、道具掉落、特殊事件
        """
        # 查找当前工作
        current_job = await self._part_time_job_repo.get_current_working_job(player.id)

        if not current_job:
            return False, "你当前没有在工作", None

        if not current_job.is_completed():
            remaining = current_job.get_remaining_time()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return False, f"工作尚未完成，剩余时间：{hours}小时{minutes}分钟", None

        # 先标记为已完成，防止重复领取
        current_job.is_working = False
        current_job.completed_time = datetime.now()
        await self._part_time_job_repo.update(current_job)
        await self._part_time_job_repo._session.flush()

        job_config = self.JOB_TYPES[current_job.job_type]
        base_reward = job_config["base_reward"]

        # ====== 熟练度系统 ======
        stats = await self._player_job_stats_repo.get_or_create(player.id)
        proficiency = stats.job_proficiency or {}
        job_prof = proficiency.get(current_job.job_type, {"count": 0, "level": 0})
        old_prof_idx = self.get_proficiency_level_index(job_prof["count"])
        job_prof["count"] = job_prof.get("count", 0) + 1
        new_prof_idx = self.get_proficiency_level_index(job_prof["count"])
        job_prof["level"] = new_prof_idx
        proficiency[current_job.job_type] = job_prof
        # 重新赋值整个字段，确保 SQLAlchemy 检测到变化
        stats.job_proficiency = dict(proficiency)

        prof_level_info = self.get_proficiency_level(job_prof["count"])
        proficiency_bonus = prof_level_info["bonus"]  # 0% ~ 60%
        leveled_up = new_prof_idx > old_prof_idx

        # ====== 基础奖励计算 ======
        # 等级加成 (每级增加3%)
        level_bonus = int(base_reward * (player.level - 1) * 0.03)

        # 运气加成 (最多50%)
        luck_multiplier = 1 + luck_prob(player.luck) * 0.5

        # 连续工作奖励 (每天连续+10金币, 最多200)
        consecutive_bonus = min(stats.current_streak * 10, 200)

        # 熟练度加成
        prof_reward_bonus = int(base_reward * proficiency_bonus)

        # 基础金币(评级前)
        pre_rating_gold = int((base_reward + level_bonus + prof_reward_bonus) * luck_multiplier) + consecutive_bonus

        # ====== 评级系统 ======
        rating_key, rating_cfg = self.calculate_rating(new_prof_idx, player.luck)
        rating_multiplier = rating_cfg["multiplier"]
        rated_gold = int(pre_rating_gold * rating_multiplier)

        # ====== 特殊事件 ======
        special_event = None
        bonus_reward = 0
        for event in job_config.get("special_events", []):
            if random.random() < event["probability"]:
                special_event = event
                bonus_reward = event["bonus"]
                break

        # ====== 道具掉落 ======
        dropped_item = self.roll_item_drop(new_prof_idx, player.luck)
        if dropped_item:
            from ..models.inventory import ItemInstance
            await ItemInstance.add_item(
                self._player_repo._session,
                player.id,
                dropped_item["item_id"],
                dropped_item["quantity"]
            )

        # ====== 最终奖励 ======
        total_reward = max(rated_gold + bonus_reward, 1)  # 至少1金币

        current_job.base_reward = pre_rating_gold
        current_job.bonus_reward = bonus_reward
        current_job.total_reward = total_reward
        if special_event:
            current_job.special_event = special_event["description"]

        # 发放金币
        player.gold += total_reward
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(
            self._player_repo._session, player.id,
            "gold_earned_total", increment=total_reward, auto_commit=False
        )
        await self._player_repo.update(player)

        # 更新统计
        stats.total_jobs_completed += 1
        stats.total_earnings += total_reward
        stats.total_work_hours += current_job.work_duration_hours
        stats.update_streak(datetime.now())
        await self.update_job_preferences(stats, current_job.job_type, current_job.job_location_id)

        await self._part_time_job_repo.update(current_job)
        await self._player_job_stats_repo.update(stats)

        # 构建结果
        result = {
            "job_name": job_config["name"],
            "base_reward": pre_rating_gold,
            "bonus_reward": bonus_reward,
            "total_reward": total_reward,
            "special_event": special_event,
            "level_bonus": level_bonus,
            "luck_multiplier": luck_multiplier,
            "consecutive_bonus": consecutive_bonus,
            "current_streak": stats.current_streak,
            # 新增字段
            "rating": rating_key,
            "rating_icon": rating_cfg["icon"],
            "rating_multiplier": rating_multiplier,
            "proficiency": prof_level_info,
            "proficiency_count": job_prof["count"],
            "proficiency_bonus": proficiency_bonus,
            "leveled_up": leveled_up,
            "dropped_item": dropped_item,
        }

        return True, "工作完成！", result

    async def get_current_job_status(self, player: Player) -> Tuple[bool, str, Optional[Dict]]:
        """获取当前工作状态"""
        current_job = await self._part_time_job_repo.get_current_working_job(player.id)

        if not current_job:
            return False, "当前没有在工作", None

        job_config = self.JOB_TYPES[current_job.job_type]
        remaining = current_job.get_remaining_time()

        status = {
            "job_name": job_config["name"],
            "job_emoji": job_config["emoji"],
            "start_time": current_job.start_time,
            "end_time": current_job.end_time,
            "remaining_time": remaining,
            "is_completed": current_job.is_completed(),
            "location_id": current_job.job_location_id
        }

        return True, "工作状态", status

    async def update_job_preferences(self, stats: PlayerJobStats, job_type: str, location_id: str) -> None:
        """更新工作偏好统计"""
        # 简单的偏好更新逻辑
        if not stats.favorite_job_type:
            stats.favorite_job_type = job_type
        if not stats.favorite_location:
            stats.favorite_location = location_id

    async def get_job_locations_list(self) -> List[Dict]:
        """获取所有工作地点列表"""
        locations = await self._job_location_repo.get_active_locations()

        result = []
        for location in locations:
            job_count = len(location.available_jobs)
            result.append({
                "location_id": location.location_id,
                "name": location.name,
                "description": location.description,
                "x": location.x,
                "y": location.y,
                "job_count": job_count,
                "required_level": location.required_level
            })

        return result

    async def get_player_job_history(self, player_id: str, limit: int = 10) -> List[Dict]:
        """获取玩家打工历史"""
        jobs = await self._part_time_job_repo.get_completed_jobs(player_id, limit)

        result = []
        for job in jobs:
            if job.job_type in self.JOB_TYPES:
                job_config = self.JOB_TYPES[job.job_type]
                result.append({
                    "job_name": job_config["name"],
                    "job_emoji": job_config["emoji"],
                    "total_reward": job.total_reward,
                    "special_event": job.special_event,
                    "completed_time": job.completed_time,
                    "work_duration": job.work_duration_hours
                })

        return result
