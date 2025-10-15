"""
增强战斗引擎 - 集成状态效果和触发系统
完整的战斗引擎，支持装备特殊效果、状态效果、触发系统等
"""

import random
from typing import Dict, List, Optional, Any, Tuple
from ..models.player import Player
from .battle_attributes import BattleAttributeCalculator
from .battle_effects import (
    BattleEffectManager, TriggerType, EffectType, BattleEffect,
    TriggerConfig, parse_triggers_from_yaml, format_effect_message
)


class EnhancedBattleEngine:
    """增强战斗引擎 - 支持状态效果和触发系统"""

    def __init__(self, seed: Optional[str] = None):
        """初始化增强战斗引擎

        Args:
            seed: 随机种子，用于确定性战斗
        """
        if seed:
            import hashlib
            self.rng = random.Random(hashlib.md5(seed.encode()).hexdigest())
        else:
            self.rng = random.Random()

        self.effect_manager = BattleEffectManager()
        self.turn_counter = 0
        self.battle_log: List[str] = []
        # 记录首回合临时加成（需战后回退）
        self._temp_hp_from_mp: Dict[str, int] = {}


    def start_battle(self, player: Player, enemy: Any, player_equipped_items: List = None):
        """战斗开始，初始化效果和触发器

        Args:
            player: 玩家对象
            enemy: 敌人(Player或怪物字典)
            player_equipped_items: 玩家装备的物品列表
        """
        self.turn_counter = 0
        self.battle_log = []

        # 清除旧效果
        self.effect_manager.clear_effects(player.id)
        enemy_id = enemy.id if hasattr(enemy, 'id') else "enemy"
        self.effect_manager.clear_effects(enemy_id)

        # 注册玩家装备的触发器
        if player_equipped_items:
            self._register_equipment_triggers(player.id, player_equipped_items)

        # 先应用被动效果（始终生效类），确保后续判定可读取
        try:
            from ..utils import get_weekly_theme
            theme_name = get_weekly_theme()["name"]
        except Exception:
            theme_name = ""
        region = player.get_current_region() if hasattr(player, 'get_current_region') else getattr(player, 'region', "")
        passive_effects = self.effect_manager.check_triggers(player.id, TriggerType.PASSIVE, {
            "source": "战斗开始",
            "current_hp": player.hp,
            "max_hp": player.max_hp,
            "current_mp": getattr(player, 'mp', 0),
            "max_mp": getattr(player, 'max_mp', 0),
            "region": region,
            "theme": theme_name,
        })
        for eff in passive_effects:
            self.effect_manager.add_effect(player.id, eff)

        # 触发玩家首回合效果（补充环境上下文）
        triggered = self.effect_manager.check_triggers(player.id, TriggerType.FIRST_TURN, {
            "source": "战斗开始",
            "current_hp": player.hp,
            "max_hp": player.max_hp,
            "current_mp": getattr(player, 'mp', 0),
            "max_mp": getattr(player, 'max_mp', 0),
            "region": region,
            "theme": theme_name,
        })

        for effect in triggered:
            self.effect_manager.add_effect(player.id, effect)

        # 首回合：将灵影护盾转换为实际护盾值（按最大理智）
        try:
            player_max_mp = getattr(player, 'max_mp', 0)
            mp_shields = self.effect_manager.get_active_effects(player.id, EffectType.SHIELD_FROM_MP)
            for eff in mp_shields:
                eff.shield_value = int(player_max_mp)
                eff.effect_type = EffectType.SHIELD
        except AttributeError:
            pass

        # 首回合：灵影体质·lv.EX - 按最大理智增加最大生命值，同时按同百分比提升当前生命值
        try:
            player_max_mp = getattr(player, 'max_mp', 0)
            hp_from_mp_effects = self.effect_manager.get_active_effects(player.id, EffectType.HP_FROM_MP)
            # 汇总百分比，避免多特效循环导致不一致
            total_pct = 0
            for eff in hp_from_mp_effects:
                if eff.is_percentage:
                    total_pct += eff.value
            if total_pct > 0:
                base_hp = player.hp
                hp_bonus_total = int(player_max_mp * total_pct / 100)
                player.max_hp += hp_bonus_total
                # 当前生命值按百分比提升（基于提升前的当前HP）
                hp_inc_cur = int(base_hp * total_pct / 100)
                player.hp = min(player.max_hp, base_hp + hp_inc_cur)
                # 记录临时加成，战斗结束回退
                self._temp_hp_from_mp[player.id] = self._temp_hp_from_mp.get(player.id, 0) + hp_bonus_total
                self.battle_log.append(f"✨ 灵影体质·lv.EX：最大生命值+{hp_bonus_total}（理智值的{total_pct:.0f}%），当前生命值+{hp_inc_cur}")
        except AttributeError:
            pass

        # 触发敌方首回合效果（对称处理）
        enemy_hp = enemy.hp if hasattr(enemy, 'hp') else enemy.get("hp", 100)
        enemy_max_hp = enemy.max_hp if hasattr(enemy, 'max_hp') else enemy.get("max_hp", 100)
        enemy_region = getattr(enemy, 'region', region)
        enemy_triggered = self.effect_manager.check_triggers(enemy_id, TriggerType.FIRST_TURN, {
            "source": "战斗开始",
            "current_hp": enemy_hp,
            "max_hp": enemy_max_hp,
            "current_mp": getattr(enemy, 'mp', 0),
            "max_mp": getattr(enemy, 'max_mp', 0),
            "region": enemy_region,
            "theme": theme_name,
        })

        # 敌方同理处理灵影护盾
        try:
            enemy_max_mp = getattr(enemy, 'max_mp', 0) if hasattr(enemy, 'max_mp') else 0
            mp_shields_enemy = self.effect_manager.get_active_effects(enemy_id, EffectType.SHIELD_FROM_MP)
            for eff in mp_shields_enemy:
                eff.shield_value = int(enemy_max_mp)
                eff.effect_type = EffectType.SHIELD
        except AttributeError:
            pass

        # 敌方同理处理灵影体质：上限按理智百分比提升，当前生命值也按相同百分比提升
        try:
            enemy_max_mp = getattr(enemy, 'max_mp', 0) if hasattr(enemy, 'max_mp') else 0
            hp_from_mp_effects_enemy = self.effect_manager.get_active_effects(enemy_id, EffectType.HP_FROM_MP)
            total_pct_e = 0
            for eff in hp_from_mp_effects_enemy:
                if eff.is_percentage:
                    total_pct_e += eff.value
            if total_pct_e > 0 and hasattr(enemy, 'max_hp'):
                base_hp_e = enemy.hp if hasattr(enemy, 'hp') else 0
                hp_bonus_total_e = int(enemy_max_mp * total_pct_e / 100)
                enemy.max_hp += hp_bonus_total_e
                hp_inc_cur_e = int(base_hp_e * total_pct_e / 100)
                if hasattr(enemy, 'hp'):
                    enemy.hp = min(enemy.max_hp, base_hp_e + hp_inc_cur_e)
                # 记录敌方的临时加成（若为玩家对象）
                if hasattr(enemy, 'id'):
                    self._temp_hp_from_mp[enemy.id] = self._temp_hp_from_mp.get(enemy.id, 0) + hp_bonus_total_e
                self.battle_log.append(f"✨ {enemy.nickname if hasattr(enemy, 'nickname') else '敌人'}的灵影体质·lv.EX：最大生命值+{hp_bonus_total_e}")
        except AttributeError:
            pass

        for effect in enemy_triggered:
            self.effect_manager.add_effect(enemy_id, effect)

    def _register_equipment_triggers(self, unit_id: str, equipped_items: List):
        """注册装备的触发器

        特殊效果解锁规则：
        - 普通装备：+2阶解锁第1个效果，+4阶解锁第2个效果，依此类推
        - VIP定制装备（斩龙闪、镜怨之衣）：0阶即解锁全部效果
        """
        # VIP定制装备列表（0阶即全解锁）
        VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi"}

        for item in equipped_items:
            # 从装备配置中获取special_effects
            config = item.config if hasattr(item, 'config') else None
            if not config:
                continue

            special_effects = getattr(config, 'special_effects', None)
            if not special_effects:
                continue

            # 获取装备ID和升阶等级
            item_id = getattr(item, 'item_id', '')
            upgrade_level = getattr(item, 'upgrade_level', 0)

            # 判断是否为VIP定制装备
            if item_id in VIP_EQUIPMENT_IDS:
                # VIP装备：0阶即解锁全部效果
                unlocked_effects = special_effects
            else:
                # 普通装备：每2阶解锁1个效果
                unlocked_count = upgrade_level // 2
                unlocked_effects = special_effects[:unlocked_count] if unlocked_count > 0 else []

            if not unlocked_effects:
                continue

            # 解析触发器配置
            triggers = parse_triggers_from_yaml(unlocked_effects)

            # 为每个触发器添加来源信息
            for trigger in triggers:
                if not trigger.description:
                    trigger.description = f"{config.name}的特殊效果"

            self.effect_manager.register_triggers(unit_id, triggers)

    def execute_turn(self, attacker: Player, defender: Any, is_player_turn: bool = True) -> Dict:
        """执行一个回合，包含效果处理

        Args:
            attacker: 攻击者
            defender: 防御者
            is_player_turn: 是否为玩家回合

        Returns:
            回合结果字典，包含 damage_dealt 和 hp_restored
        """
        self.turn_counter += 1
        turn_result = {
            "turn": self.turn_counter,
            "messages": [],
            "damage_dealt": 0,
            "hp_restored": 0,  # 新增：记录恢复的HP
            "effects_triggered": []
        }

        attacker_id = attacker.id
        defender_id = defender.id if hasattr(defender, 'id') else "enemy"

        # 回合开始效果
        turn_start_msgs, turn_start_hp = self._process_turn_start(attacker_id, attacker)
        turn_result["messages"].extend(turn_start_msgs)
        turn_result["hp_restored"] += turn_start_hp

        # 检查是否被控制
        if self.effect_manager.has_control_effect(attacker_id):
            turn_result["messages"].append(f"😱 {attacker.nickname}被恐惧，无法行动")
            return turn_result

        # 执行攻击
        attack_result = self._execute_enhanced_attack(attacker, defender, is_player_turn)
        turn_result["messages"].extend(attack_result["messages"])
        turn_result["damage_dealt"] = attack_result.get("total_damage", 0)
        turn_result["hp_restored"] += attack_result.get("hp_restored", 0)  # 累加恢复的HP（包括regen和吸血）
        turn_result["effects_triggered"] = attack_result.get("effects_triggered", [])

        # 处理反弹伤害（对攻击者造成伤害）
        reflect_damage = attack_result.get("reflect_damage", 0)
        if reflect_damage > 0:
            turn_result["reflect_damage"] = reflect_damage
            # 注意：实际扣血由外部战斗系统处理

        # 处理防御者回血
        defender_hp_restored = attack_result.get("defender_hp_restored", 0)
        if defender_hp_restored > 0:
            turn_result["defender_hp_restored"] = defender_hp_restored

        return turn_result

    def _process_turn_start(self, unit_id: str, unit: Any) -> Tuple[List[str], int]:
        """处理回合开始效果

        Returns:
            (消息列表, 恢复的HP)
        """
        messages = []
        hp_restored = 0

        # 触发每回合效果
        region = unit.get_current_region() if hasattr(unit, 'get_current_region') else getattr(unit, 'region', "")
        try:
            from ..utils import get_weekly_theme
            theme_name = get_weekly_theme()["name"]
        except Exception:
            theme_name = ""
        triggered = self.effect_manager.check_triggers(unit_id, TriggerType.EACH_TURN, {
            "source": "回合开始",
            "current_hp": getattr(unit, 'hp', 100),
            "max_hp": getattr(unit, 'max_hp', 100),
            "current_mp": getattr(unit, 'mp', 0),
            "max_mp": getattr(unit, 'max_mp', 0),
            "region": region,
            "theme": theme_name,
        })

        for effect in triggered:
            self.effect_manager.add_effect(unit_id, effect)
            messages.append(format_effect_message(effect, unit.nickname if hasattr(unit, 'nickname') else "敌人"))

        # 处理回血效果
        regen_effects = self.effect_manager.get_active_effects(unit_id, EffectType.REGEN)
        total_regen = 0
        for effect in regen_effects:
            regen_amount = int(getattr(unit, 'max_hp', 100) * effect.value / 100)
            total_regen += regen_amount

        if total_regen > 0:
            hp_restored += total_regen
            messages.append(f"💚 {unit.nickname if hasattr(unit, 'nickname') else '敌人'}回复{total_regen}HP")

        # 效果持续时间递减
        tick_msgs = self.effect_manager.tick_effects(unit_id)
        messages.extend(tick_msgs)

        return messages, hp_restored

    def execute_player_turn(self, attacker: Player, defender: Any, base_attack: int, is_skill: bool = False) -> Dict:
        """执行玩家攻击回合（简化版本，用于PVP简洁格式）

        Args:
            attacker: 攻击者
            defender: 防御者
            base_attack: 基础攻击力
            is_skill: 是否为技能攻击

        Returns:
            攻击结果字典，包含 hit, damage/total_damage, is_critical, combo_count, is_penetration 等字段
        """
        # 统一委托到增强攻击入口，避免双入口漂移
        attacker_id = attacker.id
        # 先应用攻击修正到传入的 base_attack，再通过 override 传给统一入口
        attack_modifier = self.effect_manager.calculate_attribute_modifier(attacker_id, "attack")
        modified_attack = int(base_attack * (1 + attack_modifier / 100))

        unified = self._execute_enhanced_attack(
            attacker, defender,
            is_player_turn=True, is_counter=False, is_combo=False,
            is_skill=is_skill, override_base_attack=modified_attack
        )

        # 保持原有返回字段
        return {
            "hit": unified.get("hit", False),
            "damage": unified.get("total_damage", 0),
            "total_damage": unified.get("total_damage", 0),
            "is_critical": unified.get("is_critical", False),
            "combo_count": unified.get("combo_count", 1),
            "is_penetration": unified.get("is_penetration", False),
            "messages": unified.get("messages", []),
            "hp_restored": unified.get("hp_restored", 0),
            "defender_hp_restored": unified.get("defender_hp_restored", 0),
            "effects_triggered": unified.get("effects_triggered", []),
        }

    def trigger_on_kill(self, killer: Player, victim: Any) -> Dict:
        """触发击杀效果

        Args:
            killer: 击杀者
            victim: 被击杀者

        Returns:
            击杀效果结果字典
        """
        result = {
            "messages": [],
            "hp_restored": 0,
            "effects_triggered": []
        }

        killer_id = killer.id
        killer_name = killer.nickname
        victim_name = victim.nickname if hasattr(victim, 'nickname') else victim.get("name", "敌人")

        # 触发击杀效果
        kill_effects = self.effect_manager.check_triggers(killer_id, TriggerType.ON_KILL, {
            "source": killer_name,
            "victim": victim_name,
            "current_hp": killer.hp,
            "max_hp": killer.max_hp
        })

        # 处理击杀触发的效果
        for effect in kill_effects:
            if effect.effect_type == EffectType.HEAL:
                # 立即回血
                heal_amount = int(killer.max_hp * effect.value / 100) if effect.is_percentage else int(effect.value)
                result["hp_restored"] += heal_amount
                result["messages"].append(f"💚 击杀回复{heal_amount}HP")
                result["effects_triggered"].append("heal")

            elif effect.effect_type == EffectType.GAIN_MP:
                # 噬灵者：永久获得理智值（需要在战斗结束后持久化）
                result["messages"].append(f"👻 噬灵者：剥离灵魂，理智值+{int(effect.value)}（战后结算）")
                result["effects_triggered"].append("gain_mp")
                # 标记需要在战斗结束后处理
                if not hasattr(result, 'post_battle_effects'):
                    result['post_battle_effects'] = []
                result['post_battle_effects'].append({
                    'type': 'gain_mp',
                    'value': int(effect.value)
                })

            elif effect.effect_type == EffectType.GAIN_RANDOM_ATTR:
                # 刃之魔灵：掠夺随机属性（需要在战斗结束后持久化）
                result["messages"].append(f"⚔️ 刃之魔灵：掠夺灵魂，随机属性+{int(effect.value)}（战后结算）")
                result["effects_triggered"].append("gain_random_attr")
                # 标记需要在战斗结束后处理
                if not hasattr(result, 'post_battle_effects'):
                    result['post_battle_effects'] = []
                result['post_battle_effects'].append({
                    'type': 'gain_random_attr',
                    'value': int(effect.value)
                })

            elif effect.duration > 0:
                # 持续性效果
                self.effect_manager.add_effect(killer_id, effect)
                result["messages"].append(format_effect_message(effect, killer_name))
                result["effects_triggered"].append(effect.effect_type.value)

        return result

    def _execute_enhanced_attack(self, attacker: Player, defender: Any,
                                is_player_turn: bool, is_counter: bool = False,
                                is_combo: bool = False, is_skill: bool = False,
                                override_base_attack: Optional[int] = None) -> Dict:
        """执行增强攻击，包含触发效果

        Args:
            attacker: 攻击者
            defender: 防御者
            is_player_turn: 是否为玩家回合
            is_counter: 是否为反击攻击（反击不触发连击）
            is_combo: 是否为连击攻击（连击不触发first_turn效果）
            is_skill: 是否为技能攻击（影响暴击率/连击判定）
            override_base_attack: 覆盖基础攻击力（已应用攻击修正的值）
        """
        result = {
            "messages": [],
            "total_damage": 0,
            "hp_restored": 0,  # 新增：记录恢复的HP
            "effects_triggered": [],
            "combo_count": 1,  # 记录连击次数
            "hit": True,
            "is_critical": False,
            "is_penetration": False
        }

        attacker_id = attacker.id
        defender_id = defender.id if hasattr(defender, 'id') else "enemy"
        attacker_name = attacker.nickname
        defender_name = defender.nickname if hasattr(defender, 'nickname') else defender.get("name", "敌人")

        # 获取属性修正
        attack_modifier = self.effect_manager.calculate_attribute_modifier(attacker_id, "attack")

        # 计算基础攻击力（可被外部覆盖）
        base_attack = override_base_attack if override_base_attack is not None else int(attacker.attack * (1 + attack_modifier / 100))

        # 检查是否有真伤状态
        has_true_damage = len(self.effect_manager.get_active_effects(attacker_id, EffectType.TRUE_DAMAGE)) > 0
        # 预取“无视类”效果：
        # - IGNORE_SPECIAL（绝魔体质，来自PASSIVE）
        # - IGNORE_DEFENSE（至尊锋刃，ON_ATTACK逐次判定）
        ignore_special_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.IGNORE_SPECIAL)
        ignore_special_ratio = 0.0
        for eff in ignore_special_effects:
            val = float(getattr(eff, 'value', 0))
            ignore_special_ratio += max(0.0, val) / 100.0
        # ON_ATTACK 前置判定，仅提取 IGNORE_DEFENSE，用于本次攻击
        pre_ctx = {"source": "pre_attack", "current_hp": getattr(attacker, 'hp', 0), "max_hp": getattr(attacker, 'max_hp', 0)}
        pre_attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, pre_ctx)
        ignore_defense_ratio = 0.0
        for eff in pre_attack_effects:
            if eff.effect_type == EffectType.IGNORE_DEFENSE:
                val = float(getattr(eff, 'value', 0))
                ignore_defense_ratio += max(0.0, val) / 100.0
        # 组合用于护盾/无敌等通用绕过比例
        bypass_fraction = 1.0 - (1.0 - min(1.0, ignore_special_ratio)) * (1.0 - min(1.0, ignore_defense_ratio))

        # 执行基础攻击
        if hasattr(defender, 'defense'):
            # 对玩家 - 需要应用双方的战斗buff
            # 获取双方基础属性
            attacker_base_attrs = BattleAttributeCalculator.calculate_effective_attributes(attacker)
            defender_base_attrs = BattleAttributeCalculator.calculate_effective_attributes(defender)

            # 应用战斗buff
            attacker_attrs = self._get_effective_battle_attributes(attacker_id, attacker_base_attrs)
            defender_attrs = self._get_effective_battle_attributes(defender_id, defender_base_attrs)

            # 使用增强的属性进行攻击判定（真伤在判定内处理）
            attack_result = self._process_pvp_attack(
                attacker, defender, base_attack, is_skill,
                attacker_attrs, defender_attrs, has_true_damage,
                ignore_defense_ratio=ignore_defense_ratio,
                ignore_special_ratio=ignore_special_ratio,
            )
        else:
            # 对怪物（真伤在判定内处理）
            attack_result = self._process_monster_attack(
                attacker, defender, base_attack, is_skill, has_true_damage,
                ignore_defense_ratio=ignore_defense_ratio,
                ignore_special_ratio=ignore_special_ratio,
            )

        # 格式化基础攻击消息
        if not attack_result["hit"]:
            result["messages"].append(f"⚡ {attacker_name}攻击{defender_name}，但被闪避了")

            # 触发闪避效果(防御方)
            dodge_effects = self.effect_manager.check_triggers(defender_id, TriggerType.ON_DODGE, {
                "source": "闪避成功",
                "current_hp": getattr(defender, 'hp', 100),
                "max_hp": getattr(defender, 'max_hp', 100)
            })

            for effect in dodge_effects:
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(format_effect_message(effect, defender_name))
                result["effects_triggered"].append(effect.effect_type.value)

            # 闪避后触发反击（联动增强）
            if hasattr(defender, 'attack') and hasattr(attacker, 'defense'):
                counter = self.check_counter_attack(defender, attacker)
                if counter and counter.get("hit"):
                    counter_damage = counter.get("damage", 0)
                    result["messages"].append(f"↩️ {defender_name}趁机反击，造成{counter_damage}伤害")
                    result["counter_damage"] = counter_damage

            # 标记本次攻击未命中
            result["hit"] = False
            return result

        # 命中
        damage = attack_result["damage"]
        is_critical = attack_result.get("is_critical", False)
        combo_count = attack_result.get("combo_count", 1)
        result["combo_count"] = combo_count
        # 记录关键标志
        result["is_critical"] = is_critical
        result["is_penetration"] = attack_result.get("is_penetration", False)

        # 检查并应用虎标弹等计数型伤害加成效果
        tiger_bullet_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.TIGER_BULLET)
        for tiger_effect in tiger_bullet_effects:
            if tiger_effect.consume_trigger():
                # 还有剩余次数，应用伤害加成
                boost_damage = int(damage * tiger_effect.value / 100)
                damage += boost_damage
                result["messages"].append(f"🐯 虎标弹！伤害提升{tiger_effect.value:.0f}% (+{boost_damage})")
            else:
                # 次数用尽，移除效果并触发下一个效果
                self.effect_manager.remove_effect(attacker_id, tiger_effect)
                result["messages"].append(f"🐯 虎标弹效果结束")

                # 触发猛虎标弹
                if tiger_effect.next_effect == "fierce_tiger_bullet":
                    from .battle_effects import BattleEffect
                    fierce_effect = BattleEffect(
                        effect_type=EffectType.FIERCE_TIGER_BULLET,
                        value=50,  # 造成伤害提高50%
                        duration=0,
                        source=tiger_effect.source,
                        description="猛虎标弹",
                        max_trigger_count=3,
                        next_effect="rigid_qi_heart"
                    )
                    self.effect_manager.add_effect(attacker_id, fierce_effect)
                    result["messages"].append(f"🐅 猛虎标弹激活！")

        # 检查并应用猛虎标弹效果
        fierce_tiger_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.FIERCE_TIGER_BULLET)
        for fierce_effect in fierce_tiger_effects:
            if fierce_effect.consume_trigger():
                # 还有剩余次数，应用伤害加成
                boost_damage = int(damage * fierce_effect.value / 100)
                damage += boost_damage
                result["messages"].append(f"🐅 猛虎标弹！伤害提升{fierce_effect.value:.0f}% (+{boost_damage})")
            else:
                # 次数用尽，移除效果并触发刚气-心
                self.effect_manager.remove_effect(attacker_id, fierce_effect)
                result["messages"].append(f"🐅 猛虎标弹效果结束")

                # 触发刚气-心
                if fierce_effect.next_effect == "rigid_qi_heart":
                    from .battle_effects import BattleEffect
                    rigid_effect = BattleEffect(
                        effect_type=EffectType.RIGID_QI_HEART,
                        value=60,  # 受到伤害降低60%
                        duration=3,
                        source=fierce_effect.source,
                        description="刚气-心"
                    )
                    self.effect_manager.add_effect(attacker_id, rigid_effect)
                    result["messages"].append(f"💪 刚气-心触发！受到伤害降低60%(持续3回合)")

        # 检查刚气-心状态，降低造成的伤害
        rigid_qi_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.RIGID_QI_HEART)
        if rigid_qi_effects:
            for rigid_effect in rigid_qi_effects:
                # 刚气-心：造成伤害降低30%
                damage_reduction = int(damage * 30 / 100)
                damage -= damage_reduction
                result["messages"].append(f"💪 刚气-心：造成伤害降低30% (-{damage_reduction})")

        # 检查防御者是否有无敌状态（可被“绝魔体质/至尊锋刃”部分无视）
        invincible_effects = self.effect_manager.get_active_effects(defender_id, EffectType.INVINCIBLE)
        if invincible_effects:
            if 'bypass_fraction' in locals() and bypass_fraction > 0:
                partial = max(1, int(damage * bypass_fraction))
                result["messages"].append(f"✨ {defender_name}处于无敌状态，但被锋刃/绝魔部分无视，仍造成{partial}伤害！")
                damage = partial
            else:
                result["messages"].append(f"✨ {defender_name}处于无敌状态，免疫所有伤害！")
                return result

        # 恐惧状态增伤（联动增强）
        fear_effects = self.effect_manager.get_active_effects(defender_id, EffectType.FEAR)
        if fear_effects:
            fear_bonus = int(damage * 0.2)
            damage += fear_bonus
            result["messages"].append(f"😱 恐惧加深伤害 +{fear_bonus}")

        # 检查防御者是否有护盾（可被部分无视）
        shield_effects = self.effect_manager.get_active_effects(defender_id, EffectType.SHIELD)
        absorbed_by_shield = 0
        # 先计算直接绕过护盾的伤害比例
        pre_bypass = 0
        if 'bypass_fraction' in locals() and bypass_fraction > 0 and damage > 0:
            pre_bypass = int(damage * min(1.0, max(0.0, bypass_fraction)))
            damage_for_shield = max(0, damage - pre_bypass)
        else:
            damage_for_shield = damage
        for shield_effect in shield_effects:
            if hasattr(shield_effect, 'shield_value') and shield_effect.shield_value > 0:
                if damage_for_shield <= shield_effect.shield_value:
                    # 护盾完全吸收伤害（未能被绕过的部分）
                    absorbed_by_shield += damage_for_shield
                    shield_effect.shield_value -= damage_for_shield
                    damage_for_shield = 0
                    result["messages"].append(f"🛡️ 护盾吸收{absorbed_by_shield}伤害，剩余{shield_effect.shield_value}点护盾")
                    break
                else:
                    # 护盾部分吸收
                    absorbed_by_shield += shield_effect.shield_value
                    damage_for_shield -= shield_effect.shield_value
                    result["messages"].append(f"🛡️ 护盾吸收{shield_effect.shield_value}伤害后破碎")
                    shield_effect.shield_value = 0
                    # 护盾破碎，移除效果
                    self.effect_manager.remove_effect(defender_id, shield_effect)
        # 合并护盾绕过与护盾结算后的伤害
        damage = pre_bypass + damage_for_shield

        # 构建攻击消息
        if is_combo:
            # 连击攻击的消息格式
            attack_msg = f"  🔄 连击"
        else:
            attack_msg = f"⚔️ {attacker_name}攻击{defender_name}"
            if combo_count > 1 and not is_counter:
                attack_msg += f" 🔄x{combo_count}"

        if has_true_damage:
            attack_msg += " 🔥真伤！"
        if is_critical:
            attack_msg += " 💥暴击！"

        # 显示实际伤害（扣除护盾后）
        if absorbed_by_shield > 0:
            # pre_bypass 部分直接穿透护盾，故展示总伤害需包含该部分
            total_shown = damage + absorbed_by_shield
            if 'pre_bypass' in locals() and pre_bypass > 0:
                total_shown += 0  # damage 已经包含 pre_bypass，不重复相加
            attack_msg += f" 造成{total_shown}伤害(护盾吸收{absorbed_by_shield})"
        else:
            attack_msg += f" 造成{damage}伤害"

        result["messages"].append(attack_msg)
        result["total_damage"] = damage

        # 触发攻击时效果
        context = {
            "source": attacker_name,
            "damage": damage,
            "is_critical": is_critical,
            "current_hp": attacker.hp,
            "max_hp": attacker.max_hp
        }

        attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, context)

        # 触发命中效果（命中后触发）
        hit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_HIT, context)
        attack_effects.extend(hit_effects)

        # 如果暴击，触发暴击效果
        if is_critical:
            crit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_CRITICAL, context)
            attack_effects.extend(crit_effects)

        # 处理触发的效果
        for effect in attack_effects:
            # 立即生效的效果
            if effect.effect_type == EffectType.LIFESTEAL:
                lifesteal_amount = int(damage * effect.value / 100)
                # 暴击时吸血加强（联动增强）
                if is_critical:
                    lifesteal_amount = int(lifesteal_amount * 1.5)
                # 实际恢复HP（不超过最大值）
                result["hp_restored"] += lifesteal_amount
                result["messages"].append(f"🧡 吸血{lifesteal_amount}HP{'(暴击加强)' if is_critical else ''}")
                result["effects_triggered"].append("lifesteal")

            elif effect.effect_type == EffectType.HEAL:
                # 立即回血效果
                heal_amount = int(attacker.max_hp * effect.value / 100) if effect.is_percentage else int(effect.value)
                result["hp_restored"] += heal_amount
                result["messages"].append(f"💚 回复{heal_amount}HP")

                result["effects_triggered"].append("heal")

            elif effect.effect_type == EffectType.FEAR:
                # 对敌人施加恐惧效果
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(f"😱 {defender_name}被恐惧{effect.duration}回合")
                result["effects_triggered"].append("fear")

            elif effect.effect_type == EffectType.TRUE_DAMAGE:
                # 真伤状态：添加到攻击者身上
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(f"🔥 进入真伤状态！(持续{effect.duration}回合)")
                result["effects_triggered"].append("true_damage")

            elif effect.effect_type == EffectType.DAMAGE_BOOST:
                # 伤害提升效果（立即生效）
                boost_damage = int(damage * effect.value / 100)
                result["total_damage"] += boost_damage
                result["messages"].append(f"💥 伤害提升！额外造成{boost_damage}伤害")
                result["effects_triggered"].append("damage_boost")

            elif effect.duration > 0:
                # 其他持续性效果
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(format_effect_message(effect, attacker_name))
                result["effects_triggered"].append(effect.effect_type.value)

        # 触发防御时效果(被攻击方) - 同时触发ON_DEFENSE和ON_ATTACKED
        defender_region = defender.get_current_region() if hasattr(defender, 'get_current_region') else getattr(defender, 'region', "")
        try:
            from ..utils import get_weekly_theme
            theme_name = get_weekly_theme()["name"]
        except Exception:
            theme_name = ""

        defense_context = {
            "source": defender_name,
            "attacker": attacker_name,
            "attacker_id": attacker_id,
            "damage": damage,
            "current_hp": getattr(defender, 'hp', 100),
            "max_hp": getattr(defender, 'max_hp', 100),
            "current_mp": getattr(defender, 'mp', 0),
            "max_mp": getattr(defender, 'max_mp', 0),
            "region": defender_region,
            "theme": theme_name,
        }

        defense_effects = self.effect_manager.check_triggers(defender_id, TriggerType.ON_DEFENSE, defense_context)
        # 同时检查ON_ATTACKED触发器（镜怨之衣使用）
        attacked_effects = self.effect_manager.check_triggers(defender_id, TriggerType.ON_ATTACKED, defense_context)
        defense_effects.extend(attacked_effects)

        #  50%
        if 'ignore_special_ratio' in locals() and ignore_special_ratio > 0 and defense_effects:
            scale = max(0.0, 1.0 - min(1.0, ignore_special_ratio))
            for eff in defense_effects:
                if hasattr(eff, 'value') and isinstance(getattr(eff, 'value'), (int, float)):
                    eff.value = float(eff.value) * scale

        for effect in defense_effects:
            if effect.effect_type == EffectType.REFLECT_DEATH:
                # 镜怨体质：反射死亡(可被“绝魔体质”按概率压制)
                apply_instant_death = True
                if 'ignore_special_ratio' in locals() and ignore_special_ratio > 0:
                    # 将“必死”视为100%概率效果，被忽视50%后 -> 仅有(1-忽视)的概率生效
                    if self.rng.random() < min(1.0, ignore_special_ratio):
                        apply_instant_death = False
                        result["messages"].append("🪞 镜怨体质被斩龙闪压制，必死效果本次未触发")
                if apply_instant_death:
                    result["attacker_instant_death"] = True
                    result["messages"].append(f"🪞 镜怨体质！{attacker_name}的攻击被镜像反噬，灵魂瞬间破碎——直接死亡！")
                    result["messages"].append("💀 镜中之人，以己之力斩己之形。")
                    result["effects_triggered"].append("reflect_death")
                # 标记攻击者需要立即死亡
                if hasattr(attacker, 'hp'):
                    attacker.hp = 0

            elif effect.effect_type == EffectType.REFLECT:
                # 反弹伤害（实际扣血），可被“绝魔体质”部分无视
                reflect_damage = int(damage * effect.value / 100)
                reduce_factor = 1.0
                if 'ignore_special_ratio' in locals() and ignore_special_ratio > 0:
                    reduce_factor = max(0.0, 1.0 - min(1.0, ignore_special_ratio))
                reflect_damage = int(reflect_damage * reduce_factor)
                if reflect_damage > 0:
                    result["reflect_damage"] = result.get("reflect_damage", 0) + reflect_damage
                    result["messages"].append(f"↩️ {defender_name}反弹{reflect_damage}伤害给{attacker_name}")
                    result["effects_triggered"].append("reflect")

            elif effect.effect_type == EffectType.SHIELD:
                # 护盾效果
                shield_value = int(defender.max_hp * effect.value / 100) if effect.is_percentage else int(effect.value)
                self.effect_manager.add_effect(defender_id, effect)
                # 将护盾值存储在effect中
                effect.shield_value = shield_value
                result["messages"].append(f"🛡️ {defender_name}获得{shield_value}点护盾")
                result["effects_triggered"].append("shield")

            elif effect.effect_type == EffectType.HEAL:
                # 立即回血
                heal_amount = int(defender.max_hp * effect.value / 100) if effect.is_percentage else int(effect.value)
                result["defender_hp_restored"] = result.get("defender_hp_restored", 0) + heal_amount
                result["messages"].append(f"💚 {defender_name}回复{heal_amount}HP")
                result["effects_triggered"].append("heal")

            else:
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(format_effect_message(effect, defender_name))
                result["effects_triggered"].append(effect.effect_type.value)

        # 处理连击（反击不触发连击，连击本身也不再触发连击）
        if not is_counter and not is_combo and combo_count > 1:
            for combo_index in range(combo_count - 1):
                # 连击时需要重新执行完整的攻击流程
                # 但使用85%的基础攻击力
                combo_result = self._execute_single_combo_attack(
                    attacker, defender, is_player_turn,
                    attacker_id, defender_id, attacker_name, defender_name,
                    base_attack, combo_index + 2  # 第2、3、4次连击
                )

                # 累加伤害和恢复值
                result["total_damage"] += combo_result.get("total_damage", 0)
                result["hp_restored"] += combo_result.get("hp_restored", 0)
                result["messages"].extend(combo_result.get("messages", []))
                result["effects_triggered"].extend(combo_result.get("effects_triggered", []))

        return result

    def _execute_single_combo_attack(self, attacker: Player, defender: Any,
                                     is_player_turn: bool, attacker_id: str,
                                     defender_id: str, attacker_name: str,
                                     defender_name: str, base_attack: int,
                                     combo_number: int) -> Dict:
        """执行单次连击攻击

        Args:
            attacker: 攻击者
            defender: 防御者
            is_player_turn: 是否为玩家回合
            attacker_id: 攻击者ID
            defender_id: 防御者ID
            attacker_name: 攻击者名称
            defender_name: 防御者名称
            base_attack: 基础攻击力
            combo_number: 连击序号（2、3、4...）
        """
        result = {
            "messages": [],
            "total_damage": 0,
            "hp_restored": 0,
            "effects_triggered": []
        }

        # 连击伤害为85%
        combo_base_attack = int(base_attack * 0.85)

        # 应用属性修正
        attack_modifier = self.effect_manager.calculate_attribute_modifier(attacker_id, "attack")
        combo_attack = int(combo_base_attack * (1 + attack_modifier / 100))

        # 检查是否有真伤状态
        has_true_damage = len(self.effect_manager.get_active_effects(attacker_id, EffectType.TRUE_DAMAGE)) > 0

        # 执行基础攻击
        if hasattr(defender, 'defense'):
            # 获取双方基础属性
            attacker_base_attrs = BattleAttributeCalculator.calculate_effective_attributes(attacker)
            defender_base_attrs = BattleAttributeCalculator.calculate_effective_attributes(defender)

            # 应用战斗buff
            attacker_attrs = self._get_effective_battle_attributes(attacker_id, attacker_base_attrs)
            defender_attrs = self._get_effective_battle_attributes(defender_id, defender_base_attrs)

            # 使用增强的属性进行攻击判定（真伤在判定内处理）
            attack_result = self._process_pvp_attack(
                attacker, defender, combo_attack, False,
                attacker_attrs, defender_attrs, has_true_damage
            )
        else:
            # 对怪物（真伤在判定内处理）
            attack_result = self._process_monster_attack(
                attacker, defender, combo_attack, False, has_true_damage
            )

        # 如果未命中
        if not attack_result["hit"]:
            result["messages"].append(f"  🔄 连击第{combo_number}次 被闪避")
            return result

        # 命中
        damage = attack_result["damage"]
        is_critical = attack_result.get("is_critical", False)

        # 构建攻击消息
        attack_msg = f"  🔄 连击第{combo_number}次"
        if has_true_damage:
            attack_msg += " 🔥真伤！"
        if is_critical:
            attack_msg += " 💥暴击！"
        attack_msg += f" 造成{damage}伤害"
        result["messages"].append(attack_msg)
        result["total_damage"] = damage

        # 触发攻击时效果
        context = {
            "source": attacker_name,
            "damage": damage,
            "is_critical": is_critical,
            "current_hp": attacker.hp,
            "max_hp": attacker.max_hp
        }

        attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, context)

        # 触发命中效果（连击也触发ON_HIT，联动增强）
        hit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_HIT, context)
        attack_effects.extend(hit_effects)

        # 如果暴击，触发暴击效果
        if is_critical:
            crit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_CRITICAL, context)
            attack_effects.extend(crit_effects)

        # 处理触发的效果
        for effect in attack_effects:
            if effect.effect_type == EffectType.LIFESTEAL:
                lifesteal_amount = int(damage * effect.value / 100)
                # 暴击时吸血加强（联动增强）
                if is_critical:
                    lifesteal_amount = int(lifesteal_amount * 1.5)
                result["hp_restored"] += lifesteal_amount
                result["messages"].append(f"    🧡 吸血{lifesteal_amount}HP{'(暴击加强)' if is_critical else ''}")
                result["effects_triggered"].append("lifesteal")

            elif effect.effect_type == EffectType.TRUE_DAMAGE:
                # 真伤状态：添加到攻击者身上
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(f"    🔥 进入真伤状态！(持续{effect.duration}回合)")
                result["effects_triggered"].append("true_damage")

            elif effect.effect_type == EffectType.FEAR:
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(f"    😱 {defender_name}被恐惧{effect.duration}回合")
                result["effects_triggered"].append("fear")

            elif effect.effect_type == EffectType.DAMAGE_BOOST:
                boost_damage = int(damage * effect.value / 100)
                result["total_damage"] += boost_damage
                result["messages"].append(f"    💥 伤害提升！额外造成{boost_damage}伤害")
                result["effects_triggered"].append("damage_boost")

            elif effect.duration > 0:
                # 其他持续性效果（连击不重复添加，避免叠加过多）
                pass

        return result

    def _get_effective_battle_attributes(self, unit_id: str, base_attrs: Dict) -> Dict:
        """获取应用了战斗buff后的有效属性

        Args:
            unit_id: 单位ID
            base_attrs: 基础属性字典

        Returns:
            应用buff后的属性字典
        """
        effective_attrs = base_attrs.copy()

        # 应用战斗buff修正
        for attr_name in ["critical_rate", "dodge_rate", "accuracy_rate"]:
            modifier = self.effect_manager.calculate_attribute_modifier(unit_id, attr_name)
            if modifier != 0:
                effective_attrs[attr_name] = effective_attrs.get(attr_name, 0) + modifier
                # 应用上限
                cap = BattleAttributeCalculator.ATTRIBUTE_CAPS.get(attr_name, 100)
                effective_attrs[attr_name] = min(effective_attrs[attr_name], cap)
                effective_attrs[attr_name] = max(0, effective_attrs[attr_name])

        return effective_attrs

    def _process_pvp_attack(self, attacker: Player, defender: Player, base_damage: int,
                           is_skill: bool, attacker_attrs: Dict, defender_attrs: Dict,
                           has_true_damage: bool = False,
                           ignore_defense_ratio: float = 0.0,
                           ignore_special_ratio: float = 0.0) -> Dict:
        """处理PVP攻击（使用已应用buff的属性）

        Args:
            attacker: 攻击者
            defender: 防御者
            base_damage: 基础伤害
            is_skill: 是否为技能攻击
            attacker_attrs: 攻击者的有效属性（已应用buff）
            defender_attrs: 防御者的有效属性（已应用buff）
            has_true_damage: 是否有真伤状态（只无视防御，不跳过命中判定）

        Returns:
            攻击结果字典
        """
        result = {
            "hit": False,
            "damage": 0,
            "is_critical": False,
            "is_penetration": False,
            "combo_count": 1,
            "effects": []
        }

        # 1. 命中判定（真伤也需要命中判定）
        # 斩龙闪：无视部分“闪避/特殊效果”，对方闪避率按忽视比例降低
        adjusted_dodge = defender_attrs.get("dodge_rate", 0)
        adjusted_dodge = adjusted_dodge * (1 - max(0.0, min(1.0, ignore_defense_ratio)))
        adjusted_dodge = adjusted_dodge * (1 - max(0.0, min(1.0, ignore_special_ratio)))
        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            attacker_attrs.get("accuracy_rate", 0),
            adjusted_dodge
        )

        if self.rng.random() > hit_chance:
            result["effects"].append("被闪避")
            return result

        result["hit"] = True

        # 2. 穿透判定（真伤时跳过，因为真伤直接无视防御）
        penetration_ratio = 0
        if not has_true_damage:
            penetration_ratio = BattleAttributeCalculator.get_penetration_ratio(
                attacker_attrs.get("penetration_rate", 0)
            )
            # 叠加“至尊锋刃”提供的额外无视比例
            penetration_ratio = min(1.0, penetration_ratio + max(0.0, ignore_defense_ratio))
            if penetration_ratio > 0:
                result["is_penetration"] = True
                result["penetration_ratio"] = penetration_ratio

        # 3. 暴击判定（考虑防御方抗暴率）
        crit_rate = attacker_attrs["skill_crit_rate"] if is_skill else attacker_attrs["critical_rate"]
        defender_anti_crit_rate = defender_attrs["anti_crit_rate"]

        # 计算实际暴击率（攻击方暴击率 - 防御方抗暴率）
        effective_crit_rate = max(0, crit_rate - defender_anti_crit_rate)
        is_critical = BattleAttributeCalculator.roll_critical_hit(effective_crit_rate, self.rng)
        result["is_critical"] = is_critical

        # 4. 连击判定（仅普攻）
        if not is_skill:
            combo_count = BattleAttributeCalculator.roll_combo_attack(
                attacker_attrs["combo_rate"], self.rng
            )
            result["combo_count"] = combo_count

        # 5. 伤害计算
        final_damage = base_damage

        # 应用暴击
        if is_critical:
            final_damage = BattleAttributeCalculator.calculate_critical_damage(
                final_damage, attacker_attrs["critical_power"]
            )
            result["effects"].append("CRITICAL")

        # 应用防御减伤（真伤时完全无视防御）
        if has_true_damage:
            # 真伤：不应用防御减伤
            result["effects"].append("TRUE_DAMAGE")
        else:
            # 获取防御者的防御力修正
            defender_id = defender.id if hasattr(defender, 'id') else "enemy"
            defense_modifier = self.effect_manager.calculate_attribute_modifier(defender_id, "defense")
            effective_defense = int(defender.defense * (1 + defense_modifier / 100))

            if penetration_ratio > 0:
                from ..utils import apply_defense_mitigation
                mitigation = apply_defense_mitigation(
                    final_damage, effective_defense, penetration_ratio
                )
                final_damage = mitigation["final_damage"]
                result["effects"].append("PENETRATION")
            else:
                from ..utils import apply_defense_mitigation
                mitigation = apply_defense_mitigation(final_damage, effective_defense)
                final_damage = mitigation["final_damage"]

        result["damage"] = final_damage
        result["total_damage"] = final_damage  # 添加 total_damage 字段以保持兼容性
        return result

    def _process_monster_attack(self, attacker: Player, monster_stats: Dict,
                               base_damage: int, is_skill: bool, has_true_damage: bool = False,
                               ignore_defense_ratio: float = 0.0,
                               ignore_special_ratio: float = 0.0) -> Dict:
        """处理对怪物的攻击（简化版）

        Args:
            attacker: 攻击者玩家
            monster_stats: 怪物属性字典
            base_damage: 基础伤害
            is_skill: 是否为技能攻击
            has_true_damage: 是否有真伤状态（只无视防御，不跳过命中判定）

        Returns:
            攻击结果字典
        """
        # 获取基础属性
        base_attrs = BattleAttributeCalculator.calculate_effective_attributes(attacker)

        # 应用战斗buff
        attacker_id = attacker.id
        attacker_attrs = self._get_effective_battle_attributes(attacker_id, base_attrs)

        result = {
            "hit": False,
            "damage": 0,
            "is_critical": False,
            "is_penetration": False,
            "combo_count": 1,
            "effects": []
        }

        # 命中判定（怪物闪避率固定为0，敏捷只影响先后手）（真伤也需要命中判定）
        monster_dodge_rate = 0.0  # 怪物闪避率固定为0

        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            attacker_attrs["accuracy_rate"], monster_dodge_rate
        )

        if self.rng.random() > hit_chance:
            result["effects"].append("被闪避")
            return result

        result["hit"] = True

        # 穿透比例计算（真伤时跳过，因为真伤直接无视防御）
        penetration_ratio = 0
        if not has_true_damage:
            penetration_ratio = BattleAttributeCalculator.get_penetration_ratio(
                attacker_attrs.get("penetration_rate", 0)
            )
            # 叠加“至尊锋刃”提供的额外无视比例
            penetration_ratio = min(1.0, penetration_ratio + max(0.0, ignore_defense_ratio))
            if penetration_ratio > 0:
                result["is_penetration"] = True
                result["penetration_ratio"] = penetration_ratio

        # 暴击判定（考虑怪物抗暴率）
        crit_rate = attacker_attrs["skill_crit_rate"] if is_skill else attacker_attrs["critical_rate"]
        monster_anti_crit_rate = monster_stats.get("anti_crit_rate", 0)

        # 计算实际暴击率（玩家暴击率 - 怪物抗暴率）
        effective_crit_rate = max(0, crit_rate - monster_anti_crit_rate)
        is_critical = BattleAttributeCalculator.roll_critical_hit(effective_crit_rate, self.rng)
        result["is_critical"] = is_critical

        # 连击判定（仅普攻）
        if not is_skill:
            combo_count = BattleAttributeCalculator.roll_combo_attack(
                attacker_attrs["combo_rate"], self.rng
            )
            result["combo_count"] = combo_count

        # 伤害计算
        final_damage = base_damage

        # 应用暴击
        if is_critical:
            final_damage = BattleAttributeCalculator.calculate_critical_damage(
                final_damage, attacker_attrs["critical_power"]
            )
            result["effects"].append("CRITICAL")

        # 应用防御减伤（真伤时完全无视防御）
        if has_true_damage:
            # 真伤：不应用防御减伤
            result["effects"].append("TRUE_DAMAGE")
        else:
            # 应用穿透和防御
            monster_defense = monster_stats.get("defense", 0)
            if penetration_ratio > 0:
                from ..utils import apply_defense_mitigation

                mitigation = apply_defense_mitigation(
                    final_damage, monster_defense, penetration_ratio
                )
                final_damage = mitigation["final_damage"]
                result["effects"].append("PENETRATION")
            else:
                from ..utils import apply_defense_mitigation

                mitigation = apply_defense_mitigation(final_damage, monster_defense)
                final_damage = mitigation["final_damage"]

        result["damage"] = final_damage
        result["total_damage"] = final_damage  # 添加 total_damage 字段以保持兼容性
        return result

    def check_counter_attack(self, defender: Player, attacker: Player) -> Optional[Dict]:
        """检查并执行反击

        Args:
            defender: 防御者（可能反击的一方）
            attacker: 攻击者（被反击的目标）

        Returns:
            反击结果字典，如果未触发反击则返回None
            包含字段: hit, damage, is_critical
        """
        # 获取防御者的有效属性
        defender_base_attrs = BattleAttributeCalculator.calculate_effective_attributes(defender)
        defender_id = defender.id
        defender_attrs = self._get_effective_battle_attributes(defender_id, defender_base_attrs)

        # 判定是否触发反击
        counter_triggered = BattleAttributeCalculator.roll_counter_attack(
            defender_attrs["counter_rate"], self.rng
        )

        if not counter_triggered:
            return None

        # 触发反击，执行一次简化的攻击
        # 反击伤害为防御者攻击力的50%
        counter_attack = int(defender.attack * 0.5)

        # 获取攻击者的有效属性
        attacker_base_attrs = BattleAttributeCalculator.calculate_effective_attributes(attacker)
        attacker_id = attacker.id if hasattr(attacker, 'id') else "enemy"
        attacker_attrs = self._get_effective_battle_attributes(attacker_id, attacker_base_attrs)

        # 执行反击攻击判定
        attack_result = self._process_pvp_attack(
            defender, attacker, counter_attack, False,
            defender_attrs, attacker_attrs
        )
        return attack_result

    def reset_temp_bonuses(self, unit: Any):
        """回退首回合临时增加的最大生命值等（如灵影体质）"""
        try:
            unit_id = unit.id if hasattr(unit, 'id') else None
        except Exception:
            unit_id = None
        if not unit_id:
            return
        bonus = self._temp_hp_from_mp.pop(unit_id, 0)
        if bonus > 0 and hasattr(unit, 'max_hp'):
            old_max = unit.max_hp
            new_max = max(1, old_max - bonus)
            # 维持战斗结束时的血量比例：按比例回退当前生命值
            if hasattr(unit, 'hp') and old_max > 0:
                ratio = unit.hp / float(old_max)
            else:
                ratio = 0.0
            unit.max_hp = new_max
            if hasattr(unit, 'hp'):
                unit.hp = int(max(0, min(new_max, ratio * new_max)))

    def get_battle_log(self) -> List[str]:
        """获取战斗日志"""
        return self.battle_log.copy()

    def format_battle_summary(self) -> str:
        """格式化战斗摘要"""
        return "\n".join(self.battle_log)
