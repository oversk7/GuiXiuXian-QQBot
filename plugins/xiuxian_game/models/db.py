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


# 优化的SQLite引擎配置，解决数据库锁定问题
engine = create_async_engine(
    "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(__file__), "../data/game.db"),
    echo=False,
    # SQLite优化配置
    connect_args={
        "timeout": 30,           # 30秒超时
        "check_same_thread": False,  # 允许多线程访问
    },
)
# --- SQL 执行耗时埋点（SQLite/MySQL 通用） ---
from sqlalchemy import event
import time, logging

try:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_exec(conn, cursor, stmt, params, ctx, execmany):
        ctx._q_t0 = time.perf_counter()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_exec(conn, cursor, stmt, params, ctx, execmany):
        t0 = getattr(ctx, "_q_t0", None)
        if t0 is not None:
            ms = (time.perf_counter() - t0) * 1000
            # 只记录>50ms的SQL，避免日志过多
            if ms > 50:
                logging.getLogger("sql").info(f"{ms:.1f}ms | {str(stmt)[:200]}")
except (AttributeError, RuntimeError):
    # 在极少数初始化阶段 engine 未就绪时跳过埋点，不影响主流程
    pass


# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()
def get_base():
    import models
    return Base

async def init_db():
    print("🔄 正在初始化数据库...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库初始化完成")

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """标准会话管理器"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

@asynccontextmanager
async def safe_session():
    """安全会话管理器（自动回滚+资源清理）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # 自动提交成功的事务
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

@asynccontextmanager
async def retry_session(max_retries: int = 3):
    """带重试机制的会话管理器，用于处理数据库锁定问题"""
    session = None
    for attempt in range(max_retries):
        try:
            session = AsyncSessionLocal()
            yield session
            await session.commit()
            break  # 成功则跳出重试循环
        except SQLAlchemyError as e:
            if session:
                try:
                    await session.rollback()
                except Exception:
                    pass  # 忽略回滚错误
            if attempt == max_retries - 1:  # 最后一次尝试失败
                raise e
            # 等待一段时间后重试
            await asyncio.sleep(0.1 * (attempt + 1))
        except Exception as e:
            if session:
                try:
                    await session.rollback()
                except Exception:
                    pass  # 忽略回滚错误
            raise e
        finally:
            if session:
                try:
                    await session.close()
                except Exception:
                    pass  # 忽略关闭错误
                session = None

if __name__ == "__main__":
    asyncio.run(init_db())