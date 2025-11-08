#!/bin/bash
# MySQL 自动备份脚本
# 
# 功能：
# 1. 备份 MySQL 数据库
# 2. 自动清理过期备份（保留7天）
# 3. 记录备份日志
#
# 使用方法：
#   chmod +x scripts/backup_mysql.sh
#   ./scripts/backup_mysql.sh
#
# 定时任务（每天凌晨3点）：
#   crontab -e
#   0 3 * * * /path/to/GuiXiuXian2/scripts/backup_mysql.sh

# ==================== 配置区 ====================

# 数据库配置
DB_USER="guixiuxian"
DB_PASSWORD="your_strong_password_here"  # ⚠️ 请修改为实际密码
DB_NAME="guixiuxian_db"
DB_HOST="localhost"

# 备份目录
BACKUP_DIR="/path/to/backups"  # ⚠️ 请修改为实际路径
LOG_FILE="$BACKUP_DIR/backup.log"

# 保留天数
RETENTION_DAYS=7

# ==================== 脚本开始 ====================

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 生成备份文件名
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql"

# 记录开始时间
echo "========================================" >> "$LOG_FILE"
echo "备份开始: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"

# 执行备份
echo "正在备份数据库..."
mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > "$BACKUP_FILE" 2>> "$LOG_FILE"

# 检查备份是否成功
if [ $? -eq 0 ]; then
    # 压缩备份文件
    gzip "$BACKUP_FILE"
    BACKUP_FILE="$BACKUP_FILE.gz"
    
    # 获取文件大小
    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    
    echo "✅ 备份成功: $BACKUP_FILE (大小: $FILE_SIZE)" >> "$LOG_FILE"
    echo "✅ 备份成功: $BACKUP_FILE (大小: $FILE_SIZE)"
else
    echo "❌ 备份失败，请检查日志: $LOG_FILE" >> "$LOG_FILE"
    echo "❌ 备份失败，请检查日志: $LOG_FILE"
    exit 1
fi

# 清理过期备份
echo "正在清理过期备份（保留 $RETENTION_DAYS 天）..."
find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "✅ 过期备份已清理" >> "$LOG_FILE"

# 记录结束时间
echo "备份结束: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

echo "✅ 备份完成"

