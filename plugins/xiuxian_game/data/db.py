from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy import event
from datetime import datetime
import shutil
from pathlib import Path
from nonebot_plugin_apscheduler import scheduler


engine = create_async_engine(
    "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(__file__), "game.db"),
    echo=False
)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# 自动备份配置
BACKUP_DIR = Path(__file__).parent / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
MAX_BACKUPS = 7  # 保留最近7天备份

async def create_backup():
    """创建数据库备份"""
    backup_file = BACKUP_DIR / f"game_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
    source = Path(__file__).parent / "game.db"
    shutil.copy(source, backup_file)
    
    # 清理旧备份
    backups = sorted(BACKUP_DIR.glob("game_*.db"), reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()

async def init_db():
    print("🔄 正在初始化数据库...")
    # 每天凌晨执行备份
    scheduler.add_job(create_backup, 'cron', hour=0, minute=0)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # 新增任务配置初始化
    from ..config import config
    from ..models.quest import Quest
    quests_config = config.quests_config  # 从本地文件读取
    
    async with AsyncSessionLocal() as session:
        # 检查是否已有任务配置
        existing = (await session.execute(select(Quest))).scalars().first()
        if not existing:
            for q in quests_config["quests"]:
                session.add(Quest(
                    id=q["id"],
                    quest_type=q["type"],
                    title=q["title"],
                    description=q["description"],
                    condition_type=q["condition_type"],
                    condition_params={"required": q["required"]},
                    rewards=q["rewards"],
                    repeatable=q.get("repeatable", False),
                    min_level=q.get("min_level", 1)
                ))
            await session.commit()
    
    print("✅ 数据库初始化完成")

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session 

@asynccontextmanager
async def safe_session():
    """安全会话管理器（自动回滚+资源清理+操作审计）"""
    async with AsyncSessionLocal() as session:
        try:
            # 添加审计钩子
            @event.listens_for(session.sync_session, 'before_flush')
            def before_flush(session, flush_context, instances):
                """数据变更前校验"""
                for obj in session.dirty | session.new:
                    if isinstance(obj, Player):
                        # 数值合法性校验
                        if obj.gold < 0 or obj.gold > 10**9:  # 设置合理上限
                            raise ValueError(f"异常金币值 {obj.gold}")
                        if obj.level < 1 or obj.level > config.game_config["game"]["max_level"]:
                            raise ValueError(f"异常等级 {obj.level}")
                    elif isinstance(obj, Inventory):
                        if obj.quantity < 0 or obj.quantity > 1000:  # 单物品数量上限
                            raise ValueError(f"异常物品数量 {obj.quantity}")
            
            yield session
            await session.commit()
        except (SQLAlchemyError, ValueError) as e:
            await session.rollback()
            logger.error(f"数据操作异常：{str(e)}")
            raise e
        finally:
            await session.close()

if __name__ == "__main__":
    asyncio.run(init_db())