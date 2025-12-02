"""
游戏系统诊断脚本 - 新手体验与系统平衡分析
基于 game-designer 代理的系统诊断需求
"""
import sys
import os
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from plugins.xiuxian_game.models.db import AsyncSessionLocal
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.guild import Guild, GuildMember
from plugins.xiuxian_game.config import config
from sqlalchemy import select, func, and_, desc
from collections import defaultdict
import json


async def analyze_player_distribution():
    """分析玩家等级分布 - 识别新手卡关"""
    async with AsyncSessionLocal() as session:
        # 查询所有玩家
        result = await session.execute(select(Player))
        players = result.scalars().all()

        total = len(players)
        if total == 0:
            print("警告: 数据库无玩家数据")
            return {}

        # 等级分布统计
        level_ranges = {
            "0-10": 0,
            "11-20": 0,
            "21-30": 0,
            "31-50": 0,
            "51-100": 0,
            "101+": 0
        }

        for p in players:
            if p.level <= 10:
                level_ranges["0-10"] += 1
            elif p.level <= 20:
                level_ranges["11-20"] += 1
            elif p.level <= 30:
                level_ranges["21-30"] += 1
            elif p.level <= 50:
                level_ranges["31-50"] += 1
            elif p.level <= 100:
                level_ranges["51-100"] += 1
            else:
                level_ranges["101+"] += 1

        print("\n=== 玩家等级分布分析 ===")
        print(f"总玩家数: {total}")
        for range_name, count in level_ranges.items():
            pct = (count / total * 100) if total > 0 else 0
            print(f"{range_name}级: {count}人 ({pct:.1f}%)")

        return {
            "total": total,
            "distribution": level_ranges,
            "percentages": {k: (v/total*100) for k, v in level_ranges.items()}
        }


async def analyze_economy():
    """分析经济系统 - 通胀与资源分配"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Player).order_by(desc(Player.gold))
        )
        players = result.scalars().all()

        if not players:
            print("警告: 无玩家数据")
            return {}

        gold_values = [p.gold for p in players]
        gold_values.sort(reverse=True)

        total_gold = sum(gold_values)
        top_10_count = max(1, len(gold_values) // 10)
        top_10_gold = sum(gold_values[:top_10_count])

        print("\n=== 经济系统分析 ===")
        print(f"最高金币: {gold_values[0]:,}")
        print(f"中位数金币: {gold_values[len(gold_values)//2]:,}")
        print(f"平均金币: {total_gold//len(gold_values):,}")
        print(f"Top 10%玩家持有金币占比: {(top_10_gold/total_gold*100):.1f}%")

        # 计算基尼系数 (简化版)
        n = len(gold_values)
        gold_values_sorted = sorted(gold_values)
        cumulative_gold = 0
        gini_sum = 0
        for i, gold in enumerate(gold_values_sorted):
            cumulative_gold += gold
            gini_sum += (2 * (i + 1) - n - 1) * gold
        gini = gini_sum / (n * total_gold) if total_gold > 0 else 0

        print(f"基尼系数: {gini:.3f} (0=完全平等, 1=完全不平等)")

        return {
            "max_gold": gold_values[0],
            "median_gold": gold_values[len(gold_values)//2],
            "avg_gold": total_gold//len(gold_values),
            "top_10_percentage": top_10_gold/total_gold*100,
            "gini_coefficient": gini
        }


async def analyze_equipment_inflation():
    """分析装备属性膨胀"""
    async with AsyncSessionLocal() as session:
        # 查询所有已装备的装备
        result = await session.execute(
            select(ItemInstance).where(
                and_(
                    ItemInstance.equipped == True,
                    ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
                )
            )
        )
        equipments = result.scalars().all()

        if not equipments:
            print("警告: 无装备数据")
            return {}

        # 统计 _persist_bonus
        total_bonuses = defaultdict(int)
        max_bonuses = defaultdict(int)
        equipment_count = 0

        for eq in equipments:
            persist_bonus = (eq.extra_attrs or {}).get("_persist_bonus", {})
            if persist_bonus:
                equipment_count += 1
                for attr, value in persist_bonus.items():
                    total_bonuses[attr] += value
                    max_bonuses[attr] = max(max_bonuses[attr], value)

        print("\n=== 装备属性膨胀分析 ===")
        print(f"已装备装备总数: {len(equipments)}")
        print(f"有属性加成的装备数: {equipment_count}")

        if equipment_count > 0:
            print("\n单件装备最高加成:")
            for attr, max_val in sorted(max_bonuses.items(), key=lambda x: x[1], reverse=True)[:5]:
                avg_val = total_bonuses[attr] / equipment_count
                print(f"  {attr}: 最高={max_val}, 平均={avg_val:.1f}")

        return {
            "total_equipped": len(equipments),
            "with_bonus": equipment_count,
            "max_bonuses": dict(max_bonuses),
            "avg_bonuses": {k: total_bonuses[k]/equipment_count for k in total_bonuses} if equipment_count > 0 else {}
        }


async def analyze_resource_flow():
    """分析资源流动性 - Sources vs Sinks"""
    async with AsyncSessionLocal() as session:
        # 统计背包中的物品
        result = await session.execute(select(ItemInstance))
        all_items = result.scalars().all()

        # 分类统计
        item_type_count = defaultdict(int)
        item_total_quantity = defaultdict(int)

        for item in all_items:
            item_config = config.items_config["by_id"].get(item.item_id)
            if item_config:
                item_type = item_config.type
                item_type_count[item_type] += 1
                item_total_quantity[item_type] += item.quantity

        print("\n=== 资源流动性分析 ===")
        print("物品类型分布:")
        for item_type in ["CONSUMABLE", "MATERIAL", "EQUIPMENT", "GEM"]:
            count = item_type_count.get(item_type, 0)
            qty = item_total_quantity.get(item_type, 0)
            print(f"  {item_type}: {count}种 (总量={qty})")

        # 检查药品囤积
        heal_potions = 0
        spirit_herbs = 0
        for item in all_items:
            if item.item_id == "heal_potion":
                heal_potions += item.quantity
            elif item.item_id == "spirit_herb":
                spirit_herbs += item.quantity

        print(f"\n药品囤积检测:")
        print(f"  回春散总量: {heal_potions}")
        print(f"  凝神草总量: {spirit_herbs}")

        return {
            "item_types": dict(item_type_count),
            "item_quantities": dict(item_total_quantity),
            "potion_hoarding": {
                "heal_potion": heal_potions,
                "spirit_herb": spirit_herbs
            }
        }


async def analyze_guild_participation():
    """分析公会参与度"""
    async with AsyncSessionLocal() as session:
        # 玩家总数
        player_result = await session.execute(select(func.count(Player.id)))
        total_players = player_result.scalar()

        # 公会成员数
        member_result = await session.execute(select(func.count(GuildMember.id)))
        total_members = member_result.scalar()

        # 公会数量
        guild_result = await session.execute(select(func.count(Guild.id)))
        total_guilds = guild_result.scalar()

        print("\n=== 公会系统参与度 ===")
        print(f"总玩家数: {total_players}")
        print(f"公会成员数: {total_members}")
        print(f"加入公会比例: {(total_members/total_players*100):.1f}%")
        print(f"公会数量: {total_guilds}")

        return {
            "total_players": total_players,
            "guild_members": total_members,
            "participation_rate": total_members/total_players*100 if total_players > 0 else 0,
            "total_guilds": total_guilds
        }


async def analyze_new_player_bottleneck():
    """分析新手成长瓶颈"""
    async with AsyncSessionLocal() as session:
        # 0-10级玩家详细分析
        result = await session.execute(
            select(Player).where(Player.level <= 10).order_by(Player.level)
        )
        newbies = result.scalars().all()

        if not newbies:
            print("警告: 无新手玩家数据")
            return {}

        # 统计各级人数
        level_dist = defaultdict(int)
        avg_gold_by_level = defaultdict(list)
        avg_stamina_by_level = defaultdict(list)

        for p in newbies:
            level_dist[p.level] += 1
            avg_gold_by_level[p.level].append(p.gold)
            avg_stamina_by_level[p.level].append(p.stamina)

        print("\n=== 新手成长瓶颈分析 (0-10级) ===")
        print(f"新手总数: {len(newbies)}")
        print("\n各级分布:")
        for lv in sorted(level_dist.keys()):
            count = level_dist[lv]
            avg_gold = sum(avg_gold_by_level[lv]) / len(avg_gold_by_level[lv])
            avg_stamina = sum(avg_stamina_by_level[lv]) / len(avg_stamina_by_level[lv])
            print(f"  Lv.{lv}: {count}人 (平均金币={avg_gold:.0f}, 平均咒抗={avg_stamina:.1f})")

        return {
            "total_newbies": len(newbies),
            "level_distribution": dict(level_dist),
            "avg_gold": {k: sum(v)/len(v) for k, v in avg_gold_by_level.items()},
            "avg_stamina": {k: sum(v)/len(v) for k, v in avg_stamina_by_level.items()}
        }


async def main():
    """主分析流程"""
    print("=" * 60)
    print("诡修仙游戏系统诊断 - 新手体验与平衡分析")
    print("=" * 60)

    # 执行所有分析
    results = {}

    results["player_distribution"] = await analyze_player_distribution()
    results["economy"] = await analyze_economy()
    results["equipment"] = await analyze_equipment_inflation()
    results["resource_flow"] = await analyze_resource_flow()
    results["guild"] = await analyze_guild_participation()
    results["newbie_bottleneck"] = await analyze_new_player_bottleneck()

    # 保存结果到JSON
    output_file = project_root / "scripts" / "game_analysis_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"分析完成! 结果已保存到: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
