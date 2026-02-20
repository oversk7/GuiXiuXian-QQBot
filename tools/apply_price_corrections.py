"""
将 price_corrections.yaml 中的建议价格直接写入 items.yaml。
通过正则定位 item_id 后修改对应 price 行，保留原始格式。
"""
import yaml
import re
from pathlib import Path

script_dir = Path(__file__).parent
project_root = script_dir.parent
corrections_path = script_dir / "price_corrections.yaml"
items_path = project_root / "plugins" / "xiuxian_game" / "data" / "items.yaml"

# 加载修正建议
with open(corrections_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

corrections = {c["item_id"]: c["suggested_price"] for c in data["corrections"]}

# 跳过不应该改价的物品（成就、任务道具等 price=0 的特殊物品）
SKIP_IDS = set()
for c in data["corrections"]:
    # 成就物品不应有价格
    if c["item_id"].startswith("achievement_"):
        SKIP_IDS.add(c["item_id"])
    # 任务钥匙/道具如果原价=0，可能是故意的
    if c["current_price"] == 0 and c["item_id"] in (
        "medical_record_key", "surgery_notes", "director_key",
        "organ_trafficking_ledger", "knocker_relic",
    ):
        SKIP_IDS.add(c["item_id"])

for sid in SKIP_IDS:
    corrections.pop(sid, None)

print(f"共 {len(corrections)} 条修正待应用（已跳过 {len(SKIP_IDS)} 个特殊物品）")

# 读取 items.yaml 原始文本
with open(items_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 逐行扫描，遇到 item_id 匹配的就记录，然后找到下一个 price 行并替换
current_item_id = None
applied = 0
applied_items = []

for i, line in enumerate(lines):
    # 检测 item_id 行
    m = re.match(r'^(\s*)(?:- )?item_id:\s*["\']?(\w+)["\']?\s*$', line)
    if m:
        current_item_id = m.group(2)
        continue

    # 如果当前 item_id 在修正列表中，找 price 行
    if current_item_id and current_item_id in corrections:
        pm = re.match(r'^(\s*)price:\s*(\d+)\s*$', line)
        if pm:
            indent = pm.group(1)
            old_price = int(pm.group(2))
            new_price = corrections[current_item_id]
            lines[i] = f"{indent}price: {new_price}\n"
            applied_items.append((current_item_id, old_price, new_price))
            applied += 1
            del corrections[current_item_id]
            current_item_id = None

# 写回
with open(items_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"\n已应用 {applied} 条修正到 items.yaml")
if corrections:
    print(f"未匹配（可能无 price 行）: {list(corrections.keys())}")

# 显示修改摘要
print(f"\n{'物品ID':<30} {'旧价格':>10} {'新价格':>10} {'变化':>8}")
print("-" * 65)
for item_id, old, new in sorted(applied_items, key=lambda x: x[0]):
    change = new - old
    sign = "+" if change > 0 else ""
    print(f"{item_id:<30} {old:>10,} {new:>10,} {sign}{change:>8,}")
