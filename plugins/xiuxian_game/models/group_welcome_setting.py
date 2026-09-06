from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class GroupWelcomeSetting(Base):
    __tablename__ = "group_welcome_setting"

    group_openid: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
