from sqlmodel import SQLModel

class BaseModel(SQLModel):
    id: int | None = None