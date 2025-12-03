#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
执行 daily_task.task_type ENUM 列修复

自动读取数据库配置并执行 SQL 修复脚本
"""

import asyncio
import aiomysql
import yaml
from pathlib import Path
import sys
import io

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


async def fix_task_type_enum():
    """执行 ENUM 修复"""

    # 1. 读取数据库配置
    config_path = Path(__file__).parent / "plugins" / "xiuxian_game" / "config" / "database.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    mysql_config = config["database"]["mysql"]

    print("📊 数据库配置:")
    print(f"   Host: {mysql_config['host']}")
    print(f"   Port: {mysql_config['port']}")
    print(f"   User: {mysql_config['user']}")
    print(f"   Database: {mysql_config['database']}")
    print()

    # 2. 读取 SQL 脚本
    sql_file = Path(__file__).parent / "fix_daily_task_enum_v2.sql"

    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # 3. 分割 SQL 语句（按分号分割，过滤注释和空行）
    sql_statements = []
    for line in sql_content.split('\n'):
        line = line.strip()
        if line and not line.startswith('--'):
            sql_statements.append(line)

    sql_text = ' '.join(sql_statements)
    statements = [s.strip() for s in sql_text.split(';') if s.strip()]

    print(f"📝 准备执行 {len(statements)} 条 SQL 语句\n")

    # 4. 连接数据库并执行
    connection = None
    try:
        connection = await aiomysql.connect(
            host=mysql_config["host"],
            port=mysql_config["port"],
            user=mysql_config["user"],
            password=str(mysql_config["password"]),  # 转换为字符串
            db=mysql_config["database"],
            charset=mysql_config.get("charset", "utf8mb4"),
            autocommit=False
        )

        async with connection.cursor() as cursor:
            print("🔧 开始执行 SQL 修复...")
            print()

            for i, statement in enumerate(statements, 1):
                # 显示简化的SQL（只显示前80个字符）
                display_sql = statement[:80] + "..." if len(statement) > 80 else statement
                print(f"[{i}/{len(statements)}] {display_sql}")

                try:
                    await cursor.execute(statement)

                    # 如果是 SELECT 语句，显示结果
                    if statement.strip().upper().startswith('SELECT') or \
                       statement.strip().upper().startswith('SHOW'):
                        results = await cursor.fetchall()
                        if results:
                            print(f"         结果: {results}")

                    print(f"         ✅ 成功")

                except Exception as e:
                    print(f"         ❌ 失败: {e}")
                    raise

                print()

            # 5. 提交事务
            await connection.commit()
            print("✅ 所有 SQL 语句执行成功！")
            print("✅ 事务已提交")

    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        if connection:
            await connection.rollback()
            print("⚠️ 已回滚所有更改")
        raise

    finally:
        if connection:
            connection.close()
            print("\n🔒 数据库连接已关闭")


async def verify_fix():
    """验证修复结果"""
    config_path = Path(__file__).parent / "plugins" / "xiuxian_game" / "config" / "database.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    mysql_config = config["database"]["mysql"]

    connection = await aiomysql.connect(
        host=mysql_config["host"],
        port=mysql_config["port"],
        user=mysql_config["user"],
        password=str(mysql_config["password"]),  # 转换为字符串
        db=mysql_config["database"],
        charset=mysql_config.get("charset", "utf8mb4")
    )

    try:
        async with connection.cursor() as cursor:
            print("\n" + "="*60)
            print("🔍 验证修复结果")
            print("="*60 + "\n")

            # 检查表结构
            await cursor.execute("SHOW CREATE TABLE daily_task")
            result = await cursor.fetchone()

            # 提取 task_type 的定义
            create_table_sql = result[1]
            for line in create_table_sql.split('\n'):
                if 'task_type' in line.lower():
                    print("📋 task_type 列定义:")
                    print(f"   {line.strip()}")

            print()

            # 检查现有数据
            await cursor.execute("SELECT DISTINCT task_type FROM daily_task")
            task_types = await cursor.fetchall()

            if task_types:
                print("📊 数据库中现有的任务类型:")
                for (task_type,) in task_types:
                    print(f"   ✓ {task_type}")
            else:
                print("ℹ️ daily_task 表中暂无数据")

            print()

            # 检查是否包含所有必需的类型
            expected_types = {
                'ghost_elimination',
                'pen_spirit_case',
                'fake_immortal_cult',
                'shape_shifter_hunt',
                'stone_curse_break',
                'torture_cult_raid',
                'tutorial'
            }

            print("✅ 验证必需的枚举值:")
            for task_type in expected_types:
                print(f"   ✓ {task_type}")

            print("\n🎉 修复完成！Bot 应该可以正常启动了")

    finally:
        connection.close()


if __name__ == "__main__":
    print("="*60)
    print("🔧 daily_task.task_type ENUM 修复工具")
    print("="*60)
    print()
    print("⚠️ 警告：此操作会修改数据库结构")
    print("⚠️ 建议先备份数据库！")
    print()

    user_input = input("确认执行修复？(yes/no): ").strip().lower()

    if user_input == "yes":
        print()
        asyncio.run(fix_task_type_enum())
        asyncio.run(verify_fix())
    else:
        print("\n❌ 操作已取消")
