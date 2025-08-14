#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
快速字体测试脚本
用于快速验证地图可视化器的字体配置
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.xiuxian_game.world.map_visualizer import MapVisualizer

def test_map_visualizer_fonts():
    """测试地图可视化器的字体配置"""
    print("=== 地图可视化器字体测试 ===\n")
    
    # 创建地图可视化器实例
    visualizer = MapVisualizer()
    
    # 加载字体
    print("1. 加载字体...")
    visualizer._load_fonts()
    
    # 检查字体加载情况
    print("\n2. 字体加载情况:")
    for name, font in visualizer.fonts.items():
        print(f"  {name}: {type(font).__name__}")
    
    # 测试中文字体支持
    print("\n3. 测试中文字体支持:")
    test_texts = ["图例", "玩家位置", "市集交易", "打工地点"]
    
    for text in test_texts:
        supports = visualizer._check_font_support(text)
        status = "✓" if supports else "✗"
        print(f"  {status} '{text}': {'支持' if supports else '不支持'}")
    
    # 给出建议
    print("\n4. 建议:")
    if visualizer._check_font_support("测试"):
        print("  ✓ 字体配置正常，可以正确显示中文")
    else:
        print("  ❌ 字体配置有问题，建议:")
        print("    1. 运行: bash scripts/install_fonts.sh")
        print("    2. 重启应用程序")
        print("    3. 检查字体安装: python3 scripts/check_fonts.py")

if __name__ == "__main__":
    try:
        test_map_visualizer_fonts()
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保在项目根目录运行此脚本")
    except Exception as e:
        print(f"测试失败: {e}")
        print("请检查依赖是否正确安装")
