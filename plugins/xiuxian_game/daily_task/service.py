"""每日任务系统服务类"""
import random
from datetime import date, datetime
from typing import List, Dict, Tuple, Optional
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.daily_task import DailyTask, TaskType, TaskStatus
from ..config import config


class DailyTaskService:
    """每日任务系统服务类"""

    # 用于避免频繁清理的缓存
    _last_cleanup_date = None
    
    GHOST_NAMES = [
        "太上仙翁", "太极真仙", "玄妙道长", "无相道君", "太虚真人",
        "笔佡", "纸人道长", "梦游仙师", "黑斑真人", "虚影道君", "道仙",
        "石像仙翁", "星光仙师", "血肉道君", "尸斑仙翁"
    ]

    CITY_NAMES = [
        "长安", "洛阳", "金陵", "临安", "汴梁", "大梁", "邺城", "蓟城",
        "成都", "扬州", "苏州", "杭州", "开封", "太原", "西安", "北京",
    ]
    
    @staticmethod
    async def generate_daily_task(session: AsyncSession, player: Player) -> DailyTask:
        """为玩家生成每日任务"""
        today = date.today()

        # 被动清理过期任务
        await DailyTaskService.check_and_cleanup_expired_tasks(session)

        # 检查今日是否已有任务
        existing_task = await DailyTaskService.get_player_daily_task(session, player.id, today)
        if existing_task:
            return existing_task
        
        # 生成随机坐标（在大都会范围内）
        target_x = random.randint(-200, 200)
        target_y = random.randint(-200, 200)
        
        # 随机选择城市和鬼怪名称
        city_name = random.choice(DailyTaskService.CITY_NAMES)
        ghost_name = random.choice(DailyTaskService.GHOST_NAMES)

        # 随机选择任务类型
        task_types = list(TaskType)
        selected_task_type = random.choice(task_types)
        
        # 根据任务类型生成对应的任务描述
        task_descriptions = DailyTaskService._get_task_descriptions_by_type(selected_task_type, city_name, ghost_name)
        description = random.choice(task_descriptions)

        # 根据玩家等级计算敌人属性
        enemy_level = max(1, player.level + random.randint(-5, 5))
        enemy_stats = DailyTaskService._calculate_enemy_stats(enemy_level)

        # 计算奖励
        rewards = DailyTaskService._calculate_rewards(player.level, enemy_level, selected_task_type)

        # 根据任务类型生成不同的标题和敌人名称
        task_title, enemy_name = DailyTaskService._generate_task_title_and_enemy(
            selected_task_type, city_name, ghost_name
        )

        # 创建任务
        task = DailyTask(
            player_id=player.id,
            task_type=selected_task_type,
            title=task_title,
            description=description,
            target_region="大都会",
            target_x=target_x,
            target_y=target_y,
            enemy_name=enemy_name,
            enemy_level=enemy_level,
            enemy_hp=enemy_stats["hp"],
            enemy_attack=enemy_stats["attack"],
            enemy_defense=enemy_stats["defense"],
            enemy_agility=enemy_stats["agility"],
            exp_reward=rewards["exp"],
            gold_reward=rewards["gold"],
            guild_points_reward=rewards["guild_points"],
            task_date=today
        )

        session.add(task)
        return task

    @staticmethod
    def _get_task_descriptions_by_type(task_type: TaskType, city_name: str, ghost_name: str) -> List[str]:
        """根据任务类型获取对应的任务描述"""
        if task_type == TaskType.PEN_SPIRIT_CASE:
            return [
                f"{city_name}城中近夜有诡异之事：居民夜半梦游，穿墙而过，手持黑笔，于空中书写。醒后皆不记所为，唯身生黑斑，日渐增多。疑为{ghost_name}作祟，以笔墨控人心神。恳请道友速赴{city_name}城，破此笔仙之术。",
                f"闻{city_name}城中有{ghost_name}化身笔仙，夜入民宅，操控人心。被其蛊惑者皆夜半起身，手执黑笔，书写诡异文字，醒后身生梅花黑斑，痛痒难忍。此鬼善隐匿，难以察觉。望道友前往{city_name}城，寻此笔仙踪迹。",
                f"{city_name}城内近日怪事频发：有人夜半梦游，身如纸片，可穿墙遁地。醒后皆言不知所为，唯手中握有黑笔一支。疑为{ghost_name}笔仙作祟，以梦境控人。恳请道友速往{city_name}城，破此梦游之术。"
            ]
        elif task_type == TaskType.FAKE_IMMORTAL_CULT:
            return [
                f"闻{city_name}城中有{ghost_name}设神坛，供奉石像，传授修炼之法。修者需以沸水灼身，以针刺骨，痛苦万分。然修者皆言此乃仙途必经，甘愿受苦。实则此鬼以痛苦为食，蛊惑人心。望道友前往{city_name}城，毁此邪坛。",
                f"{city_name}城遭{ghost_name}蛊惑，城中设有神像，红光照耀，香火不断。修者需日夜跪拜，不得安眠。久之，修者皆成石像模样，僵硬不动，唯眼中有泪。此鬼以人为石，极为残忍。恳请道友速赴{city_name}城，救此石化之民。",
                f"近闻{city_name}城中有{ghost_name}传授道仙经，声称可得长生。修者需承受非人折磨：沸水煮身、针刺入骨、悬梁练气。修者皆言此乃成仙正道，实为此鬼蛊惑。望道友前往{city_name}城，破此邪教。"
            ]
        elif task_type == TaskType.SHAPE_SHIFTER_HUNT:
            return [
                f"{city_name}城内近日怪事频发：有人入室而不开门，有人变脸而不自知，有人身生肉洞而自残不止。皆因{ghost_name}化身道长，传授邪法所致。此鬼能操控人形，变化无常，极为危险。恳请道友速往{city_name}城，除此变形之鬼。",
                f"近日{city_name}城中监控尽失，天眼不明。有{ghost_name}化身修者，身如纸片，可穿墙遁地，来去无踪。城中居民夜不敢眠，恐遭此鬼侵扰。此鬼善隐匿，难以察觉，需高人出手。望道友前往{city_name}城，寻此隐形之鬼。",
                f"{city_name}城中有{ghost_name}善变化，可化作任何人形，混入人群。被其附身者面容渐变，行为诡异，最终失去人性。此鬼极为狡猾，难以分辨真假。恳请道友速赴{city_name}城，识破此变形之鬼。"
            ]
        elif task_type == TaskType.STONE_CURSE_BREAK:
            return [
                f"{city_name}城遭{ghost_name}石化诅咒，城中居民渐成石像。初时仅行动迟缓，继而肌肤僵硬，最终化为顽石。唯眼中尚有泪水，可知其痛苦。此诅咒传播极快，需速破解。恳请道友前往{city_name}城，破此石化之咒。",
                f"闻{city_name}城中有{ghost_name}设石像神坛，凡拜者皆渐化石。城中已有数百人成石像，立于街头，神情痛苦。此鬼以石化为乐，极为残忍。望道友速赴{city_name}城，毁此石像神坛。",
                f"{city_name}城内近日异象：居民皆面色苍白，行动僵硬，如石像般。疑为{ghost_name}石化鬼作祟，以诅咒控人。被诅咒者渐失血肉，化为顽石，痛苦万分。恳请道友速往{city_name}城，解此石化之厄。"
            ]
        elif task_type == TaskType.TORTURE_CULT_RAID:
            return [
                f"闻{city_name}城中有{ghost_name}传授锻体之法：以热水煮身，以苦胆入口，以悬梁练气。修者皆言此乃成仙正道，然观其状，皆面容扭曲，痛苦不堪。实为此鬼以折磨为乐，蛊惑众生。望道友前往{city_name}城，破此酷刑之术。",
                f"{city_name}城中有{ghost_name}设酷刑道场，传授痛苦修炼法。修者需承受沸水灼身、针刺入骨、刀割血肉等酷刑。修者皆言痛苦乃成仙必经，甘愿受虐。实为此鬼以痛苦为食。恳请道友速赴{city_name}城，毁此酷刑道场。",
                f"近日{city_name}城中异象频生：有人自残不止，有人痛苦哀嚎，有人身生肉洞。皆因{ghost_name}传授酷刑修炼法所致。此鬼善蛊惑人心，以折磨为乐。恳请道友速往{city_name}城，除此酷刑之鬼。"
            ]
        else:
            # 默认的鬼怪消除任务描述
            return [
            # 原有的道仙蛊惑类任务
            f"近日{city_name}城中异象频生，{ghost_name}蛊惑民心，百姓皆言修仙得道，却不知所修非仙。城中老幼皆面露诡笑，双目无神，夜夜诵经不休。望道友速往{city_name}城，破此邪术，还百姓清明。",

            f"{city_name}城内邪气冲天，{ghost_name}传授邪法，民众争相修习。然所修之法实为鬼道，修者渐失人性，面容枯槁，行如游魂。城中已无活人气息，唯余阴森鬼气。恳请道友前往{city_name}城，斩断此邪缘。",

            f"闻{city_name}城中有{ghost_name}自称道仙，传授长生之术。城中百姓趋之若鹜，日夜修炼。然修者皆渐生异状：肌肤苍白如纸，双目深陷无光，言语颠倒，行为诡异。实乃鬼魅蛊惑，非真仙道。望道友速赴{city_name}城，除此伪仙。",

            f"{city_name}城遭{ghost_name}侵扰，此鬼化身道长，于城中设坛传法。百姓信以为真，皆来求道。然所传之法实为邪术，修者渐失血色，夜不能寐，日不思食，形如行尸。城中阴气弥漫，生机断绝。恳请道友前往{city_name}城，破此邪坛。",

            f"近闻{city_name}城中出现奇人，自称得道高仙，能传不老之术。城中富商巨贾、平民百姓皆拜其为师。然修习月余，弟子们皆生怪病：白日昏睡，夜晚游荡，面无血色，目光呆滞。实为{ghost_name}作祟，以邪法控制人心。望道友速往{city_name}城，揭穿此鬼伪装。",

            f"{city_name}城中近日香火鼎盛，皆因有{ghost_name}化身仙师，传授修仙之法。城中男女老幼皆言得遇真仙，日夜修炼不辍。然观其修者，皆面色青白，双目无神，言语失常，行为怪异。此非修仙，实为鬼道蛊惑。恳请道友前往{city_name}城，破此迷障。",

            # 基于《厉鬼纪元》新增的任务类型
            f"{city_name}城中近夜有诡异之事：居民夜半梦游，穿墙而过，手持黑笔，于空中书写。醒后皆不记所为，唯身生黑斑，日渐增多。疑为{ghost_name}作祟，以笔墨控人心神。恳请道友速赴{city_name}城，破此笔仙之术。",

            f"闻{city_name}城中有{ghost_name}设神坛，供奉石像，传授修炼之法。修者需以沸水灼身，以针刺骨，痛苦万分。然修者皆言此乃仙途必经，甘愿受苦。实则此鬼以痛苦为食，蛊惑人心。望道友前往{city_name}城，毁此邪坛。",

            f"{city_name}城内近日怪事频发：有人入室而不开门，有人变脸而不自知，有人身生肉洞而自残不止。皆因{ghost_name}化身道长，传授邪法所致。此鬼能操控人形，变化无常，极为危险。恳请道友速往{city_name}城，除此变形之鬼。",

            f"近日{city_name}城中监控尽失，天眼不明。有{ghost_name}化身修者，身如纸片，可穿墙遁地，来去无踪。城中居民夜不敢眠，恐遭此鬼侵扰。此鬼善隐匿，难以察觉，需高人出手。望道友前往{city_name}城，寻此隐形之鬼。",

            f"{city_name}城遭{ghost_name}蛊惑，城中设有神像，红光照耀，香火不断。修者需日夜跪拜，不得安眠。久之，修者皆成石像模样，僵硬不动，唯眼中有泪。此鬼以人为石，极为残忍。恳请道友速赴{city_name}城，救此石化之民。",

            f"闻{city_name}城中有{ghost_name}传授锻体之法：以热水煮身，以苦胆入口，以悬梁练气。修者皆言此乃成仙正道，然观其状，皆面容扭曲，痛苦不堪。实为此鬼以折磨为乐，蛊惑众生。望道友前往{city_name}城，破此酷刑之术。"
        ]

    @staticmethod
    def _generate_task_title_and_enemy(task_type: TaskType, city_name: str, ghost_name: str) -> Tuple[str, str]:
        """根据任务类型生成任务标题和敌人名称"""
        if task_type == TaskType.GHOST_ELIMINATION:
            return f"缉邪司委托：{city_name}城伪仙{ghost_name}蛊惑事件", f"伪仙·{ghost_name}"
        elif task_type == TaskType.PEN_SPIRIT_CASE:
            return f"缉邪司委托：{city_name}城笔仙{ghost_name}梦游案", f"笔仙·{ghost_name}"
        elif task_type == TaskType.FAKE_IMMORTAL_CULT:
            return f"缉邪司委托：{city_name}城道仙{ghost_name}邪教案", f"道仙·{ghost_name}"
        elif task_type == TaskType.SHAPE_SHIFTER_HUNT:
            return f"缉邪司委托：{city_name}城变形鬼{ghost_name}追捕令", f"变形鬼·{ghost_name}"
        elif task_type == TaskType.STONE_CURSE_BREAK:
            return f"缉邪司委托：{city_name}城石化诅咒{ghost_name}破解案", f"石化鬼·{ghost_name}"
        elif task_type == TaskType.TORTURE_CULT_RAID:
            return f"缉邪司委托：{city_name}城酷刑邪教{ghost_name}清剿令", f"酷刑鬼·{ghost_name}"
        else:
            # 默认情况
            return f"缉邪司委托：{city_name}城伪仙{ghost_name}蛊惑事件", f"伪仙·{ghost_name}"

    @staticmethod
    def _calculate_guild_exp_reward(task_type: TaskType, enemy_level: int) -> int:
        """计算公会经验奖励"""
        # 基础公会经验
        base_guild_exp = 10 + enemy_level * 2

        # 根据任务类型调整公会经验
        task_multipliers = {
            TaskType.GHOST_ELIMINATION: 1.0,      # 基础公会经验
            TaskType.PEN_SPIRIT_CASE: 1.2,       # 笔仙案件+20%
            TaskType.FAKE_IMMORTAL_CULT: 1.1,    # 伪仙邪教+10%
            TaskType.SHAPE_SHIFTER_HUNT: 1.3,    # 变形鬼最难，+30%
            TaskType.STONE_CURSE_BREAK: 1.15,    # 石化诅咒+15%
            TaskType.TORTURE_CULT_RAID: 1.25     # 酷刑邪教+25%
        }

        multiplier = task_multipliers.get(task_type, 1.0)
        return int(base_guild_exp * multiplier)
    
    @staticmethod
    def _calculate_enemy_stats(enemy_level: int) -> Dict[str, int]:
        """计算敌人属性"""
        # 基础属性计算，确保与玩家等级匹配
        base_hp = 100 + enemy_level * 15
        base_attack = 20 + enemy_level * 8
        base_defense = 10 + enemy_level * 5
        base_agility = 15 + enemy_level * 3
        
        # 添加随机波动（±20%）
        hp = int(base_hp * random.uniform(0.8, 1.2))
        attack = int(base_attack * random.uniform(0.8, 1.2))
        defense = int(base_defense * random.uniform(0.8, 1.2))
        agility = int(base_agility * random.uniform(0.8, 1.2))
        
        return {
            "hp": hp,
            "attack": attack,
            "defense": defense,
            "agility": agility
        }
    
    @staticmethod
    def _calculate_rewards(player_level: int, enemy_level: int, task_type: TaskType = TaskType.GHOST_ELIMINATION) -> Dict[str, int]:
        """计算任务奖励"""
        # 基础奖励
        base_exp = 50 + enemy_level * 10
        base_gold = 200 + enemy_level * 20
        base_guild_points = 20 + enemy_level * 5

        # 根据任务类型调整奖励
        task_multipliers = {
            TaskType.GHOST_ELIMINATION: 1.0,      # 基础奖励
            TaskType.PEN_SPIRIT_CASE: 1.2,       # 笔仙案件较难，奖励+20%
            TaskType.FAKE_IMMORTAL_CULT: 1.1,    # 伪仙邪教奖励+10%
            TaskType.SHAPE_SHIFTER_HUNT: 1.3,    # 变形鬼最难追捕，奖励+30%
            TaskType.STONE_CURSE_BREAK: 1.15,    # 石化诅咒奖励+15%
            TaskType.TORTURE_CULT_RAID: 1.25     # 酷刑邪教危险，奖励+25%
        }

        task_multiplier = task_multipliers.get(task_type, 1.0)

        # 等级差异调整
        level_diff = enemy_level - player_level
        if level_diff > 0:
            # 敌人等级高，奖励增加
            level_multiplier = 1.0 + (level_diff * 0.1)
        else:
            # 敌人等级低，奖励减少
            level_multiplier = max(0.5, 1.0 + (level_diff * 0.05))

        # 综合倍率
        final_multiplier = task_multiplier * level_multiplier

        return {
            "exp": int(base_exp * final_multiplier),
            "gold": int(base_gold * final_multiplier),
            "guild_points": int(base_guild_points * final_multiplier)
        }
    
    @staticmethod
    async def get_player_daily_task(session: AsyncSession, player_id: str, task_date: date = None) -> Optional[DailyTask]:
        """获取玩家指定日期的每日任务"""
        if task_date is None:
            task_date = date.today()
        
        result = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.task_date == task_date
                )
            )
        )
        return result.scalars().first()
    
    @staticmethod
    async def accept_task(session: AsyncSession, task: DailyTask) -> Tuple[bool, str]:
        """接取任务"""
        # 被动清理过期任务
        await DailyTaskService.check_and_cleanup_expired_tasks(session)

        if not task.is_available():
            return False, "任务已被接取或已完成"

        task.accept_task()
        session.add(task)

        return True, f"✅ 成功接取任务：{task.title}"
    
    @staticmethod
    async def complete_task(session: AsyncSession, player: Player, task: DailyTask) -> Tuple[bool, str, Dict]:
        """完成任务并发放奖励"""
        if not task.is_accepted():
            return False, "任务尚未接取或已完成", {}
        
        # 检查玩家是否在任务目标位置
        if player.x != task.target_x or player.y != task.target_y:
            return False, f"请先前往任务目标位置：{task.location_str}", {}
        
        # 发放奖励
        rewards_given = {}
        
        # 经验奖励
        if task.exp_reward > 0:
            player.exp += task.exp_reward
            rewards_given["exp"] = task.exp_reward
        
        # 金币奖励
        if task.gold_reward > 0:
            player.gold += task.gold_reward
            rewards_given["gold"] = task.gold_reward
        
        # 公会积分奖励（只有加入公会的玩家才能获得）
        if task.guild_points_reward > 0 and player.guild_id:
            player.gold2 += task.guild_points_reward
            rewards_given["guild_points"] = task.guild_points_reward

            # 添加公会经验奖励（基于任务类型给予不同的公会经验）
            from ..guild.guild_economy_service import GuildEconomyService
            base_guild_exp = DailyTaskService._calculate_guild_exp_reward(task.task_type, task.enemy_level)
            guild_exp_gained = await GuildEconomyService.add_guild_experience(
                session, player.guild_id, base_guild_exp
            )
            rewards_given["guild_exp"] = guild_exp_gained
        
        # 完成任务
        task.complete_task()
        session.add(task)
        session.add(player)
        
        return True, "任务完成！", rewards_given
    
    @staticmethod
    async def get_task_summary(session: AsyncSession, player_id: str) -> Dict:
        """获取玩家任务完成情况汇总"""
        today = date.today()

        # 被动清理过期任务
        await DailyTaskService.check_and_cleanup_expired_tasks(session)

        # 今日任务
        today_task = await DailyTaskService.get_player_daily_task(session, player_id, today)
        
        # 本周完成任务数
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())
        
        result = await session.execute(
            select(func.count(DailyTask.id)).where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.status == TaskStatus.COMPLETED,
                    DailyTask.task_date >= week_start
                )
            )
        )
        weekly_completed = result.scalar_one()
        
        # 总完成任务数
        result = await session.execute(
            select(func.count(DailyTask.id)).where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.status == TaskStatus.COMPLETED
                )
            )
        )
        total_completed = result.scalar_one()
        
        return {
            "today_task": today_task,
            "weekly_completed": weekly_completed,
            "total_completed": total_completed
        }
    



# ==================== 被动触发的任务管理 ====================

    @staticmethod
    async def check_and_cleanup_expired_tasks(session: AsyncSession) -> int:
        """检查并清理过期任务（被动触发，避免频繁执行）"""
        today = date.today()

        # 如果今天已经清理过，就不再重复清理
        if DailyTaskService._last_cleanup_date == today:
            return 0

        # 获取昨天及之前未完成的任务
        result = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.task_date < today,
                    DailyTask.status.in_([TaskStatus.AVAILABLE, TaskStatus.ACCEPTED])
                )
            )
        )
        expired_tasks = result.scalars().all()

        # 标记为过期
        expired_count = 0
        for task in expired_tasks:
            task.expire_task()
            session.add(task)
            expired_count += 1

        # 更新清理日期缓存
        DailyTaskService._last_cleanup_date = today

        return expired_count
