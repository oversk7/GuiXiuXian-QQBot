import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.cooking import cooking_service
from plugins.xiuxian_game.cooking.cooking_service import CookingService, DishQuality, RecipeData
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemConfig, ItemInstance
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


@pytest.fixture
def service(monkeypatch):
    service = CookingService()
    recipe = RecipeData({
        "recipe_id": "concurrency_soup", "name": "测试汤", "category": "soup",
        "tier": "white", "kitchen_level": 0, "ingredients": {"cook_a": 2, "cook_b": 2},
        "base_price": 100, "description": "测试",
    })
    service.recipe_manager = SimpleNamespace(get_recipe=lambda key: recipe)
    monkeypatch.setattr(cooking_service.random, "random", lambda: 0)
    monkeypatch.setattr(service, "_determine_quality", lambda *args: DishQuality.NORMAL)
    for item_id in ["cook_a", "cook_b", "dish_concurrency_soup_normal", "dish_concurrency_soup_dark"]:
        item = ItemConfig({"item_id": item_id, "name": item_id, "description": "测试",
                           "type": "DISH" if item_id.startswith("dish_") else "MATERIAL", "price": 1})
        monkeypatch.setitem(config.items_config["by_id"], item_id, item)
    return service


async def seed(factory, a=2, b=2):
    async with db.safe_session(factory) as session:
        session.add(Player(id="cook", uid=1, nickname="厨师"))
        await session.flush()
        session.add_all([ItemInstance(player_id="cook", item_id="cook_a", quantity=a),
                         ItemInstance(player_id="cook", item_id="cook_b", quantity=b)])


def prepare_uow(uow, monkeypatch):
    monkeypatch.setattr(uow.player_recipes, "has_recipe", AsyncMock(return_value=True))
    monkeypatch.setattr(uow.restaurants, "get_by_player_id", AsyncMock(return_value=None))


async def stock(factory):
    async with db.safe_session(factory) as session:
        items = (await session.execute(select(ItemInstance))).scalars().all()
        return {item.item_id: item.quantity for item in items}


@pytest.mark.parametrize("initial,removed,success", [(2, 1, False), (2, 2, False), (4, 1, True)])
async def test_mysql_cooking_rechecks_inventory_after_precheck(mysql_session_factory, monkeypatch, service,
                                                             initial, removed, success):
    factory = mysql_session_factory
    await seed(factory, b=initial)
    async with UnitOfWork(factory) as uow:
        prepare_uow(uow, monkeypatch)
        count = uow.items.get_material_total_quantity
        # 保留引用，避免旧实例从 ORM 的弱引用身份映射中消失。
        stale_items = []

        async def count_and_change(player_id, item_id):
            result = await count(player_id, item_id)
            if item_id == "cook_b":
                stale_items.extend((await uow.session.execute(select(ItemInstance))).scalars().all())
                async with db.safe_session(factory) as competitor:
                    await ItemInstance.consume_item(competitor, player_id, item_id, removed)
            return result

        monkeypatch.setattr(uow.items, "get_material_total_quantity", count_and_change)
        result, message, dishes = await service.cook_dish(uow, "cook", "concurrency_soup")
        assert result is success
        if success:
            assert len(dishes) == 1 and dishes[0]["quality"] == DishQuality.NORMAL
        else:
            assert "食材不足" in message and dishes is None
    expected = {"cook_b": initial - removed} if initial > removed else {}
    if success:
        expected["cook_b"] -= 2
        expected["dish_concurrency_soup_normal"] = 1
    else:
        expected["cook_a"] = 2
    assert await stock(factory) == expected


async def test_mysql_two_cooks_cannot_use_same_ingredients(mysql_session_factory, monkeypatch, service):
    factory = mysql_session_factory
    await seed(factory)
    barrier = asyncio.Barrier(2)

    async def cook():
        async with UnitOfWork(factory) as uow:
            prepare_uow(uow, monkeypatch)
            count = uow.items.get_material_total_quantity

            async def synchronized_count(player_id, item_id):
                result = await count(player_id, item_id)
                if item_id == "cook_b":
                    await barrier.wait()
                return result

            monkeypatch.setattr(uow.items, "get_material_total_quantity", synchronized_count)
            return await service.cook_dish(uow, "cook", "concurrency_soup")

    results = await asyncio.wait_for(asyncio.gather(cook(), cook()), timeout=15)
    assert sum(success for success, _, _ in results) == 1
    assert await stock(factory) == {"dish_concurrency_soup_normal": 1}


async def test_mysql_full_bag_rolls_back_all_ingredients(mysql_session_factory, monkeypatch, service):
    factory = mysql_session_factory
    await seed(factory)
    monkeypatch.setattr(ItemInstance, "add_item", AsyncMock(side_effect=ValueError("背包空间不足")))
    async with UnitOfWork(factory) as uow:
        prepare_uow(uow, monkeypatch)
        success, message, dishes = await service.cook_dish(uow, "cook", "concurrency_soup")
        assert not success and "背包空间不足" in message and dishes is None
    assert await stock(factory) == {"cook_a": 2, "cook_b": 2}


async def test_failed_cook_preserves_half_consumption_and_skips_zero(monkeypatch, service):
    recipe = service.recipe_manager.get_recipe("concurrency_soup")
    recipe.ingredients = {"cook_b": 1, "cook_a": 3}
    monkeypatch.setattr(cooking_service.random, "random", lambda: 0.99)
    add_item = AsyncMock()
    monkeypatch.setattr(ItemInstance, "add_item", add_item)
    uow = SimpleNamespace(
        session=Mock(), players=SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id="cook"))),
        player_recipes=SimpleNamespace(has_recipe=AsyncMock(return_value=True)),
        restaurants=SimpleNamespace(get_by_player_id=AsyncMock(return_value=None)),
        items=SimpleNamespace(get_material_total_quantity=AsyncMock(return_value=10),
                              consume_item=AsyncMock(return_value=True)),
        commit=AsyncMock(), rollback=AsyncMock(),
    )
    success, _, dishes = await service.cook_dish(uow, "cook", recipe.recipe_id, quantity=2)
    assert success and len(dishes) == 2
    assert all(dish["quality"] == DishQuality.DARK and dish["price"] == 10 for dish in dishes)
    uow.items.consume_item.assert_awaited_once_with("cook", "cook_a", 2)
    add_item.assert_awaited_once_with(uow.session, "cook", "dish_concurrency_soup_dark", 2)
    uow.commit.assert_awaited_once()
