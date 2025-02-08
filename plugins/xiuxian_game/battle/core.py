from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from .skills import SkillManager
from nonebot_plugin_statemachine import StateMachine
from ..models.player import Player

battle = on_command("战斗", block=True, priority=5)

@battle.handle()
async def handle_battle(event: MessageEvent, args: Message = CommandArg()):
    # 示例战斗流程
    user_id = event.get_user_id()
    group_id = event.get_session_id().split("_")[1]
    
    # 获取玩家数据
    player = await get_player(user_id)
    
    # 初始化战斗
    await battle.send(f"🩸 你遭遇了诡异生物！\n生命：{player.hp} | 境界：{player.cultivation}")
    
    # 使用状态机管理战斗流程
    while True:
        # 处理玩家输入
        # 战斗逻辑...
        break 

class BattleState(StateMachine):
    def __init__(self, player: Player):
        self.player = player
        self.states = {
            'start': self.on_start,
            'attack': self.on_attack,
            'defend': self.on_defend
        }
    
    async def on_start(self):
        return "🩸 选择你的行动：\n1️⃣ 攻击\n2️⃣ 防御"
    
    async def on_attack(self):
        # 攻击逻辑
        return "💥 你发动了凌厉的攻势！" 