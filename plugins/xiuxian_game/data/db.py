from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio


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
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库初始化完成")

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session 

if __name__ == "__main__":
    asyncio.run(init_db())