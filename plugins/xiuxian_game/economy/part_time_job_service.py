from __future__ import annotations

"""打工系统核心服务

功能：
1. 工作地点管理
2. 工作执行和奖励计算
3. 玩家打工状态管理
4. 特殊事件处理
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.part_time_job import PartTimeJob, JobLocation, PlayerJobStats
from ..utils import luck_prob


class PartTimeJobService:
    """打工系统核心服务类"""

    # 工作类型配置 - 针对年轻玩家优化，3分钟内完成，支持主动通知
    JOB_TYPES = {
        "cashier": {
            "name": "便利店收银员",
            "description": "在便利店负责收银和简单服务工作",
            "base_reward": 80,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🏪",
            "special_events": [
                {"name": "遇到好心顾客", "probability": 0.15, "bonus": 30, "description": "顾客给了小费"},
                {"name": "找到遗失钱包", "probability": 0.05, "bonus": 100, "description": "在店里找到钱包，老板奖励了你"},
            ]
        },
        "delivery_sorter": {
            "name": "快递分拣员",
            "description": "在快递站负责包裹分拣工作",
            "base_reward": 120,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 1,
            "emoji": "📦",
            "special_events": [
                {"name": "效率奖励", "probability": 0.2, "bonus": 40, "description": "工作效率很高，获得效率奖金"},
                {"name": "加班费", "probability": 0.1, "bonus": 80, "description": "主动加班获得额外报酬"},
            ]
        },
        "coffee_server": {
            "name": "咖啡店服务员",
            "description": "在咖啡店为顾客提供服务",
            "base_reward": 100,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 5,
            "emoji": "☕",
            "special_events": [
                {"name": "制作完美咖啡", "probability": 0.18, "bonus": 50, "description": "制作了完美的咖啡，获得顾客赞赏"},
                {"name": "遇到网红", "probability": 0.03, "bonus": 200, "description": "为网红服务，获得丰厚小费"},
            ]
        },
        "factory_worker": {
            "name": "工厂流水线工人",
            "description": "在工厂流水线上进行重复性工作",
            "base_reward": 150,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 1,
            "emoji": "🔧",
            "special_events": [
                {"name": "零缺陷奖励", "probability": 0.12, "bonus": 60, "description": "工作零缺陷，获得质量奖金"},
                {"name": "技能提升", "probability": 0.08, "bonus": 100, "description": "掌握了新技能，获得技能奖金"},
            ]
        },
        "cargo_handler": {
            "name": "安全屋建造",
            "description": "负责使用黄金建造安全屋，隔绝灵异力量，用于临时避难",
            "base_reward": 180,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 3,
            "emoji": "🚛",
            "special_events": [
                {"name": "体力奖励", "probability": 0.15, "bonus": 70, "description": "体力充沛，完成额外工作"},
                {"name": "安全奖励", "probability": 0.1, "bonus": 90, "description": "工作期间零事故，获得安全奖金"},
                {"name": "好评奖励", "probability": 0.1, "bonus": 110, "description": "买你安全屋的都默认打了好评，看来差评都没机会打呢"},
            ]
        },
        "quality_inspector": {
            "name": "质检员",
            "description": "负责产品质量检查工作",
            "base_reward": 140,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 8,
            "emoji": "🔍",
            "special_events": [
                {"name": "发现重大问题", "probability": 0.1, "bonus": 120, "description": "发现了重大质量问题，避免了损失"},
                {"name": "专业认可", "probability": 0.12, "bonus": 80, "description": "专业能力获得认可"},
            ]
        },
        "internet_cafe_manager": {
            "name": "网吧管理员",
            "description": "负责网吧的日常管理工作",
            "base_reward": 90,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🎮",
            "special_events": [
                {"name": "维护设备", "probability": 0.2, "bonus": 35, "description": "成功维护了设备"},
                {"name": "调解纠纷", "probability": 0.08, "bonus": 60, "description": "成功调解了顾客纠纷"},
            ]
        },
        "cinema_usher": {
            "name": "电影院检票员",
            "description": "在电影院负责检票和引导工作",
            "base_reward": 85,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 1,
            "emoji": "🍿",
            "special_events": [
                {"name": "明星签名", "probability": 0.02, "bonus": 300, "description": "遇到明星并获得签名，可以卖个好价钱"},
                {"name": "优质服务", "probability": 0.15, "bonus": 40, "description": "服务态度获得好评"},
            ]
        },
        "street_performer_assistant": {
            "name": "街头表演助手",
            "description": "协助街头艺人进行表演",
            "base_reward": 60,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🎪",
            "special_events": [
                {"name": "表演成功", "probability": 0.25, "bonus": 80, "description": "表演大获成功，收入丰厚"},
                {"name": "观众打赏", "probability": 0.3, "bonus": 40, "description": "观众额外打赏"},
                {"name": "表演失败", "probability": 0.1, "bonus": -20, "description": "表演效果不佳，收入减少"},
            ]
        },
        "delivery_driver": {
            "name": "配送司机",
            "description": "负责货物配送和运输工作",
            "base_reward": 160,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 5,
            "emoji": "🚚",
            "special_events": [
                {"name": "准时送达", "probability": 0.2, "bonus": 50, "description": "准时送达获得时效奖金"},
                {"name": "客户好评", "probability": 0.15, "bonus": 70, "description": "服务态度好获得客户好评奖励"},
                {"name": "节油奖励", "probability": 0.1, "bonus": 40, "description": "驾驶技术好，节省燃油获得奖励"},
            ]
        },
        "warehouse_keeper": {
            "name": "仓库管理员",
            "description": "负责仓库货物管理和盘点工作",
            "base_reward": 130,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 3,
            "emoji": "📋",
            "special_events": [
                {"name": "盘点准确", "probability": 0.18, "bonus": 60, "description": "盘点工作准确无误"},
                {"name": "发现问题", "probability": 0.12, "bonus": 80, "description": "发现库存问题并及时处理"},
                {"name": "效率提升", "probability": 0.15, "bonus": 45, "description": "工作效率高获得效率奖金"},
            ]
        },
        "farm_worker": {
            "name": "农场帮工",
            "description": "在农贸集散地帮忙搬运、分拣农产品",
            "base_reward": 130,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🌾",
            "special_events": [
                {"name": "丰收季", "probability": 0.15, "bonus": 70, "description": "赶上丰收季，老板多给了工钱"},
                {"name": "挑到好货", "probability": 0.10, "bonus": 100, "description": "帮老板挑到了品相极好的货，获得额外奖励"},
            ]
        },
        "night_market_vendor": {
            "name": "夜市摊贩",
            "description": "在热闹的夜市摆摊，吆喝叫卖各种小吃",
            "base_reward": 145,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 1,
            "emoji": "🏮",
            "special_events": [
                {"name": "爆单时刻", "probability": 0.15, "bonus": 90, "description": "排队排到马路上，赚翻了"},
                {"name": "美食博主", "probability": 0.05, "bonus": 200, "description": "被美食博主拍了视频，老板发了大红包"},
            ]
        },
        "fisherman_helper": {
            "name": "渔船帮工",
            "description": "跟着老渔民出海捕鱼，负责撒网收网",
            "base_reward": 200,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 3,
            "emoji": "🎣",
            "special_events": [
                {"name": "大丰收", "probability": 0.12, "bonus": 120, "description": "捞上来满满一网鱼，老船长乐开了花"},
                {"name": "稀有海鲜", "probability": 0.05, "bonus": 250, "description": "网到一只罕见的大龙虾，卖了大价钱"},
            ]
        },
        "miner": {
            "name": "矿场矿工",
            "description": "在幽暗的矿洞中开采矿石",
            "base_reward": 260,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 5,
            "emoji": "⛏️",
            "special_events": [
                {"name": "挖到矿脉", "probability": 0.08, "bonus": 180, "description": "运气爆棚挖到了富矿脉"},
                {"name": "稀有矿石", "probability": 0.04, "bonus": 300, "description": "发现了一块稀有矿石"},
            ]
        },
        "mechanic": {
            "name": "修车技师",
            "description": "在修配街的车行里给各种车辆做保养维修",
            "base_reward": 230,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 5,
            "emoji": "🔩",
            "special_events": [
                {"name": "疑难杂症", "probability": 0.10, "bonus": 150, "description": "修好了别人搞不定的故障"},
                {"name": "豪车客户", "probability": 0.05, "bonus": 200, "description": "来了辆豪车，维修费翻倍还给了小费"},
            ]
        },
        "tour_guide": {
            "name": "景区导游",
            "description": "带领游客参观金陵古城，讲解历史文化",
            "base_reward": 170,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 3,
            "emoji": "🗺️",
            "special_events": [
                {"name": "好评如潮", "probability": 0.18, "bonus": 80, "description": "讲解生动有趣，游客全五星好评"},
                {"name": "土豪团", "probability": 0.05, "bonus": 250, "description": "带了个土豪旅游团，小费给得大方"},
            ]
        },
        "escort_guard": {
            "name": "镖局护卫",
            "description": "护送货物安全抵达目的地",
            "base_reward": 300,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 8,
            "emoji": "⚔️",
            "special_events": [
                {"name": "一路平安", "probability": 0.20, "bonus": 100, "description": "轻松完成护送任务"},
                {"name": "击退劫匪", "probability": 0.10, "bonus": 200, "description": "成功击退了路上的劫匪"},
            ]
        },
        "snow_patrol": {
            "name": "雪山巡逻员",
            "description": "在风雪镇外围巡逻，排查异常和救助旅人",
            "base_reward": 350,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 10,
            "emoji": "🏔️",
            "special_events": [
                {"name": "救助旅人", "probability": 0.12, "bonus": 150, "description": "救了个迷路的旅人"},
                {"name": "发现异常", "probability": 0.08, "bonus": 200, "description": "发现并上报了可疑活动"},
            ]
        },
        "dock_worker": {
            "name": "码头搬运工",
            "description": "在舟山渔港码头搬运卸货",
            "base_reward": 190,
            "duration_hours": 0.05,  # 3分钟
            "required_level": 1,
            "emoji": "⚓",
            "special_events": [
                {"name": "加急货", "probability": 0.15, "bonus": 80, "description": "帮忙搬了批加急货，拿了加急费"},
                {"name": "力大无穷", "probability": 0.10, "bonus": 100, "description": "一人干了两人的活"},
            ]
        },
        "herb_gatherer": {
            "name": "药材采集员",
            "description": "在云岭山区采集各种珍贵药材",
            "base_reward": 210,
            "duration_hours": 0.042,  # 2.5分钟
            "required_level": 5,
            "emoji": "🌿",
            "special_events": [
                {"name": "珍稀草药", "probability": 0.08, "bonus": 180, "description": "找到了一株年份很老的药材"},
                {"name": "满载而归", "probability": 0.15, "bonus": 90, "description": "今天运气好，采了满满一筐好药材"},
            ]
        },
        "tavern_waiter": {
            "name": "酒馆跑堂",
            "description": "在大昌市的热闹酒馆里端盘子、招待客人",
            "base_reward": 110,
            "duration_hours": 0.033,  # 2分钟
            "required_level": 1,
            "emoji": "🍺",
            "special_events": [
                {"name": "豪客打赏", "probability": 0.12, "bonus": 100, "description": "来了桌豪客，喝高兴了赏了一大笔"},
                {"name": "听到情报", "probability": 0.08, "bonus": 80, "description": "无意间听到有用情报，老板给了信息费"},
            ]
        },
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
            "x": 250,  # 荔湾镇
            "y": -1350,
            "available_jobs": ["factory_worker", "cargo_handler", "quality_inspector"],
            "required_level": 1
        },
        "entertainment_district": {
            "location_id": "entertainment_district",
            "name": "郸城娱乐街区",
            "description": "充满活力的娱乐区，工作轻松有趣",
            "x": 150,  # 郸城
            "y": -130,
            "available_jobs": ["internet_cafe_manager", "cinema_usher", "street_performer_assistant"],
            "required_level": 1
        },
        "logistics_center": {
            "location_id": "logistics_center",
            "name": "天海卫物流中心",
            "description": "天海卫港口的物流配送中心",
            "x": 250,  # 天海卫
            "y": -50,
            "available_jobs": ["delivery_driver", "warehouse_keeper", "cargo_handler"],
            "required_level": 1
        },
        "farm_market": {
            "location_id": "farm_market",
            "name": "石关农贸集散地",
            "description": "石关最大的农产品集散中心",
            "x": -200,  # 石关
            "y": -150,
            "available_jobs": ["farm_worker", "delivery_sorter", "warehouse_keeper"],
            "required_level": 1
        },
        "culture_street": {
            "location_id": "culture_street",
            "name": "金陵文化商街",
            "description": "古色古香的文化街区",
            "x": 450,  # 金陵
            "y": -480,
            "available_jobs": ["tour_guide", "night_market_vendor", "coffee_server"],
            "required_level": 1
        },
        "mining_area": {
            "location_id": "mining_area",
            "name": "云岭采矿区",
            "description": "云岭深处的矿区，报酬不菲",
            "x": -850,  # 云岭
            "y": -1150,
            "available_jobs": ["miner", "herb_gatherer", "cargo_handler"],
            "required_level": 3
        },
        "repair_street": {
            "location_id": "repair_street",
            "name": "摩配镇修配街",
            "description": "摩配镇最热闹的修配一条街",
            "x": 80,
            "y": 140,
            "available_jobs": ["mechanic", "factory_worker", "night_market_vendor"],
            "required_level": 1
        },
        "snow_outpost": {
            "location_id": "snow_outpost",
            "name": "风雪镇哨站",
            "description": "风雪镇外围的巡逻哨站",
            "x": 150,  # 风雪镇
            "y": 1200,
            "available_jobs": ["snow_patrol", "escort_guard", "herb_gatherer"],
            "required_level": 5
        },
        "fishing_dock": {
            "location_id": "fishing_dock",
            "name": "舟山渔业码头",
            "description": "舟山最繁忙的渔港码头",
            "x": 700,  # 舟山
            "y": -600,
            "available_jobs": ["fisherman_helper", "dock_worker", "delivery_driver"],
            "required_level": 1
        },
        "trade_district": {
            "location_id": "trade_district",
            "name": "大昌市商贸区",
            "description": "大昌市的核心商贸区",
            "x": -600,  # 大昌市
            "y": -800,
            "available_jobs": ["escort_guard", "tavern_waiter", "warehouse_keeper"],
            "required_level": 1
        },
        "guanzhong_arena": {
            "location_id": "guanzhong_arena",
            "name": "长安武馆",
            "description": "古都长安最大的武馆，常年招收杂役",
            "x": -500,
            "y": -280,
            "available_jobs": ["escort_guard", "snow_patrol", "cargo_handler"],
            "required_level": 3
        },
        "bianliang_market": {
            "location_id": "bianliang_market",
            "name": "汴梁集市",
            "description": "中原最繁忙的集市，需要大量帮工",
            "x": -100,
            "y": -450,
            "available_jobs": ["cashier", "delivery_driver", "night_market_vendor"],
            "required_level": 1
        },
        "yumen_outpost": {
            "location_id": "yumen_outpost",
            "name": "玉门驿站",
            "description": "丝路重要驿站，为往来商旅提供服务",
            "x": -1200,
            "y": 100,
            "available_jobs": ["escort_guard", "cargo_handler", "delivery_driver"],
            "required_level": 5
        },
        "pengcheng_dock": {
            "location_id": "pengcheng_dock",
            "name": "鹏城码头",
            "description": "南海最繁忙的商港码头",
            "x": 350,
            "y": -1450,
            "available_jobs": ["dock_worker", "fisherman_helper", "cargo_handler"],
            "required_level": 1
        },
    }

    @classmethod
    async def initialize_job_locations(cls, session: AsyncSession) -> None:
        """初始化工作地点数据"""
        for location_data in cls.JOB_LOCATIONS.values():
            # 检查是否已存在
            stmt = select(JobLocation).where(JobLocation.location_id == location_data["location_id"])
            existing = (await session.execute(stmt)).scalars().first()

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
                        job_type: cls.JOB_TYPES[job_type] for job_type in location_data["available_jobs"]
                    }
                )
                session.add(location)

        # 注意：不在这里commit，由调用方控制事务边界

    @classmethod
    async def get_available_jobs_at_location(cls, session: AsyncSession, player: Player) -> Tuple[bool, str, List[Dict]]:
        """获取玩家当前位置可用的工作"""
        if player.region != "大都会":
            return False, "只有在大都会才能打工", []

        # 查找当前坐标的工作地点 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        stmt = select(JobLocation).where(
            and_(
                JobLocation.x == current_x,
                JobLocation.y == current_y,
                JobLocation.is_active == True
            )
        )
        location = (await session.execute(stmt)).scalars().first()

        if not location:
            return False, "当前位置没有工作机会", []

        if player.level < location.required_level:
            return False, f"等级不足，需要{location.required_level}级", []

        # 获取可用工作列表
        available_jobs = []
        for job_type, job_config in location.available_jobs.items():
            if player.level >= job_config.get("required_level", 1):
                available_jobs.append({
                    "job_type": job_type,
                    "name": job_config["name"],
                    "description": job_config["description"],
                    "base_reward": job_config["base_reward"],
                    "duration_hours": job_config["duration_hours"],
                    "emoji": job_config["emoji"]
                })

        return True, f"在{location.name}找到{len(available_jobs)}个工作机会", available_jobs

    @classmethod
    async def start_job(cls, session: AsyncSession, player: Player, job_type: str) -> Tuple[bool, str, Optional[PartTimeJob]]:
        """开始工作"""
        # 检查是否已在工作
        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player.id,
                PartTimeJob.is_working == True
            )
        )
        current_job = (await session.execute(stmt)).scalars().first()

        if current_job:
            remaining = current_job.get_remaining_time()
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return False, f"你正在工作中，剩余时间：{hours}小时{minutes}分钟", None

        # 检查工作类型是否存在
        if job_type not in cls.JOB_TYPES:
            return False, "工作类型不存在", None

        job_config = cls.JOB_TYPES[job_type]

        # 检查等级要求
        if player.level < job_config["required_level"]:
            return False, f"等级不足，需要{job_config['required_level']}级", None

        # 检查当前位置是否有这个工作
        success, msg, available_jobs = await cls.get_available_jobs_at_location(session, player)
        if not success:
            return False, msg, None

        job_available = any(job["job_type"] == job_type for job in available_jobs)
        if not job_available:
            return False, "当前位置没有这个工作", None

        # 获取工作地点 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        stmt = select(JobLocation).where(
            and_(
                JobLocation.x == current_x,
                JobLocation.y == current_y,
                JobLocation.is_active == True
            )
        )
        location = (await session.execute(stmt)).scalars().first()

        # 创建工作记录
        now = datetime.now()
        end_time = now + timedelta(hours=job_config["duration_hours"])

        # 如果有未完成的工作记录，先完成它
        if current_job:
            current_job.is_working = False
            current_job.completed_time = now

        new_job = PartTimeJob(
            player_id=player.id,
            job_location_id=location.location_id,
            job_type=job_type,
            is_working=True,
            start_time=now,
            end_time=end_time,
            work_duration_hours=job_config["duration_hours"]
        )

        session.add(new_job)
        # 注意：不在这里commit，由调用方控制事务边界

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

    @classmethod
    async def complete_job(cls, session: AsyncSession, player: Player) -> Tuple[bool, str, Optional[Dict]]:
        """完成工作并获得奖励"""
        # 查找当前工作
        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player.id,
                PartTimeJob.is_working == True
            )
        )
        current_job = (await session.execute(stmt)).scalars().first()

        if not current_job:
            return False, "你当前没有在工作", None

        if not current_job.is_completed():
            remaining = current_job.get_remaining_time()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return False, f"工作尚未完成，剩余时间：{hours}小时{minutes}分钟", None

        # 计算奖励
        job_config = cls.JOB_TYPES[current_job.job_type]
        base_reward = job_config["base_reward"]

        # 等级加成 (每级增加2%)
        level_bonus = int(base_reward * (player.level - 1) * 0.02)

        # 运气加成
        luck_multiplier = 1 + luck_prob(player.luck) * 0.5  # 最多50%加成

        # 连续工作奖励
        stats = await cls.get_or_create_player_stats(session, player.id)
        consecutive_bonus = min(stats.current_streak * 5, 100)  # 每天连续+5金币，最多100

        # 基础奖励计算
        total_base = int((base_reward + level_bonus) * luck_multiplier) + consecutive_bonus

        # 特殊事件处理
        special_event = None
        bonus_reward = 0

        # 随机触发特殊事件
        for event in job_config.get("special_events", []):
            if random.random() < event["probability"]:
                special_event = event
                bonus_reward = event["bonus"]
                break

        # 计算最终奖励
        current_job.base_reward = total_base
        current_job.bonus_reward = bonus_reward
        current_job.total_reward = total_base + bonus_reward
        current_job.is_working = False
        current_job.completed_time = datetime.now()

        if special_event:
            current_job.special_event = special_event["description"]

        # 发放奖励
        player.gold += current_job.total_reward

        # 更新统计
        stats.total_jobs_completed += 1
        stats.total_earnings += current_job.total_reward
        stats.total_work_hours += current_job.work_duration_hours
        stats.update_streak(datetime.now())

        # 更新偏好统计
        await cls.update_job_preferences(session, stats, current_job.job_type, current_job.job_location_id)

        session.add_all([current_job, player, stats])
        # 注意：不在这里commit，由调用方控制事务边界

        # 构建结果信息
        result = {
            "job_name": job_config["name"],
            "base_reward": total_base,
            "bonus_reward": bonus_reward,
            "total_reward": current_job.total_reward,
            "special_event": special_event,
            "level_bonus": level_bonus,
            "luck_multiplier": luck_multiplier,
            "consecutive_bonus": consecutive_bonus,
            "current_streak": stats.current_streak
        }

        return True, "工作完成！", result

    @classmethod
    async def get_current_job_status(cls, session: AsyncSession, player: Player) -> Tuple[bool, str, Optional[Dict]]:
        """获取当前工作状态"""
        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player.id,
                PartTimeJob.is_working == True
            )
        )
        current_job = (await session.execute(stmt)).scalars().first()

        if not current_job:
            return False, "当前没有在工作", None

        job_config = cls.JOB_TYPES[current_job.job_type]
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

    @classmethod
    async def get_or_create_player_stats(cls, session: AsyncSession, player_id: str) -> PlayerJobStats:
        """获取或创建玩家打工统计"""
        stmt = select(PlayerJobStats).where(PlayerJobStats.player_id == player_id)
        stats = (await session.execute(stmt)).scalars().first()

        if not stats:
            stats = PlayerJobStats(
                player_id=player_id,
                total_jobs_completed=0,
                total_earnings=0,
                total_work_hours=0,
                current_streak=0,
                max_streak=0,
                achievements={}
            )
            session.add(stats)
            await session.flush()

        return stats

    @classmethod
    async def update_job_preferences(cls, session: AsyncSession, stats: PlayerJobStats, job_type: str, location_id: str) -> None:
        """更新工作偏好统计"""
        # 简单的偏好更新逻辑
        if not stats.favorite_job_type:
            stats.favorite_job_type = job_type
        if not stats.favorite_location:
            stats.favorite_location = location_id

    @classmethod
    async def get_job_locations_list(cls, session: AsyncSession) -> List[Dict]:
        """获取所有工作地点列表"""
        stmt = select(JobLocation).where(JobLocation.is_active == True)
        locations = (await session.execute(stmt)).scalars().all()

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

    @classmethod
    async def get_player_job_history(cls, session: AsyncSession, player_id: str, limit: int = 10) -> List[Dict]:
        """获取玩家打工历史"""
        stmt = select(PartTimeJob).where(
            and_(
                PartTimeJob.player_id == player_id,
                PartTimeJob.is_working == False
            )
        ).order_by(PartTimeJob.completed_time.desc()).limit(limit)

        jobs = (await session.execute(stmt)).scalars().all()

        result = []
        for job in jobs:
            if job.job_type in cls.JOB_TYPES:
                job_config = cls.JOB_TYPES[job.job_type]
                result.append({
                    "job_name": job_config["name"],
                    "job_emoji": job_config["emoji"],
                    "total_reward": job.total_reward,
                    "special_event": job.special_event,
                    "completed_time": job.completed_time,
                    "work_duration": job.work_duration_hours
                })

        return result