"""更新市场库存为500-1000随机数

Revision ID: update_market_stock_to_500_1000
Revises: 019b6d7cd48e
Create Date: 2025-07-29 00:00:00.000000

"""
from typing import Sequence, Union
import random

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'update_market_stock_to_500_1000'
down_revision: Union[str, None] = '019b6d7cd48e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """更新现有市场状态记录的库存为500-1000随机数"""
    # 获取数据库连接
    connection = op.get_bind()
    
    # 查询所有现有的市场状态记录
    result = connection.execute(text("SELECT id FROM market_state"))
    market_state_ids = [row[0] for row in result.fetchall()]
    
    # 为每个记录生成新的随机库存
    for state_id in market_state_ids:
        new_stock = random.randint(500, 1000)
        connection.execute(
            text("UPDATE market_state SET current_stock = :stock, max_stock = :stock WHERE id = :id"),
            {"stock": new_stock, "id": state_id}
        )
    
    print(f"已更新 {len(market_state_ids)} 个市场状态记录的库存为500-1000随机数")


def downgrade() -> None:
    """回滚：将库存恢复为100"""
    connection = op.get_bind()
    
    # 将所有市场状态的库存恢复为100
    connection.execute(
        text("UPDATE market_state SET current_stock = 100, max_stock = 100")
    )
    
    print("已将所有市场状态记录的库存恢复为100")
