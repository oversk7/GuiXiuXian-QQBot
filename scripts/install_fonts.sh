#!/bin/bash

# 中文字体安装脚本
# 适用于 Ubuntu/Debian/CentOS/RHEL 等 Linux 发行版

echo "开始安装中文字体..."

# 检测系统类型
if [ -f /etc/debian_version ]; then
    # Debian/Ubuntu 系统
    echo "检测到 Debian/Ubuntu 系统"
    
    # 更新包列表
    sudo apt update
    
    # 安装中文字体包
    echo "安装中文字体包..."
    sudo apt install -y fonts-wqy-microhei fonts-wqy-zenhei fonts-noto-cjk fonts-arphic-ukai fonts-arphic-uming
    
    # 安装额外的字体包
    sudo apt install -y fonts-droid-fallback ttf-wqy-microhei ttf-wqy-zenhei
    
elif [ -f /etc/redhat-release ]; then
    # CentOS/RHEL/Fedora 系统
    echo "检测到 RedHat 系列系统"
    
    # 检测包管理器
    if command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"
    elif command -v yum &> /dev/null; then
        PKG_MANAGER="yum"
    else
        echo "错误: 找不到包管理器"
        exit 1
    fi
    
    # 安装中文字体包
    echo "安装中文字体包..."
    sudo $PKG_MANAGER install -y wqy-microhei-fonts wqy-zenhei-fonts google-noto-cjk-fonts
    
    # 尝试安装额外字体
    sudo $PKG_MANAGER install -y cjkuni-ukai-fonts cjkuni-uming-fonts
    
elif [ -f /etc/arch-release ]; then
    # Arch Linux 系统
    echo "检测到 Arch Linux 系统"
    
    # 安装中文字体包
    sudo pacman -S --noconfirm wqy-microhei wqy-zenhei noto-fonts-cjk adobe-source-han-sans-cn-fonts
    
else
    echo "未识别的系统，尝试通用安装方法..."
fi

# 手动下载并安装文泉驿字体（如果系统包不可用）
FONT_DIR="/usr/share/fonts/truetype/wqy"
if [ ! -d "$FONT_DIR" ]; then
    echo "创建字体目录..."
    sudo mkdir -p "$FONT_DIR"
fi

# 下载文泉驿微米黑字体
if [ ! -f "$FONT_DIR/wqy-microhei.ttc" ]; then
    echo "下载文泉驿微米黑字体..."
    cd /tmp
    wget -O wqy-microhei-0.2.0-beta.tar.gz "https://sourceforge.net/projects/wqy/files/wqy-microhei/0.2.0-beta/wqy-microhei-0.2.0-beta.tar.gz/download" || {
        echo "下载失败，尝试备用链接..."
        wget -O wqy-microhei-0.2.0-beta.tar.gz "https://github.com/anthonyfok/fonts-wqy-microhei/raw/master/wqy-microhei.ttc" || {
            echo "字体下载失败，请手动安装"
        }
    }
    
    if [ -f "wqy-microhei-0.2.0-beta.tar.gz" ]; then
        tar -xzf wqy-microhei-0.2.0-beta.tar.gz
        sudo cp wqy-microhei/wqy-microhei.ttc "$FONT_DIR/"
        rm -rf wqy-microhei*
    fi
fi

# 更新字体缓存
echo "更新字体缓存..."
sudo fc-cache -fv

# 验证字体安装
echo "验证字体安装..."
fc-list :lang=zh

echo "字体安装完成！"
echo "如果仍然显示方块，请重启应用程序。"
