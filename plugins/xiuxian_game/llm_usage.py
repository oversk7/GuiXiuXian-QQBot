"""
LLM 用量统计

记录各玩法的 DeepSeek 调用消耗（token/费用），供管理员查看与后续安排限次。
- 记录点埋在各 LLM 管道：ai_guide.call_deepseek_api / 怪谈 LLMClient / 海龟汤 _call_llm
- 玩法名与群/玩家来源通过 contextvars 在指令入口打标，深层调用与 asyncio 子任务自动继承
- 单价配置在 config.yaml 的 llm_usage.pricing（元/百万 token），未配置的模型只记 token 不算钱
"""
from contextvars import ContextVar
from datetime import datetime, timedelta

from nonebot import logger, on_command
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from .config import config
from .models.db import safe_session
from .models.llm_usage import LLMUsageLog

_usage_ctx: ContextVar[dict | None] = ContextVar("llm_usage_ctx", default=None)


def set_llm_usage_context(
    feature: str, event=None, *, group_id: str | None = None, user_id: str | None = None
) -> None:
    """在指令入口标记本次调用链的玩法与来源，供深层 LLM 记录点归因。"""
    if event is not None:
        group_id = group_id or getattr(event, "group_openid", None)
        user_id = user_id or getattr(event, "get_user_id", lambda: None)()
    _usage_ctx.set({"feature": feature, "group_id": group_id, "user_id": user_id})


async def record_llm_usage(model: str, usage: dict, *, feature: str | None = None) -> None:
    """写入一条用量日志。任何失败只记 warning，绝不影响玩法流程。"""
    ctx = _usage_ctx.get() or {}
    if not isinstance(usage, dict):
        usage = {}
    try:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        async with safe_session() as session:
            session.add(
                LLMUsageLog(
                    feature=str(feature or ctx.get("feature") or "其他")[:32],
                    model=str(model or "")[:64],
                    group_id=ctx.get("group_id"),
                    user_id=ctx.get("user_id"),
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=int(usage.get("total_tokens") or (prompt + completion)),
                    cache_hit_tokens=int(usage.get("prompt_cache_hit_tokens") or 0),
                    cache_miss_tokens=int(usage.get("prompt_cache_miss_tokens") or 0),
                )
            )
    except (SQLAlchemyError, OSError, TypeError, ValueError) as exc:
        logger.warning(f"[LLM用量] 记录失败: {exc}")


# ---------------- 费用估算与管理员查询 ----------------


def _pricing() -> dict:
    section = config.game_config.get("llm_usage", {}) or {}
    return section.get("pricing", {}) or {}


def estimate_cost(model: str, prompt: int, completion: int, hit: int, miss: int) -> float | None:
    """按单价表估算费用（元）。模型未配置单价时返回 None。"""
    price = _pricing().get(model)
    if not isinstance(price, dict):
        return None
    if hit or miss:
        input_cost = hit * float(price.get("input_cache_hit", 0)) + miss * float(
            price.get("input_cache_miss", 0)
        )
    else:
        # 老记录/无缓存字段时按全部未命中估算（偏保守）
        input_cost = prompt * float(price.get("input_cache_miss", 0))
    return (input_cost + completion * float(price.get("output", 0))) / 1_000_000


def _fmt_tokens(n: int) -> str:
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _fmt_cost(cost: float, priced: bool) -> str:
    if not priced:
        return "未配单价"
    return f"¥{cost:.2f}" if cost >= 0.1 else f"¥{cost:.3f}"


async def _window_stats(session, since: datetime | None) -> list[dict]:
    """按玩法汇总某时间窗内的调用次数、token 与估算费用。"""
    stmt = select(
        LLMUsageLog.feature,
        LLMUsageLog.model,
        func.count(LLMUsageLog.id),
        func.sum(LLMUsageLog.prompt_tokens),
        func.sum(LLMUsageLog.completion_tokens),
        func.sum(LLMUsageLog.total_tokens),
        func.sum(LLMUsageLog.cache_hit_tokens),
        func.sum(LLMUsageLog.cache_miss_tokens),
    ).group_by(LLMUsageLog.feature, LLMUsageLog.model)
    if since is not None:
        stmt = stmt.where(LLMUsageLog.created_at >= since)
    rows = (await session.execute(stmt)).all()

    merged: dict[str, dict] = {}
    for feature, model, calls, prompt, completion, total, hit, miss in rows:
        item = merged.setdefault(
            feature, {"feature": feature, "calls": 0, "tokens": 0, "cost": 0.0, "priced": True}
        )
        item["calls"] += int(calls or 0)
        item["tokens"] += int(total or 0)
        cost = estimate_cost(model, int(prompt or 0), int(completion or 0), int(hit or 0), int(miss or 0))
        if cost is None:
            item["priced"] = False
        else:
            item["cost"] += cost
    return sorted(merged.values(), key=lambda x: (-x["cost"], -x["tokens"]))


def _render_window(title: str, stats: list[dict]) -> str:
    if not stats:
        return f"{title}\n· 无调用"
    lines = [title]
    for item in stats:
        lines.append(
            f"· {item['feature']}：{item['calls']}次 | {_fmt_tokens(item['tokens'])}tok"
            f" | {_fmt_cost(item['cost'], item['priced'])}"
        )
    if len(stats) > 1:
        total_calls = sum(x["calls"] for x in stats)
        total_tokens = sum(x["tokens"] for x in stats)
        total_cost = sum(x["cost"] for x in stats)
        all_priced = all(x["priced"] for x in stats)
        lines.append(
            f"合计：{total_calls}次 | {_fmt_tokens(total_tokens)}tok | {_fmt_cost(total_cost, all_priced)}"
        )
    return "\n".join(lines)


usage_cmd = on_command(
    "AI用量", aliases={"ai用量", "AI费用", "ai费用"}, priority=5, block=True, permission=SUPERUSER
)


@usage_cmd.handle()
async def handle_usage(matcher: Matcher):
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)

    async with safe_session() as session:
        earliest = (await session.execute(select(func.min(LLMUsageLog.created_at)))).scalar()
        if earliest is None:
            await matcher.finish("📭 暂无 LLM 调用记录。")
        today_stats = await _window_stats(session, today_start)
        week_stats = await _window_stats(session, week_start)
        all_stats = await _window_stats(session, None)

    total_calls = sum(x["calls"] for x in all_stats)
    total_tokens = sum(x["tokens"] for x in all_stats)
    total_cost = sum(x["cost"] for x in all_stats)
    all_priced = all(x["priced"] for x in all_stats)

    text = (
        "🤖 AI用量统计（DeepSeek）\n"
        "━━━━━━━━━━━━━\n"
        f"{_render_window('📅 今日', today_stats)}\n"
        "━━━━━━━━━━━━━\n"
        f"{_render_window('📆 近7天', week_stats)}\n"
        "━━━━━━━━━━━━━\n"
        f"📊 累计（自 {earliest.strftime('%m-%d')} 起）：{total_calls}次"
        f" | {_fmt_tokens(total_tokens)}tok | {_fmt_cost(total_cost, all_priced)}"
    )
    await matcher.finish(text)
