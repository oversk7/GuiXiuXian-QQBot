from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from ..utils import  create_rich_message, calculate_level_up_exp
from ..data.db import safe_session
from ..models.player import Player
from ..config import config
from datetime import datetime
import random


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
        
        # 冷却时间检查
        if player.last_cultivation and (datetime.now() - player.last_cultivation).seconds < cfg["cool_down"]:
            remaining = cfg["cool_down"] - (datetime.now() - player.last_cultivation).seconds

            await cultivate.finish(f"🕒 修炼调息中...（冷却剩余 {remaining//60}分{remaining%60}秒）")
        
        k = 5 if player.level <= 10 else 2
        # 基础收益计算
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        exp_gain = round(base_gain * random.uniform(0.8, 1.2))
        
        # 更新数据
        player.last_cultivation = datetime.now()
        player.exp += exp_gain
        session.add(player)
        await session.commit()
        
        await cultivate.finish(f"🌀 运转周天完毕 🌀\n▫️ 获得修为：+{exp_gain}\n▫️ 当前经验：{player.exp}/{calculate_level_up_exp(player.level)}")

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
        await seclusion.finish(f"🏜️ {player.nickname} 进入闭关状态！")

@out_seclusion.handle()
async def handle_out_seclusion(event: MessageEvent):
    """出关逻辑"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await out_seclusion.finish("⛔ 请先使用【注册】命令创建角色")

        if not player.is_secluded:
            await out_seclusion.finish("⛔ 你不在闭关状态")

        player.is_secluded = False
        k = 5 if player.level <= 10 else 2
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        delta_time = (datetime.now() - player.seclusion_start_time).seconds
        delta_time = delta_time if delta_time < 7 * 3600 else 7 * 3600
        exp_gain = int(delta_time / cfg["cool_down"] * base_gain * 0.5)
        player.exp += exp_gain

        session.add(player)
        await session.commit()
        await out_seclusion.finish(f"🏜️ {player.nickname} 出关成功！\n▫️ 共获得修为：+{exp_gain}\n▫️ 当前经验：{player.exp}/{calculate_level_up_exp(player.level)}")

@breakthrough.handle()
async def handle_breakthrough(event: MessageEvent):
    """突破境界逻辑"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await breakthrough.finish("⛔ 请先使用【注册】命令创建角色")

        cfg_break = cfg["breakthrough"]
        required_exp = calculate_level_up_exp(player.level)
        
        # 检查经验是否足够
        if player.exp < required_exp:
            await breakthrough.finish(
                f"💢 修为不足！\n"
                f"▫️ 需要修为：{player.exp}/{required_exp}"
            )

        if player.level < cfg_break["change_level"]:
            player.exp -= required_exp
            player.level += 1
            player.attribute_points += config.game_config["game"]["points_per_level"]
            msg = (
                f"✨ 突破成功！Lv.{player.level-1}→Lv.{player.level} ✨\n"
                f"▫️ 获得属性点：+{config.game_config['game']['points_per_level']}✨\n"
                f"▫️ 剩余修为：{player.exp}"
            )
        else:
            if random.random() <= 0.8:
                player.exp -= required_exp
                player.level += 1
                player.attribute_points += config.game_config["game"]["points_per_level"]
                msg = (
                    f"✨ 突破成功！Lv.{player.level-1}→Lv.{player.level} ✨\n"
                    f"▫️ 获得属性点：+{config.game_config['game']['points_per_level']}✨\n"
                    f"▫️ 剩余修为：{player.exp}"
                )
            else:
                # 突破失败
                player.exp = round(player.exp * cfg_break["fail_keep_ratio"])
                msg = (
                    f"💥 突破失败！修为反噬\n"
                    f"▫️ 剩余修为：{player.exp}\n"
                )

        session.add(player)
        await session.commit()
        await breakthrough.finish(create_rich_message(msg, event))

# 基础属性映射表
ATTRIBUTE_MAP = {
    "体": "max_hp",
    "智": "max_mp",
    "力": "attack",
    "防": "defense",
    "敏": "agility",
}

@assign_points.handle()
async def handle_assign(event: MessageEvent, args: Message = CommandArg()):
    """分配属性点"""
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await assign_points.finish("⛔ 格式错误，正确格式：加点 [属性] [点数]\n例：加点 力 5\n可选属性：体/智/力/防/敏")
    
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
        setattr(player, attr_field, getattr(player, attr_field) + points*cfg["attributes_base"][attr_field])
        player.attribute_points -= points
        
        session.add(player)
        await session.commit()
        msg = (
            f"✨ {attr_name} 分配成功！\n"
            f"▫️ 当前{attr_name}：{getattr(player, attr_field)}\n"
            f"▫️ 剩余属性点：{player.attribute_points}✨"
        )
        await assign_points.finish(create_rich_message(msg, event))
