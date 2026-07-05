"""LLM 用量统计纯函数测试（不触发数据库/网络）。"""

from plugins.xiuxian_game import llm_usage as lu


PRICING = {
    "deepseek-v4-pro": {"input_cache_hit": 0.026, "input_cache_miss": 3.13, "output": 6.26},
}


def _patch_pricing(monkeypatch):
    monkeypatch.setattr(lu, "_pricing", lambda: PRICING)


# ---------------- 费用估算 ----------------


def test_estimate_cost_with_cache_split(monkeypatch):
    _patch_pricing(monkeypatch)
    # 100万命中 + 100万未命中 + 100万输出
    cost = lu.estimate_cost("deepseek-v4-pro", 2_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert cost is not None
    assert abs(cost - (0.026 + 3.13 + 6.26)) < 1e-9


def test_estimate_cost_without_cache_fields_uses_miss_price(monkeypatch):
    _patch_pricing(monkeypatch)
    cost = lu.estimate_cost("deepseek-v4-pro", 1_000_000, 0, 0, 0)
    assert cost is not None
    assert abs(cost - 3.13) < 1e-9


def test_estimate_cost_unpriced_model_returns_none(monkeypatch):
    _patch_pricing(monkeypatch)
    assert lu.estimate_cost("glm-z1-flash", 1000, 1000, 0, 0) is None


# ---------------- 格式化 ----------------


def test_fmt_tokens():
    assert lu._fmt_tokens(999) == "999"
    assert lu._fmt_tokens(53_000) == "5.3万"
    assert lu._fmt_tokens(182_400_000) == "1.8亿"


def test_fmt_cost():
    assert lu._fmt_cost(5.83, True) == "¥5.83"
    assert lu._fmt_cost(0.021, True) == "¥0.021"
    assert lu._fmt_cost(1.23, False) == "未配单价"


def test_render_window_sorted_with_total():
    stats = [
        {"feature": "怪谈主线", "calls": 30, "tokens": 900_000, "cost": 4.2, "priced": True},
        {"feature": "海龟汤", "calls": 12, "tokens": 53_000, "cost": 0.21, "priced": True},
    ]
    text = lu._render_window("📅 今日", stats)
    lines = text.split("\n")
    assert lines[0] == "📅 今日"
    assert "怪谈主线" in lines[1] and "30次" in lines[1]
    assert "海龟汤" in lines[2]
    assert lines[3].startswith("合计：42次")


def test_render_window_empty():
    assert lu._render_window("📅 今日", []) == "📅 今日\n· 无调用"


# ---------------- 上下文打标 ----------------


def test_usage_context_roundtrip():
    lu.set_llm_usage_context("海龟汤", group_id="G1", user_id="U1")
    ctx = lu._usage_ctx.get()
    assert ctx == {"feature": "海龟汤", "group_id": "G1", "user_id": "U1"}


def test_usage_context_from_event_attrs():
    class FakeEvent:
        group_openid = "G2"

        def get_user_id(self):
            return "U2"

    lu.set_llm_usage_context("NPC对话", FakeEvent())
    ctx = lu._usage_ctx.get()
    assert ctx == {"feature": "NPC对话", "group_id": "G2", "user_id": "U2"}
