from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from enum import Enum as PyEnum
from datetime import datetime, timedelta
from sqlalchemy.sql import func


class CardType(str, PyEnum):
    """月卡类型"""
    BASIC = "BASIC"      # 基础月卡
    PREMIUM = "PREMIUM"  # 高级月卡


class MonthlyCard(Base):
    """月卡记录表"""
    __tablename__ = "monthly_card"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")
    card_type: Mapped[CardType] = mapped_column(SQLEnum(CardType), comment="月卡类型")
    start_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="开始时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    
    # 关联关系
    player: Mapped["Player"] = relationship("Player", back_populates="monthly_cards")
    
    @property
    def is_active(self) -> bool:
        """检查月卡是否有效"""
        now = datetime.now()
        return self.start_time <= now <= self.end_time
    
    @property
    def remaining_days(self) -> int:
        """剩余天数"""
        if not self.is_active:
            return 0
        return max(0, (self.end_time - datetime.now()).days)
    
    @classmethod
    async def get_active_card(cls, session, player_id: str, card_type: CardType = None):
        """获取玩家的有效月卡"""
        from sqlalchemy import select, and_

        now = datetime.now()
        query = select(cls).where(
            and_(
                cls.player_id == player_id,
                cls.start_time <= now,
                cls.end_time >= now
            )
        )

        if card_type:
            query = query.where(cls.card_type == card_type)

        result = await session.execute(query)
        return result.scalars().first()
    
    @classmethod
    async def get_all_active_cards(cls, session, player_id: str):
        """获取玩家所有有效月卡"""
        from sqlalchemy import select, and_

        now = datetime.now()
        query = select(cls).where(
            and_(
                cls.player_id == player_id,
                cls.start_time <= now,
                cls.end_time >= now
            )
        )
        result = await session.execute(query)
        return result.scalars().all()
    
    @classmethod
    async def add_monthly_card(cls, session, player_id: str, card_type: CardType, months: int = 1):
        """为玩家添加月卡"""
        now = datetime.now()
        
        # 检查是否已有同类型的有效月卡
        existing_card = await cls.get_active_card(session, player_id, card_type)
        
        if existing_card:
            # 如果已有有效月卡，延长时间
            existing_card.end_time += timedelta(days=30 * months)
            session.add(existing_card)
            return existing_card
        else:
            # 创建新月卡
            end_time = now + timedelta(days=30 * months)
            new_card = cls(
                player_id=player_id,
                card_type=card_type,
                start_time=now,
                end_time=end_time
            )
            session.add(new_card)
            return new_card


def get_monthly_card_config():
    """从配置文件获取月卡配置"""
    try:
        from ..config import config
        monthly_config = config.game_config.get("monthly_card", {})
    except ImportError:
        # 如果相对导入失败，使用绝对导入
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from config import config
        monthly_config = config.game_config.get("monthly_card", {})

    return {
        CardType.BASIC: {
            "name": monthly_config.get("basic", {}).get("name", "基础月卡"),
            "cultivation_efficiency": monthly_config.get("basic", {}).get("cultivation_efficiency", 0.2),
            "seclusion_time_limit": monthly_config.get("basic", {}).get("seclusion_time_limit", 9) * 3600,
            "seclusion_efficiency": monthly_config.get("basic", {}).get("seclusion_efficiency", 0.2),
            "inventory_bonus": monthly_config.get("basic", {}).get("inventory_bonus", 5),
            "auto_collect": monthly_config.get("basic", {}).get("auto_collect", False),
            "sign_stamina_bonus": monthly_config.get("basic", {}).get("sign_stamina_bonus", 0),
            "sign_monthly_card_boxes": monthly_config.get("basic", {}).get("sign_monthly_card_boxes", 1),
            "breakthrough_protection": monthly_config.get("basic", {}).get("breakthrough_protection", 0.0),
        },
        CardType.PREMIUM: {
            "name": monthly_config.get("premium", {}).get("name", "高级月卡"),
            "cultivation_efficiency": monthly_config.get("premium", {}).get("cultivation_efficiency", 0.0),
            "seclusion_time_limit": monthly_config.get("premium", {}).get("seclusion_time_limit", 12) * 3600,
            "seclusion_efficiency": monthly_config.get("premium", {}).get("seclusion_efficiency", 0.5),
            "inventory_bonus": monthly_config.get("premium", {}).get("inventory_bonus", 20),
            "auto_collect": monthly_config.get("premium", {}).get("auto_collect", True),
            "sign_stamina_bonus": monthly_config.get("premium", {}).get("sign_stamina_bonus", 0),
            "sign_monthly_card_boxes": monthly_config.get("premium", {}).get("sign_monthly_card_boxes", 3),
            "breakthrough_protection": monthly_config.get("premium", {}).get("breakthrough_protection", 0.0),
        }
    }

# 月卡权益配置（动态从配置文件读取）
def get_card_benefits_config():
    """获取月卡权益配置"""
    return get_monthly_card_config()


async def get_player_card_benefits(session, player_id: str) -> dict:
    """获取玩家的月卡权益"""
    benefits = {
        "cultivation_efficiency": 0.0,
        "seclusion_time_limit": 7 * 3600,  # 默认7小时
        "seclusion_efficiency": 0.0,
        "inventory_bonus": 0,
        "auto_collect": False,
        "sign_stamina_bonus": 0,  # 签到咒抗上限增加
        "sign_monthly_card_boxes": 0,  # 签到获得月卡宝箱数量
        "breakthrough_protection": 0.0,  # 突破失败保护（修为保留比例）
        "basic_active": False,  # 基础月卡是否激活
        "premium_active": False,  # 高级月卡是否激活
    }

    active_cards = await MonthlyCard.get_all_active_cards(session, player_id)

    # 获取月卡配置
    card_config = get_card_benefits_config()

    for card in active_cards:
        card_benefits = card_config.get(card.card_type, {})

        # 标记月卡激活状态
        if card.card_type == CardType.BASIC:
            benefits["basic_active"] = True
        elif card.card_type == CardType.PREMIUM:
            benefits["premium_active"] = True

        # 累加数值型权益
        benefits["cultivation_efficiency"] += card_benefits.get("cultivation_efficiency", 0)
        benefits["seclusion_efficiency"] += card_benefits.get("seclusion_efficiency", 0)
        benefits["inventory_bonus"] += card_benefits.get("inventory_bonus", 0)
        benefits["sign_stamina_bonus"] += card_benefits.get("sign_stamina_bonus", 0)
        benefits["sign_monthly_card_boxes"] += card_benefits.get("sign_monthly_card_boxes", 0)

        # 突破保护取最大值
        benefits["breakthrough_protection"] = max(
            benefits["breakthrough_protection"],
            card_benefits.get("breakthrough_protection", 0)
        )

        # 取最大值的权益
        benefits["seclusion_time_limit"] = max(
            benefits["seclusion_time_limit"],
            card_benefits.get("seclusion_time_limit", 7 * 3600)
        )

        # 布尔型权益，任一为True则为True
        if card_benefits.get("auto_collect", False):
            benefits["auto_collect"] = True

    return benefits
