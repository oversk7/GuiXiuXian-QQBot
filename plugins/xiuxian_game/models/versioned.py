from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class Versioned:
    """拒绝其他事务提交后基于旧快照的 ORM 写入。"""

    version_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.version_id}
