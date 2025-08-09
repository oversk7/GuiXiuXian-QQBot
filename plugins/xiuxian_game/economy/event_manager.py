"""事件管理器

用于存储玩家最新的MessageEvent，支持主动回复功能
注意：这是内存存储，不持久化到数据库
"""

from typing import Dict, Optional
from nonebot.adapters.qq import MessageEvent
from datetime import datetime, timedelta
import asyncio
from nonebot import logger


class EventManager:
    """事件管理器 - 存储玩家最新的MessageEvent"""
    
    def __init__(self):
        # 存储玩家最新的event {player_id: (event, timestamp)}
        self._player_events: Dict[str, tuple[MessageEvent, datetime]] = {}
        # 事件过期时间（3分钟）
        self._expire_time = timedelta(minutes=3)
    
    def store_event(self, player_id: str, event: MessageEvent):
        """存储玩家的最新事件"""
        self._player_events[player_id] = (event, datetime.now())
        logger.debug(f"存储玩家 {player_id} 的事件")
        # 确保清理任务已启动
        ensure_cleanup_task_started()
    
    def get_event(self, player_id: str) -> Optional[MessageEvent]:
        """获取玩家的最新事件（如果未过期）"""
        if player_id not in self._player_events:
            return None
        
        event, timestamp = self._player_events[player_id]
        
        # 检查是否过期
        if datetime.now() - timestamp > self._expire_time:
            # 清理过期事件
            del self._player_events[player_id]
            logger.debug(f"清理玩家 {player_id} 的过期事件")
            return None
        
        return event
    
    def remove_event(self, player_id: str):
        """移除玩家的事件"""
        if player_id in self._player_events:
            del self._player_events[player_id]
            logger.debug(f"移除玩家 {player_id} 的事件")
    
    def cleanup_expired_events(self):
        """清理所有过期事件"""
        now = datetime.now()
        expired_players = []
        
        for player_id, (event, timestamp) in self._player_events.items():
            if now - timestamp > self._expire_time:
                expired_players.append(player_id)
        
        for player_id in expired_players:
            del self._player_events[player_id]
        
        if expired_players:
            logger.debug(f"清理了 {len(expired_players)} 个过期事件")
    
    def get_stored_count(self) -> int:
        """获取当前存储的事件数量"""
        return len(self._player_events)


# 全局事件管理器实例
event_manager = EventManager()


async def start_cleanup_task():
    """启动定期清理任务"""
    while True:
        try:
            await asyncio.sleep(60)  # 每分钟清理一次
            event_manager.cleanup_expired_events()
        except Exception as e:
            logger.error(f"事件清理任务出错: {e}")


# 清理任务将在需要时启动，而不是在模块导入时
_cleanup_task = None

def ensure_cleanup_task_started():
    """确保清理任务已启动"""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        try:
            _cleanup_task = asyncio.create_task(start_cleanup_task())
            logger.debug("事件清理任务已启动")
        except RuntimeError:
            # 如果没有运行的事件循环，稍后再启动
            pass
