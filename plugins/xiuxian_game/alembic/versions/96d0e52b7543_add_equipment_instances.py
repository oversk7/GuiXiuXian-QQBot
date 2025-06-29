"""add equipment_instances

Revision ID: 96d0e52b7543
Revises: 1f23bb217ddd
Create Date: 2025-06-30 00:53:34.943015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96d0e52b7543'
down_revision: Union[str, None] = '1f23bb217ddd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
