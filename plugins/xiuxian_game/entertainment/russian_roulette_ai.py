"""
恶魔轮盘 PvE AI 决策引擎
基于已知信息做出最优决策，不偷看弹仓
"""
import json
import random
from typing import Optional, List, Tuple
from .russian_roulette_core import RussianRouletteCore, ItemType


# ==================== 隐藏透视机制 ====================
# AI 有概率"直觉感知"当前弹药，概率随加倍次数递增
# 对玩家完全不可见，只影响 ai_known_bullet 字段

_ENABLE_HIDDEN_PEEK = False  # 默认关闭“透视”作弊
_PEEK_BASE_CHANCE = 0.20       # 基础透视概率 20%
_PEEK_PER_DOUBLE = 0.10        # 每次加倍增加 10%
_PEEK_MAX_CHANCE = 0.65         # 最高 65%
_PEEK_BLANK_USE_RATE = 0.85    # 透视到空弹时使用信息的概率（偶尔"忽略"以掩饰）
_PEEK_LIVE_USE_RATE = 0.95     # 透视到实弹时使用信息的概率


def _maybe_peek_bullet(session_data: dict) -> None:
    """
    AI 隐藏透视：有概率直接获知当前弹药类型
    - 对玩家完全不可见（不产生任何消息）
    - 概率随 double_count 递增
    - 偶尔故意"忽略"透视结果以降低可疑度
    """
    if not _ENABLE_HIDDEN_PEEK:
        return

    # 如果已经知道当前弹药，不需要透视
    if session_data.get("ai_known_bullet") is not None:
        return

    double_count = session_data.get("double_count", 0)
    peek_chance = min(_PEEK_BASE_CHANCE + double_count * _PEEK_PER_DOUBLE, _PEEK_MAX_CHANCE)

    if random.random() >= peek_chance:
        return  # 未触发透视

    # 透视成功 - 偷看当前弹药
    gs = session_data["game_state"]
    bullets = json.loads(gs["bullets"])
    current_index = gs["current_bullet_index"]

    if current_index >= len(bullets):
        return  # 弹仓已空

    actual_bullet = bullets[current_index]

    # 偶尔故意"忽略"透视结果，避免AI表现过于完美
    use_rate = _PEEK_LIVE_USE_RATE if actual_bullet else _PEEK_BLANK_USE_RATE
    if random.random() < use_rate:
        session_data["ai_known_bullet"] = actual_bullet


class AIAction:
    """AI 动作"""
    def __init__(self, action_type: str, target: str = None, item: str = None, steal_item: str = None):
        self.action_type = action_type  # "shoot", "use_item"
        self.target = target  # "self" or "opponent" (for shoot)
        self.item = item  # ItemType value (for use_item)
        self.steal_item = steal_item  # target item for adrenaline


def _get_bullet_probability(session_data: dict) -> float:
    """
    计算当前弹药为实弹的概率（基于公开信息）
    返回实弹概率 0.0 ~ 1.0
    """
    bc = session_data["bullet_counts"]
    remaining_live = bc["total_live"] - bc["fired_live"]
    remaining_blank = bc["total_blank"] - bc["fired_blank"]
    remaining_total = remaining_live + remaining_blank
    if remaining_total <= 0:
        return 0.5
    return remaining_live / remaining_total


def _get_ai_items(session_data: dict) -> List[str]:
    """获取 AI 当前道具列表"""
    gs = session_data["game_state"]
    return json.loads(gs.get("ai_items", "[]"))


def _get_player_items(session_data: dict) -> List[str]:
    """获取玩家当前道具列表"""
    gs = session_data["game_state"]
    return json.loads(gs.get("player_items", "[]"))


def _has_item(items: list, item_type: ItemType) -> bool:
    """检查道具列表中是否有指定道具"""
    return item_type.value in items


def _sync_phone_knowledge(session_data: dict) -> None:
    """
    同步 AI 电话情报到当前子弹认知。
    """
    phone_info = session_data.get("ai_known_phone")
    if not phone_info:
        return

    gs = session_data["game_state"]
    current_index = gs.get("current_bullet_index", 0)

    absolute_index = phone_info.get("absolute_index")
    if absolute_index is None:
        relative_pos = phone_info.get("bullet_position")
        if not isinstance(relative_pos, int) or relative_pos <= 0:
            session_data["ai_known_phone"] = None
            return
        absolute_index = current_index + relative_pos - 1
        phone_info["absolute_index"] = absolute_index
        session_data["ai_known_phone"] = phone_info

    if absolute_index < current_index:
        session_data["ai_known_phone"] = None
        return

    if absolute_index == current_index:
        session_data["ai_known_bullet"] = phone_info.get("is_live")


def _get_phone_relative_position(session_data: dict) -> Optional[int]:
    """返回电话情报相对当前位置（1=当前弹位）。"""
    phone_info = session_data.get("ai_known_phone")
    if not phone_info:
        return None

    gs = session_data["game_state"]
    current_index = gs.get("current_bullet_index", 0)
    absolute_index = phone_info.get("absolute_index")
    if absolute_index is None:
        return None
    return absolute_index - current_index + 1


def _ensure_knowledge_consistency(session_data: dict) -> None:
    """
    保证 AI 侧缓存情报与 game_state 一致。
    特别处理：骰子会清空 phone_info/magnifier_info，避免继续使用旧电话情报。
    """
    gs = session_data["game_state"]
    bullets = json.loads(gs.get("bullets", "[]"))
    current_index = gs.get("current_bullet_index", 0)

    phone_info_raw = gs.get("phone_info")
    if not phone_info_raw and session_data.get("ai_known_phone"):
        session_data["ai_known_phone"] = None

    # 当前弹位越界时，不应保留“已知当前弹药”
    if current_index >= len(bullets):
        session_data["ai_known_bullet"] = None
        session_data["ai_known_phone"] = None
        return

    known_phone = session_data.get("ai_known_phone")
    if known_phone:
        absolute_index = known_phone.get("absolute_index")
        if isinstance(absolute_index, int) and absolute_index >= len(bullets):
            session_data["ai_known_phone"] = None


def _score_shoot_target(
    target: str,
    p_live: float,
    is_sawed_off: bool,
    hp_diff: int,
) -> float:
    """
    对射击目标做期望收益评分，分数高者优先。
    """
    damage = 2.0 if is_sawed_off else 1.0
    p_blank = 1.0 - p_live

    # 价值权重：击伤对手 > 自身受伤惩罚；领先时更保守，落后时更激进
    opp_damage_value = 1.30 + (0.18 if hp_diff < 0 else 0.0)
    self_damage_cost = 1.15 + (0.20 if hp_diff > 0 else 0.0)
    keep_turn_value = 0.55 + (0.10 if hp_diff < 0 else 0.0)
    lose_turn_cost = 0.22

    if target == "self":
        return p_blank * keep_turn_value - p_live * damage * self_damage_cost
    return p_live * damage * opp_damage_value - p_blank * lose_turn_cost


def _choose_best_item_action(
    session_data: dict,
    ai_items: list,
    player_items: list,
    ai_hp: int,
    max_hp: int,
    hp_diff: int,
    p_live: float,
    known_current_bullet: Optional[bool],
    known_phone_pos: Optional[int],
    is_sawed_off: bool,
    handcuffed: Optional[str],
) -> Optional[AIAction]:
    """
    道具评分选择器。
    只处理“非硬规则”的常规道具决策，硬连招留在 decide_action 的前置分支。
    """
    gs = session_data["game_state"]
    ai_known_phone = session_data.get("ai_known_phone")
    magnifier_info = gs.get("magnifier_info")
    phone_info = gs.get("phone_info")

    candidates: list[tuple[float, AIAction]] = []

    def push(score: float, action: AIAction):
        candidates.append((score, action))

    # 放大镜：未知当前弹时信息价值最高
    if _has_item(ai_items, ItemType.MAGNIFIER) and known_current_bullet is None:
        info_score = 2.2 + (0.2 if hp_diff < 0 else 0.0)
        push(info_score, AIAction("use_item", item=ItemType.MAGNIFIER.value))

    # 电话：已有电话情报时避免重复
    if _has_item(ai_items, ItemType.PHONE) and known_current_bullet is None and not ai_known_phone:
        phone_score = 1.6 + (0.2 if hp_diff < 0 else 0.0)
        push(phone_score, AIAction("use_item", item=ItemType.PHONE.value))

    # 香烟：稳定回血
    if _has_item(ai_items, ItemType.CIGARETTE) and ai_hp < max_hp:
        heal_score = 1.0 + (0.7 if ai_hp <= 2 else 0.0) + (0.25 if hp_diff < 0 else 0.0)
        push(heal_score, AIAction("use_item", item=ItemType.CIGARETTE.value))

    # 过期药：仅在低血时有价值
    if _has_item(ai_items, ItemType.EXPIRED_MEDICINE) and ai_hp <= 2:
        med_score = 1.25 + (0.35 if ai_hp == 1 else 0.0)
        push(med_score, AIAction("use_item", item=ItemType.EXPIRED_MEDICINE.value))

    # 手铐：对手跳回合价值高，尤其当前实弹概率高时
    if _has_item(ai_items, ItemType.HANDCUFFS) and handcuffed != "player":
        cooldown = gs.get("handcuffs_cooldown_player_id")
        if cooldown != "player":
            cuff_score = 1.15 + (0.45 if p_live >= 0.5 else 0.0) + (0.35 if known_current_bullet is True else 0.0)
            push(cuff_score, AIAction("use_item", item=ItemType.HANDCUFFS.value))

    # 手锯：提高下一发实弹收益
    if _has_item(ai_items, ItemType.KNIFE) and not is_sawed_off:
        knife_score = 0.95 + (0.55 if p_live >= 0.55 else 0.0) + (0.45 if known_current_bullet is True else 0.0)
        push(knife_score, AIAction("use_item", item=ItemType.KNIFE.value))

    # 逆转器：高实弹概率时用于降风险；已知空弹+手锯时前置硬规则已覆盖
    if _has_item(ai_items, ItemType.INVERTER):
        inv_score = 0.45
        if known_current_bullet is True and not is_sawed_off:
            inv_score = 1.3
        elif known_current_bullet is None and p_live > 0.58 and not is_sawed_off:
            inv_score = 1.0
        push(inv_score, AIAction("use_item", item=ItemType.INVERTER.value))

    # 啤酒：推进弹仓，电话已知下一发时价值更高
    if _has_item(ai_items, ItemType.BEER):
        beer_score = 0.4
        if known_phone_pos == 2:
            beer_score = 2.25
        elif known_current_bullet is False:
            beer_score = 1.2
        elif p_live > 0.55:
            beer_score = 0.95
        push(beer_score, AIAction("use_item", item=ItemType.BEER.value))

    # 肾上腺素：偷取高价值道具
    if _has_item(ai_items, ItemType.ADRENALINE) and player_items:
        steal_target = _pick_steal_target(player_items, ai_hp, p_live)
        if steal_target:
            steal_bonus = 0.0
            if steal_target in (ItemType.MAGNIFIER.value, ItemType.HANDCUFFS.value, ItemType.KNIFE.value):
                steal_bonus = 0.45
            elif steal_target in (ItemType.CIGARETTE.value, ItemType.EXPIRED_MEDICINE.value):
                steal_bonus = 0.35 if ai_hp <= 2 else 0.1
            adr_score = 1.05 + steal_bonus
            push(adr_score, AIAction("use_item", item=ItemType.ADRENALINE.value, steal_item=steal_target))

    # 骰子：对手存在预知信息时打乱价值更高
    if _has_item(ai_items, ItemType.DICE):
        has_player_info = False
        if magnifier_info:
            info = json.loads(magnifier_info)
            has_player_info = has_player_info or info.get("player_id") == "player"
        if phone_info:
            info = json.loads(phone_info)
            has_player_info = has_player_info or info.get("player_id") == "player"
        if has_player_info:
            dice_score = 1.2 + (0.2 if hp_diff < 0 else 0.0)
            push(dice_score, AIAction("use_item", item=ItemType.DICE.value))

    if not candidates:
        return None

    # 落后时更愿意用道具，领先时略保守
    min_item_score = 0.85 if hp_diff < 0 else 1.0
    best_score, best_action = max(candidates, key=lambda x: x[0])
    if best_score < min_item_score:
        return None
    return best_action


def decide_action(session_data: dict) -> AIAction:
    """
    AI 决策：基于当前状态选择最优操作
    返回一个 AIAction
    """
    gs = session_data["game_state"]
    ai_items = _get_ai_items(session_data)
    player_items = _get_player_items(session_data)
    ai_hp = gs["ai_hp"]
    player_hp = gs["player_hp"]
    max_hp = session_data["max_hp"]
    is_sawed_off = gs.get("is_sawed_off", False)
    handcuffed = gs.get("handcuffed_player_id")
    # AI 的已知信息
    _ensure_knowledge_consistency(session_data)
    _sync_phone_knowledge(session_data)
    known_current_bullet = session_data.get("ai_known_bullet")  # True=实弹, False=空包弹, None=未知
    known_phone_pos = _get_phone_relative_position(session_data)
    known_phone_live = None
    if session_data.get("ai_known_phone"):
        known_phone_live = session_data["ai_known_phone"].get("is_live")
    p_live = _get_bullet_probability(session_data)

    # HP 差值用于动态调整策略
    hp_diff = ai_hp - player_hp  # 正=AI优势, 负=AI劣势

    # === 1. 预知阶段：使用放大镜或电话获取信息 ===
    if (
        known_current_bullet is None
        and known_phone_pos == 2
        and known_phone_live is True
        and _has_item(ai_items, ItemType.INVERTER)
        and _has_item(ai_items, ItemType.BEER)
        and not is_sawed_off
    ):
        return AIAction("use_item", item=ItemType.INVERTER.value)

    if known_current_bullet is None and known_phone_pos == 2 and _has_item(ai_items, ItemType.BEER):
        return AIAction("use_item", item=ItemType.BEER.value)

    if known_current_bullet is None:
        item_action = _choose_best_item_action(
            session_data=session_data,
            ai_items=ai_items,
            player_items=player_items,
            ai_hp=ai_hp,
            max_hp=max_hp,
            hp_diff=hp_diff,
            p_live=p_live,
            known_current_bullet=known_current_bullet,
            known_phone_pos=known_phone_pos,
            is_sawed_off=is_sawed_off,
            handcuffed=handcuffed,
        )
        if item_action:
            return item_action

    # === 2. 已知弹药时的操作 ===
    if known_current_bullet is not None:
        if known_current_bullet is False:
            # 已知空包弹
            if is_sawed_off:
                # 手锯激活时不能浪费在空弹上！
                # 优先逆转器：空弹→实弹→配合手锯打出2伤害
                if _has_item(ai_items, ItemType.INVERTER):
                    return AIAction("use_item", item=ItemType.INVERTER.value)
                # 啤酒退掉空弹，保留手锯效果给下一发
                if _has_item(ai_items, ItemType.BEER):
                    return AIAction("use_item", item=ItemType.BEER.value)
            elif _has_item(ai_items, ItemType.KNIFE) and _has_item(ai_items, ItemType.INVERTER):
                # 有手锯+逆转器→翻转空弹为实弹→可打出手锯2伤害连招
                return AIAction("use_item", item=ItemType.INVERTER.value)
            # 普通空包弹 → 对自己开枪保留行动权
            return AIAction("shoot", target="self")
        else:
            # 已知实弹 → 准备对对手开枪（完整连招：手铐→手锯→开枪）
            # 优先手铐限制对手（锁住对手后打出实弹，对手无法反击）
            if _has_item(ai_items, ItemType.HANDCUFFS) and handcuffed != "player":
                cooldown = gs.get("handcuffs_cooldown_player_id")
                if cooldown != "player":
                    return AIAction("use_item", item=ItemType.HANDCUFFS.value)
            # 再用手锯增伤
            if _has_item(ai_items, ItemType.KNIFE) and not is_sawed_off:
                return AIAction("use_item", item=ItemType.KNIFE.value)
            # 无手锯但有逆转器→翻转为空弹→射自己保留回合权（比直接打对手1伤害更优）
            if _has_item(ai_items, ItemType.INVERTER) and not is_sawed_off:
                return AIAction("use_item", item=ItemType.INVERTER.value)
            # 对对手开枪
            return AIAction("shoot", target="opponent")

    # 常规道具改为评分选择（已知弹药的硬规则在前面已处理）
    item_action = _choose_best_item_action(
        session_data=session_data,
        ai_items=ai_items,
        player_items=player_items,
        ai_hp=ai_hp,
        max_hp=max_hp,
        hp_diff=hp_diff,
        p_live=p_live,
        known_current_bullet=known_current_bullet,
        known_phone_pos=known_phone_pos,
        is_sawed_off=is_sawed_off,
        handcuffed=handcuffed,
    )
    if item_action:
        return item_action

    # === 6. 射击决策（信息价值加权评分）===
    if is_sawed_off:
        # 手锯已激活，必须对对手开枪
        return AIAction("shoot", target="opponent")

    # 评分法：融合实弹概率、回合价值、血量差，替代硬阈值
    score_self = _score_shoot_target("self", p_live, is_sawed_off, hp_diff)
    score_opp = _score_shoot_target("opponent", p_live, is_sawed_off, hp_diff)
    if score_self > score_opp:
        return AIAction("shoot", target="self")
    return AIAction("shoot", target="opponent")


def _pick_steal_target(player_items: list, ai_hp: int = 999, p_live: float = 0.5) -> Optional[str]:
    """选择肾上腺素偷取目标（按优先级，考虑血量和弹药情况）"""
    # 濒死时优先偷回血道具续命
    if ai_hp <= 2:
        for item_type in [ItemType.CIGARETTE, ItemType.EXPIRED_MEDICINE]:
            if item_type.value in player_items:
                return item_type.value

    # 根据实弹概率动态调整优先级
    if p_live >= 0.5:
        # 实弹概率高 -> 偷逆转器/啤酒（操控弹药）和放大镜（信息）更有价值
        priority = [
            ItemType.MAGNIFIER,
            ItemType.INVERTER,
            ItemType.KNIFE,
            ItemType.BEER,
            ItemType.CIGARETTE,
            ItemType.PHONE,
            ItemType.HANDCUFFS,
            ItemType.EXPIRED_MEDICINE,
            ItemType.DICE,
        ]
    else:
        # 空弹概率高 -> 偷放大镜和手锯/手铐更有价值
        priority = [
            ItemType.MAGNIFIER,
            ItemType.KNIFE,
            ItemType.HANDCUFFS,
            ItemType.CIGARETTE,
            ItemType.BEER,
            ItemType.INVERTER,
            ItemType.PHONE,
            ItemType.EXPIRED_MEDICINE,
            ItemType.DICE,
        ]

    for item_type in priority:
        if item_type.value in player_items:
            return item_type.value
    return None


def execute_ai_action(session_data: dict, action: AIAction) -> Tuple[str, bool, bool]:
    """
    执行 AI 的单个动作
    返回: (消息文本, 是否游戏结束, AI是否继续行动)
    """
    gs = session_data["game_state"]
    max_hp = session_data["max_hp"]

    if action.action_type == "shoot":
        shooter_id = "ai"
        target_id = "ai" if action.target == "self" else "player"

        hit, shoot_msg, game_over = RussianRouletteCore.shoot(gs, shooter_id, target_id)

        # 更新已发射弹药统计
        if hit:
            session_data["bullet_counts"]["fired_live"] += 1
        else:
            session_data["bullet_counts"]["fired_blank"] += 1

        # 清除 AI 预知信息（射击后信息失效）
        session_data["ai_known_bullet"] = None

        target_text = "自己" if action.target == "self" else "对手"
        msg = f"🤖 花花对{target_text}开枪\n{shoot_msg}"

        if game_over:
            return msg, True, False

        # 判断是否继续行动
        if action.target == "self" and not hit:
            # 对自己开空包弹，继续行动
            continue_turn = True
        else:
            # 射中或对对手开枪，切换回合
            continue_turn = False

        # 检查对手被手铐情况
        if not continue_turn and gs.get("handcuffed_player_id") == "player":
            gs["handcuffed_player_id"] = None
            msg += "\n⛓️ 玩家被手铐限制，跳过回合"
            continue_turn = True

        return msg, False, continue_turn

    elif action.action_type == "use_item":
        item_type = ItemType(action.item)
        item_name = RussianRouletteCore.ITEM_CONFIGS[item_type]["name"]
        ai_items = json.loads(gs.get("ai_items", "[]"))

        success = False
        result_msg = ""

        if item_type == ItemType.KNIFE:
            success, result_msg = RussianRouletteCore.use_knife(gs)
        elif item_type == ItemType.HANDCUFFS:
            success, result_msg = RussianRouletteCore.use_handcuffs(gs, "player")
        elif item_type == ItemType.CIGARETTE:
            success, result_msg = RussianRouletteCore.use_cigarette(gs, "ai", max_hp)
        elif item_type == ItemType.MAGNIFIER:
            success, result_msg = RussianRouletteCore.use_magnifier(gs, "ai")
            if success:
                # AI 直接获取信息（不需要私聊）
                magnifier_data = json.loads(gs.get("magnifier_info", "{}"))
                if magnifier_data.get("player_id") == "ai":
                    session_data["ai_known_bullet"] = magnifier_data.get("is_live")
                result_msg = "🔍 花花使用了放大镜查看了当前弹药"
        elif item_type == ItemType.BEER:
            success, result_msg = RussianRouletteCore.use_beer(gs)
            if success:
                # 啤酒退膛后更新已发射统计
                if "实弹" in result_msg:
                    session_data["bullet_counts"]["fired_live"] += 1
                else:
                    session_data["bullet_counts"]["fired_blank"] += 1
                # 清除 AI 预知信息
                session_data["ai_known_bullet"] = None
        elif item_type == ItemType.INVERTER:
            known_before = session_data.get("ai_known_bullet")
            success, result_msg = RussianRouletteCore.use_inverter(gs)
            if success:
                # 逆转器翻转弹药：已知则取反，未知时因使用条件p_live>0.6故翻转后为空弹
                session_data["ai_known_bullet"] = (not known_before) if known_before is not None else False
        elif item_type == ItemType.PHONE:
            success, result_msg = RussianRouletteCore.use_phone(gs, "ai")
            if success:
                phone_data = json.loads(gs.get("phone_info", "{}"))
                if phone_data.get("player_id") == "ai":
                    current_index = gs.get("current_bullet_index", 0)
                    bullet_position = phone_data.get("bullet_position")
                    if isinstance(bullet_position, int) and bullet_position > 0:
                        phone_data["absolute_index"] = current_index + bullet_position - 1
                    session_data["ai_known_phone"] = phone_data
                    # 如果电话透露的是当前弹药（position=1），直接记录
                    if phone_data.get("bullet_position") == 1:
                        session_data["ai_known_bullet"] = phone_data.get("is_live")
                result_msg = "📞 花花使用了电话获取了弹药信息"
        elif item_type == ItemType.EXPIRED_MEDICINE:
            success, result_msg = RussianRouletteCore.use_expired_medicine(gs, "ai", max_hp)
        elif item_type == ItemType.DICE:
            success, result_msg = RussianRouletteCore.use_dice(gs)
            if success:
                # 骰子打乱了顺序，清除所有预知
                session_data["ai_known_bullet"] = None
                session_data["ai_known_phone"] = None
        elif item_type == ItemType.ADRENALINE:
            if action.steal_item:
                stolen_type = ItemType(action.steal_item)
                success, result_msg = RussianRouletteCore.use_adrenaline(
                    gs, "ai", "player", stolen_type, max_hp
                )
                if success:
                    # 肾上腺素偷放大镜时，AI 获得信息
                    if stolen_type == ItemType.MAGNIFIER:
                        magnifier_data = json.loads(gs.get("magnifier_info", "{}"))
                        if magnifier_data.get("player_id") == "ai":
                            session_data["ai_known_bullet"] = magnifier_data.get("is_live")
                    elif stolen_type == ItemType.BEER:
                        if "实弹" in result_msg:
                            session_data["bullet_counts"]["fired_live"] += 1
                        elif "空包弹" in result_msg:
                            session_data["bullet_counts"]["fired_blank"] += 1
                        session_data["ai_known_bullet"] = None
                    elif stolen_type == ItemType.INVERTER:
                        session_data["ai_known_bullet"] = None
                    elif stolen_type == ItemType.PHONE:
                        phone_data = json.loads(gs.get("phone_info", "{}"))
                        if phone_data.get("player_id") == "ai":
                            current_index = gs.get("current_bullet_index", 0)
                            bullet_position = phone_data.get("bullet_position")
                            if isinstance(bullet_position, int) and bullet_position > 0:
                                phone_data["absolute_index"] = current_index + bullet_position - 1
                            session_data["ai_known_phone"] = phone_data
                            if phone_data.get("bullet_position") == 1:
                                session_data["ai_known_bullet"] = phone_data.get("is_live")
                    elif stolen_type == ItemType.DICE:
                        session_data["ai_known_bullet"] = None
                        session_data["ai_known_phone"] = None
            else:
                return f"🤖 花花想用肾上腺素但没找到合适目标", False, True

        if not success:
            # 道具使用失败，继续决策（不消耗道具）
            return f"🤖 花花尝试使用{item_name}但失败了: {result_msg}", False, True

        # 消耗道具（对于肾上腺素，Core 已经处理了消耗）
        if item_type != ItemType.ADRENALINE:
            ai_items.remove(item_type.value)
            gs["ai_items"] = json.dumps(ai_items)

        msg = f"🤖 花花使用了{item_name}\n{result_msg}"

        # 检查道具使用后是否有人死亡（过期药可能自杀）
        game_over = gs.get("ai_hp", 1) <= 0 or gs.get("player_hp", 1) <= 0

        return msg, game_over, not game_over  # 使用道具后继续行动（除非游戏结束）

    return "🤖 AI 无法操作", False, False


def execute_ai_turn(session_data: dict) -> Tuple[List[str], bool]:
    """
    执行 AI 的完整回合（可能包含多次道具使用 + 最终射击）
    返回: (消息列表, 是否游戏结束)
    """
    messages = []
    max_actions = 20  # 防止无限循环

    # AI 开始行动，清除针对 AI 的手铐冷却（AI 已完成被跳过的回合，可以被再次手铐）
    gs = session_data["game_state"]
    if gs.get("handcuffs_cooldown_player_id") == "ai" and gs.get("handcuffed_player_id") != "ai":
        gs["handcuffs_cooldown_player_id"] = None

    for _ in range(max_actions):
        if session_data["current_turn"] != "ai":
            break

        # 检查弹药是否耗尽需要重装
        gs = session_data["game_state"]
        reloaded, reload_msg = RussianRouletteCore.check_and_reload(gs, "player", "ai")
        if reloaded:
            messages.append(reload_msg)
            # 更新弹药统计
            bullets = json.loads(gs["bullets"])
            session_data["bullet_counts"] = {
                "total_live": sum(1 for b in bullets if b),
                "total_blank": sum(1 for b in bullets if not b),
                "fired_live": 0,
                "fired_blank": 0,
            }
            # 清除 AI 预知信息
            session_data["ai_known_bullet"] = None
            session_data["ai_known_phone"] = None

        # 隐藏透视：AI 有概率直觉感知当前弹药
        _maybe_peek_bullet(session_data)

        action = decide_action(session_data)
        msg, game_over, continue_turn = execute_ai_action(session_data, action)
        messages.append(msg)

        if game_over:
            return messages, True

        if not continue_turn:
            session_data["current_turn"] = "player"
            # 交还回合给玩家前，检查弹药是否耗尽需要重装
            gs = session_data["game_state"]
            reloaded, reload_msg = RussianRouletteCore.check_and_reload(gs, "player", "ai")
            if reloaded:
                messages.append(reload_msg)
                bullets = json.loads(gs["bullets"])
                session_data["bullet_counts"] = {
                    "total_live": sum(1 for b in bullets if b),
                    "total_blank": sum(1 for b in bullets if not b),
                    "fired_live": 0,
                    "fired_blank": 0,
                }
                session_data["ai_known_bullet"] = None
                session_data["ai_known_phone"] = None
            break

        # 继续 AI 行动前，再检查一下弹药
        reloaded, reload_msg = RussianRouletteCore.check_and_reload(gs, "player", "ai")
        if reloaded:
            messages.append(reload_msg)
            bullets = json.loads(gs["bullets"])
            session_data["bullet_counts"] = {
                "total_live": sum(1 for b in bullets if b),
                "total_blank": sum(1 for b in bullets if not b),
                "fired_live": 0,
                "fired_blank": 0,
            }
            session_data["ai_known_bullet"] = None
            session_data["ai_known_phone"] = None

    return messages, False
