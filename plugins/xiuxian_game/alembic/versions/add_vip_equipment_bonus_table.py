"""add_vip_equipment_bonus_table

Revision ID: vip_equipment_001
Revises: 316ae6f6d779
Create Date: 2025-10-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vip_equipment_001'
down_revision: Union[str, None] = '316ae6f6d779'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建VIP装备永久加成表"""
    op.create_table(
        'vip_equipment_bonus',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.String(length=32), nullable=False),
        sa.Column('bonus_attrs', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        op.f('ix_vip_equipment_bonus_player_id'),
        'vip_equipment_bonus',
        ['player_id'],
        unique=True
    )


def downgrade() -> None:
    """删除VIP装备永久加成表"""
    op.drop_index(op.f('ix_vip_equipment_bonus_player_id'), table_name='vip_equipment_bonus')
    op.drop_table('vip_equipment_bonus')

