"""打工列表显示一致性测试

JobLocation.available_jobs 是建点时把 JOB_TYPES 快照进 DB 的 JSON 列，
此后常量调整（如基础报酬+50%）不会回写 DB。列表显示必须取常量而非快照，
否则玩家看到的报酬与收工结算（直接读 JOB_TYPES）不一致。
"""
import asyncio
from types import SimpleNamespace

from plugins.xiuxian_game.economy.part_time_job_service import PartTimeJobService


class _FakeJobLocationRepo:
    def __init__(self, location):
        self._location = location

    async def get_by_coordinates(self, x, y):
        return self._location


class _FakeStatsRepo:
    async def get_or_create(self, player_id):
        return SimpleNamespace(job_proficiency={})


def _make_service(location):
    return PartTimeJobService(
        player_repo=None,
        part_time_job_repo=None,
        job_location_repo=_FakeJobLocationRepo(location),
        player_job_stats_repo=_FakeStatsRepo(),
    )


def _make_player():
    return SimpleNamespace(
        id=1,
        region="大都会",
        level=10,
        get_current_coordinates=lambda: (0, 0),
    )


def test_display_reads_constants_not_db_snapshot():
    """DB 快照里的旧报酬不得出现在列表中，应显示当前常量值"""
    stale_snapshot = {
        "cashier": dict(PartTimeJobService.JOB_TYPES["cashier"], base_reward=1)
    }
    location = SimpleNamespace(
        name="测试商圈", required_level=1, available_jobs=stale_snapshot
    )

    ok, _, jobs = asyncio.run(
        _make_service(location).get_available_jobs_at_location(_make_player())
    )

    assert ok
    assert len(jobs) == 1
    assert jobs[0]["base_reward"] == PartTimeJobService.JOB_TYPES["cashier"]["base_reward"]
    assert jobs[0]["base_reward"] != 1


def test_removed_job_type_in_snapshot_is_skipped():
    """快照里存在但常量中已下线的工种应被跳过而非 KeyError"""
    snapshot = {
        "ghost_job": {"name": "已下线工种", "base_reward": 999},
        "cashier": dict(PartTimeJobService.JOB_TYPES["cashier"]),
    }
    location = SimpleNamespace(
        name="测试商圈", required_level=1, available_jobs=snapshot
    )

    ok, _, jobs = asyncio.run(
        _make_service(location).get_available_jobs_at_location(_make_player())
    )

    assert ok
    assert [j["job_type"] for j in jobs] == ["cashier"]
