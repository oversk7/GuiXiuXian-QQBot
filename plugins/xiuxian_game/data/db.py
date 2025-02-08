from sqlmodel import create_engine, Session
from ..models import Player, GameItem  # 显式导入

engine = create_engine("sqlite:///game.db")

def get_session():
    with Session(engine) as session:
        yield session 