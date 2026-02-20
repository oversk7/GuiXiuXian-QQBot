"""
物品价格校准分析工具

根据游戏机制（掉落率、配方成本、属性效果）自动推导每个物品的理论价格，
与当前 items.yaml 中的配置价格对比，输出分析报告。

用法：
    python tools/price_calibration.py
    python tools/price_calibration.py --type MATERIAL        # 只看材料
    python tools/price_calibration.py --type EQUIPMENT       # 只看装备
    python tools/price_calibration.py --warn-only            # 只显示偏差大的
    python tools/price_calibration.py --export corrections.yaml  # 导出建议修正
"""

import yaml
import sys
import os
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ─────────────────── 定价参数（可调整） ───────────────────

# 材料定价：基于掉率的稀缺度倍率
# 公式：theoretical_price = WHITE_BASE * (white_drop / this_drop) * difficulty_mult
DROP_RATES = {
    "white":  0.30,
    "green":  0.15,
    "blue":   0.08,
    "purple": 0.03,
    "orange": 0.01,
}

# 白色材料的价格基准（锚点）
WHITE_MATERIAL_BASE = 80

# 难度系数：高稀有度材料需要更深的诡域层级才能获取，有额外时间/风险成本
DIFFICULTY_MULTIPLIER = {
    "white":  1.0,
    "green":  1.25,
    "blue":   1.5,
    "purple": 2.0,
    "orange": 2.5,
}

# 装备配方溢价倍率：成品价值 > 材料成本之和（加工增值）
RECIPE_MARKUP = 1.2

# 宝石属性定价基准：每 1% 战斗属性值多少金币
GEM_ATTR_VALUE_PER_PERCENT = {
    "critical_rate":      10000,   # 暴击率
    "combo_rate":         10000,   # 连击率
    "dodge_rate":         10000,   # 闪避率
    "counter_rate":       8000,    # 反击率
    "critical_damage":    6000,    # 暴击伤害（按%算）
    "penetration":        8000,    # 穿透率
    "spirit_burst":       8000,    # 灵爆率
    "anti_crit_rate":     8000,    # 抗暴率
}

# 鱼类定价基准（比材料低，因为鱼的用途主要是烹饪）
FISH_BASE = 50
FISH_DIFFICULTY_MULT = {
    "white":  1.0,
    "green":  1.2,
    "blue":   1.5,
    "purple": 2.0,
    "orange": 3.0,
}

# 偏差阈值：超过此比例视为需要调整
WARN_THRESHOLD = 0.5  # 50% 偏差

# ─────────────────── 主逻辑 ───────────────────


def load_items(yaml_path: str) -> dict:
    """加载 items.yaml"""
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_material_theoretical_prices(items_data: dict) -> Dict[str, int]:
    """
    计算所有材料的理论价格（基于掉率稀缺度）。
    返回 {item_id: theoretical_price}
    """
    prices = {}
    white_drop = DROP_RATES["white"]

    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "MATERIAL":
                continue
            rarity = item.get("rarity", "white")
            drop_rate = DROP_RATES.get(rarity, DROP_RATES["white"])
            diff_mult = DIFFICULTY_MULTIPLIER.get(rarity, 1.0)

            # 理论价格 = 白色基准 × 稀缺度倍率 × 难度系数
            scarcity_ratio = white_drop / drop_rate
            theoretical = int(WHITE_MATERIAL_BASE * scarcity_ratio * diff_mult)
            prices[item["item_id"]] = theoretical

    return prices


def compute_fish_theoretical_prices(items_data: dict) -> Dict[str, int]:
    """计算鱼类理论价格"""
    prices = {}
    white_drop = DROP_RATES["white"]

    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "FISH":
                continue
            rarity = item.get("rarity", "white")
            drop_rate = DROP_RATES.get(rarity, DROP_RATES["white"])
            diff_mult = FISH_DIFFICULTY_MULT.get(rarity, 1.0)

            scarcity_ratio = white_drop / drop_rate
            theoretical = int(FISH_BASE * scarcity_ratio * diff_mult)
            prices[item["item_id"]] = theoretical

    return prices


def build_all_prices_index(items_data: dict, material_prices: Dict[str, int]) -> Dict[str, int]:
    """
    构建所有物品的价格索引（用于装备配方成本计算）。
    材料使用理论价格，其他物品使用 yaml 中的 price。
    """
    index = {}
    for category in items_data["items"].values():
        for item in category:
            item_id = item["item_id"]
            if item_id in material_prices:
                index[item_id] = material_prices[item_id]
            else:
                index[item_id] = item.get("price", 0)
    return index


def compute_equipment_recipe_costs(
    items_data: dict, price_index: Dict[str, int]
) -> Dict[str, dict]:
    """
    计算所有有配方的装备的制作成本。
    返回 {item_id: {"material_cost": X, "gold_cost": Y, "total": Z, "theoretical": W, "details": [...]}}
    """
    results = {}
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "EQUIPMENT":
                continue
            recipe = item.get("recipe")
            if not recipe:
                continue  # Boss 掉落装备无配方

            gold_cost = recipe.get("gold", 0)
            materials = recipe.get("materials", {})
            material_cost = 0
            details = []

            for mat_id, qty in materials.items():
                mat_price = price_index.get(mat_id, 0)
                cost = mat_price * qty
                material_cost += cost
                details.append((mat_id, qty, mat_price, cost))

            total = material_cost + gold_cost
            theoretical = int(total * RECIPE_MARKUP)

            results[item["item_id"]] = {
                "material_cost": material_cost,
                "gold_cost": gold_cost,
                "total_cost": total,
                "theoretical_price": theoretical,
                "details": details,
            }

    return results


def compute_gem_theoretical_prices(items_data: dict) -> Dict[str, dict]:
    """
    计算宝石理论价格（基于属性加成效果）。
    返回 {item_id: {"theoretical": X, "attr_details": [...]}}
    """
    results = {}
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "GEM":
                continue
            attr_bonus = item.get("attr_bonus", {})
            total_value = 0
            attr_details = []

            for attr_name, attr_value in attr_bonus.items():
                value_per = GEM_ATTR_VALUE_PER_PERCENT.get(attr_name, 5000)
                contribution = value_per * attr_value
                total_value += contribution
                attr_details.append((attr_name, attr_value, value_per, contribution))

            results[item["item_id"]] = {
                "theoretical": total_value,
                "attr_details": attr_details,
            }

    return results


def format_deviation(current: int, theoretical: int) -> str:
    """格式化偏差百分比"""
    if theoretical == 0:
        return "N/A"
    dev = (current - theoretical) / theoretical
    sign = "+" if dev > 0 else ""
    return f"{sign}{dev:.0%}"


def deviation_ratio(current: int, theoretical: int) -> float:
    """计算偏差比例（绝对值）"""
    if theoretical == 0:
        return 0
    return abs(current - theoretical) / theoretical


def get_severity(dev_ratio: float) -> str:
    """根据偏差程度给出标记"""
    if dev_ratio > 1.0:
        return "‼️ 严重"
    elif dev_ratio > 0.5:
        return "⚠️ 偏高" if dev_ratio > 0 else "⚠️ 偏低"
    elif dev_ratio > 0.3:
        return "📌 注意"
    else:
        return "✅ 合理"


# ─────────────────── 报告输出 ───────────────────


def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_material_report(items_data: dict, material_prices: Dict[str, int], warn_only: bool):
    print_separator("材料定价分析")
    print(f"\n定价模型：白色基准={WHITE_MATERIAL_BASE}金币，按掉率稀缺度×难度系数推导")
    print(f"{'物品名':<12} {'稀有度':<6} {'当前价':>8} {'理论价':>8} {'偏差':>8} {'判定':<10}")
    print("-" * 60)

    items_list = []
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "MATERIAL":
                continue
            items_list.append(item)

    # 按稀有度排序
    rarity_order = {"white": 0, "green": 1, "blue": 2, "purple": 3, "orange": 4}
    items_list.sort(key=lambda x: (rarity_order.get(x.get("rarity", "white"), 0), x["name"]))

    for item in items_list:
        current = item.get("price", 0)
        theoretical = material_prices.get(item["item_id"], 0)
        dev = deviation_ratio(current, theoretical)
        severity = get_severity(dev)

        if warn_only and dev < WARN_THRESHOLD:
            continue

        print(f"{item['name']:<12} {item.get('rarity', 'white'):<6} "
              f"{current:>8,} {theoretical:>8,} "
              f"{format_deviation(current, theoretical):>8} {severity}")


def print_equipment_report(
    items_data: dict,
    recipe_costs: Dict[str, dict],
    warn_only: bool,
):
    print_separator("装备定价分析（有配方的装备）")
    print(f"\n定价模型：配方成本 = Σ(材料理论价×数量) + 制作费，再×{RECIPE_MARKUP}溢价")
    print(f"{'装备名':<14} {'等级':>4} {'当前价':>10} {'配方成本':>10} {'理论价':>10} {'偏差':>8} {'判定':<10}")
    print("-" * 76)

    equip_list = []
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "EQUIPMENT" and item["item_id"] not in recipe_costs:
                continue
            if item["item_id"] in recipe_costs:
                equip_list.append(item)

    equip_list.sort(key=lambda x: x.get("required_level", 0))

    for item in equip_list:
        costs = recipe_costs[item["item_id"]]
        current = item.get("price", 0)
        theoretical = costs["theoretical_price"]
        dev = deviation_ratio(current, theoretical)
        severity = get_severity(dev)

        if warn_only and dev < WARN_THRESHOLD:
            continue

        print(f"{item['name']:<14} {item.get('required_level', 0):>4} "
              f"{current:>10,} {costs['total_cost']:>10,} {theoretical:>10,} "
              f"{format_deviation(current, theoretical):>8} {severity}")

    # 没有配方的装备（Boss掉落等）
    no_recipe = []
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "EQUIPMENT":
                continue
            if item["item_id"] not in recipe_costs and item.get("price", 0) > 0:
                no_recipe.append(item)

    if no_recipe:
        print(f"\n--- 无配方装备（Boss掉落等，无法自动推导价格）---")
        print(f"{'装备名':<14} {'等级':>4} {'当前价':>10} {'稀有度':<8}")
        print("-" * 40)
        for item in sorted(no_recipe, key=lambda x: x.get("required_level", 0)):
            print(f"{item['name']:<14} {item.get('required_level', 0):>4} "
                  f"{item.get('price', 0):>10,} {item.get('rarity', '?'):<8}")


def print_gem_report(items_data: dict, gem_prices: Dict[str, dict], warn_only: bool):
    print_separator("宝石定价分析")
    print(f"\n定价模型：按属性加成计算（每1%暴击/连击≈10,000金币等）")
    print(f"{'宝石名':<16} {'当前价':>10} {'理论价':>10} {'偏差':>8} {'判定':<10} {'属性'}")
    print("-" * 80)

    gem_list = []
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "GEM":
                continue
            gem_list.append(item)

    gem_list.sort(key=lambda x: x.get("price", 0))

    for item in gem_list:
        info = gem_prices.get(item["item_id"])
        if not info:
            continue
        current = item.get("price", 0)
        theoretical = info["theoretical"]
        dev = deviation_ratio(current, theoretical)
        severity = get_severity(dev)

        if warn_only and dev < WARN_THRESHOLD:
            continue

        attr_str = ", ".join(f"{a}+{v}%" for a, v, _, _ in info["attr_details"])
        print(f"{item['name']:<16} {current:>10,} {theoretical:>10,} "
              f"{format_deviation(current, theoretical):>8} {severity:<10} {attr_str}")


def print_fish_report(items_data: dict, fish_prices: Dict[str, int], warn_only: bool):
    print_separator("鱼类定价分析")
    print(f"\n定价模型：基准={FISH_BASE}金币，按稀有度推导")
    print(f"{'鱼名':<12} {'稀有度':<6} {'当前价':>8} {'理论价':>8} {'偏差':>8} {'判定':<10}")
    print("-" * 60)

    fish_list = []
    for category in items_data["items"].values():
        for item in category:
            if item.get("type") != "FISH":
                continue
            fish_list.append(item)

    rarity_order = {"white": 0, "green": 1, "blue": 2, "purple": 3, "orange": 4}
    fish_list.sort(key=lambda x: (rarity_order.get(x.get("rarity", "white"), 0), x["name"]))

    for item in fish_list:
        current = item.get("price", 0)
        theoretical = fish_prices.get(item["item_id"], 0)
        dev = deviation_ratio(current, theoretical)
        severity = get_severity(dev)

        if warn_only and dev < WARN_THRESHOLD:
            continue

        print(f"{item['name']:<12} {item.get('rarity', 'white'):<6} "
              f"{current:>8,} {theoretical:>8,} "
              f"{format_deviation(current, theoretical):>8} {severity}")


def print_summary(
    items_data: dict,
    material_prices: Dict[str, int],
    recipe_costs: Dict[str, dict],
    gem_prices: Dict[str, dict],
    fish_prices: Dict[str, int],
):
    """打印总结统计"""
    print_separator("校准总结")

    stats = {"合理": 0, "注意": 0, "偏差": 0, "严重": 0, "无法判定": 0}

    def count(current, theoretical):
        if theoretical == 0:
            stats["无法判定"] += 1
            return
        dev = deviation_ratio(current, theoretical)
        if dev > 1.0:
            stats["严重"] += 1
        elif dev > 0.5:
            stats["偏差"] += 1
        elif dev > 0.3:
            stats["注意"] += 1
        else:
            stats["合理"] += 1

    for category in items_data["items"].values():
        for item in category:
            item_id = item["item_id"]
            current = item.get("price", 0)
            t = item.get("type", "")

            if t == "MATERIAL" and item_id in material_prices:
                count(current, material_prices[item_id])
            elif t == "EQUIPMENT" and item_id in recipe_costs:
                count(current, recipe_costs[item_id]["theoretical_price"])
            elif t == "GEM" and item_id in gem_prices:
                count(current, gem_prices[item_id]["theoretical"])
            elif t == "FISH" and item_id in fish_prices:
                count(current, fish_prices[item_id])

    total = sum(stats.values())
    print(f"\n共分析 {total} 个物品：")
    print(f"  ✅ 合理（偏差<30%）：{stats['合理']} 个")
    print(f"  📌 注意（偏差30-50%）：{stats['注意']} 个")
    print(f"  ⚠️  偏差（偏差50-100%）：{stats['偏差']} 个")
    print(f"  ‼️  严重（偏差>100%）：{stats['严重']} 个")
    print(f"  ❓ 无法判定：{stats['无法判定']} 个")

    if stats["严重"] + stats["偏差"] > 0:
        print(f"\n建议优先调整 {stats['严重']} 个严重偏差 + {stats['偏差']} 个中度偏差的物品。")
        print(f"使用 --export corrections.yaml 导出建议修正值。")


def export_corrections(
    items_data: dict,
    material_prices: Dict[str, int],
    recipe_costs: Dict[str, dict],
    gem_prices: Dict[str, dict],
    fish_prices: Dict[str, int],
    output_path: str,
):
    """导出建议修正值到 yaml 文件"""
    corrections = []

    for category in items_data["items"].values():
        for item in category:
            item_id = item["item_id"]
            current = item.get("price", 0)
            t = item.get("type", "")
            theoretical = 0

            if t == "MATERIAL" and item_id in material_prices:
                theoretical = material_prices[item_id]
            elif t == "EQUIPMENT" and item_id in recipe_costs:
                theoretical = recipe_costs[item_id]["theoretical_price"]
            elif t == "GEM" and item_id in gem_prices:
                theoretical = gem_prices[item_id]["theoretical"]
            elif t == "FISH" and item_id in fish_prices:
                theoretical = fish_prices[item_id]
            else:
                continue

            if theoretical == 0:
                continue

            dev = deviation_ratio(current, theoretical)
            if dev < WARN_THRESHOLD:
                continue

            corrections.append({
                "item_id": item_id,
                "name": item["name"],
                "type": t,
                "rarity": item.get("rarity", "N/A"),
                "current_price": current,
                "suggested_price": theoretical,
                "deviation": f"{format_deviation(current, theoretical)}",
            })

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"corrections": corrections, "total": len(corrections)},
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"\n已导出 {len(corrections)} 条修正建议到 {output_path}")


# ─────────────────── 入口 ───────────────────


def main():
    parser = argparse.ArgumentParser(description="物品价格校准分析工具")
    parser.add_argument("--type", choices=["MATERIAL", "EQUIPMENT", "GEM", "FISH", "ALL"],
                        default="ALL", help="只分析指定类型")
    parser.add_argument("--warn-only", action="store_true", help="只显示偏差>50%%的物品")
    parser.add_argument("--export", type=str, help="导出建议修正到 yaml 文件")
    args = parser.parse_args()

    # 定位 items.yaml
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    yaml_path = project_root / "plugins" / "xiuxian_game" / "data" / "items.yaml"

    if not yaml_path.exists():
        print(f"错误：找不到 {yaml_path}")
        sys.exit(1)

    print(f"加载: {yaml_path}")
    items_data = load_items(str(yaml_path))

    # 第一步：计算材料理论价格
    material_prices = compute_material_theoretical_prices(items_data)
    fish_prices = compute_fish_theoretical_prices(items_data)

    # 第二步：构建价格索引（材料用理论价格）
    price_index = build_all_prices_index(items_data, material_prices)

    # 第三步：计算装备配方成本
    recipe_costs = compute_equipment_recipe_costs(items_data, price_index)

    # 第四步：计算宝石理论价格
    gem_prices = compute_gem_theoretical_prices(items_data)

    # 输出报告
    show_type = args.type
    warn_only = args.warn_only

    if show_type in ("ALL", "MATERIAL"):
        print_material_report(items_data, material_prices, warn_only)

    if show_type in ("ALL", "EQUIPMENT"):
        print_equipment_report(items_data, recipe_costs, warn_only)

    if show_type in ("ALL", "GEM"):
        print_gem_report(items_data, gem_prices, warn_only)

    if show_type in ("ALL", "FISH"):
        print_fish_report(items_data, fish_prices, warn_only)

    # 总结
    print_summary(items_data, material_prices, recipe_costs, gem_prices, fish_prices)

    # 导出
    if args.export:
        export_corrections(
            items_data, material_prices, recipe_costs, gem_prices, fish_prices,
            args.export,
        )


if __name__ == "__main__":
    main()
