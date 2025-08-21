#!/usr/bin/env python3
"""
测试俄罗斯轮盘赌子弹生成的随机性
"""
import sys
import os
import random

# 直接复制核心逻辑来测试
class RussianRouletteCore:
    """恶魔轮盘赌核心游戏逻辑"""

    @staticmethod
    def generate_bullets(live_count: int = None, blank_count: int = None):
        """生成随机弹药序列"""
        # 如果没有指定数量，则从预设配置中随机选择
        if live_count is None or blank_count is None:
            bullet_configs = [
                (2, 4),  # 2实弹 + 4空包弹
                (3, 3),  # 3实弹 + 3空包弹
                (4, 2),  # 4实弹 + 2空包弹
            ]
            live_count, blank_count = random.choice(bullet_configs)

        bullets = [True] * live_count + [False] * blank_count
        random.shuffle(bullets)
        return bullets

def test_bullet_randomness():
    """测试子弹生成的随机性"""
    print("🔍 测试俄罗斯轮盘赌子弹生成随机性")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # 统计第一发子弹的类型
    first_bullet_stats = {"实弹": 0, "空包弹": 0}
    total_tests = 1000
    
    print(f"📊 进行 {total_tests} 次测试...")
    
    for i in range(total_tests):
        bullets = RussianRouletteCore.generate_bullets()
        first_bullet = bullets[0]
        
        if first_bullet:
            first_bullet_stats["实弹"] += 1
        else:
            first_bullet_stats["空包弹"] += 1
        
        # 每100次显示一次进度
        if (i + 1) % 100 == 0:
            print(f"⏳ 已完成 {i + 1}/{total_tests} 次测试")
    
    print("\n📈 第一发子弹统计结果：")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    live_count = first_bullet_stats["实弹"]
    blank_count = first_bullet_stats["空包弹"]
    live_percentage = (live_count / total_tests) * 100
    blank_percentage = (blank_count / total_tests) * 100
    
    print(f"💥 实弹：{live_count} 次 ({live_percentage:.1f}%)")
    print(f"🔫 空包弹：{blank_count} 次 ({blank_percentage:.1f}%)")
    
    # 分析结果
    print("\n🔍 分析结果：")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # 理论期望值计算
    # 配置：(2,4), (3,3), (4,2) 各有1/3概率
    # 第一发是实弹的理论概率：
    # (2,4): 2/6 = 1/3
    # (3,3): 3/6 = 1/2  
    # (4,2): 4/6 = 2/3
    # 平均：(1/3 + 1/2 + 2/3) / 3 = (2+3+4)/(6*3) = 9/18 = 1/2 = 50%
    expected_live_percentage = 50.0
    
    print(f"📊 理论期望：实弹 {expected_live_percentage}%，空包弹 {100-expected_live_percentage}%")
    
    # 检查是否存在明显偏差
    deviation = abs(live_percentage - expected_live_percentage)
    if deviation > 5:  # 偏差超过5%认为异常
        print(f"⚠️  警告：实弹概率偏差较大 ({deviation:.1f}%)，可能存在问题！")
        if live_percentage < 40:
            print("❌ 第一发子弹确实倾向于空包弹！")
        elif live_percentage > 60:
            print("❌ 第一发子弹确实倾向于实弹！")
    else:
        print(f"✅ 随机性正常，偏差在合理范围内 ({deviation:.1f}%)")
    
    # 详细分析每种配置的第一发概率
    print("\n🎯 详细配置分析：")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    config_stats = {
        (2, 4): {"实弹": 0, "空包弹": 0, "总数": 0},
        (3, 3): {"实弹": 0, "空包弹": 0, "总数": 0},
        (4, 2): {"实弹": 0, "空包弹": 0, "总数": 0}
    }
    
    # 重新测试并记录配置
    for i in range(1000):
        bullets = RussianRouletteCore.generate_bullets()
        live_count = sum(1 for b in bullets if b)
        blank_count = len(bullets) - live_count
        config = (live_count, blank_count)
        
        if config in config_stats:
            config_stats[config]["总数"] += 1
            if bullets[0]:
                config_stats[config]["实弹"] += 1
            else:
                config_stats[config]["空包弹"] += 1
    
    for config, stats in config_stats.items():
        if stats["总数"] > 0:
            live_rate = (stats["实弹"] / stats["总数"]) * 100
            print(f"配置 {config[0]}实弹+{config[1]}空包弹：")
            print(f"  出现次数：{stats['总数']}")
            print(f"  第一发实弹率：{live_rate:.1f}% ({stats['实弹']}/{stats['总数']})")
            print(f"  理论实弹率：{config[0]/(config[0]+config[1])*100:.1f}%")
            print()

if __name__ == "__main__":
    test_bullet_randomness()
