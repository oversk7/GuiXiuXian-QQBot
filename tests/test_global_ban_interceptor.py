"""全局封禁拦截器的单元测试。

重点回归：封禁记录存的是 Player.id（新注册玩家为 UUID），
而 event.get_user_id() 是平台用户 ID（openid），两者不能直接比较。
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from plugins.xiuxian_game import global_ban_interceptor as interceptor


class _Base(DeclarativeBase):
    pass


class _MappedPlayerBan(_Base):
    """仅用于构造合法 SQL 语句的映射类，不实际建表。"""
    __tablename__ = "test_global_ban_player_ban"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean)

    def __init__(self, player_id: str, is_active: bool = True):
        self.player_id = player_id
        self.is_active = is_active

    def is_expired(self) -> bool:
        return False

    def get_ban_info(self) -> str:
        return "封禁状态：生效中\n原因：test\n剩余时间：永久"


class _ExpiredPlayerBan(_MappedPlayerBan):
    def is_expired(self) -> bool:
        return True


class _FakeResult:
    def __init__(self, record):
        self._record = record

    def scalars(self):
        class _Scalars:
            @staticmethod
            def first():
                return self._record
        return _Scalars()


class _FakeSession:
    def __init__(self, active_player=None, legacy_player=None, ban_record=None):
        self.active_player = active_player
        self.legacy_player = legacy_player
        self.ban_record = ban_record
        self.committed = False

    async def get(self, model, pk):
        return self.legacy_player

    async def execute(self, stmt):
        return _FakeResult(self.ban_record)

    async def commit(self):
        self.committed = True


class _FakePlayerRepository:
    def __init__(self, session):
        self._session = session

    async def get_active_by_platform_id(self, platform_id: str):
        return self._session.active_player


def _install_fakes(monkeypatch, session):
    @asynccontextmanager
    async def _fake_safe_session():
        yield session

    monkeypatch.setattr(interceptor, "safe_session", _fake_safe_session)
    monkeypatch.setattr(interceptor, "PlayerRepository", _FakePlayerRepository)
    monkeypatch.setattr(interceptor, "PlayerBan", _MappedPlayerBan)


async def test_ban_matches_active_player_uuid_not_platform_id(monkeypatch):
    """封禁记录按 Player.id 匹配，不能按 event.get_user_id() 匹配。"""
    player = SimpleNamespace(id="uuid-4217-player")
    record = _MappedPlayerBan(player_id="uuid-4217-player")
    session = _FakeSession(active_player=player, ban_record=record)
    _install_fakes(monkeypatch, session)

    is_banned, ban_info = await interceptor.check_player_ban("platform-openid-4217")

    assert is_banned is True
    assert "生效中" in ban_info


async def test_ban_not_matched_when_no_active_or_legacy_player(monkeypatch):
    record = _MappedPlayerBan(player_id="some-uuid")
    session = _FakeSession(active_player=None, legacy_player=None, ban_record=record)
    _install_fakes(monkeypatch, session)

    is_banned, _ = await interceptor.check_player_ban("platform-openid-000")

    assert is_banned is False


async def test_ban_matches_legacy_player_by_platform_id(monkeypatch):
    """老玩家没有 ownership 记录时，Player.id 就是平台 ID。"""
    player = SimpleNamespace(id="legacy-openid-4217")
    record = _MappedPlayerBan(player_id="legacy-openid-4217")
    session = _FakeSession(active_player=None, legacy_player=player, ban_record=record)
    _install_fakes(monkeypatch, session)

    is_banned, _ = await interceptor.check_player_ban("legacy-openid-4217")

    assert is_banned is True


async def test_expired_ban_auto_deactivates(monkeypatch):
    player = SimpleNamespace(id="uuid-4217-player")
    record = _ExpiredPlayerBan(player_id="uuid-4217-player")
    session = _FakeSession(active_player=player, ban_record=record)
    _install_fakes(monkeypatch, session)

    is_banned, _ = await interceptor.check_player_ban("platform-openid-4217")

    assert is_banned is False
    assert record.is_active is False
    assert session.committed is True
