from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from ..utils import  message_add_head, calculate_level_up_exp
from ..models.db import safe_session
from ..models.player import Player
from ..config import config
from datetime import datetime
import random
from sqlalchemy import select as _sel
from ..models.equipment import EquipmentInstance as _Equip


cfg = config.game_config["cultivate"]
cultivate = on_command("修炼", block=True, priority=5)
seclusion = on_command("闭关", block=True, priority=5)
out_seclusion = on_command("出关", block=True, priority=5)
breakthrough = on_command("突破", block=True, priority=5)
assign_points = on_command("加点",aliases={"分配"}, block=True, priority=5)



@cultivate.handle()
async def handle_cultivate(event: MessageEvent):
    """修炼主逻辑"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取玩家数据
        player = await session.get(Player, user_id)
        if not player:
            await cultivate.finish("⛔ 请先使用【注册】命令创建角色")
        
        # 闭关状态检查
        if player.is_secluded:
            await cultivate.finish("⛔ 闭关期间无法进行普通修炼，请先【出关】或完成闭关")
        
        # 冷却时间检查
        if player.last_cultivation and (datetime.now() - player.last_cultivation).seconds < cfg["cool_down"]:
            remaining = cfg["cool_down"] - (datetime.now() - player.last_cultivation).seconds
            await cultivate.finish(message_add_head(
                f"🕒 血火仍在灼烧…剩余 {remaining//60}分{remaining%60}秒，之后再尝试修炼。",
                event
            ))
        
        k = 7 if player.level <= 10 else 6
        # 基础收益计算
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        exp_gain = round(base_gain * random.uniform(0.8, 1.2))
        
        # 更新数据
        player.last_cultivation = datetime.now()
        player.exp += exp_gain
        session.add(player)
        await session.commit()
        exp_max = calculate_level_up_exp(player.level)
        msg = (
            "你在黑焰里看见自己的影子喘息。\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 汲取怨炁 + {exp_gain}↑\n"
            f"✧ 修为残烛 {player.exp}↑/{exp_max} {f'(可突破)' if player.exp> exp_max else ''}\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【突破】倾听骨骼断裂\n"
            "⬇️ 【加点】缝合裂隙，塑形新肉"
        )
        await cultivate.finish(message_add_head(msg, event))

@seclusion.handle()
async def handle_seclusion(event: MessageEvent):
    """闭关逻辑"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await seclusion.finish("⛔ 请先使用【注册】命令创建角色")

        if player.is_secluded:
            await seclusion.finish("⛔ 你已经在闭关中")

        player.is_secluded = True
        player.seclusion_start_time = datetime.now()
        session.add(player)
        await session.commit()
        msg_secl = (
            f"🕯️{player.nickname} 躺入破棺，将最后一枚钉子钉入。\n"
            "━━━━━━━━━━━━━\n"
            "✧ 离线修炼进行中，期间无法普通修炼\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【出关】推开棺盖"
        )
        await seclusion.finish(message_add_head(msg_secl, event))

@out_seclusion.handle()
async def handle_out_seclusion(event: MessageEvent):
    """出关逻辑"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await out_seclusion.finish("⛔ 请先使用【注册】命令创建角色")

        if not player.is_secluded:
            await out_seclusion.finish("⛔ 你不在闭棺状态")

        player.is_secluded = False
        k = 7 if player.level <= 10 else 6
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        delta_time = (datetime.now() - player.seclusion_start_time).seconds
        delta_time = delta_time if delta_time < 7 * 3600 else 7 * 3600
        exp_gain = int(delta_time / cfg["cool_down"] * base_gain * 0.5)
        player.exp += exp_gain

        session.add(player)
        await session.commit()
        exp_max2 = calculate_level_up_exp(player.level)
        msg_out = (
            "🔓你推开棺盖，阴灰散落。\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 累积怨炁 + {exp_gain}↑\n"
            f"✧ 修为残烛 {player.exp}↑/{exp_max2} {('(可突破)' if player.exp>exp_max2 else '')}\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【修炼】继续喂养怨炁\n"
            "⬇️ 【突破】倾听骨骼断裂"
        )
        await out_seclusion.finish(message_add_head(msg_out, event))

@breakthrough.handle()
async def handle_breakthrough(event: MessageEvent, args: Message = CommandArg()):
    """突破境界逻辑"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await breakthrough.finish("⛔ 请先使用【注册】命令创建角色")

        cfg_break = cfg["breakthrough"]
        required_exp = calculate_level_up_exp(player.level)
        
        # 解析参数，若包含"镇厄"则启用保驾护航模式
        arg_text = args.extract_plain_text().strip().lower() if isinstance(args, Message) else ""
        use_guardian = arg_text in {"护", "镇厄", "镇"}

        base_cost = cfg_break.get("guardian_cost_base", cfg_break.get("guardian_cost", 50))
        per_level_inc = cfg_break.get("guardian_cost_per_level", 1)
        guardian_cost = base_cost + player.level * per_level_inc
        
        # 计算成功率
        if player.level < cfg_break["change_level"]:
            success_chance = 1.0
        else:
            base_rate = cfg_break.get("base_success_rate", 0.8)
            decay = cfg_break.get("decay_per_level", 0.005)
            min_rate = cfg_break.get("min_success_rate", 0.05)
            success_chance = max(min_rate, base_rate - decay * (player.level - cfg_break["change_level"]))

        # 护航则必定成功
        if use_guardian:
            success_chance = 1.0

        # 检查经验是否足够
        if player.exp < required_exp:
            await breakthrough.finish(
                f"💢 修为不足！\n"
                f"▫️ 需要修为：{player.exp}/{required_exp}"
            )

        # 如果启用护航，检查怨念值是否足够
        if use_guardian and player.resentment < guardian_cost:
            await breakthrough.finish(f"⛔ 怨念值不足，镇厄需要 {guardian_cost}，当前 {player.resentment}")

        # 消耗怨念值（如果启用护航）
        if use_guardian:
            player.resentment -= guardian_cost

        if player.level < cfg_break["change_level"]:
            player.exp -= required_exp
            player.level += 1
            player.attribute_points += config.game_config["game"]["points_per_level"]
            msg = (
                f"⛓️‍💥骨裂声回荡，已突破至Lv.{player.level}↑\n"
                "━━━━━━━━━━━━━\n"
                f"✧ 获得属性点 + {config.game_config['game']['points_per_level']}\n"
                f"✧ 剩余修为 {player.exp}\n"
                + (f"✧ 消耗怨念值 {guardian_cost} (剩余{player.resentment})\n" if use_guardian else "") +
                "━━━━━━━━━━━━━\n"
                "⬇️ 【加点】缝合裂隙\n"
                "⬇️ 【修炼】继续喂养怨炁"
            )
        else:
            if random.random() <= success_chance:
                player.exp -= required_exp
                player.level += 1
                player.attribute_points += config.game_config["game"]["points_per_level"]
                msg = (
                    f"⛓️‍💥骨裂声回荡，已突破至Lv.{player.level}↑\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 获得属性点 + {config.game_config['game']['points_per_level']}\n"
                    f"✧ 剩余修为 {player.exp}\n"
                    + (f"✧ 消耗怨念值 {guardian_cost} (剩余{player.resentment})\n" if use_guardian else "") +
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 【加点】缝合裂隙\n"
                    "⬇️ 【修炼】继续喂养怨炁"
                )
            else:
                # 突破失败
                player.exp = round(player.exp * cfg_break["fail_keep_ratio"])
                msg = (
                    "💥 镇厄崩散，修为反噬席卷脏腑。\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 剩余修为 {player.exp}\n"
                    f"✧ 本次理论成功率 {int(success_chance*100)}%\n"
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 建议【突破 [镇厄]】以怨念护体"
                )

        session.add(player)
        await session.commit()
        await breakthrough.finish(message_add_head(msg, event))

# 基础属性映射表
ATTRIBUTE_MAP = {
    "体": "max_hp",
    "智": "max_mp",
    "力": "attack",
    "敏": "agility",
    "运": "luck",
    "防": "defense",
}

@assign_points.handle()
async def handle_assign(event: MessageEvent, args: Message = CommandArg()):
    """分配属性点"""
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await assign_points.finish("⛔ 格式错误，正确格式：加点 [属性] [点数]\n例：加点 力 5\n可选属性：体/智/力/敏/运")
    
    attr_name, points = params
    try:
        points = int(points)
        if points <= 0:
            raise ValueError
    except ValueError:
        await assign_points.finish("⛔ 点数必须为正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await assign_points.finish("⛔ 请先创建角色")
        
        if attr_name not in ATTRIBUTE_MAP:
            await assign_points.finish(f"⛔ 无效属性，可用属性：{'/'.join(ATTRIBUTE_MAP.keys())}")
        
        if player.attribute_points < points:
            await assign_points.finish(f"💢 属性点不足！当前剩余：{player.attribute_points}✨")
        
        attr_field = ATTRIBUTE_MAP[attr_name]
        inc_val = points * cfg["attributes_base"][attr_field]

        # -------- 撤销旧装备 bonus --------
        result_eq = await session.execute(
            _sel(_Equip).where(_Equip.player_id == player.id, _Equip.equipped == True)
        )
        equipped_items = result_eq.scalars().all()

        for eq in equipped_items:
            delta_prev = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta_prev.items():
                setattr(player, k, getattr(player, k) - v)
            # 清空记录，待会重新计算
            if eq.extra_attrs:
                eq.extra_attrs["_persist_bonus"] = {}

        # -------- 更新基础属性 --------
        setattr(player, attr_field, getattr(player, attr_field) + inc_val)
        player.attribute_points -= points

        # -------- 重新计算装备 bonus 根据新基础 --------
        base_attrs_snapshot = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        for eq in equipped_items:
            attrs_temp = base_attrs_snapshot.copy()
            eq.apply_attr_bonus(attrs_temp)
            new_delta = {k: attrs_temp[k] - base_attrs_snapshot[k] for k in attrs_temp if attrs_temp[k] != base_attrs_snapshot[k]}

            # 应用新 delta
            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            # 保存
            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra

        # 修正 HP/MP 不超过新上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        session.add(player)
        await session.commit()
        msg = (
            "🩸 裂隙缝合\n"
            f"✧ {attr_name} +{points} → {getattr(player, attr_field)}\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 剩余属性点 {player.attribute_points}\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【面板】检查残骸"
        )
        await assign_points.finish(message_add_head(msg, event))
