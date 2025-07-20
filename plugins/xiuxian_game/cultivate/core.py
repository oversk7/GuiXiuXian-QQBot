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
from ..models.inventory import ItemInstance as _Equip, ItemType


cfg = config.game_config["cultivate"]


async def get_coffin_nail_count(session, player_id: str) -> int:
    """获取玩家背包中棺材钉的数量"""
    result = await session.execute(
        _sel(_Equip).where(
            _Equip.player_id == player_id,
            _Equip.item_id == "coffin_nail"
        )
    )
    coffin_nails = result.scalars().all()
    return sum(nail.quantity for nail in coffin_nails)
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
            await cultivate.finish(message_add_head(
                "⚰️ 钉子阻隔冥修\n"
                "━━━━━━━━━━━━━\n"
                "闭棺期间无法普通修炼。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【出关】推开棺盖 或 等待结算",
                event))
        
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
            await seclusion.finish(message_add_head(
                "⚰️ 棺材已封\n"
                "━━━━━━━━━━━━━\n"
                "你已在闭棺中。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【出关】推开棺盖",
                event))

        # 计算棺材钉数量和效率加成
        coffin_nail_count = await get_coffin_nail_count(session, player.id)
        efficiency_bonus = coffin_nail_count * 0.5  # 每个棺材钉提升0.5%效率

        player.is_secluded = True
        player.seclusion_start_time = datetime.now()
        session.add(player)
        await session.commit()

        # 构建闭关消息，包含棺材钉效率提示
        efficiency_msg = ""
        if coffin_nail_count > 0:
            efficiency_msg = f"\n✧ 棺材钉 ⚰️ ✖️{coffin_nail_count} 提升效率 +{efficiency_bonus:.1f}%"

        msg_secl = (
            f"🕯️{player.nickname} 躺入破棺，将最后一枚钉子钉入。\n"
            "━━━━━━━━━━━━━\n"
            "✧ 离线修炼进行中，期间无法普通修炼"
            f"{efficiency_msg}\n"
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
            await out_seclusion.finish(message_add_head(
                "🕳️ 棺盖早已打开\n"
                "━━━━━━━━━━━━━\n"
                "你当前并未闭棺。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【闭关】钉上棺盖",
                event))

        # 计算棺材钉数量和效率加成
        coffin_nail_count = await get_coffin_nail_count(session, player.id)
        efficiency_multiplier = 1.0 + (coffin_nail_count * 0.005)  # 每个棺材钉提升0.5%效率

        player.is_secluded = False
        k = 7 if player.level <= 10 else 6
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        delta_time = int((datetime.now() - player.seclusion_start_time).total_seconds())
        delta_time = delta_time if delta_time < 7 * 3600 else 7 * 3600

        # 应用棺材钉效率加成
        base_exp_gain = int(delta_time / cfg["cool_down"] * base_gain * 0.5)
        exp_gain = int(base_exp_gain * efficiency_multiplier)
        bonus_exp = exp_gain - base_exp_gain

        player.exp += exp_gain

        session.add(player)
        await session.commit()
        exp_max2 = calculate_level_up_exp(player.level)

        # 构建出关消息，包含棺材钉效率提示
        efficiency_msg = ""
        if coffin_nail_count > 0:
            efficiency_bonus = coffin_nail_count * 0.5
            efficiency_msg = f"\n✧ 棺材钉 ⚰️ ✖️{coffin_nail_count} 额外获得 +{bonus_exp} 怨炁 (+{efficiency_bonus:.1f}%)"

        msg_out = (
            "🔓你推开棺盖，阴灰散落。\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 累积怨炁 + {exp_gain}↑"
            f"{efficiency_msg}\n"
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
            old_level = player.level
            player.exp -= required_exp
            player.level += 1
            player.attribute_points += config.game_config["game"]["points_per_level"]

            # 触发升级钩子
            from ..social.level_hooks import on_player_level_up
            await on_player_level_up(session, player.id, old_level, player.level)

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
                old_level = player.level
                player.exp -= required_exp
                player.level += 1
                player.attribute_points += config.game_config["game"]["points_per_level"]

                # 触发升级钩子
                from ..social.level_hooks import on_player_level_up
                await on_player_level_up(session, player.id, old_level, player.level)

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
        await assign_points.finish("指令说明：加点 [属性] [点数]\n例：加点 力 5\n可选属性：体/智/力/敏/防/运")
    
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

        # 记录分配前是否满血满蓝（仅在分配体/智属性时需要）
        was_hp_full = player.hp >= player.max_hp
        was_mp_full = player.mp >= player.max_mp

        # -------- 撤销旧装备 bonus --------
        result_eq = await session.execute(
            _sel(_Equip).where(
                _Equip.player_id == player.id, _Equip.equipped == True,
                _Equip.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
            )
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
            # 确保装备状态正确（应该已经是equipped=True，但为了安全起见）
            if not eq.equipped:
                continue

            attrs_temp = base_attrs_snapshot.copy()
            eq.apply_attr_bonus(attrs_temp)
            new_delta = {k: attrs_temp[k] - base_attrs_snapshot[k] for k in attrs_temp if attrs_temp[k] != base_attrs_snapshot[k]}

            # 应用新 delta
            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            # 保存新的持久化bonus
            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra
            session.add(eq)  # 确保装备的修改被保存

        # 如果分配前是满血满蓝，分配后也应该保持满状态
        if attr_field == "max_hp" and was_hp_full:
            player.hp = player.max_hp
        elif attr_field == "max_mp" and was_mp_full:
            player.mp = player.max_mp
        else:
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
        if attr_name == '运':
            msg += "\n⬇️ 【幸运榜】查看运气排名"
        await assign_points.finish(message_add_head(msg, event))
