"""
事件处理器示例

展示如何订阅和处理领域事件。
这些处理器可以用于成就系统、统计系统、通知系统等跨模块功能。
"""
from nonebot import logger

from .interfaces import IEvent, IEventHandler
from .game_events import (
    GiftGivenEvent,
    WorldBossDamageEvent,
    PlayerLevelUpEvent,
    MonsterKilledEvent,
)


class GiftStatisticsHandler(IEventHandler):
    """
    送礼统计处理器

    功能：
    - 记录送礼次数
    - 统计送礼总价值
    - 可用于成就系统、排行榜等
    """

    async def handle(self, event: IEvent) -> None:
        if not isinstance(event, GiftGivenEvent):
            return

        logger.info(
            f"📊 送礼统计 | {event.sender_id} 向 {event.receiver_id} "
            f"送出 {event.item_name}x{event.quantity}"
        )

        # 这里可以添加实际的统计逻辑
        # 例如：更新成就进度、更新排行榜、发送通知等


class WorldBossStatisticsHandler(IEventHandler):
    """
    世界BOSS统计处理器

    功能：
    - 记录BOSS伤害排行
    - 更新实时伤害统计
    - 触发特殊事件（如首杀、最高伤害等）
    """

    async def handle(self, event: IEvent) -> None:
        if not isinstance(event, WorldBossDamageEvent):
            return

        logger.info(
            f"📊 BOSS伤害统计 | {event.player_id} 对 {event.boss_name} "
            f"造成 {event.damage:,} 伤害（累计 {event.total_damage:,}）"
        )

        # 这里可以添加实际的统计逻辑
        # 例如：更新排行榜、检查成就、发送全服通知等


# ==================== 函数式处理器示例 ====================

async def log_player_level_up(event: PlayerLevelUpEvent) -> None:
    """
    玩家升级日志处理器（函数式）

    这是一个简单的函数式处理器示例。
    相比类处理器，函数式处理器更轻量，适合简单的逻辑。
    """
    logger.info(
        f"🎉 玩家升级 | {event.player_id} "
        f"从 Lv.{event.old_level} 升到 Lv.{event.new_level} ({event.realm})"
    )


async def log_monster_killed(event: MonsterKilledEvent) -> None:
    """
    怪物击杀日志处理器（函数式）
    """
    boss_flag = "[BOSS]" if event.is_boss else ""
    logger.info(
        f"⚔️ 击杀怪物 | {event.player_id} 击杀了 "
        f"{boss_flag}{event.monster_name}(Lv.{event.monster_level}) "
        f"获得 {event.exp_gained} 经验"
    )


# ==================== 订阅示例 ====================

def register_example_handlers():
    """
    注册示例事件处理器

    这个函数展示了如何订阅事件。
    在实际使用中，应该在应用启动时调用此函数。

    使用方式：
        from plugins.xiuxian_game.domain.events import event_bus
        from plugins.xiuxian_game.domain.events.example_handlers import register_example_handlers

        # 在应用启动时注册
        register_example_handlers()
    """
    from . import event_bus

    # 订阅类处理器
    event_bus.subscribe(GiftGivenEvent, GiftStatisticsHandler())
    event_bus.subscribe(WorldBossDamageEvent, WorldBossStatisticsHandler())

    # 订阅函数处理器
    event_bus.subscribe_func(PlayerLevelUpEvent, log_player_level_up)
    event_bus.subscribe_func(MonsterKilledEvent, log_monster_killed)

    logger.success("✅ 示例事件处理器已注册")


# ==================== 高级示例：成就系统 ====================

class AchievementHandler(IEventHandler):
    """
    成就系统处理器

    这是一个更复杂的处理器示例，展示如何根据事件触发成就。
    实际使用时需要配合成就系统的数据库模型。
    """

    async def handle(self, event: IEvent) -> None:
        """处理所有事件，检查成就触发条件"""

        # 送礼相关成就
        if isinstance(event, GiftGivenEvent):
            await self._check_gift_achievements(event)

        # BOSS伤害相关成就
        elif isinstance(event, WorldBossDamageEvent):
            await self._check_boss_achievements(event)

        # 升级相关成就
        elif isinstance(event, PlayerLevelUpEvent):
            await self._check_level_achievements(event)

    async def _check_gift_achievements(self, event: GiftGivenEvent) -> None:
        """检查送礼相关成就"""
        # 示例：送礼达人 - 累计送礼100次
        # 示例：慷慨大方 - 单次送礼价值超过10000金币
        logger.debug(f"检查送礼成就: {event.sender_id}")

    async def _check_boss_achievements(self, event: WorldBossDamageEvent) -> None:
        """检查BOSS相关成就"""
        # 示例：伤害王者 - 单次伤害超过100万
        if event.damage >= 1_000_000:
            logger.success(f"🏆 {event.player_id} 达成成就：伤害王者（单次伤害 {event.damage:,}）")

        # 示例：BOSS克星 - 累计伤害超过1000万
        if event.total_damage >= 10_000_000:
            logger.success(f"🏆 {event.player_id} 达成成就：BOSS克星（累计伤害 {event.total_damage:,}）")

    async def _check_level_achievements(self, event: PlayerLevelUpEvent) -> None:
        """检查等级相关成就"""
        # 示例：百级修士 - 达到100级
        if event.new_level >= 100:
            logger.success(f"🏆 {event.player_id} 达成成就：百级修士")
