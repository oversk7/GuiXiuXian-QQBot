import asyncio
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException, PausedException, RejectedException
from sqlalchemy.exc import SQLAlchemyError

from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork
from plugins.xiuxian_game.models.db import safe_session


@pytest.mark.parametrize("manager", [safe_session, UnitOfWork])
@pytest.mark.parametrize("error", [None, FinishedException, PausedException, RejectedException, ValueError, asyncio.CancelledError])
async def test_transaction_exit_commits_control_flow_and_rolls_back_failures(manager, error):
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False

    async def execute():
        async with manager(lambda: session):
            if error is not None:
                raise error

    if error is None:
        await execute()
    else:
        with pytest.raises(error):
            await execute()
    if error in (None, FinishedException, PausedException, RejectedException):
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
    else:
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.parametrize("manager", [safe_session, UnitOfWork])
@pytest.mark.parametrize("finish", [False, True])
async def test_failed_commit_is_rolled_back_even_during_finish(manager, finish):
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.commit.side_effect = SQLAlchemyError("commit failed")
    with pytest.raises(SQLAlchemyError, match="commit failed"):
        async with manager(lambda: session):
            if finish:
                raise FinishedException
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
