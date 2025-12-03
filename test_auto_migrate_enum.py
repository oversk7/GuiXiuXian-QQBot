#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 auto_migrate.py 的 ENUM 自动修复功能
"""

import asyncio
import sys
import io

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


async def test_auto_migrate():
    """测试自动迁移功能"""
    from plugins.xiuxian_game.models.db import engine
    from plugins.xiuxian_game.models.auto_migrate import auto_migrate

    print("=" * 60)
    print("测试 auto_migrate ENUM 自动修复功能")
    print("=" * 60)
    print()

    # 执行自动迁移
    await auto_migrate(engine, verbose=True)

    print()
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)


async def check_enum_status():
    """检查 ENUM 列的当前状态"""
    from plugins.xiuxian_game.models.db import AsyncSessionLocal
    from sqlalchemy import text

    print("\n检查 daily_task.task_type ENUM 列状态:")
    print("-" * 60)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SHOW COLUMNS FROM daily_task LIKE 'task_type'")
        )
        row = result.fetchone()

        if row:
            print(f"列名: {row[0]}")
            print(f"类型: {row[1]}")
            print(f"可空: {row[2]}")
            print(f"默认值: {row[4]}")
            print(f"注释: {row[5] if len(row) > 5 else ''}")

            # 提取 ENUM 值
            import re
            enum_values = re.findall(r"'([^']*)'", row[1])
            print(f"\nENUM 值列表 ({len(enum_values)} 个):")
            for i, val in enumerate(enum_values, 1):
                print(f"  {i}. {val}")
        else:
            print("❌ 列不存在！")


if __name__ == "__main__":
    print()
    asyncio.run(check_enum_status())
    print()
    asyncio.run(test_auto_migrate())
    print()
    asyncio.run(check_enum_status())
