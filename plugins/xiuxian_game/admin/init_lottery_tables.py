"""
初始化抽奖系统数据表
直接创建表，不使用alembic迁移
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def init_lottery_tables():
    """初始化抽奖系统数据表"""
    # 直接创建引擎
    db_path = project_root / "plugins" / "xiuxian_game" / "data" / "game.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=True)
    
    async with engine.begin() as conn:
        # 检查表是否已存在
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='lottery'")
        )
        if result.fetchone():
            print("抽奖表已存在，跳过创建")
            return
        
        # 创建抽奖活动表
        await conn.execute(text("""
            CREATE TABLE lottery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id VARCHAR(32) NOT NULL,
                creator_uid INTEGER NOT NULL,
                creator_name VARCHAR(24) NOT NULL,
                lottery_type VARCHAR(16) NOT NULL,
                item_id VARCHAR(64),
                item_name VARCHAR(64) NOT NULL,
                winner_count INTEGER NOT NULL,
                prize_per_winner INTEGER NOT NULL,
                total_prize INTEGER NOT NULL,
                min_level INTEGER DEFAULT 1,
                status VARCHAR(16) DEFAULT '进行中',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME,
                group_id VARCHAR(64)
            )
        """))
        
        # 创建抽奖参与者表
        await conn.execute(text("""
            CREATE TABLE lottery_participant (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lottery_id INTEGER NOT NULL,
                player_id VARCHAR(32) NOT NULL,
                player_uid INTEGER NOT NULL,
                player_name VARCHAR(24) NOT NULL,
                is_winner BOOLEAN DEFAULT 0,
                prize_received BOOLEAN DEFAULT 0,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                won_at DATETIME
            )
        """))
        
        # 创建索引
        await conn.execute(text("CREATE INDEX idx_lottery_creator ON lottery(creator_id)"))
        await conn.execute(text("CREATE INDEX idx_lottery_status ON lottery(status)"))
        await conn.execute(text("CREATE INDEX idx_lottery_participant_lottery ON lottery_participant(lottery_id)"))
        await conn.execute(text("CREATE INDEX idx_lottery_participant_player ON lottery_participant(player_id)"))
        
        print("抽奖系统数据表创建成功！")


if __name__ == "__main__":
    asyncio.run(init_lottery_tables())

