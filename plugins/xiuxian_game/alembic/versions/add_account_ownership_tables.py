"""add account ownership tables

Revision ID: acc_ownership_001
Revises: 316ae6f6d779
Create Date: 2025-11-30

说明：
添加账号所有权系统，支持：
1. 一个真实玩家（platform_id）拥有多个游戏账号（Player）
2. 账号切换功能
3. 账号转让功能（通过6位数字密钥）
4. 转让历史审计

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'acc_ownership_001'
down_revision: Union[str, None] = '316ae6f6d779'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建账号所有权表并迁移现有数据"""

    # 1. 创建 account_ownership 表
    op.create_table(
        'account_ownership',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('owner_platform_id', sa.String(length=64), nullable=False, comment='拥有者的平台ID（真实玩家）'),
        sa.Column('player_id', sa.String(length=64), nullable=False, comment='拥有的游戏账号ID'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='0', comment='是否是当前激活使用的账号'),
        sa.Column('display_name', sa.String(length=32), nullable=True, comment='账号备注名（如\'主号\'、\'小号\'、\'买来的\'）'),
        sa.Column('transfer_key', sa.String(length=16), nullable=True, comment='账号转让密钥（6位数字，NULL表示未生成）'),
        sa.Column('transfer_key_created_at', sa.DateTime(), nullable=True, comment='转让密钥生成时间'),
        sa.Column('acquired_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='获得此账号的时间'),
        sa.Column('acquired_type', sa.String(length=16), nullable=False, server_default='created', comment='获得方式：created/transferred/purchased/gift'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='记录创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='记录更新时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('player_id', name='uq_account_ownership_player_id')
    )

    # 创建索引
    op.create_index('idx_account_ownership_owner', 'account_ownership', ['owner_platform_id'])
    op.create_index('idx_account_ownership_active', 'account_ownership', ['owner_platform_id', 'is_active'])

    # 2. 创建 account_transfer_logs 表
    op.create_table(
        'account_transfer_logs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('player_id', sa.String(length=64), nullable=False, comment='被转让的游戏账号ID'),
        sa.Column('from_platform_id', sa.String(length=64), nullable=False, comment='原拥有者的平台ID'),
        sa.Column('to_platform_id', sa.String(length=64), nullable=False, comment='新拥有者的平台ID'),
        sa.Column('transfer_type', sa.String(length=16), nullable=False, comment='转让类型：sale（买卖）/gift（赠送）/admin（管理员操作）'),
        sa.Column('transfer_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='转让完成时间'),
        sa.Column('transfer_key_used', sa.String(length=16), nullable=True, comment='使用的转让密钥'),
        sa.Column('notes', sa.String(length=256), nullable=True, comment='转让备注'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE')
    )

    # 创建索引
    op.create_index('idx_transfer_log_player', 'account_transfer_logs', ['player_id', 'transfer_time'])
    op.create_index('idx_transfer_log_from', 'account_transfer_logs', ['from_platform_id', 'transfer_time'])
    op.create_index('idx_transfer_log_to', 'account_transfer_logs', ['to_platform_id', 'transfer_time'])

    # 3. 数据迁移：为所有现有Player创建AccountOwnership记录
    # 注意：这里假设Player表有platform_id字段，表示最初创建该账号的平台ID
    connection = op.get_bind()

    # 检查是否有现有的Player数据
    result = connection.execute(text("SELECT COUNT(*) FROM players"))
    player_count = result.scalar()

    if player_count > 0:
        # 为每个现有Player创建AccountOwnership记录
        # owner_platform_id = player的platform_id（假设是最初创建者）
        # is_active = True（现有账号都设为激活状态）
        connection.execute(text("""
            INSERT INTO account_ownership (
                owner_platform_id,
                player_id,
                is_active,
                display_name,
                acquired_type,
                acquired_at,
                created_at,
                updated_at
            )
            SELECT
                id as owner_platform_id,
                id as player_id,
                1 as is_active,
                '主号' as display_name,
                'created' as acquired_type,
                created_at as acquired_at,
                CURRENT_TIMESTAMP as created_at,
                CURRENT_TIMESTAMP as updated_at
            FROM players
        """))


def downgrade() -> None:
    """降级：删除账号所有权表"""

    # 删除索引
    op.drop_index('idx_transfer_log_to', table_name='account_transfer_logs')
    op.drop_index('idx_transfer_log_from', table_name='account_transfer_logs')
    op.drop_index('idx_transfer_log_player', table_name='account_transfer_logs')

    op.drop_index('idx_account_ownership_active', table_name='account_ownership')
    op.drop_index('idx_account_ownership_owner', table_name='account_ownership')

    # 删除表
    op.drop_table('account_transfer_logs')
    op.drop_table('account_ownership')
