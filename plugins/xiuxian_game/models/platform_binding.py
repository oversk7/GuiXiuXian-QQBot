from sqlalchemy import String, DateTime, Boolean, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timedelta
from .db import Base
import secrets
import string


class PlatformBinding(Base):
    """跨平台账号绑定模型"""
    __tablename__ = "platform_binding"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    primary_platform_id: Mapped[str] = mapped_column(String(32), index=True, comment="主平台ID（群聊用户ID）")
    secondary_platform_id: Mapped[str] = mapped_column(String(32), index=True, comment="次平台ID（频道用户ID）")
    binding_key: Mapped[str] = mapped_column(String(16), nullable=True, comment="绑定密钥（永久有效直到使用）")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1', comment="绑定是否有效")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="绑定创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="最后更新时间")
    
    @classmethod
    def generate_binding_key(cls) -> str:
        """生成6位数字绑定密钥"""
        return ''.join(secrets.choice(string.digits) for _ in range(6))
    
    def is_key_valid(self) -> bool:
        """检查绑定密钥是否有效"""
        return bool(self.binding_key)

    def clear_binding_key(self):
        """清除绑定密钥"""
        self.binding_key = None
        self.updated_at = datetime.now()
