"""
自动数据库迁移模块
在 bot 启动时自动检测并添加缺失的字段、索引和 ENUM 值
无需手动执行 SQL 或 Alembic 命令

功能：
1. 创建缺失的表
2. 添加缺失的字段
3. 创建缺失的索引
4. 检测并修复 ENUM 类型不匹配（新增）
"""
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine
from typing import Dict, List, Tuple, Set
import logging
import re

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


# 定义需要检查的 ENUM 列
# 格式: {表名: {列名: [允许的值列表]}}
# ⚠️ 这里定义的值必须与代码中的 Enum 类保持一致！
REQUIRED_ENUMS: Dict[str, Dict[str, List[str]]] = {
    "daily_task": {
        "task_type": [
            "ghost_elimination",
            "pen_spirit_case",
            "fake_immortal_cult",
            "shape_shifter_hunt",
            "stone_curse_break",
            "torture_cult_raid",
            "tutorial",
        ],
        # 如果有其他 ENUM 列，在这里添加
        # "status": ["AVAILABLE", "ACCEPTED", "COMPLETED", "EXPIRED"],
    },
    # 未来如果有其他表的 ENUM 列需要检查，在这里添加
    # "other_table": {
    #     "enum_column": ["value1", "value2", "value3"],
    # },
}


# ==================== 自动迁移逻辑 ====================

async def auto_migrate(engine: AsyncEngine, verbose: bool = True):
    """
    自动检测并添加缺失的数据库字段、索引和 ENUM 值

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

        # 4. 检测并修复 ENUM 列（新增）
        enums_fixed = await _fix_enum_columns(conn, verbose)

        if verbose:
            if tables_created > 0 or fields_added > 0 or indexes_added > 0 or enums_fixed > 0:
                print(f"✅ [自动迁移] 完成！创建了 {tables_created} 个表，"
                      f"添加了 {fields_added} 个字段，{indexes_added} 个索引，"
                      f"修复了 {enums_fixed} 个 ENUM 列")
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


# ==================== ENUM 修复函数 ====================

async def _fix_enum_columns(conn, verbose: bool) -> int:
    """
    检测并修复 ENUM 列的值不匹配问题

    MySQL ENUM 类型的限制：
    - 不能直接 ALTER ENUM ADD VALUE
    - 必须重建整个列

    修复策略：
    1. 检测数据库中 ENUM 列的实际值
    2. 与 REQUIRED_ENUMS 中定义的期望值对比
    3. 如果不匹配，自动重建 ENUM 列

    Returns:
        int: 修复的 ENUM 列数量
    """
    fixed_count = 0

    for table_name, enum_columns in REQUIRED_ENUMS.items():
        for column_name, expected_values in enum_columns.items():
            try:
                # 1. 获取数据库中的实际 ENUM 值
                actual_values = await _get_enum_values(conn, table_name, column_name)

                if actual_values is None:
                    if verbose:
                        logger.warning(f"⚠️ [ENUM检查] 表 {table_name} 或列 {column_name} 不存在，跳过")
                    continue

                # 2. 对比期望值和实际值
                expected_set = set(expected_values)
                actual_set = set(actual_values)

                if expected_set == actual_set:
                    if verbose:
                        logger.debug(f"  ✓ ENUM 列 {table_name}.{column_name} 已是最新")
                    continue

                # 3. 发现差异，执行修复
                missing_values = expected_set - actual_set
                extra_values = actual_set - expected_set

                if verbose:
                    print(f"  🔧 修复 ENUM 列: {table_name}.{column_name}")
                    if missing_values:
                        print(f"     缺失值: {', '.join(missing_values)}")
                    if extra_values:
                        print(f"     多余值: {', '.join(extra_values)} (将保留)")

                # 4. 重建 ENUM 列
                await _rebuild_enum_column(conn, table_name, column_name, expected_values, verbose)
                fixed_count += 1

                if verbose:
                    print(f"     ✅ 修复完成")

            except Exception as e:
                logger.error(f"❌ [ENUM修复] 处理 {table_name}.{column_name} 失败: {e}")

    return fixed_count


async def _get_enum_values(conn, table_name: str, column_name: str) -> Set[str] | None:
    """
    获取数据库中 ENUM 列的实际值

    Args:
        conn: 数据库连接
        table_name: 表名
        column_name: 列名

    Returns:
        Set[str]: ENUM 值集合，如果列不存在或不是 ENUM 类型则返回 None
    """
    try:
        # 使用 SHOW COLUMNS 获取列信息
        result = await conn.execute(
            text(f"SHOW COLUMNS FROM {table_name} LIKE :column_name"),
            {"column_name": column_name}
        )
        row = result.fetchone()

        if not row:
            return None  # 列不存在

        # row[1] 是 Type 字段，格式如: enum('value1','value2','value3')
        column_type = row[1]

        if not column_type.startswith('enum('):
            return None  # 不是 ENUM 类型

        # 解析 ENUM 值
        # 正则提取所有单引号内的值
        enum_values = re.findall(r"'([^']*)'", column_type)

        return set(enum_values)

    except Exception as e:
        logger.error(f"获取 ENUM 值失败: {table_name}.{column_name}: {e}")
        return None


async def _rebuild_enum_column(
    conn,
    table_name: str,
    column_name: str,
    new_values: List[str],
    verbose: bool
) -> None:
    """
    重建 ENUM 列（安全的方式）

    步骤：
    1. 创建临时 VARCHAR 列
    2. 复制数据到临时列
    3. 删除旧 ENUM 列
    4. 创建新 ENUM 列（包含所有期望的值）
    5. 恢复数据
    6. 删除临时列

    Args:
        conn: 数据库连接
        table_name: 表名
        column_name: 列名
        new_values: 新的 ENUM 值列表
        verbose: 是否打印详细日志
    """
    temp_column = f"{column_name}_temp_migration"

    try:
        # 获取列的完整定义（包括 NOT NULL、DEFAULT 等属性）
        result = await conn.execute(
            text(f"SHOW COLUMNS FROM {table_name} LIKE :column_name"),
            {"column_name": column_name}
        )
        row = result.fetchone()

        is_nullable = (row[2] == 'YES')  # Null 字段
        default_value = row[4]  # Default 字段
        comment = row[5] if len(row) > 5 else ''  # Comment 字段

        # 构建 ENUM 列的属性
        enum_values_str = ', '.join(f"'{v}'" for v in new_values)
        column_attrs = []

        if not is_nullable:
            column_attrs.append("NOT NULL")

        if default_value:
            column_attrs.append(f"DEFAULT '{default_value}'")

        if comment:
            column_attrs.append(f"COMMENT '{comment}'")

        attrs_str = ' '.join(column_attrs)

        # 执行迁移步骤
        steps = [
            # 1. 添加临时列
            f"ALTER TABLE {table_name} ADD COLUMN {temp_column} VARCHAR(100)",

            # 2. 复制数据
            f"UPDATE {table_name} SET {temp_column} = {column_name}",

            # 3. 删除旧列
            f"ALTER TABLE {table_name} DROP COLUMN {column_name}",

            # 4. 创建新 ENUM 列
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} ENUM({enum_values_str}) {attrs_str}",

            # 5. 恢复数据
            f"UPDATE {table_name} SET {column_name} = {temp_column}",

            # 6. 删除临时列
            f"ALTER TABLE {table_name} DROP COLUMN {temp_column}",
        ]

        for step_sql in steps:
            if verbose:
                logger.debug(f"     执行: {step_sql[:80]}...")
            await conn.execute(text(step_sql))

    except Exception as e:
        logger.error(f"重建 ENUM 列失败: {table_name}.{column_name}: {e}")
        # 尝试清理临时列
        try:
            await conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {temp_column}"))
        except:
            pass
        raise
