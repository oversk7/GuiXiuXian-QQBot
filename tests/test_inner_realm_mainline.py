"""里界·荔湾鬼镇主线可通关性回归测试。

玩家反馈"荔湾剧情走不通"后补充：用受控骰子完整走一遍主线，
确保 关键道具 → 旅馆 → 宵夜 → 一号房 → 厨房密室 → 黎明结算 全链路畅通。
不连接数据库：直接构造 ORM 对象 + FakeUow，发奖函数打桩记录。
"""

import asyncio
import json

import pytest

from plugins.xiuxian_game.inner_realm.service import InnerRealmService
from plugins.xiuxian_game.models.inner_realm import InnerRealmSession
from plugins.xiuxian_game.models.player import Player


REALM = "liwan_ghost_town"


class _FakeSession:
    def add(self, obj):
        pass


class _FakeUow:
    def __init__(self):
        self.session = _FakeSession()

    async def commit(self):
        pass


def _make_player():
    player = Player(id="test_liwan", level=60, gold=0)
    player.inner_realm = REALM
    player.inner_realm_clears = None
    return player


def _make_session():
    """与 enter_realm 创建的会话保持一致的初始状态"""
    return InnerRealmSession(
        player_id="test_liwan",
        realm_name=REALM,
        killed_count=0,
        saved_count=0,
        sanity=100,
        clue_collected='[]',
        current_scene="town_entrance_dusk",
        visited_scenes='["town_entrance_dusk"]',
        inventory='{}',
        is_first_clear=0,
        move_count=0,
        is_settled=0,
        state=json.dumps({
            "scene_states": {},
            "npc_states": {},
            "events_triggered": [],
            "phase": "dusk",
            "pending_rewards": {"items": [], "gold": 0},
            "is_first_playthrough": True,
        }, ensure_ascii=False),
    )


@pytest.fixture
def env(monkeypatch):
    """禁用冷却、骰子可控、发奖打桩"""
    monkeypatch.setattr(
        InnerRealmService, "check_action_cooldown",
        lambda self, session, action: (True, 0),
    )

    dice_queue = []

    def fake_randint(a, b):
        if dice_queue:
            return dice_queue.pop(0)
        return 6  # 默认全 6（大成功）

    monkeypatch.setattr(
        "plugins.xiuxian_game.inner_realm.service.random.randint", fake_randint
    )

    delivered = []

    async def fake_add_item(session, player_id, template_id, quantity=1, durability=None):
        delivered.append((template_id, quantity))
        return True

    from plugins.xiuxian_game.models.inventory import ItemInstance
    monkeypatch.setattr(ItemInstance, "add_item", staticmethod(fake_add_item))

    service = InnerRealmService(_FakeUow())
    return service, _make_player(), _make_session(), dice_queue, delivered


def _inv(session):
    return json.loads(session.inventory) if session.inventory else {}


def _state(session):
    return json.loads(session.state) if session.state else {}


def test_mainline_full_clear(env):
    """主线全程：针线引诱得房卡 → 旅馆 → 宵夜 → 一号房 → 喂牙齿 → 黎明自动结算"""
    service, player, session, dice_queue, delivered = env

    async def run():
        # 黄昏：镇口 → 小区楼下 → 家中
        ok, msg = await service.move_to_scene(player, session, "小区楼下")
        assert ok, msg
        ok, msg = await service.move_to_scene(player, session, "家中")
        assert ok, msg

        # 搜刮家中（全6大成功）→ 针线
        ok, msg = await service.perform_search(player, session)
        assert ok, msg
        assert _inv(session).get("needle_thread", 0) >= 1, msg

        # 卧室 → 楼道
        ok, msg = await service.move_to_scene(player, session, "卧室")
        assert ok, msg
        ok, msg = await service.move_to_scene(player, session, "楼道")
        assert ok, msg

        # 使用针线：引诱厂服男 → 必得四号房卡 + 雨衣男死亡 + 线索2
        ok, msg = await service.use_item(player, session, "针线")
        assert ok, msg
        assert _inv(session).get("room_card_4", 0) >= 1, msg
        assert _state(session)["npc_states"].get("raincoat_man", {}).get("alive") is False
        assert "clue_2" in json.loads(session.clue_collected)

        # 持房卡进旅馆（第5步，入夜）→ 四号房
        ok, msg = await service.move_to_scene(player, session, "旅馆大厅")
        assert ok, msg
        assert not session.is_settled, "持房卡进旅馆不应触发死亡"
        ok, msg = await service.move_to_scene(player, session, "四号房")
        assert ok, msg

        # 观察四号房 → 自动进入宵夜，蛋糕难题给出选项
        msg = await service.observe_scene(player, session)
        assert session.current_scene == "lobby_midnight", msg
        assert _state(session).get("pending_event"), "宵夜事件应给出待选择项"

        # 选择坐最外侧 → 自动进入一号房
        ok, msg = await service.resolve_special_event(player, session, "坐在桌子最外侧")
        assert ok, msg
        assert session.current_scene == "room_1", msg

        # 搜刮一号房 → 牙齿 + 日记
        ok, msg = await service.perform_search(player, session)
        assert ok, msg
        assert _inv(session).get("teeth_key_item", 0) >= 1, msg

        # 厨房密室 → 使用牙齿 → 喂食事件给出选项
        ok, msg = await service.move_to_scene(player, session, "厨房密室")
        assert ok, msg
        ok, msg = await service.use_item(player, session, "牙齿")
        assert ok, msg
        pending = _state(session).get("pending_event")
        assert pending, "喂牙齿事件必须给出选择项（主线阻断点）"
        labels = [c.get("label") for c in pending["choices"]]
        assert "等外面安静后再喂" in labels, labels

        # 选择等待 → 腐肉入账 → 黎明 → 自动结算
        ok, msg = await service.resolve_special_event(player, session, "等外面安静后再喂")
        assert ok, msg
        assert session.current_scene == "town_entrance_dawn", msg
        assert session.is_settled, "到达黎明应自动结算"
        assert player.inner_realm is None
        assert "黎明幸存者" in msg, msg
        assert any(item_id == "freezer_woman_flesh" for item_id, _ in delivered), \
            f"腐肉应随结算发放: {delivered}"
        clears = json.loads(player.inner_realm_clears)
        assert clears[REALM]["cleared"] is True, "首通应写入玩家全局记录"
        assert player.gold > 0, "结算应发放金币"

    asyncio.run(run())


def test_search_failure_is_retryable(env):
    """搜刮失败不锁场景：一号房失败后可重搜拿到牙齿（原42%概率永久死锁）"""
    service, player, session, dice_queue, delivered = env

    async def run():
        session.current_scene = "home"
        # 第一次：1+1 大失败 → 不应标记已搜刮
        dice_queue.extend([1, 1])
        ok, msg = await service.perform_search(player, session)
        assert ok, msg
        assert not _state(session)["scene_states"].get("home", {}).get("searched", False)

        # 第二次：全6 → 拿到针线
        ok, msg = await service.perform_search(player, session)
        assert ok, msg
        assert _inv(session).get("needle_thread", 0) >= 1, msg
        assert _state(session)["scene_states"]["home"]["searched"] is True

    asyncio.run(run())


def test_key_item_not_wasted_in_wrong_scene(env):
    """在无对应事件的场景使用针线：不消耗、给出提示"""
    service, player, session, dice_queue, delivered = env

    async def run():
        session.current_scene = "home"
        session.inventory = json.dumps({"needle_thread": 1})
        ok, msg = await service.use_item(player, session, "针线")
        assert not ok, msg
        assert _inv(session).get("needle_thread", 0) == 1, "道具不应被消耗"

    asyncio.run(run())


def test_early_leave_no_first_clear_bonus(env):
    """中途【返回】= 中途撤离结局：×1.0、无首通奖励、不标记通关（原漏洞按黎明幸存者发首通）"""
    from plugins.xiuxian_game.inner_realm.config import InnerRealmConfig

    service, player, session, dice_queue, delivered = env

    async def run():
        session.current_scene = "home"
        realm_config = InnerRealmConfig.get_realm_config(REALM)
        ending = await service.settle_ending(player, session, realm_config)
        assert "中途撤离" in ending["display_name"], ending
        assert session.is_settled
        assert player.inner_realm is None
        clears = json.loads(player.inner_realm_clears) if player.inner_realm_clears else {}
        assert not clears.get(REALM, {}).get("cleared", False), "中途撤离不应标记通关"
        assert player.gold == 0, "无探索所得时不应凭空发钱"

    asyncio.run(run())


def _walk_to_corridor(service, player, session):
    """走完前半程，把玩家送到旅馆走廊"""
    import asyncio as _a

    async def run():
        await service.move_to_scene(player, session, "小区楼下")
        await service.move_to_scene(player, session, "家中")
        await service.perform_search(player, session)
        await service.move_to_scene(player, session, "卧室")
        await service.move_to_scene(player, session, "楼道")
        await service.use_item(player, session, "针线")
        await service.move_to_scene(player, session, "旅馆大厅")
        await service.move_to_scene(player, session, "四号房")
        await service.move_to_scene(player, session, "旅馆走廊")

    _a.run(run())
    assert session.current_scene == "hotel_corridor"


def test_corridor_can_advance(env):
    """走廊不应是死胡同：在走廊【观察】应能触发宵夜，推进到大厅·宵夜"""
    service, player, session, dice_queue, delivered = env
    _walk_to_corridor(service, player, session)

    async def run():
        obs = await service.observe_scene(player, session)
        # 修复后：走廊观察可触发宵夜，进入 lobby_midnight 并给出蛋糕难题选项
        assert session.current_scene == "lobby_midnight", \
            f"在走廊观察应能推进到宵夜，却仍停在 {session.current_scene}"
        assert _state(session).get("pending_event"), "宵夜应给出待选择项"

    asyncio.run(run())


