"""
恶魔轮盘 PvE AI 决策引擎
基于已知信息做出最优决策，不偷看弹仓
"""
import json
import random
from typing import Optional, List, Tuple
from .russian_roulette_core import RussianRouletteCore, ItemType


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
    known_current_bullet = session_data.get("ai_known_bullet")  # True=实弹, False=空包弹, None=未知
    p_live = _get_bullet_probability(session_data)

    # === 1. 预知阶段：使用放大镜或电话获取信息 ===
    if known_current_bullet is None:
        if _has_item(ai_items, ItemType.MAGNIFIER):
            return AIAction("use_item", item=ItemType.MAGNIFIER.value)

        if _has_item(ai_items, ItemType.PHONE) and not session_data.get("ai_known_phone"):
            return AIAction("use_item", item=ItemType.PHONE.value)

    # === 2. 已知弹药时的操作 ===
    if known_current_bullet is not None:
        if known_current_bullet is False:
            # 已知空包弹 -> 对自己开枪保留行动权
            return AIAction("shoot", target="self")
        else:
            # 已知实弹 -> 准备对对手开枪
            # 先用手锯增伤
            if _has_item(ai_items, ItemType.KNIFE) and not is_sawed_off:
                return AIAction("use_item", item=ItemType.KNIFE.value)
            # 用手铐限制对手
            if _has_item(ai_items, ItemType.HANDCUFFS) and handcuffed != "player":
                cooldown = gs.get("handcuffs_cooldown_player_id")
                if cooldown != "player":
                    return AIAction("use_item", item=ItemType.HANDCUFFS.value)
            # 对对手开枪
            return AIAction("shoot", target="opponent")

    # === 3. 生存优先 ===
    if ai_hp < max_hp:
        if ai_hp <= 2 and _has_item(ai_items, ItemType.CIGARETTE):
            return AIAction("use_item", item=ItemType.CIGARETTE.value)
        if ai_hp == 1 and _has_item(ai_items, ItemType.EXPIRED_MEDICINE):
            return AIAction("use_item", item=ItemType.EXPIRED_MEDICINE.value)

    # === 4. 弹药操控 ===
    # 如果实弹概率高且打算对自己开枪，可以用逆转器
    if _has_item(ai_items, ItemType.INVERTER) and p_live > 0.6 and not is_sawed_off:
        return AIAction("use_item", item=ItemType.INVERTER.value)

    # 用啤酒退膛（实弹概率高时退膛有利）
    if _has_item(ai_items, ItemType.BEER) and p_live > 0.6:
        return AIAction("use_item", item=ItemType.BEER.value)

    # === 5. 战术道具 ===
    # 手铐（实弹概率低时不用，宁可对自己开空枪多保一次行动权）
    if _has_item(ai_items, ItemType.HANDCUFFS) and handcuffed != "player" and p_live >= 0.5:
        cooldown = gs.get("handcuffs_cooldown_player_id")
        if cooldown != "player":
            return AIAction("use_item", item=ItemType.HANDCUFFS.value)

    # 手锯（仅在打算对对手开枪时）
    if _has_item(ai_items, ItemType.KNIFE) and not is_sawed_off and p_live >= 0.5:
        return AIAction("use_item", item=ItemType.KNIFE.value)

    # 肾上腺素（偷取对手高价值道具）
    if _has_item(ai_items, ItemType.ADRENALINE) and player_items:
        steal_target = _pick_steal_target(player_items, ai_hp)
        if steal_target:
            return AIAction("use_item", item=ItemType.ADRENALINE.value, steal_item=steal_target)

    # 骰子（如果自己没有预知信息，打乱来破坏对手可能的预知）
    if _has_item(ai_items, ItemType.DICE):
        # 只在可能对对手有利时使用
        magnifier_info = gs.get("magnifier_info")
        phone_info = gs.get("phone_info")
        if magnifier_info or phone_info:
            # 检查是否是玩家的预知信息
            if magnifier_info:
                info = json.loads(magnifier_info)
                if info.get("player_id") == "player":
                    return AIAction("use_item", item=ItemType.DICE.value)
            if phone_info:
                info = json.loads(phone_info)
                if info.get("player_id") == "player":
                    return AIAction("use_item", item=ItemType.DICE.value)

    # === 6. 射击决策（无预知信息时）===
    if is_sawed_off:
        # 手锯已激活，必须对对手开枪
        return AIAction("shoot", target="opponent")

    if p_live < 0.5:
        # 空包弹概率较高，对自己开枪保留行动权
        return AIAction("shoot", target="self")
    else:
        # 实弹概率较高或相等，对对手开枪
        return AIAction("shoot", target="opponent")


def _pick_steal_target(player_items: list, ai_hp: int = 999) -> Optional[str]:
    """选择肾上腺素偷取目标（按优先级，低血时优先偷回血道具）"""
    # 濒死时优先偷回血道具续命
    if ai_hp <= 2:
        for item_type in [ItemType.CIGARETTE, ItemType.EXPIRED_MEDICINE]:
            if item_type.value in player_items:
                return item_type.value

    priority = [
        ItemType.MAGNIFIER,
        ItemType.KNIFE,
        ItemType.CIGARETTE,
        ItemType.BEER,
        ItemType.INVERTER,
        ItemType.PHONE,
        ItemType.HANDCUFFS,
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
