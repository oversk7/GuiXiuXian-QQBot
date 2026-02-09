"""
临时修复脚本：注册菜肴物品配置
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=" * 60)
    print("烹饪系统物品配置修复脚本")
    print("=" * 60)

    try:
        # 1. 加载食谱管理器
        print("\n[1] 加载食谱配置...")
        from plugins.xiuxian_game.cooking.cooking_service import RecipeManager
        recipe_manager = RecipeManager()
        recipe_count = len(recipe_manager._recipes)
        print(f"成功加载 {recipe_count} 个食谱")

        # 显示部分食谱
        print("\n食谱列表（前5个）:")
        for i, (recipe_id, recipe) in enumerate(list(recipe_manager._recipes.items())[:5]):
            print(f"  {i+1}. {recipe_id} -> {recipe.name}")

        # 2. 生成菜肴物品
        print("\n[2] 生成菜肴物品配置...")
        from plugins.xiuxian_game.cooking.dish_item_generator import DishItemGenerator
        dish_items = DishItemGenerator.generate_dish_items(recipe_manager)
        print(f"成功生成 {len(dish_items)} 个菜肴物品")

        # 3. 注册到配置系统
        print("\n[3] 注册到配置系统...")
        from plugins.xiuxian_game.config import config
        DishItemGenerator.register_dish_items_to_config(config, recipe_manager)

        # 4. 验证注册结果
        print("\n[4] 验证注册结果...")
        test_item_id = "dish_braised_carp_normal"
        if test_item_id in config.items_config.get("by_id", {}):
            item = config.items_config["by_id"][test_item_id]
            print(f"验证成功: {test_item_id} -> {item.name}")
        else:
            print(f"验证失败: {test_item_id} 未找到")

        # 统计
        dish_count = sum(1 for k in config.items_config.get("by_id", {}).keys() if k.startswith("dish_"))
        print(f"\n配置系统中菜肴物品总数: {dish_count}")

        print("\n" + "=" * 60)
        print("修复完成！请重启Bot使配置生效")
        print("=" * 60)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
