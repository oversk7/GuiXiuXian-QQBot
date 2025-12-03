#!/bin/bash
# ==========================================
# 完整修复脚本 - 一键解决ENUM问题
# ==========================================

echo "========================================"
echo "🔧 开始完整修复 daily_task.task_type"
echo "========================================"

# 步骤1: 执行SQL修复
echo ""
echo "[1/4] 执行SQL修复..."
read -p "请输入MySQL用户名: " mysql_user
read -p "请输入数据库名: " mysql_db
read -sp "请输入MySQL密码: " mysql_pass
echo ""

mysql -u"$mysql_user" -p"$mysql_pass" "$mysql_db" < ultimate_fix.sql

if [ $? -eq 0 ]; then
    echo "✓ SQL修复成功"
else
    echo "✗ SQL修复失败"
    exit 1
fi

# 步骤2: 重启MySQL
echo ""
echo "[2/4] 重启MySQL数据库..."
echo "请选择你的系统:"
echo "  1) Linux (systemctl)"
echo "  2) Linux (service)"
echo "  3) Docker"
echo "  4) 手动重启（跳过此步骤）"
read -p "请选择 [1-4]: " choice

case $choice in
    1)
        sudo systemctl restart mysql
        echo "✓ MySQL已重启 (systemctl)"
        ;;
    2)
        sudo service mysql restart
        echo "✓ MySQL已重启 (service)"
        ;;
    3)
        read -p "请输入MySQL容器名: " container_name
        docker restart "$container_name"
        echo "✓ MySQL已重启 (docker)"
        ;;
    4)
        echo "⚠️ 请手动重启MySQL后按回车继续..."
        read
        ;;
    *)
        echo "✗ 无效选择"
        exit 1
        ;;
esac

# 步骤3: 清理Python缓存
echo ""
echo "[3/4] 清理Python缓存..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
echo "✓ Python缓存已清理"

# 步骤4: 停止旧的bot进程
echo ""
echo "[4/4] 停止旧的bot进程..."
pkill -f bot.py 2>/dev/null
sleep 2
echo "✓ 旧进程已停止"

# 完成
echo ""
echo "========================================"
echo "✅ 修复完成！"
echo "========================================"
echo ""
echo "现在可以启动bot了:"
echo "  python bot.py"
echo ""
echo "如果还有问题，请查看 FINAL_FIX_STEPS.md"
