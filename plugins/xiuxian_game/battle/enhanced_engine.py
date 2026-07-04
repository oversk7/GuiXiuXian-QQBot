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
from ..item.equipment_service import VIP_EQUIPMENT_IDS


def _effective_max_hp(unit) -> int:
    """战斗内读有效血量上限：优先开战预计算缓存（含临时buff/宠物），无缓存回退裸字段/怪物dict"""
    cached = getattr(unit, '_cached_max_hp', None)
    if cached is not None:
        return int(cached)
    if isinstance(unit, dict):
        return int(unit.get('max_hp', 100))
    return int(getattr(unit, 'max_hp', 100))


def _unit_battle_attr(unit, attr_name: str) -> float:
    """战斗内读单位战斗属性：优先开战预计算缓存（含buff/宠物/T1词缀），回退裸字段/怪物dict"""
    cached = getattr(unit, '_cached_battle_attrs', None)
    if isinstance(cached, dict) and attr_name in cached:
        return float(cached[attr_name])
    if isinstance(unit, dict):
        return float(unit.get(attr_name, 0))
    return float(getattr(unit, attr_name, 0))


class EnhancedBattleEngine:
    """增强战斗引擎 - 支持状态效果和触发系统"""

    def __init__(self, seed: Optional[str] = None, session=None):
        """初始化增强战斗引擎

        Args:
            seed: 随机种子，用于确定性战斗
            session: 数据库会话，用于查询临时buff
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
        self._temp_mp_from_hp: Dict[str, int] = {}

        # 骰子buff临时加成（诡面骰）：{player_id: (attr_name, original_value)}
        self._temp_dice_buff: Dict[str, tuple] = {}
        # 绝魔体质对敌方特殊属性的临时削减：{target_id: {attr_name: original_value}}
        self._temp_ignore_special_debuff: Dict[str, Dict[str, float]] = {}
        # 缓存装备实例，用于检查每日触发限制
        self._equipped_items_cache: Dict[str, List] = {}
        # 数据库会话，用于查询临时buff
        self.session = session
        # 战斗发起者ID：用于判断镜怨体质(REFLECT_DEATH)是否触发
        # 仅当防御方不是战斗发起者时才触发镜怨体质（即被动防守方才能反杀）
        # None表示不限制（PvE等场景）
        self.battle_initiator_id: Optional[str] = None
        # 切磋模式：切磋不触发镜怨体质(REFLECT_DEATH)等致死效果
        self.is_sparring: bool = False


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

        # 缓存玩家装备，用于后续检查每日触发限制
        if player_equipped_items:
            self._equipped_items_cache[player.id] = player_equipped_items
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
            "max_hp": _effective_max_hp(player),
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
            "max_hp": _effective_max_hp(player),
            "current_mp": getattr(player, 'mp', 0),
            "max_mp": getattr(player, 'max_mp', 0),
            "region": region,
            "theme": theme_name,
        })

        for effect in triggered:
            if effect.effect_type == EffectType.SHIELD:
                effect.shield_value = int(_effective_max_hp(player) * effect.value / 100) if effect.is_percentage else int(effect.value)
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
                # 同步开战预计算缓存，保持战斗内血量上限单一口径
                if getattr(player, '_cached_max_hp', None) is not None:
                    player._cached_max_hp += hp_bonus_total
                # 当前生命值按百分比提升（基于提升前的当前HP）
                hp_inc_cur = int(base_hp * total_pct / 100)
                player.hp = min(_effective_max_hp(player), base_hp + hp_inc_cur)
                # 记录临时加成，战斗结束回退
                self._temp_hp_from_mp[player.id] = self._temp_hp_from_mp.get(player.id, 0) + hp_bonus_total
                self.battle_log.append(f"✨ 灵影体质·lv.EX：最大生命值+{hp_bonus_total}（理智值的{total_pct:.0f}%），当前生命值+{hp_inc_cur}")
        except AttributeError:
            pass

        # 首回合：灵影体质（反向）- 按最大生命值增加最大理智值，同时可按同百分比提升当前理智
        try:
            player_max_hp = getattr(player, 'max_hp', 0)
            mp_from_hp_effects = self.effect_manager.get_active_effects(player.id, EffectType.MP_FROM_HP)
            total_pct_mp = 0
            for eff in mp_from_hp_effects:
                if eff.is_percentage:
                    total_pct_mp += eff.value
            if total_pct_mp > 0 and hasattr(player, 'max_mp'):
                base_mp = getattr(player, 'mp', 0)
                mp_bonus_total = int(player_max_hp * total_pct_mp / 100)
                player.max_mp = getattr(player, 'max_mp', 0) + mp_bonus_total
                # 当前理智按百分比提升（仅展示用途）
                if hasattr(player, 'mp'):
                    mp_inc_cur = int(base_mp * total_pct_mp / 100)
                    player.mp = min(player.max_mp, base_mp + mp_inc_cur)
                # 记录临时加成，战斗结束回退
                self._temp_mp_from_hp[player.id] = self._temp_mp_from_hp.get(player.id, 0) + mp_bonus_total
                self.battle_log.append(f"✨ 灵影体质·反：最大理智+{mp_bonus_total}（生命值的{total_pct_mp:.0f}%）")
        except AttributeError:
            pass

        # 首回合：诡面骰骰子buff - 从vip_equipment_data读取未消耗的骰子buff并应用
        # 主动发起切磋时使用buff；被动接受切磋时不使用，保留至真实战斗
        try:
            vip_data = getattr(player, 'vip_equipment_data', None) or {}
            dice_buff = vip_data.get("dice_buff")
            is_initiator = self.battle_initiator_id and str(player.id) == str(self.battle_initiator_id)
            if dice_buff and not dice_buff.get("consumed") and (not self.is_sparring or is_initiator):
                attr_name = dice_buff.get("attribute", "")
                attr_cn = dice_buff.get("attribute_cn", attr_name)
                valid_attrs = ["critical_rate", "critical_power", "combo_rate", "counter_rate", "dodge_rate",
                               "accuracy_rate", "penetration_rate", "anti_crit_rate",
                               "anti_combo_rate", "anti_counter_rate"]
                if attr_name in valid_attrs and hasattr(player, attr_name):
                    original_value = getattr(player, attr_name, 0)
                    # 暴击力特殊处理：翻倍（其余属性+100百分点）
                    if attr_name == "critical_power":
                        boosted_value = original_value * 2
                        log_suffix = f"{original_value:.0f}→{boosted_value:.0f} (×2)"
                    else:
                        boosted_value = original_value + 100
                        log_suffix = f"{original_value:.0f}%→{boosted_value:.0f}% (+100%点)"
                    self._sync_unit_attr(player, attr_name, boosted_value)
                    self._temp_dice_buff[player.id] = (attr_name, original_value)
                    self.battle_log.append(f"🎲 骰相·乱：{attr_cn} {log_suffix}")
                    # 标记为已消耗（战后持久化）
                    import copy
                    new_data = copy.deepcopy(dict(vip_data))
                    new_data["dice_buff"]["consumed"] = True
                    player.vip_equipment_data = new_data
        except (AttributeError, TypeError, KeyError):
            pass

        # 触发敌方首回合效果（对称处理）
        enemy_hp = enemy.hp if hasattr(enemy, 'hp') else enemy.get("hp", 100)
        enemy_max_hp = _effective_max_hp(enemy)
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
        #
        #
        #
        # 	
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        #
        # 敌方同理处理灵影体质（反向）：最大理智按生命值百分比提升
        try:
            enemy_max_hp2 = getattr(enemy, 'max_hp', 0) if hasattr(enemy, 'max_hp') else 0
            mp_from_hp_enemy = self.effect_manager.get_active_effects(enemy_id, EffectType.MP_FROM_HP)
            total_pct_emp = 0
            for eff in mp_from_hp_enemy:
                if eff.is_percentage:
                    total_pct_emp += eff.value
            if total_pct_emp > 0 and hasattr(enemy, 'max_mp'):
                base_emp = getattr(enemy, 'mp', 0) if hasattr(enemy, 'mp') else 0
                mp_bonus_total_e2 = int(enemy_max_hp2 * total_pct_emp / 100)
                enemy.max_mp = getattr(enemy, 'max_mp', 0) + mp_bonus_total_e2
                if hasattr(enemy, 'mp'):
                    mp_inc_cur_e = int(base_emp * total_pct_emp / 100)
                    enemy.mp = min(enemy.max_mp, base_emp + mp_inc_cur_e)
                if hasattr(enemy, 'id'):
                    self._temp_mp_from_hp[enemy.id] = self._temp_mp_from_hp.get(enemy.id, 0) + mp_bonus_total_e2
                self.battle_log.append(f"✨ {enemy.nickname if hasattr(enemy, 'nickname') else '敌人'}的灵影体质·反：最大理智+{mp_bonus_total_e2}")
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
                # 同步开战预计算缓存，保持战斗内血量上限单一口径
                if getattr(enemy, '_cached_max_hp', None) is not None:
                    enemy._cached_max_hp += hp_bonus_total_e
                hp_inc_cur_e = int(base_hp_e * total_pct_e / 100)
                if hasattr(enemy, 'hp'):
                    enemy.hp = min(_effective_max_hp(enemy), base_hp_e + hp_inc_cur_e)
                # 记录敌方的临时加成（若为玩家对象）
                if hasattr(enemy, 'id'):
                    self._temp_hp_from_mp[enemy.id] = self._temp_hp_from_mp.get(enemy.id, 0) + hp_bonus_total_e
                self.battle_log.append(f"✨ {enemy.nickname if hasattr(enemy, 'nickname') else '敌人'}的灵影体质·lv.EX：最大生命值+{hp_bonus_total_e}")
        except AttributeError:
            pass

        # 敌方同理处理骰子buff（诡面骰）
        # 主动发起切磋时使用buff；被动接受切磋时不使用，保留至真实战斗
        try:
            enemy_vip_data = getattr(enemy, 'vip_equipment_data', None) or {}
            enemy_dice = enemy_vip_data.get("dice_buff")
            enemy_is_initiator = self.battle_initiator_id and hasattr(enemy, 'id') and str(enemy.id) == str(self.battle_initiator_id)
            if enemy_dice and not enemy_dice.get("consumed") and hasattr(enemy, 'id') and (not self.is_sparring or enemy_is_initiator):
                e_attr = enemy_dice.get("attribute", "")
                e_attr_cn = enemy_dice.get("attribute_cn", e_attr)
                valid_attrs = ["critical_rate", "critical_power", "combo_rate", "counter_rate", "dodge_rate",
                               "accuracy_rate", "penetration_rate", "anti_crit_rate",
                               "anti_combo_rate", "anti_counter_rate"]
                if e_attr in valid_attrs and hasattr(enemy, e_attr):
                    e_orig = getattr(enemy, e_attr, 0)
                    if e_attr == "critical_power":
                        e_boosted = e_orig * 2
                        e_log_suffix = f"{e_orig:.0f}→{e_boosted:.0f} (×2)"
                    else:
                        e_boosted = e_orig + 100
                        e_log_suffix = f"{e_orig:.0f}%→{e_boosted:.0f}% (+100%点)"
                    self._sync_unit_attr(enemy, e_attr, e_boosted)
                    self._temp_dice_buff[enemy.id] = (e_attr, e_orig)
                    enemy_name = enemy.nickname if hasattr(enemy, 'nickname') else '敌人'
                    self.battle_log.append(f"🎲 {enemy_name}的骰相·乱：{e_attr_cn} {e_log_suffix}")
                    import copy
                    new_edata = copy.deepcopy(dict(enemy_vip_data))
                    new_edata["dice_buff"]["consumed"] = True
                    enemy.vip_equipment_data = new_edata
        except (AttributeError, TypeError, KeyError):
            pass

        for effect in enemy_triggered:
            self.effect_manager.add_effect(enemy_id, effect)

        # 应用"绝魔体质"对敌方特殊属性的战前削减（IGNORE_SPECIAL）
        # 拥有IGNORE_SPECIAL的一方 → 对手的9种特殊属性按比例削弱
        self.apply_ignore_special_debuff(player.id, enemy, enemy_id)
        self.apply_ignore_special_debuff(enemy_id, player, player.id)

    def _register_equipment_triggers(self, unit_id: str, equipped_items: List):
        """注册装备的触发器

        特殊效果解锁规则：
        - 普通装备：+2阶解锁第1个效果，+4阶解锁第2个效果，依此类推
        - VIP定制装备（斩龙闪、镜怨之衣、天退星刀、归雨、折光年）：0阶即解锁全部效果
        """
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

            # 为每个触发器添加来源信息（装备名·技能名）
            equip_name = config.name
            for trigger in triggers:
                if not trigger.description:
                    trigger.description = f"{config.name}的特殊效果"
                # 从description中提取技能名（取"："前的部分）
                skill_name = ""
                if trigger.description:
                    parts = trigger.description.split("：", 1)
                    if len(parts) > 1:
                        skill_name = parts[0].strip()
                if skill_name:
                    trigger.source_equipment = f"{equip_name}·{skill_name}"
                else:
                    trigger.source_equipment = equip_name

            # 针对"斩龙闪"：其"生命→理智"的加成应为全局被动，面板可见，不在战斗内首回合生效
            # 因此这里过滤掉其 MP_FROM_HP 的战斗触发器，避免与全局持久化重复
            if item_id == "vip_blade_zhanlongshan":
                triggers = [t for t in triggers if t.effect != EffectType.MP_FROM_HP]

            # 针对"诡面骰"：其"攻击力→生命值"的加成已在穿戴时持久写入，不在战斗内重复生效
            if item_id == "vip_ghost_dice":
                triggers = [t for t in triggers if t.effect != EffectType.HP_FROM_ATTACK]

            self.effect_manager.register_triggers(unit_id, triggers)

        # 注册T2词缀触发器
        from ..item.affix_service import get_affixes_from_equipment, get_t2_trigger_configs
        for item in equipped_items:
            affixes = get_affixes_from_equipment(getattr(item, 'extra_attrs', None))
            if not affixes:
                continue
            equip_name = getattr(getattr(item, 'config', None), 'name', '装备')
            t2_triggers = get_t2_trigger_configs(affixes, source_name=equip_name)
            if t2_triggers:
                self.effect_manager.register_triggers(unit_id, t2_triggers)

        # 注册铭文触发器（支持基础+高级铭文多效果）
        from ..item.inscription_service import get_inscriptions_from_equipment, inscription_to_trigger_configs
        for item in equipped_items:
            inscriptions = get_inscriptions_from_equipment(getattr(item, 'gem_slots_data', None))
            if not inscriptions:
                continue
            equip_name = getattr(getattr(item, 'config', None), 'name', '装备')
            for insc_data in inscriptions:
                triggers = inscription_to_trigger_configs(insc_data, source_name=equip_name)
                if triggers:
                    self.effect_manager.register_triggers(unit_id, triggers)

        # 注册套装触发效果
        from ..item.set_bonus_service import get_set_trigger_configs
        set_triggers = get_set_trigger_configs([getattr(item, 'item_id', '') for item in equipped_items])
        if set_triggers:
            self.effect_manager.register_triggers(unit_id, set_triggers)

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

        # 先检查控制效果（必须在 tick 之前），避免 tick 把 duration=1 的恐惧消耗后检查失效
        is_controlled = self.effect_manager.has_control_effect(attacker_id)

        # 回合开始效果（内部会 tick 效果持续时间）
        turn_start_msgs, turn_start_hp = self._process_turn_start(attacker_id, attacker)
        turn_result["messages"].extend(turn_start_msgs)
        turn_result["hp_restored"] += turn_start_hp

        # 检查是否被控制
        if is_controlled:
            turn_result["messages"].append(f"😱 {attacker.nickname}被恐惧，无法行动")
            return turn_result

        # 执行攻击
        attack_result = self._execute_enhanced_attack(attacker, defender, is_player_turn)
        turn_result["messages"].extend(attack_result["messages"])
        turn_result["damage_dealt"] = attack_result.get("total_damage", 0)
        turn_result["hp_restored"] += attack_result.get("hp_restored", 0)  # 累加恢复的HP（包括regen和吸血）
        turn_result["effects_triggered"] = attack_result.get("effects_triggered", [])

        # 兼容旧调用方：回填关键字段，便于上层紧凑日志使用
        turn_result["hit"] = attack_result.get("hit", False)
        # 注意：优先使用 total_damage（包含连击与护盾结算后），回退到 damage
        turn_result["damage"] = attack_result.get("total_damage", attack_result.get("damage", 0))
        turn_result["is_critical"] = attack_result.get("is_critical", False)
        turn_result["is_penetration"] = attack_result.get("is_penetration", False)
        turn_result["combo_count"] = attack_result.get("combo_count", 1)
        turn_result["effects"] = attack_result.get("effects", [])
        # 斩龙闪：20%必中与80%常规部分的拆分
        turn_result["guaranteed_damage"] = attack_result.get("guaranteed_damage", 0)
        turn_result["normal_damage"] = attack_result.get("normal_damage", 0)
        turn_result["normal_missed"] = attack_result.get("normal_missed", False)

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
            "max_hp": _effective_max_hp(unit),
            "current_mp": getattr(unit, 'mp', 0),
            "max_mp": getattr(unit, 'max_mp', 0),
            "region": region,
            "theme": theme_name,
        })

        for effect in triggered:
            if effect.effect_type == EffectType.SHIELD:
                effect.shield_value = int(_effective_max_hp(unit) * effect.value / 100) if effect.is_percentage else int(effect.value)
            self.effect_manager.add_effect(unit_id, effect)
            messages.append(format_effect_message(effect, unit.nickname if hasattr(unit, 'nickname') else "敌人"))

        # 处理回血效果
        regen_effects = self.effect_manager.get_active_effects(unit_id, EffectType.REGEN)
        total_regen = 0
        for effect in regen_effects:
            regen_amount = int(_effective_max_hp(unit) * effect.value / 100)
            total_regen += regen_amount

        # 属性面板回复率（T1词缀/宠物饰品等数值型来源）：每回合回复 max_hp 的 regen_rate%
        stat_regen_rate = _unit_battle_attr(unit, 'regen_rate')
        if stat_regen_rate > 0:
            total_regen += int(_effective_max_hp(unit) * stat_regen_rate / 100)

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
        ret = {
            "hit": unified.get("hit", False),
            "damage": unified.get("total_damage", 0),
            "total_damage": unified.get("total_damage", 0),
            "pre_boost_damage": unified.get("pre_boost_damage", unified.get("total_damage", 0)),
            "is_critical": unified.get("is_critical", False),
            "combo_count": unified.get("combo_count", 1),
            "is_penetration": unified.get("is_penetration", False),
            "messages": unified.get("messages", []),
            "hp_restored": unified.get("hp_restored", 0),
            "defender_hp_restored": unified.get("defender_hp_restored", 0),
            "effects_triggered": unified.get("effects_triggered", []),
        }
        # 转发反弹伤害和即死效果，供上层正确结算HP
        if unified.get("reflect_damage", 0) > 0:
            ret["reflect_damage"] = unified["reflect_damage"]
        if unified.get("attacker_instant_death"):
            ret["attacker_instant_death"] = True
        return ret

    def _check_blade_daily_random_available(self, player: Player) -> bool:
        """检查刃之魔灵效果今天是否可以触发

        Args:
            player: 玩家对象

        Returns:
            True表示今天还未触发，可以触发；False表示今天已触发
        """
        # 获取缓存的装备列表
        equipped_items = self._equipped_items_cache.get(player.id, [])

        # 查找斩龙闪装备
        for item in equipped_items:
            if item.item_id == "vip_blade_zhanlongshan":
                extra = item.extra_attrs or {}
                from datetime import datetime
                today = datetime.now().strftime("%Y%m%d")
                # 如果今天已经触发过，返回False
                if extra.get("blade_rand_day") == today:
                    return False
                break

        return True

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
            "max_hp": _effective_max_hp(killer)
        })

        # 处理击杀触发的效果
        for effect in kill_effects:
            _ktag = effect.equip_tag()  # 装备来源标签
            if effect.effect_type == EffectType.HEAL:
                # 立即回血
                heal_amount = int(_effective_max_hp(killer) * effect.value / 100) if effect.is_percentage else int(effect.value)
                result["hp_restored"] += heal_amount
                result["messages"].append(f"💚 {_ktag}击杀回复{heal_amount}HP")
                result["effects_triggered"].append("heal")

            elif effect.effect_type == EffectType.GAIN_MP:
                # 噬灵者：永久获得理智值（需要在战斗结束后持久化）
                result["messages"].append(f"👻 {_ktag}剥离灵魂，理智值+{int(effect.value)}（战后结算）")
                result["effects_triggered"].append("gain_mp")
                # 标记需要在战斗结束后处理
                if 'post_battle_effects' not in result:
                    result['post_battle_effects'] = []
                result['post_battle_effects'].append({
                    'type': 'gain_mp',
                    'value': int(effect.value)
                })

            elif effect.effect_type == EffectType.GAIN_HP:
                # 噬灵者（变更）：永久获得最大生命值（需要在战斗结束后持久化）
                # value是属性点数，1属性点=3生命值
                attr_points = int(effect.value)
                actual_hp = attr_points * 3  # 转换为实际生命值
                result["messages"].append(f"💓 {_ktag}剥离血肉，最大生命值+{actual_hp}（战后结算）")
                result["effects_triggered"].append("gain_max_hp")
                if 'post_battle_effects' not in result:
                    result['post_battle_effects'] = []
                result['post_battle_effects'].append({
                    'type': 'gain_max_hp',
                    'value': attr_points  # 传递属性点数，由上层转换
                })


            elif effect.effect_type == EffectType.GAIN_RANDOM_ATTR:
                # 刃之魔灵：掠夺随机属性（需要在战斗结束后持久化）
                # 检查今天是否已经触发过
                should_trigger = self._check_blade_daily_random_available(killer)

                if should_trigger:
                    # 预先抽取属性用于显示，持久化时也可使用该字段
                    allowed_attrs = [
                        "attack", "defense", "max_hp", "max_mp", "agility", "luck"
                    ]
                    attr_cn = {
                        "attack": "攻击力",
                        "defense": "防御力",
                        "max_hp": "最大生命值",
                        "max_mp": "最大理智值",
                        "agility": "敏捷",
                        "luck": "运气",
                    }
                    chosen_attr = self.rng.choice(allowed_attrs)
                    val = int(effect.value)
                    result["messages"].append(
                        f"⚔️ {_ktag}掠夺灵魂，{attr_cn.get(chosen_attr, '随机属性')}+{val}（战后结算）"
                    )
                    result["effects_triggered"].append("gain_random_attr")
                    # 标记需要在战后结算中处理（包含已抽取的属性名）
                    if 'post_battle_effects' not in result:
                        result['post_battle_effects'] = []
                    result['post_battle_effects'].append({
                        'type': 'gain_random_attr',
                        'attr': chosen_attr,
                        'value': val
                    })

            elif effect.effect_type == EffectType.GAIN_AGILITY:
                # 夺伞步（归雨）：永久获得敏捷（需要在战斗结束后持久化）
                attr_points = int(effect.value)
                result["messages"].append(f"👣 {_ktag}脚步更轻，敏捷+{attr_points}（战后结算）")
                result["effects_triggered"].append("gain_agility")
                if 'post_battle_effects' not in result:
                    result['post_battle_effects'] = []
                result['post_battle_effects'].append({
                    'type': 'gain_agility',
                    'value': attr_points
                })

            elif effect.effect_type == EffectType.GAIN_ATTACK:
                # 永久获得攻击力（需要在战斗结束后持久化）
                attr_points = int(effect.value)
                result["messages"].append(f"⏱️ {_ktag}攻击力+{attr_points}（战后结算）")
                result["effects_triggered"].append("gain_attack")
                if 'post_battle_effects' not in result:
                    result['post_battle_effects'] = []
                result['post_battle_effects'].append({
                    'type': 'gain_attack',
                    'value': attr_points,
                    'description': effect.description or ""
                })

            elif effect.duration > 0 or effect.duration == -1:
                # 持续性效果（duration=-1 为永久效果）
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

        # 子效果行（缩进显示在攻击消息后）和状态变更消息
        sub_lines = []
        status_lines = []

        attacker_id = attacker.id
        defender_id = defender.id if hasattr(defender, 'id') else "enemy"
        attacker_name = attacker.nickname
        defender_name = defender.nickname if hasattr(defender, 'nickname') else defender.get("name", "敌人")

        # 获取属性修正
        attack_modifier = self.effect_manager.calculate_attribute_modifier(attacker_id, "attack")

        # 计算基础攻击力（优先使用缓存的属性值，包含临时buff）
        attacker_attack = getattr(attacker, '_cached_attack', attacker.attack)
        base_attack = override_base_attack if override_base_attack is not None else int(attacker_attack * (1 + attack_modifier / 100))

        # 检查是否有真伤状态
        has_true_damage = len(self.effect_manager.get_active_effects(attacker_id, EffectType.TRUE_DAMAGE)) > 0
        # 属性面板真伤率（T1词缀等数值型来源）：按概率使本次攻击为真伤
        if not has_true_damage:
            stat_td_rate = _unit_battle_attr(attacker, 'true_damage_rate')
            if stat_td_rate > 0 and self.rng.random() * 100 < stat_td_rate:
                has_true_damage = True
        # 预取"无视类"效果：
        # - IGNORE_SPECIAL（绝魔体质，来自PASSIVE）
        # - IGNORE_DEFENSE（至尊锋刃，ON_ATTACK逐次判定）
        ignore_special_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.IGNORE_SPECIAL)
        ignore_special_ratio = 0.0
        for eff in ignore_special_effects:
            val = float(getattr(eff, 'value', 0))
            ignore_special_ratio += max(0.0, val) / 100.0
        # ON_ATTACK 前置判定，仅提取 IGNORE_DEFENSE，用于本次攻击
        pre_ctx = {"source": "pre_attack", "current_hp": getattr(attacker, 'hp', 0), "max_hp": _effective_max_hp(attacker),
                   "target_hp": getattr(defender, 'hp', 0), "target_max_hp": _effective_max_hp(defender)}
        pre_attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, pre_ctx)
        ignore_defense_ratio = 0.0
        for eff in pre_attack_effects:
            if eff.effect_type == EffectType.IGNORE_DEFENSE:
                val = float(getattr(eff, 'value', 0))
                ignore_defense_ratio += max(0.0, val) / 100.0

        # 检查DEFENSE_PENETRATION持续效果（归雨·伞骨穿）
        defense_pen_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.DEFENSE_PENETRATION)
        defense_pen_ratio = 0.0
        for eff in defense_pen_effects:
            defense_pen_ratio += max(0.0, float(getattr(eff, 'value', 0))) / 100.0
        defense_pen_ratio = min(1.0, defense_pen_ratio)
        # 组合用于护盾/无敌等通用绕过比例
        bypass_fraction = 1.0 - (1.0 - min(1.0, ignore_special_ratio)) * (1.0 - min(1.0, ignore_defense_ratio))

        # 执行基础攻击
        if hasattr(defender, 'defense'):
            # 对玩家 - 需要应用双方的战斗buff
            # 获取双方基础属性(优先使用缓存的战斗属性,包含临时buff)
            attacker_base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(attacker)
            defender_base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(defender)

            # 应用战斗buff
            attacker_attrs = self._get_effective_battle_attributes(attacker_id, attacker_base_attrs)
            defender_attrs = self._get_effective_battle_attributes(defender_id, defender_base_attrs)

            # 使用增强的属性进行攻击判定（真伤在判定内处理）
            attack_result = self._process_pvp_attack(
                attacker, defender, base_attack, is_skill,
                attacker_attrs, defender_attrs, has_true_damage,
                ignore_defense_ratio=defense_pen_ratio,
                ignore_special_ratio=ignore_special_ratio,
                guaranteed_fraction=ignore_defense_ratio,
            )
        else:
            # 对怪物（真伤在判定内处理）
            attack_result = self._process_monster_attack(
                attacker, defender, base_attack, is_skill, has_true_damage,
                ignore_defense_ratio=defense_pen_ratio,
                ignore_special_ratio=ignore_special_ratio,
                guaranteed_fraction=ignore_defense_ratio,
            )

        # 格式化基础攻击消息
        if not attack_result["hit"]:
            _miss_hit_pct = attack_result.get("hit_chance", 0)
            result["messages"].append(f"⚡ {attacker_name}攻击{defender_name}，但被闪避了(命中率{_miss_hit_pct * 100:.0f}%)")

            # 触发闪避效果(防御方)
            dodge_effects = self.effect_manager.check_triggers(defender_id, TriggerType.ON_DODGE, {
                "source": "闪避成功",
                "current_hp": getattr(defender, 'hp', 100),
                "max_hp": _effective_max_hp(defender)
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
        total_damage_from_attack = attack_result["damage"]
        guaranteed_damage = attack_result.get("guaranteed_damage", 0)
        damage = max(0, total_damage_from_attack - guaranteed_damage)
        is_critical = attack_result.get("is_critical", False)
        combo_count = attack_result.get("combo_count", 1)
        result["combo_count"] = combo_count
        # 记录关键标志
        result["is_critical"] = is_critical
        result["is_penetration"] = attack_result.get("is_penetration", False)
        # 标记是否包含必中20%
        has_guaranteed = guaranteed_damage > 0
        # 记录防御减伤后、技能提升前的基础伤害，供战斗日志正确显示"格挡"
        result["pre_boost_damage"] = total_damage_from_attack

        # 检查并应用虎标弹等计数型伤害加成效果
        tiger_bullet_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.TIGER_BULLET)
        for tiger_effect in tiger_bullet_effects:
            # 先应用伤害加成（本次攻击有效）- 基于全部伤害(含必中部分)计算
            total_current = guaranteed_damage + damage
            boost_damage = int(total_current * tiger_effect.value / 100)
            damage += boost_damage
            sub_lines.append(f"  └ 🐯 虎标弹 +{tiger_effect.value:.0f}% (+{boost_damage})")
            # 再消耗次数，判断是否需要触发下一个效果
            if not tiger_effect.consume_trigger():
                # 次数用尽，移除效果并触发下一个效果
                self.effect_manager.remove_effect(attacker_id, tiger_effect)
                status_lines.append(f"🐯 虎标弹效果结束")

                # 触发猛虎标弹
                if tiger_effect.next_effect == "fierce_tiger_bullet":
                    fierce_effect = BattleEffect(
                        effect_type=EffectType.FIERCE_TIGER_BULLET,
                        value=100,  # 造成伤害提高100%
                        duration=0,
                        source=tiger_effect.source,
                        description="猛虎标弹",
                        max_trigger_count=3,
                        next_effect="rigid_qi_heart"
                    )
                    self.effect_manager.add_effect(attacker_id, fierce_effect)
                    status_lines.append(f"🐅 猛虎标弹激活！")

        # 检查并应用猛虎标弹效果
        fierce_tiger_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.FIERCE_TIGER_BULLET)
        for fierce_effect in fierce_tiger_effects:
            # 先应用伤害加成（本次攻击有效）- 基于全部伤害(含必中部分)计算
            total_current = guaranteed_damage + damage
            boost_damage = int(total_current * fierce_effect.value / 100)
            damage += boost_damage
            sub_lines.append(f"  └ 🐅 猛虎标弹 +{fierce_effect.value:.0f}% (+{boost_damage})")
            # 再消耗次数，判断是否需要触发下一个效果
            if not fierce_effect.consume_trigger():
                # 次数用尽，移除效果并触发刚气-心
                self.effect_manager.remove_effect(attacker_id, fierce_effect)
                status_lines.append(f"🐅 猛虎标弹效果结束")

                # 触发刚气-心
                if fierce_effect.next_effect == "rigid_qi_heart":
                    rigid_effect = BattleEffect(
                        effect_type=EffectType.RIGID_QI_HEART,
                        value=60,  # 受到伤害降低60%
                        duration=3,
                        source=fierce_effect.source,
                        description="刚气-心"
                    )
                    self.effect_manager.add_effect(attacker_id, rigid_effect)
                    status_lines.append(f"💪 刚气-心触发！受到伤害降低60%(持续3回合)")

        # 检查攻击者是否有持续性DAMAGE_BOOST效果（如闪避触发的"风刃反击"）
        active_boosts = self.effect_manager.get_active_effects(attacker_id, EffectType.DAMAGE_BOOST)
        if active_boosts and damage > 0:
            total_boost_pct = sum(float(getattr(b, 'value', 0)) for b in active_boosts)
            if total_boost_pct > 0:
                total_current = guaranteed_damage + damage
                boost_damage = int(total_current * total_boost_pct / 100)
                damage += boost_damage
                # 取第一个效果的装备标签用于显示
                boost_tag = active_boosts[0].equip_tag()
                sub_lines.append(f"  └ 💥 {boost_tag}伤害提升 +{total_boost_pct:.0f}% (+{boost_damage})")

        # 检查刚气-心状态，降低造成的伤害
        rigid_qi_effects = self.effect_manager.get_active_effects(attacker_id, EffectType.RIGID_QI_HEART)
        if rigid_qi_effects:
            for rigid_effect in rigid_qi_effects:
                # 刚气-心：造成伤害降低10%
                damage_reduction = int(damage * 10 / 100)
                damage -= damage_reduction
                sub_lines.append(f"  └ 💪 刚气-心自损 -10% (-{damage_reduction})")

        # 检查防御者是否有无敌状态（可被"绝魔体质/至尊锋刃"部分无视）
        invincible_effects = self.effect_manager.get_active_effects(defender_id, EffectType.INVINCIBLE)
        if invincible_effects:
            bypass = 0.0
            if 'bypass_fraction' in locals():
                bypass = min(1.0, max(0.0, bypass_fraction))
            invincible_msg = f"  └ ✨ {defender_name}无敌，"
            if damage > 0:
                if bypass > 0:
                    partial = max(1, int(damage * bypass))
                    invincible_msg += f"锋刃/绝魔部分无视，常规伤害{partial}"
                    damage = partial
                else:
                    invincible_msg += "常规伤害免疫"
                    damage = 0
            else:
                invincible_msg += "常规伤害免疫"
            if guaranteed_damage > 0:
                invincible_msg += f"，必中段{guaranteed_damage}"
            sub_lines.append(invincible_msg)
            if damage == 0 and guaranteed_damage <= 0:
                result["messages"].extend(sub_lines)
                result["messages"].extend(status_lines)
                return result

        # 恐惧状态增伤（联动增强）
        fear_effects = self.effect_manager.get_active_effects(defender_id, EffectType.FEAR)
        if fear_effects:
            fear_bonus = int(damage * 0.2)
            damage += fear_bonus
            sub_lines.append(f"  └ 😱 恐惧增伤 +20% (+{fear_bonus})")

        # 受到伤害减少（DAMAGE_REDUCTION效果，如归雨·伞下、龙刃鞋·龙鳞护足等）
        dmg_reduction_effects = self.effect_manager.get_active_effects(defender_id, EffectType.DAMAGE_REDUCTION)
        total_reduction_pct = 0.0
        for dr_eff in dmg_reduction_effects:
            total_reduction_pct += float(getattr(dr_eff, 'value', 0))
        total_reduction_pct = min(50.0, total_reduction_pct)  # 上限50%减伤
        if total_reduction_pct > 0 and damage > 0:
            reduction_amount = int(damage * total_reduction_pct / 100)
            damage -= reduction_amount
            damage = max(1, damage)  # 至少造成1点伤害
            # 动态显示来源装备名
            dr_tag = dmg_reduction_effects[0].equip_tag() if dmg_reduction_effects else ""
            sub_lines.append(f"  └ ☂️ {dr_tag}减伤 -{total_reduction_pct:.0f}% (-{reduction_amount})")

        # 猛虎标弹：防御者受到伤害降低30%（天退星刀专属）
        fierce_tiger_def_effects = self.effect_manager.get_active_effects(defender_id, EffectType.FIERCE_TIGER_BULLET)
        if fierce_tiger_def_effects and damage > 0:
            for _ in fierce_tiger_def_effects:
                reduction_amount = int(damage * 30 / 100)
                damage -= reduction_amount
                damage = max(1, damage)
                sub_lines.append(f"  └ 🐅 猛虎标弹减伤 -30% (-{reduction_amount})")
                break  # 多个效果只应用一次

        # 刚气-心：防御者受到伤害降低60%（天退星刀专属）
        rigid_qi_def_effects = self.effect_manager.get_active_effects(defender_id, EffectType.RIGID_QI_HEART)
        if rigid_qi_def_effects and damage > 0:
            for rigid_def_effect in rigid_qi_def_effects:
                reduction_amount = int(damage * rigid_def_effect.value / 100)
                damage -= reduction_amount
                damage = max(1, damage)
                sub_lines.append(f"  └ 💪 刚气-心减伤 -{rigid_def_effect.value:.0f}% (-{reduction_amount})")
                break  # 多个效果只应用一次

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
                    sub_lines.append(f"  └ 🛡️ 护盾吸收{absorbed_by_shield} 剩余{shield_effect.shield_value}")
                    break
                else:
                    # 护盾部分吸收
                    absorbed_by_shield += shield_effect.shield_value
                    damage_for_shield -= shield_effect.shield_value
                    sub_lines.append(f"  └ 🛡️ 护盾吸收{shield_effect.shield_value}后破碎")
                    shield_effect.shield_value = 0
                    # 护盾破碎，移除效果
                    self.effect_manager.remove_effect(defender_id, shield_effect)
        # 合并护盾绕过与护盾结算后的伤害
        damage = pre_bypass + damage_for_shield

        # 防御减伤子行（含穿透收益）
        defense_mit = attack_result.get("defense_mitigation")
        if defense_mit and defense_mit.get("blocked", 0) > 0:
            blocked = defense_mit["blocked"]
            flat = defense_mit.get("flat_reduction", 0)
            pct = defense_mit["percent_reduction"] * 100
            pen_benefit = attack_result.get("penetration_benefit", 0)
            pen_ratio = attack_result.get("penetration_ratio", 0)
            mit_desc = f"  └ 🛡️ 防御减伤 -{blocked} (数值{flat} + 比例{pct:.0f}%)"
            if pen_benefit > 0:
                mit_desc += f" | 🗡️穿透{pen_ratio*100:.0f}%减免+{pen_benefit}"
            sub_lines.append(mit_desc)

        # 构建攻击消息（主行只保留攻击+伤害，标签移到子行）
        if is_combo:
            attack_msg = f"  🔄 连击"
        else:
            attack_msg = f"⚔️ {attacker_name}攻击{defender_name}"
            if combo_count > 1 and not is_counter:
                attack_msg += f" 🔄x{combo_count}"

        # 显示实际伤害（扣除护盾后）
        _normal_missed = attack_result.get("normal_missed", False)
        normal_after_mod = damage

        final_damage = guaranteed_damage + damage
        if absorbed_by_shield > 0:
            attack_msg += f" 造成{final_damage}伤害(护盾吸收{absorbed_by_shield})"
        else:
            attack_msg += f" 造成{final_damage}伤害"

        # 标签子行（真伤/必中/暴击等，穿透已合并到防御减伤行）
        tags = []
        if has_true_damage:
            tags.append("🔥真伤")
        if has_guaranteed:
            tags.append("🎯必中20%")
        if is_critical:
            crit_mult = attack_result.get("crit_multiplier", 1.5)
            tags.append(f"💥暴击x{crit_mult:.1f}")
        if tags:
            sub_lines.insert(0, f"  └ {' | '.join(tags)}")

        # 拆分信息改为子行（显示必中/常规拆分及等效命中率）
        if has_guaranteed:
            _hit_pct = attack_result.get("hit_chance", 0)
            _nd_text = "被闪避" if _normal_missed else str(normal_after_mod)
            sub_lines.append(f"  └ 📊 必中:{guaranteed_damage} + 常规:{_nd_text} (命中率{_hit_pct * 100:.0f}%)")

        # 消息组装：攻击主消息在前，子效果行紧随，状态变更最后
        result["messages"].append(attack_msg)
        result["messages"].extend(sub_lines)
        result["messages"].extend(status_lines)
        result["total_damage"] = final_damage
        damage = final_damage

        # 触发攻击时效果
        context = {
            "source": attacker_name,
            "damage": damage,
            "is_critical": is_critical,
            "current_hp": attacker.hp,
            "max_hp": _effective_max_hp(attacker),
            "target_hp": getattr(defender, 'hp', 0),
            "target_max_hp": _effective_max_hp(defender),
        }

        attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, context)

        # 触发命中效果（命中后触发）
        hit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_HIT, context)
        attack_effects.extend(hit_effects)

        # 如果暴击，触发暴击效果
        if is_critical:
            crit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_CRITICAL, context)
            attack_effects.extend(crit_effects)

        # 低血量触发效果（每次攻击时检查自身血量）
        low_hp_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.LOW_HP, context)
        attack_effects.extend(low_hp_effects)

        # 属性面板吸血率（T1词缀/宠物饰品等数值型来源，与触发型吸血叠加）
        stat_lifesteal = _unit_battle_attr(attacker, 'lifesteal_rate')
        if stat_lifesteal > 0 and damage > 0:
            stat_ls_amount = int(damage * stat_lifesteal / 100)
            if stat_ls_amount > 0:
                result["hp_restored"] += stat_ls_amount
                result["messages"].append(f"🧡 吸血{stat_ls_amount}HP")
                result["effects_triggered"].append("lifesteal")

        # 处理触发的效果
        for effect in attack_effects:
            _tag = effect.equip_tag()  # 装备来源标签
            # 立即生效的效果
            if effect.effect_type == EffectType.LIFESTEAL:
                lifesteal_amount = int(damage * effect.value / 100)
                # 暴击时吸血加强（联动增强）
                if is_critical:
                    lifesteal_amount = int(lifesteal_amount * 1.5)
                # 实际恢复HP（不超过最大值）
                result["hp_restored"] += lifesteal_amount
                result["messages"].append(f"🧡 {_tag}吸血{lifesteal_amount}HP{'(暴击加强)' if is_critical else ''}")
                result["effects_triggered"].append("lifesteal")

            elif effect.effect_type == EffectType.HEAL:
                # 立即回血效果
                heal_amount = int(_effective_max_hp(attacker) * effect.value / 100) if effect.is_percentage else int(effect.value)
                result["hp_restored"] += heal_amount
                result["messages"].append(f"💚 {_tag}回复{heal_amount}HP")

                result["effects_triggered"].append("heal")

            elif effect.effect_type == EffectType.FEAR:
                # 对敌人施加恐惧效果
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(f"😱 {_tag}{defender_name}被恐惧{effect.duration}回合")
                result["effects_triggered"].append("fear")

            elif effect.effect_type == EffectType.TRUE_DAMAGE:
                # 真伤状态：添加到攻击者身上
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(f"🔥 {_tag}进入真伤状态！(持续{effect.duration}回合)")
                result["effects_triggered"].append("true_damage")

            elif effect.effect_type == EffectType.DAMAGE_BOOST:
                # 伤害提升效果（立即生效）
                boost_damage = int(damage * effect.value / 100)
                result["total_damage"] += boost_damage
                result["messages"].append(f"💥 {_tag}伤害提升！额外造成{boost_damage}伤害")
                result["effects_triggered"].append("damage_boost")

            elif effect.effect_type == EffectType.DEFENSE_PENETRATION:
                # 伞骨穿：无视防御持续效果，添加到攻击者身上
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(f"☂️ {_tag}无视敌人{effect.value:.0f}%防御(持续{effect.duration}回合)")
                result["effects_triggered"].append("defense_penetration")

            elif effect.duration > 0 or effect.duration == -1:
                # 其他持续性效果（duration=-1 为永久效果）
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(format_effect_message(effect, attacker_name))
                result["effects_triggered"].append(effect.effect_type.value)

        # 定身率：命中后有概率触发恐惧（无法行动1回合）
        immobilize_rate = _unit_battle_attr(attacker, 'immobilize_rate')
        if immobilize_rate > 0 and self.rng.random() * 100 < immobilize_rate:
            imm_effect = BattleEffect(
                effect_type=EffectType.FEAR,
                value=0,
                duration=1,
                source="定身率",
                source_equipment="定身率",
            )
            self.effect_manager.add_effect(defender_id, imm_effect)
            result["messages"].append(format_effect_message(imm_effect, defender_name))
            result["effects_triggered"].append("fear")

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
            "is_critical": is_critical,
            "current_hp": getattr(defender, 'hp', 100),
            "max_hp": _effective_max_hp(defender),
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
            _dtag = effect.equip_tag()  # 防御方装备来源标签
            if effect.effect_type == EffectType.REFLECT_DEATH:
                # 镜怨体质：反射死亡(可被"绝魔体质"按概率压制)
                # 切磋模式下不触发镜怨体质（切磋不算死斗）
                if self.is_sparring:
                    continue
                # 仅当防御方是被动应战方时触发（防御方不是战斗发起者）
                # 如果battle_initiator_id为None（PvE等），不限制触发
                defender_is_initiator = (
                    self.battle_initiator_id is not None
                    and hasattr(defender, 'id')
                    and str(defender.id) == str(self.battle_initiator_id)
                )
                if defender_is_initiator:
                    # 防御方是战斗发起者（主动攻击别人），镜怨体质不触发
                    continue

                apply_instant_death = True
                if 'ignore_special_ratio' in locals() and ignore_special_ratio > 0:
                    # 将"必死"视为100%概率效果，被忽视50%后 -> 仅有(1-忽视)的概率生效
                    if self.rng.random() < min(1.0, ignore_special_ratio):
                        apply_instant_death = False
                        result["messages"].append(f"🪞 {_dtag}镜怨体质被斩龙闪压制，必死效果本次未触发")
                if apply_instant_death:
                    result["attacker_instant_death"] = True
                    result["messages"].append(f"🪞 {_dtag}镜怨体质！{attacker_name}的攻击被镜像反噬，灵魂瞬间破碎——直接死亡！")
                    result["messages"].append("💀 镜中之人，以己之力斩己之形。")
                    result["effects_triggered"].append("reflect_death")
                    # 标记攻击者需要立即死亡
                    if hasattr(attacker, 'hp'):
                        attacker.hp = 0

            elif effect.effect_type == EffectType.REFLECT:
                # 反弹伤害（实际扣血），可被"绝魔体质"部分无视
                reflect_damage = int(damage * effect.value / 100)
                reduce_factor = 1.0
                if 'ignore_special_ratio' in locals() and ignore_special_ratio > 0:
                    reduce_factor = max(0.0, 1.0 - min(1.0, ignore_special_ratio))
                reflect_damage = int(reflect_damage * reduce_factor)
                if reflect_damage > 0:
                    result["reflect_damage"] = result.get("reflect_damage", 0) + reflect_damage
                    result["messages"].append(f"↩️ {_dtag}{defender_name}反弹{reflect_damage}伤害给{attacker_name}")
                    result["effects_triggered"].append("reflect")

            elif effect.effect_type == EffectType.SHIELD:
                # 护盾效果
                shield_value = int(_effective_max_hp(defender) * effect.value / 100) if effect.is_percentage else int(effect.value)
                self.effect_manager.add_effect(defender_id, effect)
                # 将护盾值存储在effect中
                effect.shield_value = shield_value
                result["messages"].append(f"🛡️ {_dtag}{defender_name}获得{shield_value}点护盾")
                result["effects_triggered"].append("shield")

            elif effect.effect_type == EffectType.HEAL:
                # 立即回血
                heal_amount = int(_effective_max_hp(defender) * effect.value / 100) if effect.is_percentage else int(effect.value)
                result["defender_hp_restored"] = result.get("defender_hp_restored", 0) + heal_amount
                result["messages"].append(f"💚 {_dtag}{defender_name}回复{heal_amount}HP")
                result["effects_triggered"].append("heal")

            elif effect.effect_type == EffectType.FEAR:
                # on_attacked 触发的恐惧应施加给攻击者（"使敌人恐惧"），而非自己
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(format_effect_message(effect, attacker_name))
                result["effects_triggered"].append("fear")

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
        # 属性面板真伤率（T1词缀等数值型来源）：按概率使本次攻击为真伤
        if not has_true_damage:
            stat_td_rate = _unit_battle_attr(attacker, 'true_damage_rate')
            if stat_td_rate > 0 and self.rng.random() * 100 < stat_td_rate:
                has_true_damage = True

        # 执行基础攻击
        if hasattr(defender, 'defense'):
            # 获取双方基础属性(优先使用缓存的战斗属性,包含临时buff)
            attacker_base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(attacker)
            defender_base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(defender)

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
        # 检查是否包含必中20%
        has_guaranteed = False
        for eff_tag in attack_result.get("effects", []):
            if isinstance(eff_tag, str) and "GUARANTEED_20%" in eff_tag:
                has_guaranteed = True
                break

        # 构建攻击消息（主行只保留攻击+伤害，标签移到子行）
        attack_msg = f"  🔄 连击第{combo_number}次 造成{damage}伤害"
        result["messages"].append(attack_msg)
        combo_tags = []
        if has_true_damage:
            combo_tags.append("🔥真伤")
        if has_guaranteed:
            combo_tags.append("🎯必中20%")
        if is_critical:
            crit_mult = attack_result.get("crit_multiplier", 1.5)
            combo_tags.append(f"💥暴击x{crit_mult:.1f}")
        if combo_tags:
            result["messages"].append(f"    └ {' | '.join(combo_tags)}")
        result["total_damage"] = damage

        # 触发攻击时效果
        context = {
            "source": attacker_name,
            "damage": damage,
            "is_critical": is_critical,
            "current_hp": attacker.hp,
            "max_hp": _effective_max_hp(attacker),
            "target_hp": getattr(defender, 'hp', 0),
            "target_max_hp": _effective_max_hp(defender),
        }

        attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, context)

        # 触发命中效果（连击也触发ON_HIT，联动增强）
        hit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_HIT, context)
        attack_effects.extend(hit_effects)

        # 如果暴击，触发暴击效果
        if is_critical:
            crit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_CRITICAL, context)
            attack_effects.extend(crit_effects)

        # 属性面板吸血率（T1词缀/宠物饰品等数值型来源，与触发型吸血叠加）
        stat_lifesteal = _unit_battle_attr(attacker, 'lifesteal_rate')
        if stat_lifesteal > 0 and damage > 0:
            stat_ls_amount = int(damage * stat_lifesteal / 100)
            if stat_ls_amount > 0:
                result["hp_restored"] += stat_ls_amount
                result["messages"].append(f"    🧡 吸血{stat_ls_amount}HP")
                result["effects_triggered"].append("lifesteal")

        # 处理触发的效果
        for effect in attack_effects:
            _ctag = effect.equip_tag()  # 装备来源标签
            if effect.effect_type == EffectType.LIFESTEAL:
                lifesteal_amount = int(damage * effect.value / 100)
                # 暴击时吸血加强（联动增强）
                if is_critical:
                    lifesteal_amount = int(lifesteal_amount * 1.5)
                result["hp_restored"] += lifesteal_amount
                result["messages"].append(f"    🧡 {_ctag}吸血{lifesteal_amount}HP{'(暴击加强)' if is_critical else ''}")
                result["effects_triggered"].append("lifesteal")

            elif effect.effect_type == EffectType.TRUE_DAMAGE:
                # 真伤状态：添加到攻击者身上
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(f"    🔥 {_ctag}进入真伤状态！(持续{effect.duration}回合)")
                result["effects_triggered"].append("true_damage")

            elif effect.effect_type == EffectType.FEAR:
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(f"    😱 {_ctag}{defender_name}被恐惧{effect.duration}回合")
                result["effects_triggered"].append("fear")

            elif effect.effect_type == EffectType.DAMAGE_BOOST:
                boost_damage = int(damage * effect.value / 100)
                result["total_damage"] += boost_damage
                result["messages"].append(f"    💥 {_ctag}伤害提升！额外造成{boost_damage}伤害")
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
                           ignore_special_ratio: float = 0.0,
                           guaranteed_fraction: float = 0.0) -> Dict:
        """处理PVP攻击（使用已应用buff的属性）

        规则调整：
        - guaranteed_fraction 部分的伤害"必中"（绕过命中判定），且直接结算为最终伤害，
          不参与暴击、连击、额外穿透或任何形式的减伤。
        - 其余 (1 - guaranteed_fraction) 部分按原有流程进行完整判定。
        """
        result = {
            "hit": False,            # 是否有任何伤害命中
            "damage": 0,
            "is_critical": False,
            "is_penetration": False,
            "combo_count": 1,
            "effects": []
        }

        gf = max(0.0, min(1.0, float(guaranteed_fraction)))
        guaranteed_base = int(base_damage * gf)
        normal_base = max(0, base_damage - guaranteed_base)

        # 1) 命中判定（仅对 normal 部分生效）
        # 闪避率已由 apply_ignore_special_debuff 在开战时按 IGNORE_SPECIAL 比例削减，
        # 此处仅额外应用 DEFENSE_PENETRATION 的闪避穿透。
        adjusted_dodge = defender_attrs.get("dodge_rate", 0)
        adjusted_dodge = adjusted_dodge * (1 - max(0.0, min(1.0, ignore_defense_ratio)))
        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            attacker_attrs.get("accuracy_rate", 0), adjusted_dodge
        )
        normal_hit = True
        if normal_base > 0 and self.rng.random() > hit_chance:
            normal_hit = False
            result["effects"].append("被闪避(80%)")

        if guaranteed_base > 0 or normal_hit:
            result["hit"] = True

        result["hit_chance"] = hit_chance

        # 2) 穿透判定（仅对 normal 部分，真伤跳过）
        penetration_ratio = 0.0
        if normal_hit and normal_base > 0 and not has_true_damage:
            penetration_ratio = BattleAttributeCalculator.get_penetration_ratio(
                attacker_attrs.get("penetration_rate", 0)
            )
            if penetration_ratio > 0:
                result["is_penetration"] = True
                result["penetration_ratio"] = penetration_ratio

        # 3) 暴击判定（仅对 normal 部分）
        is_critical = False
        if normal_hit and normal_base > 0:
            crit_rate = attacker_attrs["skill_crit_rate"] if is_skill else attacker_attrs["critical_rate"]
            defender_anti_crit_rate = defender_attrs["anti_crit_rate"]
            effective_crit_rate = max(0, crit_rate - defender_anti_crit_rate)
            is_critical = BattleAttributeCalculator.roll_critical_hit(effective_crit_rate, self.rng)
            result["is_critical"] = is_critical

        # 3.5) 连击判定（仅普攻且 normal 命中时，考虑防御方抗连击率）
        if not is_skill and normal_hit and normal_base > 0:
            effective_combo = max(0, attacker_attrs.get("combo_rate", 0) - defender_attrs.get("anti_combo_rate", 0))
            result["combo_count"] = BattleAttributeCalculator.roll_combo_attack(
                effective_combo, self.rng
            )

        # 4) 计算防御修正(优先使用缓存属性,包含临时buff)
        defender_id = defender.id if hasattr(defender, 'id') else "enemy"
        defense_modifier = self.effect_manager.calculate_attribute_modifier(defender_id, "defense")
        defender_defense = getattr(defender, '_cached_defense', defender.defense)
        effective_defense = int(defender_defense * (1 + defense_modifier / 100))

        from ..utils import apply_defense_mitigation

        # 5) guaranteed 部分：直接结算为最终伤害，不参与任何减伤/暴击/穿透
        guaranteed_final = guaranteed_base
        if guaranteed_final > 0:
            result["effects"].append("GUARANTEED_20%")

        # 6) 再计算 normal 部分
        normal_final = 0
        if normal_hit and normal_base > 0:
            dmg = normal_base
            if is_critical:
                crit_power = max(0, attacker_attrs["critical_power"] - defender_attrs.get("anti_crit_rate", 0))
                crit_multiplier = 1.5 + (crit_power * 0.1)
                dmg = BattleAttributeCalculator.calculate_critical_damage(dmg, crit_power)
                result["crit_multiplier"] = crit_multiplier
                result["effects"].append("CRITICAL")
            if has_true_damage:
                # 检查防御方是否有绝魔体质（免疫50%真伤）
                if ignore_special_ratio > 0:
                    # 50%真伤 + 50%普通伤害（受防御减伤）
                    true_damage_part = int(dmg * 0.5)
                    normal_damage_part = dmg - true_damage_part
                    # 普通伤害部分受防御减伤
                    if penetration_ratio > 0:
                        mit = apply_defense_mitigation(normal_damage_part, effective_defense, penetration_ratio)
                        mit_no_pen = apply_defense_mitigation(normal_damage_part, effective_defense)
                        result["penetration_benefit"] = mit_no_pen["blocked"] - mit["blocked"]
                        dmg = true_damage_part + mit["final_damage"]
                        result["effects"].append("TRUE_DAMAGE(绝魔免疫50%)+PENETRATION")
                    else:
                        mit = apply_defense_mitigation(normal_damage_part, effective_defense)
                        dmg = true_damage_part + mit["final_damage"]
                        result["effects"].append("TRUE_DAMAGE(绝魔免疫50%)")
                    result["defense_mitigation"] = {
                        "blocked": mit["blocked"],
                        "flat_reduction": mit["flat_reduction"],
                        "percent_reduction": mit["percent_reduction"],
                    }
                else:
                    result["effects"].append("TRUE_DAMAGE")
            else:
                if penetration_ratio > 0:
                    mit = apply_defense_mitigation(dmg, effective_defense, penetration_ratio)
                    mit_no_pen = apply_defense_mitigation(dmg, effective_defense)
                    result["penetration_benefit"] = mit_no_pen["blocked"] - mit["blocked"]
                    dmg = mit["final_damage"]
                    result["effects"].append("PENETRATION")
                else:
                    mit = apply_defense_mitigation(dmg, effective_defense)
                    dmg = mit["final_damage"]
                result["defense_mitigation"] = {
                    "blocked": mit["blocked"],
                    "flat_reduction": mit["flat_reduction"],
                    "percent_reduction": mit["percent_reduction"],
                }
            normal_final = dmg

        total = guaranteed_final + normal_final
        result["damage"] = total
        result["total_damage"] = total
        # 暴露拆分信息，供上层日志与PVP/副本共用
        result["guaranteed_damage"] = guaranteed_final
        result["normal_damage"] = normal_final
        result["normal_missed"] = (normal_base > 0 and not normal_hit)
        return result

    def _process_monster_attack(self, attacker: Player, monster_stats: Dict,
                               base_damage: int, is_skill: bool, has_true_damage: bool = False,
                               ignore_defense_ratio: float = 0.0,
                               ignore_special_ratio: float = 0.0,
                               guaranteed_fraction: float = 0.0) -> Dict:
        """
        简化的对怪攻击判定，支持固定比例伤害必中（直接结算最终伤害，不参与命中/暴击/穿透/减伤），
        其余部分走常规判定。
        """
        # 基础与buff（优先使用开战预计算缓存，含临时buff/宠物/词缀）
        base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(attacker)
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

        gf = max(0.0, min(1.0, float(guaranteed_fraction)))
        guaranteed_base = int(base_damage * gf)
        normal_base = max(0, base_damage - guaranteed_base)

        # 命中（仅影响 normal 部分）
        monster_dodge_rate = 0.0
        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            attacker_attrs["accuracy_rate"], monster_dodge_rate
        )
        normal_hit = True
        if normal_base > 0 and self.rng.random() > hit_chance:
            normal_hit = False
            result["effects"].append("被闪避(80%)")

        if guaranteed_base > 0 or normal_hit:
            result["hit"] = True

        result["hit_chance"] = hit_chance

        # 穿透（仅 normal 部分；真伤跳过）
        penetration_ratio = 0.0
        if normal_hit and normal_base > 0 and not has_true_damage:
            penetration_ratio = BattleAttributeCalculator.get_penetration_ratio(
                attacker_attrs.get("penetration_rate", 0)
            )
            if penetration_ratio > 0:
                result["is_penetration"] = True
                result["penetration_ratio"] = penetration_ratio

        # 暴击（仅 normal 部分）
        is_critical = False
        if normal_hit and normal_base > 0:
            crit_rate = attacker_attrs["skill_crit_rate"] if is_skill else attacker_attrs["critical_rate"]
            monster_anti_crit_rate = monster_stats.get("anti_crit_rate", 0)
            effective_crit_rate = max(0, crit_rate - monster_anti_crit_rate)
            is_critical = BattleAttributeCalculator.roll_critical_hit(effective_crit_rate, self.rng)
            result["is_critical"] = is_critical

        # 连击判定（仅普攻且 normal 命中时，考虑怪物抗连击率）
        if not is_skill and normal_hit and normal_base > 0:
            effective_combo = max(0, attacker_attrs.get("combo_rate", 0) - monster_stats.get("anti_combo_rate", 0))
            result["combo_count"] = BattleAttributeCalculator.roll_combo_attack(
                effective_combo, self.rng
            )

        from ..utils import apply_defense_mitigation
        monster_defense = monster_stats.get("defense", 0)

        # guaranteed 部分：直接结算为最终伤害，不参与任何减伤/暴击/穿透
        guaranteed_final = guaranteed_base
        if guaranteed_final > 0:
            result["effects"].append("GUARANTEED_20%")

        # normal 部分
        normal_final = 0
        if normal_hit and normal_base > 0:
            dmg = normal_base
            if is_critical:
                crit_power = max(0, attacker_attrs["critical_power"] - monster_stats.get("anti_crit_rate", 0))
                crit_multiplier = 1.5 + (crit_power * 0.1)
                dmg = BattleAttributeCalculator.calculate_critical_damage(dmg, crit_power)
                result["crit_multiplier"] = crit_multiplier
                result["effects"].append("CRITICAL")
            if has_true_damage:
                result["effects"].append("TRUE_DAMAGE")
            else:
                if penetration_ratio > 0:
                    mit = apply_defense_mitigation(dmg, monster_defense, penetration_ratio)
                    mit_no_pen = apply_defense_mitigation(dmg, monster_defense)
                    result["penetration_benefit"] = mit_no_pen["blocked"] - mit["blocked"]
                    dmg = mit["final_damage"]
                    result["effects"].append("PENETRATION")
                else:
                    mit = apply_defense_mitigation(dmg, monster_defense)
                    dmg = mit["final_damage"]
                result["defense_mitigation"] = {
                    "blocked": mit["blocked"],
                    "flat_reduction": mit["flat_reduction"],
                    "percent_reduction": mit["percent_reduction"],
                }
            normal_final = dmg

        total = guaranteed_final + normal_final
        result["damage"] = total
        result["total_damage"] = total
        # 暴露拆分信息，供上层日志与PVP/副本共用
        result["guaranteed_damage"] = guaranteed_final
        result["normal_damage"] = normal_final
        result["normal_missed"] = (normal_base > 0 and not normal_hit)
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
        # 获取防御者的有效属性(优先使用缓存的战斗属性,包含临时buff)
        defender_base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(defender)
        defender_id = defender.id
        defender_attrs = self._get_effective_battle_attributes(defender_id, defender_base_attrs)

        # 获取攻击者的有效属性（用于抗反击率判定和后续反击伤害计算）
        attacker_base_attrs = BattleAttributeCalculator.effective_attrs_in_battle(attacker)
        attacker_id = attacker.id if hasattr(attacker, 'id') else "enemy"
        attacker_attrs = self._get_effective_battle_attributes(attacker_id, attacker_base_attrs)

        # 判定是否触发反击（考虑攻击方抗反击率）
        effective_counter = max(0, defender_attrs["counter_rate"] - attacker_attrs.get("anti_counter_rate", 0))
        counter_triggered = BattleAttributeCalculator.roll_counter_attack(
            effective_counter, self.rng
        )

        if not counter_triggered:
            return None

        # 触发反击，执行一次简化的攻击
        # 反击伤害为防御者攻击力的50%（含临时buff）
        counter_attack = int(getattr(defender, '_cached_attack', defender.attack) * 0.5)

        # 执行反击攻击判定
        attack_result = self._process_pvp_attack(
            defender, attacker, counter_attack, False,
            defender_attrs, attacker_attrs
        )
        return attack_result

    # ==================== 绝魔体质：无视特殊属性 ====================

    # 需要削减的9种特殊战斗属性
    _IGNORE_SPECIAL_ATTRS = [
        "critical_rate", "critical_power", "combo_rate", "counter_rate",
        "dodge_rate", "accuracy_rate", "skill_crit_rate",
        "penetration_rate", "anti_crit_rate",
        "anti_combo_rate", "anti_counter_rate",
    ]

    def apply_ignore_special_debuff(self, holder_id: str, target: Any, target_id: str):
        """应用绝魔体质：将对手的特殊属性按 ignore_special 比例削减

        在战斗开始时调用。拥有 IGNORE_SPECIAL 被动的一方，会使对方的 9 种
        特殊战斗属性（暴击率/暴击伤害/连击率/反击率/闪避率/命中率/灵爆率/穿透率/抗暴率）
        按比例削弱，从而在整场战斗中持续生效。战后通过 reset_temp_bonuses 回退。
        """
        ignore_effects = self.effect_manager.get_active_effects(holder_id, EffectType.IGNORE_SPECIAL)
        ratio = 0.0
        for eff in ignore_effects:
            ratio += max(0.0, float(getattr(eff, 'value', 0))) / 100.0
        ratio = min(1.0, ratio)
        if ratio <= 0:
            return

        # 避免重复削减（同一 target 只削减一次）
        if target_id in self._temp_ignore_special_debuff:
            return

        originals: Dict[str, float] = {}
        is_dict = isinstance(target, dict)

        for attr in self._IGNORE_SPECIAL_ATTRS:
            if is_dict:
                old_val = float(target.get(attr, 0))
            elif hasattr(target, attr):
                old_val = float(getattr(target, attr, 0))
            else:
                continue

            if old_val <= 0:
                continue

            new_val = old_val * (1.0 - ratio)
            if is_dict:
                target[attr] = new_val
            else:
                self._sync_unit_attr(target, attr, new_val)
            originals[attr] = old_val

        if originals:
            self._temp_ignore_special_debuff[target_id] = originals
            target_name = (target.get("name", "敌人") if is_dict
                           else getattr(target, 'nickname', '敌人'))
            self.battle_log.append(
                f"🔮 绝魔体质：{target_name}的特殊属性被削弱{ratio * 100:.0f}%"
            )

    @staticmethod
    def _sync_unit_attr(unit: Any, attr_name: str, value: float) -> None:
        """设置单位属性，并同步更新战斗属性缓存。

        临时属性修改（如诡面骰骰子buff）需要同时反映到 _cached_battle_attrs，
        否则战斗中每次攻击判定用缓存覆盖实时值时，修改会被悄无声息地丢弃。

        缓存镜像写入时应用 ATTRIBUTE_CAPS 上限（仅对上限表中明确列出的属性），
        防止骰子buff等临时修改把连击/反击等顶破战斗上限。
        """
        setattr(unit, attr_name, value)
        cached = getattr(unit, '_cached_battle_attrs', None)
        if isinstance(cached, dict) and attr_name in cached:
            cap = BattleAttributeCalculator.ATTRIBUTE_CAPS.get(attr_name)
            if cap is not None:
                cached[attr_name] = max(0.0, min(float(value), float(cap)))
            else:
                cached[attr_name] = value

    def reset_temp_bonuses(self, unit: Any):
        """回退首回合临时增加的最大生命值等（如灵影体质）"""
        try:
            unit_id = unit.id if hasattr(unit, 'id') else None
        except Exception:
            unit_id = None
        if not unit_id:
            return
        # 回退首回合由理智转生命（HP_FROM_MP）
        bonus_hp = self._temp_hp_from_mp.pop(unit_id, 0)
        if bonus_hp > 0 and hasattr(unit, 'max_hp'):
            old_max = unit.max_hp
            new_max = max(1, old_max - bonus_hp)
            if hasattr(unit, 'hp') and old_max > 0:
                ratio = unit.hp / float(old_max)
            else:
                ratio = 0.0
            unit.max_hp = new_max
            # 同步回退开战预计算缓存
            cached_max = getattr(unit, '_cached_max_hp', None)
            if cached_max is not None:
                unit._cached_max_hp = max(1, int(cached_max) - bonus_hp)
            if hasattr(unit, 'hp'):
                unit.hp = int(max(0, min(new_max, ratio * new_max)))
        # 回退首回合由生命转理智（MP_FROM_HP）
        bonus_mp = self._temp_mp_from_hp.pop(unit_id, 0) if hasattr(self, '_temp_mp_from_hp') else 0
        if bonus_mp > 0 and hasattr(unit, 'max_mp'):
            old_max_mp = unit.max_mp
            new_max_mp = max(1, old_max_mp - bonus_mp)
            if hasattr(unit, 'mp') and old_max_mp > 0:
                ratio_mp = unit.mp / float(old_max_mp)
            else:
                ratio_mp = 0.0
            unit.max_mp = new_max_mp
            if hasattr(unit, 'mp'):
                unit.mp = int(max(0, min(new_max_mp, ratio_mp * new_max_mp)))
        # 回退绝魔体质对特殊属性的削减（IGNORE_SPECIAL）- 必须在骰子buff之前还原
        # 原因：IGNORE_SPECIAL 记录的是被削减前的值（可能是骰子加成后的中间值），
        # 若先还原骰子buff（→原始值），再还原IGNORE_SPECIAL（→中间值），会覆盖正确结果。
        # 正确顺序是逆应用顺序：先撤销IGNORE_SPECIAL，再撤销骰子buff。
        ignore_debuff = self._temp_ignore_special_debuff.pop(unit_id, None) if hasattr(self, '_temp_ignore_special_debuff') else None
        if ignore_debuff:
            is_dict = isinstance(unit, dict)
            for attr, original_value in ignore_debuff.items():
                if is_dict:
                    unit[attr] = original_value
                elif hasattr(unit, attr):
                    self._sync_unit_attr(unit, attr, original_value)
        # 回退骰子buff临时属性（诡面骰·骰相·乱）- 独立异常保护，确保一定执行
        # 最后还原，保证骰子buff的原始值（应用前的真实DB值）是最终写入的值
        try:
            dice_info = self._temp_dice_buff.pop(unit_id, None) if hasattr(self, '_temp_dice_buff') else None
            if dice_info:
                attr_name, original_value = dice_info
                if hasattr(unit, attr_name):
                    self._sync_unit_attr(unit, attr_name, original_value)
        except Exception:
            pass

    def get_battle_log(self) -> List[str]:
        """获取战斗日志"""
        return self.battle_log.copy()

    def format_battle_summary(self) -> str:
        """格式化战斗摘要"""
        return "\n".join(self.battle_log)
