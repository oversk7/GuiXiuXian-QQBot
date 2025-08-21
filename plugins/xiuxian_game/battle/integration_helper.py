"""
战斗系统集成助手

提供将新战斗属性系统集成到现有战斗逻辑中的工具函数
"""

import random
from typing import Dict, List, Tuple, Optional
from ..models.player import Player
from .battle_engine import BattleEngine


class BattleIntegrationHelper:
    """战斗系统集成助手"""

    @staticmethod
    def enhanced_player_vs_player_battle(
        player1: Player,
        player2: Player,
        seed: Optional[str] = None,
        max_rounds: int = 30
    ) -> Tuple[bool, List[str], int, int]:
        """增强版玩家vs玩家战斗（PVP切磋）

        Args:
            player1: 挑战者玩家
            player2: 被挑战者玩家
            seed: 随机种子
            max_rounds: 最大回合数

        Returns:
            (player1是否胜利, 战斗日志, player1受到的伤害, player2受到的伤害)
        """
        engine = BattleEngine(seed)
        battle_log = []

        # 初始化战斗状态
        player1_hp = player1.hp
        player2_hp = player2.hp
        initial_player1_hp = player1_hp
        initial_player2_hp = player2_hp

        battle_log.append(f"⚔️ {player1.nickname} VS {player2.nickname}")

        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player1_first = BattleAttributeCalculator.determine_turn_order(
            player1.agility, player2.agility, engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player1_hp <= 0 or player2_hp <= 0:
                break

            battle_log.append(f"━━━ 第{round_num}回合 ━━━")

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
                    first_player, second_player, first_player.attack, False
                )

                if attack_result["hit"]:
                    damage = attack_result["damage"]
                    second_hp_ref[0] = max(0, second_hp_ref[0] - damage)

                    # 构建详细攻击描述
                    action_desc = f"⚔️ {first_player.nickname} 攻击 {second_player.nickname}"

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

                    action_desc += f" 造成 {damage} 点伤害"
                    battle_log.append(action_desc)

                    # 显示血量变化
                    battle_log.append(f"   {second_player.nickname} 血量: {second_hp_ref[0]}")

                    # 检查反击
                    if second_hp_ref[0] > 0:
                        counter_result = engine.check_counter_attack(second_player, first_player)
                        if counter_result and counter_result.get("hit"):
                            counter_damage = counter_result["damage"]
                            first_hp_ref[0] = max(0, first_hp_ref[0] - counter_damage)

                            counter_desc = f"🛡️ {second_player.nickname} 反击 {first_player.nickname}"
                            if counter_result.get("is_critical"):
                                counter_desc += " (💥暴击)"
                            counter_desc += f" 造成 {counter_damage} 点伤害"
                            battle_log.append(counter_desc)
                            battle_log.append(f"   {first_player.nickname} 血量: {first_hp_ref[0]}")
                else:
                    battle_log.append(f"⚡ {first_player.nickname} 攻击 {second_player.nickname}，但被敏捷地闪避了！")

            # 第二个玩家攻击（如果还活着且第一个玩家也还活着）
            if second_hp_ref[0] > 0 and first_hp_ref[0] > 0:
                attack_result = engine.execute_player_turn(
                    second_player, first_player, second_player.attack, False
                )

                if attack_result["hit"]:
                    damage = attack_result["damage"]
                    first_hp_ref[0] = max(0, first_hp_ref[0] - damage)

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

                    action_desc += f" 造成 {damage} 点伤害"
                    battle_log.append(action_desc)

                    # 显示血量变化
                    battle_log.append(f"   {first_player.nickname} 血量: {first_hp_ref[0]}")

                    # 检查反击
                    if first_hp_ref[0] > 0:
                        counter_result = engine.check_counter_attack(first_player, second_player)
                        if counter_result and counter_result.get("hit"):
                            counter_damage = counter_result["damage"]
                            second_hp_ref[0] = max(0, second_hp_ref[0] - counter_damage)

                            counter_desc = f"🛡️ {first_player.nickname} 反击 {second_player.nickname}"
                            if counter_result.get("is_critical"):
                                counter_desc += " (💥暴击)"
                            counter_desc += f" 造成 {counter_damage} 点伤害"
                            battle_log.append(counter_desc)
                            battle_log.append(f"   {second_player.nickname} 血量: {second_hp_ref[0]}")
                else:
                    battle_log.append(f"⚡ {second_player.nickname} 攻击 {first_player.nickname}，但被敏捷地闪避了！")

            # 更新实际血量变量
            if player1_first:
                player1_hp, player2_hp = first_hp_ref[0], second_hp_ref[0]
            else:
                player2_hp, player1_hp = first_hp_ref[0], second_hp_ref[0]

        # 战斗结果
        player1_victory = player2_hp <= 0
        player1_damage_taken = initial_player1_hp - player1_hp
        player2_damage_taken = initial_player2_hp - player2_hp

        # 详细的结果显示
        battle_log.append("━━━━━━━━━━━━━")
        if player1_victory:
            battle_log.append(f"🎉 {player1.nickname} 获得胜利！")
            battle_log.append(f"📊 战斗统计：")
            battle_log.append(f"   回合数：{round_num}")
            battle_log.append(f"   {player1.nickname} 剩余血量：{player1_hp}/{initial_player1_hp}")
            battle_log.append(f"   {player2.nickname} 受到伤害：{player2_damage_taken}")
        elif player1_hp <= 0:
            battle_log.append(f"🎉 {player2.nickname} 获得胜利！")
            battle_log.append(f"📊 战斗统计：")
            battle_log.append(f"   回合数：{round_num}")
            battle_log.append(f"   {player2.nickname} 剩余血量：{player2_hp}/{initial_player2_hp}")
            battle_log.append(f"   {player1.nickname} 受到伤害：{player1_damage_taken}")
        else:
            # 平局或超时
            battle_log.append(f"⏰ 战斗超时，平局！")
            battle_log.append(f"📊 战斗统计：")
            battle_log.append(f"   回合数：{round_num}")
            battle_log.append(f"   {player1.nickname} 剩余血量：{player1_hp}/{initial_player1_hp}")
            battle_log.append(f"   {player2.nickname} 剩余血量：{player2_hp}/{initial_player2_hp}")

        return player1_victory, battle_log, player1_damage_taken, player2_damage_taken

    @staticmethod
    def enhanced_player_vs_monster_battle(
        player: Player,
        monster_stats: Dict,
        monster_name: str,
        seed: Optional[str] = None,
        max_rounds: int = 20
    ) -> Tuple[bool, List[str], int]:
        """增强版玩家vs怪物战斗

        Args:
            player: 玩家对象
            monster_stats: 怪物属性字典 {"hp": int, "attack": int, "defense": int, "agility": int}
            monster_name: 怪物名称
            seed: 随机种子
            max_rounds: 最大回合数

        Returns:
            (是否胜利, 战斗日志, 玩家受到的伤害)
        """
        engine = BattleEngine(seed)
        battle_log = []

        # 初始化战斗状态
        player_hp = player.hp
        monster_hp = monster_stats["hp"]
        initial_player_hp = player_hp

        battle_log.append(f"⚔️ {player.nickname} VS {monster_name}")
        
        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player_first = BattleAttributeCalculator.determine_turn_order(
            player.agility, monster_stats.get("agility", 10), engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player_hp <= 0 or monster_hp <= 0:
                break

            round_actions = []  # 紧凑模式的单行显示

            # 根据先后手判定执行攻击顺序
            if player_first:
                # 玩家先手
                if player_hp > 0 and monster_hp > 0:
                    player_attack_result = engine.execute_player_turn(
                        player, monster_stats, player.attack, is_skill=False
                    )

                    if player_attack_result["hit"]:
                        monster_hp = max(0, monster_hp - player_attack_result["total_damage"])
                        # 紧凑格式：显示效果和总伤害
                        effects = []
                        if player_attack_result["is_critical"]:
                            effects.append("💥")
                        if player_attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{player_attack_result['combo_count']}")
                        if player_attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)
                        round_actions.append(f"{effect_text}{player.nickname}→{player_attack_result['total_damage']}")
                    else:
                        round_actions.append(f"{player.nickname}→被闪避")

                # 怪物反击（如果存活）
                if monster_hp > 0 and player_hp > 0:
                    monster_attack_result = BattleIntegrationHelper._monster_attack_player(
                        monster_stats, player, engine
                    )

                    if monster_attack_result["hit"]:
                        player_hp = max(0, player_hp - monster_attack_result["damage"])
                        # 紧凑模式：显示伤害、特殊效果和格挡信息
                        effects = "".join(monster_attack_result.get("effects", []))
                        if monster_attack_result["blocked"] > 0:
                            round_actions.append(f"{effects}{monster_name}→{monster_attack_result['damage']}🛡️挡{monster_attack_result['blocked']}")
                        else:
                            round_actions.append(f"{effects}{monster_name}→{monster_attack_result['damage']}")
                    else:
                        round_actions.append(f"{monster_name}→被闪避")
            else:
                # 怪物先手攻击
                monster_attack_result = BattleIntegrationHelper._monster_attack_player(
                    monster_stats, player, engine
                )

                if monster_attack_result["hit"]:
                    player_hp = max(0, player_hp - monster_attack_result["damage"])
                    # 紧凑模式：显示伤害、特殊效果和格挡信息
                    effects = "".join(monster_attack_result.get("effects", []))
                    if monster_attack_result["blocked"] > 0:
                        round_actions.append(f"{effects}{monster_name}→{monster_attack_result['damage']}🛡️挡{monster_attack_result['blocked']}")
                    else:
                        round_actions.append(f"{effects}{monster_name}→{monster_attack_result['damage']}")

                    # 检查玩家反击
                    if player_hp > 0:
                        counter_result = engine.check_counter_attack(player, monster_stats)
                        if counter_result:
                            monster_hp = max(0, monster_hp - counter_result["total_damage"])
                            round_actions.append(f"🛡️反击→{counter_result['total_damage']}")

                    # 检查怪物反击（200级以后的怪物才有反击）
                    if monster_hp > 0 and player_hp > 0:
                        monster_counter_rate = monster_stats.get("counter_rate", 0)
                        if engine.rng.random() < (monster_counter_rate / 100):
                            # 怪物反击伤害为攻击力的70%
                            counter_damage = max(1, int(monster_stats["attack"] * 0.7))
                            from ..utils import damage_reduction_rate
                            damage_reduction = damage_reduction_rate(player.defense)
                            final_counter_damage = max(1, int(counter_damage * (1 - damage_reduction)))

                            player_hp = max(0, player_hp - final_counter_damage)
                            round_actions.append(f"⚡{monster_name}反击→{final_counter_damage}")
                else:
                    round_actions.append(f"{monster_name}→被闪避")

                # 玩家反击（如果存活且怪物未死）
                if player_hp > 0 and monster_hp > 0:
                    player_attack_result = engine.execute_player_turn(
                        player, monster_stats, player.attack, is_skill=False
                    )

                    if player_attack_result["hit"]:
                        monster_hp = max(0, monster_hp - player_attack_result["total_damage"])
                        # 紧凑格式：显示效果和总伤害
                        effects = []
                        if player_attack_result["is_critical"]:
                            effects.append("💥")
                        if player_attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{player_attack_result['combo_count']}")
                        if player_attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)
                        round_actions.append(f"{effect_text}{player.nickname}→{player_attack_result['total_damage']}")
                    else:
                        round_actions.append(f"{player.nickname}→被闪避")


            # 将回合动作合并为一行
            if round_actions:
                battle_log.append(f"R{round_num}: " + " | ".join(round_actions))
        
        # 战斗结果
        victory = monster_hp <= 0
        damage_taken = initial_player_hp - player_hp

        # 紧凑格式的结果显示
        remaining_player_hp = player_hp
        if victory:
            battle_log.append(f"🎉 胜利！{round_num}回合，剩余{remaining_player_hp}血")
        else:
            # 显示失败原因和剩余血量
            remaining_monster_hp = monster_hp
            battle_log.append(f"💀 战败！{round_num}回合，剩余{remaining_player_hp}血，敌剩{remaining_monster_hp}血")

        return victory, battle_log, damage_taken

    @staticmethod
    def compact_player_vs_player_battle(
        player1: Player,
        player2: Player,
        seed: Optional[str] = None,
        max_rounds: int = 30
    ) -> Tuple[bool, List[str], int, int]:
        """简洁版玩家vs玩家战斗（PVP切磋）- 使用与副本相同的简洁格式

        Args:
            player1: 挑战者玩家
            player2: 被挑战者玩家
            seed: 随机种子
            max_rounds: 最大回合数

        Returns:
            (player1是否胜利, 战斗日志, player1受到的伤害, player2受到的伤害)
        """
        engine = BattleEngine(seed)
        battle_log = []

        # 初始化战斗状态
        player1_hp = player1.hp
        player2_hp = player2.hp
        initial_player1_hp = player1_hp
        initial_player2_hp = player2_hp

        battle_log.append(f"⚔️ {player1.nickname} VS {player2.nickname}")

        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player1_first = BattleAttributeCalculator.determine_turn_order(
            player1.agility, player2.agility, engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player1_hp <= 0 or player2_hp <= 0:
                break

            round_actions = []  # 紧凑模式的单行显示

            # 根据先后手判定执行攻击顺序
            if player1_first:
                # 玩家1先手
                if player1_hp > 0 and player2_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player1, player2, player1.attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player2_hp = max(0, player2_hp - damage)
                        # 紧凑格式：显示效果和伤害
                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)

                        # 计算格挡伤害（基础攻击力 - 实际伤害）
                        blocked_damage = player1.attack - damage
                        if blocked_damage > 0:
                            round_actions.append(f"{effect_text}{player1.nickname}→{damage}🛡️挡{blocked_damage}")
                        else:
                            round_actions.append(f"{effect_text}{player1.nickname}→{damage}")
                    else:
                        round_actions.append(f"{player1.nickname}→被闪避")

                # 玩家2反击（如果存活）
                if player2_hp > 0 and player1_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player2, player1, player2.attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player1_hp = max(0, player1_hp - damage)
                        # 紧凑格式：显示效果和伤害
                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)

                        # 计算格挡伤害（基础攻击力 - 实际伤害）
                        blocked_damage = player2.attack - damage
                        if blocked_damage > 0:
                            round_actions.append(f"{effect_text}{player2.nickname}→{damage}🛡️挡{blocked_damage}")
                        else:
                            round_actions.append(f"{effect_text}{player2.nickname}→{damage}")
                    else:
                        round_actions.append(f"{player2.nickname}→被闪避")
            else:
                # 玩家2先手
                if player2_hp > 0 and player1_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player2, player1, player2.attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player1_hp = max(0, player1_hp - damage)
                        # 紧凑格式：显示效果和伤害
                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)

                        # 计算格挡伤害（基础攻击力 - 实际伤害）
                        blocked_damage = player2.attack - damage
                        if blocked_damage > 0:
                            round_actions.append(f"{effect_text}{player2.nickname}→{damage}🛡️挡{blocked_damage}")
                        else:
                            round_actions.append(f"{effect_text}{player2.nickname}→{damage}")
                    else:
                        round_actions.append(f"{player2.nickname}→被闪避")

                # 玩家1反击（如果存活）
                if player1_hp > 0 and player2_hp > 0:
                    attack_result = engine.execute_player_turn(
                        player1, player2, player1.attack, is_skill=False
                    )

                    if attack_result["hit"]:
                        damage = attack_result["damage"]
                        player2_hp = max(0, player2_hp - damage)
                        # 紧凑格式：显示效果和伤害
                        effects = []
                        if attack_result.get("is_critical"):
                            effects.append("💥")
                        if attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{attack_result['combo_count']}")
                        if attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)

                        # 计算格挡伤害（基础攻击力 - 实际伤害）
                        blocked_damage = player1.attack - damage
                        if blocked_damage > 0:
                            round_actions.append(f"{effect_text}{player1.nickname}→{damage}🛡️挡{blocked_damage}")
                        else:
                            round_actions.append(f"{effect_text}{player1.nickname}→{damage}")
                    else:
                        round_actions.append(f"{player1.nickname}→被闪避")

            # 将回合动作合并为一行
            if round_actions:
                battle_log.append(f"R{round_num}: " + " | ".join(round_actions))

        # 计算伤害
        player1_damage_taken = initial_player1_hp - player1_hp
        player2_damage_taken = initial_player2_hp - player2_hp
        player1_victory = player2_hp <= 0

        # 紧凑格式的结果显示
        if player1_victory:
            battle_log.append(f"🎉 {player1.nickname}胜利！{round_num}回合，剩余{player1_hp}血")
        elif player1_hp <= 0:
            battle_log.append(f"🎉 {player2.nickname}胜利！{round_num}回合，剩余{player2_hp}血")
        else:
            # 平局或超时
            battle_log.append(f"⏰ 战斗超时，平局！{round_num}回合，{player1.nickname}剩{player1_hp}血，{player2.nickname}剩{player2_hp}血")

        return player1_victory, battle_log, player1_damage_taken, player2_damage_taken

    @staticmethod
    def _monster_attack_player(monster_stats: Dict, player: Player, engine: BattleEngine) -> Dict:
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

        # 防御减伤计算
        from ..utils import damage_reduction_rate
        damage_reduction = damage_reduction_rate(player.defense)
        final_damage = max(1, int(current_damage * (1 - damage_reduction)))
        blocked_damage = current_damage - final_damage

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
