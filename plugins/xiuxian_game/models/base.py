from ..data.db import Base

class BaseModel(Base):
    __abstract__ = True  # 声明为抽象基类