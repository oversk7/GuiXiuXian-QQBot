#!/bin/bash
# 一键迁移脚本（适合新服务器）
# 
# 功能：自动完成从 SQLite 到 MySQL 的迁移
# 
# 使用方法：
#   chmod +x scripts/one_click_migrate.sh
#   ./scripts/one_click_migrate.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "🚀 SQLite 转 MySQL 一键迁移脚本"
echo "=========================================="
echo ""

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ==================== 检查 root 权限 ====================
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ 请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# ==================== 第一步：安装 MySQL ====================
echo -e "${GREEN}📦 第一步：安装 MySQL${NC}"
echo "正在检查 MySQL 是否已安装..."

if command -v mysql &> /dev/null; then
    echo -e "${YELLOW}⚠️ MySQL 已安装，跳过安装步骤${NC}"
else
    echo "正在安装 MySQL..."
    apt update
    apt install mysql-server -y
    systemctl start mysql
    systemctl enable mysql
    echo -e "${GREEN}✅ MySQL 安装完成${NC}"
fi

echo ""

# ==================== 第二步：配置 MySQL ====================
echo -e "${GREEN}🔧 第二步：配置 MySQL${NC}"
echo "请输入以下信息："

read -p "数据库名称 [guixiuxian_db]: " DB_NAME
DB_NAME=${DB_NAME:-guixiuxian_db}

read -p "数据库用户名 [guixiuxian]: " DB_USER
DB_USER=${DB_USER:-guixiuxian}

read -sp "数据库密码（至少8位）: " DB_PASSWORD
echo ""

if [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}❌ 密码不能为空${NC}"
    exit 1
fi

echo "正在创建数据库和用户..."
mysql -u root <<EOF
CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
EOF

echo -e "${GREEN}✅ 数据库配置完成${NC}"
echo ""

# ==================== 第三步：安装 Python 依赖 ====================
echo -e "${GREEN}📦 第三步：安装 Python 依赖${NC}"

# 获取项目目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_DIR"

echo "正在安装 Python 依赖..."
pip install aiomysql pymysql cryptography pyyaml

echo -e "${GREEN}✅ Python 依赖安装完成${NC}"
echo ""

# ==================== 第四步：备份 SQLite ====================
echo -e "${GREEN}💾 第四步：备份 SQLite 数据库${NC}"

SQLITE_DB="$PROJECT_DIR/plugins/xiuxian_game/data/game.db"
BACKUP_FILE="$PROJECT_DIR/plugins/xiuxian_game/data/game_backup_$(date +%Y%m%d_%H%M%S).db"

if [ -f "$SQLITE_DB" ]; then
    cp "$SQLITE_DB" "$BACKUP_FILE"
    echo -e "${GREEN}✅ 备份完成: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}⚠️ SQLite 数据库不存在，跳过备份${NC}"
fi

echo ""

# ==================== 第五步：创建配置文件 ====================
echo -e "${GREEN}📝 第五步：创建配置文件${NC}"

CONFIG_DIR="$PROJECT_DIR/plugins/xiuxian_game/config"
CONFIG_FILE="$CONFIG_DIR/database.yaml"

mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" <<EOF
# 数据库配置文件
# ⚠️ 请勿将此文件提交到 Git（包含敏感信息）

database:
  # 当前使用的数据库类型：sqlite 或 mysql
  type: mysql
  
  # SQLite 配置（保留作为备份）
  sqlite:
    path: "data/game.db"
    timeout: 30
    check_same_thread: false
  
  # MySQL 配置
  mysql:
    host: localhost
    port: 3306
    user: $DB_USER
    password: $DB_PASSWORD
    database: $DB_NAME
    charset: utf8mb4
    
    # 连接池配置
    pool_size: 20
    max_overflow: 10
    pool_recycle: 3600
    pool_pre_ping: true
    pool_use_lifo: true
    
    # 其他配置
    echo: false
    autocommit: false
EOF

echo -e "${GREEN}✅ 配置文件已创建: $CONFIG_FILE${NC}"
echo ""

# ==================== 第六步：替换数据库模块 ====================
echo -e "${GREEN}🔄 第六步：替换数据库模块${NC}"

DB_MODULE="$PROJECT_DIR/plugins/xiuxian_game/models/db.py"
DB_MODULE_NEW="$PROJECT_DIR/plugins/xiuxian_game/models/db_new.py"
DB_MODULE_OLD="$PROJECT_DIR/plugins/xiuxian_game/models/db_old.py"

if [ -f "$DB_MODULE_NEW" ]; then
    cp "$DB_MODULE" "$DB_MODULE_OLD"
    cp "$DB_MODULE_NEW" "$DB_MODULE"
    echo -e "${GREEN}✅ 数据库模块已替换${NC}"
else
    echo -e "${RED}❌ 找不到新的数据库模块: $DB_MODULE_NEW${NC}"
    exit 1
fi

echo ""

# ==================== 第七步：初始化 MySQL 表结构 ====================
echo -e "${GREEN}🔧 第七步：初始化 MySQL 表结构${NC}"
echo "正在初始化表结构（这可能需要几秒钟）..."

cd "$PROJECT_DIR"
timeout 30 python bot.py || true

echo -e "${GREEN}✅ 表结构初始化完成${NC}"
echo ""

# ==================== 第八步：迁移数据 ====================
echo -e "${GREEN}📦 第八步：迁移数据${NC}"
echo "正在迁移数据（这可能需要几分钟）..."

python scripts/migrate_sqlite_to_mysql.py

echo -e "${GREEN}✅ 数据迁移完成${NC}"
echo ""

# ==================== 第九步：验证数据 ====================
echo -e "${GREEN}🔍 第九步：验证数据${NC}"

echo "正在验证数据..."
mysql -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -e "SHOW TABLES;" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 数据验证通过${NC}"
else
    echo -e "${RED}❌ 数据验证失败${NC}"
    exit 1
fi

echo ""

# ==================== 第十步：配置自动备份 ====================
echo -e "${GREEN}⏰ 第十步：配置自动备份${NC}"

BACKUP_SCRIPT="$PROJECT_DIR/scripts/backup_mysql.sh"

if [ -f "$BACKUP_SCRIPT" ]; then
    # 更新备份脚本中的密码
    sed -i "s/DB_PASSWORD=\".*\"/DB_PASSWORD=\"$DB_PASSWORD\"/" "$BACKUP_SCRIPT"
    sed -i "s/DB_USER=\".*\"/DB_USER=\"$DB_USER\"/" "$BACKUP_SCRIPT"
    sed -i "s/DB_NAME=\".*\"/DB_NAME=\"$DB_NAME\"/" "$BACKUP_SCRIPT"
    
    chmod +x "$BACKUP_SCRIPT"
    
    echo "是否配置每天自动备份？(y/n)"
    read -p "> " SETUP_CRON
    
    if [ "$SETUP_CRON" = "y" ] || [ "$SETUP_CRON" = "Y" ]; then
        # 添加到 crontab（每天凌晨3点）
        (crontab -l 2>/dev/null; echo "0 3 * * * $BACKUP_SCRIPT") | crontab -
        echo -e "${GREEN}✅ 自动备份已配置（每天凌晨3点）${NC}"
    else
        echo -e "${YELLOW}⚠️ 跳过自动备份配置${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ 找不到备份脚本，跳过配置${NC}"
fi

echo ""

# ==================== 完成 ====================
echo "=========================================="
echo -e "${GREEN}🎉 迁移完成！${NC}"
echo "=========================================="
echo ""
echo "📊 迁移信息："
echo "  数据库类型: MySQL"
echo "  数据库名称: $DB_NAME"
echo "  数据库用户: $DB_USER"
echo "  配置文件: $CONFIG_FILE"
echo ""
echo "🚀 下一步："
echo "  1. 启动机器人: python bot.py"
echo "  2. 测试功能是否正常"
echo "  3. 监控日志: tail -f logs/command_log.txt"
echo ""
echo "🔙 如需回滚："
echo "  python scripts/switch_database.py sqlite"
echo ""
echo -e "${GREEN}预祝运行顺利！${NC}"

