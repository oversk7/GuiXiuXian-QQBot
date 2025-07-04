"""Increase inventory capacity to 100

Revision ID: 25d8b32abcde
Revises: 1f23bb217ddd
Create Date: 2025-07-04 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '25d8b32abcde'
down_revision: Union[str, None] = '96d0e52b7543'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 更新列默认值
    op.alter_column(
        'player',
        'inventory_capacity',
        existing_type=sa.Integer(),
        server_default='100',
        existing_nullable=False
    )
    # 更新已有数据，将容量不足 100 的玩家统一提升到 100
    op.execute("UPDATE player SET inventory_capacity = 100 WHERE inventory_capacity < 100")


def downgrade() -> None:
    # 恢复默认值为 10
    op.alter_column(
        'player',
        'inventory_capacity',
        existing_type=sa.Integer(),
        server_default='10',
        existing_nullable=False
    )
    # 可选：不回滚已更新的数据 