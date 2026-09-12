"""滑动窗口边界、缓存清理与独立业务限制。"""

from collections import defaultdict, deque

import pytest

from plugins.xiuxian_game.rate_limiter import SlidingWindowRateLimiter
from plugins.xiuxian_game import utils


def test_window_boundary_and_rejection_do_not_extend_window():
    now = [0.0]
    limiter = SlidingWindowRateLimiter(lambda: now[0])
    assert limiter.allow("player", 1, 5)
    now[0] = 4.9
    assert not limiter.allow("player", 1, 5)
    now[0] = 5.0
    assert limiter.allow("player", 1, 5)


def test_rate_limiter_amortizes_stale_key_cleanup():
    now = [0.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])
    for index in range(255):
        assert limiter.allow(f"old-{index}", 1, 5)
    now[0] = 6
    assert limiter.allow("current", 1, 5)
    assert len(limiter) == 1
    assert not limiter.allow("current", 1, 5)


def test_work_and_ai_limits_are_independent(monkeypatch):
    monkeypatch.setattr(utils.time, "monotonic", lambda: 100.0)
    limiter = utils.RateLimiter()
    limiter.register_action("start_work", utils.RateLimitConfig(10, 3600, 60))
    limiter.register_action("liuyao", utils.RateLimitConfig(10, 300, 30))
    limiter.record_request("player", "start_work")
    assert not limiter.check_rate_limit("player", "start_work")[0]
    assert limiter.check_rate_limit("player", "liuyao")[0]
    limiter.record_request("player", "liuyao")
    assert not limiter.check_rate_limit("player", "liuyao")[0]
    assert limiter.check_rate_limit("other", "start_work")[0]


@pytest.mark.parametrize("action,limit,window", [
    ("fortune", 3, 3600),
    ("daily_api", 10, 600),
    ("today_meal", 5, 300),
])
def test_entertainment_business_quotas_remain_active(monkeypatch, action, limit, window):
    now = [0.0]
    monkeypatch.setattr(utils.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(utils.rate_limiter, "_request_history", defaultdict(deque))
    monkeypatch.setattr(utils.rate_limiter, "_last_request_time", {})
    for _ in range(limit):
        assert utils.check_action_limit("player", action)[0]
        utils.record_action("player", action)
        now[0] += 1.0

    assert not utils.check_action_limit("player", action)[0]
    assert utils.check_action_limit("player", "start_work")[0]
    now[0] = window + 0.1
    assert utils.check_action_limit("player", action)[0]
