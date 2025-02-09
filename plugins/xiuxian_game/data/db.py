from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, delete


engine = create_async_engine(
    "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(__file__), "game.db"),
    echo=False
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def init_db():
    print("🔄 正在初始化数据库...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # 加载物品配置
    from ..config import config
    from ..models.item import Item
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Item))
        if not result.scalars().first():  # 仅当没有物品时加载
            print("🔄 正在加载物品配置...")
            items_data = []
            # 合并所有分类的物品
            for category in config.items_config["items"].values():
                items_data.extend(category)
            
            # 先清空现有数据
            await session.execute(delete(Item))
            
            # 批量插入新数据
            for item_data in items_data:
                session.add(Item(**item_data))
            await session.commit()
            del items_data  # 主动释放内存
            
    print("✅ 数据库初始化完成")

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session 

@asynccontextmanager
async def safe_session():
    """安全会话管理器（自动回滚+资源清理）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

if __name__ == "__main__":
    asyncio.run(init_db())