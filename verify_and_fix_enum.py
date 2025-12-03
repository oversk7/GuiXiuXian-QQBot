#!/usr/bin/env python3
"""
验证和修复 daily_task.task_type ENUM 问题的辅助脚本

功能：
1. 检查数据库中当前 ENUM 的定义
2. 检查数据库中实际存在的值
3. 提供修复建议
4. （可选）执行修复

使用方法：
    python verify_and_fix_enum.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from plugins.xiuxian_game.models.db import engine
from sqlalchemy import text


async def check_enum_status():
    """检查当前 ENUM 状态"""
    print("=" * 60)
    print("检查 daily_task.task_type ENUM 状态")
    print("=" * 60)

    async with engine.begin() as conn:
        # 1. 获取 ENUM 定义
        print("\n1️⃣ 获取 ENUM 定义...")
        result = await conn.execute(
            text("SHOW COLUMNS FROM daily_task LIKE 'task_type'")
        )
        row = result.fetchone()

        if not row:
            print("❌ 错误: 列 task_type 不存在！")
            return False

        column_type = row[1]
        print(f"   当前 ENUM 定义: {column_type}")

        # 解析 ENUM 值
        import re
        enum_values = re.findall(r"'([^']*)'", column_type)
        print(f"   包含的值: {enum_values}")

        # 2. 检查数据中实际存在的值
        print("\n2️⃣ 检查数据中实际存在的值...")
        try:
            result = await conn.execute(
                text("SELECT DISTINCT task_type, COUNT(*) as count "
                     "FROM daily_task "
                     "WHERE task_type IS NOT NULL "
                     "GROUP BY task_type "
                     "ORDER BY task_type")
            )
            actual_values = result.fetchall()

            if actual_values:
                print("   数据中的值:")
                for value, count in actual_values:
                    status = "✅" if value in enum_values else "❌ 不在ENUM中"
                    print(f"     - {value}: {count} 条记录 {status}")
            else:
                print("   ⚠️ 数据表为空")

        except Exception as e:
            print(f"   ❌ 查询数据失败: {e}")
            print("   这通常意味着 ENUM 定义有问题，导致无法读取数据")
            return False

        # 3. 与代码定义对比
        print("\n3️⃣ 与代码定义对比...")
        expected_values = [
            "ghost_elimination",
            "pen_spirit_case",
            "fake_immortal_cult",
            "shape_shifter_hunt",
            "stone_curse_break",
            "torture_cult_raid",
            "tutorial"
        ]

        enum_set = set(enum_values)
        expected_set = set(expected_values)

        missing_in_db = expected_set - enum_set
        extra_in_db = enum_set - expected_set

        if missing_in_db:
            print(f"   ❌ ENUM 中缺少的值: {missing_in_db}")

        if extra_in_db:
            print(f"   ⚠️ ENUM 中多余的值: {extra_in_db}")

        if not missing_in_db and not extra_in_db:
            print("   ✅ ENUM 定义与代码完全一致")
            return True

        # 4. 提供修复建议
        print("\n4️⃣ 修复建议:")
        if missing_in_db:
            print(f"   需要在 ENUM 中添加: {missing_in_db}")
            print(f"   请执行:")
            print(f"   1. 手动执行 SQL: fix_enum_immediate.sql")
            print(f"   2. 或重启 bot，让 auto_migrate 自动修复（已改进）")

        return False


async def main():
    """主函数"""
    try:
        is_ok = await check_enum_status()

        if is_ok:
            print("\n" + "=" * 60)
            print("✅ ENUM 状态正常，无需修复")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("⚠️ ENUM 状态异常，需要修复")
            print("=" * 60)
            print("\n修复方法:")
            print("1. 执行 SQL 脚本: fix_enum_immediate.sql")
            print("2. 或重启 bot（auto_migrate 已改进，会自动修复）")

    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
