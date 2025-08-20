#!/bin/bash

# 诡修仙游戏部署脚本
# 用于在服务器上部署游戏指南页面

echo "🚀 开始部署诡修仙游戏指南..."

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装Python3"
    exit 1
fi

# 检查pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 未安装，请先安装pip3"
    exit 1
fi

# 安装依赖
echo "📦 安装Python依赖..."
pip3 install fastapi uvicorn

# 检查端口8888是否被占用
if lsof -Pi :8888 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  端口8888已被占用，请先关闭占用进程或修改端口"
    echo "查看占用进程: lsof -i :8888"
    echo "杀死进程: kill -9 \$(lsof -t -i:8888)"
    read -p "是否继续部署？(y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 创建systemd服务文件（可选）
echo "📝 创建systemd服务配置..."
cat > /tmp/guixiuxian-web.service << EOF
[Unit]
Description=诡修仙游戏指南Web服务
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3 $(pwd)/web_server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "📋 systemd服务文件已创建在 /tmp/guixiuxian-web.service"
echo "如需设置开机自启，请执行："
echo "  sudo cp /tmp/guixiuxian-web.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable guixiuxian-web"
echo "  sudo systemctl start guixiuxian-web"

# 启动web服务器
echo "🌐 启动Web服务器..."
echo "访问地址: http://oversky.online:8888"
echo "本地地址: http://localhost:8888"
echo "按 Ctrl+C 停止服务"

python3 web_server.py
