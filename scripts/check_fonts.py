#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
字体检测和验证脚本
用于检查系统中可用的中文字体
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont

def check_font_paths():
    """检查常见的中文字体路径"""
    font_paths = [
        # Windows 中文字体
        'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
        'C:/Windows/Fonts/simhei.ttf',    # 黑体
        'C:/Windows/Fonts/simsun.ttc',    # 宋体
        
        # Linux 中文字体
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',           # 文泉驿微米黑
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',             # 文泉驿正黑
        '/usr/share/fonts/truetype/arphic/ukai.ttc',                # AR PL UKai CN
        '/usr/share/fonts/truetype/arphic/uming.ttc',               # AR PL UMing CN
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',   # Noto Sans CJK
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf', # Droid Sans Fallback
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/wqy-microhei/wqy-microhei.ttc',
        '/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc',
        
        # macOS 中文字体
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/Hiragino Sans GB.ttc',
    ]
    
    available_fonts = []
    for font_path in font_paths:
        if os.path.exists(font_path):
            available_fonts.append(font_path)
            print(f"✓ 找到字体: {font_path}")
        else:
            print(f"✗ 未找到: {font_path}")
    
    return available_fonts

def test_font_rendering(font_path, test_text="测试中文字体渲染"):
    """测试字体渲染效果"""
    try:
        # 创建测试图片
        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)
        
        # 加载字体
        font = ImageFont.truetype(font_path, 24)
        
        # 绘制文字
        draw.text((10, 30), test_text, fill='black', font=font)
        
        # 保存测试图片
        output_path = f"font_test_{os.path.basename(font_path)}.png"
        img.save(output_path)
        print(f"✓ 字体渲染测试成功: {font_path}")
        print(f"  测试图片保存为: {output_path}")
        return True
        
    except Exception as e:
        print(f"✗ 字体渲染测试失败: {font_path}")
        print(f"  错误: {e}")
        return False

def check_system_fonts():
    """检查系统字体命令"""
    print("\n=== 系统字体检查 ===")
    
    # 检查 fc-list 命令
    if os.system("which fc-list > /dev/null 2>&1") == 0:
        print("✓ fc-list 命令可用")
        print("\n中文字体列表:")
        os.system("fc-list :lang=zh | head -10")
    else:
        print("✗ fc-list 命令不可用")
        print("请安装 fontconfig: sudo apt install fontconfig")

def main():
    print("=== 字体检测和验证脚本 ===\n")
    
    # 检查字体路径
    print("1. 检查常见字体路径:")
    available_fonts = check_font_paths()
    
    if not available_fonts:
        print("\n❌ 未找到任何中文字体！")
        print("请运行字体安装脚本: bash scripts/install_fonts.sh")
        return
    
    print(f"\n✓ 找到 {len(available_fonts)} 个可用字体")
    
    # 测试字体渲染
    print("\n2. 测试字体渲染:")
    success_count = 0
    for font_path in available_fonts[:3]:  # 只测试前3个字体
        if test_font_rendering(font_path):
            success_count += 1
    
    print(f"\n✓ {success_count}/{min(3, len(available_fonts))} 个字体渲染测试成功")
    
    # 检查系统字体
    check_system_fonts()
    
    # 给出建议
    print("\n=== 建议 ===")
    if success_count > 0:
        print("✓ 字体配置正常，应该可以正确显示中文")
    else:
        print("❌ 字体渲染失败，建议:")
        print("1. 运行字体安装脚本: bash scripts/install_fonts.sh")
        print("2. 重启应用程序")
        print("3. 检查 PIL/Pillow 是否正确安装")

if __name__ == "__main__":
    main()
