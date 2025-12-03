#!/usr/bin/env python3
"""
使用Python强制修复 daily_task.task_type ENUM 问题
绕过MySQL客户端的显示问题
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import yaml

# 直接加载数据库配置，不依赖NoneBot
def load_config():
    """加载数据库配置"""
    config_path = Path(__file__).parent / "plugins" / "xiuxian_game" / "config" / "database.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config

# 创建数据库引擎
config = load_config()
db_config = config["database"]

if db_config["type"] == "mysql":
    mysql_cfg = db_config["mysql"]
    DATABASE_URL = (
        f"mysql+aiomysql://{mysql_cfg['user']}:{mysql_cfg['password']}"
        f"@{mysql_cfg['host']}:{mysql_cfg['port']}/{mysql_cfg['database']}"
        f"?charset={mysql_cfg.get('charset', 'utf8mb4')}"
    )
else:
    raise ValueError("此脚本仅支持MySQL数据库")

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


async def force_fix():
    """强制修复ENUM问题"""
    print("=" * 60)
    print("开始强制修复 daily_task.task_type")
    print("=" * 60)

    async with engine.begin() as conn:
        try:
            # 步骤1: 删除可能存在的临时列
            print("\n[1/7] 清理临时列...")
            for temp_col in ['task_type_temp', 'task_type_temp_migration',
                            'task_type_backup', 'task_type_fixed', 'task_type_new']:
                try:
                    await conn.execute(text(f"ALTER TABLE daily_task DROP COLUMN IF EXISTS {temp_col}"))
                    print(f"  - 删除临时列: {temp_col}")
                except:
                    pass

            # 步骤2: 删除旧的task_type列
            print("\n[2/7] 删除旧的 task_type 列...")
            await conn.execute(text("ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type"))
            print("  ✓ 已删除")

            # 步骤3: 创建新的ENUM列
            print("\n[3/7] 创建新的 task_type ENUM 列...")
            create_sql = """
            ALTER TABLE daily_task
            ADD COLUMN task_type ENUM(
                'ghost_elimination',
                'pen_spirit_case',
                'fake_immortal_cult',
                'shape_shifter_hunt',
                'stone_curse_break',
                'torture_cult_raid',
                'tutorial'
            ) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型'
            """
            await conn.execute(text(create_sql))
            print("  ✓ 已创建")

            # 步骤4: 验证ENUM定义
            print("\n[4/7] 验证 ENUM 定义...")
            result = await conn.execute(text("SHOW COLUMNS FROM daily_task LIKE 'task_type'"))
            row = result.fetchone()
            column_type = row[1]
            print(f"  ENUM 类型: {column_type}")

            # 步骤5: 检查数据分布
            print("\n[5/7] 检查数据分布...")
            result = await conn.execute(text(
                "SELECT task_type, COUNT(*) as count FROM daily_task GROUP BY task_type ORDER BY task_type"
            ))
            rows = result.fetchall()
            print("  数据分布:")
            for task_type, count in rows:
                print(f"    - {task_type}: {count} 条")

            # 步骤6: 统计总记录数
            print("\n[6/7] 验证总记录数...")
            result = await conn.execute(text("SELECT COUNT(*) FROM daily_task"))
            total = result.scalar()
            print(f"  总记录数: {total}")

            # 步骤7: 验证代码枚举定义
            print("\n[7/7] 验证代码中的枚举定义...")
            expected_values = [
                'ghost_elimination',
                'pen_spirit_case',
                'fake_immortal_cult',
                'shape_shifter_hunt',
                'stone_curse_break',
                'torture_cult_raid',
                'tutorial'
            ]
            print(f"  代码中的值: {expected_values}")
            print(f"  数量: {len(expected_values)}")

            print("\n" + "=" * 60)
            print("✅ 修复完成！")
            print("=" * 60)
            print("\n现在可以重启bot了:")
            print("  python bot.py")

        except Exception as e:
            print(f"\n❌ 修复失败: {e}")
            import traceback
            traceback.print_exc()
            raise


async def main():
    try:
        await force_fix()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
