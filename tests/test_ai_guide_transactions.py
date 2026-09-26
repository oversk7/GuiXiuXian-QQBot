"""AI 问答的玩家事务须在等待网络与发送消息之前结束。"""
import asyncio
import importlib
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from nonebot.exception import FinishedException
from sqlalchemy import String, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


ROOT = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game"
PACKAGE = "ai_guide_transaction_test"


def _module(name, **members):
    module = ModuleType(name)
    module.__dict__.update(members)
    return module


@pytest.fixture(scope="module")
def guide_modules():
    package = _module(PACKAGE)
    package.__path__ = [str(ROOT)]
    models = _module(f"{PACKAGE}.models")
    models.__path__ = [str(ROOT / "models")]
    platform = _module(f"{PACKAGE}.platform_utils", get_unified_player=AsyncMock())
    stubs = {
        PACKAGE: package,
        models.__name__: models,
        f"{PACKAGE}.models.player": _module(f"{PACKAGE}.models.player", Player=type("Player", (), {})),
        f"{PACKAGE}.models.story_session": _module(f"{PACKAGE}.models.story_session", StorySession=object),
        f"{PACKAGE}.utils": _module(f"{PACKAGE}.utils", message_add_head=Mock()),
        f"{PACKAGE}.config": _module(f"{PACKAGE}.config", Config=object),
        f"{PACKAGE}.llm_usage": _module(f"{PACKAGE}.llm_usage", set_llm_usage_context=Mock()),
        platform.__name__: platform,
    }
    original_exists = Path.exists

    def exists_without_database_config(path):
        # db.py 的默认引擎只需构造，不连接磁盘；真实会话使用各测试的临时库。
        if path.name == "database.yaml" and path.parent.name == "config":
            return False
        return original_exists(path)

    try:
        with patch.dict(sys.modules, stubs):
            with patch.object(Path, "exists", exists_without_database_config):
                db = importlib.import_module(f"{PACKAGE}.models.db")
            guide = importlib.import_module(f"{PACKAGE}.ai_guide")
            with patch.object(guide, "call_ai_with_fallback", AsyncMock(side_effect=AssertionError("unexpected model call"))), \
                 patch.object(guide, "_log_qa_record", Mock(side_effect=AssertionError("unexpected QA log"))):
                yield guide, db, platform
    finally:
        for name in list(sys.modules):
            if name == PACKAGE or name.startswith(f"{PACKAGE}."):
                sys.modules.pop(name, None)


async def _sqlite_session(guide, db, monkeypatch, tmp_path, session_class=AsyncSession):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'guide.db').as_posix()}",
        pool_size=1, max_overflow=0, pool_timeout=0.2,
    )
    factory = sessionmaker(engine, class_=session_class, expire_on_commit=True)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE guide_marker (value TEXT NOT NULL)"))
    monkeypatch.setattr(guide, "safe_session", lambda: db.safe_session(factory))
    return engine, factory


def _event_and_args(question="如何升级"):
    return SimpleNamespace(), SimpleNamespace(extract_plain_text=lambda: question)


def _player():
    return SimpleNamespace(uid=42, nickname="初名", level=12, reincarnation_level=3)


@pytest.mark.asyncio
async def test_commits_and_closes_before_send_and_ai_releases_only_connection(
    guide_modules, monkeypatch, tmp_path,
):
    guide, db, platform = guide_modules
    steps = []

    class ObservedSession(AsyncSession):
        async def commit(self):
            await super().commit()
            steps.append("commit")

        async def close(self):
            await super().close()
            steps.append("close")

    engine, factory = await _sqlite_session(guide, db, monkeypatch, tmp_path, ObservedSession)

    class Base(DeclarativeBase):
        pass

    class GuidePlayer(Base):
        __tablename__ = "guide_player"
        uid: Mapped[int] = mapped_column(primary_key=True)
        nickname: Mapped[str] = mapped_column(String(24))
        level: Mapped[int]
        reincarnation_level: Mapped[int]

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("INSERT INTO guide_player VALUES (42, '初名', 12, 3)"))
    entered, release = asyncio.Event(), asyncio.Event()
    player = None

    async def lookup(session, event):
        nonlocal player
        steps.append("lookup")
        player = await session.get(GuidePlayer, 42)
        await session.execute(text("INSERT INTO guide_marker (value) VALUES ('saved')"))
        return player

    async def send(message):
        steps.append("send")
        assert steps[:3] == ["lookup", "commit", "close"]
        assert steps[-1] == "send"
        assert set(steps[2:-1]) == {"close"}
        assert engine.pool.checkedout() == 0
        assert {"nickname", "level", "reincarnation_level"} <= inspect(player).expired_attributes
        player.__dict__.update(uid=999, nickname="后改", level=99, reincarnation_level=9)

    async def answer(question, context):
        steps.append("ai")
        assert question == "如何升级"
        assert isinstance(context, guide.GuidePlayerContext)
        assert (context.uid, context.nickname, context.level, context.reincarnation_level) == (42, "初名", 12, 3)
        with pytest.raises(FrozenInstanceError):
            context.nickname = "可变"
        assert engine.pool.checkedout() == 0
        entered.set()
        await release.wait()
        return "**回答**"

    async def finish(message):
        steps.append("finish")
        assert engine.pool.checkedout() == 0
        raise FinishedException

    matcher = SimpleNamespace(send=AsyncMock(side_effect=send), finish=AsyncMock(side_effect=finish))
    monkeypatch.setattr(platform, "get_unified_player", lookup)
    monkeypatch.setattr(guide, "ai_guide", matcher)
    monkeypatch.setattr(guide, "get_ai_guidance", answer)
    event, args = _event_and_args()
    task = asyncio.create_task(guide.handle_ai_guide(event, args))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        # AI 被阻塞时，另一个真实 SQLAlchemy 会话必须拿到同一条连接。
        async with factory() as session:
            result = await asyncio.wait_for(session.execute(text("SELECT value FROM guide_marker")), 1)
            assert result.scalar_one() == "saved"
    finally:
        release.set()
        try:
            with pytest.raises(FinishedException):
                await asyncio.wait_for(task, 2)
        finally:
            await engine.dispose()
    assert steps[:3] == ["lookup", "commit", "close"]
    assert steps[steps.index("send") + 1] == "ai"
    assert steps[-1] == "finish"
    matcher.send.assert_awaited_once()
    matcher.finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_failure_prevents_all_messages_and_ai(guide_modules, monkeypatch, tmp_path):
    guide, db, platform = guide_modules
    rolled_back = []

    class FailingSession(AsyncSession):
        async def commit(self):
            raise RuntimeError("commit failed")

        async def rollback(self):
            rolled_back.append(True)
            await super().rollback()

    engine, _ = await _sqlite_session(guide, db, monkeypatch, tmp_path, FailingSession)

    async def lookup(session, event):
        await session.execute(text("INSERT INTO guide_marker (value) VALUES ('uncommitted')"))
        return _player()

    matcher = SimpleNamespace(send=AsyncMock(), finish=AsyncMock())
    ai = AsyncMock()
    monkeypatch.setattr(platform, "get_unified_player", lookup)
    monkeypatch.setattr(guide, "ai_guide", matcher)
    monkeypatch.setattr(guide, "get_ai_guidance", ai)
    try:
        with pytest.raises(RuntimeError, match="commit failed"):
            await guide.handle_ai_guide(*_event_and_args())
        assert rolled_back
        assert engine.pool.checkedout() == 0
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT count(*) FROM guide_marker"))
            assert result.scalar_one() == 0
    finally:
        await engine.dispose()
    matcher.send.assert_not_awaited()
    matcher.finish.assert_not_awaited()
    ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_question_and_unregistered_player_finish_outside_transaction(
    guide_modules, monkeypatch, tmp_path,
):
    guide, db, platform = guide_modules
    engine, _ = await _sqlite_session(guide, db, monkeypatch, tmp_path)
    matcher = SimpleNamespace(send=AsyncMock(), finish=AsyncMock(side_effect=FinishedException))
    ai = AsyncMock()
    monkeypatch.setattr(guide, "ai_guide", matcher)
    monkeypatch.setattr(guide, "get_ai_guidance", ai)
    try:
        monkeypatch.setattr(guide, "safe_session", Mock(side_effect=AssertionError("empty question opened session")))
        with pytest.raises(FinishedException):
            await guide.handle_ai_guide(*_event_and_args("  "))
        assert "用法" in matcher.finish.call_args.args[0].data["markdown"].content

        monkeypatch.setattr(guide, "safe_session", lambda: db.safe_session(sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False,
        )))

        async def unregistered(session, event):
            await session.execute(text("SELECT 1"))
            return None

        async def finished_after_close(message):
            assert engine.pool.checkedout() == 0
            assert "注册" in message.data["markdown"].content
            raise FinishedException

        monkeypatch.setattr(platform, "get_unified_player", unregistered)
        matcher.finish.side_effect = finished_after_close
        with pytest.raises(FinishedException):
            await guide.handle_ai_guide(*_event_and_args())
        assert matcher.finish.await_count == 2
    finally:
        await engine.dispose()
    matcher.send.assert_not_awaited()
    ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_uses_snapshot_after_source_changes(guide_modules, monkeypatch, tmp_path):
    guide, db, platform = guide_modules
    engine, _ = await _sqlite_session(guide, db, monkeypatch, tmp_path)
    player = _player()
    messages = []
    logs = []

    async def send(message):
        assert engine.pool.checkedout() == 0
        player.uid, player.nickname, player.level, player.reincarnation_level = 99, "新名", 99, 9

    async def provider(payload):
        messages.extend(payload)
        assert engine.pool.checkedout() == 0
        return {"choices": [{"message": {"content": "游戏回答"}}]}

    matcher = SimpleNamespace(send=AsyncMock(side_effect=send),
                              finish=AsyncMock(side_effect=FinishedException))
    monkeypatch.setattr(platform, "get_unified_player", AsyncMock(return_value=player))
    monkeypatch.setattr(guide, "ai_guide", matcher)
    monkeypatch.setattr(guide, "_build_context_from_retrieval", lambda question, max_chunks: ("帮助条目", []))
    monkeypatch.setattr(guide, "call_ai_with_fallback", provider)
    monkeypatch.setattr(guide, "_log_qa_record", lambda *args: logs.append(args))
    try:
        with pytest.raises(FinishedException):
            await guide.handle_ai_guide(*_event_and_args())
    finally:
        await engine.dispose()
    prompt = messages[0]["content"]
    assert "初名[UID：42]" in prompt
    assert "等级：12级" in prompt
    assert "转数：3转" in prompt
    assert "新名" not in prompt
    assert logs == [(42, "如何升级", [], "游戏回答")]
    matcher.finish.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [asyncio.TimeoutError, asyncio.CancelledError])
async def test_timeout_and_cancellation_leave_no_player_connection(
    guide_modules, monkeypatch, tmp_path, failure,
):
    guide, db, platform = guide_modules
    engine, _ = await _sqlite_session(guide, db, monkeypatch, tmp_path)
    matcher = SimpleNamespace(send=AsyncMock(), finish=AsyncMock(side_effect=FinishedException))
    monkeypatch.setattr(platform, "get_unified_player", AsyncMock(return_value=_player()))
    monkeypatch.setattr(guide, "ai_guide", matcher)
    monkeypatch.setattr(guide, "_build_context_from_retrieval", lambda question, max_chunks: ("帮助条目", []))

    async def provider(messages):
        assert engine.pool.checkedout() == 0
        raise failure()

    monkeypatch.setattr(guide, "call_ai_with_fallback", provider)
    try:
        if failure is asyncio.CancelledError:
            with pytest.raises(asyncio.CancelledError):
                await guide.handle_ai_guide(*_event_and_args())
            matcher.finish.assert_not_awaited()
        else:
            with pytest.raises(FinishedException):
                await guide.handle_ai_guide(*_event_and_args())
            assert "超时" in matcher.finish.call_args.args[0].data["markdown"].content
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
    matcher.send.assert_awaited_once()
