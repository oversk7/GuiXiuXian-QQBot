"""月蚀祭：个人进度、挑战与限时兑换。"""

import json
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..battle.integration_helper import BattleIntegrationHelper
from ..infrastructure.locking import lock_row
from ..item.vip_battle_growth_service import settle_pve_victory
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..utils import generate_progress_bar
from ..utils_markdown import cmd
from .knocker_event import KnockerEventService


STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "moon_festival_state.json"
DURATION = 7 * 86400
EXCHANGE_GRACE = 2 * 86400
DAILY_ACTIONS = 2
ACTION_REWARD = 20
TITLE = "守月人"
ACTIONS = {"sign": "签到", "cultivate": "修炼", "explore": "探索", "cook": "烹饪"}


@dataclass(frozen=True)
class Chapter:
    name: str
    threshold: int
    enemy: str
    opening: str
    ending: str


CHAPTERS = (
    Chapter("缺月", 40, "窥月影", "月华照亮月轮的第一道裂纹。窥月影从裂处爬出，挡住了你的手。", "月影散了。你将月华按入缺口，月轮稳住了一分。"),
    Chapter("藏月", 80, "吞辉客", "月轮的缺口看得更清了。吞辉客贴着你的脚步，无声地跟来。", "脚边的黑影终于退去。月华沿裂纹流淌，缺口又合上一段。"),
    Chapter("归月", 120, "蚀月之影", "月蚀将至，最后一道裂口前，蚀月之影等着你。", "月影退尽，月轮重新合拢。月光照见一扇扇未熄灯的窗。"),
)

# id -> (显示名, 月华价格, 本期个人限购)
SHOP = {
    "moon_festival_cake": ("团圆月饼", 10, 3),
    "moon_festival_dew": ("桂月露", 20, 2),
    "moon_festival_talisman": ("望月符", 15, 2),
}


class MoonFestivalService:
    @staticmethod
    def state() -> dict:
        if not STATE_FILE.exists():
            return {}
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))

    @staticmethod
    def _save_state(state: dict) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, STATE_FILE)

    @classmethod
    def start(cls) -> str:
        if cls.active():
            return "月蚀祭已经开启"
        now = time.time()
        cls._save_state({"run": str(time.time_ns()), "start": now, "end": now + DURATION})
        return "月蚀祭已开启，持续7天；结束后还可兑换2天。发送【月蚀祭】查看。"

    @classmethod
    def stop(cls) -> str:
        state = cls.state()
        if not state or state.get("stopped"):
            return "月蚀祭未开启"
        state["stopped"] = True
        cls._save_state(state)
        return "月蚀祭已关闭"

    @classmethod
    def active(cls, now: float | None = None) -> bool:
        state = cls.state()
        current = time.time() if now is None else now
        return bool(state and not state.get("stopped") and state["start"] <= current < state["end"])

    @classmethod
    def exchange_open(cls, now: float | None = None) -> bool:
        state = cls.state()
        current = time.time() if now is None else now
        return bool(state and not state.get("stopped") and state["start"] <= current < state["end"] + EXCHANGE_GRACE)

    @classmethod
    def _progress(cls, player: Player) -> dict:
        state = cls.state()
        saved = (player.extra_attrs or {}).get("moon_festival", {})
        if not state or saved.get("run") != state.get("run"):
            return {"run": state.get("run"), "total": 0, "balance": 0, "cleared": 0, "days": {}, "bought": {}}
        return deepcopy(saved)

    @staticmethod
    def _store(player: Player, data: dict) -> None:
        player.extra_attrs = {**(player.extra_attrs or {}), "moon_festival": data}

    @classmethod
    def record_action(cls, player: Player, action: str) -> str:
        """成功的日常动作在同笔事务内调用；活动期间调用者须先锁定玩家。"""
        if action not in ACTIONS or not cls.active():
            return ""
        data = cls._progress(player)
        today = datetime.now().date().isoformat()
        done = list(data.get("days", {}).get(today, []))
        if action in done or len(done) >= DAILY_ACTIONS:
            return ""
        done.append(action)
        data.setdefault("days", {})[today] = done
        data["total"] = data.get("total", 0) + ACTION_REWARD
        data["balance"] = data.get("balance", 0) + ACTION_REWARD
        cls._store(player, data)
        return f"月蚀祭：{ACTIONS[action]}获得月华+{ACTION_REWARD}（今日{len(done)}/{DAILY_ACTIONS}）"

    @classmethod
    def status(cls, player: Player) -> str:
        state = cls.state()
        if not state or state.get("stopped") or time.time() >= state["end"] + EXCHANGE_GRACE:
            return f"# 🌘 月蚀祭\n> 活动当前未开放。\n***\n{cmd('帮助')}"

        data = cls._progress(player)
        total = data.get("total", 0)
        cleared = data.get("cleared", 0)
        active = cls.active()
        deadline = state["end"] if active else state["end"] + EXCHANGE_GRACE
        title = "# 🌕 月蚀祭 · 月轮已圆" if active and cleared == len(CHAPTERS) else (
            "# 🌘 月蚀祭 · 守月" if active else "# 🌕 月蚀祭 · 兑换期"
        )
        lines = [
            title,
            "> 今夜月光照见归途。" if active and cleared == len(CHAPTERS) else (
                "> 月华落进裂纹，月轮正等你补全。" if active else "> 月影已退，留下的月华仍可兑换。"
            ),
            f"⏳ {'活动' if active else '兑换'}至 **{datetime.fromtimestamp(deadline):%m月%d日 %H:%M}**",
            "***",
            f"🌙 累计月华 **{total}** · 可用 **{data.get('balance', 0)}**",
            f"月轮 {generate_progress_bar(total, CHAPTERS[-1].threshold)}",
        ]

        if active:
            done = data.get("days", {}).get(datetime.now().date().isoformat(), [])
            lines.extend(["***", f"## 今日采月 · {len(done)}/{DAILY_ACTIONS}"])
            if done:
                lines.append("已完成 " + " · ".join(f"✅ {ACTIONS[action]}" for action in done if action in ACTIONS))
            if len(done) < DAILY_ACTIONS:
                choices = [cmd(label) for action, label in ACTIONS.items() if action not in done]
                lines.append("可选 " + " | ".join(choices))
            else:
                lines.append("今日月华已收齐")

        lines.extend(["***", f"## 修补月轮 · {cleared}/{len(CHAPTERS)}"])
        for index, chapter in enumerate(CHAPTERS):
            if index < cleared:
                lines.append(f"✅ {chapter.name} · 已修补")
            elif not active:
                lines.append(f"◌ {chapter.name} · 未完成")
            elif index > cleared:
                lines.append(f"🔒 {chapter.name} · 等待前一关")
            elif total >= chapter.threshold:
                lines.append(f"⚔️ {chapter.name} · 可挑战")
            else:
                lines.append(f"◌ {chapter.name} · 月华 {total}/{chapter.threshold}")

        actions = [cmd("月华商店"), cmd("月蚀祭帮助")]
        if active and cleared < len(CHAPTERS) and total >= CHAPTERS[cleared].threshold:
            actions.insert(0, cmd("守月"))
        lines.extend(["***", " | ".join(actions)])
        return "\n".join(lines)

    @classmethod
    async def lock_for_action(cls, session, player: Player) -> Player:
        """在日常动作修改玩家前锁定记录，序列化月华进度。"""
        return await cls._lock_player(session, player) if cls.active() else player

    @staticmethod
    async def _lock_player(session, player: Player) -> Player:
        return await lock_row(session, Player, player.id)

    @classmethod
    async def challenge(cls, session, player: Player) -> str:
        if not cls.active():
            return "月蚀祭当前未开放"
        player = await cls._lock_player(session, player)
        data = cls._progress(player)
        chapter_index = data.get("cleared", 0)
        if chapter_index >= len(CHAPTERS):
            return "月轮已经修补完成。去【月华商店】看看吧。"
        chapter = CHAPTERS[chapter_index]
        if data.get("total", 0) < chapter.threshold:
            return f"还需累计月华 {chapter.threshold - data.get('total', 0)}，才能挑战「{chapter.name}」"
        if player.hp <= 0:
            return "生命值不足，恢复后再来守月。"

        effective = await player.get_effective_attributes(session)
        hp = max(1, int(effective.get("max_hp", player.max_hp)))
        attack = max(1, int(effective.get("attack", player.attack)))
        defense = max(0, int(effective.get("defense", player.defense)))
        agility = max(1, int(effective.get("agility", player.agility)))
        enemy = {"hp": max(8, hp // 4), "attack": max(1, attack // 5),
                 "defense": defense // 4, "agility": max(1, agility // 2)}
        victory, _, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
            player, enemy, chapter.enemy, session, max_rounds=12
        )
        player.hp = max(0, min(hp, player.hp - damage_taken))
        if not victory:
            return f"{chapter.opening}\n月影未散，月轮还等着你。剩余生命 {player.hp}，恢复状态后可再次【守月】，进度不会损失。"
        reward_item = ("moon_festival_cake", "moon_festival_dew", "moon_festival_keepsake")[chapter_index]
        try:
            await ItemInstance.add_item(session, player.id, reward_item, 1)
        except ValueError as error:
            return f"挑战胜利，但奖励发放失败（{error}）。整理背包后再次【守月】，进度不受影响。"
        data["cleared"] = chapter_index + 1
        if chapter_index == 0:
            reward = "获得团圆月饼×1"
        elif chapter_index == 1:
            reward = "获得桂月露×1"
        else:
            KnockerEventService.grant_title(player, TITLE)
            reward = f"获得月轮残片×1、称号「{TITLE}」（使用【切换称号 守月人】佩戴）"
        cls._store(player, data)
        growth = await settle_pve_victory(session, player, post_effects)
        details = "\n" + "\n".join(growth) if growth else ""
        return f"{chapter.opening}\n{chapter.ending}\n守月成功（{chapter_index + 1}/3）！{reward}{details}"

    @classmethod
    def shop(cls, player: Player) -> str:
        if not cls.exchange_open():
            return "月华商店当前未开放"
        data = cls._progress(player)
        lines = [f"月华商店 · 可用月华 {data.get('balance', 0)}"]
        for item_id, (name, price, limit) in SHOP.items():
            lines.append(f"{name}：{price}月华，余 {max(0, limit - data.get('bought', {}).get(item_id, 0))} 件")
        lines.append("【月华商店 兑换 物品名 [数量]】")
        return "\n".join(lines)

    @classmethod
    async def buy(cls, session, player: Player, name: str, quantity: int) -> str:
        if not cls.exchange_open():
            return "月华商店当前未开放"
        if quantity <= 0 or quantity > 99:
            return "兑换数量须在1至99之间"
        product = next(((key, value) for key, value in SHOP.items() if value[0] == name), None)
        if product is None:
            return "没有这件商品，发送【月华商店】查看列表"
        player = await cls._lock_player(session, player)
        data = cls._progress(player)
        item_id, (_, price, limit) = product
        if data.get("bought", {}).get(item_id, 0) + quantity > limit:
            return "超过本期个人限购数量"
        if data.get("balance", 0) < price * quantity:
            return "可用月华不足"
        try:
            await ItemInstance.add_item(session, player.id, item_id, quantity)
        except ValueError as error:
            return f"兑换失败：{error}"
        data["balance"] -= price * quantity
        data.setdefault("bought", {})[item_id] = data["bought"].get(item_id, 0) + quantity
        cls._store(player, data)
        return f"兑换成功：{name}×{quantity}，剩余月华 {data['balance']}"
