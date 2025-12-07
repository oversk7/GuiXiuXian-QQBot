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
    "navigation_task": {
        "initial_distance": "FLOAT NULL COMMENT '初始总距离（用于进度计算）'",
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
    "bank_fund": """
        CREATE TABLE IF NOT EXISTS bank_fund (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '基金ID',
            fund_name VARCHAR(100) NOT NULL COMMENT '基金名称',
            fund_type VARCHAR(50) DEFAULT 'lively' COMMENT '基金类型(lively=活期)',
            daily_return FLOAT DEFAULT 0.0 COMMENT '当日收益率',
            total_scale BIGINT DEFAULT 0 COMMENT '基金总规模(金币)',
            participant_count INT DEFAULT 0 COMMENT '参与人数',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='银行理财基金表'
    """,
    "fund_holding": """
        CREATE TABLE IF NOT EXISTS fund_holding (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT '持仓ID',
            player_id VARCHAR(32) NOT NULL COMMENT '玩家ID',
            fund_id INT NOT NULL COMMENT '基金ID',
            principal BIGINT NOT NULL COMMENT '本金(金币)',
            current_value BIGINT NOT NULL COMMENT '当前市值(金币)',
            accumulated_profit BIGINT DEFAULT 0 COMMENT '累计盈亏(金币)',
            buy_date DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '购买时间',
            last_settlement DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '最后结算时间',
            is_active BOOLEAN DEFAULT TRUE COMMENT '是否持有中',
            INDEX idx_player_holding (player_id, is_active),
            INDEX idx_fund_holding (fund_id, is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='理财持仓表'
    """,
    "player_achievement": """
        CREATE TABLE IF NOT EXISTS player_achievement (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            player_id VARCHAR(32) NOT NULL COMMENT '玩家ID',
            achievement_id VARCHAR(64) NOT NULL COMMENT '成就ID',
            unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '解锁时间',
            progress INT DEFAULT 0 COMMENT '当前进度',
            is_completed BOOLEAN DEFAULT FALSE COMMENT '是否已完成',
            reward_claimed BOOLEAN DEFAULT FALSE COMMENT '是否已领取奖励',
            UNIQUE INDEX idx_player_achievement (player_id, achievement_id),
            INDEX idx_player_completed (player_id, is_completed),
            FOREIGN KEY (player_id) REFERENCES player(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家成就表'
    """,
    "player_stats": """
        CREATE TABLE IF NOT EXISTS player_stats (
            player_id VARCHAR(32) PRIMARY KEY COMMENT '玩家ID',
            cultivation_count INT DEFAULT 0 COMMENT '累计修炼次数',
            total_battles INT DEFAULT 0 COMMENT '总战斗次数',
            total_wins INT DEFAULT 0 COMMENT '总胜利次数',
            total_kills INT DEFAULT 0 COMMENT '总击杀数',
            gold_earned_total INT DEFAULT 0 COMMENT '累计获得金币',
            gold_spent_total INT DEFAULT 0 COMMENT '累计花费金币',
            locations_visited INT DEFAULT 0 COMMENT '探索过的地点数',
            locations_visited_list VARCHAR(1024) NULL COMMENT '探索过的地点列表(逗号分隔)',
            equipment_obtained INT DEFAULT 0 COMMENT '获得过的装备数',
            last_login_date DATETIME NULL COMMENT '最后登录日期',
            consecutive_login_days INT DEFAULT 0 COMMENT '连续登录天数',
            total_login_days INT DEFAULT 0 COMMENT '总登录天数',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            FOREIGN KEY (player_id) REFERENCES player(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家统计数据表'
    """,
    "npc_dialogue_history": """
        CREATE TABLE IF NOT EXISTS npc_dialogue_history (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            npc_id INT NOT NULL COMMENT 'NPC ID',
            player_id VARCHAR(32) NOT NULL COMMENT '玩家ID',
            dialogue_type VARCHAR(20) NOT NULL COMMENT '对话类型: natural_dialogue | game_command',
            player_input TEXT NOT NULL COMMENT '玩家输入',
            npc_response TEXT NOT NULL COMMENT 'NPC回复',
            game_command VARCHAR(255) NULL COMMENT '游戏指令内容（仅game_command类型）',
            game_output TEXT NULL COMMENT '游戏指令执行结果',
            game_command_status VARCHAR(20) DEFAULT 'success' COMMENT '指令执行状态: success | failed | partial',
            favorability_change INT DEFAULT 0 COMMENT '本次对话导致的好感度变化',
            favorability_after INT DEFAULT 50 COMMENT '本次对话后的总好感度',
            dialogue_duration_seconds INT DEFAULT 0 COMMENT '对话耗时(秒)',
            ai_tokens_used INT NULL COMMENT 'AI调用消耗的token数',
            ai_cost INT NULL COMMENT 'AI调用成本(分，人民币)',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '对话时间',
            INDEX idx_npc_id (npc_id),
            INDEX idx_player_id (player_id),
            INDEX idx_created_at (created_at),
            INDEX idx_npc_player_created (npc_id, player_id, created_at),
            FOREIGN KEY (npc_id) REFERENCES npc(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES player(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='NPC对话历史表'
    """,
    "npc_favorability": """
        CREATE TABLE IF NOT EXISTS npc_favorability (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            npc_id INT NOT NULL COMMENT 'NPC ID',
            player_id VARCHAR(32) NOT NULL COMMENT '玩家ID',
            current_favorability INT DEFAULT 50 COMMENT '当前好感度(0-100)',
            total_interactions INT DEFAULT 0 COMMENT '累计互动次数',
            total_favorability_gained INT DEFAULT 0 COMMENT '累计好感度获得（可为负）',
            relationship_level VARCHAR(20) DEFAULT '陌生人' COMMENT '关系等级: 陌生人|熟识|友好|亲密|知心',
            is_follower BOOLEAN DEFAULT FALSE COMMENT '是否跟随关系',
            is_partner BOOLEAN DEFAULT FALSE COMMENT '是否伴侣关系',
            milestone_events JSON NULL COMMENT '关键事件记录',
            first_interaction_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '首次互动时间',
            last_interaction_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后互动时间',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
            UNIQUE INDEX idx_npc_player_unique (npc_id, player_id),
            INDEX idx_npc_id (npc_id),
            INDEX idx_player_id (player_id),
            FOREIGN KEY (npc_id) REFERENCES npc(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES player(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='NPC好感度表'
    """,
    "npc_long_term_memory": """
        CREATE TABLE IF NOT EXISTS npc_long_term_memory (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            npc_id INT NOT NULL COMMENT 'NPC ID',
            player_id VARCHAR(32) NOT NULL COMMENT '玩家ID',
            memory_type VARCHAR(20) NOT NULL COMMENT '记忆类型: summary(对话总结) | event(关键事件)',
            content TEXT NOT NULL COMMENT '记忆内容（对话总结或事件描述）',
            event_type VARCHAR(20) NULL COMMENT '事件类型: gift|quest|promise|conflict|emotion|other',
            importance_score INT DEFAULT 5 COMMENT '重要性评分(1-10)',
            emotion_change INT DEFAULT 0 COMMENT '情感变化值（好感度变化）',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            weight FLOAT DEFAULT 1.0 COMMENT '记忆权重（随时间衰减）',
            last_accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '最后访问时间',
            from_dialogue_id INT NULL COMMENT '关联的起始对话ID',
            to_dialogue_id INT NULL COMMENT '关联的结束对话ID',
            metadata JSON NULL COMMENT '额外元数据',
            INDEX idx_npc_player_time (npc_id, player_id, created_at),
            INDEX idx_memory_type (memory_type),
            INDEX idx_importance (importance_score),
            INDEX idx_weight (weight),
            FOREIGN KEY (npc_id) REFERENCES npc(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES player(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='NPC长期记忆表'
    """,
    "npc_dialogue_summary_checkpoint": """
        CREATE TABLE IF NOT EXISTS npc_dialogue_summary_checkpoint (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
            npc_id INT NOT NULL COMMENT 'NPC ID',
            player_id VARCHAR(32) NOT NULL COMMENT '玩家ID',
            last_summarized_dialogue_id INT NOT NULL COMMENT '最后总结的对话ID',
            total_dialogues_summarized INT DEFAULT 0 COMMENT '已总结的对话总数',
            last_summary_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '最后总结时间',
            next_summary_threshold INT DEFAULT 20 COMMENT '下次总结的对话数阈值',
            UNIQUE INDEX idx_npc_player_checkpoint (npc_id, player_id),
            FOREIGN KEY (npc_id) REFERENCES npc(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES player(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='NPC对话总结检查点表'
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
# 警告: 这里定义的值必须与代码中的 Enum 类保持一致！
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
        print("[自动迁移] 检查数据库结构...")

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
                print(f"[√] [自动迁移] 完成！创建了 {tables_created} 个表，"
                      f"添加了 {fields_added} 个字段，{indexes_added} 个索引，"
                      f"修复了 {enums_fixed} 个 ENUM 列")
            else:
                print("[√] [自动迁移] 数据库结构已是最新")


async def _create_missing_tables(conn, verbose: bool) -> int:
    """创建缺失的表"""
    created_count = 0

    for table_name, create_sql in REQUIRED_TABLES.items():
        try:
            await conn.execute(text(create_sql))
            if verbose:
                print(f"  [创建] 表: {table_name}")
            created_count += 1
        except Exception as e:
            error_msg = str(e).lower()
            # 忽略"表已存在"错误
            if "already exists" in error_msg or "duplicate" in error_msg:
                if verbose:
                    logger.debug(f"  [√] 表 {table_name} 已存在")
            else:
                logger.error(f"[X] [自动迁移] 创建表 {table_name} 失败: {e}")

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
                logger.warning(f"[!] [自动迁移] 表 {table_name} 不存在，跳过字段检查")
            continue

        # 检查并添加缺失的字段
        for field_name, field_def in fields.items():
            if field_name not in existing_columns:
                try:
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {field_name} {field_def}"
                    await conn.execute(text(sql))

                    if verbose:
                        print(f"  [+] 添加字段: {table_name}.{field_name}")

                    added_count += 1

                except Exception as e:
                    error_msg = str(e).lower()
                    # 忽略"字段已存在"错误
                    if "duplicate" in error_msg or "exists" in error_msg:
                        if verbose:
                            logger.debug(f"  [√] 字段 {table_name}.{field_name} 已存在")
                    else:
                        logger.error(f"[X] [自动迁移] 添加字段 {table_name}.{field_name} 失败: {e}")

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
                logger.error(f"[X] [自动迁移] 创建索引 {idx_name} 失败: {e}")

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
                    logger.error(f"[X] 缺失字段: {table_name}.{field_name}")
                    return False

        logger.info("[√] 所有必需字段都已存在")
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
                        logger.warning(f"[!] [ENUM检查] 表 {table_name} 或列 {column_name} 不存在，跳过")
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
                    print(f"  [修复] 修复 ENUM 列: {table_name}.{column_name}")
                    if missing_values:
                        print(f"     缺失值: {', '.join(missing_values)}")
                    if extra_values:
                        print(f"     多余值: {', '.join(extra_values)} (将保留)")

                # 4. 重建 ENUM 列
                await _rebuild_enum_column(conn, table_name, column_name, expected_values, verbose)
                fixed_count += 1

                if verbose:
                    print(f"     [√] 修复完成")

            except Exception as e:
                logger.error(f"[X] [ENUM修复] 处理 {table_name}.{column_name} 失败: {e}")

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
    重建 ENUM 列（安全的方式，带数据验证）

    步骤：
    0. 验证现有数据中的所有值都在新 ENUM 中（新增）
    1. 创建临时 VARCHAR 列
    2. 复制数据到临时列
    3. 删除旧 ENUM 列
    4. 创建新 ENUM 列（包含所有期望的值）
    5. 恢复数据（分步进行，便于诊断）
    6. 验证数据恢复完整性（新增）
    7. 删除临时列

    Args:
        conn: 数据库连接
        table_name: 表名
        column_name: 列名
        new_values: 新的 ENUM 值列表
        verbose: 是否打印详细日志
    """
    temp_column = f"{column_name}_temp_migration"

    try:
        # ===== 步骤 0: 验证现有数据 =====
        if verbose:
            print(f"     验证现有数据...")

        result = await conn.execute(
            text(f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL")
        )
        actual_data_values = {row[0] for row in result.fetchall()}

        if verbose:
            print(f"     现有数据中的值: {actual_data_values}")
            print(f"     新 ENUM 定义的值: {set(new_values)}")

        # 检查是否有数据值不在新 ENUM 中
        unsupported_values = actual_data_values - set(new_values)
        if unsupported_values:
            error_msg = f"数据中存在新 ENUM 不支持的值: {unsupported_values}"
            logger.error(f"[X] {error_msg}")
            logger.error(f"   请先更新 REQUIRED_ENUMS 或手动处理这些数据")
            raise ValueError(error_msg)

        if verbose:
            print(f"     ✓ 数据验证通过")

        # ===== 获取列的完整定义 =====
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

        # ===== 步骤 1-4: 基础迁移步骤 =====
        basic_steps = [
            ("添加临时列", f"ALTER TABLE {table_name} ADD COLUMN {temp_column} VARCHAR(100)"),
            ("复制数据到临时列", f"UPDATE {table_name} SET {temp_column} = {column_name}"),
            ("删除旧 ENUM 列", f"ALTER TABLE {table_name} DROP COLUMN {column_name}"),
            ("创建新 ENUM 列", f"ALTER TABLE {table_name} ADD COLUMN {column_name} ENUM({enum_values_str}) {attrs_str}"),
        ]

        for step_name, step_sql in basic_steps:
            if verbose:
                print(f"     {step_name}...")
            await conn.execute(text(step_sql))

        # ===== 步骤 5: 分步恢复数据（改进） =====
        if verbose:
            print(f"     恢复数据...")

        total_restored = 0
        for value in actual_data_values:
            update_sql = f"UPDATE {table_name} SET {column_name} = :value WHERE {temp_column} = :value"
            result = await conn.execute(text(update_sql), {"value": value})
            row_count = result.rowcount
            total_restored += row_count

            if verbose:
                print(f"       恢复值 '{value}': {row_count} 行")

        # ===== 步骤 6: 验证数据恢复完整性 =====
        if verbose:
            print(f"     验证数据完整性...")

        result = await conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL AND {temp_column} IS NOT NULL")
        )
        orphaned_count = result.scalar()

        if orphaned_count > 0:
            error_msg = f"数据恢复不完整: {orphaned_count} 行数据未能恢复"
            logger.error(f"[X] {error_msg}")
            raise ValueError(error_msg)

        if verbose:
            print(f"     ✓ 数据恢复完整 (总计 {total_restored} 行)")

        # ===== 步骤 7: 删除临时列 =====
        if verbose:
            print(f"     删除临时列...")
        await conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {temp_column}"))

    except Exception as e:
        logger.error(f"重建 ENUM 列失败: {table_name}.{column_name}: {e}")
        # 尝试清理临时列
        try:
            await conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {temp_column}"))
        except:
            pass
        raise
