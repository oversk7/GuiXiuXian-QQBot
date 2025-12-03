#!/usr/bin/env python3
"""
检查 ENUM 问题的诊断脚本
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from plugins.xiuxian_game.models.db import engine


async def diagnose():
    """诊断 ENUM 问题"""
    print("=" * 60)
    print("诊断 daily_task.task_type ENUM 问题")
    print("=" * 60)

    async with engine.begin() as conn:
        # 1. 检查表是否存在
        print("\n1️⃣ 检查表是否存在...")
        result = await conn.execute(
            text("SHOW TABLES LIKE 'daily_task'")
        )
        if not result.fetchone():
            print("❌ 表 daily_task 不存在！")
            return
        print("   ✅ 表存在")

        # 2. 获取 ENUM 定义
        print("\n2️⃣ 获取 ENUM 定义...")
        try:
            result = await conn.execute(
                text("SHOW COLUMNS FROM daily_task LIKE 'task_type'")
            )
            row = result.fetchone()

            if not row:
                print("❌ 列 task_type 不存在！")
                return

            column_type = row[1]
            print(f"   当前类型: {column_type}")

            # 解析 ENUM 值
            import re
            enum_values = re.findall(r"'([^']*)'", column_type)
            print(f"   ENUM 值: {enum_values}")
            print(f"   ENUM 值数量: {len(enum_values)}")

            # 检查是否包含 torture_cult_raid
            if 'torture_cult_raid' in enum_values:
                print("   ✅ ENUM 中包含 torture_cult_raid")
            else:
                print("   ❌ ENUM 中缺少 torture_cult_raid")

        except Exception as e:
            print(f"❌ 获取 ENUM 定义失败: {e}")
            return

        # 3. 检查数据中的值（尝试读取）
        print("\n3️⃣ 检查数据中实际存在的值...")
        try:
            # 尝试用 HEX 读取，避免 ENUM 转换问题
            result = await conn.execute(
                text("SELECT HEX(task_type) as hex_value, COUNT(*) as count "
                     "FROM daily_task "
                     "GROUP BY hex_value")
            )
            rows = result.fetchall()

            if rows:
                print("   数据中的值（十六进制）:")
                for hex_value, count in rows:
                    # 尝试解码
                    try:
                        decoded = bytes.fromhex(hex_value).decode('utf-8')
                        status = "✅" if decoded in enum_values else "❌ 不在ENUM中"
                        print(f"     - {decoded} (0x{hex_value}): {count} 条记录 {status}")
                    except:
                        print(f"     - 0x{hex_value}: {count} 条记录 (无法解码)")
            else:
                print("   ⚠️ 表中没有数据")

        except Exception as e:
            print(f"❌ 查询数据失败: {e}")
            print(f"   错误类型: {type(e).__name__}")
            print(f"   这说明 ENUM 定义与数据不匹配")

        # 4. 尝试直接读取原始字节
        print("\n4️⃣ 尝试读取表结构信息...")
        try:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM daily_task")
            )
            total_count = result.scalar()
            print(f"   表中总记录数: {total_count}")
        except Exception as e:
            print(f"❌ 查询记录数失败: {e}")

        # 5. 检查是否有临时列残留
        print("\n5️⃣ 检查是否有临时列...")
        result = await conn.execute(
            text("SHOW COLUMNS FROM daily_task LIKE '%temp%'")
        )
        temp_cols = result.fetchall()
        if temp_cols:
            print(f"   ⚠️ 发现临时列: {[col[0] for col in temp_cols]}")
            print("   建议手动删除这些临时列")
        else:
            print("   ✅ 没有临时列")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


async def main():
    try:
        await diagnose()
    except Exception as e:
        print(f"\n❌ 诊断过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
