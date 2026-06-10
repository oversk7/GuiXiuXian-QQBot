from __future__ import annotations

"""世界BOSS - 命令入口

指令：
  - 世界BOSS / 世界Boss / worldboss：查看当前BOSS信息与规则
  - 讨伐BOSS：对当前BOSS发起一次攻击（每日3次，冷却1秒）
  - BOSS排行 / 世界BOSS排行：查看本期累计伤害排行榜与奖励区间

战斗机制：
  - BOSS不可战胜，每次攻击会削减玩家理智（mp）
  - 理智归零则血量也为零，结束讨伐
  - 低等级玩家（≤50级）按固定值40-80削减理智
  - 高等级玩家按10%-20%百分比削减理智
  - BOSS等级显示为???，增强压迫感
  - 使用完整战斗属性系统：暴击、连击、穿透、命中等
  - 战报采用副本风格的简洁格式

懒加载刷新：周三/周六 20:00 到点后，首次访问上述指令时自动结算并生成新BOSS。
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..utils_markdown import build_markdown
from ..battle.battle_markdown import build_battle_markdown
from ..battle.battle_log_filter import filter_battle_log, get_player_log_mode
from .service import WorldBossService
from ..platform_utils import require_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的WorldBossService，False使用旧版本
# =====================================================


view_cmd = on_command("世界BOSS", aliases={"世界Boss", "世界boss"}, block=True, priority=13)
attack_cmd = on_command("讨伐BOSS", aliases={"讨伐boss", "讨伐BOSS"}, block=True, priority=13)
rank_cmd = on_command("BOSS排行", aliases={"世界BOSS排行", "世界boss排行", "boss排行"}, block=True, priority=13)
open_chest_cmd = on_command("开启深渊宝箱", aliases={"开启宝箱", "开宝箱"}, block=True, priority=13)


@view_cmd.handle()
async def handle_view(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, view_cmd)

        from ..infrastructure.repositories.world_boss_cycle_repository import WorldBossCycleRepository
        from ..infrastructure.repositories.world_boss_damage_repository import WorldBossDamageRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from .service import WorldBossService as WorldBossServiceNew

        service = WorldBossServiceNew(
            session=session,
            cycle_repo=WorldBossCycleRepository(session),
            damage_repo=WorldBossDamageRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session)
        )
        # 懒触发：检查并刷新周期（必要时结算上期）
        cycle, tip = await service.check_and_refresh_cycle()
        msg = await service.build_boss_view(cycle, player)
        if tip:
            msg = tip + "\n" + msg
        await view_cmd.finish(message_add_head(msg, event))


@attack_cmd.handle()
async def handle_attack(event: MessageEvent, args: Message = CommandArg()):
    async with safe_session() as session:
        player = await require_player(session, event, attack_cmd)

        from ..infrastructure.repositories.world_boss_cycle_repository import WorldBossCycleRepository
        from ..infrastructure.repositories.world_boss_damage_repository import WorldBossDamageRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from .service import WorldBossService as WorldBossServiceNew

        service = WorldBossServiceNew(
            session=session,
            cycle_repo=WorldBossCycleRepository(session),
            damage_repo=WorldBossDamageRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session)
        )
        cycle, tip = await service.check_and_refresh_cycle()
        ok, lines, boss_title, boss_hint = await service.attack_boss(cycle, player)
        if ok:
            boss_log_mode = get_player_log_mode(player)
            lines = filter_battle_log(lines, boss_log_mode)
            if tip:
                lines = [tip, "━━━━━━━━━━━━━"] + lines
            boss_mode_label = "详细模式" if boss_log_mode == "detailed" else "简洁模式"
            await attack_cmd.finish(build_battle_markdown(
                title=boss_title,
                battle_log=lines,
                hint=f"{boss_hint} | {boss_mode_label}",
                btn1="讨伐BOSS",
                btn2="日志模式",
                btn3="面板",
            ))
        else:
            reply = "\n".join(lines)
            if tip:
                reply = tip + "\n" + reply
            await attack_cmd.finish(message_add_head(reply, event))


@rank_cmd.handle()
async def handle_rank(event: MessageEvent):
    async with safe_session() as session:
        from ..infrastructure.repositories.world_boss_cycle_repository import WorldBossCycleRepository
        from ..infrastructure.repositories.world_boss_damage_repository import WorldBossDamageRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from .service import WorldBossService as WorldBossServiceNew

        service = WorldBossServiceNew(
            session=session,
            cycle_repo=WorldBossCycleRepository(session),
            damage_repo=WorldBossDamageRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session)
        )
        cycle, tip = await service.check_and_refresh_cycle()
        msg = await service.build_ranking_view(cycle)
        if tip:
            msg = tip + "\n" + msg
        await rank_cmd.finish(build_markdown(msg))


@open_chest_cmd.handle()
async def handle_open_chest(event: MessageEvent, args: Message = CommandArg()):
    """开启深渊宝箱"""
    from sqlalchemy import select
    from ..models.inventory import ItemInstance, ItemType
    from ..item.item_effects import apply_effect
    from ..config import config

    async with safe_session() as session:
        player = await require_player(session, event, open_chest_cmd)

        # 获取参数
        arg_text = args.extract_plain_text().strip()

        # 查找玩家的深渊宝箱
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id.like("%chest%"),
            ItemInstance.quantity > 0
        )
        chest_items = (await session.execute(stmt)).scalars().all()

        # 过滤出深渊宝箱
        abyss_chests = []
        for item in chest_items:
            if item.item_id.startswith("abyss_") and item.item_id.endswith("_chest"):
                abyss_chests.append(item)

        if not abyss_chests:
            await open_chest_cmd.finish("⛔ 你没有任何深渊宝箱可以开启")

        # 如果没有指定宝箱名称，显示可用宝箱列表
        if not arg_text:
            lines = ["🎁 你拥有的深渊宝箱：", ""]
            for i, chest in enumerate(abyss_chests, 1):
                chest_config = config.items_config["by_id"].get(chest.item_id)
                if chest_config:
                    lines.append(f"{i}. {chest_config.get_display_name()} x{chest.quantity}")

            lines.extend([
                "",
                "💡 使用方法：",
                "  开宝箱 <宝箱名称>",
                "  开宝箱 <序号>",
                "  开宝箱 全部",
                "",
                "示例：开宝箱 深渊勇士宝箱",
                "示例：开宝箱 1"
            ])

            await open_chest_cmd.finish(message_add_head("\n".join(lines), event))

        # 支持一键开启所有宝箱
        normalized_arg = arg_text.lower()
        all_keywords = {"全部", "全部开启", "全部开", "全开", "全部打开", "全都开", "全部宝箱", "all"}
        if normalized_arg in all_keywords:
            opened_count = 0
            result_messages = []

            for chest in abyss_chests:
                chest_config = config.items_config["by_id"].get(chest.item_id)
                if not chest_config:
                    result_messages.append(f"⛔ 未找到宝箱配置：{chest.item_id}，已跳过")
                    continue

                if chest.quantity <= 0:
                    continue

                success, result_msg = await apply_effect(player, chest_config, chest.quantity, "world", session)
                if success:
                    opened_count += chest.quantity
                    result_messages.append(result_msg)
                    await session.delete(chest)
                else:
                    display_name = chest_config.get_display_name()
                    result_messages.append(f"⛔ {display_name} 开启失败：{result_msg}")

            if not result_messages:
                await open_chest_cmd.finish("⛔ 未找到可开启的深渊宝箱")

            if opened_count > 0:
                await session.commit()
                summary = ["🎉 已开启所有深渊宝箱！", ""]
                summary.extend(result_messages)
                await open_chest_cmd.finish(message_add_head("\n\n".join(summary).strip(), event))
            else:
                await open_chest_cmd.finish(message_add_head("\n\n".join(result_messages).strip(), event))

        # 查找指定的宝箱
        target_chest = None

        # 尝试按序号查找
        if arg_text.isdigit():
            index = int(arg_text) - 1
            if 0 <= index < len(abyss_chests):
                target_chest = abyss_chests[index]
        else:
            # 按名称查找
            for chest in abyss_chests:
                chest_config = config.items_config["by_id"].get(chest.item_id)
                if chest_config and arg_text in chest_config.name:
                    target_chest = chest
                    break

        if not target_chest:
            await open_chest_cmd.finish("⛔ 找不到指定的宝箱，请检查名称或序号")

        # 获取宝箱配置
        chest_config = config.items_config["by_id"].get(target_chest.item_id)
        if not chest_config:
            await open_chest_cmd.finish("⛔ 宝箱配置错误")

        # 开启宝箱
        success, result_msg = await apply_effect(player, chest_config, 1, "world", session)

        if success:
            # 扣除宝箱
            target_chest.quantity -= 1
            if target_chest.quantity <= 0:
                await session.delete(target_chest)
            else:
                session.add(target_chest)

            await session.commit()
            await open_chest_cmd.finish(message_add_head(result_msg, event))
        else:
            await open_chest_cmd.finish(message_add_head(f"⛔ 开启失败：{result_msg}", event))


