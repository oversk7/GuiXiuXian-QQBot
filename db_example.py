# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
# from sqlalchemy.orm import sessionmaker
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
# import os
# from typing import AsyncGenerator
# from contextlib import asynccontextmanager
# import asyncio
# from sqlalchemy.exc import SQLAlchemyError
# from sqlalchemy import select


# engine = create_async_engine(
#     "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(__file__), "../data/game.db"),
#     echo=False
# )

# # 创建异步会话工厂
# AsyncSessionLocal = sessionmaker(
#     bind=engine,
#     class_=AsyncSession,
#     expire_on_commit=False
# )

# Base = declarative_base()
# def get_base():
#     import models
#     return Base

# async def init_db():
#     print("🔄 正在初始化数据库...")
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)
#     print("✅ 数据库初始化完成")

# @asynccontextmanager
# async def get_session() -> AsyncGenerator[AsyncSession, None]:
#     async with AsyncSessionLocal() as session:
#         yield session 

# @asynccontextmanager
# async def safe_session():
#     """安全会话管理器（自动回滚+资源清理）"""
#     async with AsyncSessionLocal() as session:
#         try:
#             yield session
#         except SQLAlchemyError as e:
#             await session.rollback()
#             raise e
#         finally:
#             await session.close()

# if __name__ == "__main__":
#     asyncio.run(init_db())