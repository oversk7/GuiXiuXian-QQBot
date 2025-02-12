from nonebot import on_command, get_bot, logger
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from nonebot_plugin_apscheduler import scheduler
import random
import asyncio
from ..config import config
from ..data.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..utils import create_rich_message
from sqlalchemy.orm import joinedload
from sqlalchemy import select, delete
from ..models.team import Team, TeamMember
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.player import get_player_by_uid
from ..models.inventory import ItemType, ItemEffectType

# 战斗命令
explore_cmd = on_command("探索", block=True, priority=5)
attack_cmd = on_command("攻击", block=True, priority=5)
use_item_cmd = on_command("使用", block=True, priority=5)
escape_cmd = on_command("逃跑", block=True, priority=5)

# 战斗缓存结构
_player_battles: Dict[str, 'BattleInstance'] = {}  # 玩家ID映射到战斗实例
_BATTLE_TIMEOUT = 600


class BattleActor:
    """战斗参与者基类"""
    __slots__ = ['id', 'name', 'is_player', 'hp', 'max_hp', 'mp', 'max_mp', 
                'attack', 'defense', 'agility', 'fear_resistance', 'luck',
                'behavior', 'skills', 'action_weights','level', 'drops']
    
    def __init__(self, entity: Any, is_player: bool = True):
        self.id = str(id(entity)) if not is_player else entity.id
        self.name = getattr(entity, 'nickname', '未知') if is_player else entity['name']
        self.is_player = is_player
        
        # 玩家属性（从Player对象获取）
        if is_player:
            self.level = entity.level
            self.hp = entity.hp
            self.max_hp = entity.max_hp
            self.mp = entity.mp
            self.max_mp = entity.max_mp
            self.attack = entity.attack
            self.defense = entity.defense
            self.agility = entity.agility
            self.fear_resistance = entity.fear_resistance
            self.luck = entity.luck
        # 敌人属性（从字典配置获取）
        else:
            self.level = entity['level']
            self.max_hp = entity['max_hp']
            self.hp = entity.get('hp', self.max_hp)
            self.max_mp = entity.get('max_mp', 0)
            self.mp = entity.get('mp', 0)
            self.attack = entity['attack']
            self.defense = entity['defense']
            self.agility = entity['agility']
            self.fear_resistance = entity.get('fear_resistance', 0)
            self.luck = entity.get('luck', 0)
            self.behavior = entity.get('behavior', 'normal')
            self.skills = entity.get('skills', [])
            self.action_weights = entity.get('action_weights', (70, 20, 10))  # 使用元组节省内存
            self.drops = entity.get('drops', [])  # 添加掉落物属性
        
    def calculate_hit_chance(self, target) -> float:
        """根据双方敏捷计算命中率"""
        return min(0.95, max(0.05, self.agility / (self.agility + target.agility)))

class BattleInstance:
    """战斗实例管理"""
    __slots__ = ['battle_id', 'battle_type', 'players', 'enemies', 
                'turn', 'last_active', 'actions', 'logs', 'latest_event', 'max_logs']
    
    def __init__(self, battle_type: str, players: List[Player], enemies: List[Dict], latest_event: MessageEvent):
        # 生成唯一战斗ID（包含所有参与者ID的哈希）
        participants = [p.id for p in players]
        self.battle_id = f"battle_{hash(frozenset(participants))}_{datetime.now().timestamp()}"
        
        # 注册玩家到战斗映射
        for p in players:
            _player_battles[p.id] = self  # 直接存储实例引用
        
        self.battle_type = battle_type
        self.players = [BattleActor(p) for p in players]
        self.enemies = [BattleActor(e, False) for e in enemies]
        self.turn = 0
        self.last_active = datetime.now()
        self.actions = {}
        self.logs = []
        self.latest_event = latest_event
        self.max_logs = 5  # 只保留最近5回合日志

    @property
    def is_expired(self) -> bool:
        return (datetime.now() - self.last_active).seconds > _BATTLE_TIMEOUT

    async def process_turn(self):
        """优化后的回合处理逻辑"""
        self.turn += 1
        self.last_active = datetime.now()
        
        # 等待所有存活玩家提交行动
        await self._wait_for_actions()
        
        # 合并所有存活的参与者并按敏捷排序
        all_actors = self.players + self.enemies
        actors = sorted(
            [a for a in all_actors if a.hp > 0],
            key=lambda x: x.agility,
            reverse=True
        )
        
        battle_log = []
        for actor in actors:
            if not actor.hp > 0:
                continue
            
            # 玩家行动
            if actor.is_player:
                if action := self.actions.get(actor.id):
                    act_type, value = action
                    if act_type == "attack":
                        target_id = value
                        await self._handle_player_attack_action(actor, act_type, target_id, battle_log)
                    elif act_type == "use_item":
                        item_id = value
                        await self._handle_use_item_action(actor, item_id, battle_log)
            # 敌人行动
            else:
                await self._handle_enemy_action(actor, battle_log)
        
        # 生成回合报告
        report = create_rich_message(
            f"🌀 第{self.turn}回合结算：\n" +
            "\n".join(battle_log) + "\n\n" +
            "👥 己方状态：\n" + 
            "\n".join([f"{'💀' if p.hp <=0 else '👤'} {p.name} ❤️ {p.hp if p.hp>0 else 0}/{p.max_hp}\n🔵 {p.mp}/{p.max_mp}" 
                      for p in self.players]) + 
            "\n👹 敌方状态：\n" +
            "\n".join([f"{'💀' if e.hp <=0 else '👹'} {e.name} ❤️ {e.hp if e.hp>0 else 0}/{e.max_hp}" 
                      for e in self.enemies])
        )
        
        # 处理战斗结果
        if all(e.hp <= 0 for e in self.enemies):
            return "players_win", report
        if all(p.hp <= 0 for p in self.players):
            return "enemies_win", report
        return "continue", report

    async def _wait_for_actions(self):
        """等待所有存活玩家提交行动（无超时）"""
        while True:
            alive_players = [p.id for p in self.players if p.hp > 0]
            if len(self.actions) >= len(alive_players):
                return
            await asyncio.sleep(1)

    async def _handle_player_attack_action(self, actor: BattleActor, act_type: str, target_id: str, battle_log: list):
        """玩家行动处理"""
        target = next((e for e in self.enemies if e.id == target_id), None)
        if not target:
            return
        if act_type == "attack":
            # 计算伤害（加入暴击和闪避判定）
            is_crit = random.random() < (actor.luck / 1000)
            is_dodge = random.random() > actor.calculate_hit_chance(target)
            
            if is_dodge:
                log = f"✨ {target.name} 灵巧地躲过了攻击！"
            else:
                actual_attack = int(actor.attack * random.uniform(0.8, 1.2))
                damage = max(max(1,int(actual_attack * 0.1)), actual_attack - target.defense)
                if is_crit:
                    damage = int(damage * 1.5)
                target.hp = max(0, target.hp - damage)
                
                crit_mark = "💥触发暴击" if is_crit else ""
                log = f"{crit_mark}{actor.name} ➔ {target.name} 造成{damage}点伤害！"
        
        battle_log.append(log)

    async def _handle_enemy_action(self, enemy: BattleActor, battle_log: list):
        """敌人每回合随机选择行动"""
        valid_players = [p for p in self.players if p.hp > 0]
        if not valid_players:
            return
        
        # 根据概率随机选择行动类型
        action_type = random.choices(
            ['normal', 'skill', 'debuff'],
            weights=enemy.action_weights,
            k=1
        )[0]

        # 选择目标策略：优先攻击血量最低的玩家
        target = min(valid_players, key=lambda x: x.hp)
        
        # 根据随机结果执行不同行动
        if action_type == 'normal':
            await self._handle_normal_attack(enemy, target, battle_log)
        elif action_type == 'skill':
            await self._handle_skill_attack(enemy, target, battle_log)
        else:
            await self._handle_debuff_attack(enemy, target, battle_log)

    async def _handle_normal_attack(self, attacker: BattleActor, target: BattleActor, battle_log):
        """普通攻击处理"""
        hit_chance = attacker.calculate_hit_chance(target)
        if random.random() > hit_chance:
            battle_log.append(f"✨ {target.name} 灵巧地躲过了 {attacker.name} 的反击！")
            return
        actual_attack = int(attacker.attack * random.uniform(0.8, 1.2))
        damage = max(max(1,int(actual_attack * 0.1)), actual_attack - target.defense)
        target.hp = max(0, target.hp - damage)
        battle_log.append(f"👹 {attacker.name} 反击 {target.name} 造成 {damage} 伤害！")

    async def _handle_debuff_attack(self, attacker, target, battle_log):
        """异常状态攻击"""
        hit_chance = attacker.calculate_hit_chance(target) * 0.8  # 技能命中率较低
        if random.random() > hit_chance:
            battle_log.append(f"✨ {target.name} 抵抗了 {attacker.name} 的异常攻击！")
            return
            
        # 随机选择debuff（示例）
        debuff = random.choice(["中毒", "虚弱", "恐惧"])
        battle_log.append(f"☠️ {attacker.name} 使 {target.name} 陷入【{debuff}】状态！")
        # 这里可以扩展debuff的持续效果存储

    async def _handle_skill_attack(self, attacker, target, battle_log):
        """技能攻击（更高伤害但命中率较低）"""
        hit_chance = attacker.calculate_hit_chance(target) * 0.7
        if random.random() > hit_chance:
            battle_log.append(f"✨ {target.name} 惊险躲过了 {attacker.name} 的技能！")
            return
        
        damage = int((attacker.attack * 1.5 - target.defense) * random.uniform(0.8, 1.2))
        target.hp = max(0, target.hp - damage)
        battle_log.append(f"🔥 {attacker.name} 发动技能攻击！对 {target.name} 造成 {damage} 伤害！")

    async def _handle_use_item_action(self, actor: BattleActor, item_id: str, battle_log: list):
        """处理玩家使用物品的行动"""
        async with safe_session() as session:
            # 获取物品配置
            item_config = config.items_config["by_id"].get(item_id)
            if not item_config:
                battle_log.append(f"⛔ {actor.name} 使用了未知的物品")
                return

            # 从玩家背包中扣除物品
            inventory = await session.execute(
                select(Inventory)
                .where(Inventory.player_id == actor.id)
                .where(Inventory.item_id == item_id)
            )
            inventory = inventory.scalars().first()

            if not inventory or inventory.quantity <= 0:
                battle_log.append(f"⛔ {actor.name} 发现没有 {item_config.name}，无法使用")
                return

            # 应用物品效果
            effect_type = item_config.effect_type
            effect_params = item_config.effect_params

            if effect_type == ItemEffectType.RESTORE_HP:
                restore_amount = effect_params.get("value", 0)
                actor.hp = min(actor.max_hp, actor.hp + restore_amount)
                battle_log.append(f"💊 {actor.name} 使用了 {item_config.name}，恢复了 {restore_amount} 点生命值")
            elif effect_type == ItemEffectType.RESTORE_MP:
                restore_amount = effect_params.get("value", 0)
                actor.mp = min(actor.max_mp, actor.mp + restore_amount)
                battle_log.append(f"💊 {actor.name} 使用了 {item_config.name}，恢复了 {restore_amount} 点理智值")
            else:
                battle_log.append(f"⚠️ {actor.name} 使用了 {item_config.name}，但似乎没有任何效果")

            # 扣除物品数量
            inventory.quantity -= 1
            if inventory.quantity <= 0:
                await session.delete(inventory)
            else:
                session.add(inventory)

            await session.commit()

    def _add_log(self, log: str):
        """优化日志存储"""
        if len(self.logs) >= self.max_logs:
            self.logs.pop(0)
        self.logs.append(log)

async def generate_enemy_by_region(region_name: str, player_level: int) -> List[Dict]:
    """根据地区生成敌人"""
    from ..config import config
    
    region = next((r for r in config.map_config["regions"] if r["name"] == region_name), None)
    if not region:
        raise ValueError(f"地区 {region_name} 不存在")
    
    enemies = []
    for _ in range(random.randint(1, 3)):  # 随机1-3个敌人
        monster = random.choice(region["monsters"])
        level = min(max(player_level, region["level_range"][0]), region["level_range"][1])
        
        enemy = {
            "name": f"{monster['name']}",
            "level": level,
            "max_hp": monster["base_hp"] + level * 5,
            "attack": monster["base_attack"] + level * 2,
            "defense": monster["base_defense"] + level,
            "agility": monster["base_agility"] + level,
            "skills": monster.get("skills", []),
            "drops": monster.get("drops", []),
            "action_weights": (100, 0, 0)  # 默认行动权重
        }
        enemies.append(enemy)
    return enemies

async def send_battle_ui(battle: BattleInstance, event: MessageEvent):
    """生成美观的战斗界面"""
    # 启动战斗循环
    asyncio.create_task(battle_loop(battle, event))
    enemy_info = "\n".join([
        f"{idx+1}. {'💀' if e.hp <=0 else '👹'} {e.name} ❤️ {e.hp if e.hp>0 else 0}/{e.max_hp} | ⚡ {e.agility}"
        for idx, e in enumerate(battle.enemies)
    ])
    player_info = "\n".join([
        f"{'💀' if p.hp <=0 else '👤'} {p.name} ❤️ {p.hp if p.hp>0 else 0}/{p.max_hp}\n🔵 {p.mp}/{p.max_mp}"
        for p in battle.players
    ])
    
    msg = (
        f"⚔️ {'组队' if battle.battle_type == 'TEAM' else '单人'}战斗开始！\n"
        f"------------------------\n"
        f"{player_info}\n"
        f"------------------------\n"
        f"VS\n"
        f"------------------------\n"
        f"{enemy_info}\n"
        f"------------------------\n"
        f"可用指令：\n"
        f"攻击 序号 | 使用 道具名"
    )
    await explore_cmd.finish(create_rich_message(msg, event))

async def battle_loop(battle: BattleInstance, event: MessageEvent):
    """优化后的战斗主循环"""
    try:
        bot = get_bot()
        while True:
            # 处理回合
            result, report = await battle.process_turn()
            
            # 发送回合报告到最新上下文
            if battle.latest_event:
                await bot.send(battle.latest_event, report)

            # 处理战斗结果
            if result != "continue":
                async with safe_session() as session:
                    # +++ 战斗结束前强制保存所有玩家状态 +++
                    for actor in battle.players:
                        player = await session.get(Player, actor.id)
                        if player:
                            player.hp = max(0, actor.hp)
                            player.mp = max(0, actor.mp)
                            session.add(player)
                    await session.commit()
                # +++ 保存结束 +++
                
                if result == "players_win":
                    # 奖励处理
                    total_exp, drops = await process_battle_rewards(battle)
                    result_msg = (
                        "🎉 战斗胜利！\n"
                        f"📈 获得总经验：{total_exp}\n"
                        f"🎁 获得战利品：{', '.join(drops) if drops else '无'}"
                    )
                else:
                    # 遍历所有玩家，检查是否死亡
                    async with safe_session() as session:
                        for actor in battle.players:
                            if actor.hp <= 0:
                                player = await session.get(Player, actor.id)
                                if player:
                                    # 计算复活代价
                                    gold_loss = int(player.gold * 0.05)
                                    exp_loss = int(player.exp * 0.05)
                                    player.gold -= gold_loss
                                    player.exp -= exp_loss
                                    # 设置玩家为死亡状态，需要复活
                                    player.is_dead = True
                                    session.add(player)
                                    await bot.send(
                                        battle.latest_event,
                                        f"💀 {player.nickname} 已战败！损失 {gold_loss}💰 和 {exp_loss} 修为。\n" +
                                        "👉 输入指令【复活】选择复活方式。"
                                    )
                        session.commit()
                    result_msg = "💀 战斗失败，敌人获得了胜利..."
                
                await bot.send(battle.latest_event, result_msg)

                # 清理缓存
                for p in battle.players:
                    _player_battles.pop(p.id, None)

                return
                
            # 重置行动记录
            battle.actions.clear()
            
            # 减少循环间隔（原5秒改为1秒）
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        # 清理过期的战斗
        for p in battle.players:
            _player_battles.pop(p.id, None)

@explore_cmd.handle()
async def handle_explore(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await explore_cmd.finish("⛔ 请先创建角色")
            
        if player.battle_mode == "TEAM":
            # 获取队伍信息
            team_member = await session.execute(
                select(TeamMember)
                .options(joinedload(TeamMember.team).joinedload(Team.members))
                .where(TeamMember.player_id == user_id)
            )
            team_member = team_member.scalars().first()
            
            if not team_member:
                await explore_cmd.finish("⛔ 组队模式需要先加入队伍")
                
            if team_member.team.leader_id != user_id:
                await explore_cmd.finish("⛔ 只有队长可以发起组队探索")
                
            if not await team_manager.can_start_team_explore(session, team_member.team.id):
                await explore_cmd.finish("⛔ 队伍成员不满足条件：1.全部组队模式 2.不在战斗中 3.同一地区")
                
            # 检查队员是否在战斗中（通过缓存）
            for member in team_member.team.members:
                if member.player.id in _player_battles:
                    await explore_cmd.finish(f"⛔ 队员 {member.player.nickname} 正在战斗中")
            
            # 生成基于队伍平均等级的敌人
            members_level = [m.player.level for m in team_member.team.members]
            avg_level = sum(members_level) // len(members_level)
            enemies = await generate_enemy_by_region(player.position, avg_level)
            
            # 创建组队战斗
            battle = BattleInstance(
                "TEAM", 
                [m.player for m in team_member.team.members],
                enemies,
                event
            )
            
        else:  # 个人模式
            if user_id in _player_battles:
                await explore_cmd.finish("⛔ 你已经在战斗中")
                
            enemies = await generate_enemy_by_region(player.position, player.level)
            battle = BattleInstance("SOLO", [player], enemies, event)
        
        await session.commit()
        await send_battle_ui(battle, event)

@attack_cmd.handle()
async def handle_attack(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    battle = _player_battles.get(user_id)
    
    if not battle or battle.is_expired:
        await attack_cmd.finish("⛔ 你当前没有参与战斗")
    if battle.actions.get(user_id, None):
        return

    # 更新玩家最新消息上下文
    battle.latest_event = event
    
    # 解析攻击目标（按序号）
    arg = args.extract_plain_text().strip()
    
    try:
        if not arg:  # 无参数时选择第一个存活的敌人
            if not battle.enemies:
                await attack_cmd.finish("⚠️ 战场上已无敌人")
            # 寻找第一个存活的敌人
            for enemy in battle.enemies:
                if enemy.hp > 0:
                    target = enemy
                    break
            else:
                await attack_cmd.finish("⚠️ 所有敌人都已被击败")
        else:
            # 尝试转换为数字序号
            index = int(arg) - 1
            if index < 0 or index >= len(battle.enemies):
                raise ValueError
            target = battle.enemies[index]
            
    except ValueError:
        # 生成带序号的敌人列表提示
        enemy_list = "\n".join([f"{i+1}. {e.name}" for i, e in enumerate(battle.enemies)])
        await attack_cmd.finish(f"⛔ 请输入有效序号：\n{enemy_list}")

    # 记录行动
    battle.actions[user_id] = ('attack', target.id)
    await attack_cmd.finish(f"✅ 已锁定目标 {target.name}，等待回合结算")

@use_item_cmd.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    battle = _player_battles.get(user_id)
    
    if not battle or battle.is_expired:
        await use_item_cmd.finish("⛔ 你当前没有参与战斗")
    if battle.actions.get(user_id, None):
        await use_item_cmd.finish("⛔ 你已经提交了本回合的行动")
    
    # 更新玩家最新消息上下文
    battle.latest_event = event
    
    # 解析使用的物品名称
    item_name = args.extract_plain_text().strip()
    if not item_name:
        await use_item_cmd.finish("⛔ 请输入要使用的物品名称")
    
    # 获取玩家背包中是否有该物品
    async with safe_session() as session:
        # 获取玩家背包
        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == user_id)
        )
        inventories = result.scalars().all()
        inventory = next((inv for inv in inventories if inv.config.name == item_name), None)
        
        if not inventory or inventory.quantity <= 0:
            await use_item_cmd.finish(f"⛔ 你的背包中没有 {item_name}")
        
        # 检查物品是否可在战斗中使用
        item_config = inventory.config
        if item_config.type != ItemType.CONSUMABLE:
            await use_item_cmd.finish("⛔ 该物品无法在战斗中使用")
        
        # 记录玩家的使用物品行动
        battle.actions[user_id] = ('use_item', item_config.item_id)
        await use_item_cmd.finish(f"✅ 已选择使用 {item_name}，等待回合结算")

async def process_battle_rewards(battle: BattleInstance) -> tuple:
    """处理战斗奖励（经验+掉落）"""
    from ..models.inventory import Inventory
    from ..models.player import Player
    from ..config import config  # 添加导入
    
    total_exp = 0
    all_drops = {}  # 改为字典统计数量和名称
    alive_players = [p for p in battle.players if p.hp > 0]
    
    # 计算怪物平均等级
    monster_levels = [e.level for e in battle.enemies]
    avg_monster_level = sum(monster_levels) / len(monster_levels) if monster_levels else 0

    async with safe_session() as session:
        # 处理经验分配
        for enemy in battle.enemies:
            # 基础经验 = 怪物等级 * 基础经验系数
            base_exp = enemy.level * config.game_config["base_exp_per_level"]
            
            # 组队经验加成
            if battle.battle_type == "TEAM":
                base_exp *= (1 + config.game_config["team"]["team_exp_bonus"])
            
            total_exp += base_exp

        # 按存活玩家数平均分配
        per_player_exp = total_exp / len(alive_players) if alive_players else 0

        # 更新玩家经验（考虑等级差衰减）
        for actor in alive_players:
            player = await session.get(Player, actor.id)
            if not player:
                continue
            
            # 计算等级差系数
            level_diff = avg_monster_level - player.level
            if level_diff < -config.game_config["team"]["max_level_diff"]:
                exp_multiplier = config.game_config["team"]["min_exp_multiplier"]
            else:
                exp_multiplier = max(
                    config.game_config["team"]["min_exp_multiplier"],
                    1 - (max(level_diff, 0) / (config.game_config["team"]["max_level_diff"] * 2))
                )
            
            gained_exp = int(per_player_exp * exp_multiplier)
            player.exp += gained_exp
            session.add(player)

        # 处理掉落物
        for enemy in battle.enemies:
            for drop in enemy.drops:
                # 获取物品配置
                item_config = config.items_config["by_id"].get(drop["item_id"])
                if not item_config:
                    continue
                
                # 共享模式：全队获得相同掉落
                if config.game_config["team"]["loot_strategy"] == "SHARED":
                    if random.random() <= drop["chance"]:
                        # 统计总数量（存活玩家数 x 1）
                        all_drops[item_config.name] = all_drops.get(item_config.name, 0) + len(alive_players)
                        
                        # 实际添加物品到背包
                        for actor in alive_players:
                            inv = await session.execute(
                                select(Inventory)
                                .where(Inventory.player_id == actor.id)
                                .where(Inventory.item_id == drop["item_id"])
                            )
                            inv = inv.scalars().first()
                            if inv:
                                inv.quantity += 1
                            else:
                                inv = Inventory(
                                    player_id=actor.id,
                                    item_id=drop["item_id"],
                                    quantity=1
                                )
                            session.add(inv)
                
                # 随机模式：每个玩家独立判定
                else:  
                    for actor in alive_players:
                        if random.random() <= drop["chance"]:
                            # 统计数量
                            all_drops[item_config.name] = all_drops.get(item_config.name, 0) + 1
                            
                            inv = await session.execute(
                                select(Inventory)
                                .where(Inventory.player_id == actor.id)
                                .where(Inventory.item_id == drop["item_id"])
                            )
                            inv = inv.scalars().first()
                            if inv:
                                inv.quantity += 1
                            else:
                                inv = Inventory(
                                    player_id=actor.id,
                                    item_id=drop["item_id"],
                                    quantity=1
                                )
                            session.add(inv)

        await session.commit()
    
    # 格式化掉落物显示
    formatted_drops = [f"{name}×{count}" for name, count in all_drops.items()]
    return int(total_exp), formatted_drops

# 组队命令
team_cmd = on_command("队伍", block=True, priority=5)
join_cmd = on_command("加入队伍", block=True, priority=5)
disband_cmd = on_command("解散队伍", block=True, priority=5)
leave_cmd = on_command("退出队伍", block=True, priority=5)
kick_cmd = on_command("踢出队员", block=True, priority=5)
mode_cmd = on_command("探索模式", block=True, priority=5)

# 组队系统缓存
_team_invitations: Dict[int, Dict[str, datetime]] = {}  # {队伍ID: {受邀者ID: 过期时间}}

# 定时清理任务
@scheduler.scheduled_job("interval", minutes=1)
def _clean_expired_invitations():
    now = datetime.now()
    expired_count = 0
    for team_id in list(_team_invitations.keys()):
        invites = _team_invitations[team_id]
        # 保留未过期的邀请
        valid_invites = {k: v for k, v in invites.items() if v > now}
        if valid_invites:
            _team_invitations[team_id] = valid_invites
        else:
            del _team_invitations[team_id]
            expired_count += 1
    logger.info(f"🧹 已清理过期邀请，本次清理{expired_count}个过期队伍邀请")

# 组队功能
class TeamManager:
    """基于数据库的组队管理器"""
    async def create_team(self, session: AsyncSession, leader_id: str) -> Team:
        # 检查玩家是否已经在其他队伍中
        existing_member = await session.execute(
            select(TeamMember).where(TeamMember.player_id == leader_id)
        )
        if existing_member.scalars().first():
            raise ValueError("你已加入其他队伍，请先退出")

        # 检查是否已创建过队伍
        existing_team = await session.execute(
            select(Team).where(Team.leader_id == leader_id)
        )
        if existing_team.scalars().first():
            raise ValueError("每个玩家只能创建一个队伍")
        
        # 创建新队伍
        new_team = Team(leader_id=leader_id)
        session.add(new_team)
        await session.flush()  # 获取自动生成的team_id

        # 添加队长为成员
        session.add(TeamMember(team_id=new_team.id, player_id=leader_id))
        await session.commit()
        return new_team

    async def join_team(self, session: AsyncSession, team_id: int, member_id: str) -> bool:
        # 检查：是否已加入其他队伍
        existing_member = await session.execute(
            select(TeamMember).where(TeamMember.player_id == member_id)
        )
        if existing_member.scalars().first():
            raise ValueError("你已加入其他队伍，请先退出")

        # 检查邀请有效性
        if not self._is_valid_invitation(team_id, member_id):
            return False

        # 获取当前队伍人数
        current_members = await session.execute(
            select(TeamMember).where(TeamMember.team_id == team_id)
        )
        if current_members and len(current_members.scalars().all()) >= config.game_config["team"]["max_members"]:
            raise ValueError(f"队伍人数已达上限（{config.game_config['team']['max_members']}人）")

        # 检查是否已在队伍中
        existing = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.player_id == member_id
            )
        )
        if existing.scalars().first():
            return False

        # 添加成员
        session.add(TeamMember(team_id=team_id, player_id=member_id))
        await session.commit()

        # 加入成功后移除对应邀请
        if team_id in _team_invitations and member_id in _team_invitations[team_id]:
            del _team_invitations[team_id][member_id]
            if not _team_invitations[team_id]:
                del _team_invitations[team_id]

        return True

    async def get_team(self, session: AsyncSession, team_id: int) -> Optional[Team]:
        result = await session.execute(
            select(Team)
            .options(joinedload(Team.members).joinedload(TeamMember.player))
            .where(Team.id == team_id)
        )
        return result.scalars().first()

    def _is_valid_invitation(self, team_id: int, member_id: str) -> bool:
        """检查邀请是否有效"""
        now = datetime.now()
        print(f"检查邀请: {team_id}, {member_id}, {_team_invitations[team_id]}")
        return (
            team_id in _team_invitations and 
            member_id in _team_invitations[team_id] and 
            _team_invitations[team_id][member_id] > now
        )

    async def disband_team(self, session: AsyncSession, team_id: int):
        """解散队伍"""
        # 删除队伍和成员
        await session.execute(delete(TeamMember).where(TeamMember.team_id == team_id))
        await session.execute(delete(Team).where(Team.id == team_id))
        # 清理邀请缓存
        _team_invitations.pop(team_id, None)
        await session.commit()

    async def leave_team(self, session: AsyncSession, user_id: str) -> bool:
        """退出队伍，返回是否成功"""
        # 获取用户所在队伍
        member = await session.execute(
            select(TeamMember)
            .options(joinedload(TeamMember.team))
            .where(TeamMember.player_id == user_id)
        )
        member = member.scalars().first()
        if not member:
            return False

        team = member.team
        if team.leader_id == user_id:  # 队长退出等于解散队伍
            await self.disband_team(session, team.id)
            return True
        else:  # 普通成员退出
            await session.delete(member)
            await session.commit()
            return True

    async def kick_member(self, session: AsyncSession, leader_id: str, target_uid: str) -> bool:
        """踢出队员"""
        # 验证操作者是队长
        team = await session.execute(
            select(Team).where(Team.leader_id == leader_id)
        )
        team = team.scalars().first()
        if not team:
            return False
        target = await get_player_by_uid(target_uid)
        # 删除目标成员
        result = await session.execute(
            delete(TeamMember)
            .where(TeamMember.team_id == team.id)
            .where(TeamMember.player_id == target.id)
        )
        if result.rowcount == 0:
            return False
        await session.commit()
        return True

    async def can_start_team_explore(self, session: AsyncSession, team_id: int) -> bool:
        """检查队伍是否可以开始探索"""
        team = await self.get_team(session, team_id)
        if not team:
            return False

        # 检查所有队员状态
        for member in team.members:
            player = member.player
            if (player.battle_mode != "TEAM" or 
                player.id in _player_battles or  # 通过缓存检查战斗状态
                player.position != team.leader.position):
                return False
        return True

team_manager = TeamManager()

# 优化组队命令处理
@team_cmd.handle()
async def handle_team(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    user_id = event.get_user_id()
    
    async with safe_session() as session:
        if arg == "创建":
            try:
                team = await team_manager.create_team(session, user_id)
                msg = f"✅ 队伍创建成功！队伍ID：{team.id}"
            except ValueError as e:
                msg = f"⛔ {str(e)}"
            await team_cmd.finish(msg)
            
        elif arg.startswith("邀请"):
            target_uid = arg[2:].strip()
            # 获取当前用户的队伍
            team = await session.execute(
                select(Team).where(Team.leader_id == user_id)
            )
            team = team.scalars().first()
            if not team:
                await team_cmd.finish("⛔ 请先创建队伍")
            target_player = await get_player_by_uid(target_uid)
            if not target_player:
                await team_cmd.finish("⛔ 目标玩家不存在")

            # 存储到内存邀请缓存（保留3分钟）
            _team_invitations.setdefault(team.id, {})
            _team_invitations[team.id][target_player.id] = datetime.now() + timedelta(minutes=3)
            await team_cmd.finish(f"📨 已向玩家 {target_uid} 发送组队邀请，有效期3分钟\n 队伍ID：{team.id}")

        elif arg == "解散":
            # 获取用户队伍
            team = await session.execute(
                select(Team).where(Team.leader_id == user_id)
            )
            team = team.scalars().first()
            if not team:
                await team_cmd.finish("⛔ 你还没有创建队伍")
                return
            
            await team_manager.disband_team(session, team.id)
            await team_cmd.finish("🗑️ 队伍已解散")

@join_cmd.handle()
async def handle_join(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    arg = args.extract_plain_text().strip()
    
    if not arg.isdigit():
        await join_cmd.finish("⛔ 请输入正确的队伍ID")
    team_id = int(arg)
    
    async with safe_session() as session:
        team = await team_manager.get_team(session, team_id)
        if not team:
            await join_cmd.finish("⛔ 队伍不存在")
        
        try:
            if await team_manager.join_team(session, team_id, user_id):
                # 获取队伍成员信息
                members = [m.player.nickname for m in team.members]
                await join_cmd.finish(f"✅ 成功加入队伍！队伍成员：{'、'.join(members)}")
            else:
                await join_cmd.finish("⛔ 加入失败，请确认邀请是否有效")
        except ValueError as e:
            await join_cmd.finish(f"⛔ {str(e)}")

@disband_cmd.handle()
async def handle_disband(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取用户队伍
        team = await session.execute(
            select(Team).where(Team.leader_id == user_id)
        )
        team = team.scalars().first()
        if not team:
            await disband_cmd.finish("⛔ 你还没有创建队伍或不是队长")
            return

        await team_manager.disband_team(session, team.id)
        await disband_cmd.finish("🗑️ 队伍已解散")

@leave_cmd.handle()
async def handle_leave(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        success = await team_manager.leave_team(session, user_id)
        if not success:
            await leave_cmd.finish("⛔ 你当前没有加入任何队伍")
            return
        await leave_cmd.finish("🚪 你已退出队伍")

@kick_cmd.handle()
async def handle_kick(event: MessageEvent, args: Message = CommandArg()):
    target_uid = args.extract_plain_text().strip()
    if not target_uid.isdigit():
        await kick_cmd.finish("⛔ 请输入正确的UID")
    
    user_id = event.get_user_id()
    async with safe_session() as session:
        success = await team_manager.kick_member(session, user_id, target_uid)
        if not success:
            await kick_cmd.finish("⛔ 踢出失败，请确认你是队长且目标在队伍中")
            return
        await kick_cmd.finish(f"👢 已踢出玩家 {target_uid}")

@mode_cmd.handle()
async def handle_mode(event: MessageEvent, args: Message = CommandArg()):
    mode_map = {
        "个人": "SOLO",
        "组队": "TEAM"
    }
    
    mode = args.extract_plain_text().strip()
    if mode not in mode_map:
        await mode_cmd.finish("⛔ 无效模式，可选：个人/组队")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        player.battle_mode = mode_map[mode]
        await session.commit()
        
    await mode_cmd.finish(f"✅ 已切换为【{mode}】探索模式")

# 添加查看队伍信息的命令
team_info_cmd = on_command("查看队伍", block=True, priority=5)

@team_info_cmd.handle()
async def handle_team_info(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取用户所在的队伍
        team_member = await session.execute(
            select(TeamMember)
            .options(joinedload(TeamMember.team).joinedload(Team.members).joinedload(TeamMember.player))
            .where(TeamMember.player_id == user_id)
        )
        team_member = team_member.scalars().first()
        if not team_member:
            await team_info_cmd.finish("⛔ 你当前没有加入任何队伍")
            return
        team = team_member.team
        # 获取队伍成员信息
        members = [f"{'队长' if m.player.id == team.leader_id else '队员'}：{m.player.nickname} (UID: {m.player.uid})" for m in team.members]
        msg = (
            f"🔍 队伍ID: {team.id}\n"
            f"👥 成员列表：\n" +
            "\n".join(members)
        )
        await team_info_cmd.finish(msg)

revive_cmd = on_command("复活", block=True, priority=5)

@revive_cmd.handle()
async def handle_revive(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player or not player.is_dead:
            await revive_cmd.finish("⚠️ 你当前不需要复活。")

        args = event.get_plaintext().strip()
        if args == "原地复活":
            # 检查玩家是否有足够的金币或复活道具
            revival_cost = 500  # 假设原地复活需要500金币
            if player.gold >= revival_cost:
                player.gold -= revival_cost
                player.hp = player.max_hp
                player.mp = player.max_mp
                player.is_dead = False
                session.add(player)
                await session.commit()
                await revive_cmd.finish(f"✨ 你支付了 {revival_cost}💰，原地满状态复活！")
            else:
                await revive_cmd.finish("💰 金币不足，无法原地复活。")

        elif args == "复活点复活":
            # 设置玩家状态，传送回主城，并设置冷却时间
            player.hp = int(player.max_hp * 0.5)
            player.mp = int(player.max_mp * 0.5)
            player.position = "主城"
            player.is_dead = False
            session.add(player)
            await session.commit()
            await revive_cmd.finish("🏙️ 你在复活点复活，生命值和理智值恢复50%，已被传送回主城。")
        else:
            await revive_cmd.finish("📝 请输入复活方式：原地复活 或 复活点复活。")
        
