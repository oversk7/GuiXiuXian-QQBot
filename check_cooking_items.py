"""
烹饪系统物品注册诊断脚本
用于检查菜肴物品是否正确注册到配置系统
"""
import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def main():
    print("=" * 60)
    print("烹饪系统诊断工具")
    print("=" * 60)

    try:
        # 1. 检查食谱配置文件
        print("\n[1] 检查食谱配置文件...")
        recipes_file = Path(__file__).parent / "plugins" / "xiuxian_game" / "data" / "recipes.yaml"
        if not recipes_file.exists():
            print(f"❌ 食谱配置文件不存在: {recipes_file}")
            return
        else:
            print(f"✅ 食谱配置文件存在: {recipes_file}")

        # 2. 加载食谱
        print("\n[2] 加载食谱配置...")
        from plugins.xiuxian_game.cooking.cooking_service import RecipeManager
        recipe_manager = RecipeManager()
        print(f"✅ 成功加载 {len(recipe_manager._recipes)} 个食谱")

        # 检查 fried_catfish 食谱
        if "fried_catfish" in recipe_manager._recipes:
            recipe = recipe_manager._recipes["fried_catfish"]
            print(f"✅ 找到 'fried_catfish' 食谱: {recipe.name}")
        else:
            print(f"❌ 未找到 'fried_catfish' 食谱")
            print(f"可用的食谱ID: {list(recipe_manager._recipes.keys())}")

        # 3. 生成菜肴物品
        print("\n[3] 生成菜肴物品配置...")
        from plugins.xiuxian_game.cooking.dish_item_generator import DishItemGenerator
        dish_items = DishItemGenerator.generate_dish_items(recipe_manager)
        print(f"✅ 成功生成 {len(dish_items)} 个菜肴物品配置")

        # 检查 dish_fried_catfish_normal
        if "dish_fried_catfish_normal" in dish_items:
            dish = dish_items["dish_fried_catfish_normal"]
            print(f"✅ 找到 'dish_fried_catfish_normal': {dish.name}")
        else:
            print(f"❌ 未找到 'dish_fried_catfish_normal'")
            # 显示所有fried_catfish相关的菜肴
            fried_catfish_dishes = [k for k in dish_items.keys() if "fried_catfish" in k]
            print(f"fried_catfish相关菜肴: {fried_catfish_dishes}")

        # 4. 检查配置系统注册
        print("\n[4] 检查配置系统中的注册状态...")
        from plugins.xiuxian_game.config import config

        if "by_id" not in config.items_config:
            print("❌ config.items_config 中没有 'by_id' 键")
            return

        if "dish_fried_catfish_normal" in config.items_config["by_id"]:
            item = config.items_config["by_id"]["dish_fried_catfish_normal"]
            print(f"✅ 'dish_fried_catfish_normal' 已注册到配置系统: {item.name}")
        else:
            print(f"❌ 'dish_fried_catfish_normal' 未在配置系统中找到")

            # 尝试手动注册
            print("\n[5] 尝试手动注册菜肴物品...")
            DishItemGenerator.register_dish_items_to_config(config, recipe_manager)

            # 再次检查
            if "dish_fried_catfish_normal" in config.items_config["by_id"]:
                print(f"✅ 手动注册成功！")
            else:
                print(f"❌ 手动注册失败")

        # 6. 显示统计信息
        print("\n" + "=" * 60)
        print("统计信息:")
        print(f"- 食谱总数: {len(recipe_manager._recipes)}")
        print(f"- 菜肴物品总数: {len(dish_items)}")
        print(f"- 配置系统中物品总数: {len(config.items_config.get('by_id', {}))}")

        # 显示部分菜肴ID
        print("\n示例菜肴ID (前5个):")
        for i, (item_id, item_config) in enumerate(list(dish_items.items())[:5]):
            print(f"  {i+1}. {item_id} -> {item_config.name}")

        print("\n" + "=" * 60)
        print("✅ 诊断完成")

    except Exception as e:
        print(f"\n❌ 诊断过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
