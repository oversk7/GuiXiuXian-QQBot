"""
数据库连接管理模块（支持 SQLite 和 MySQL）

修改说明：
1. 支持通过配置文件切换数据库类型
2. 保留 SQLite 和 MySQL 的兼容性
3. 最小化代码改动，保持原有 API 不变
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import event
import sqlite3
import os
import yaml
from typing import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from nonebot.exception import FinishedException, PausedException, RejectedException
from pathlib import Path


# ==================== 配置加载 ====================

def load_database_config() -> dict:
    """加载数据库配置"""
    config_path = Path(__file__).parent.parent / "config" / "database.yaml"
    
    # 如果配置文件不存在，使用默认 SQLite 配置
    if not config_path.exists():
        print(f"⚠️ 数据库配置文件不存在: {config_path}")
        print("📝 使用默认 SQLite 配置")
        return {
            "database": {
                "type": "sqlite",
                "sqlite": {
                    "path": "data/game.db",
                    "timeout": 30,
                    "check_same_thread": False
                }
            }
        }
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    return config


def build_database_url(config: dict) -> str:
    """根据配置构建数据库连接 URL"""
    db_config = config["database"]
    db_type = db_config.get("type", "sqlite")
    
    if db_type == "sqlite":
        sqlite_config = db_config["sqlite"]
        db_path = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            sqlite_config["path"]
        )
        return f"sqlite+aiosqlite:///{db_path}"
    
    elif db_type == "mysql":
        mysql_config = db_config["mysql"]
        host = mysql_config["host"]
        port = mysql_config["port"]
        user = mysql_config["user"]
        password = mysql_config["password"]
        database = mysql_config["database"]
        charset = mysql_config.get("charset", "utf8mb4")
        
        return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"
    
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


def build_engine_config(config: dict) -> dict:
    """根据配置构建引擎参数"""
    db_config = config["database"]
    db_type = db_config.get("type", "sqlite")
    
    if db_type == "sqlite":
        sqlite_config = db_config["sqlite"]
        return {
            "echo": False,
            "connect_args": {
                "timeout": sqlite_config.get("timeout", 30),
                "check_same_thread": sqlite_config.get("check_same_thread", False),
            }
        }
    
    elif db_type == "mysql":
        mysql_config = db_config["mysql"]
        return {
            "echo": mysql_config.get("echo", False),
            "pool_size": mysql_config.get("pool_size", 20),
            "max_overflow": mysql_config.get("max_overflow", 10),
            "pool_recycle": mysql_config.get("pool_recycle", 3600),
            "pool_pre_ping": mysql_config.get("pool_pre_ping", True),
            "pool_use_lifo": mysql_config.get("pool_use_lifo", True),
            "connect_args": {
                "charset": mysql_config.get("charset", "utf8mb4"),
                "autocommit": mysql_config.get("autocommit", False),
            }
        }
    
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


# ==================== 创建数据库引擎 ====================

# 加载配置
db_config = load_database_config()
db_type = db_config["database"].get("type", "sqlite")

# 构建数据库 URL 和引擎配置
database_url = build_database_url(db_config)
engine_config = build_engine_config(db_config)

print(f"数据库类型: {db_type.upper()}")
print(f"连接地址: {database_url.split('@')[-1] if '@' in database_url else database_url}")

# 创建异步引擎
engine = create_async_engine(database_url, **engine_config)


# ==================== SQLite 特定配置 ====================

if db_type == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_enable_wal(dbapi_connection, connection_record):
        """仅对 SQLite 连接应用 WAL 模式"""
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    
    print("SQLite WAL 模式已启用")


# ==================== 会话工厂 ====================

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


def get_base():
    """获取 Base（兼容旧代码）"""
    return Base


# ==================== 数据库初始化 ====================

async def init_db():
    """初始化数据库表结构"""
    print("正在初始化数据库...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库初始化完成")

    # 自动检测并添加缺失的字段和索引
    from .auto_migrate import auto_migrate
    await auto_migrate(engine, verbose=True)


# ==================== 会话管理器 ====================

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
async def safe_session(session_factory=None):
    """安全会话管理器（自动回滚+资源清理）"""
    async with (session_factory or AsyncSessionLocal)() as session:
        try:
            try:
                yield session
            except (FinishedException, PausedException, RejectedException):
                await session.commit()
                raise
            else:
                await session.commit()
        except (FinishedException, PausedException, RejectedException):
            raise
        except BaseException:
            # 包括提交失败和任务取消，事务都必须回滚。
            await session.rollback()
            raise
        finally:
            await session.close()


async def run_transaction(operation, max_attempts: int = 3, session_factory=None):
    """用新会话重试整笔事务；operation 内不得提交事务或发送外部消息。"""
    if max_attempts < 1:
        raise ValueError("max_attempts 必须大于零")
    for attempt in range(max_attempts):
        try:
            async with safe_session(session_factory) as session:
                return await operation(session)
        except (OperationalError, StaleDataError) as error:
            retryable = isinstance(error, StaleDataError) or (
                getattr(error.orig, "args", (None,))[0] in (1205, 1213, 3572)
            )
            if not retryable or attempt + 1 == max_attempts:
                raise
            await asyncio.sleep(0.1 * (attempt + 1))


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    asyncio.run(init_db())

