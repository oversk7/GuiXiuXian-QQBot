import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .age import AgeManager
from .event import Event, EventManager, WeightedEvent
from .property import Property, Summary
from .talent import Talent, TalentManager

logger = logging.getLogger(__name__)

data_path = Path(__file__).parent / "resources" / "data"

# ─── 模块级缓存：启动时加载一次，后续复用 ────────────────
_cache: dict = {}


def _ensure_cache():
    """首次调用时从磁盘加载并解析所有游戏数据，之后从内存复用"""
    if _cache:
        return

    logger.info("人生重开: 首次加载游戏数据...")

    # ages: {age_int: [WeightedEvent, ...]}
    age_raw = json.loads((data_path / "age.json").read_text(encoding="utf8"))
    _cache["ages"] = {
        int(k): [WeightedEvent(s) for s in v.get("event", [])]
        for k, v in age_raw.items()
    }

    # events: {event_id: Event}
    event_raw = json.loads((data_path / "events.json").read_text(encoding="utf8"))
    _cache["events"] = {int(k): Event(v) for k, v in event_raw.items()}

    # talents: {grade: [Talent, ...]}
    talent_raw = json.loads((data_path / "talents.json").read_text(encoding="utf8"))
    talent_list = [Talent(d) for d in talent_raw.values()]
    _cache["talents"] = {
        i: [t for t in talent_list if t.grade == i] for i in range(4)
    }

    logger.info(
        f"人生重开: 数据加载完成 "
        f"(ages={len(_cache['ages'])}, events={len(_cache['events'])}, "
        f"talents={sum(len(v) for v in _cache['talents'].values())})"
    )


@dataclass
class PerAgeProperty:
    AGE: int
    CHR: int
    INT: int
    STR: int
    MNY: int
    SPR: int

    def __str__(self) -> str:
        return (
            f"【{self.AGE}岁/颜{self.CHR}智{self.INT}"
            f"体{self.STR}钱{self.MNY}乐{self.SPR}】"
        )


@dataclass
class PerAgeResult:
    property: PerAgeProperty
    event_log: list[str]
    talent_log: list[str]

    def __str__(self) -> str:
        return (
            f"{self.property}\n"
            + "\n".join(self.event_log)
            + "\n".join(self.talent_log)
        )


class Life:
    def __init__(self):
        self.property = Property()
        self.age = AgeManager(self.property)
        self.event = EventManager(self.property)
        self.talent = TalentManager(self.property)

    def load(self):
        _ensure_cache()
        self.age.ages = _cache["ages"]        # 只读引用，无需拷贝
        self.event.events = _cache["events"]  # 只读引用
        self.talent.talent_dict = _cache["talents"]  # 只读引用

    def alive(self) -> bool:
        return self.property.LIF > 0

    def get_property(self) -> PerAgeProperty:
        return PerAgeProperty(
            self.property.AGE,
            self.property.CHR,
            self.property.INT,
            self.property.STR,
            self.property.MNY,
            self.property.SPR,
        )

    def run(self) -> Iterator[PerAgeResult]:
        while self.alive():
            self.age.grow()
            talent_log = self.talent.update_talent()
            event_log = self.event.run_events(self.age.get_events())
            yield PerAgeResult(
                self.get_property(),
                list(event_log),
                list(talent_log),
            )

    def rand_talents(self, num: int) -> list[Talent]:
        return list(self.talent.rand_talents(num))

    def set_talents(self, talents: list[Talent]):
        for t in talents:
            self.talent.add_talent(t)
        self.talent.update_talent_prop()

    def apply_property(self, effect: dict[str, int]):
        self.property.apply(effect)

    def total_property(self) -> int:
        return self.property.total

    def gen_summary(self) -> Summary:
        return self.property.gen_summary()
