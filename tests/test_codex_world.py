from __future__ import annotations

import pytest

from plugins.xiuxian_game.item import codex_world


def test_entries_follow_contract_and_have_stable_unique_keys():
    entries = codex_world.get_entries()
    assert entries
    assert len({entry["key"] for entry in entries}) == len(entries)

    for entry in entries:
        assert set(entry) == {"key", "name", "category", "description", "aliases", "lines"}
        assert all(isinstance(entry[field], str) for field in ("key", "name", "category", "description"))
        assert isinstance(entry["aliases"], list)
        assert isinstance(entry["lines"], list)

    categories = {entry["category"] for entry in entries}
    assert {"地点", "人物", "首领", "套装", "词缀", "宠物", "守护兽"} <= categories


def test_public_entries_omit_ai_personality_and_story_material():
    entries = codex_world.get_entries()
    rendered = "\n".join(
        [entry["description"] for entry in entries]
        + [line for entry in entries for line in entry["lines"]]
    )
    assert "宠物人设" not in rendered
    assert "behavioral_rules" not in rendered
    assert "background" not in rendered
    assert "化形为" not in rendered


def test_affixes_show_configured_ranges_without_unresolved_templates():
    entries = {entry["key"]: entry for entry in codex_world.get_entries()}
    fear = entries["affix:fear_strike"]
    assert any("蓝色" in line and "5～8%概率使敌人恐惧1回合" in line for line in fear["lines"])
    assert any("橙色" in line and "12～15%" in line and "恐惧1～2回合" in line for line in fear["lines"])
    assert all("{" not in line and "}" not in line for line in fear["lines"])

    pierce = entries["affix:defense_pierce"]
    assert any("蓝色" in line and "15～20%" in line and "防御" in line for line in pierce["lines"])
    assert any("橙色" in line and "2～3回合" in line for line in pierce["lines"])


def test_public_npcs_and_guild_boss_pools_are_included_without_lore_text():
    entries = codex_world.get_entries()
    by_key = {entry["key"]: entry for entry in entries}
    assert by_key["npc:临安:月老"]["category"] == "人物"
    assert by_key["npc:station:上京"]["name"] == "驿丞·京畿总驿"
    assert by_key["npc:intel:楼兰"]["name"] == "情报贩子·丝路讯"
    assert "guild_boss:纸新娘" in by_key
    assert "guild_boss:黑山羊之裔" in by_key
    all_text = "\n".join(entry["description"] + "\n" + "\n".join(entry["lines"]) for entry in entries)
    assert "纸扎铺的老师傅" not in all_text
    assert "林子里所有的兽" not in all_text


def test_guardian_entries_do_not_claim_an_unverified_daily_feed_currency():
    entries = codex_world.get_entries()
    guardian = next(entry for entry in entries if entry["key"] == "guardian:guard_dog")
    assert any("拦截率：30%" == line for line in guardian["lines"])
    assert all("喂养消耗" not in line for line in guardian["lines"])


def test_set_and_guardian_items_link_to_item_codex():
    entries = codex_world.get_entries()
    linked_lines = "\n".join(
        line for entry in entries for line in entry["lines"]
    )
    assert 'text="图鉴 item:' in linked_lines
    assert 'show="' in linked_lines


def test_dungeon_entry_uses_generated_range_cost_and_materials_without_fixed_monsters():
    entry = codex_world.dungeon_entry(10)
    assert entry["key"] == "dungeon:10"
    assert entry["name"] == "10层诡域"
    assert entry["category"] == "地点"
    assert any(line == "诡异等级范围：48-52" for line in entry["lines"])
    assert any(line == "理智消耗：1" for line in entry["lines"])
    material_lines = [line for line in entry["lines"] if line.startswith(("基础材料：", "商人材料："))]
    assert any(line.startswith('基础材料：') for line in material_lines)
    assert any(line.startswith('商人材料：') for line in material_lines)
    assert all('text="图鉴 item:' in line for line in material_lines)
    assert not any("怪物属性" in line or line.startswith("怪物：") for line in entry["lines"])


def test_dungeon_entry_supports_depth_beyond_pre_generated_levels():
    entry = codex_world.dungeon_entry(10001)
    assert entry["key"] == "dungeon:10001"
    assert "诡异等级范围：50003-50007" in entry["lines"]
    assert "理智消耗：1000" in entry["lines"]


@pytest.mark.parametrize("depth", [0, -1, 1.5, True, "10"])
def test_dungeon_entry_rejects_invalid_depth(depth):
    with pytest.raises(ValueError):
        codex_world.dungeon_entry(depth)
