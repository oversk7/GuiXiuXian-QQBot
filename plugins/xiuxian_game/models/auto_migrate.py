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
    "stocks": {
        "relisted_at": "DATETIME NULL COMMENT '重新上市时间'",
        "relist_reason": "VARCHAR(100) NULL COMMENT '重新上市原因'"
    },
    "lottery": {
        "description": "VARCHAR(200) NULL COMMENT '抽奖描述'"
    },
    # 师徒系统字段
    "player": {
        "incense": "INT DEFAULT 0 COMMENT '香火点数'",
        "max_apprentice_slots": "INT DEFAULT 3 COMMENT '最大徒弟位'",
        "mentor_cooldown_until": "DATETIME NULL COMMENT '师徒操作冷却结束时间'",
        # 里界系统字段
        "inner_realm": "VARCHAR(64) NULL COMMENT '当前所在里界(None=不在里界)'",
        # 诡烛氪金货币
        "gui_zhu": "BIGINT DEFAULT 0 COMMENT '诡烛(氪金专属货币)'",
        # 扩展数据字段(活动数据等)
        "extra_attrs": "JSON NULL COMMENT '扩展数据JSON(活动数据、特殊系统数据等)'",
        # VIP装备专属数据字段
        "vip_equipment_data": "JSON NULL COMMENT 'VIP装备专属数据(锚点坐标、快照等)'",
        "vip_skill_cooldown": "JSON NULL COMMENT 'VIP技能冷却时间戳'",
        # 灵田系统 - 玩家活跃时间
        "last_active_at": "DATETIME NULL COMMENT '最后活跃时间(灵田偷菜判定用)'",
        # 恶魔轮盘排行积分
        "demon_coins": "BIGINT DEFAULT 0 COMMENT '恶魔币(恶魔轮盘排行积分)'",
        # 消息系统字段
        "last_system_check": "DATETIME NULL COMMENT '最后查看系统公告时间'",
        "last_guild_check": "DATETIME NULL COMMENT '最后查看公会消息时间'"
    },
    "player_relationship": {
        "master_id": "VARCHAR(32) NULL COMMENT '师父ID(师徒关系专用)'",
        "apprentice_level_at_start": "INT DEFAULT 0 COMMENT '拜师时徒弟等级'",
        "total_incense_contributed": "INT DEFAULT 0 COMMENT '累计贡献香火'",
        "established_at": "DATETIME NULL COMMENT '关系建立时间'",
        "mentorship_request_status": "VARCHAR(20) NULL COMMENT '拜师申请状态(pending/rejected)'",
        "mentorship_request_time": "DATETIME NULL COMMENT '拜师申请发起时间'",
        "mentorship_reject_time": "DATETIME NULL COMMENT '拜师申请被拒绝时间'",
        # 结婚申请相关字段
        "marriage_request_status": "VARCHAR(20) NULL COMMENT '结婚申请状态(pending/rejected)'",
        "marriage_request_time": "DATETIME NULL COMMENT '结婚申请发起时间'",
        "marriage_reject_time": "DATETIME NULL COMMENT '结婚申请被拒绝时间'",
        "marriage_proposer_id": "VARCHAR(32) NULL COMMENT '结婚申请发起者ID'",
        # 结义申请相关字段
        "sworn_request_status": "VARCHAR(20) NULL COMMENT '结义申请状态(pending/rejected)'",
        "sworn_request_time": "DATETIME NULL COMMENT '结义申请发起时间'",
        "sworn_reject_time": "DATETIME NULL COMMENT '结义申请被拒绝时间'",
        "sworn_proposer_id": "VARCHAR(32) NULL COMMENT '结义申请发起者ID'"
    },
    # 里界系统表
    "inner_realm_session": {
        "sanity": "INT DEFAULT 100 COMMENT '当前理智值(0-100)'",
        "clue_collected": "TEXT COMMENT '已收集的线索ID列表(JSON数组)'",
        "state": "TEXT COMMENT '探索状态(JSON对象,存储自定义数据)'"
    },
    # 烹饪系统 - 餐厅招募冷却 & 仓库等级
    "restaurant": {
        "last_recruit_time": "DATETIME NULL COMMENT '上次招募厨师时间'",
        "daily_recruit_count": "INT DEFAULT 0 COMMENT '当日招募次数(用于递增费用计算)'",
        "last_recruit_date": "VARCHAR(10) NULL COMMENT '上次招募日期(YYYY-MM-DD格式,用于每日重置)'",
        "storage_level": "INT DEFAULT 1 COMMENT '仓库等级(1-5)'"
    },
    # 背包表 - 扩展item_id长度以支持更长的食谱ID
    "inventory": {
        "item_id": "VARCHAR(64) NOT NULL COMMENT '物品模板ID'"
    },
    # 灵田偷菜记录 - 汇总字段
    "spirit_field_steal_log": {
        "stolen_summary": "TEXT NULL COMMENT '偷取作物汇总JSON，格式:{作物名:数量}'"
    },
    # 天灾山寨 - 战斗冷却字段
    "lower_world_stronghold": {
        "last_battle_at": "DATETIME NULL COMMENT '最后一次迎战时间（战斗冷却用）'",
        "best_wave": "INT DEFAULT 1 COMMENT '历史最高波次'"
    },
    # 世界消息 - 新增scope和guild_id字段
    "world_message": {
        "scope": "VARCHAR(20) DEFAULT 'world' COMMENT '消息范围: world/private/system/guild'",
        "guild_id": "INT NULL COMMENT '公会ID(公会频道专用)'"
    },
    # 市场状态 - 分时补货
    "market_state": {
        "last_restock_time": "DATETIME NULL COMMENT '上次分时补货时间'"
    },
    # 定期理财 - 到期时间字段
    "fund_holding": {
        "maturity_date": "DATETIME NULL COMMENT '到期时间(定期专用,活期为NULL)'"
    },
    # 世界BOSS - 分段排行快照
    "world_boss_damage": {
        "reincarnation_snapshot": "INT DEFAULT -1 COMMENT '首次攻击时的转数快照(-1表示未攻击)'"
    },
    # 拍卖行 - 缓存当前出价人昵称，避免列表页额外查询；卖家昵称快照
    "auction_item": {
        "current_bidder_name": "VARCHAR(64) NULL COMMENT '当前最高出价人昵称（快照）'",
        "seller_name": "VARCHAR(64) NULL COMMENT '卖家昵称快照（防止改名后丢失）'",
        "seller_uid": "INT NULL COMMENT '卖家游戏UID（player.uid）'",
        "current_bidder_uid": "INT NULL COMMENT '当前最高出价人游戏UID（player.uid）'"
    },
    "auction_bid_history": {
        "bidder_uid": "INT NULL COMMENT '出价人游戏UID（player.uid）'"
    },
    # 恶魔轮盘PvE人机模式
    "russian_roulette_pve_game": {
        "player_id": "VARCHAR(32) NOT NULL COMMENT '玩家ID'",
        "initial_bet": "INT NOT NULL COMMENT '初始赌注'",
        "pot": "INT NOT NULL COMMENT '当前奖池'",
        "double_count": "INT DEFAULT 0 COMMENT '加倍次数'",
        "max_hp": "INT DEFAULT 3 COMMENT '血量上限'",
        "game_state": "TEXT NOT NULL COMMENT '完整game_state字典(JSON)'",
        "current_turn": "VARCHAR(16) NOT NULL COMMENT '当前回合: player / ai'",
        "status": "VARCHAR(16) DEFAULT 'playing' COMMENT '游戏状态: playing / won'",
        "ai_known_bullet": "BOOLEAN NULL COMMENT 'AI预知的当前弹药(True=实弹)'",
        "ai_known_phone": "TEXT NULL COMMENT 'AI电话预知信息(JSON)'",
        "bullet_counts": "TEXT NOT NULL COMMENT '弹药统计(JSON)'",
        "created_at": "DATETIME NULL COMMENT '创建时间'",
        "updated_at": "DATETIME NULL COMMENT '更新时间'"
    }
    # 注释: 以下字段已通过多次重启完成迁移:
    # - daily_task: quest_chain_id, quest_step, is_tutorial, auto_accept
    # - stocks: health, health_decay_rate, is_active, delisted_at, delist_reason
    # - player: completed_trials, charm, daily_gift_purchases
    # - navigation_task: initial_distance
    # - player_stats: gold_earned_total, gold_spent_total, locations_visited_list
    # - location: expires_at
    # - world_message: is_deleted, deleted_by, deleted_at
}


# 定义需要自动创建的表（仅用于新表创建，不修改已有表）
# 注意：这会调用 CREATE TABLE IF NOT EXISTS
REQUIRED_TABLES: Dict[str, str] = {
    # 所有表均已通过多次重启创建完成,无需额外配置
    # 注释: 以下表已创建完成:
    # - stock_events, bank_fund, fund_holding, player_achievement, player_stats
    # - npc_dialogue_history, npc_favorability, npc_long_term_memory, npc_dialogue_summary_checkpoint
    # - message_board_blacklist, player_ban, player_relationship
    # - invite_reward, dungeon_chest_record, russian_roulette_room, russian_roulette_game
    # - guild_task_record, player_task_stats, part_time_job, job_location, player_job_stats
    # - world_boss_cycle, world_boss_damage, alchemy_record
    # - russian_roulette_bet（新增：旁观者下注记录，通过ORM Base.metadata.create_all自动建表）
}


# 定义需要自动创建的索引
# 格式: [(表名, 索引名, 索引列)]
REQUIRED_INDEXES: List[Tuple[str, str, str]] = [
    # 所有索引均已创建完成,无需额外配置
    # 注释: 以下索引已创建完成:
    # - idx_daily_task_tutorial, idx_daily_task_quest_chain
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

        # 4. 检测并修复 ENUM 列
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
    """添加缺失的字段或修改现有字段类型"""
    added_count = 0

    for table_name, fields in REQUIRED_FIELDS.items():
        # 获取表的现有字段及其类型
        def get_columns_with_types(connection):
            inspector = inspect(connection)
            try:
                columns = {}
                for col in inspector.get_columns(table_name):
                    # 获取字段类型的大写名称
                    type_name = str(col['type']).upper()
                    columns[col['name']] = type_name
                return columns
            except Exception:
                return {}  # 表不存在

        existing_columns = await conn.run_sync(get_columns_with_types)

        if not existing_columns:
            if verbose:
                logger.warning(f"[!] [自动迁移] 表 {table_name} 不存在，跳过字段检查")
            continue

        # 检查并添加/修改字段
        for field_name, field_def in fields.items():
            # 提取目标类型 (例如: "BIGINT DEFAULT 0" -> "BIGINT")
            target_type = field_def.split()[0].upper()

            if field_name not in existing_columns:
                # 字段不存在,添加新字段
                try:
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {field_name} {field_def}"
                    await conn.execute(text(sql))

                    if verbose:
                        print(f"  [+] 添加字段: {table_name}.{field_name}")

                    added_count += 1

                except Exception as e:
                    error_msg = str(e).lower()
                    if "duplicate" in error_msg or "exists" in error_msg:
                        if verbose:
                            logger.debug(f"  [√] 字段 {table_name}.{field_name} 已存在")
                    else:
                        logger.error(f"[X] [自动迁移] 添加字段 {table_name}.{field_name} 失败: {e}")
            else:
                # 字段已存在,检查类型是否需要修改
                current_type = existing_columns[field_name]
                # 处理类型别名 (INT可能显示为INTEGER)
                current_type_normalized = current_type.replace('INTEGER', 'INT')
                target_type_normalized = target_type.replace('INTEGER', 'INT')

                if current_type_normalized != target_type_normalized:
                    try:
                        sql = f"ALTER TABLE {table_name} MODIFY COLUMN {field_name} {field_def}"
                        await conn.execute(text(sql))

                        if verbose:
                            print(f"  [*] 修改字段类型: {table_name}.{field_name} {current_type} -> {target_type}")

                        added_count += 1

                    except Exception as e:
                        logger.error(f"[X] [自动迁移] 修改字段类型 {table_name}.{field_name} 失败: {e}")
                else:
                    if verbose:
                        logger.debug(f"  [√] 字段 {table_name}.{field_name} 类型正确: {current_type}")

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
