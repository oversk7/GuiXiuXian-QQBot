"""添加私信支持"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f6d7d2b5d9c'
down_revision: Union[str, None] = 'af46f455df24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'world_message',
        sa.Column('recipient_id', sa.String(length=32), nullable=True)
    )
    op.create_index(op.f('ix_world_message_recipient_id'), 'world_message', ['recipient_id'], unique=False)
    op.add_column(
        'player',
        sa.Column('last_private_message_check', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('player', 'last_private_message_check')
    op.drop_index(op.f('ix_world_message_recipient_id'), table_name='world_message')
    op.drop_column('world_message', 'recipient_id')
