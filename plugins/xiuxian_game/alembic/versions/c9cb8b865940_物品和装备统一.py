"""物品和装备统一

Revision ID: c9cb8b865940
Revises: f1aececaab00
Create Date: 2025-07-12 22:53:22.887803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9cb8b865940'
down_revision: Union[str, None] = 'f1aececaab00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 在 SQLite 下使用 batch_alter_table 重新创建表并添加列/外键 ###
    with op.batch_alter_table('inventory', recreate="always") as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False, comment='获得时间'))
        batch_op.create_foreign_key('fk_inventory_player', 'player', ['player_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### 回滚同样使用 batch_alter_table ###
    with op.batch_alter_table('inventory', recreate="always") as batch_op:
        batch_op.drop_constraint('fk_inventory_player', type_='foreignkey')
        batch_op.drop_column('created_at')
    # ### end Alembic commands ###
