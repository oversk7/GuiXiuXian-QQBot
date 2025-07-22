"""数据库备份定时任务调度器"""
import logging
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler
from .service import backup_service

logger = logging.getLogger(__name__)

driver = get_driver()


@driver.on_startup
async def setup_backup_scheduler():
    """设置数据库备份定时任务"""
    try:
        # 添加每小时执行一次的备份任务
        scheduler.add_job(
            func=perform_backup,
            trigger="interval",
            hours=1,  # 每小时执行一次
            id="database_backup",
            replace_existing=True,  # 如果任务已存在则替换
            max_instances=1,  # 最多同时运行1个实例
            coalesce=True,  # 如果有多个任务堆积，只执行最新的一个
        )
        
        logger.info("✅ 数据库备份定时任务已设置 - 每小时执行一次")
        
        # 启动时立即执行一次备份
        perform_backup()
        
    except Exception as e:
        logger.error(f"❌ 设置数据库备份定时任务失败: {e}")


def perform_backup():
    """执行数据库备份"""
    try:
        logger.info("🔄 开始执行数据库备份...")
        success = backup_service.create_backup()
        
        if success:
            # 获取当前备份列表
            backups = backup_service.get_backup_list()
            backup_count = len(backups)
            
            logger.info(f"✅ 数据库备份完成，当前共有 {backup_count} 个备份文件")
            
            # 记录备份文件信息
            if backups:
                latest_backup = backups[0]
                size_mb = latest_backup["size"] / (1024 * 1024)
                logger.info(f"📁 最新备份: {latest_backup['filename']} ({size_mb:.2f} MB)")
        else:
            logger.error("❌ 数据库备份失败")
            
    except Exception as e:
        logger.error(f"❌ 执行数据库备份时发生错误: {e}")


@driver.on_shutdown
async def cleanup_backup_scheduler():
    """清理备份调度器"""
    try:
        if scheduler.get_job("database_backup"):
            scheduler.remove_job("database_backup")
            logger.info("🧹 数据库备份定时任务已清理")
    except Exception as e:
        logger.error(f"❌ 清理备份定时任务失败: {e}")
