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
    ending: str


CHAPTERS = (
    Chapter("缺月", 40, "窥月影", "窥月影散去，第一道裂纹收住了月光。"),
    Chapter("藏月", 80, "吞辉客", "脚边黑影退去，月华将缺口又合上一段。"),
    Chapter("归月", 120, "蚀月之影", "蚀月之影散尽，月轮合拢，照见窗前未熄的灯。"),
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
            f"🌙 可用月华 **{data.get('balance', 0)}** · 累计 **{total}**",
            f"守月 {generate_progress_bar(cleared, len(CHAPTERS))} {cleared}/{len(CHAPTERS)}",
        ]

        if active:
            done = data.get("days", {}).get(datetime.now().date().isoformat(), [])
            lines.extend(["***", f"## 今日采月 · {len(done)}/{DAILY_ACTIONS}"])
            if len(done) < DAILY_ACTIONS:
                lines.append(f"> 每日任选两项，各得 {ACTION_REWARD} 月华。")
                choices = [f"✓ {label}" if action in done else cmd(label) for action, label in ACTIONS.items()]
                lines.append(" · ".join(choices))
            else:
                lines.append(f"✓ 今日月华已收齐 · +{DAILY_ACTIONS * ACTION_REWARD}")

        lines.extend(["***", "## 守月三关"])
        for index, chapter in enumerate(CHAPTERS):
            if index < cleared:
                lines.append(f"✅ {chapter.name} · 已修补")
            elif not active:
                lines.append(f"◌ {chapter.name} · 未完成")
            elif index > cleared:
                lines.append(f"🔒 {chapter.name} · 前关通关 / {chapter.threshold} 月华")
            elif total >= chapter.threshold:
                lines.append(f"⚔️ {chapter.name} · 可挑战 · {cmd('前往守月', '守月')}")
            else:
                lines.append(f"◌ {chapter.name} · 还差 {chapter.threshold - total} 月华")
        if cleared == len(CHAPTERS):
            lines.append(f"🏅 守月人 · {cmd('佩戴称号', '切换称号 守月人')}")
        elif active:
            lines.append("> 通关得称号「守月人」· 兑换不影响解锁。")

        actions = [cmd("月华商店"), cmd("玩法", "月蚀祭帮助")]
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
            return f"# 🌕 月轮已圆\n> 月轮已经修补完成。\n***\n{cmd('月华商店')} | {cmd('返回月蚀祭', '月蚀祭')}"
        chapter = CHAPTERS[chapter_index]
        if data.get("total", 0) < chapter.threshold:
            return f"# 🌘 守月 · {chapter.name}\n> 还差 {chapter.threshold - data.get('total', 0)} 月华解锁。\n***\n{cmd('前往采月', '月蚀祭')}"
        if player.hp <= 0:
            return f"# 🌘 暂歇片刻\n> 生命值不足，恢复后再来守月。\n***\n{cmd('背包')} | {cmd('返回月蚀祭', '月蚀祭')}"

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
            return (
                f"# 🌘 守月未成 · {chapter.name}\n> 月影未散，且待重来。\n***\n"
                f"剩余生命 **{player.hp}**\n进度不会损失，恢复后可重试。\n***\n"
                f"{cmd('背包')} | {cmd('再次守月', '守月')} | {cmd('月蚀祭')}"
            )
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
            reward = f"获得月轮残片×1\n🏅 称号「{TITLE}」 · {cmd('佩戴', '切换称号 守月人')}"
        cls._store(player, data)
        growth = await settle_pve_victory(session, player, post_effects)
        details = "\n" + "\n".join(growth) if growth else ""
        navigation = [cmd("月蚀祭"), cmd("月华商店")]
        if chapter_index + 1 < len(CHAPTERS) and data.get("total", 0) >= CHAPTERS[chapter_index + 1].threshold:
            navigation.insert(0, cmd("继续守月", "守月"))
        return (
            f"# 🌕 守月成功（{chapter_index + 1}/3）\n> {chapter.ending}\n***\n"
            f"🎁 {reward}{details}\n***\n" + " | ".join(navigation)
        )

    @classmethod
    def shop(cls, player: Player) -> str:
        if not cls.exchange_open():
            return "月华商店当前未开放"
        data = cls._progress(player)
        deadline = cls.state()["end"] + EXCHANGE_GRACE
        lines = [
            "# 🌙 月华商店",
            f"可用月华 **{data.get('balance', 0)}**",
            f"> 兑换至 {datetime.fromtimestamp(deadline):%m月%d日 %H:%M} · 本期个人限兑",
        ]
        effects = {
            "moon_festival_cake": "生命恢复 15%",
            "moon_festival_dew": "生命、理智恢复 30%",
            "moon_festival_talisman": "命中 +10 · 暴击 +5 · 持续30分钟",
        }
        for item_id, (name, price, limit) in SHOP.items():
            remaining = max(0, limit - data.get('bought', {}).get(item_id, 0))
            action = cmd("兑换", f"月华商店 兑换 {name}") if remaining else "已兑完"
            lines.extend([
                "***",
                f"**{name}** · {price} 月华",
                f"> {effects[item_id]}",
                f"余 {remaining}/{limit} · {action}",
            ])
        lines.extend(["***", f"{cmd('返回月蚀祭', '月蚀祭')} | {cmd('玩法', '月蚀祭帮助')}"])
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
        return (
            f"# 🎁 兑换成功\n**{name} ×{quantity}**\n"
            f"消耗月华 {price * quantity} · 剩余 **{data['balance']}**\n***\n"
            f"{cmd('继续兑换', '月华商店')} | {cmd('月蚀祭')}"
        )
