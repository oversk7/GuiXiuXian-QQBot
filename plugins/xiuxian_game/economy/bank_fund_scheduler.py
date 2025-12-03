"""理财产品定时任务调度器"""
import logging
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler
from .bank_fund_service import BankFundService
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

driver = get_driver()


@driver.on_startup
async def setup_fund_scheduler():
    """设置理财产品定时任务"""
    try:
        # 检查任务是否已存在，避免重复设置
        existing_job = scheduler.get_job("fund_daily_settlement")

        if existing_job:
            logger.info("⚠️ 理财产品每日结算定时任务已存在，跳过设置")
        else:
            # 添加每日结算任务（每天凌晨3点执行）
            scheduler.add_job(
                func=perform_daily_settlement,
                trigger="cron",
                hour=3,  # 每天凌晨3点执行
                id="fund_daily_settlement",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 理财产品每日结算定时任务已设置 - 每天凌晨3点执行")

    except Exception as e:
        logger.error(f"❌ 设置理财产品定时任务失败: {e}")


async def perform_daily_settlement():
    """执行每日理财产品结算"""
    try:
        logger.info("💰 开始执行理财产品每日结算...")

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )

            daily_return, settlement_count = await fund_service.daily_settlement()
            await uow.commit()

        daily_return_pct = daily_return * 100
        logger.info(
            f"✅ 理财产品每日结算完成: "
            f"收益率 {daily_return_pct:+.2f}%, "
            f"结算 {settlement_count} 个持仓"
        )

    except Exception as e:
        logger.error(f"❌ 理财产品每日结算失败: {e}", exc_info=True)


@driver.on_shutdown
async def cleanup_fund_scheduler():
    """清理理财产品调度器"""
    try:
        if scheduler.get_job("fund_daily_settlement"):
            scheduler.remove_job("fund_daily_settlement")
            logger.info("🧹 理财产品每日结算定时任务已清理")

    except Exception as e:
        logger.error(f"❌ 清理理财产品定时任务失败: {e}")
