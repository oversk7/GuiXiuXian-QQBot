#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试 ENUM 自动修复功能（不依赖 Nonebot）
"""

import asyncio
import sys
import io
import yaml
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def load_db_config():
    """加载数据库配置"""
    config_path = Path("plugins/xiuxian_game/config/database.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["database"]["mysql"]


async def check_enum_values(engine):
    """检查 ENUM 值"""
    print("\n" + "=" * 60)
    print("检查 daily_task.task_type 当前的 ENUM 值")
    print("=" * 60)

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SHOW COLUMNS FROM daily_task LIKE 'task_type'")
        )
        row = result.fetchone()

        if row:
            import re
            enum_values = re.findall(r"'([^']*)'", row[1])
            print(f"\n当前 ENUM 值 ({len(enum_values)} 个):")
            for i, val in enumerate(enum_values, 1):
                print(f"  {i}. {val}")

            # 检查缺失的值
            expected = {
                'ghost_elimination', 'pen_spirit_case', 'fake_immortal_cult',
                'shape_shifter_hunt', 'stone_curse_break', 'torture_cult_raid', 'tutorial'
            }
            actual = set(enum_values)
            missing = expected - actual
            extra = actual - expected

            if missing:
                print(f"\n⚠️ 缺失的值: {', '.join(missing)}")
            if extra:
                print(f"\n⚠️ 多余的值: {', '.join(extra)}")
            if not missing and not extra:
                print("\n✅ ENUM 值完全匹配！")

        else:
            print("❌ 列不存在！")


async def test_auto_migrate():
    """测试自动迁移"""
    # 加载数据库配置
    mysql_config = load_db_config()

    # 创建引擎
    database_url = (
        f"mysql+aiomysql://{mysql_config['user']}:{mysql_config['password']}"
        f"@{mysql_config['host']}:{mysql_config['port']}/{mysql_config['database']}"
        f"?charset={mysql_config.get('charset', 'utf8mb4')}"
    )

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True
    )

    try:
        # 1. 检查修复前状态
        await check_enum_values(engine)

        # 2. 执行自动迁移
        print("\n" + "=" * 60)
        print("执行 auto_migrate")
        print("=" * 60 + "\n")

        # 直接导入并执行
        sys.path.insert(0, str(Path.cwd()))
        from plugins.xiuxian_game.models.auto_migrate import auto_migrate

        await auto_migrate(engine, verbose=True)

        # 3. 检查修复后状态
        await check_enum_values(engine)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_auto_migrate())
