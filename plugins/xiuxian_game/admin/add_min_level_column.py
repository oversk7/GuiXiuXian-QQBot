"""
为抽奖表添加min_level字段
用于已存在的抽奖表升级
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def add_min_level_column():
    """为抽奖表添加min_level字段"""
    # 直接创建引擎
    db_path = project_root / "plugins" / "xiuxian_game" / "data" / "game.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=True)
    
    async with engine.begin() as conn:
        # 检查表是否存在
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='lottery'")
        )
        if not result.fetchone():
            print("抽奖表不存在，请先运行 init_lottery_tables.py")
            return
        
        # 检查字段是否已存在
        result = await conn.execute(
            text("PRAGMA table_info(lottery)")
        )
        columns = result.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'min_level' in column_names:
            print("min_level字段已存在，无需添加")
            return
        
        # 添加min_level字段
        await conn.execute(text("""
            ALTER TABLE lottery ADD COLUMN min_level INTEGER DEFAULT 1
        """))
        
        print("min_level字段添加成功！")


if __name__ == "__main__":
    asyncio.run(add_min_level_column())

