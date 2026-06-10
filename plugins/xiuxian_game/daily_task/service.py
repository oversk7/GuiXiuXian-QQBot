"""每日任务系统服务类（DI版本）

基于 REFACTORING_PLAN_v4.md 的DI架构重构
"""
import random
from datetime import date, datetime, timedelta
from typing import List, Dict, Tuple, Optional

from ..models.player import Player
from ..models.daily_task import DailyTask, TaskType, TaskStatus
from ..models.npc import NPC, NPCType
from ..infrastructure.repositories.daily_task_repository import DailyTaskRepository
from ..world.location_service import LocationService
from ..world.npc_service import NPCService
from ..guild.guild_economy_service import GuildEconomyService


class DailyTaskService:
    """每日任务系统服务类（DI版本）"""

    # 类级别常量（保持不变）
    # 鬼怪名字池（扩展到200+个，降低重名概率）
    GHOST_NAMES = [
        # 原始50个名字
        "张伟", "王芳", "李娜", "刘强", "陈静", "杨明", "赵丽", "黄勇", "周敏", "吴华",
        "徐丽", "朱军", "林峰", "何静", "郭强", "马丽", "孙勇", "罗敏", "高峰", "梁静",
        "宋伟", "唐丽", "许强", "韩敏", "冯勇", "曹静", "彭峰", "董丽", "袁强", "蒋敏",
        "贾勇", "夏静", "邹峰", "施丽", "陆强", "孔敏", "崔勇", "史静", "龚峰", "邵丽",
        "段强", "雷敏", "黎勇", "薛静", "常峰", "武丽", "乔强", "钟敏", "谭勇", "戴静",

        # 扩展150个新名字（常见中文姓名）
        "魏建", "田霞", "汪杰", "蔡敏", "于涛", "杜娟", "叶辉", "范玲", "石磊", "姚鹏",
        "廖婷", "严浩", "沈燕", "陶飞", "江红", "金龙", "傅雪", "程刚", "秦慧", "齐军",
        "卢丽", "顾强", "任静", "毛峰", "郝伟", "覃芳", "邱明", "钱勇", "闫丽", "尹浩",
        "苗华", "易军", "丁丽", "余强", "戴敏", "柳峰", "滕静", "温伟", "景芳", "卜明",
        "包勇", "方丽", "柴静", "蓝峰", "苏伟", "万芳", "华明", "洪勇", "鲍丽", "龙静",
        "盛峰", "甘伟", "纪芳", "路明", "裴勇", "辛丽", "童静", "符峰", "芦伟", "仇芳",
        "宁明", "应勇", "汤丽", "向静", "隋峰", "管伟", "宗芳", "车明", "练勇", "晏丽",
        "左静", "时峰", "单伟", "井芳", "伏明", "阮勇", "全丽", "丛静", "葛峰", "奚伟",
        "封芳", "季明", "卫勇", "米丽", "缪静", "艾峰", "楚伟", "连芳", "窦明", "佘勇",
        "裘丽", "牛静", "关峰", "花伟", "麻芳", "游明", "殷勇", "晋丽", "原静", "巩峰",
        "霍伟", "查芳", "阎明", "尚勇", "湛丽", "焦静", "翟峰", "栾伟", "苟芳", "欧明",
        "莫勇", "卓丽", "祝静", "阳峰", "简伟", "舒芳", "庞明", "冉勇", "屈丽", "满静",
        "曾峰", "文伟", "祁芳", "农明", "经勇", "卢丽", "幸静", "解峰", "植伟", "麦芳",
        "宣明", "扈勇", "支丽", "危静", "揭峰", "相伟", "柯芳", "边明", "乐勇", "巫丽",
        "郁静", "茅峰", "荣伟", "郎芳", "师明", "钮勇", "明丽", "赖静", "干峰", "臧伟",
        "党芳", "鞠明", "郜勇", "亓丽", "隆静", "东峰", "逄伟", "蒙芳", "那明", "索勇"
    ]

    CITY_NAMES = [
        "长安", "洛阳", "金陵", "临安", "汴梁", "大梁", "邺城", "蓟城",
        "成都", "扬州", "苏州", "杭州", "开封", "太原", "西安", "北京",
    ]

    def __init__(
        self,
        daily_task_repo: DailyTaskRepository,
        location_service: LocationService,
        npc_service: NPCService,
        guild_economy_service: GuildEconomyService = None
    ):
        """
        初始化每日任务服务

        Args:
            daily_task_repo: 每日任务仓储（必需）
            location_service: 地点服务（必需，已DI改造）
            npc_service: NPC服务（必需，已DI改造）
            guild_economy_service: 公会经济服务（可选，已DI改造）
        """
        self._daily_task_repo = daily_task_repo
        self._location_service = location_service
        self._npc_service = npc_service
        self._guild_economy_service = guild_economy_service
        self._last_cleanup_date = None  # 实例级别缓存

    # ==================== 核心业务方法 ====================

    async def generate_daily_task(self, player: Player) -> DailyTask:
        """为玩家生成每日任务"""
        today = date.today()

        # 被动清理过期任务
        await self.check_and_cleanup_expired_tasks()

        # 检查今日可用任务数量（每天最多3个委托）
        existing_tasks = await self._daily_task_repo.find_all_by_player_and_date(player.id, today)
        if len(existing_tasks) >= 3:
            # 返回第一个可用的任务
            for task in existing_tasks:
                if task.is_available() or task.is_accepted():
                    return task
            # 如果都完成了，返回最后一个
            return existing_tasks[-1] if existing_tasks else None

        # 如果有未完成的任务，优先返回
        for task in existing_tasks:
            if task.is_available() or task.is_accepted():
                return task

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

        # 根据玩家等级和总战力计算敌人属性
        enemy_level = max(1, player.level + random.randint(-5, 5))
        enemy_stats = DailyTaskService._calculate_enemy_stats(enemy_level, player)

        # 计算奖励
        rewards = DailyTaskService._calculate_rewards(player.level, enemy_level, selected_task_type)

        # 根据任务类型生成不同的标题和敌人名称（简化鬼怪名字）
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

        # 使用Repository添加任务
        return await self._daily_task_repo.add(task)

    async def force_generate_new_task(self, player: Player) -> Optional[DailyTask]:
        """强制生成新的每日任务（用于刷新委托）"""
        today = date.today()

        # 被动清理过期任务
        await self.check_and_cleanup_expired_tasks()

        # 检查今日任务数量
        existing_tasks = await self._daily_task_repo.find_all_by_player_and_date(player.id, today)
        if len(existing_tasks) >= 3:
            return None  # 已达上限

        # 生成新任务的逻辑（与原generate_daily_task相同，但跳过检查）
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

        # 根据玩家等级和总战力计算敌人属性
        enemy_level = max(1, player.level + random.randint(-5, 5))
        enemy_stats = DailyTaskService._calculate_enemy_stats(enemy_level, player)

        # 计算奖励
        rewards = DailyTaskService._calculate_rewards(player.level, enemy_level, selected_task_type)

        # 根据任务类型生成不同的标题和敌人名称（简化鬼怪名字）
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

        # 使用Repository添加任务
        return await self._daily_task_repo.add(task)

    async def accept_task(self, task: DailyTask) -> Tuple[bool, str]:
        """接取任务"""
        # 被动清理过期任务
        await self.check_and_cleanup_expired_tasks()

        if not task.is_available():
            return False, "任务已被接取或已完成"

        # 在指定位置生成鬼怪NPC
        ghost_npc = await self.create_ghost_npc_for_task(task)
        if not ghost_npc:
            return False, "生成鬼怪NPC失败，请稍后重试"

        task.accept_task()
        await self._daily_task_repo.update(task)

        return True, f"✅ 成功接取任务：{task.title}\n👻 {task.enemy_name}已在{task.location_str}出现！"

    async def complete_task(self, player: Player, task: DailyTask) -> Tuple[bool, str, Dict]:
        """完成任务并发放奖励"""
        if not task.is_accepted():
            return False, "任务尚未接取或已完成", {}

        # 检查玩家是否在任务目标位置
        if player.x != task.target_x or player.y != task.target_y:
            return False, f"请先前往任务目标位置：{task.location_str}", {}

        # 检查指定的鬼怪NPC是否已死亡
        ghost_npc = await self._npc_service.get_npc_by_id(f"ghost_task_{task.id}")
        if not ghost_npc:
            return False, "找不到任务目标鬼怪，任务可能已过期", {}

        if not ghost_npc.is_dead():
            return False, f"任务目标{task.enemy_name}仍然存活，请击杀后再来完成任务", {}

        # 发放奖励
        rewards_given = {}

        # 经验奖励
        if task.exp_reward > 0:
            player.exp += task.exp_reward
            rewards_given["exp"] = task.exp_reward

        # 金币奖励
        if task.gold_reward > 0:
            player.gold += task.gold_reward
            # 更新财富成就统计
            from ..achievement.achievement_service import AchievementService
            await AchievementService.update_stat(self._daily_task_repo._session, player.id, "gold_earned_total", increment=task.gold_reward, auto_commit=False)
            rewards_given["gold"] = task.gold_reward

        # 积分奖励（无论是否有公会都给予）
        if task.guild_points_reward > 0:
            player.gold2 += task.guild_points_reward
            rewards_given["guild_points"] = task.guild_points_reward

        # 公会经验奖励（只有加入公会的玩家才能获得）
        if task.guild_points_reward > 0 and player.guild_id and self._guild_economy_service:
            base_guild_exp = DailyTaskService._calculate_guild_exp_reward(task.task_type, task.enemy_level)
            # 使用注入的GuildEconomyService实例（DI版本）
            guild_exp_gained = await self._guild_economy_service.add_guild_experience(
                player.guild_id, base_guild_exp
            )
            rewards_given["guild_exp"] = guild_exp_gained

        # 完成任务
        task.complete_task()
        await self._daily_task_repo.update(task)

        return True, "任务完成！", rewards_given

    async def get_task_summary(self, player_id: str) -> Dict:
        """获取玩家任务完成情况汇总"""
        today = date.today()

        # 被动清理过期任务
        await self.check_and_cleanup_expired_tasks()

        # 今日任务
        today_task = await self._daily_task_repo.find_by_player_and_date(player_id, today)

        # 本周完成任务数
        week_start = today - timedelta(days=today.weekday())
        weekly_completed = await self._daily_task_repo.count_weekly_completed(player_id, week_start)

        # 总完成任务数
        total_completed = await self._daily_task_repo.count_total_completed(player_id)

        return {
            "today_task": today_task,
            "weekly_completed": weekly_completed,
            "total_completed": total_completed
        }

    async def create_ghost_npc_for_task(self, task: DailyTask) -> Optional[NPC]:
        """为委托任务创建鬼怪NPC"""
        try:
            # 先检查是否已存在该NPC（防止重复创建）
            npc_id = f"ghost_task_{task.id}"
            existing_npc = await self._npc_service.get_npc_by_id(npc_id)
            if existing_npc:
                # 如果已存在，直接返回
                return existing_npc

            # 查找或创建目标地点
            location = await self._location_service.get_location_by_coordinates(
                task.target_x, task.target_y, task.target_region
            )

            if not location:
                # 先检查是否已存在该location_id（防止重复创建）
                location_id = f"task_location_{task.target_x}_{task.target_y}"
                location = await self._location_service.get_location_by_id(location_id)

                if not location:
                    # 创建临时地点
                    location = await self._location_service.create_location(
                        location_id=location_id,
                        name=f"荒野({task.target_x},{task.target_y})",
                        x=task.target_x,
                        y=task.target_y,
                        location_type="normal",
                        description="这里出现了异常的鬼怪活动...",
                        region=task.target_region
                    )

            # 创建鬼怪NPC
            ghost_npc = await self._npc_service.create_ghost_npc(
                npc_id=npc_id,
                name=task.enemy_name,
                location_id=location.id,
                level=task.enemy_level,
                hp=task.enemy_hp,
                attack=task.enemy_attack,
                defense=task.enemy_defense,
                agility=task.enemy_agility
            )

            # 设置任务关联
            if ghost_npc.extra_data is None:
                ghost_npc.extra_data = {}
            ghost_npc.extra_data["task_id"] = task.id
            # task.task_type可能是枚举对象或字符串,需要转换为字符串
            if hasattr(task.task_type, 'value'):
                ghost_npc.extra_data["task_type"] = task.task_type.value
            else:
                ghost_npc.extra_data["task_type"] = str(task.task_type)

            return ghost_npc

        except Exception as e:
            # 如果创建失败，不影响任务生成
            print(f"创建鬼怪NPC失败: {e}")
            return None

    async def find_task_ghost_npc(self, task: DailyTask) -> Optional[NPC]:
        """查找任务对应的鬼怪NPC"""
        # 查找目标地点
        location = await self._location_service.get_location_by_coordinates(
            task.target_x, task.target_y, task.target_region
        )

        if not location:
            return None

        # 查找鬼怪NPC
        npcs = await self._npc_service.get_npcs_by_location(location.id, NPCType.GHOST)

        for npc in npcs:
            if npc.extra_data and npc.extra_data.get("task_id") == task.id:
                return npc

        return None

    async def check_and_cleanup_expired_tasks(self) -> int:
        """检查并清理过期任务（被动触发，避免频繁执行）"""
        today = date.today()

        # 如果今天已经清理过，就不再重复清理
        if self._last_cleanup_date == today:
            return 0

        # 获取昨天及之前未完成的任务
        expired_tasks = await self._daily_task_repo.find_expired_tasks(today)

        # 标记为过期
        expired_count = 0
        for task in expired_tasks:
            task.expire_task()
            await self._daily_task_repo.update(task)
            expired_count += 1

        # 更新清理日期缓存
        self._last_cleanup_date = today

        return expired_count

    async def get_player_daily_tasks(self, player_id: str, task_date: date = None) -> List[DailyTask]:
        """获取玩家指定日期的所有每日任务"""
        if task_date is None:
            task_date = date.today()

        return await self._daily_task_repo.find_all_by_player_and_date(player_id, task_date)

    async def get_player_daily_task(self, player_id: str, task_date: date = None) -> Optional[DailyTask]:
        """获取玩家指定日期的第一个每日任务"""
        if task_date is None:
            task_date = date.today()

        return await self._daily_task_repo.find_by_player_and_date(player_id, task_date)

    # ==================== 纯计算方法（保留@staticmethod） ====================

    @staticmethod
    def _get_task_descriptions_by_type(task_type: TaskType, city_name: str, ghost_name: str) -> List[str]:
        """根据任务类型获取对应的任务描述"""
        if task_type == TaskType.PEN_SPIRIT_CASE:
            return [
                f"{city_name}城中近夜有诡异之事：居民夜半梦游，穿墙而过，手持黑笔，于空中书写。醒后皆不记所为，唯身生黑斑，日渐增多。据调查，此事与死者{ghost_name}有关，其生前酷爱书法，死后化为笔仙作祟。恳请道友速赴{city_name}城，超度此鬼。",
                f"闻{city_name}城中有死者{ghost_name}化身笔仙，夜入民宅，操控人心。被其蛊惑者皆夜半起身，手执黑笔，书写诡异文字，醒后身生梅花黑斑，痛痒难忍。此鬼善隐匿，难以察觉。望道友前往{city_name}城，寻此笔仙踪迹。",
                f"{city_name}城内近日怪事频发：有人夜半梦游，身如纸片，可穿墙遁地。醒后皆言不知所为，唯手中握有黑笔一支。经查，死者{ghost_name}生前为书法家，死后不散，化为笔仙作祟。恳请道友速往{city_name}城，破此梦游之术。",
                f"{city_name}城中传来怪谈：每逢子时，街巷墙壁上便自行浮现血色文字，皆为死者{ghost_name}生前未竟之遗书。凡读其文者，三日内必梦见一无面女子持笔立于枕畔，醒来枕下便多一张写满咒文的黄纸。已有数人因此疯癫，不知今夕何夕。望道友速赴{city_name}城，封印此笔仙怨念。",
                f"{city_name}城学堂中近日频现异象：学童们白日端坐读书，忽然双目失神，不由自主地提笔书写。所书之字非人间文字，笔迹与死者{ghost_name}生前手书一模一样。更诡异者，夜半时分，学堂中空无一人，却传来沙沙书写之声，烛火自燃自灭。此鬼执念深重，欲借童子之手续写未竟之书。恳请道友前往{city_name}城，渡此执念亡魂。",
                f"近闻{city_name}城中有一古井，夜半时分井水化墨，黑气升腾。死者{ghost_name}化为笔灵，以墨气为躯，游走于屋舍之间。凡被墨气沾染者，皮肤上便生出密密麻麻的细小文字，如虫蚁蠕动，刮之不去，洗之不掉，直至覆满全身。被害者最终口不能言，唯以手指不停书写。望道友速往{city_name}城，破此墨咒。",
                f"{city_name}城南有一废弃书斋，夜间常闻磨墨声与翻书声。据传死者{ghost_name}生前为落第书生，含恨而终，怨气化为笔仙。此鬼白日藏于砚台之中，夜晚便附身于人，强迫其抄写同一篇文章——一封永远寄不出的家书。被附者手腕青筋暴起，血管中似有墨汁流淌，面容枯槁如百岁老人。恳请道友速赴{city_name}城，了此亡魂心结。",
                f"{city_name}城中近日出现一件异常之物——一部无主的传音符。此符每日子时自行发出滴滴之声，屏上显现一行行文字，皆为死者{ghost_name}生前未发出的遗言。凡阅读此符之人，次日便会发现自己的传音符中也出现了同样的文字，且不断自行发送给通讯录中每一个人。更诡者，那些文字读来虽为寻常之语，却令读者不由自主地泪流满面、悲从中来，数人因此郁结于心，精神崩溃。此笔仙已由纸墨侵入灵器之中。望道友速赴{city_name}城，净化此受污染之灵器。",
                f"{city_name}城中有修士在旧货铺中购得一本古籍，封面无字，内页空白。然每至夜深，书页上便自行浮现密密麻麻的蝇头小楷，记录的竟是阅读者当日的一举一动，巨细靡遗，连心中所想亦一字不漏。此书越读越厚，永无尽头。据查，此为死者{ghost_name}怨念所化之'记忆簿'，凡被此书记录者，生平将被永久封存，本人则如被抽去记忆般渐渐忘却一切，最终沦为一具只会翻书的空壳。恳请道友速赴{city_name}城，焚毁此邪书。"
            ]
        elif task_type == TaskType.FAKE_IMMORTAL_CULT:
            return [
                f"闻{city_name}城中有死者{ghost_name}化为邪修，设神坛蛊惑民众。其生前或为修炼者，死后不甘，化为邪灵传授邪法。修者需以沸水灼身，以针刺骨，痛苦万分。然修者皆言此乃仙途必经，甘愿受苦。实则此鬼以痛苦为食。望道友前往{city_name}城，毁此邪坛。",
                f"{city_name}城遭死者{ghost_name}化成的邪修蛊惑，城中设有神像，红光照耀，香火不断。此鬼生前或为邪道中人，死后化为邪灵，继续传播邪法。修者需日夜跪拜，不得安眠。久之，修者皆成石像模样，僵硬不动，唯眼中有泪。恳请道友速赴{city_name}城，救此石化之民。",
                f"近闻{city_name}城中有死者{ghost_name}化为邪修，传授邪道经文，声称可得长生。此鬼生前或为邪教徒，死后不散，继续传播邪法。修者需承受非人折磨：沸水煮身、针刺入骨、悬梁练气。修者皆言此乃成仙正道，实为此鬼蛊惑。望道友前往{city_name}城，破此邪教。",
                f"{city_name}城外荒山忽现一座无名神社，社中供奉一尊面目模糊的木像，据传为死者{ghost_name}所化。每至黄昏，神社四周便响起低沉的诵经声，闻者不自觉地走向神社跪拜。入社者七日后目光呆滞，口中反复念叨同一句经文，问其何意却茫然不知。信众日增，城中已空去三成人口。恳请道友速赴{city_name}城，捣毁此妖社。",
                f"{city_name}城中近日有一游方道人，自称仙师，实为死者{ghost_name}怨灵所化。此鬼以幻术示人以仙境之景，令人心生向往，甘愿献出精血修炼所谓'仙法'。修者初时面色红润、精力充沛，然数日后便急剧衰老，肌肤干瘪如枯木，发白齿落，却仍沉浸于幻境不愿醒来。此鬼以生人精气为食，甚为歹毒。望道友前往{city_name}城，破此幻术邪法。",
                f"{city_name}城东有一古庙，夜间常传出百人齐声诵经之声。然推门而入，庙中空无一人，唯有满地白烛自燃。据查，死者{ghost_name}生前为一邪教祭司，死后不甘，以此古庙为巢穴，每夜引诱路人入庙。入庙者醒来后自称已悟大道，赤足不食，行为癫狂。更有甚者，以利刃划破掌心写下血书，誓言追随'仙师'。此鬼蛊惑之力甚深。恳请道友速往{city_name}城，焚此鬼庙。",
                f"近闻{city_name}城中出现一处地下洞窟，洞口不断飘出檀香气息。死者{ghost_name}化为白衣仙人端坐洞中，面容慈祥，口吐莲花，引得城中百姓纷纷前往聆听。然细观之，所谓仙人面皮之下隐隐可见森白骨相。信众跪拜日久，身上渐渐长出白色菌丝，如蛛网般蔓延。被菌丝覆盖者不痛不痒，反觉通体舒畅，直至被菌丝完全包裹，化为一具具白茧。望道友速赴{city_name}城，斩此菌鬼邪修。",
                f"{city_name}城中近日出现一座异常的自动售货机，无人知其来历。此机外表锈迹斑斑，屏幕上只显示一行字：'投入寿元，赐予机缘'。有贪者投入灵石，机中便吐出一枚金光闪闪的丹药，服后修为暴涨。然数日后，服丹者开始急剧衰老，仿佛一夜间过了数十年。据查，此售货机为死者{ghost_name}怨念凝聚之邪器，以'机缘'为饵，窃取生人寿元为己用。已有数人因贪图捷径而枯竭而亡。恳请道友速赴{city_name}城，销毁此邪器。",
                f"{city_name}城中流传着一个名为'回响'的修炼法门：修习者需在密室中播放一段来历不明的录音，录音内容为一个低沉的声音反复念诵经文。据说听满七七四十九遍便可顿悟大道。然凡听过此录音者，耳中便再也听不到其他声音，日夜只闻那段经文在脑中回荡，无法入睡、无法思考，最终精神崩溃。据查，此录音为死者{ghost_name}死前最后的诵经之声，怨念附着其上，化为声咒蛊惑人心。望道友速往{city_name}城，销毁所有录音拓本。"
            ]
        elif task_type == TaskType.SHAPE_SHIFTER_HUNT:
            return [
                f"{city_name}城内近日怪事频发：有人入室而不开门，有人变脸而不自知，有人身生肉洞而自残不止。皆因死者{ghost_name}化为变形怪作祟。此鬼生前或为术士，死后化为变形鬼，能操控人形，变化无常，极为危险。恳请道友速往{city_name}城，除此变形之鬼。",
                f"近日{city_name}城中监控尽失，天眼不明。有死者{ghost_name}化为变形怪，身如纸片，可穿墙遁地，来去无踪。此鬼生前或精通变化之术，死后化为变形鬼，城中居民夜不敢眠，恐遭此鬼侵扰。此鬼善隐匿，难以察觉，需高人出手。望道友前往{city_name}城，寻此隐形之鬼。",
                f"{city_name}城中有死者{ghost_name}化为变形怪，善变化，可化作任何人形，混入人群。此鬼生前或为江湖术士，死后不散，化为变形鬼。被其附身者面容渐变，行为诡异，最终失去人性。此鬼极为狡猾，难以分辨真假。恳请道友速赴{city_name}城，识破此变形之鬼。",
                f"{city_name}城中近日流传一则怪谈：城西老宅里住着一户人家，邻里皆言此家主人面善温和。然有心人察觉，此人白日之面与夜间之面并不相同——鼻梁高低有异，耳垂长短不一，甚至瞳孔颜色也日日变换。经查，真正的宅主早已失踪，现居者乃死者{ghost_name}所化之变形鬼，以蚕食宅主皮相维持人形。此鬼每七日需换一副面皮，已有数人无故失踪。恳请道友速赴{city_name}城，猎杀此窃皮之鬼。",
                f"近闻{city_name}城中有一怪事：城里的铜镜、水面、一切能映出倒影之物，皆开始映出与本人不同的面孔。死者{ghost_name}化为镜鬼，藏身于一切倒影之中，趁人不备便与映中之人对调。被替换者困于镜中，日渐消瘦透明，而镜鬼则堂而皇之地顶替其身份生活。城中已有十余人'性情大变'，家人虽觉异样，却无法指证。望道友速往{city_name}城，碎镜擒鬼。",
                f"{city_name}城中近夜出现一诡异之象：有人在街头撞见与自己一模一样的人。那'另一个自己'微笑不语，转身便消失于暗巷。凡见过自己分身者，此后便渐渐忘却自己是谁——先忘姓名，再忘亲人，最后忘却自己的面容。据查，死者{ghost_name}化为'合影鬼'，以窃取他人身份记忆为食。此鬼每夺一人记忆，便多一副可用之面。恳请道友速赴{city_name}城，斩断此鬼所窃之因缘线。",
                f"{city_name}城有一奇案：城中接连出现多具无面尸体——死者面部光滑如蛋，五官尽失，如同被人用手抹去一般。与此同时，城中多了许多'新面孔'，皆为此前从未见过之人。经查，死者{ghost_name}化为剥面鬼，专取活人面皮制成面具。此鬼收集面皮无数，可随意切换身份，行走于光天化日之下。城中人人自危，不敢与生人对视。望道友速往{city_name}城，诛此剥面恶鬼。",
                f"{city_name}城中近日出现一件异常之物——一面古旧的铜镜，不知何人放置于城中央的告示栏旁。此镜并不映照眼前之人，而是映出照镜者三日后的模样。起初众人只觉新奇，争相围观。然很快有人发现，镜中的'未来之我'开始做出本人从未做过的表情和动作，甚至朝镜外之人露出嘲讽的笑容。数日后，城中开始有人'变得不像自己'——据传是镜中之影取代了真身。死者{ghost_name}化为镜妖附于此物之上。恳请道友速赴{city_name}城，封印此镜。",
                f"{city_name}城中近日有人在深夜拾到一个做工精致的木偶人，高约一尺，面容酷似拾到者本人。此木偶被带回家后，每夜都会自行改变姿态——先是坐着，再是站着，然后转向门口。第七日清晨，主人发现木偶消失了，而自己的倒影变得不再跟随自己行动。据查，此木偶为死者{ghost_name}以怨念所制之替身傀儡，会逐渐取代真人的存在，令真人沦为无人能见的'透明人'。城中已有数人在众目睽睽之下'消失'，实则仍在原地，只是再无人能感知其存在。望道友速往{city_name}城，追回被夺之存在。"
            ]
        elif task_type == TaskType.STONE_CURSE_BREAK:
            return [
                f"{city_name}城遭死者{ghost_name}化成的石化怪诅咒，城中居民渐成石像。此鬼生前或为雕刻师，死后化为石化鬼，以石化诅咒害人。初时仅行动迟缓，继而肌肤僵硬，最终化为顽石。唯眼中尚有泪水，可知其痛苦。此诅咒传播极快，需速破解。恳请道友前往{city_name}城，破此石化之咒。",
                f"闻{city_name}城中有死者{ghost_name}化为石化怪，设石像神坛，凡拜者皆渐化石。此鬼生前或精通石雕之术，死后化为石化鬼，以石化为乐。城中已有数百人成石像，立于街头，神情痛苦。此鬼极为残忍。望道友速赴{city_name}城，毁此石像神坛。",
                f"{city_name}城内近日异象：居民皆面色苍白，行动僵硬，如石像般。疑为死者{ghost_name}化成的石化怪作祟，以诅咒控人。此鬼生前或为石匠，死后不散，化为石化鬼。被诅咒者渐失血肉，化为顽石，痛苦万分。恳请道友速往{city_name}城，解此石化之厄。",
                f"{city_name}城中传来令人胆寒之怪谈：城北园林中原有十二座栩栩如生的石像，然近日变为十三座——多出的那座石像，面容竟与昨日失踪的药铺掌柜一模一样。更骇人者，每至深夜，石像眼中便渗出血泪，嘴唇微微翕动，似在无声求救。据查，死者{ghost_name}化为石化鬼，以凝视之术将活人化为石像，却保留其意识，令其永世困于石躯之中，不生不死。恳请道友速赴{city_name}城，解救石中冤魂。",
                f"近闻{city_name}城中有一奇病蔓延：患者先是指尖变灰，继而双手僵硬如石，数日后蔓延至全身。更可怖者，被石化之人并未死去——若将耳朵贴近石像，可隐约听见其体内心脏仍在缓缓跳动，如敲石之声。据查，死者{ghost_name}化为石化鬼，以一种看不见的石粉散播诅咒，凡吸入者皆逃脱不了化石之厄。城中石像日增，活人日减。望道友速往{city_name}城，寻得解咒之法。",
                f"{city_name}城中近日传闻：城中心广场上的古老石碑忽然开裂，碑中走出一具灰白色人形，面如死灰，双目空洞。此物正是死者{ghost_name}所化之石化鬼。凡被其目光扫过者，身上便开始生出细密的石纹，如龟裂之大地。三日后石纹扩散全身，血肉化为白石，唯有一双眼睛尚能转动，目睹自己变为一尊永恒的雕像。此鬼以恐惧为食，愈恐惧则石化愈快。恳请道友速赴{city_name}城，封印此碑中恶鬼。",
                f"{city_name}城西有一座废弃石窟，近日有采药人误入其中，见窟壁上密密麻麻雕满人脸——每张脸表情各异，皆是惊恐、哀求、绝望之态，细看之下竟是城中历年失踪之人。据查，死者{ghost_name}化为石窟鬼，以石窟为巢穴，引诱路人入内。入窟者先觉双足沉重，继而下半身与地面融为一体，最终整个人被窟壁吞噬，只留一张脸嵌于石壁之上，永世不得超脱。望道友速往{city_name}城，破此石窟禁制。",
                f"{city_name}城中近日出现一件异常之物——一只精致的石质八音盒，旋开后奏出一段凄美的曲调。凡听到此曲者，先是指尖泛出灰白色泽，渐渐蔓延至手掌、手臂。奇怪的是，石化之处触感温热，并不冰冷，仿佛石头之下仍有血肉在跳动。据查，此八音盒为死者{ghost_name}怨念所铸，其生前为乐师，被人活埋于石棺之中，以乐声为怨，以石棺为咒。凡听其曲者，便如同被缓缓封入一口无形的石棺。望道友速赴{city_name}城，砸碎此八音盒。",
                f"{city_name}城中流传一种诡异的'石化照影术'：城中出现了一台来历不明的照影灵器，可为人拍下极为逼真的影像。然凡被此器拍过之人，影像中的自己竟比真人更加鲜活——影像会微笑、转头、甚至向观看者招手。而真人则日渐僵硬，面色灰白，最终彻底化为一尊灰白石像，而影像中的'自己'则变得越来越真实。据查，此灵器为死者{ghost_name}怨念附着之邪物，以影像窃取生人的'活性'，将真身化为永恒的静物。恳请道友速往{city_name}城，销毁此邪器。"
            ]
        elif task_type == TaskType.TORTURE_CULT_RAID:
            return [
                f"闻{city_name}城中有死者{ghost_name}化为邪教徒，传授锻体之法：以热水煮身，以苦胆入口，以悬梁练气。此鬼生前或为邪教头目，死后化为邪灵，继续传播邪法。修者皆言此乃成仙正道，然观其状，皆面容扭曲，痛苦不堪。实为此鬼以折磨为乐，蛊惑众生。望道友前往{city_name}城，破此酷刑之术。",
                f"{city_name}城中有死者{ghost_name}化为邪教徒，设酷刑道场，传授痛苦修炼法。此鬼生前或为酷刑师，死后不散，化为邪灵。修者需承受沸水灼身、针刺入骨、刀割血肉等酷刑。修者皆言痛苦乃成仙必经，甘愿受虐。实为此鬼以痛苦为食。恳请道友速赴{city_name}城，毁此酷刑道场。",
                f"近日{city_name}城中异象频生：有人自残不止，有人痛苦哀嚎，有人身生肉洞。皆因死者{ghost_name}化为邪教徒，传授酷刑修炼法所致。此鬼生前或为虐待狂，死后化为邪灵，善蛊惑人心，以折磨为乐。恳请道友速往{city_name}城，除此酷刑之鬼。",
                f"{city_name}城地下发现一处密室，室内遍布锈迹斑斑的铁链与刑具，墙上血迹层层叠叠，新旧交错。据查，死者{ghost_name}化为刑鬼，以此密室为巢穴，每夜引诱城中之人前来'修行'。被引诱者心甘情愿地将自己绑缚于刑架之上，面露痴迷之色，口中喃喃道'痛即是道'。此鬼以受刑者的痛苦为养分，越痛越强。更可怕者，受过刑罚之人离去后亦会引诱他人前来，如瘟疫般蔓延。恳请道友速赴{city_name}城，封印此地下刑狱。",
                f"近闻{city_name}城中出现一种名为'百骨炼'的邪术，修习者需以铁针刺入全身一百零八处穴位，据称可打通经脉、脱胎换骨。此邪术源自死者{ghost_name}所化之刑鬼。修习者初时确能感受到一股暖流遍布全身，然数日后针孔处便渗出黑血，穴位溃烂，痛不欲生。然此时已无法拔针——铁针已与骨肉融为一体，受害者沦为人形针垫，日夜哀嚎。望道友速往{city_name}城，破此百骨之邪术。",
                f"{city_name}城中近日有一怪异仪式悄然流行：参与者需在子夜赤足行走于碎瓷片之上，穿越火坑，最后以滚烫铜汁浇灌双手，美其名曰'淬火炼魂'。死者{ghost_name}化为刑鬼，以此仪式为饵，吸食参与者的痛苦与恐惧。受害者双手虽被烫成焦炭，却诡异地不觉疼痛，反而面露狂喜之色，四处宣扬此术之妙。此鬼蛊惑甚深，信众日增，已有数十人沦为此鬼之'信徒'。恳请道友速赴{city_name}城，斩此刑鬼。",
                f"{city_name}城外有一废弃铁匠铺，每到深夜便传出叮叮当当的打铁声与凄厉的惨叫声。有胆大者窥探，见一白衣身影正将活人放入炉中锻打，如打铁一般。死者{ghost_name}化为锻骨鬼，声称可为人重铸筋骨、脱胎换骨。然被'锻打'之人虽未死去，骨骼却被重新排列成扭曲之态，四肢反曲，脊柱弯折，如同一具被折叠的人偶，再无法恢复人形。望道友速往{city_name}城，灭此锻骨邪鬼。",
                f"{city_name}城中近日出现一种诡异的灵器——一副纯黑色的耳坠，佩戴者声称能听到'天道之音'。然实际上，耳坠会在佩戴者耳中不断播放一种令人极度痛苦的尖锐噪音，却同时释放一种令人上瘾的快感。佩戴者痛并快乐着，无法摘下耳坠，最终耳膜破裂、七窍流血而亡，面上却挂着狂喜的笑容。据查，此耳坠为死者{ghost_name}怨念所化之刑器，生前为一刑讯之人，死后以此物延续其对痛苦的执念。恳请道友速赴{city_name}城，收缴所有流通的黑耳坠。",
                f"{city_name}城中有人建了一座'体验馆'，声称可让人体验前世之苦以消今生之业。入馆者被绑缚于一台铁椅之上，头戴铁冠，眼前浮现出种种酷刑景象——凌迟、炮烙、车裂，历历在目，痛感真实无比。然所谓体验不过是死者{ghost_name}所设之精神刑狱，受刑者的痛苦会被此鬼吸食为养分。更可怕者，出馆之人虽身无伤痕，精神却已被折磨至崩溃边缘，夜夜噩梦重温刑罚之苦，数人因此疯癫自尽。望道友速往{city_name}城，捣毁此精神刑狱。"
            ]
        else:
            # 默认的鬼怪消除任务描述
            return [
            # 真人名字的鬼怪作祟任务
            f"近日{city_name}城中异象频生，死者{ghost_name}化为厉鬼，四处作祟害人。其生前或有冤屈，死后怨气不散，常于夜间出没，吓唬路人，甚至附身害命。此鬼戾气极重，已伤及无辜数人。恳请道友前往{city_name}城，超度此鬼。",

            f"{city_name}城内阴气弥漫，死者{ghost_name}化为恶鬼，夜夜作祟。其生前或遭横死，死后不甘，化为厉鬼报复世人。凡遇此鬼者，轻则大病一场，重则性命不保。城中百姓人心惶惶，不敢夜出。望道友速赴{city_name}城，除此大害。",

            f"闻{city_name}城中有死者{ghost_name}化为恶鬼，专门害人性命。此鬼手段残忍，已有多人遇害。当地百姓避之不及，夜不敢出门。据传此鬼生前身份不明，死后怨气冲天，化为厉鬼作祟。望道友速赴{city_name}城，诛杀此鬼。",

            f"{city_name}城遭死者{ghost_name}化成的厉鬼侵扰，此鬼生前或有深仇大恨，死后不散，化为恶鬼害人。城中已有数人被其害死，百姓惶恐不安。此鬼凶残异常，普通人根本无法对付。恳请道友前往{city_name}城，超度此恶鬼。",

            f"近闻{city_name}城中出现恶鬼{ghost_name}，此鬼生前身份成谜，死后化为厉鬼，专门寻仇报复。凡与其有过节者，皆遭其害。城中人人自危，不知何时会成为下一个受害者。实为{ghost_name}怨气太重，化鬼作祟。望道友速往{city_name}城，除此恶鬼。",

            f"{city_name}城中近日香火鼎盛，皆因有{ghost_name}化身仙师，传授修仙之法。城中男女老幼皆言得遇真仙，日夜修炼不辍。然观其修者，皆面色青白，双目无神，言语失常，行为怪异。此非修仙，实为鬼道蛊惑。恳请道友前往{city_name}城，破此迷障。",

            # 基于《厉鬼纪元》新增的任务类型
            f"{city_name}城中近夜有诡异之事：居民夜半梦游，穿墙而过，手持黑笔，于空中书写。醒后皆不记所为，唯身生黑斑，日渐增多。疑为{ghost_name}作祟，以笔墨控人心神。恳请道友速赴{city_name}城，破此笔仙之术。",

            f"闻{city_name}城中有{ghost_name}设神坛，供奉石像，传授修炼之法。修者需以沸水灼身，以针刺骨，痛苦万分。然修者皆言此乃仙途必经，甘愿受苦。实则此鬼以痛苦为食，蛊惑人心。望道友前往{city_name}城，毁此邪坛。",

            f"{city_name}城内近日怪事频发：有人入室而不开门，有人变脸而不自知，有人身生肉洞而自残不止。皆因{ghost_name}化身道长，传授邪法所致。此鬼能操控人形，变化无常，极为危险。恳请道友速往{city_name}城，除此变形之鬼。",

            f"近日{city_name}城中监控尽失，天眼不明。有{ghost_name}化身修者，身如纸片，可穿墙遁地，来去无踪。城中居民夜不敢眠，恐遭此鬼侵扰。此鬼善隐匿，难以察觉，需高人出手。望道友前往{city_name}城，寻此隐形之鬼。",

            f"{city_name}城遭{ghost_name}蛊惑，城中设有神像，红光照耀，香火不断。修者需日夜跪拜，不得安眠。久之，修者皆成石像模样，僵硬不动，唯眼中有泪。此鬼以人为石，极为残忍。恳请道友速赴{city_name}城，救此石化之民。",

            f"闻{city_name}城中有{ghost_name}传授锻体之法：以热水煮身，以苦胆入口，以悬梁练气。修者皆言此乃成仙正道，然观其状，皆面容扭曲，痛苦不堪。实为此鬼以折磨为乐，蛊惑众生。望道友前往{city_name}城，破此酷刑之术。",

            # 怪谈与日式鬼怪风格新增
            f"{city_name}城中近日流传一则怪谈：每逢雨夜，城中十字路口便出现一名撑着红伞的女子，面色苍白如纸，嘴角挂着诡异的微笑。凡与其对视者，此后每夜都会梦见自己站在同一个十字路口，而那女子渐渐向自己走来。梦中的距离一夜比一夜近，直到第七夜——此后那人便再也没有醒来。据查，此为死者{ghost_name}怨念所化，以梦境吞噬人魂。恳请道友速赴{city_name}城，斩断此梦中因缘。",

            f"{city_name}城中有一间常年紧锁的空屋，近日门缝中不断渗出带着腐臭的冷风。有人趴在门缝窥视，只见屋内漆黑一片，唯有角落里蹲着一个白衣人影，长发垂地，正缓缓转头。窥视者当场吓得昏厥，醒来后发现自己头发一夜全白，且再也无法闭眼入睡——每当闭眼便看见那张苍白的脸在黑暗中微笑。据查，此为死者{ghost_name}化为屋守鬼作祟。望道友速往{city_name}城，驱逐此鬼。",

            f"近闻{city_name}城北古桥之下，每至丑时便传来孩童的嬉笑声与拍手声。有人好奇探看，见桥下水面上漂浮着数个惨白人头，皆闭目微笑。待定睛再看，水面空无一物，唯有自己的倒影诡异地朝自己招手。此后数日，探看者总觉身后有人跟随，余光中能看见一道湿漉漉的身影，却永远无法正面看清。据查，死者{ghost_name}溺亡于此桥下，怨气化为水鬼，专引活人替死。恳请道友速赴{city_name}城，渡此水中冤魂。",

            f"{city_name}城中流传一种诡异现象：城中所有钟表在每日凌晨两点十三分同时停止，持续整整四分钟后恢复正常。而在这四分钟内，有人声称看见城中街道上行走着无数透明的人影，皆是已故之人的模样。更有人发现，每过一夜，自己家中便多出一样不属于自己的物品——一只旧鞋、一把断梳、一面碎镜。据查，死者{ghost_name}化为时隙鬼，撕裂了阴阳之间的缝隙，令亡者得以短暂回归阳世。望道友速往{city_name}城，修补此阴阳裂隙。",

            f"{city_name}城中近日有一怪谈广为流传：城南巷口的老槐树上，夜半时分会出现一个倒悬的人影——头朝下，长发拖地，双手垂于身侧，如同一只巨大的蝙蝠。凡从树下经过者，第二日起便觉得天旋地转，看一切事物都是颠倒的。此后病情日渐加重，患者开始倒行逆施、言语颠倒，最终整个人如同被翻转了一般，五脏六腑错位而亡。据查，死者{ghost_name}化为倒悬鬼，以颠倒之术害人。恳请道友速赴{city_name}城，斩此倒悬邪祟。",

            f"{city_name}城中近日接连发生怪事：数户人家的墙壁上出现了潮湿的手印，手印逐日增多，由外墙蔓延至内室，最终爬满天花板。更诡异者，手印似乎在缓慢移动——白日看尚在东墙，夜半再看已移至西墙。凡手印爬满之屋，屋中之人便无故失踪，只留下一地湿漉漉的脚印，通向墙壁深处。据查，死者{ghost_name}化为壁中鬼，将活人拖入墙壁之中。城中已有数人消失于墙内，至今生死不明。望道友速往{city_name}城，破壁救人。",

            # 现代异常物品与日式怪谈风格
            f"{city_name}城中近日出现一台异常的扭蛋机，外壳鲜红，不知何时何人放置于城中集市。投入灵石后可得一枚透明扭蛋，内装一张写有姓名的纸条——每次都是投币者认识之人的名字。次日，纸条上的那人便会突发怪病、遭遇意外，甚至凭空消失。更诡异的是，此扭蛋机每日子时会自行运转，吐出一枚无人认领的扭蛋。据查，此物为死者{ghost_name}怨念凝结之邪器，以诅咒为蛋，以熟人为靶。恳请道友速赴{city_name}城，销毁此诅咒扭蛋机。",

            f"{city_name}城中近日有一怪谈广为流传：城中某处楼梯，上行时为十三阶，下行时却变为十四阶。凡数出第十四阶者，此后便会不断遇见一名不存在于世上的'第十四个人'——此人总在人群中微笑注视，却无人能看见他。被注视者渐渐变得不安、多疑、失眠，最终在某个深夜独自走向那段楼梯，从此再也没有回来。据查，死者{ghost_name}化为阶梯鬼，以楼梯为境界之门，引诱生人步入永无尽头的异空间。望道友速往{city_name}城，封印此楼梯。",

            f"{city_name}城中有人在路边拾到一只旧手表，此表指针逆时针旋转，且无法丢弃——丢出多远，第二日清晨必回到拾者枕边。佩戴此表之人开始经历'时间倒流'：先是忘记今日之事，接着忘记昨日，渐渐连亲友的面孔、自己的姓名都忘得一干二净，最终退化为婴儿状态。据查，此表为死者{ghost_name}怨念附着之物——其生前执着于回到过去弥补遗憾，死后怨念化为此表，令佩戴者的时间不断倒退。恳请道友速赴{city_name}城，打碎此轮回表。",

            f"{city_name}城中出现一种异常现象：每到深夜，城中某些巷口便会凭空出现一扇红色的门。此门白日不可见，唯有独行之人在午夜时分方能看到。有好奇者推门而入，门后是一条无尽的走廊，两侧挂满了看不清面容的肖像画。据归来者描述（极少数人能回来），画中之人的目光会跟随行人移动，走得越深画中人的表情越扭曲，直到走廊尽头——那里站着一个与自己一模一样的人，背对着自己，正缓缓转头。凡看清那张脸的人，此后再也没有回来。据查，此门为死者{ghost_name}怨念所化之鬼门，连接生死之间的狭间空间。望道友速往{city_name}城，封印此鬼门。",

            f"{city_name}城中近日有修士发现一件异常之物——一只会自行书写的毛笔。此笔无需人握，每夜自行在桌案上书写，内容皆为第二日将要发生之事，且无一不应验。起初有人以此趋吉避凶，然渐渐发现此笔开始书写恐怖之事：'明日午时，三人将死于东街'、'后日子时，红衣女子现于古井'。而这些可怖预言亦一一成真。更可怕的是，此笔最近写下了一行话：'此笔之持有者，七日后将...'后面的字迹被血迹覆盖，无法辨认。据查，此笔为死者{ghost_name}执念所化之预言凶器。恳请道友速赴{city_name}城，毁此凶笔。"
        ]

    @staticmethod
    def _generate_task_title_and_enemy(task_type: TaskType, city_name: str, ghost_name: str) -> Tuple[str, str]:
        """根据任务类型生成任务标题和敌人名称"""
        if task_type == TaskType.GHOST_ELIMINATION:
            return f"缉邪司委托：{city_name}城鬼怪{ghost_name}作祟事件", f"鬼怪·{ghost_name}"
        elif task_type == TaskType.PEN_SPIRIT_CASE:
            return f"缉邪司委托：{city_name}城笔仙{ghost_name}梦游案", f"笔仙·{ghost_name}"
        elif task_type == TaskType.FAKE_IMMORTAL_CULT:
            return f"缉邪司委托：{city_name}城邪修{ghost_name}蛊惑案", f"邪修·{ghost_name}"
        elif task_type == TaskType.SHAPE_SHIFTER_HUNT:
            return f"缉邪司委托：{city_name}城变形怪{ghost_name}追捕令", f"变形怪·{ghost_name}"
        elif task_type == TaskType.STONE_CURSE_BREAK:
            return f"缉邪司委托：{city_name}城石化怪{ghost_name}破解案", f"石化怪·{ghost_name}"
        elif task_type == TaskType.TORTURE_CULT_RAID:
            return f"缉邪司委托：{city_name}城邪教徒{ghost_name}清剿令", f"邪教徒·{ghost_name}"
        else:
            # 默认情况
            return f"缉邪司委托：{city_name}城鬼怪{ghost_name}事件", f"鬼怪·{ghost_name}"

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
    def _calculate_player_power_score(player) -> float:
        """计算玩家的综合战力评分

        Args:
            player: 玩家对象

        Returns:
            玩家的综合战力评分
        """
        # 基础属性权重
        base_score = (
            player.attack * 2.0 +      # 攻击力权重最高
            player.defense * 1.5 +     # 防御力次之
            player.max_hp * 0.5 +      # 血量
            player.agility * 1.2 +     # 敏捷
            player.luck * 0.8          # 运气
        )

        # 战斗属性加成（这些属性对战斗力影响很大）
        battle_bonus = (
            player.critical_rate * 3.0 +      # 暴击率
            player.critical_power * 5.0 +     # 暴击力
            player.combo_rate * 2.5 +         # 连击率
            player.counter_rate * 2.0 +       # 反击率
            player.dodge_rate * 2.0 +         # 闪避率
            (player.accuracy_rate - 80) * 1.5 + # 命中率（基础80，超出部分有价值）
            player.skill_crit_rate * 2.5 +    # 灵爆率
            player.penetration_rate * 3.0     # 穿透率
        )

        # 等级加成
        level_bonus = player.level * 10

        return base_score + battle_bonus + level_bonus

    @staticmethod
    def _calculate_enemy_stats(enemy_level: int, player=None) -> Dict[str, int]:
        """计算敌人属性

        Args:
            enemy_level: 敌人等级
            player: 玩家对象（用于计算难度调整）

        Returns:
            敌人属性字典
        """
        # 基础属性计算
        base_hp = 100 + enemy_level * 4
        base_attack = 20 + enemy_level * 2
        base_defense = 10 + enemy_level * 2
        base_agility = 15 + enemy_level * 2

        # 如果提供了玩家信息，根据玩家战力调整敌人强度
        difficulty_multiplier = 1.0
        if player:
            player_power = DailyTaskService._calculate_player_power_score(player)
            # 根据玩家战力计算期望的同等级战力
            # 调整期望战力，让它更符合实际玩家的战力水平
            expected_power = player.level * 20  # 降低基础期望战力

            # 计算玩家相对强度（战力/期望战力）
            relative_strength = player_power / max(expected_power, 1)

            # 根据相对强度调整敌人难度
            # 玩家越强，敌人相对越弱（降低难度）
            # 整体降低难度，让委托任务更容易完成
            if relative_strength > 1.5:
                # 玩家很强，敌人减弱50%
                difficulty_multiplier = 1.1
            elif relative_strength > 1.2:
                # 玩家较强，敌人减弱40%
                difficulty_multiplier = 1
            elif relative_strength > 1.0:
                # 玩家正常，敌人减弱30%
                difficulty_multiplier = 0.8
            elif relative_strength > 0.8:
                # 玩家较弱，敌人减弱20%
                difficulty_multiplier = 0.7
            elif relative_strength > 0.6:
                # 玩家弱，敌人减弱15%
                difficulty_multiplier = 0.7
            else:
                # 玩家很弱，敌人减弱10%
                difficulty_multiplier = 0.7

        # 应用难度调整
        base_hp = int(base_hp * difficulty_multiplier)
        base_attack = int(base_attack * difficulty_multiplier)
        base_defense = int(base_defense * difficulty_multiplier)
        base_agility = int(base_agility * difficulty_multiplier)

        # 添加随机波动（±15%，比原来的20%稍微减少一些）
        hp = int(base_hp * random.uniform(0.85, 1.15))
        attack = int(base_attack * random.uniform(0.85, 1.15))
        defense = int(base_defense * random.uniform(0.85, 1.15))
        agility = int(base_agility * random.uniform(0.85, 1.15))

        # 确保最小值
        hp = max(hp, 10)
        attack = max(attack, 5)
        defense = max(defense, 1)
        agility = max(agility, 5)

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
