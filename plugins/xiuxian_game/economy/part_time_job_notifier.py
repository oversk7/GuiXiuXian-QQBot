"""打工完成主动通知系统

定期检查已完成的工作，主动通知玩家收工
"""

import asyncio
from datetime import datetime
from typing import List
from nonebot import logger, get_bot
from nonebot.adapters.qq import Bot
from sqlalchemy import select, and_

from ..models.db import safe_session
from ..models.part_time_job import PartTimeJob
from .event_manager import event_manager
from ..utils import message_add_head
from .part_time_job_service import PartTimeJobService


class PartTimeJobNotifier:
    """打工完成通知器"""
    
    def __init__(self):
        self._running = False
        self._check_interval = 30  # 每30秒检查一次
    
    async def start(self):
        """启动通知服务"""
        if self._running:
            return
        
        self._running = True
        logger.info("✅ 打工完成通知服务已启动")
        
        while self._running:
            try:
                await self._check_completed_jobs()
                await asyncio.sleep(self._check_interval)
            except Exception as e:
                logger.error(f"❌ 打工通知检查出错: {e}")
                await asyncio.sleep(self._check_interval)
    
    def stop(self):
        """停止通知服务"""
        self._running = False
        logger.info("⏹️ 打工完成通知服务已停止")
    
    async def _check_completed_jobs(self):
        """检查已完成的工作并发送通知"""
        try:
            async with safe_session() as session:
                # 查找所有已完成但还在工作状态的任务
                stmt = select(PartTimeJob).where(
                    and_(
                        PartTimeJob.is_working == True,
                        PartTimeJob.end_time <= datetime.now()
                    )
                )
                
                completed_jobs = (await session.execute(stmt)).scalars().all()
                
                if not completed_jobs:
                    return
                
                logger.info(f"🔔 发现 {len(completed_jobs)} 个已完成的工作，准备发送通知")
                
                # 获取bot实例
                try:
                    bot = get_bot()
                except ValueError:
                    logger.warning("⚠️ 无法获取bot实例，跳过通知")
                    return
                
                # 为每个完成的工作发送通知
                for job in completed_jobs:
                    await self._notify_job_completion(bot, job)
                    
        except Exception as e:
            logger.error(f"❌ 检查完成工作时出错: {e}")
    
    async def _notify_job_completion(self, bot: Bot, job: PartTimeJob):
        """通知单个工作完成"""
        try:
            # 获取玩家最新的event
            latest_event = event_manager.get_event(job.player_id)
            
            if not latest_event:
                logger.debug(f"玩家 {job.player_id} 没有可用的事件，跳过通知")
                return
            
            # 获取工作配置
            job_config = PartTimeJobService.JOB_TYPES.get(job.job_type)
            if not job_config:
                logger.warning(f"未找到工作类型配置: {job.job_type}")
                return
            
            # 构建通知消息
            duration = job_config['duration_hours']
            if duration < 1:
                time_str = f"{int(duration * 60)}分钟"
            else:
                time_str = f"{duration}小时"
            
            notification_msg = (
                f"🎉 工作完成通知！\n"
                f"━━━━━━━━━━━━━\n"
                f"{job_config['emoji']} {job_config['name']} 已完成\n"
                f"⏰ 工作时长：{time_str}\n"
                f"💰 预期收入：{job_config['base_reward']}+ 金币\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 使用【收工】获得奖励！"
            )
            
            # 发送通知
            await bot.send(latest_event, message_add_head(notification_msg, latest_event))
            logger.info(f"✅ 已通知玩家 {job.player_id} 工作完成")
            
            # 清理事件（避免重复通知）
            event_manager.remove_event(job.player_id)
            
        except Exception as e:
            logger.error(f"❌ 通知玩家 {job.player_id} 工作完成时出错: {e}")


# 全局通知器实例
job_notifier = PartTimeJobNotifier()


async def start_job_notifier():
    """启动打工通知服务"""
    await job_notifier.start()


# 通知服务将在需要时启动，而不是在模块导入时
_notifier_task = None

def ensure_notifier_started():
    """确保通知服务已启动"""
    global _notifier_task
    if _notifier_task is None or _notifier_task.done():
        try:
            _notifier_task = asyncio.create_task(start_job_notifier())
            logger.info("打工通知服务启动任务已创建")
        except RuntimeError:
            # 如果没有运行的事件循环，稍后再启动
            pass
