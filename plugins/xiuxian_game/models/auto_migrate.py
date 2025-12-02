"""
自动数据库迁移模块
在 bot 启动时自动检测并添加缺失的字段和索引
无需手动执行 SQL 或 Alembic 命令
"""
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


# ==================== 字段定义 ====================

# 定义需要自动添加的字段
# 格式: {表名: {字段名: 字段定义}}
REQUIRED_FIELDS: Dict[str, Dict[str, str]] = {
    "daily_task": {
        "quest_chain_id": "VARCHAR(50) NULL COMMENT '任务链ID（如novice_basic）'",
        "quest_step": "INT NULL COMMENT '任务链步骤（1、2、3...）'",
        "is_tutorial": "BOOLEAN DEFAULT FALSE COMMENT '是否为新手教程任务'",
        "auto_accept": "BOOLEAN DEFAULT FALSE COMMENT '是否自动接取'",
    },
    "stocks": {
        "health": "INT DEFAULT 100 COMMENT '健康度(100-0)'",
        "health_decay_rate": "FLOAT DEFAULT 1.0 COMMENT '健康度衰减速度倍率'",
        "is_active": "BOOLEAN DEFAULT TRUE COMMENT '是否活跃（未退市）'",
        "delisted_at": "DATETIME NULL COMMENT '退市时间'",
        "delist_reason": "VARCHAR(100) NULL COMMENT '退市原因'",
    },
    # 未来需要添加更多字段时，直接在这里添加即可
    # "player": {
    #     "new_field": "VARCHAR(100) NULL COMMENT '新字段说明'",
    # },
}


# 定义需要自动创建的表（仅用于新表创建，不修改已有表）
# 注意：这会调用 CREATE TABLE IF NOT EXISTS
REQUIRED_TABLES: Dict[str, str] = {
    "stock_events": """
        CREATE TABLE IF NOT EXISTS stock_events (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            event_id VARCHAR(50) NOT NULL COMMENT '事件ID',
            event_name VARCHAR(100) NOT NULL COMMENT '事件名称',
            description VARCHAR(500) NOT NULL COMMENT '事件描述',
            affected_stock_id INT NOT NULL COMMENT '受影响股票ID',
            price_impact FLOAT NOT NULL COMMENT '价格影响（-0.4表示跌40%）',
            health_impact INT NOT NULL COMMENT '健康度影响',
            trigger_date DATETIME NOT NULL COMMENT '触发时间',
            duration_days INT NOT NULL COMMENT '持续天数',
            is_active BOOLEAN DEFAULT TRUE COMMENT '是否生效中',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            INDEX idx_stock_event (affected_stock_id, is_active),
            FOREIGN KEY (affected_stock_id) REFERENCES stocks(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票突发事件表'
    """,
}


# 定义需要自动创建的索引
# 格式: [(表名, 索引名, 索引列)]
REQUIRED_INDEXES: List[Tuple[str, str, str]] = [
    ("daily_task", "idx_daily_task_tutorial", "player_id, is_tutorial, status"),
    ("daily_task", "idx_daily_task_quest_chain", "player_id, quest_chain_id, quest_step"),
    # 未来需要添加更多索引时，直接在这里添加即可
]


# ==================== 自动迁移逻辑 ====================

async def auto_migrate(engine: AsyncEngine, verbose: bool = True):
    """
    自动检测并添加缺失的数据库字段和索引

    Args:
        engine: SQLAlchemy 异步引擎
        verbose: 是否打印详细日志
    """
    if verbose:
        print("🔍 [自动迁移] 检查数据库结构...")

    async with engine.begin() as conn:
        # 1. 创建缺失的表
        tables_created = await _create_missing_tables(conn, verbose)

        # 2. 添加缺失的字段
        fields_added = await _add_missing_fields(conn, verbose)

        # 3. 创建缺失的索引
        indexes_added = await _add_missing_indexes(conn, verbose)

        if verbose:
            if tables_created > 0 or fields_added > 0 or indexes_added > 0:
                print(f"✅ [自动迁移] 完成！创建了 {tables_created} 个表，添加了 {fields_added} 个字段，{indexes_added} 个索引")
            else:
                print("✓ [自动迁移] 数据库结构已是最新")


async def _create_missing_tables(conn, verbose: bool) -> int:
    """创建缺失的表"""
    created_count = 0

    for table_name, create_sql in REQUIRED_TABLES.items():
        try:
            await conn.execute(text(create_sql))
            if verbose:
                print(f"  📊 创建表: {table_name}")
            created_count += 1
        except Exception as e:
            error_msg = str(e).lower()
            # 忽略"表已存在"错误
            if "already exists" in error_msg or "duplicate" in error_msg:
                if verbose:
                    logger.debug(f"  ✓ 表 {table_name} 已存在")
            else:
                logger.error(f"❌ [自动迁移] 创建表 {table_name} 失败: {e}")

    return created_count


async def _add_missing_fields(conn, verbose: bool) -> int:
    """添加缺失的字段"""
    added_count = 0

    for table_name, fields in REQUIRED_FIELDS.items():
        # 获取表的现有字段
        def get_columns(connection):
            inspector = inspect(connection)
            try:
                return [col['name'] for col in inspector.get_columns(table_name)]
            except Exception:
                return []  # 表不存在

        existing_columns = await conn.run_sync(get_columns)

        if not existing_columns:
            if verbose:
                logger.warning(f"⚠️ [自动迁移] 表 {table_name} 不存在，跳过字段检查")
            continue

        # 检查并添加缺失的字段
        for field_name, field_def in fields.items():
            if field_name not in existing_columns:
                try:
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {field_name} {field_def}"
                    await conn.execute(text(sql))

                    if verbose:
                        print(f"  ➕ 添加字段: {table_name}.{field_name}")

                    added_count += 1

                except Exception as e:
                    error_msg = str(e).lower()
                    # 忽略"字段已存在"错误
                    if "duplicate" in error_msg or "exists" in error_msg:
                        if verbose:
                            logger.debug(f"  ✓ 字段 {table_name}.{field_name} 已存在")
                    else:
                        logger.error(f"❌ [自动迁移] 添加字段 {table_name}.{field_name} 失败: {e}")

    return added_count


async def _add_missing_indexes(conn, verbose: bool) -> int:
    """创建缺失的索引"""
    added_count = 0

    for table_name, idx_name, idx_cols in REQUIRED_INDEXES:
        try:
            sql = f"CREATE INDEX {idx_name} ON {table_name}({idx_cols})"
            await conn.execute(text(sql))

            if verbose:
                print(f"  📌 创建索引: {idx_name}")

            added_count += 1

        except Exception as e:
            error_msg = str(e).lower()
            # 忽略"索引已存在"错误
            if "duplicate" in error_msg or "exists" in error_msg:
                if verbose:
                    logger.debug(f"  ✓ 索引 {idx_name} 已存在")
            else:
                logger.error(f"❌ [自动迁移] 创建索引 {idx_name} 失败: {e}")

    return added_count


# ==================== 验证函数 ====================

async def verify_migration(engine: AsyncEngine) -> bool:
    """
    验证所有必需的字段和索引是否存在

    Returns:
        bool: 如果所有字段和索引都存在则返回 True
    """
    async with engine.begin() as conn:
        # 检查所有表的所有字段
        for table_name, fields in REQUIRED_FIELDS.items():
            def get_columns(connection):
                inspector = inspect(connection)
                try:
                    return [col['name'] for col in inspector.get_columns(table_name)]
                except Exception:
                    return []

            existing_columns = await conn.run_sync(get_columns)

            for field_name in fields.keys():
                if field_name not in existing_columns:
                    logger.error(f"❌ 缺失字段: {table_name}.{field_name}")
                    return False

        logger.info("✅ 所有必需字段都已存在")
        return True
