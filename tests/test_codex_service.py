from types import SimpleNamespace

from plugins.xiuxian_game.item import codex_service


def entry(name, category="物品", description="", aliases=None, lines=None, key=None):
    return {
        "key": key or f"test:{name}",
        "name": name,
        "category": category,
        "description": description,
        "aliases": aliases or [],
        "lines": lines or [],
    }


def test_runtime_entries_follow_contract_and_exclude_admin_knowledge():
    entries = codex_service.get_entries()
    assert entries
    assert all({"key", "name", "category", "description", "aliases", "lines"} <= entry.keys() for entry in entries)
    assert all(isinstance(entry["aliases"], list) and isinstance(entry["lines"], list) for entry in entries)
    assert all(not entry["name"].startswith("管理员") for entry in entries)
    assert any(entry["category"] == "烹饪食谱" for entry in entries)
    assert any(entry["category"] == "玩法知识" for entry in entries)
    assert any(entry["key"] == "knowledge:battle_mechanics_detail" for entry in entries)
    assert not any("AI客服专用" in entry["name"] for entry in entries)
    assert any(entry["key"] == "knowledge:battle_mechanics_detail"
               for entry in codex_service.search_entries("暴击", entries))


def test_empty_source_data_is_reported_as_pending_not_unobtainable(monkeypatch):
    from plugins.xiuxian_game.item import codex_sources

    item = SimpleNamespace(item_id="test_material")
    monkeypatch.setattr(codex_service, "_item_entries", lambda: [entry("测试材料", aliases=["test_material"])])
    monkeypatch.setattr(codex_service, "_recipe_entries", lambda: [])
    monkeypatch.setattr(codex_service, "_cooking_entries", lambda: [])
    monkeypatch.setattr(codex_service, "_craft_entries", lambda: [])
    monkeypatch.setattr(codex_service, "_knowledge_entries", lambda: [])
    monkeypatch.setattr(codex_service, "config", SimpleNamespace(
        items_config={"by_id": {"test_material": item}}, elixirs_config={"elixirs": {}},
    ))
    monkeypatch.setattr(codex_sources, "source_lines", lambda item_id: [])
    monkeypatch.setattr(codex_sources, "upgrade_use_lines", lambda item_id: [])

    rows = codex_service.get_entries()
    assert rows[0]["lines"] == []
    relations = codex_service.get_item_relations("test_material")
    assert "来源资料待补充。" in relations
    assert "不可获得" not in "".join(relations)


def test_event_only_items_are_tagged_without_claiming_event_is_open(monkeypatch):
    item = SimpleNamespace(
        item_id="moon_item", name="月蚀祭物品", type=SimpleNamespace(value="CONSUMABLE"),
        description="活动道具", tags={"event_only"},
    )
    monkeypatch.setattr(codex_service, "config", SimpleNamespace(items_config={"by_id": {"moon_item": item}}))
    row = codex_service._item_entries()[0]
    assert "活动限定物品" in row["lines"][0]
    assert "当前是否开放以游戏内活动状态为准" in row["lines"][0]


def test_exact_name_and_id_take_precedence_over_fuzzy_matches():
    entries = [
        entry("血肉结晶", aliases=["flesh_crystal"]),
        entry("结晶丹", description="需要血肉结晶", aliases=["crystal_pill"]),
    ]
    assert codex_service.search_entries("flesh_crystal", entries) == [entries[0]]
    assert codex_service.search_entries("血肉结晶", entries) == [entries[0]]


def test_fuzzy_search_keeps_ambiguous_candidates_for_disambiguation():
    entries = [entry("初级丹方", description="血肉结晶配方"), entry("护甲", description="血肉结晶锻造")]
    assert codex_service.search_entries("血肉结晶", entries) == entries


def test_exact_item_name_precedes_recipe_alias():
    item = entry("回春散", "丹药与消耗品", key="item:heal_elixir")
    recipe = entry("回春散丹方", "丹方", aliases=["回春散"], key="alchemy:heal")
    assert codex_service.search_entries("回春散", [recipe, item]) == [item]
    assert codex_service.search_entries("alchemy:heal", [recipe, item]) == [recipe]


def test_category_aliases_group_recipe_types_and_world_categories():
    entries = [entry("A", "丹方"), entry("B", "烹饪食谱"), entry("C", "锻造配方"), entry("D", "人物")]
    assert codex_service.resolve_category("配方", entries) == "配方"
    assert [row["name"] for row in codex_service.category_entries(entries, "配方")] == ["A", "B", "C"]
    assert codex_service.resolve_category("NPC", entries) == "人物"


def test_category_pagination_clamps_page_and_returns_counts():
    entries = [entry(f"材料{i}", "材料") for i in range(17)] + [entry("丹药", "丹药")]
    page, current, total = codex_service.page_entries(entries, "材料", page=3, page_size=8)
    assert [row["name"] for row in page] == ["材料16"]
    assert (current, total) == (3, 3)
    page, current, total = codex_service.page_entries(entries, "材料", page=99, page_size=8)
    assert (len(page), current, total) == (1, 3, 3)


def test_item_relations_link_back_to_manufacturing_recipe_keys(monkeypatch):
    from plugins.xiuxian_game.item import codex_sources

    product = SimpleNamespace(
        item_id="product", name="测试装备", type=SimpleNamespace(value="EQUIPMENT"),
        recipe={"materials": {"material": 2}, "gold": 10},
    )
    material = SimpleNamespace(item_id="material", name="测试材料", type=SimpleNamespace(value="MATERIAL"))
    monkeypatch.setattr(codex_service, "config", SimpleNamespace(
        items_config={"by_id": {"product": product, "material": material}},
        elixirs_config={"elixirs": {"test_formula": {
            "produce_item_id": "product", "materials": {"material": 1},
        }}},
    ))
    monkeypatch.setattr(codex_sources, "source_lines", lambda item_id: ["商店购买"])
    monkeypatch.setattr(codex_sources, "upgrade_use_lines", lambda item_id: [])

    product_lines = codex_service.get_item_relations("product")
    material_lines = codex_service.get_item_relations("material")
    assert any('text="图鉴 alchemy:test_formula"' in line for line in product_lines)
    assert any('text="图鉴 craft:product"' in line for line in product_lines)
    assert any('text="图鉴 alchemy:test_formula"' in line for line in material_lines)
    assert any('text="图鉴 craft:product"' in line for line in material_lines)


def test_long_detail_is_split_into_pages():
    item = entry("长条目", lines=[f"详情{i}" for i in range(27)])
    page, current, total = codex_service.detail_page(item, 2, page_size=12)
    assert page == [f"详情{i}" for i in range(12, 24)]
    assert (current, total) == (2, 3)


def test_craft_recipe_adds_required_flesh_crystal(monkeypatch):
    equipment = SimpleNamespace(
        item_id="test_sword", name="测试剑", type=SimpleNamespace(value="EQUIPMENT"),
        description="剑", recipe={"materials": {"iron": 2}, "gold": 30},
    )
    monkeypatch.setattr(codex_service, "config", SimpleNamespace(items_config={"by_id": {
        "test_sword": equipment,
        "iron": SimpleNamespace(name="铁矿"),
        "flesh_crystal": SimpleNamespace(name="血肉结晶"),
    }}))
    entries = codex_service._craft_entries()
    assert entries[0]["category"] == "锻造配方"
    assert any("材料：" in line and "血肉结晶" in line and "×1" in line for line in entries[0]["lines"])


def test_craft_recipe_does_not_double_add_flesh_crystal(monkeypatch):
    equipment = SimpleNamespace(
        item_id="test_sword", name="测试剑", type=SimpleNamespace(value="EQUIPMENT"),
        description="剑", recipe={"materials": {"flesh_crystal": 3}, "gold": 30},
    )
    monkeypatch.setattr(codex_service, "config", SimpleNamespace(items_config={"by_id": {
        "test_sword": equipment,
        "flesh_crystal": SimpleNamespace(name="血肉结晶"),
    }}))
    entries = codex_service._craft_entries()
    assert sum("材料：" in line and "血肉结晶" in line and "×3" in line for line in entries[0]["lines"]) == 1
