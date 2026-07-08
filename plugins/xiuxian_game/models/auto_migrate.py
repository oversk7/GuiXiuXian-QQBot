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
    "player": {
        "exp": "BIGINT NOT NULL DEFAULT 0 COMMENT '经验'",
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
        "last_group_openid": "VARCHAR(64) DEFAULT NULL COMMENT '最近活跃QQ群openid'",
        "last_group_member_id": "VARCHAR(64) DEFAULT NULL COMMENT '最近活跃QQ群成员openid(用于@)'",
        "last_group_username": "VARCHAR(64) DEFAULT NULL COMMENT '最近活跃QQ群昵称(用于@展示)'",
        "inventory_compact": "BOOLEAN NOT NULL DEFAULT 0 COMMENT '背包精简模式'",
        "anti_combo_rate": "INTEGER NOT NULL DEFAULT 0 COMMENT '抗连击率(百分比)'",
        "anti_counter_rate": "INTEGER NOT NULL DEFAULT 0 COMMENT '抗反击率(百分比)'",
        "dungeon_kill_streak": "INTEGER NOT NULL DEFAULT 0 COMMENT '诡域无伤连杀数(死亡或返回清零)'",
    },
    "guild": {
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
        "boss_level": "INTEGER NOT NULL DEFAULT 1 COMMENT '镇诡凶戾度'",
        "boss_week_summons": "INTEGER NOT NULL DEFAULT 0 COMMENT '今日开坛次数(列名沿用week为历史原因)'",
        "boss_week_key": "VARCHAR(10) NOT NULL DEFAULT '' COMMENT '开坛计数所属日期键YYYY-MM-DD'",
    },
    "player_donation_log": {
        "amount": "BIGINT NOT NULL DEFAULT 0 COMMENT '捐献金币金额'",
    },
    "guild_building": {
        "plot_x": "INTEGER DEFAULT NULL COMMENT '公会基地布局X坐标'",
        "plot_y": "INTEGER DEFAULT NULL COMMENT '公会基地布局Y坐标'",
    },
    "market_orders": {
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
    },
    "auction_item": {
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
    },
    "world_tile": {
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
    },
    "red_envelope": {
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
    },
    "invite_reward": {
        "server_id": "INTEGER NOT NULL DEFAULT 1 COMMENT '所属区服ID'",
    },
    "elixir_usage_log": {
        "attribute_changes": "JSON DEFAULT ('{}') COMMENT '累计实际属性变动JSON'",
    },
    "fishing_record": {
        "dungeon_level": "INTEGER NOT NULL DEFAULT 0 COMMENT '钓鱼时诡域层级(0=现实世界)'",
    },
    "fishing_stats": {
        "max_fishing_dungeon_level": "INTEGER NOT NULL DEFAULT 0 COMMENT '钓到鱼的最深诡域层级'",
    },
    # 添加新字段时在此处定义，重启 bot 后自动迁移，迁移完成后移入下方注释
    #
    # 已完成迁移的字段（勿删除注释，留作记录）:
    # - stocks: relisted_at, relist_reason, health, health_decay_rate, is_active, delisted_at, delist_reason
    # - lottery: description
    # - player: incense, max_apprentice_slots, mentor_cooldown_until, gui_zhu,
    #           allocated_attrs, extra_attrs, vip_equipment_data, vip_skill_cooldown, last_active_at,
    #           demon_coins, last_system_check, last_guild_check,
    #           fenjin_charge, fenjin_last_update, fenjin_last_charge,
    #           completed_trials, charm, daily_gift_purchases
    # - trade_record: is_cross_market
    # - player_relationship: master_id, apprentice_level_at_start, total_incense_contributed,
    #           established_at, mentorship_request_status/time, mentorship_reject_time,
    #           marriage_request_status/time, marriage_reject_time, marriage_proposer_id,
    #           sworn_request_status/time, sworn_reject_time, sworn_proposer_id
    # - restaurant: last_recruit_time, daily_recruit_count, last_recruit_date, storage_level, signature_recipe_id
    # - chef: experience
    # - inventory: item_id (VARCHAR(64))
    # - spirit_field_steal_log: stolen_summary
    # - lower_world_stronghold: last_battle_at, best_wave
    # - world_message: scope, guild_id, is_deleted, deleted_by, deleted_at
    # - market_state: last_restock_time
    # - fund_holding: maturity_date
    # - world_boss_damage: reincarnation_snapshot
    # - pet_instance: evolved_rarity, transform_gender, daily_feed_count, daily_feed_date, gift_last_date, custom_personality
    # - auction_item: current_bidder_name, seller_name, seller_uid, current_bidder_uid, description
    # - auction_bid_history: bidder_uid
    # - russian_roulette_pve_game: (all fields)
    # - player_stats: npc_gifts_received, gold_earned_total, gold_spent_total, locations_visited_list
    # - player_job_stats: job_proficiency
    # - daily_task: quest_chain_id, quest_step, is_tutorial, auto_accept
    # - navigation_task: initial_distance
    # - location: expires_at
}


# 定义需要自动创建的表（仅用于新表创建，不修改已有表）
# 注意：这会调用 CREATE TABLE IF NOT EXISTS
REQUIRED_TABLES: Dict[str, str] = {
    # 添加新表时在此处定义 CREATE TABLE IF NOT EXISTS 语句
    # 已创建的表通过 ORM Base.metadata.create_all 自动管理
}


# 定义需要自动创建的普通索引
# 格式: [(表名, 索引名, 索引列)]
REQUIRED_INDEXES: List[Tuple[str, str, str]] = [
    # 添加新索引时在此处定义: (表名, 索引名, 索引列)
    ("player", "ix_player_server_id", "server_id"),
    ("guild", "ix_guild_server_id", "server_id"),
    ("market_orders", "ix_market_orders_server_id", "server_id"),
    ("auction_item", "ix_auction_item_server_id", "server_id"),
    ("world_tile", "ix_world_tile_server_id", "server_id"),
    ("red_envelope", "ix_red_envelope_server_id", "server_id"),
    ("invite_reward", "ix_invite_reward_server_id", "server_id"),
    # 2026-07 性能优化：高频查询缺失索引
    ("player", "ix_player_guild_id", "guild_id"),          # 公会成员/公会经济按 guild_id 过滤
    ("player", "ix_player_nickname", "nickname"),          # 按名字攻击玩家（PVP热路径）
    ("player", "ix_player_level", "level"),                # 世界BOSS取最高等级玩家
    ("guild_member", "ix_guild_member_guild_player", "guild_id, player_id"),  # 公会成员定位
]


# 定义需要替换的旧唯一索引/约束
# 格式: [(表名, 旧索引名, 旧索引列)]
LEGACY_UNIQUE_INDEXES: List[Tuple[str, str | None, Tuple[str, ...]]] = [
    # 多区服后，阴宅和地图坐标唯一性需要包含 server_id。
    ("player", "idx_mansion_location_unique", ("mansion_x", "mansion_y")),
    ("world_tile", "uq_region_coordinates", ("region", "x", "y")),
    # 旧公会名全局唯一，多区服后改为同服唯一。
    ("guild", None, ("name",)),
]


# 定义需要自动创建的唯一索引
# 格式: [(表名, 索引名, 索引列, SQLite WHERE 条件)]
REQUIRED_UNIQUE_INDEXES: List[Tuple[str, str, str, str | None]] = [
    (
        "player",
        "idx_mansion_location_unique",
        "server_id, mansion_x, mansion_y",
        "mansion_level > 0 AND mansion_x IS NOT NULL AND mansion_y IS NOT NULL",
    ),
    ("world_tile", "uq_server_region_coordinates", "server_id, region, x, y", None),
    ("guild", "uq_guild_server_name", "server_id, name", None),
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
    "guild_building": {
        "building_type": [
            "EXPERIENCE_SHRINE",
            "TREASURY_VAULT",
            "TRAINING_GROUND",
            "SPIRIT_TOWER",
            "DEFENSE_WALL",
            "TELEPORT_ARRAY",
            "ALCHEMY_ROOM",
            "GUILD_WAREHOUSE",
            "ARTIFACT_FORGE",
            "REFINING_PAVILION",
        ],
    },
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

        # 3. 替换旧唯一索引/约束
        unique_indexes_migrated = await _migrate_unique_indexes(conn, verbose)

        # 4. 创建缺失的索引
        indexes_added = await _add_missing_indexes(conn, verbose)

        # 5. 检测并修复 ENUM 列
        enums_fixed = await _fix_enum_columns(conn, verbose)

        if verbose:
            if tables_created > 0 or fields_added > 0 or unique_indexes_migrated > 0 or indexes_added > 0 or enums_fixed > 0:
                print(f"[√] [自动迁移] 完成！创建了 {tables_created} 个表，"
                      f"添加了 {fields_added} 个字段，"
                      f"迁移了 {unique_indexes_migrated} 个唯一索引，"
                      f"{indexes_added} 个普通索引，"
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


def _normalize_field_def_for_dialect(field_def: str, dialect_name: str) -> str:
    """按数据库方言调整字段定义。"""
    if dialect_name != "sqlite":
        return field_def
    # SQLite 的 ALTER TABLE ADD COLUMN 不支持 COMMENT。
    return re.sub(r"\s+COMMENT\s+'[^']*'", "", field_def)


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
            normalized_field_def = _normalize_field_def_for_dialect(field_def, conn.dialect.name)
            # 提取目标类型 (例如: "BIGINT DEFAULT 0" -> "BIGINT")
            target_type = normalized_field_def.split()[0].upper()

            if field_name not in existing_columns:
                # 字段不存在,添加新字段
                try:
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {field_name} {normalized_field_def}"
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
                        if conn.dialect.name == "sqlite":
                            if verbose:
                                logger.warning(
                                    "[!] [自动迁移] SQLite 不支持在线修改字段类型，跳过 %s.%s: %s -> %s",
                                    table_name,
                                    field_name,
                                    current_type,
                                    target_type,
                                )
                            continue

                        sql = f"ALTER TABLE {table_name} MODIFY COLUMN {field_name} {normalized_field_def}"
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


def _same_columns(actual: list[str] | tuple[str, ...], expected: tuple[str, ...]) -> bool:
    return tuple(actual) == expected


async def _get_index_metadata(conn, table_name: str) -> tuple[list[dict], list[dict]]:
    """读取表的普通索引和唯一约束元数据。"""

    def inspect_indexes(connection):
        inspector = inspect(connection)
        try:
            indexes = inspector.get_indexes(table_name)
        except Exception:
            indexes = []
        try:
            unique_constraints = inspector.get_unique_constraints(table_name)
        except Exception:
            unique_constraints = []
        return indexes, unique_constraints

    return await conn.run_sync(inspect_indexes)


async def _drop_index_or_constraint(conn, table_name: str, index_name: str, verbose: bool) -> bool:
    """按当前数据库方言删除索引/唯一约束。"""
    dialect = conn.dialect.name
    try:
        if dialect == "mysql":
            await conn.execute(text(f"ALTER TABLE {table_name} DROP INDEX {index_name}"))
        elif dialect == "sqlite":
            if index_name.startswith("sqlite_autoindex"):
                if verbose:
                    logger.warning(
                        "[!] [自动迁移] SQLite 自动唯一约束 %s.%s 无法在线删除，请新库验证多服地图/公会重复名",
                        table_name,
                        index_name,
                    )
                return False
            await conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
        else:
            await conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

        if verbose:
            print(f"  [-] 删除旧唯一索引: {table_name}.{index_name}")
        return True
    except Exception as e:
        logger.error(f"[X] [自动迁移] 删除旧唯一索引 {table_name}.{index_name} 失败: {e}")
        return False


async def _migrate_unique_indexes(conn, verbose: bool) -> int:
    """迁移多区服需要调整的唯一索引。"""
    migrated_count = 0

    # 先删除旧唯一索引/约束。
    for table_name, legacy_name, legacy_columns in LEGACY_UNIQUE_INDEXES:
        indexes, unique_constraints = await _get_index_metadata(conn, table_name)
        candidates: list[str] = []

        for idx in indexes:
            idx_name = idx.get("name")
            idx_columns = tuple(idx.get("column_names") or [])
            if not idx_name:
                continue
            if legacy_name and idx_name == legacy_name and _same_columns(idx_columns, legacy_columns):
                candidates.append(idx_name)
            elif idx.get("unique") and _same_columns(idx_columns, legacy_columns):
                candidates.append(idx_name)

        for constraint in unique_constraints:
            constraint_name = constraint.get("name")
            constraint_columns = tuple(constraint.get("column_names") or [])
            if not constraint_name:
                continue
            if legacy_name and constraint_name == legacy_name and _same_columns(constraint_columns, legacy_columns):
                candidates.append(constraint_name)
            elif _same_columns(constraint_columns, legacy_columns):
                candidates.append(constraint_name)

        for index_name in sorted(set(candidates)):
            if await _drop_index_or_constraint(conn, table_name, index_name, verbose):
                migrated_count += 1

    # 再创建新的唯一索引。
    for table_name, idx_name, idx_cols, sqlite_where in REQUIRED_UNIQUE_INDEXES:
        try:
            dialect = conn.dialect.name
            where_clause = f" WHERE {sqlite_where}" if dialect == "sqlite" and sqlite_where else ""
            await conn.execute(text(f"CREATE UNIQUE INDEX {idx_name} ON {table_name}({idx_cols}){where_clause}"))
            if verbose:
                print(f"  [+] 创建唯一索引: {idx_name}")
            migrated_count += 1
        except Exception as e:
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "exists" in error_msg:
                if verbose:
                    logger.debug(f"  [√] 唯一索引 {idx_name} 已存在")
            else:
                logger.error(f"[X] [自动迁移] 创建唯一索引 {idx_name} 失败: {e}")

    return migrated_count


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
