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
from sqlalchemy.exc import SQLAlchemyError
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
    import models
    return Base


# ==================== 数据库初始化 ====================

async def init_db():
    """初始化数据库表结构"""
    print("正在初始化数据库...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库初始化完成")


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


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    asyncio.run(init_db())

