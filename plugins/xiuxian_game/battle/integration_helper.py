"""
战斗系统集成助手

提供将新战斗属性系统集成到现有战斗逻辑中的工具函数
"""

import random
from typing import Dict, List, Tuple, Optional, Any
from ..models.player import Player
from .enhanced_engine import EnhancedBattleEngine

try:
    from .battle_image import get_battle_image_generator, should_use_image
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False


def _get_cached_max_hp(player, default=None):
    """获取玩家的max_hp,优先使用缓存值(包含临时buff)"""
    if default is None:
        default = player.max_hp
    return getattr(player, '_cached_max_hp', default)


def create_hp_bar(current_hp: int, max_hp: int, bar_length: int = 8, show_full: bool = False) -> str:
    """创建可视化血条

    Args:
        current_hp: 当前血量
        max_hp: 最大血量
        bar_length: 血条长度（字符数，默认8）
        show_full: 是否显示完整信息（数值+百分比），False时只显示百分比

    Returns:
        格式化的血条字符串
        show_full=True: ❤️❤️❤️❤️🖤🖤🖤🖤 1234/5000 (24.7%)
        show_full=False: ❤️❤️❤️❤️🖤🖤🖤🖤 (24.7%)
    """
    if max_hp <= 0:
        if show_full:
            return "🖤" * bar_length + " 0/0 (0.0%)"
        else:
            return "🖤" * bar_length + " (0.0%)"

    # 计算血量百分比
    hp_percent = (current_hp / max_hp) * 100

    # 计算填充的心形数量
    filled_hearts = int((current_hp / max_hp) * bar_length)
    empty_hearts = bar_length - filled_hearts

    # 构建血条
    hp_bar = "❤️" * filled_hearts + "🖤" * empty_hearts

    # 根据show_full决定显示格式
    if show_full:
        hp_text = f"{hp_bar} {current_hp}/{max_hp} ({hp_percent:.1f}%)"
    else:
        hp_text = f"{hp_bar} ({hp_percent:.1f}%)"

    return hp_text


class BattleIntegrationHelper:
    """战斗系统集成助手"""

    @staticmethod
    async def enhanced_player_vs_player_battle(
        player1: Player,
        player2: Player,
        session,
        seed: Optional[str] = None,
        max_rounds: int = 30,
        is_sparring: bool = False
    ) -> Tuple[bool, List[str], int, int]:
        """增强版玩家vs玩家战斗（PVP切磋）

        Args:
            player1: 挑战者玩家
            player2: 被挑战者玩家
            session: 数据库会话
            seed: 随机种子
            max_rounds: 最大回合数
            is_sparring: 是否为切磋模式（切磋不触发镜怨体质等致死效果）

        Returns:
            (player1是否胜利, 战斗日志, player1受到的伤害, player2受到的伤害)
        """
        # 获取双方装备
        from sqlalchemy import select
        from ..models.inventory import ItemInstance

        stmt1 = select(ItemInstance).where(
            ItemInstance.player_id == player1.id,
            ItemInstance.equipped == True
        )
        player1_equipped_items = (await session.execute(stmt1)).scalars().all()

        stmt2 = select(ItemInstance).where(
            ItemInstance.player_id == player2.id,
            ItemInstance.equipped == True
        )
        player2_equipped_items = (await session.execute(stmt2)).scalars().all()

        # 创建增强战斗引擎(传递session用于查询临时buff)
        engine = EnhancedBattleEngine(seed, session)
        # 记录战斗发起者(player1为挑战者/攻击者)
        # 镜怨体质(REFLECT_DEATH)仅在防御方是被动应战方时触发
        engine.battle_initiator_id = player1.id
        # 切磋模式下不触发镜怨体质等致死效果
        engine.is_sparring = is_sparring
        battle_log = []

        # 预计算包含临时buff的属性
        # 1. 基础属性(attack, defense, hp等)
        player1_base_attrs = await player1.get_effective_attributes(session)
        player2_base_attrs = await player2.get_effective_attributes(session)

        # 2. 战斗属性(critical_rate, dodge_rate等)
        from .battle_attributes import BattleAttributeCalculator
        player1_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player1, session)
        player2_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player2, session)

        # 将包含buff的属性值临时缓存到player对象上
        # 基础属性缓存(注意:get_effective_attributes返回的是max_hp/max_mp,不是hp/mp)
        player1._cached_attack = player1_base_attrs.get('attack', player1.attack)
        player1._cached_defense = player1_base_attrs.get('defense', player1.defense)
        player1._cached_hp = player1.hp  # 当前HP,不使用buff加成
        player1._cached_max_hp = player1_base_attrs.get('max_hp', player1.max_hp)  # 最大HP,包含buff
        player1._cached_mp = player1.mp  # 当前MP,不使用buff加成
        player1._cached_max_mp = player1_base_attrs.get('max_mp', getattr(player1, 'max_mp', 0))  # 最大MP,包含buff
        player1._cached_agility = player1_base_attrs.get('agility', player1.agility)

        player2._cached_attack = player2_base_attrs.get('attack', player2.attack)
        player2._cached_defense = player2_base_attrs.get('defense', player2.defense)
        player2._cached_hp = player2.hp  # 当前HP,不使用buff加成
        player2._cached_max_hp = player2_base_attrs.get('max_hp', player2.max_hp)  # 最大HP,包含buff
        player2._cached_mp = player2.mp  # 当前MP,不使用buff加成
        player2._cached_max_mp = player2_base_attrs.get('max_mp', getattr(player2, 'max_mp', 0))  # 最大MP,包含buff
        player2._cached_agility = player2_base_attrs.get('agility', player2.agility)

        # 战斗属性缓存
        player1._cached_battle_attrs = player1_battle_attrs
        player2._cached_battle_attrs = player2_battle_attrs

        # 执行处决阈值查询辅助
        from .battle_effects import EffectType
        def _get_execute_threshold(unit_id: str) -> int:
            cfgs = engine.effect_manager.trigger_configs.get(unit_id, [])
            for cfg in cfgs:
                if getattr(cfg, 'effect', None) == EffectType.EXECUTE:
                    try:
                        return int(cfg.value)
                    except (TypeError, ValueError):
                        return 0
            return 0

        # 初始化战斗状态(使用缓存后的HP值)
        player1_hp = player1._cached_hp
        player2_hp = player2._cached_hp
        initial_player1_hp = player1_hp
        initial_player2_hp = player2_hp

        battle_log.append(f"⚔️ {player1.nickname} VS {player2.nickname}")

        # 初始化战斗 - 注册双方装备的触发器
        engine.start_battle(player1, player2, player1_equipped_items)
        # 为玩家2也注册装备触发器
        if player2_equipped_items:
            engine._register_equipment_triggers(player2.id, player2_equipped_items)
        # 同步首回合临时增益导致的即时生命值变化（如“灵影体质”）
        player1_hp = player1.hp
        player2_hp = player2.hp
        initial_player1_hp = player1_hp
        initial_player2_hp = player2_hp

        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player1_first = BattleAttributeCalculator.determine_turn_order(
            player1.agility, player2.agility, engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player1_hp <= 0 or player2_hp <= 0:
                break

            battle_log.append(f"━━━ 第{round_num}回合 ━━━")

            # 处理回合开始效果（regen等）
            # 玩家1 regen
            _, player1_hp_restored = engine._process_turn_start(player1.id, player1)
            if player1_hp_restored > 0:
                player1_hp = min(player1.max_hp, player1_hp + player1_hp_restored)
                battle_log.append(f"💚 {player1.nickname}回复{player1_hp_restored}HP")

            # 玩家2 regen
            _, player2_hp_restored = engine._process_turn_start(player2.id, player2)
            if player2_hp_restored > 0:
                player2_hp = min(player2.max_hp, player2_hp + player2_hp_restored)
                battle_log.append(f"💚 {player2.nickname}回复{player2_hp_restored}HP")

            # 确定回合顺序
            if player1_first:
                first_player, second_player = player1, player2
                first_hp_ref = [player1_hp]
                second_hp_ref = [player2_hp]
            else:
                first_player, second_player = player2, player1
                first_hp_ref = [player2_hp]
                second_hp_ref = [player1_hp]

            # 第一个玩家攻击
            if first_hp_ref[0] > 0 and second_hp_ref[0] > 0:
                attack_result = engine.execute_player_turn(
                    first_player, second_player, first_player._cached_attack, False
                )

                if attack_result["hit"]:
                    damage = attack_result["damage"]
                    second_hp_ref[0] = max(0, second_hp_ref[0] - damage)
                    # 防守方受击触发（如镜怨披风·怨息环流：被攻击后恢复10%）
                    # 只有在防守方还活着时才能回血，避免死人复活
                    heal_def = attack_result.get("defender_hp_restored", 0)
                    if heal_def > 0 and second_hp_ref[0] > 0:
                        second_hp_ref[0] = min(second_player.max_hp, second_hp_ref[0] + heal_def)
                        battle_log.append(f"💚 {second_player.nickname}回复{heal_def}HP")


                    # 构建详细攻击描述
                    action_desc = f"⚔️ {first_player.nickname} 攻击 {second_player.nickname}"

                    # 添加特效标识
                    effects = []

                    # 命中后检查处决（忽略无敌等，直接强制死亡）
                    exec_thr = _get_execute_threshold(first_player.id)
                    if exec_thr > 0 and second_hp_ref[0] > 0:
                        if second_hp_ref[0] < int(second_player.max_hp * exec_thr / 100):
                            battle_log.append(f"⚰️ {first_player.nickname}发动处决，{second_player.nickname}被弑灭！")
                            second_hp_ref[0] = 0

                    if attack_result.get("is_critical"):
                        effects.append("💥暴击")
                    if attack_result.get("is_penetration"):
                        effects.append("🗡️穿透")
                    if attack_result.get("combo_count", 1) > 1:
                        effects.append(f"🔄连击x{attack_result['combo_count']}")

                    if effects:
                        action_desc += f" ({' '.join(effects)})"

                    action_desc += f" 造成{damage}伤害"
                    battle_log.append(action_desc)
                    # 附加引擎生成的细节（含🎯20%/80%拆分）
                    if attack_result.get("messages"):
                        battle_log.extend(attack_result["messages"])

                    # 检查击杀并触发击杀效果
                    if second_hp_ref[0] <= 0:
                        kill_result = engine.trigger_on_kill(first_player, second_player)
                        if kill_result.get("messages"):
                            battle_log.extend(kill_result["messages"])
                        # 击杀回血（更新first_hp_ref）
                        if kill_result.get("hp_restored", 0) > 0:
                            if player1_first:
                                player1_hp = min(first_player.max_hp, first_hp_ref[0] + kill_result["hp_restored"])
                                first_hp_ref[0] = player1_hp
                            else:
                                player2_hp = min(first_player.max_hp, first_hp_ref[0] + kill_result["hp_restored"])
                                first_hp_ref[0] = player2_hp

                    # 检查反击
                    if second_hp_ref[0] > 0:
                        counter_result = engine.check_counter_attack(second_player, first_player)
                        if counter_result and counter_result.get("hit"):
                            counter_damage = counter_result["damage"]
                            first_hp_ref[0] = max(0, first_hp_ref[0] - counter_damage)

                            counter_desc = f"🛡️ {second_player.nickname}反击{first_player.nickname}"
                            if counter_result.get("is_critical"):
                                counter_desc += " 💥暴击"
                            counter_desc += f" 造成{counter_damage}伤害"
                            battle_log.append(counter_desc)
                else:
                    battle_log.append(f"⚡ {first_player.nickname}攻击被闪避")

            # 第二个玩家攻击（如果还活着且第一个玩家也还活着）
            if second_hp_ref[0] > 0 and first_hp_ref[0] > 0:
                attack_result = engine.execute_player_turn(
                    second_player, first_player, second_player._cached_attack, False
                )

                if attack_result["hit"]:
                    damage = attack_result["damage"]

                    # 先扣血
                    first_hp_ref[0] = max(0, first_hp_ref[0] - damage)

                    # 命中后检查处决（忽略无敌等，直接强制死亡）
                    exec_thr = _get_execute_threshold(second_player.id)
                    if exec_thr > 0 and first_hp_ref[0] > 0:
                        if first_hp_ref[0] < int(first_player.max_hp * exec_thr / 100):
                            battle_log.append(f"⚰️ {second_player.nickname}发动处决，{first_player.nickname}被弑灭！")
                            first_hp_ref[0] = 0

                    # 防守方受击触发（如镜怨披风·怨息环流：被攻击后恢复10%）
                    # 只有在防守方还活着时才能回血，避免死人复活
                    heal_def = attack_result.get("defender_hp_restored", 0)
                    if heal_def > 0 and first_hp_ref[0] > 0:
                        first_hp_ref[0] = min(first_player.max_hp, first_hp_ref[0] + heal_def)
                        battle_log.append(f"💚 {first_player.nickname}回复{heal_def}HP")

                    # 构建详细攻击描述
                    action_desc = f"⚔️ {second_player.nickname} 攻击 {first_player.nickname}"

                    # 添加特效标识
                    effects = []
                    if attack_result.get("is_critical"):
                        effects.append("💥暴击")
                    if attack_result.get("is_penetration"):
                        effects.append("🗡️穿透")
                    if attack_result.get("combo_count", 1) > 1:
                        effects.append(f"🔄连击x{attack_result['combo_count']}")

                    if effects:
                        action_desc += f" ({' '.join(effects)})"
                    # 附加引擎生成的细节（含🎯20%/80%拆分）
                    if attack_result.get("messages"):
                        battle_log.extend(attack_result["messages"])

                    action_desc += f" 造成{damage}伤害"
                    battle_log.append(action_desc)

                    # 检查击杀并触发击杀效果
                    if first_hp_ref[0] <= 0:
                        kill_result = engine.trigger_on_kill(second_player, first_player)
                        if kill_result.get("messages"):
                            battle_log.extend(kill_result["messages"])
                        # 击杀回血（更新second_hp_ref）
                        if kill_result.get("hp_restored", 0) > 0:
                            if player1_first:
                                player2_hp = min(second_player.max_hp, second_hp_ref[0] + kill_result["hp_restored"])
                                second_hp_ref[0] = player2_hp
                            else:
                                player1_hp = min(second_player.max_hp, second_hp_ref[0] + kill_result["hp_restored"])
                                second_hp_ref[0] = player1_hp

                    # 检查反击
                    if first_hp_ref[0] > 0:
                        counter_result = engine.check_counter_attack(first_player, second_player)
                        if counter_result and counter_result.get("hit"):
                            counter_damage = counter_result["damage"]
                            second_hp_ref[0] = max(0, second_hp_ref[0] - counter_damage)

                            counter_desc = f"🛡️ {first_player.nickname}反击{second_player.nickname}"
                            if counter_result.get("is_critical"):
                                counter_desc += " 💥暴击"
                            counter_desc += f" 造成{counter_damage}伤害"
                            battle_log.append(counter_desc)
                else:
                    battle_log.append(f"⚡ {second_player.nickname}攻击被闪避")

            # 更新实际血量变量
            if player1_first:
                player1_hp, player2_hp = first_hp_ref[0], second_hp_ref[0]
            else:
                player2_hp, player1_hp = first_hp_ref[0], second_hp_ref[0]

            # 回合结束后显示双方血量（只显示百分比）
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=False)
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=False)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")

        # 战斗结果
        player1_victory = player2_hp <= 0
        player1_damage_taken = initial_player1_hp - player1_hp
        player2_damage_taken = initial_player2_hp - player2_hp

        # 详细的结果显示
        battle_log.append("━━━━━━━━━━━━")
        if player1_victory:
            battle_log.append(f"🎉 {player1.nickname}获得胜利！用时{round_num}回合")
            # 只显示存活方的血条（完整信息）
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=True)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
        elif player1_hp <= 0:
            battle_log.append(f"🎉 {player2.nickname}获得胜利！用时{round_num}回合")
            # 只显示存活方的血条（完整信息）
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=True)
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")
        else:
            # 平局或超时 - 显示双方血条（完整信息）
            battle_log.append(f"⏰ 战斗超时，平局！用时{round_num}回合")
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=True)
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=True)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")
            battle_log.append(f"   {player1.nickname} 剩余血量：{player1_hp}/{initial_player1_hp}")
            battle_log.append(f"   {player2.nickname} 剩余血量：{player2_hp}/{initial_player2_hp}")


        # 战斗结束：回退双方首回合临时增益（如灵影体质）
        try:
            engine.reset_temp_bonuses(player1)
            engine.reset_temp_bonuses(player2)
        except Exception:
            pass

        return player1_victory, battle_log, player1_damage_taken, player2_damage_taken

    @staticmethod
    async def enhanced_player_vs_monster_battle_v2(
        player: Player,
        monster_stats: Dict,
        monster_name: str,
        session: Any,
        seed: Optional[str] = None,
        max_rounds: int = 20,
        monster_full_display: Optional[str] = None
    ) -> Tuple[bool, List[str], int]:
        """增强版玩家vs怪物战斗 V2 - 支持装备特殊效果

        Args:
            player: 玩家对象
            monster_stats: 怪物属性字典 {"hp": int, "attack": int, "defense": int, "agility": int}
            monster_name: 怪物名称（用于攻击动作）
            session: 数据库会话
            seed: 随机种子
            max_rounds: 最大回合数
            monster_full_display: 怪物完整显示名称（用于战斗开始，包含特殊属性）

        Returns:
            (是否胜利, 战斗日志, 玩家受到的伤害)
        """
        # 获取玩家装备
        from sqlalchemy import select
        from ..models.inventory import ItemInstance

        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

        # 创建增强战斗引擎(传递session用于查询临时buff)
        engine = EnhancedBattleEngine(seed, session)
        battle_log = []
        post_effects: list = []

        # 预计算包含临时buff的属性
        # 1. 基础属性(attack, defense, hp等)
        player_base_attrs = await player.get_effective_attributes(session)

        # 2. 战斗属性(critical_rate, dodge_rate等)
        from .battle_attributes import BattleAttributeCalculator
        player_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player, session)

        # 将包含buff的属性值临时缓存到player对象上
        # (注意:get_effective_attributes返回的是max_hp/max_mp,不是hp/mp)
        player._cached_attack = player_base_attrs.get('attack', player.attack)
        player._cached_defense = player_base_attrs.get('defense', player.defense)
        player._cached_hp = player.hp  # 当前HP,不使用buff加成
        player._cached_max_hp = player_base_attrs.get('max_hp', player.max_hp)  # 最大HP,包含buff
        player._cached_mp = player.mp  # 当前MP,不使用buff加成
        player._cached_max_mp = player_base_attrs.get('max_mp', getattr(player, 'max_mp', 0))  # 最大MP,包含buff
        player._cached_agility = player_base_attrs.get('agility', player.agility)

        # 战斗属性缓存
        player._cached_battle_attrs = player_battle_attrs

        # 处决阈值查询（从已注册的触发配置中读取）
        from .battle_effects import EffectType
        def _get_execute_threshold(unit_id: str) -> int:
            cfgs = engine.effect_manager.trigger_configs.get(unit_id, [])
            for cfg in cfgs:
                if getattr(cfg, 'effect', None) == EffectType.EXECUTE:
                    try:
                        return int(cfg.value)
                    except (TypeError, ValueError):
                        return 0
            return 0

        # 怪物ID统一使用 "enemy"
        monster_id = "enemy"

        # 初始化战斗状态(使用当前HP)
        player_hp = player.hp
        monster_hp = monster_stats["hp"]
        initial_player_hp = player_hp

        # 使用完整显示名称（如果提供）或基础名称
        display_name = monster_full_display if monster_full_display else monster_name
        battle_log.append(f"⚔️ {player.nickname} VS {display_name}")

        # 初始化战斗
        engine.start_battle(player, monster_stats, equipped_items)
        # 同步首回合临时增益导致的即时生命值变化（如“灵影体质”）
        player_hp = player.hp
        initial_player_hp = player_hp

        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player_first = BattleAttributeCalculator.determine_turn_order(
            player.agility, monster_stats.get("agility", 10), engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player_hp <= 0 or monster_hp <= 0:
                break

            battle_log.append(f"━━━ 第{round_num}回合 ━━━")

            # 玩家回合
            if player_first and player_hp > 0 and monster_hp > 0:
                turn_result = engine.execute_turn(player, monster_stats, is_player_turn=True)
                battle_log.extend(turn_result["messages"])

                # 扣除怪物血量
                monster_hp = max(0, monster_hp - turn_result["damage_dealt"])

                # 恢复玩家HP（吸血、回血等效果）
                if turn_result.get("hp_restored", 0) > 0:
                    player_hp = min(player.max_hp, player_hp + turn_result["hp_restored"])

                # 应用反弹伤害（怪物反弹给玩家）
                reflect_damage = turn_result.get("reflect_damage", 0)
                if reflect_damage > 0:
                    player_hp = max(0, player_hp - reflect_damage)
                    # 反弹消息已在turn_result中，不需要重复添加

                # 命中后检查处决（怪物战斗）：若怪物生命值低于阈值，直接斩杀
                exec_thr = _get_execute_threshold(player.id)
                if exec_thr > 0 and monster_hp > 0:
                    if monster_hp < int(monster_stats["hp"] * exec_thr / 100):
                        monster_hp = 0
                        battle_log.append(f"⚰️ {player.nickname}发动处决，{display_name}被弑灭！")


                # 检查击杀并触发击杀效果
                if monster_hp <= 0:
                    kill_result = engine.trigger_on_kill(player, monster_stats)
                    battle_log.extend(kill_result["messages"])
                    # 汇总战后效果以便统一持久化
                    if 'post_battle_effects' in kill_result:
                        post_effects.extend(kill_result['post_battle_effects'])

                    # 应用击杀回血
                    if kill_result.get("hp_restored", 0) > 0:
                        player_hp = min(player.max_hp, player_hp + kill_result["hp_restored"])

                    break

                # 检查怪物反击
                if monster_hp > 0 and player_hp > 0:
                    monster_counter_rate = monster_stats.get("counter_rate", 0)
                    if engine.rng.random() < (monster_counter_rate / 100):
                        # 怪物反击伤害为攻击力的70%
                        counter_damage = max(1, int(monster_stats["attack"] * 0.7))

                        # 检查怪物是否有真伤属性
                        monster_true_damage_rate = monster_stats.get("true_damage_rate", 0)
                        has_true_damage = monster_true_damage_rate > 0

                        # 检查玩家是否有绝魔体质
                        from ..battle.battle_effects import EffectType
                        ignore_special_effects = engine.effect_manager.get_active_effects(player.id, EffectType.IGNORE_SPECIAL)
                        ignore_special_ratio = 0.0
                        for eff in ignore_special_effects:
                            val = float(getattr(eff, 'value', 0))
                            ignore_special_ratio += max(0.0, val) / 100.0

                        from ..utils import apply_defense_mitigation

                        if has_true_damage and ignore_special_ratio > 0:
                            # 50%真伤 + 50%普通伤害
                            true_damage_part = int(counter_damage * 0.5)
                            normal_damage_part = counter_damage - true_damage_part
                            mitigation = apply_defense_mitigation(normal_damage_part, player.defense)
                            final_counter_damage = true_damage_part + mitigation["final_damage"]
                        elif has_true_damage:
                            # 完全真伤
                            final_counter_damage = counter_damage
                        else:
                            # 普通伤害
                            mitigation = apply_defense_mitigation(counter_damage, player.defense)
                            final_counter_damage = mitigation["final_damage"]

                        player_hp = max(0, player_hp - final_counter_damage)
                        battle_log.append(f"🛡️ {monster_name}反击！造成{final_counter_damage}伤害")

                        if player_hp <= 0:
                            break

            # 怪物回合
            if monster_hp > 0 and player_hp > 0:
                # 处理怪物回合开始效果（包括regen）
                monster_turn_start_msgs, monster_hp_restored = engine._process_turn_start(monster_id, monster_stats)
                if monster_turn_start_msgs:
                    battle_log.extend(monster_turn_start_msgs)
                if monster_hp_restored > 0:
                    monster_hp = min(monster_stats["hp"], monster_hp + monster_hp_restored)

                # 检查怪物是否被恐惧
                if engine.effect_manager.has_control_effect(monster_id):
                    battle_log.append(f"😱 {monster_name}被恐惧，无法行动")
                else:
                    monster_damage = monster_stats["attack"]

                    # 检查怪物是否有真伤属性（未来可能添加）
                    monster_true_damage_rate = monster_stats.get("true_damage_rate", 0)
                    has_true_damage = monster_true_damage_rate > 0

                    # 检查玩家是否有绝魔体质（免疫50%真伤）
                    from ..battle.battle_effects import EffectType
                    ignore_special_effects = engine.effect_manager.get_active_effects(player.id, EffectType.IGNORE_SPECIAL)
                    ignore_special_ratio = 0.0
                    for eff in ignore_special_effects:
                        val = float(getattr(eff, 'value', 0))
                        ignore_special_ratio += max(0.0, val) / 100.0

                    # 应用防御减伤
                    from ..utils import apply_defense_mitigation

                    if has_true_damage:
                        # 怪物有真伤属性
                        if ignore_special_ratio > 0:
                            # 玩家有绝魔体质：50%真伤 + 50%普通伤害（受防御减伤）
                            true_damage_part = int(monster_damage * 0.5)
                            normal_damage_part = monster_damage - true_damage_part
                            mitigation = apply_defense_mitigation(normal_damage_part, player.defense)
                            final_damage = true_damage_part + mitigation["final_damage"]
                            battle_log.append(f"🔥 {monster_name}的真伤被绝魔体质免疫50%！")
                        else:
                            # 完全真伤，无视防御
                            final_damage = monster_damage
                            battle_log.append(f"🔥 {monster_name}的真伤无视防御！")
                    else:
                        # 普通伤害，正常计算防御减伤
                        mitigation = apply_defense_mitigation(monster_damage, player.defense)
                        final_damage = mitigation["final_damage"]

                    # 检查玩家是否有刚气-心效果（减少受到的伤害）
                    rigid_qi_effects = engine.effect_manager.get_active_effects(player.id, EffectType.RIGID_QI_HEART)
                    if rigid_qi_effects:
                        for rigid_effect in rigid_qi_effects:
                            damage_reduction = int(final_damage * rigid_effect.value / 100)
                            final_damage -= damage_reduction
                            battle_log.append(f"💪 刚气-心！受到伤害降低{rigid_effect.value:.0f}% (-{damage_reduction})")

                    # 检查玩家是否有猛虎标弹效果（减少受到的伤害）
                    fierce_tiger_effects = engine.effect_manager.get_active_effects(player.id, EffectType.FIERCE_TIGER_BULLET)
                    if fierce_tiger_effects:
                        for fierce_effect in fierce_tiger_effects:
                            # 猛虎标弹：受到伤害降低30%
                            damage_reduction = int(final_damage * 30 / 100)
                            final_damage -= damage_reduction
                            battle_log.append(f"🐅 猛虎标弹！受到伤害降低30% (-{damage_reduction})")

                    # 先扣血
                    player_hp = max(0, player_hp - final_damage)
                    battle_log.append(f"👹 {monster_name}攻击{player.nickname}，造成{final_damage}伤害")

                    # 被攻击方（玩家）受击触发：如镜怨披风·怨息环流（恢复10%）
                    # 只有在玩家还活着时才能回血，避免死人复活
                    if player_hp > 0:
                        try:
                            from ..battle.battle_effects import TriggerType, EffectType
                            # 环境上下文（与引擎一致的最小集合）
                            region = player.get_current_region() if hasattr(player, 'get_current_region') else getattr(player, 'region', "")
                            try:
                                from ..utils import get_weekly_theme
                                theme_name = get_weekly_theme()["name"]
                            except Exception:
                                theme_name = ""
                            defense_context = {
                                "source": monster_name,
                                "attacker": monster_name,
                                "current_hp": player_hp,
                                "max_hp": player.max_hp,
                                "region": region,
                                "theme": theme_name,
                            }
                            defense_effects = engine.effect_manager.check_triggers(player.id, TriggerType.ON_DEFENSE, defense_context)
                            attacked_effects = engine.effect_manager.check_triggers(player.id, TriggerType.ON_ATTACKED, defense_context)
                            defense_effects.extend(attacked_effects)
                            for eff in defense_effects:
                                if eff.effect_type == EffectType.HEAL:
                                    heal_amount = int(player.max_hp * eff.value / 100) if eff.is_percentage else int(eff.value)
                                    player_hp = min(player.max_hp, player_hp + heal_amount)
                                    battle_log.append(f"💚 {player.nickname}回复{heal_amount}HP")
                        except Exception:
                            # 防御触发失败不影响主流程
                            pass

                    if player_hp <= 0:
                        break

                    # 检查玩家反击（只有怪物攻击成功后才能反击）
                    if player_hp > 0 and monster_hp > 0:
                        from .battle_attributes import BattleEffectProcessor
                        if BattleEffectProcessor.check_counter_attack(player, engine.rng):
                            # 玩家反击（使用增强引擎执行反击攻击）
                            counter_result = engine._execute_enhanced_attack(
                                player, monster_stats, True, is_counter=True
                            )

                            battle_log.append(f"🛡️ {player.nickname}反击！")
                            battle_log.extend(counter_result["messages"])

                            # 扣除怪物血量
                            monster_hp = max(0, monster_hp - counter_result.get("total_damage", 0))

                            # 恢复玩家HP（反击也可以吸血）
                            if counter_result.get("hp_restored", 0) > 0:
                                player_hp = min(player.max_hp, player_hp + counter_result["hp_restored"])

                            # 应用反弹伤害（怪物反弹给玩家）
                            reflect_damage = counter_result.get("reflect_damage", 0)
                            if reflect_damage > 0:
                                player_hp = max(0, player_hp - reflect_damage)


                                # 反击后检查处决（怪物战斗）
                                exec_thr = _get_execute_threshold(player.id)
                                if exec_thr > 0 and monster_hp > 0:
                                    if monster_hp < int(monster_stats["hp"] * exec_thr / 100):
                                        monster_hp = 0
                                        battle_log.append(f"⚰️ {player.nickname}发动处决，{display_name}被弑灭！")

                            # 检查反击击杀并触发击杀效果
                            if monster_hp <= 0:
                                kill_result = engine.trigger_on_kill(player, monster_stats)
                                battle_log.extend(kill_result["messages"])

                                # 汇总战后效果以便统一持久化
                                if 'post_battle_effects' in kill_result:
                                    post_effects.extend(kill_result['post_battle_effects'])


                                # 应用击杀回血
                                if kill_result.get("hp_restored", 0) > 0:
                                    player_hp = min(player.max_hp, player_hp + kill_result["hp_restored"])

                                break

            # 怪物先手的情况
            if not player_first and player_hp > 0 and monster_hp > 0:
                turn_result = engine.execute_turn(player, monster_stats, is_player_turn=True)
                battle_log.extend(turn_result["messages"])

                # 扣除怪物血量
                monster_hp = max(0, monster_hp - turn_result["damage_dealt"])

                # 恢复玩家HP（吸血、回血等效果）
                if turn_result.get("hp_restored", 0) > 0:
                    player_hp = min(player.max_hp, player_hp + turn_result["hp_restored"])

                # 应用反弹伤害（怪物反弹给玩家）
                reflect_damage = turn_result.get("reflect_damage", 0)
                if reflect_damage > 0:
                    player_hp = max(0, player_hp - reflect_damage)


                # 命中后检查处决（怪物战斗）：若怪物生命值低于阈值，直接斩杀
                exec_thr = _get_execute_threshold(player.id)
                if exec_thr > 0 and monster_hp > 0:
                    if monster_hp < int(monster_stats["hp"] * exec_thr / 100):
                        monster_hp = 0
                        battle_log.append(f"⚰️ {player.nickname}发动处决，{display_name}被弑灭！")

                # 检查击杀并触发击杀效果
                if monster_hp <= 0:
                    kill_result = engine.trigger_on_kill(player, monster_stats)
                    battle_log.extend(kill_result["messages"])
                    # 汇总战后效果以便统一持久化
                    if 'post_battle_effects' in kill_result:
                        post_effects.extend(kill_result['post_battle_effects'])

                    # 应用击杀回血
                    if kill_result.get("hp_restored", 0) > 0:
                        player_hp = min(player.max_hp, player_hp + kill_result["hp_restored"])

                    break

                # 检查怪物反击
                if monster_hp > 0 and player_hp > 0:
                    monster_counter_rate = monster_stats.get("counter_rate", 0)
                    if engine.rng.random() < (monster_counter_rate / 100):
                        # 怪物反击伤害为攻击力的70%
                        counter_damage = max(1, int(monster_stats["attack"] * 0.7))

                        # 检查怪物是否有真伤属性
                        monster_true_damage_rate = monster_stats.get("true_damage_rate", 0)
                        has_true_damage = monster_true_damage_rate > 0

                        # 检查玩家是否有绝魔体质
                        from ..battle.battle_effects import EffectType
                        ignore_special_effects = engine.effect_manager.get_active_effects(player.id, EffectType.IGNORE_SPECIAL)
                        ignore_special_ratio = 0.0
                        for eff in ignore_special_effects:
                            val = float(getattr(eff, 'value', 0))
                            ignore_special_ratio += max(0.0, val) / 100.0

                        from ..utils import apply_defense_mitigation

                        if has_true_damage and ignore_special_ratio > 0:
                            # 50%真伤 + 50%普通伤害
                            true_damage_part = int(counter_damage * 0.5)
                            normal_damage_part = counter_damage - true_damage_part
                            mitigation = apply_defense_mitigation(normal_damage_part, player.defense)
                            final_counter_damage = true_damage_part + mitigation["final_damage"]
                        elif has_true_damage:
                            # 完全真伤
                            final_counter_damage = counter_damage
                        else:
                            # 普通伤害
                            mitigation = apply_defense_mitigation(counter_damage, player.defense)
                            final_counter_damage = mitigation["final_damage"]

                        player_hp = max(0, player_hp - final_counter_damage)
                        battle_log.append(f"🛡️ {monster_name}反击！造成{final_counter_damage}伤害")

                        if player_hp <= 0:
                            break

            # 回合结束后显示双方血量（只显示百分比）
            if player_hp > 0 and monster_hp > 0:
                player_hp_bar = create_hp_bar(player_hp, player.max_hp, show_full=False)
                monster_hp_bar = create_hp_bar(monster_hp, monster_stats["hp"], show_full=False)
                battle_log.append(f"  {player.nickname}:")
                battle_log.append(f"    {player_hp_bar}")
                battle_log.append(f"  {monster_name}:")
                battle_log.append(f"    {monster_hp_bar}")

        # 战斗结果
        victory = monster_hp <= 0
        damage_taken = initial_player_hp - player_hp

        battle_log.append("━━━━━━━━━━━━")
        if victory:
            battle_log.append(f"🎉 {player.nickname}获胜！用时{round_num}回合")
            # 只显示存活方的血条（完整信息）
            player_hp_bar = create_hp_bar(player_hp, player.max_hp, show_full=True)
            battle_log.append(f"  {player.nickname}:")
            battle_log.append(f"    {player_hp_bar}")
        else:
            battle_log.append(f"💀 {player.nickname}战败！用时{round_num}回合")
            # 只显示存活方的血条（完整信息）
            monster_hp_bar = create_hp_bar(monster_hp, monster_stats["hp"], show_full=True)
            battle_log.append(f"  {monster_name}:")
            battle_log.append(f"    {monster_hp_bar}")


        # 战斗结束：回退首回合临时增益（如灵影体质）
        try:
            engine.reset_temp_bonuses(player)
        except Exception:
            pass

        return victory, battle_log, damage_taken, post_effects

    @staticmethod
    async def compact_player_vs_player_battle(
        player1: Player,
        player2: Player,
        session,
        seed: Optional[str] = None,
        max_rounds: int = 30
    ) -> Tuple[bool, List[str], int, int]:
        """简洁版玩家vs玩家战斗（PVP切磋）- 使用与副本相同的简洁格式

        Args:
            player1: 挑战者玩家
            player2: 被挑战者玩家
            session: 数据库会话
            seed: 随机种子
            max_rounds: 最大回合数

        Returns:
            (player1是否胜利, 战斗日志, player1受到的伤害, player2受到的伤害)
        """
        # 获取双方装备
        from sqlalchemy import select
        from ..models.inventory import ItemInstance

        stmt1 = select(ItemInstance).where(
            ItemInstance.player_id == player1.id,
            ItemInstance.equipped == True
        )
        player1_equipped_items = (await session.execute(stmt1)).scalars().all()

        stmt2 = select(ItemInstance).where(
            ItemInstance.player_id == player2.id,
            ItemInstance.equipped == True
        )
        player2_equipped_items = (await session.execute(stmt2)).scalars().all()

        # 创建增强战斗引擎(传递session用于查询临时buff)
        engine = EnhancedBattleEngine(seed, session)
        # 记录战斗发起者(player1为挑战者/攻击者)
        # 镜怨体质(REFLECT_DEATH)仅在防御方是被动应战方时触发
        engine.battle_initiator_id = player1.id
        # 切磋模式：不触发镜怨体质等致死效果
        engine.is_sparring = True
        battle_log = []

        # 预计算包含临时buff的属性
        # 1. 基础属性(attack, defense, hp等)
        player1_base_attrs = await player1.get_effective_attributes(session)
        player2_base_attrs = await player2.get_effective_attributes(session)

        # 2. 战斗属性(critical_rate, dodge_rate等)
        from .battle_attributes import BattleAttributeCalculator
        player1_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player1, session)
        player2_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player2, session)

        # 将包含buff的属性值临时缓存到player对象上
        # 基础属性缓存(注意:get_effective_attributes返回的是max_hp/max_mp,不是hp/mp)
        player1._cached_attack = player1_base_attrs.get('attack', player1.attack)
        player1._cached_defense = player1_base_attrs.get('defense', player1.defense)
        player1._cached_hp = player1.hp  # 当前HP,不使用buff加成
        player1._cached_max_hp = player1_base_attrs.get('max_hp', player1.max_hp)  # 最大HP,包含buff
        player1._cached_mp = player1.mp  # 当前MP,不使用buff加成
        player1._cached_max_mp = player1_base_attrs.get('max_mp', getattr(player1, 'max_mp', 0))  # 最大MP,包含buff
        player1._cached_agility = player1_base_attrs.get('agility', player1.agility)

        player2._cached_attack = player2_base_attrs.get('attack', player2.attack)
        player2._cached_defense = player2_base_attrs.get('defense', player2.defense)
        player2._cached_hp = player2.hp  # 当前HP,不使用buff加成
        player2._cached_max_hp = player2_base_attrs.get('max_hp', player2.max_hp)  # 最大HP,包含buff
        player2._cached_mp = player2.mp  # 当前MP,不使用buff加成
        player2._cached_max_mp = player2_base_attrs.get('max_mp', getattr(player2, 'max_mp', 0))  # 最大MP,包含buff
        player2._cached_agility = player2_base_attrs.get('agility', player2.agility)

        # 战斗属性缓存
        player1._cached_battle_attrs = player1_battle_attrs
        player2._cached_battle_attrs = player2_battle_attrs

        # 初始化战斗状态(使用当前HP,但后续恢复时使用max_hp)
        player1_hp = player1._cached_hp
        player2_hp = player2._cached_hp
        initial_player1_hp = player1_hp
        initial_player2_hp = player2_hp

        battle_log.append(f"⚔️ {player1.nickname} VS {player2.nickname}")

        # 初始化战斗 - 注册双方装备的触发器
        engine.start_battle(player1, player2, player1_equipped_items)
        # 为玩家2也注册装备触发器
        if player2_equipped_items:
            engine._register_equipment_triggers(player2.id, player2_equipped_items)
        # 同步首回合临时增益导致的即时生命值变化（如“灵影体质”）
        player1_hp = player1.hp
        player2_hp = player2.hp
        initial_player1_hp = player1_hp
        initial_player2_hp = player2_hp

        # eff8 ef8ececfede  afed0bf
        from .battle_effects import EffectType as _Eff
        def _get_exec_thr(_uid: str) -> int:
            cfgs = engine.effect_manager.trigger_configs.get(_uid, [])
            for cfg in cfgs:
                if getattr(cfg, 'effect', None) == _Eff.EXECUTE:
                    try:
                        return int(cfg.value)
                    except (TypeError, ValueError):
                        return 0
            return 0


        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player1_first = BattleAttributeCalculator.determine_turn_order(
            player1.agility, player2.agility, engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player1_hp <= 0 or player2_hp <= 0:
                break

            battle_log.append(f"━━━ 第{round_num}回合 ━━━")

            # 处理回合开始效果（regen等）
            # 玩家1 regen
            _, player1_hp_restored = engine._process_turn_start(player1.id, player1)
            if player1_hp_restored > 0:
                player1_hp = min(player1.max_hp, player1_hp + player1_hp_restored)
                battle_log.append(f"💚 {player1.nickname}回复{player1_hp_restored}HP")

            # 玩家2 regen
            _, player2_hp_restored = engine._process_turn_start(player2.id, player2)
            if player2_hp_restored > 0:
                player2_hp = min(player2.max_hp, player2_hp + player2_hp_restored)
                battle_log.append(f"💚 {player2.nickname}回复{player2_hp_restored}HP")

            # 根据先后手判定执行攻击顺序
            if player1_first:
                # 玩家1先手
                if player1_hp > 0 and player2_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player1, player2, player1._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player2_hp = max(0, player2_hp - damage)
                        # 斩杀判定
                        exec_thr = _get_exec_thr(player1.id)
                        if exec_thr > 0 and player2_hp > 0:
                            if player2_hp < int(player2.max_hp * exec_thr / 100):
                                player2_hp = 0
                                battle_log.append(f"⚰️ {player1.nickname}发动处决，{player2.nickname}被弑灭！")
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player2_hp > 0:
                            player2_hp = min(player2.max_hp, player2_hp + heal_def)
                            battle_log.append(f"💚 {player2.nickname}回复{heal_def}HP")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost1 = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player1._cached_attack - _pre_boost1
                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player1.nickname} 攻击 {player2.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player2.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player2_hp <= 0:
                            kill_result = engine.trigger_on_kill(player1, player2)
                            if kill_result.get("hp_restored", 0) > 0:
                                player1_hp = min(player1.max_hp, player1_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player1.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player1.nickname}攻击被闪避")

                # 玩家2反击（如果存活）
                if player2_hp > 0 and player1_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player2, player1, player2._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player1_hp = max(0, player1_hp - damage)
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player1_hp > 0:
                            player1_hp = min(player1.max_hp, player1_hp + heal_def)
                            battle_log.append(f"💚 {player1.nickname}回复{heal_def}HP")

                        # 处决判定（玩家2对玩家1）
                        _thr = _get_exec_thr(player2.id)
                        if _thr > 0 and player1_hp > 0:
                            if player1_hp < int(player1.max_hp * _thr / 100):
                                player1_hp = 0
                                battle_log.append(f"⚰️ {player2.nickname}发动处决，{player1.nickname}被弑灭！")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost2 = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player2._cached_attack - _pre_boost2
                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player2.nickname} 攻击 {player1.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player1.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player1_hp <= 0:
                            kill_result = engine.trigger_on_kill(player2, player1)
                            if kill_result.get("hp_restored", 0) > 0:
                                player2_hp = min(player2.max_hp, player2_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player2.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player2.nickname}攻击被闪避")
            else:
                # 玩家2先手
                if player2_hp > 0 and player1_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player2, player1, player2._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player1_hp = max(0, player1_hp - damage)
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player1_hp > 0:
                            player1_hp = min(player1.max_hp, player1_hp + heal_def)
                            battle_log.append(f"💚 {player1.nickname}回复{heal_def}HP")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost2b = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player2._cached_attack - _pre_boost2b

                        # 处决判定（玩家2对玩家1）
                        _thr = _get_exec_thr(player2.id)
                        if _thr > 0 and player1_hp > 0:
                            if player1_hp < int(player1.max_hp * _thr / 100):
                                player1_hp = 0
                                battle_log.append(f"⚰️ {player2.nickname}发动处决，{player1.nickname}被弑灭！")

                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player2.nickname} 攻击 {player1.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player1.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player1_hp <= 0:
                            kill_result = engine.trigger_on_kill(player2, player1)
                            if kill_result.get("hp_restored", 0) > 0:
                                player2_hp = min(player2.max_hp, player2_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player2.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player2.nickname}攻击被闪避")

                # 玩家1反击（如果存活）
                if player1_hp > 0 and player2_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player1, player2, player1._cached_attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player2_hp = max(0, player2_hp - damage)

                        # 处决判定（玩家1对玩家2）
                        _thr2 = _get_exec_thr(player1.id)
                        if _thr2 > 0 and player2_hp > 0:
                            if player2_hp < int(player2.max_hp * _thr2 / 100):
                                player2_hp = 0
                                battle_log.append(f"⚰️ {player1.nickname}发动处决，{player2.nickname}被弑灭！")
                        # 防守方受击触发
                        heal_def = attack_result.get("defender_hp_restored", 0)
                        if heal_def > 0 and player2_hp > 0:
                            player2_hp = min(player2.max_hp, player2_hp + heal_def)
                            battle_log.append(f"💚 {player2.nickname}回复{heal_def}HP")

                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥暴击")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄连击x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️穿透")
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            effects.append("🎯斩龙")
                        effect_str = f" ({' '.join(effects)})" if effects else ""

                        _pre_boost1b = attack_result.get("pre_boost_damage", damage)
                        blocked_damage = player1._cached_attack - _pre_boost1b

                        _gd = attack_result.get("guaranteed_damage", 0)
                        _nd = attack_result.get("normal_damage", 0)
                        _split = ""
                        if any(isinstance(t, str) and "GUARANTEED_20%" in t for t in attack_result.get("effects", [])):
                            _nd_text = "被闪避" if attack_result.get("normal_missed") else str(_nd)
                            _split = f" [20%:{_gd}+80%:{_nd_text}]"
                        battle_log.append(f"⚔️ {player1.nickname} 攻击 {player2.nickname}{effect_str}，造成{damage}伤害{_split}")
                        if blocked_damage > 0:
                            battle_log.append(f"  🛡️ {player2.nickname}防御吸收{blocked_damage}")

                        # 检查击杀并触发击杀效果
                        if player2_hp <= 0:
                            kill_result = engine.trigger_on_kill(player1, player2)
                            if kill_result.get("hp_restored", 0) > 0:
                                player1_hp = min(player1.max_hp, player1_hp + kill_result["hp_restored"])
                                battle_log.append(f"💚 {player1.nickname}击杀回血+{kill_result['hp_restored']}HP")
                    else:
                        battle_log.append(f"⚡ {player1.nickname}攻击被闪避")

            # 每回合结束后显示双方血量（只显示百分比）
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=False)
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=False)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")


        # 计算伤害
        player1_damage_taken = initial_player1_hp - player1_hp
        player2_damage_taken = initial_player2_hp - player2_hp
        player1_victory = player2_hp <= 0

        # 紧凑格式的结果显示
        battle_log.append("━━━━━━━━━━━━")
        if player1_victory:
            battle_log.append(f"🎉 {player1.nickname}胜利！用时{round_num}回合")
            # 只显示存活方的血条（完整信息）
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=True)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
        elif player1_hp <= 0:
            battle_log.append(f"🎉 {player2.nickname}胜利！用时{round_num}回合")
            # 只显示存活方的血条（完整信息）
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=True)
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")
        else:
            # 平局或超时 - 显示双方血条（完整信息）
            battle_log.append(f"⏰ 战斗超时，平局！用时{round_num}回合")
            player1_hp_bar = create_hp_bar(player1_hp, player1.max_hp, show_full=True)
            player2_hp_bar = create_hp_bar(player2_hp, player2.max_hp, show_full=True)
            battle_log.append(f"  {player1.nickname}:")
            battle_log.append(f"    {player1_hp_bar}")
            battle_log.append(f"  {player2.nickname}:")
            battle_log.append(f"    {player2_hp_bar}")

        return player1_victory, battle_log, player1_damage_taken, player2_damage_taken

    @staticmethod
    def _monster_attack_player(monster_stats: Dict, player: Player, engine: EnhancedBattleEngine) -> Dict:
        """怪物攻击玩家的增强逻辑（支持200级以后怪物的特殊属性）

        Args:
            monster_stats: 怪物属性（包含特殊属性）
            player: 玩家对象
            engine: 战斗引擎

        Returns:
            攻击结果字典
        """
        # 使用固定的怪物基础伤害，不再有随机波动
        base_damage = monster_stats["attack"]

        # 获取玩家战斗属性
        from .battle_attributes import BattleAttributeCalculator
        player_attrs = BattleAttributeCalculator.calculate_effective_attributes(player)

        result = {
            "hit": False,
            "damage": 0,
            "blocked": 0,
            "is_critical": False,
            "is_combo": False,
            "combo_count": 1,
            "effects": []
        }

        # 命中判定（怪物命中率固定80%，玩家闪避率来自装备）
        monster_accuracy = 80.0
        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            monster_accuracy, player_attrs["dodge_rate"]
        )

        if engine.rng.random() > hit_chance:
            return result

        result["hit"] = True

        # 怪物暴击判定（200级以后的怪物才有）
        monster_crit_rate = monster_stats.get("crit_rate", 0)
        player_anti_crit_rate = player_attrs.get("anti_crit_rate", 0)  # 玩家抗暴率（如果有的话）

        # 计算实际暴击率（怪物暴击率 - 玩家抗暴率，但玩家目前没有抗暴率）
        effective_crit_rate = max(0, monster_crit_rate - player_anti_crit_rate)
        is_critical = engine.rng.random() < (effective_crit_rate / 100)
        result["is_critical"] = is_critical

        # 怪物连击判定（200级以后的怪物才有）
        monster_combo_rate = monster_stats.get("combo_rate", 0)
        combo_count = 1
        if engine.rng.random() < (monster_combo_rate / 100):
            combo_count = 2  # 怪物连击固定为2次
            result["is_combo"] = True
        result["combo_count"] = combo_count

        # 计算基础伤害
        current_damage = base_damage

        # 暴击伤害加成
        if is_critical:
            current_damage = int(current_damage * 1.5)  # 怪物暴击1.5倍伤害
            result["effects"].append("💥暴击")

        # 检查怪物是否有真伤属性（未来可能添加）
        monster_true_damage_rate = monster_stats.get("true_damage_rate", 0)
        has_true_damage = monster_true_damage_rate > 0

        # 检查玩家是否有绝魔体质（免疫50%真伤）
        from ..battle.battle_effects import EffectType
        ignore_special_effects = engine.effect_manager.get_active_effects(player.id, EffectType.IGNORE_SPECIAL)
        ignore_special_ratio = 0.0
        for eff in ignore_special_effects:
            val = float(getattr(eff, 'value', 0))
            ignore_special_ratio += max(0.0, val) / 100.0

        # 防御减伤计算（数值减伤 + 比例减伤）
        from ..utils import apply_defense_mitigation

        if has_true_damage:
            # 怪物有真伤属性
            if ignore_special_ratio > 0:
                # 玩家有绝魔体质：50%真伤 + 50%普通伤害（受防御减伤）
                true_damage_part = int(current_damage * 0.5)
                normal_damage_part = current_damage - true_damage_part
                mitigation = apply_defense_mitigation(normal_damage_part, player.defense)
                final_damage = true_damage_part + mitigation["final_damage"]
                blocked_damage = mitigation["blocked"]
                result["effects"].append("🔥真伤(绝魔免疫50%)")
            else:
                # 完全真伤，无视防御
                final_damage = current_damage
                blocked_damage = 0
                result["effects"].append("🔥真伤")
        else:
            # 普通伤害，正常计算防御减伤
            mitigation = apply_defense_mitigation(current_damage, player.defense)
            final_damage = mitigation["final_damage"]
            blocked_damage = mitigation["blocked"]

        # 连击处理
        total_damage = final_damage
        if combo_count > 1:
            # 第二次连击伤害为85%
            combo_damage = max(1, int(final_damage * 0.85))
            total_damage += combo_damage
            result["effects"].append(f"🔄连击x{combo_count}")

        result["damage"] = total_damage
        result["blocked"] = blocked_damage
        return result

    @staticmethod
    def create_battle_summary(player: Player, victory: bool, battle_log: List[str],
                            damage_taken: int, exp_gain: int = 0) -> str:
        """创建战斗总结

        Args:
            player: 玩家对象
            victory: 是否胜利
            battle_log: 战斗日志
            damage_taken: 受到的伤害
            exp_gain: 获得的经验

        Returns:
            格式化的战斗总结
        """
        summary_lines = []

        # 战斗结果
        if victory:
            summary_lines.append("🎉 战斗胜利！")
        else:
            summary_lines.append("💀 战斗失败...")

        # 关键战斗日志（最多显示8条）
        key_logs = [log for log in battle_log if any(keyword in log for keyword in
                   ["暴击", "连击", "反击", "穿透", "闪避", "胜利", "战败", "回合"])]

        if len(key_logs) > 8:
            summary_lines.extend(key_logs[:3])
            summary_lines.append("...")
            summary_lines.extend(key_logs[-3:])
        else:
            summary_lines.extend(key_logs)

        # 战斗统计
        summary_lines.append("")
        summary_lines.append("📊 战斗统计:")
        summary_lines.append(f"剩余血量: {player.hp}/{player.max_hp}")
        summary_lines.append(f"受到伤害: {damage_taken}")

        if exp_gain > 0:
            summary_lines.append(f"获得经验: {exp_gain}")

        return "\n".join(summary_lines)

    @staticmethod
    def get_battle_attribute_display(player: Player) -> str:
        """获取战斗属性显示

        Args:
            player: 玩家对象

        Returns:
            格式化的战斗属性显示
        """
        from .battle_attributes import BattleAttributeCalculator
        attrs = BattleAttributeCalculator.calculate_effective_attributes(player)

        # 计算暴击倍数显示（基础1.5倍 + 暴击力*0.1倍）
        crit_multiplier = 1.5 + (attrs['critical_power'] * 0.1)

        lines = [
            "⚔️ 战斗属性 ⚔️",
            f"💥 暴击率: {attrs['critical_rate']:.1f}%",
            f"💢 暴击力: {crit_multiplier:.1f}倍",
            f"🔄 连击率: {attrs['combo_rate']:.1f}%",
            f"🛡️ 反击率: {attrs['counter_rate']:.1f}%",
            f"⚡ 闪避率: {attrs['dodge_rate']:.1f}%",
            f"🎯 命中率: {attrs['accuracy_rate']:.1f}%",
            f"✨ 灵爆率: {attrs['skill_crit_rate']:.1f}%",
            f"🗡️ 穿透率: {attrs['penetration_rate']:.1f}%",
            f"🛡️ 抗暴率: {attrs['anti_crit_rate']:.1f}%"
        ]

        return "\n".join(lines)

    @staticmethod
    async def get_battle_attribute_display_async(player: "Player", session=None) -> str:
        """获取战斗属性显示（异步版本，包含临时buff）

        Args:
            player: 玩家对象
            session: 数据库会话（用于获取临时buff）

        Returns:
            格式化的战斗属性显示
        """
        from .battle_attributes import BattleAttributeCalculator
        attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(player, session)

        # 计算暴击倍数显示（基础1.5倍 + 暴击力*0.1倍）
        crit_multiplier = 1.5 + (attrs['critical_power'] * 0.1)

        lines = [
            "⚔️ 战斗属性 ⚔️",
            f"💥 暴击率: {attrs['critical_rate']:.1f}%",
            f"💢 暴击力: {crit_multiplier:.1f}倍",
            f"🔄 连击率: {attrs['combo_rate']:.1f}%",
            f"🛡️ 反击率: {attrs['counter_rate']:.1f}%",
            f"⚡ 闪避率: {attrs['dodge_rate']:.1f}%",
            f"🎯 命中率: {attrs['accuracy_rate']:.1f}%",
            f"✨ 灵爆率: {attrs['skill_crit_rate']:.1f}%",
            f"🗡️ 穿透率: {attrs['penetration_rate']:.1f}%",
            f"🛡️ 抗暴率: {attrs['anti_crit_rate']:.1f}%"
        ]

        return "\n".join(lines)
