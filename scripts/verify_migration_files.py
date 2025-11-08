#!/usr/bin/env python3
"""
验证 SQLite 转 MySQL 迁移所需的所有文件是否已创建
"""

import os
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# 需要检查的文件列表
REQUIRED_FILES = {
    "文档文件": [
        "START_HERE.md",
        "QUICK_MIGRATION_STEPS.md",
        "MIGRATION_CHECKLIST.md",
        "README_MYSQL_MIGRATION.md",
        "MYSQL_MIGRATION_GUIDE.md",
        "MIGRATION_SUMMARY.md",
        "MIGRATION_FILES_LIST.md",
        "FINAL_SUMMARY.md",
    ],
    "配置文件": [
        "plugins/xiuxian_game/config/database.yaml",
        "plugins/xiuxian_game/config/database.yaml.example",
        "requirements_mysql.txt",
    ],
    "代码文件": [
        "plugins/xiuxian_game/models/db_new.py",
    ],
    "脚本文件": [
        "scripts/migrate_sqlite_to_mysql.py",
        "scripts/one_click_migrate.sh",
        "scripts/switch_database.py",
        "scripts/backup_mysql.sh",
        "scripts/verify_migration_files.py",  # 本文件
    ],
}


def check_file_exists(file_path: str) -> tuple[bool, str]:
    """
    检查文件是否存在
    
    Args:
        file_path: 相对于项目根目录的文件路径
        
    Returns:
        (是否存在, 文件大小或错误信息)
    """
    full_path = ROOT_DIR / file_path
    
    if full_path.exists():
        size = full_path.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        return True, size_str
    else:
        return False, "文件不存在"


def main():
    """主函数"""
    print("=" * 70)
    print("SQLite 转 MySQL 迁移文件验证")
    print("=" * 70)
    print()
    
    total_files = 0
    missing_files = 0
    total_size = 0
    
    for category, files in REQUIRED_FILES.items():
        print(f"📁 {category}")
        print("-" * 70)
        
        for file_path in files:
            total_files += 1
            exists, info = check_file_exists(file_path)
            
            if exists:
                print(f"  ✅ {file_path:<50} {info:>15}")
                # 计算总大小
                full_path = ROOT_DIR / file_path
                total_size += full_path.stat().st_size
            else:
                print(f"  ❌ {file_path:<50} {info:>15}")
                missing_files += 1
        
        print()
    
    # 统计信息
    print("=" * 70)
    print("统计信息")
    print("=" * 70)
    print(f"总文件数：{total_files}")
    print(f"已创建：{total_files - missing_files}")
    print(f"缺失：{missing_files}")
    
    if total_size < 1024:
        size_str = f"{total_size} B"
    elif total_size < 1024 * 1024:
        size_str = f"{total_size / 1024:.1f} KB"
    else:
        size_str = f"{total_size / (1024 * 1024):.1f} MB"
    print(f"总大小：{size_str}")
    print()
    
    # 检查 .gitignore
    print("=" * 70)
    print("检查 .gitignore")
    print("=" * 70)
    
    gitignore_path = ROOT_DIR / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        
        required_entries = [
            "plugins/xiuxian_game/config/database.yaml",
            "plugins/xiuxian_game/models/db_old.py",
            "*.sql",
            "backups/",
        ]
        
        for entry in required_entries:
            if entry in content:
                print(f"  ✅ {entry}")
            else:
                print(f"  ⚠️  {entry} (未找到)")
    else:
        print("  ❌ .gitignore 文件不存在")
    
    print()
    
    # 最终结果
    print("=" * 70)
    if missing_files == 0:
        print("✅ 所有文件都已创建，可以开始迁移了！")
        print()
        print("下一步：")
        print("  1. 阅读 START_HERE.md 了解整体方案")
        print("  2. 阅读 QUICK_MIGRATION_STEPS.md 学习迁移步骤")
        print("  3. 准备 MIGRATION_CHECKLIST.md 检查清单")
        print("  4. 开始迁移！")
    else:
        print(f"⚠️  缺失 {missing_files} 个文件，请检查！")
    print("=" * 70)


if __name__ == "__main__":
    main()

