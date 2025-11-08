"""
SQLite 到 MySQL 数据迁移脚本

功能：
1. 从 SQLite 读取所有数据
2. 批量写入 MySQL
3. 验证数据完整性
4. 生成迁移报告

使用方法：
    python scripts/migrate_sqlite_to_mysql.py

注意事项：
1. 运行前确保 MySQL 数据库已创建
2. 运行前确保 MySQL 表结构已初始化（运行一次 bot.py）
3. 建议在低峰期运行
4. 迁移过程中不要操作数据库
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, MetaData, Table, select, inspect, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import yaml


class DatabaseMigrator:
    """数据库迁移器"""
    
    def __init__(self):
        self.sqlite_engine = None
        self.mysql_engine = None
        self.migration_stats = {}
        
    def load_config(self) -> dict:
        """加载数据库配置"""
        config_path = project_root / "plugins" / "xiuxian_game" / "config" / "database.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def build_sqlite_url(self, config: dict) -> str:
        """构建 SQLite 连接 URL"""
        sqlite_config = config["database"]["sqlite"]
        db_path = project_root / "plugins" / "xiuxian_game" / sqlite_config["path"]
        return f"sqlite:///{db_path}"
    
    def build_mysql_url(self, config: dict) -> str:
        """构建 MySQL 连接 URL"""
        mysql_config = config["database"]["mysql"]
        host = mysql_config["host"]
        port = mysql_config["port"]
        user = mysql_config["user"]
        password = mysql_config["password"]
        database = mysql_config["database"]
        charset = mysql_config.get("charset", "utf8mb4")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"
    
    async def connect(self):
        """连接数据库"""
        print("🔗 正在连接数据库...")
        
        config = self.load_config()
        
        # 创建同步引擎（用于数据迁移）
        sqlite_url = self.build_sqlite_url(config)
        mysql_url = self.build_mysql_url(config)
        
        self.sqlite_engine = create_engine(sqlite_url)
        self.mysql_engine = create_engine(mysql_url)
        
        print(f"✅ SQLite 已连接: {sqlite_url}")
        print(f"✅ MySQL 已连接: {mysql_url.split('@')[-1]}")
    
    def get_table_names(self) -> List[str]:
        """获取所有表名，按依赖关系排序"""
        inspector = inspect(self.sqlite_engine)
        tables = inspector.get_table_names()

        # 排除 alembic 版本表
        tables = [t for t in tables if t != "alembic_version"]

        # 定义表的依赖关系（被依赖的表要先迁移）
        # 格式：{表名: [依赖的表...]}
        dependencies = {
            "player": [],  # 基础表，无依赖
            "inventory": ["player"],  # 依赖 player
            "alchemy_record": ["player", "inventory"],  # 依赖 player 和 inventory
            "fishing_record": ["player"],
            "fishing_stats": ["player"],
            "trade_record": ["player"],
            "dungeon_chest_record": ["player"],
            "stocks": [],
            "stock_price_history": ["stocks"],
            "stock_holdings": ["player", "stocks"],
            # 其他表可以按默认顺序
        }

        # 拓扑排序
        sorted_tables = []
        visited = set()

        def visit(table: str):
            if table in visited:
                return
            visited.add(table)

            # 先访问依赖的表
            if table in dependencies:
                for dep in dependencies[table]:
                    if dep in tables:
                        visit(dep)

            sorted_tables.append(table)

        # 先处理有依赖关系的表
        for table in tables:
            if table in dependencies:
                visit(table)

        # 再处理其他表
        for table in tables:
            if table not in sorted_tables:
                sorted_tables.append(table)

        return sorted_tables

    def clear_mysql_data(self) -> None:
        """清空 MySQL 中的所有数据（保留表结构）"""
        print("\n🧹 正在清空 MySQL 数据...")

        table_names = self.get_table_names()
        # 反向顺序删除（先删除依赖表）
        table_names_reversed = list(reversed(table_names))

        with self.mysql_engine.connect() as mysql_conn:
            # 临时禁用外键检查
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

            for table_name in table_names_reversed:
                try:
                    mysql_conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))
                    print(f"  ✅ 已清空表: {table_name}")
                except Exception as e:
                    print(f"  ⚠️ 清空表 {table_name} 失败: {e}")

            # 重新启用外键检查
            mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            mysql_conn.commit()

        print("✅ MySQL 数据已清空")

    def create_mysql_tables(self) -> None:
        """在 MySQL 中创建所有表结构"""
        print("\n🔧 正在创建 MySQL 表结构...")

        # 获取所有表名
        table_names = self.get_table_names()

        # 反射 SQLite 表结构并在 MySQL 中创建
        metadata = MetaData()

        for table_name in table_names:
            # 从 SQLite 反射表结构
            Table(table_name, metadata, autoload_with=self.sqlite_engine)

        # 在 MySQL 中创建所有表
        try:
            metadata.create_all(self.mysql_engine)
            print(f"✅ 成功创建 {len(table_names)} 个表")
        except Exception as e:
            print(f"⚠️ 创建表时出现警告: {e}")
            print("  （如果表已存在，可以忽略此警告）")
    
    def get_foreign_keys(self, table_name: str) -> List[Dict[str, str]]:
        """获取表的外键信息（从 MySQL 获取，因为 SQLite 可能没有外键元数据）"""
        try:
            inspector = inspect(self.mysql_engine)
            foreign_keys = inspector.get_foreign_keys(table_name)

            # 返回格式: [{"column": "player_id", "ref_table": "player", "ref_column": "id"}, ...]
            fk_info = []
            for fk in foreign_keys:
                if fk.get("constrained_columns") and fk.get("referred_table"):
                    fk_info.append({
                        "column": fk["constrained_columns"][0],  # 外键列
                        "ref_table": fk["referred_table"],  # 引用的表
                        "ref_column": fk["referred_columns"][0] if fk.get("referred_columns") else "id"
                    })

            return fk_info
        except Exception as e:
            print(f"  ⚠️ 无法获取表 {table_name} 的外键信息: {e}")
            return []

    def get_valid_foreign_key_values(self, ref_table: str, ref_column: str) -> set:
        """获取引用表中的所有有效值"""
        metadata = MetaData()
        table = Table(ref_table, metadata, autoload_with=self.mysql_engine)

        with self.mysql_engine.connect() as mysql_conn:
            result = mysql_conn.execute(select(table.c[ref_column]))
            return {row[0] for row in result.fetchall()}

    def clean_data(self, table_name: str, rows: List) -> List:
        """清理数据，处理外键约束问题和字符串截断"""
        if len(rows) == 0:
            return []

        # 获取该表的所有外键
        foreign_keys = self.get_foreign_keys(table_name)

        # 输出外键信息
        if foreign_keys:
            print(f"  🔍 检测到 {len(foreign_keys)} 个外键约束:")
            for fk in foreign_keys:
                print(f"     - {fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")

            # 获取所有外键的有效值
            valid_values_cache = {}
            for fk in foreign_keys:
                ref_table = fk["ref_table"]
                ref_column = fk["ref_column"]
                cache_key = f"{ref_table}.{ref_column}"

                if cache_key not in valid_values_cache:
                    try:
                        valid_values = self.get_valid_foreign_key_values(ref_table, ref_column)
                        valid_values_cache[cache_key] = valid_values
                        print(f"  📊 {cache_key} 有 {len(valid_values)} 个有效值")
                    except Exception as e:
                        print(f"  ⚠️ 无法获取 {cache_key} 的有效值: {e}")
                        valid_values_cache[cache_key] = set()
        else:
            valid_values_cache = {}

        # 清理数据
        cleaned_rows = []
        skipped_count = 0
        cleaned_fields = {}
        truncated_count = 0

        for row in rows:
            row_dict = dict(row._mapping)
            should_skip = False

            # 1. 检查外键约束（如果有外键）
            if foreign_keys:
                for fk in foreign_keys:
                    column = fk["column"]
                    ref_table = fk["ref_table"]
                    ref_column = fk["ref_column"]
                    cache_key = f"{ref_table}.{ref_column}"

                    fk_value = row_dict.get(column)
                    valid_values = valid_values_cache.get(cache_key, set())

                    # 检查外键值是否有效
                    if fk_value is not None and fk_value not in valid_values:
                        # 如果外键允许为 NULL，设置为 NULL
                        # 否则跳过这条记录
                        if self.is_nullable_column(table_name, column):
                            row_dict[column] = None
                            cleaned_fields[column] = cleaned_fields.get(column, 0) + 1
                        else:
                            # 不允许为 NULL，跳过整条记录
                            should_skip = True
                            skipped_count += 1
                            break

            # 2. 截断过长的字符串字段（所有表都需要）
            if not should_skip:
                truncated_fields = self.truncate_string_fields(table_name, row_dict)
                if truncated_fields:
                    truncated_count += 1

            if not should_skip:
                cleaned_rows.append(row_dict)

        # 输出清理统计
        if cleaned_fields:
            for field, count in cleaned_fields.items():
                print(f"  🧹 清理了 {count} 条无效的 {field} 引用（设置为 NULL）")

        if skipped_count > 0:
            print(f"  ⚠️ 跳过了 {skipped_count} 条无法修复的记录")

        if truncated_count > 0:
            print(f"  ✂️ 截断了 {truncated_count} 条记录的过长字段")

        return cleaned_rows

    def is_nullable_column(self, table_name: str, column_name: str) -> bool:
        """检查列是否允许为 NULL"""
        inspector = inspect(self.mysql_engine)
        columns = inspector.get_columns(table_name)

        for col in columns:
            if col["name"] == column_name:
                return col.get("nullable", True)

        return True  # 默认允许 NULL

    def get_column_max_length(self, table_name: str, column_name: str) -> int:
        """获取字符串列的最大长度"""
        try:
            inspector = inspect(self.mysql_engine)
            columns = inspector.get_columns(table_name)

            for col in columns:
                if col["name"] == column_name:
                    col_type = col.get("type")
                    if hasattr(col_type, "length") and col_type.length:
                        return col_type.length

            return None
        except Exception:
            return None

    def truncate_string_fields(self, table_name: str, row_dict: dict) -> List[str]:
        """截断过长的字符串字段"""
        try:
            inspector = inspect(self.mysql_engine)
            columns = inspector.get_columns(table_name)
        except Exception as e:
            print(f"  ⚠️ 无法获取表 {table_name} 的列信息: {e}")
            return []

        truncated_fields = []

        for col in columns:
            col_name = col["name"]
            col_type = col.get("type")

            # 检查是否是字符串类型且有长度限制
            if hasattr(col_type, "length") and col_type.length and col_name in row_dict:
                value = row_dict[col_name]
                if isinstance(value, str):
                    # 检查字符长度
                    char_len = len(value)
                    # 检查字节长度（utf8mb4 下每个字符最多 4 字节）
                    byte_len = len(value.encode('utf-8'))
                    max_bytes = col_type.length * 4  # utf8mb4 最多 4 字节/字符

                    # 如果字符数超过限制，或字节数超过限制，进行截断
                    if char_len > col_type.length or byte_len > max_bytes:
                        # 按字符截断
                        truncated_value = value[:col_type.length]
                        # 确保字节长度也不超标
                        while len(truncated_value.encode('utf-8')) > max_bytes:
                            truncated_value = truncated_value[:-1]

                        row_dict[col_name] = truncated_value
                        truncated_fields.append(f"{col_name}('{value}' {char_len}字符/{byte_len}字节 -> '{truncated_value}' {len(truncated_value)}字符)")

        return truncated_fields

    def migrate_table(self, table_name: str) -> Dict[str, int]:
        """迁移单个表"""
        print(f"\n📦 正在迁移表: {table_name}")

        # 反射表结构
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=self.sqlite_engine)

        # 从 SQLite 读取数据
        with self.sqlite_engine.connect() as sqlite_conn:
            result = sqlite_conn.execute(select(table))
            rows = result.fetchall()
            total_rows = len(rows)

            if total_rows == 0:
                print(f"  ⚠️ 表 {table_name} 为空，跳过")
                return {"total": 0, "success": 0, "failed": 0}

            print(f"  📊 共 {total_rows} 条数据")

        # 清理数据
        data_dicts = self.clean_data(table_name, rows)

        # 统计清理后的数据
        cleaned_rows = len(data_dicts)
        skipped_rows = total_rows - cleaned_rows

        if skipped_rows > 0:
            print(f"  ⚠️ 跳过了 {skipped_rows} 条无效记录，剩余 {cleaned_rows} 条有效数据")

        if cleaned_rows == 0:
            print(f"  ⚠️ 清理后无有效数据，跳过迁移")
            return {"total": total_rows, "success": 0, "failed": skipped_rows}

        # 批量写入 MySQL
        batch_size = 1000
        success_count = 0
        failed_count = 0

        with self.mysql_engine.connect() as mysql_conn:
            for i in range(0, len(data_dicts), batch_size):
                batch = data_dicts[i:i + batch_size]

                try:
                    # 批量插入
                    mysql_conn.execute(table.insert(), batch)
                    mysql_conn.commit()

                    success_count += len(batch)
                    print(f"  ✅ 已迁移 {success_count}/{cleaned_rows} 条")

                except Exception as e:
                    # 批量插入失败，尝试逐条插入以找出问题记录
                    print(f"  ⚠️ 批次插入失败，尝试逐条插入: {e}")
                    mysql_conn.rollback()

                    for row in batch:
                        try:
                            mysql_conn.execute(table.insert(), [row])
                            mysql_conn.commit()
                            success_count += 1
                        except Exception as row_error:
                            failed_count += 1
                            # 只显示前几个错误，避免刷屏
                            if failed_count <= 5:
                                print(f"    ❌ 记录插入失败: {row_error}")
                                print(f"       数据: {row}")

                    if failed_count > 5:
                        print(f"    ... 还有 {failed_count - 5} 条记录失败（已省略）")

                    print(f"  📊 当前进度: 成功 {success_count}, 失败 {failed_count}")

        return {
            "total": total_rows,
            "success": success_count,
            "failed": failed_count + skipped_rows
        }
    
    def verify_table(self, table_name: str) -> bool:
        """验证表数据完整性"""
        print(f"\n🔍 验证表: {table_name}")
        
        # 反射表结构
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=self.sqlite_engine)
        
        # 统计 SQLite 行数
        with self.sqlite_engine.connect() as sqlite_conn:
            sqlite_count = sqlite_conn.execute(
                select(func.count()).select_from(table)
            ).scalar()

        # 统计 MySQL 行数
        with self.mysql_engine.connect() as mysql_conn:
            mysql_count = mysql_conn.execute(
                select(func.count()).select_from(table)
            ).scalar()
        
        if sqlite_count == mysql_count:
            print(f"  ✅ 数据一致: {sqlite_count} 条")
            return True
        else:
            print(f"  ❌ 数据不一致: SQLite={sqlite_count}, MySQL={mysql_count}")
            return False
    
    async def migrate_all(self):
        """迁移所有表"""
        print("\n" + "="*60)
        print("🚀 开始数据迁移")
        print("="*60)

        start_time = datetime.now()

        # 获取所有表
        tables = self.get_table_names()
        print(f"\n📋 共发现 {len(tables)} 个表")
        print(f"表列表: {', '.join(tables)}")

        # 确认迁移
        print("\n⚠️ 警告：此操作将覆盖 MySQL 中的现有数据！")
        confirm = input("是否继续？(yes/no): ")
        if confirm.lower() != "yes":
            print("❌ 迁移已取消")
            return

        # 创建 MySQL 表结构
        self.create_mysql_tables()

        # 清空 MySQL 数据
        self.clear_mysql_data()

        # 迁移每个表
        for table_name in tables:
            stats = self.migrate_table(table_name)
            self.migration_stats[table_name] = stats
        
        # 验证数据
        print("\n" + "="*60)
        print("🔍 验证数据完整性")
        print("="*60)
        
        all_verified = True
        for table_name in tables:
            if not self.verify_table(table_name):
                all_verified = False
        
        # 生成报告
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "="*60)
        print("📊 迁移报告")
        print("="*60)
        print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总耗时: {duration:.2f} 秒")
        print(f"\n表迁移统计:")
        
        total_success = 0
        total_failed = 0
        
        for table_name, stats in self.migration_stats.items():
            print(f"  {table_name}:")
            print(f"    总数: {stats['total']}")
            print(f"    成功: {stats['success']}")
            print(f"    失败: {stats['failed']}")
            total_success += stats['success']
            total_failed += stats['failed']
        
        print(f"\n总计:")
        print(f"  成功: {total_success} 条")
        print(f"  失败: {total_failed} 条")
        
        if all_verified and total_failed == 0:
            print("\n✅ 迁移成功！所有数据已验证通过")
        else:
            print("\n⚠️ 迁移完成，但存在问题，请检查日志")
        
        print("\n" + "="*60)
    
    def close(self):
        """关闭连接"""
        if self.sqlite_engine:
            self.sqlite_engine.dispose()
        if self.mysql_engine:
            self.mysql_engine.dispose()
        print("\n🔒 数据库连接已关闭")


async def main():
    """主函数"""
    migrator = DatabaseMigrator()
    
    try:
        await migrator.connect()
        await migrator.migrate_all()
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        migrator.close()


if __name__ == "__main__":
    asyncio.run(main())

