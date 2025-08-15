"""每日任务系统服务类"""
import random
from datetime import date, datetime
from typing import List, Dict, Tuple, Optional
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.daily_task import DailyTask, TaskType, TaskStatus
from ..models.location import Location
from ..models.npc import NPC, NPCType
from ..world.location_service import LocationService
from ..world.npc_service import NPCService
from ..config import config


class DailyTaskService:
    """每日任务系统服务类"""

    # 用于避免频繁清理的缓存
    _last_cleanup_date = None
    
    # 真人名字池，增加代入感
    GHOST_NAMES = [
        "张伟", "王芳", "李娜", "刘强", "陈静", "杨明", "赵丽", "黄勇", "周敏", "吴华",
        "徐丽", "朱军", "林峰", "何静", "郭强", "马丽", "孙勇", "罗敏", "高峰", "梁静",
        "宋伟", "唐丽", "许强", "韩敏", "冯勇", "曹静", "彭峰", "董丽", "袁强", "蒋敏",
        "贾勇", "夏静", "邹峰", "施丽", "陆强", "孔敏", "崔勇", "史静", "龚峰", "邵丽",
        "段强", "雷敏", "黎勇", "薛静", "常峰", "武丽", "乔强", "钟敏", "谭勇", "戴静"
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

        # 检查今日可用任务数量（每天最多3个委托）
        existing_tasks = await DailyTaskService.get_player_daily_tasks(session, player.id, today)
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

        session.add(task)

        # 不在生成任务时创建NPC，而是在接取任务时创建

        return task

    @staticmethod
    async def force_generate_new_task(session: AsyncSession, player: Player) -> Optional[DailyTask]:
        """强制生成新的每日任务（用于刷新委托）"""
        today = date.today()

        # 被动清理过期任务
        await DailyTaskService.check_and_cleanup_expired_tasks(session)

        # 检查今日任务数量
        existing_tasks = await DailyTaskService.get_player_daily_tasks(session, player.id, today)
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

        session.add(task)
        return task

    @staticmethod
    def _get_task_descriptions_by_type(task_type: TaskType, city_name: str, ghost_name: str) -> List[str]:
        """根据任务类型获取对应的任务描述"""
        if task_type == TaskType.PEN_SPIRIT_CASE:
            return [
                f"{city_name}城中近夜有诡异之事：居民夜半梦游，穿墙而过，手持黑笔，于空中书写。醒后皆不记所为，唯身生黑斑，日渐增多。据调查，此事与死者{ghost_name}有关，其生前酷爱书法，死后化为笔仙作祟。恳请道友速赴{city_name}城，超度此鬼。",
                f"闻{city_name}城中有死者{ghost_name}化身笔仙，夜入民宅，操控人心。被其蛊惑者皆夜半起身，手执黑笔，书写诡异文字，醒后身生梅花黑斑，痛痒难忍。此鬼善隐匿，难以察觉。望道友前往{city_name}城，寻此笔仙踪迹。",
                f"{city_name}城内近日怪事频发：有人夜半梦游，身如纸片，可穿墙遁地。醒后皆言不知所为，唯手中握有黑笔一支。经查，死者{ghost_name}生前为书法家，死后不散，化为笔仙作祟。恳请道友速往{city_name}城，破此梦游之术。"
            ]
        elif task_type == TaskType.FAKE_IMMORTAL_CULT:
            return [
                f"闻{city_name}城中有死者{ghost_name}化为邪修，设神坛蛊惑民众。其生前或为修炼者，死后不甘，化为邪灵传授邪法。修者需以沸水灼身，以针刺骨，痛苦万分。然修者皆言此乃仙途必经，甘愿受苦。实则此鬼以痛苦为食。望道友前往{city_name}城，毁此邪坛。",
                f"{city_name}城遭死者{ghost_name}化成的邪修蛊惑，城中设有神像，红光照耀，香火不断。此鬼生前或为邪道中人，死后化为邪灵，继续传播邪法。修者需日夜跪拜，不得安眠。久之，修者皆成石像模样，僵硬不动，唯眼中有泪。恳请道友速赴{city_name}城，救此石化之民。",
                f"近闻{city_name}城中有死者{ghost_name}化为邪修，传授邪道经文，声称可得长生。此鬼生前或为邪教徒，死后不散，继续传播邪法。修者需承受非人折磨：沸水煮身、针刺入骨、悬梁练气。修者皆言此乃成仙正道，实为此鬼蛊惑。望道友前往{city_name}城，破此邪教。"
            ]
        elif task_type == TaskType.SHAPE_SHIFTER_HUNT:
            return [
                f"{city_name}城内近日怪事频发：有人入室而不开门，有人变脸而不自知，有人身生肉洞而自残不止。皆因死者{ghost_name}化为变形怪作祟。此鬼生前或为术士，死后化为变形鬼，能操控人形，变化无常，极为危险。恳请道友速往{city_name}城，除此变形之鬼。",
                f"近日{city_name}城中监控尽失，天眼不明。有死者{ghost_name}化为变形怪，身如纸片，可穿墙遁地，来去无踪。此鬼生前或精通变化之术，死后化为变形鬼，城中居民夜不敢眠，恐遭此鬼侵扰。此鬼善隐匿，难以察觉，需高人出手。望道友前往{city_name}城，寻此隐形之鬼。",
                f"{city_name}城中有死者{ghost_name}化为变形怪，善变化，可化作任何人形，混入人群。此鬼生前或为江湖术士，死后不散，化为变形鬼。被其附身者面容渐变，行为诡异，最终失去人性。此鬼极为狡猾，难以分辨真假。恳请道友速赴{city_name}城，识破此变形之鬼。"
            ]
        elif task_type == TaskType.STONE_CURSE_BREAK:
            return [
                f"{city_name}城遭死者{ghost_name}化成的石化怪诅咒，城中居民渐成石像。此鬼生前或为雕刻师，死后化为石化鬼，以石化诅咒害人。初时仅行动迟缓，继而肌肤僵硬，最终化为顽石。唯眼中尚有泪水，可知其痛苦。此诅咒传播极快，需速破解。恳请道友前往{city_name}城，破此石化之咒。",
                f"闻{city_name}城中有死者{ghost_name}化为石化怪，设石像神坛，凡拜者皆渐化石。此鬼生前或精通石雕之术，死后化为石化鬼，以石化为乐。城中已有数百人成石像，立于街头，神情痛苦。此鬼极为残忍。望道友速赴{city_name}城，毁此石像神坛。",
                f"{city_name}城内近日异象：居民皆面色苍白，行动僵硬，如石像般。疑为死者{ghost_name}化成的石化怪作祟，以诅咒控人。此鬼生前或为石匠，死后不散，化为石化鬼。被诅咒者渐失血肉，化为顽石，痛苦万分。恳请道友速往{city_name}城，解此石化之厄。"
            ]
        elif task_type == TaskType.TORTURE_CULT_RAID:
            return [
                f"闻{city_name}城中有死者{ghost_name}化为邪教徒，传授锻体之法：以热水煮身，以苦胆入口，以悬梁练气。此鬼生前或为邪教头目，死后化为邪灵，继续传播邪法。修者皆言此乃成仙正道，然观其状，皆面容扭曲，痛苦不堪。实为此鬼以折磨为乐，蛊惑众生。望道友前往{city_name}城，破此酷刑之术。",
                f"{city_name}城中有死者{ghost_name}化为邪教徒，设酷刑道场，传授痛苦修炼法。此鬼生前或为酷刑师，死后不散，化为邪灵。修者需承受沸水灼身、针刺入骨、刀割血肉等酷刑。修者皆言痛苦乃成仙必经，甘愿受虐。实为此鬼以痛苦为食。恳请道友速赴{city_name}城，毁此酷刑道场。",
                f"近日{city_name}城中异象频生：有人自残不止，有人痛苦哀嚎，有人身生肉洞。皆因死者{ghost_name}化为邪教徒，传授酷刑修炼法所致。此鬼生前或为虐待狂，死后化为邪灵，善蛊惑人心，以折磨为乐。恳请道友速往{city_name}城，除此酷刑之鬼。"
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

            f"闻{city_name}城中有{ghost_name}传授锻体之法：以热水煮身，以苦胆入口，以悬梁练气。修者皆言此乃成仙正道，然观其状，皆面容扭曲，痛苦不堪。实为此鬼以折磨为乐，蛊惑众生。望道友前往{city_name}城，破此酷刑之术。"
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
    
    @staticmethod
    async def get_player_daily_task(session: AsyncSession, player_id: str, task_date: date = None) -> Optional[DailyTask]:
        """获取玩家指定日期的第一个每日任务"""
        if task_date is None:
            task_date = date.today()

        result = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.task_date == task_date
                )
            ).order_by(DailyTask.id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_player_daily_tasks(session: AsyncSession, player_id: str, task_date: date = None) -> List[DailyTask]:
        """获取玩家指定日期的所有每日任务"""
        if task_date is None:
            task_date = date.today()

        result = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.task_date == task_date
                )
            ).order_by(DailyTask.id)
        )
        return result.scalars().all()
    
    @staticmethod
    async def accept_task(session: AsyncSession, task: DailyTask) -> Tuple[bool, str]:
        """接取任务"""
        # 被动清理过期任务
        await DailyTaskService.check_and_cleanup_expired_tasks(session)

        if not task.is_available():
            return False, "任务已被接取或已完成"

        # 在指定位置生成鬼怪NPC
        ghost_npc = await DailyTaskService.create_ghost_npc_for_task(session, task)
        if not ghost_npc:
            return False, "生成鬼怪NPC失败，请稍后重试"

        task.accept_task()
        session.add(task)

        return True, f"✅ 成功接取任务：{task.title}\n👻 {task.enemy_name}已在{task.location_str}出现！"
    
    @staticmethod
    async def complete_task(session: AsyncSession, player: Player, task: DailyTask) -> Tuple[bool, str, Dict]:
        """完成任务并发放奖励"""
        if not task.is_accepted():
            return False, "任务尚未接取或已完成", {}

        # 检查玩家是否在任务目标位置
        if player.x != task.target_x or player.y != task.target_y:
            return False, f"请先前往任务目标位置：{task.location_str}", {}

        # 检查指定的鬼怪NPC是否已死亡
        from ..world.npc_service import NPCService
        ghost_npc = await NPCService.get_npc_by_id(session, f"ghost_task_{task.id}")
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
            rewards_given["gold"] = task.gold_reward

        # 积分奖励（无论是否有公会都给予）
        if task.guild_points_reward > 0:
            player.gold2 += task.guild_points_reward
            rewards_given["guild_points"] = task.guild_points_reward

        # 公会经验奖励（只有加入公会的玩家才能获得）
        if task.guild_points_reward > 0 and player.guild_id:
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

    @staticmethod
    async def create_ghost_npc_for_task(session: AsyncSession, task: DailyTask) -> Optional[NPC]:
        """为委托任务创建鬼怪NPC"""
        try:
            # 查找或创建目标地点
            location = await LocationService.get_location_by_coordinates(
                session, task.target_x, task.target_y, task.target_region
            )

            if not location:
                # 创建临时地点
                location = await LocationService.create_location(
                    session,
                    location_id=f"task_location_{task.target_x}_{task.target_y}",
                    name=f"荒野({task.target_x},{task.target_y})",
                    x=task.target_x,
                    y=task.target_y,
                    location_type="normal",
                    description="这里出现了异常的鬼怪活动...",
                    region=task.target_region
                )

            # 创建鬼怪NPC
            ghost_npc = await NPCService.create_ghost_npc(
                session,
                npc_id=f"ghost_task_{task.id}",
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
            ghost_npc.extra_data["task_type"] = task.task_type.value

            return ghost_npc

        except Exception as e:
            # 如果创建失败，不影响任务生成
            print(f"创建鬼怪NPC失败: {e}")
            return None

    @staticmethod
    async def find_task_ghost_npc(session: AsyncSession, task: DailyTask) -> Optional[NPC]:
        """查找任务对应的鬼怪NPC"""
        # 查找目标地点
        location = await LocationService.get_location_by_coordinates(
            session, task.target_x, task.target_y, task.target_region
        )

        if not location:
            return None

        # 查找鬼怪NPC
        npcs = await NPCService.get_npcs_by_location(session, location.id, NPCType.GHOST)

        for npc in npcs:
            if npc.extra_data and npc.extra_data.get("task_id") == task.id:
                return npc

        return None
