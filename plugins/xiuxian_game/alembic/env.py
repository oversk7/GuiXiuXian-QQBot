import sys
import os
from logging.config import fileConfig
from pathlib import Path
import yaml

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from models.db import get_base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# ==================== 动态加载数据库配置 ====================
def load_database_config() -> dict:
    """从 database.yaml 加载数据库配置"""
    config_path = Path(project_root) / "config" / "database.yaml"

    if not config_path.exists():
        print(f"⚠️ 数据库配置文件不存在: {config_path}")
        print("📝 使用默认 SQLite 配置")
        return {
            "database": {
                "type": "sqlite",
                "sqlite": {"path": "data/game.db"}
            }
        }

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_sync_database_url(db_config: dict) -> str:
    """构建同步数据库 URL (用于 Alembic 迁移)"""
    db_cfg = db_config["database"]
    db_type = db_cfg.get("type", "sqlite")

    if db_type == "sqlite":
        sqlite_cfg = db_cfg["sqlite"]
        db_path = os.path.join(project_root, sqlite_cfg["path"])
        return f"sqlite:///{db_path}"

    elif db_type == "mysql":
        mysql_cfg = db_cfg["mysql"]
        host = mysql_cfg["host"]
        port = mysql_cfg["port"]
        user = mysql_cfg["user"]
        password = mysql_cfg["password"]
        database = mysql_cfg["database"]
        charset = mysql_cfg.get("charset", "utf8mb4")

        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"

    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


# 从配置文件加载数据库 URL
try:
    db_config = load_database_config()
    database_url = build_sync_database_url(db_config)
    config.set_main_option('sqlalchemy.url', database_url)
    print(f"✅ Alembic 数据库配置: {db_config['database']['type']}")
except Exception as e:
    print(f"❌ 加载数据库配置失败: {e}")
    print("📝 回退到默认 SQLite 配置")
    config.set_main_option('sqlalchemy.url', 'sqlite:///data/game.db')

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = get_base().metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
