"""
数据库类型快速切换脚本

功能：
- 快速切换 SQLite 和 MySQL
- 用于紧急回滚或测试

使用方法：
    python scripts/switch_database.py sqlite
    python scripts/switch_database.py mysql
"""

import sys
from pathlib import Path
import yaml

project_root = Path(__file__).parent.parent
config_path = project_root / "plugins" / "xiuxian_game" / "config" / "database.yaml"


def switch_database(db_type: str):
    """切换数据库类型"""
    if db_type not in ["sqlite", "mysql"]:
        print(f"❌ 无效的数据库类型: {db_type}")
        print("✅ 支持的类型: sqlite, mysql")
        sys.exit(1)
    
    # 读取配置
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 修改配置
    old_type = config["database"]["type"]
    config["database"]["type"] = db_type
    
    # 写回配置
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    
    print(f"✅ 数据库类型已切换: {old_type} -> {db_type}")
    print(f"📝 配置文件: {config_path}")
    print("\n⚠️ 请重启机器人使配置生效")


def main():
    if len(sys.argv) != 2:
        print("使用方法: python scripts/switch_database.py <sqlite|mysql>")
        sys.exit(1)
    
    db_type = sys.argv[1].lower()
    switch_database(db_type)


if __name__ == "__main__":
    main()

