"""斗法天梯 - 魂晶商店

魂晶是 PvP 专属货币，仅能通过天梯对战获得。
商店物品分三类：
- immediate: 立即生效（如增加匹配次数）
- currency: 直接变更玩家货币（如香火补给）
- item: 加入背包的物品

兑换接口：LadderShopService.redeem(session, player, rating, item_name, quantity)
"""
from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.player import Player
from ...models.inventory import ItemInstance
from ...models.ladder import LadderRating

logger = logging.getLogger(__name__)


# 商店物品配置
# 字段说明：
#   price: 单价（魂晶）
#   description: 商品描述
#   type: immediate / currency / item
#   max_per_purchase: 单次购买上限（防止误操作）
#   item_id / field / amount: 视类型而定
#   daily_limit: 每日购买上限（None 表示无限制）
SHOP_ITEMS: dict = {
    "斗法令": {
        "price": 50,
        "description": "残魂凝聚令，立即恢复 1 次今日斗法次数",
        "type": "immediate",
        "effect": "add_daily_match",
        "max_per_purchase": 5,
        "daily_limit": 5,
    },
    "灵气补给": {
        "price": 200,
        "description": "焚魂取气，立即获得 50 香火",
        "type": "currency",
        "field": "incense",
        "amount": 50,
        "max_per_purchase": 20,
        "daily_limit": None,
    },
    "稳定水晶": {
        "price": 800,
        "description": "升阶护身的稳定水晶（蓝色品质）×1",
        "type": "item",
        "item_id": "stabilizer_crystal",
        "max_per_purchase": 5,
        "daily_limit": None,
    },
    "洗词石": {
        "price": 300,
        "description": "装备词缀洗炼之物 ×1",
        "type": "item",
        "item_id": "affix_reroll_stone",
        "max_per_purchase": 10,
        "daily_limit": None,
    },
    "改名卡": {
        "price": 1500,
        "description": "改名卡 ×1，可修改一次道号",
        "type": "item",
        "item_id": "rename_card",
        "max_per_purchase": 1,
        "daily_limit": 1,
    },
}


class LadderShopError(Exception):
    """商店相关异常"""
    pass


class LadderShopService:
    """斗法商店服务"""

    @classmethod
    def list_items(cls) -> list[dict]:
        """返回商店所有物品（用于显示）"""
        items = []
        for name, cfg in SHOP_ITEMS.items():
            items.append({
                "name": name,
                "price": cfg["price"],
                "description": cfg["description"],
                "max_per_purchase": cfg.get("max_per_purchase", 1),
                "daily_limit": cfg.get("daily_limit"),
            })
        return items

    @classmethod
    async def redeem(
        cls,
        session: AsyncSession,
        player: Player,
        rating: LadderRating,
        item_name: str,
        quantity: int = 1,
    ) -> Tuple[bool, str]:
        """兑换商品

        Returns:
            (success, message)
        """
        if quantity <= 0:
            return False, "⛔ 兑换数量必须大于 0"

        cfg = SHOP_ITEMS.get(item_name)
        if not cfg:
            return False, f"⛔ 商店中没有「{item_name}」"

        # 单次购买上限
        max_per = cfg.get("max_per_purchase", 1)
        if quantity > max_per:
            return False, f"⛔ 「{item_name}」单次最多兑换 {max_per} 个"

        # 每日限购校验
        daily_limit = cfg.get("daily_limit")
        if daily_limit is not None:
            purchases = rating.daily_shop_purchases or {}
            already_today = purchases.get(item_name, 0)
            if already_today + quantity > daily_limit:
                remaining = max(0, daily_limit - already_today)
                return False, (
                    f"⛔ 「{item_name}」今日限购 {daily_limit} 个，已购 {already_today}，"
                    f"剩余可购 {remaining}"
                )

        # 计算总价
        total_cost = cfg["price"] * quantity
        if rating.soul_crystals < total_cost:
            return False, f"⛔ 魂晶不足，需要 {total_cost} 魂晶，当前 {rating.soul_crystals}"

        # 扣除魂晶（暂未提交，失败后回滚）
        rating.soul_crystals -= total_cost

        # 按类型执行
        try:
            if cfg["type"] == "immediate":
                msg = await cls._apply_immediate(rating, cfg, quantity)
            elif cfg["type"] == "currency":
                msg = await cls._apply_currency(player, cfg, quantity)
            elif cfg["type"] == "item":
                msg = await cls._apply_item(session, player, cfg, quantity)
            else:
                rating.soul_crystals += total_cost  # 回滚
                return False, f"⛔ 未知商品类型: {cfg['type']}"
        except LadderShopError as e:
            rating.soul_crystals += total_cost  # 回滚
            return False, str(e)
        except (SQLAlchemyError, ValueError, KeyError) as e:  # pragma: no cover
            rating.soul_crystals += total_cost
            logger.error(f"兑换失败: {e}", exc_info=True)
            return False, f"⛔ 兑换异常: {e}"

        # 记录每日购买
        if daily_limit is not None:
            purchases = dict(rating.daily_shop_purchases or {})
            purchases[item_name] = purchases.get(item_name, 0) + quantity
            rating.daily_shop_purchases = purchases

        return True, (
            f"✅ 已兑换「{item_name}」×{quantity}\n"
            f"💎 消耗 {total_cost} 魂晶 | 余额 {rating.soul_crystals}\n"
            f"{msg}"
        )

    # ========== 各类型处理 ==========

    @classmethod
    async def _apply_immediate(
        cls, rating: LadderRating, cfg: dict, quantity: int
    ) -> str:
        """立即生效类商品"""
        effect = cfg.get("effect")

        if effect == "add_daily_match":
            rating.daily_extra_matches += quantity
            return f"⚔️ 残魂凝聚，今日斗法次数 +{quantity}"

        raise LadderShopError(f"未知的立即生效类型: {effect}")

    @classmethod
    async def _apply_currency(
        cls, player: Player, cfg: dict, quantity: int
    ) -> str:
        """货币类商品（直接修改 Player 字段）"""
        field = cfg["field"]
        amount = cfg["amount"] * quantity

        if not hasattr(player, field):
            raise LadderShopError(f"玩家无字段 {field}")

        current = getattr(player, field) or 0
        setattr(player, field, current + amount)
        field_names = {"incense": "香火"}
        return f"💰 {field_names.get(field, field)} +{amount}"

    @classmethod
    async def _apply_item(
        cls, session: AsyncSession, player: Player, cfg: dict, quantity: int
    ) -> str:
        """物品类商品（加入背包）"""
        item_id = cfg["item_id"]
        ok = await ItemInstance.add_item(session, player.id, item_id, quantity)
        if not ok:
            raise LadderShopError("⛔ 背包空间不足，请整理背包后重试")
        return f"🎒 已放入背包"
