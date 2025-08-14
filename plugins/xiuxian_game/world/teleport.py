"""
传送系统模块

处理玩家在现实世界和诡域之间的传送功能
支持无限层诡域爬塔系统
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..models.navigation_task import NavigationTask
from ..config import config
from ..utils import message_add_head


# 传送指令
teleport_cmd = on_command("传送", block=True, priority=5)
enter_cmd = on_command("进入", block=True, priority=5)
revive_cmd = on_command("返回", aliases={"复活"}, block=True, priority=5)


@teleport_cmd.handle()
async def handle_teleport(event: MessageEvent, args: Message = CommandArg()):
    """处理传送指令，支持进入层级制诡域"""
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await teleport_cmd.finish("⛔ 请指定目标，例如：传送 1层诡域")

    # 调用共同的传送处理函数
    await _handle_teleport_logic(event, target_region, teleport_cmd)


@enter_cmd.handle()
async def handle_enter(event: MessageEvent, args: Message = CommandArg()):
    """处理进入指令，支持进入层级制诡域"""
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await enter_cmd.finish("⛔ 请指定目标，例如：进入 1层诡域")

    # 调用共同的传送处理函数
    await _handle_teleport_logic(event, target_region, enter_cmd)


async def _handle_teleport_logic(event: MessageEvent, target_region: str, cmd_handler):
    """共同的传送处理逻辑"""
    # 检查是否为层级诡域格式
    if target_region.endswith("层诡域"):
        try:
            level_str = target_region.replace("层诡域", "")
            dungeon_level = int(level_str)
        except ValueError:
            await cmd_handler.finish("⛔ 诡域层级格式错误，请使用：1层诡域")

        # 验证层级范围
        if dungeon_level <= 0:
            await cmd_handler.finish("⛔ 诡域层级必须大于0")
        
        # 动态生成层级配置（支持无限层）
        dungeon_config = config._generate_dungeon_level_config(
            dungeon_level, 
            config.map_config.get("dungeon_generation_rules", {})
        )
    else:
        # 兼容旧的命名诡域（如果还有的话）
        valid_regions = list(config.map_config.get("regions", {}).keys())
        if target_region not in valid_regions:
            await cmd_handler.finish("⛔ 目的地不存在，请使用：N层诡域")
        dungeon_level = None
        dungeon_config = config.map_config["regions"].get(target_region)

    STAM_COST = 1  # 咒抗消耗

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await cmd_handler.finish("⛔ 请先创建角色")

        # 检查层级解锁限制（爬塔系统）
        if dungeon_level:
            if not player.can_enter_dungeon_level(dungeon_level):
                max_level = player.max_dungeon_level or 0
                accessible_levels = player.get_accessible_dungeon_levels()
                await cmd_handler.finish(
                    f"⛔ 无法进入第{dungeon_level}重里世界！\n"
                    f"━━━━━━━━━━━━━\n"
                    f"📊 当前最深探索：第{max_level}重里世界\n"
                    f"🔓 可进入深度：{accessible_levels}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💡 需要逐重击败守护者解锁更深的里世界\n"
                    f"⬇️ 【进入 {max_level + 1}层诡域】探索下一重空间"
                )
        else:
            # 兼容旧系统的等级检查
            if dungeon_config:
                required_level = dungeon_config.get("required_level", 1)
                if player.level < required_level:
                    await cmd_handler.finish(f"⛔ 你的修为不足以进入『{target_region}』，需要达到 Lv.{required_level}")

        if player.stamina < STAM_COST:
            await cmd_handler.finish(f"⛔ 你的咒抗不足以在传送过程中维持清醒，需要 {STAM_COST}，当前 {player.stamina}")
        if player.hp < 5:
            await cmd_handler.finish(f"⛔ 你的生命值过低：当前 {player.hp}/{player.max_hp}")
        
        # 查询是否存在导航任务
        nav_task: NavigationTask | None = await session.get(NavigationTask, player.id)

        # 扣除咒抗
        player.stamina -= STAM_COST
        
        # 使用新的双层坐标系统
        if dungeon_level:
            # 进入层级诡域
            player.enter_dungeon(dungeon_level)
            target_name = f"{dungeon_level}层诡域"
            current_pos = f"({player.dungeon_x},{player.dungeon_y})"
        else:
            # 兼容旧系统
            player.region = target_region
            target_name = target_region
            current_pos = f"({player.x},{player.y})"
        
        session.add(player)
        
        # 若有导航则删除
        if nav_task:
            await session.delete(nav_task)

        await session.commit()

    msg_lines = [
        f"🚪 你耗费 {STAM_COST} 咒抗跨越裂隙，抵达『{target_name}』",
        f"当前位置：{target_name} {current_pos}",
    ]
    if nav_task:
        msg_lines.insert(1, "🛑 原导航任务已中断")
    
    if dungeon_level:
        msg_lines.append("━━━━━━━━━━━━━")
        msg_lines.append("🌀 你穿越了空间裂隙，进入了里世界")
        msg_lines.append("🗺️ 这是一个10x10的独立空间")
        msg_lines.append("📍 坐标范围：(-5,-5) 到 (5,5)")
        msg_lines.append("🧭 使用【上下左右】移动，【探索】调查")
        msg_lines.append("🏠 使用【返回】穿越回表世界")
    
    msg = "\n".join(msg_lines)
    await cmd_handler.finish(message_add_head(msg, event))


@revive_cmd.handle()
async def handle_revive(event: MessageEvent):
    """处理返回指令，退出诡域返回现实世界"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await revive_cmd.finish("⛔ 请先创建角色")
        
        # 记录返回前的位置信息
        was_in_dungeon = player.is_in_dungeon()
        dungeon_level = player.dungeon_level if was_in_dungeon else 0
        
        # 恢复满状态
        player.hp = player.max_hp
        player.mp = player.max_mp
        
        # 使用新的双层坐标系统退出诡域
        player.exit_dungeon()
        
        session.add(player)
        await session.commit()
        
        # 构建返回消息
        msg_lines = [
            "✨ 你从破碎的黑梦中惊醒，踏入『现实世界』。",
            "━━━━━━━━━━━━━",
            "✧ 生命与理智完全恢复",
        ]
        
        if was_in_dungeon:
            msg_lines.append(f"✧ 已从第{dungeon_level}重里世界穿越回表世界")
            msg_lines.append(f"✧ 恢复表世界坐标：({player.x},{player.y})")
        else:
            msg_lines.append("✧ 但你的精神状态可能不太好...")
            msg_lines.append(f"✧ 当前坐标：({player.x},{player.y})")

        msg_lines.extend([
            "━━━━━━━━━━━━━",
            "⬇️ 【导航 <x> <y>】劳逸结合，现实经商",
            "⬇️ 【进入 N层诡域】探索更深的里世界"
        ])
        
        msg = "\n".join(msg_lines)
        await revive_cmd.finish(message_add_head(msg, event))
