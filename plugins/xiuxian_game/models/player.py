from sqlmodel import Field
from .base import BaseModel
from datetime import datetime

class Player(BaseModel, table=True):
    uid: str = Field(index=True, unique=True)
    name: str = Field(max_length=20)
    level: int = 1
    hp: int = Field(default=100, ge=0)
    mp: int = Field(default=50, ge=0)
    last_active: datetime = Field(default_factory=datetime.now)