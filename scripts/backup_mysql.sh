#!/bin/bash
# MySQL 高级自动备份脚本（分级保留策略）
#
# 功能：
# 1. 自动分级保留备份（日备份/周备份/月备份）
# 2. 智能清理过期备份
# 3. 备份完整性验证
# 4. 磁盘空间检查
# 5. 详细日志记录
#
# 使用方法：
#   chmod +x scripts/backup_mysql_advanced.sh
#   ./scripts/backup_mysql_advanced.sh
#
# 推荐定时任务：
#   crontab -e
#   0 3 * * * /path/to/GuiXiuXian2/scripts/backup_mysql_advanced.sh

# ==================== 配置区 ====================

# 数据库配置
DB_USER="guixiuxian"
DB_PASSWORD="your_strong_password_here"  # ⚠️ 请修改为实际密码
DB_NAME="guixiuxian_db"
DB_HOST="localhost"

# 备份目录
BACKUP_ROOT="/var/backups/mysql"  # ⚠️ 请修改为实际路径
DAILY_DIR="$BACKUP_ROOT/daily"
WEEKLY_DIR="$BACKUP_ROOT/weekly"
MONTHLY_DIR="$BACKUP_ROOT/monthly"
LOG_FILE="$BACKUP_ROOT/backup.log"

# 分级保留策略
DAILY_RETENTION=14    # 每日备份保留14天
WEEKLY_RETENTION=56   # 每周备份保留8周（56天）
MONTHLY_RETENTION=365 # 每月备份保留12个月（365天）

# 磁盘空间检查（最小可用空间，单位GB）
MIN_FREE_SPACE_GB=10

# 通知邮箱（可选，留空则不发送邮件）
NOTIFY_EMAIL=""

# ==================== 函数定义 ====================

# 记录日志
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 错误日志
error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ ERROR: $1" | tee -a "$LOG_FILE"
}

# 成功日志
success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ SUCCESS: $1" | tee -a "$LOG_FILE"
}

# 检查磁盘空间
check_disk_space() {
    local available_gb=$(df -BG "$BACKUP_ROOT" | awk 'NR==2 {print $4}' | sed 's/G//')
    log "可用磁盘空间: ${available_gb}GB"

    if [ "$available_gb" -lt "$MIN_FREE_SPACE_GB" ]; then
        error "磁盘空间不足! 可用: ${available_gb}GB, 最小要求: ${MIN_FREE_SPACE_GB}GB"
        send_notification "备份失败 - 磁盘空间不足"
        exit 1
    fi
}

# 创建备份目录
create_backup_dirs() {
    mkdir -p "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"
    if [ $? -ne 0 ]; then
        error "无法创建备份目录"
        exit 1
    fi
}

# 执行数据库备份
perform_backup() {
    local backup_file="$1"
    local temp_file="${backup_file}.tmp"

    log "开始备份数据库到: $backup_file"

    # 执行mysqldump
    mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" \
        --single-transaction \
        --quick \
        --lock-tables=false \
        --routines \
        --triggers \
        --events \
        "$DB_NAME" > "$temp_file" 2>> "$LOG_FILE"

    if [ $? -ne 0 ]; then
        error "数据库备份失败"
        rm -f "$temp_file"
        return 1
    fi

    # 验证备份文件
    if [ ! -s "$temp_file" ]; then
        error "备份文件为空"
        rm -f "$temp_file"
        return 1
    fi

    # 压缩备份文件
    gzip -c "$temp_file" > "${backup_file}.gz"
    if [ $? -ne 0 ]; then
        error "压缩备份文件失败"
        rm -f "$temp_file"
        return 1
    fi

    # 删除临时文件
    rm -f "$temp_file"

    # 获取文件大小
    local file_size=$(du -h "${backup_file}.gz" | cut -f1)
    success "备份完成: ${backup_file}.gz (大小: $file_size)"

    return 0
}

# 验证备份完整性
verify_backup() {
    local backup_file="$1"

    log "验证备份文件: $backup_file"

    # 测试gzip文件完整性
    gzip -t "$backup_file" 2>> "$LOG_FILE"
    if [ $? -ne 0 ]; then
        error "备份文件损坏: $backup_file"
        return 1
    fi

    success "备份文件验证通过"
    return 0
}

# 清理过期备份
cleanup_old_backups() {
    local backup_dir="$1"
    local retention_days="$2"
    local backup_type="$3"

    log "清理${backup_type}过期备份（保留${retention_days}天）"

    local count=$(find "$backup_dir" -name "backup_*.sql.gz" -mtime +$retention_days | wc -l)

    if [ "$count" -gt 0 ]; then
        find "$backup_dir" -name "backup_*.sql.gz" -mtime +$retention_days -delete
        success "已清理${count}个${backup_type}过期备份"
    else
        log "没有${backup_type}过期备份需要清理"
    fi
}

# 发送通知
send_notification() {
    local message="$1"

    if [ -n "$NOTIFY_EMAIL" ]; then
        echo "$message" | mail -s "[诡修仙] 数据库备份通知" "$NOTIFY_EMAIL"
    fi
}

# 生成备份摘要
generate_summary() {
    log "=========================================="
    log "备份摘要统计"
    log "=========================================="

    local daily_count=$(find "$DAILY_DIR" -name "backup_*.sql.gz" | wc -l)
    local daily_size=$(du -sh "$DAILY_DIR" 2>/dev/null | cut -f1)
    log "每日备份: $daily_count 个文件, 总大小: $daily_size"

    local weekly_count=$(find "$WEEKLY_DIR" -name "backup_*.sql.gz" | wc -l)
    local weekly_size=$(du -sh "$WEEKLY_DIR" 2>/dev/null | cut -f1)
    log "每周备份: $weekly_count 个文件, 总大小: $weekly_size"

    local monthly_count=$(find "$MONTHLY_DIR" -name "backup_*.sql.gz" | wc -l)
    local monthly_size=$(du -sh "$MONTHLY_DIR" 2>/dev/null | cut -f1)
    log "每月备份: $monthly_count 个文件, 总大小: $monthly_size"

    local total_size=$(du -sh "$BACKUP_ROOT" 2>/dev/null | cut -f1)
    log "总计: $((daily_count + weekly_count + monthly_count)) 个备份, 总大小: $total_size"
    log "=========================================="
}

# ==================== 主程序 ====================

log "=========================================="
log "开始执行MySQL高级备份脚本"
log "=========================================="

# 1. 创建备份目录
create_backup_dirs

# 2. 检查磁盘空间
check_disk_space

# 3. 生成文件名
DATE=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)  # 1=周一, 7=周日
DAY_OF_MONTH=$(date +%d)

# 4. 执行每日备份
DAILY_BACKUP="$DAILY_DIR/backup_$DATE.sql"
if ! perform_backup "$DAILY_BACKUP"; then
    error "每日备份失败"
    send_notification "每日备份失败"
    exit 1
fi

# 5. 验证备份
if ! verify_backup "${DAILY_BACKUP}.gz"; then
    error "备份验证失败"
    send_notification "备份验证失败"
    exit 1
fi

# 6. 如果是周日，创建周备份
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    WEEKLY_BACKUP="$WEEKLY_DIR/backup_$DATE.sql"
    log "今天是周日，创建周备份"
    cp "${DAILY_BACKUP}.gz" "${WEEKLY_BACKUP}.gz"
    success "周备份已创建"
fi

# 7. 如果是每月1号，创建月备份
if [ "$DAY_OF_MONTH" -eq "01" ]; then
    MONTHLY_BACKUP="$MONTHLY_DIR/backup_$DATE.sql"
    log "今天是每月1号，创建月备份"
    cp "${DAILY_BACKUP}.gz" "${MONTHLY_BACKUP}.gz"
    success "月备份已创建"
fi

# 8. 清理过期备份
cleanup_old_backups "$DAILY_DIR" "$DAILY_RETENTION" "每日"
cleanup_old_backups "$WEEKLY_DIR" "$WEEKLY_RETENTION" "每周"
cleanup_old_backups "$MONTHLY_DIR" "$MONTHLY_RETENTION" "每月"

# 9. 生成备份摘要
generate_summary

log "=========================================="
log "备份任务完成"
log "=========================================="

exit 0
