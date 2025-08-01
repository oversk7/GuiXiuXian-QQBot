"""股票交易核心服务

实现股票买卖的核心逻辑，包括：
1. 买入股票
2. 卖出股票
3. 持仓管理
4. 交易记录
5. 手续费计算
"""

from typing import Tuple, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from ..models.player import Player
from ..models.bank_account import BankAccount
from ..models.stock import Stock, StockHolding, StockTransaction, TransactionType
from ..models.db import safe_session
# from .stock_price_engine import StockPriceEngine  # 暂时不使用


class StockService:
    """股票交易服务"""
    
    # 手续费配置
    COMMISSION_RATE = 0.03
    MIN_COMMISSION = 1 
    MAX_COMMISSION = 1000000 
    
    @classmethod
    async def buy_stock(cls, player_id: str, stock_symbol: str, shares: int, 
                       use_bank: bool = False) -> Tuple[bool, str]:
        """买入股票"""
        async with safe_session() as session:
            # 获取玩家信息
            player = await session.get(Player, player_id)
            if not player:
                return False, "玩家不存在"
            
            # 获取股票信息
            stmt = select(Stock).where(Stock.symbol == stock_symbol, Stock.is_active == True)
            stock = (await session.execute(stmt)).scalars().first()
            if not stock:
                return False, f"灵石项目 {stock_symbol} 不存在或已停止投资"
            
            # 验证交易数量
            if shares <= 0:
                return False, "交易数量必须大于0"
            
            # 计算交易金额和手续费
            unit_price = stock.current_price
            total_amount = unit_price * shares
            commission = cls._calculate_commission(total_amount)
            total_cost = total_amount + commission
            
            # 检查资金
            if use_bank:
                # 使用银行账户资金
                bank_account = await session.get(BankAccount, player.id)
                if not bank_account or bank_account.balance < total_cost:
                    return False, f"银行账户余额不足，需要 {total_cost} 金币"
                
                # 扣除银行资金
                bank_account.balance -= total_cost
                session.add(bank_account)
            else:
                # 使用现金
                if player.gold < total_cost:
                    return False, f"金币不足，需要 {total_cost} 金币"
                
                # 扣除现金
                player.gold -= total_cost
                session.add(player)
            
            # 更新持仓
            await cls._update_holding_buy(session, player_id, stock.id, shares, unit_price, total_amount)
            
            # 记录交易
            transaction = StockTransaction(
                player_id=player_id,
                stock_id=stock.id,
                transaction_type=TransactionType.BUY,
                shares=shares,
                price=unit_price,
                total_amount=total_amount,
                commission=commission
            )
            session.add(transaction)
            
            # 注释掉市场影响，避免少玩家时被操控
            # await StockPriceEngine.simulate_market_impact(session, stock.id, shares, "BUY")
            
            await session.commit()
            
            return True, f"成功投资 {stock.name}({stock_symbol}) {shares}份，" \
                        f"成交价 {unit_price} 金币/份，手续费 {commission} 金币"
    
    @classmethod
    async def sell_stock(cls, player_id: str, stock_symbol: str, shares: int, 
                        to_bank: bool = False) -> Tuple[bool, str]:
        """卖出股票"""
        async with safe_session() as session:
            # 获取玩家信息
            player = await session.get(Player, player_id)
            if not player:
                return False, "玩家不存在"
            
            # 获取股票信息
            stmt = select(Stock).where(Stock.symbol == stock_symbol, Stock.is_active == True)
            stock = (await session.execute(stmt)).scalars().first()
            if not stock:
                return False, f"灵石项目 {stock_symbol} 不存在或已停止投资"
            
            # 获取持仓信息
            holding_stmt = select(StockHolding).where(
                and_(StockHolding.player_id == player_id, StockHolding.stock_id == stock.id)
            )
            holding = (await session.execute(holding_stmt)).scalars().first()
            
            if not holding or holding.shares < shares:
                return False, f"投资不足，当前持有 {holding.shares if holding else 0} 份"
            
            # 验证交易数量
            if shares <= 0:
                return False, "交易数量必须大于0"
            
            # 计算交易金额和手续费
            unit_price = stock.current_price
            total_amount = unit_price * shares
            commission = cls._calculate_commission(total_amount)
            net_proceeds = total_amount - commission
            
            # 更新持仓
            await cls._update_holding_sell(session, holding, shares, unit_price, total_amount)
            
            # 添加资金
            if to_bank:
                # 存入银行账户
                bank_account = await session.get(BankAccount, player.id)
                if not bank_account:
                    bank_account = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
                    session.add(bank_account)
                    await session.flush()
                
                bank_account.balance += net_proceeds
                session.add(bank_account)
            else:
                # 添加到现金
                player.gold += net_proceeds
                session.add(player)
            
            # 记录交易
            transaction = StockTransaction(
                player_id=player_id,
                stock_id=stock.id,
                transaction_type=TransactionType.SELL,
                shares=shares,
                price=unit_price,
                total_amount=total_amount,
                commission=commission
            )
            session.add(transaction)
            
            # 注释掉市场影响，避免少玩家时被操控
            # await StockPriceEngine.simulate_market_impact(session, stock.id, shares, "SELL")
            
            await session.commit()
            
            return True, f"成功出售 {stock.name}({stock_symbol}) {shares}份，" \
                        f"成交价 {unit_price} 金币/份，手续费 {commission} 金币，净收入 {net_proceeds} 金币"
    
    @classmethod
    async def get_player_holdings(cls, player_id: str) -> List[Dict]:
        """获取玩家持仓"""
        async with safe_session() as session:
            # 使用 join 和 options 来避免懒加载
            from sqlalchemy.orm import selectinload
            stmt = select(StockHolding).options(selectinload(StockHolding.stock)).where(
                StockHolding.player_id == player_id,
                StockHolding.shares > 0
            )
            holdings = (await session.execute(stmt)).scalars().all()

            result = []
            for holding in holdings:
                stock = holding.stock
                result.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "shares": holding.shares,
                    "avg_cost": holding.avg_cost,
                    "current_price": stock.current_price,
                    "current_value": holding.current_value,
                    "total_cost": holding.total_cost,
                    "profit_loss": holding.profit_loss,
                    "profit_loss_rate": holding.profit_loss_rate
                })

            return result
    
    @classmethod
    async def get_player_transactions(cls, player_id: str, limit: int = 20) -> List[Dict]:
        """获取玩家交易记录"""
        async with safe_session() as session:
            # 使用 selectinload 来避免懒加载
            from sqlalchemy.orm import selectinload
            stmt = select(StockTransaction).options(selectinload(StockTransaction.stock)).where(
                StockTransaction.player_id == player_id
            ).order_by(StockTransaction.created_at.desc()).limit(limit)

            transactions = (await session.execute(stmt)).scalars().all()

            result = []
            for trans in transactions:
                stock = trans.stock
                result.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "type": trans.transaction_type,
                    "shares": trans.shares,
                    "price": trans.price,
                    "total_amount": trans.total_amount,
                    "commission": trans.commission,
                    "created_at": trans.created_at
                })

            return result
    
    @classmethod
    def _calculate_commission(cls, amount: int) -> int:
        """计算手续费"""
        commission = int(amount * cls.COMMISSION_RATE)
        return max(cls.MIN_COMMISSION, min(cls.MAX_COMMISSION, commission))
    
    @classmethod
    async def _update_holding_buy(cls, session: AsyncSession, player_id: str, 
                                 stock_id: int, shares: int, unit_price: int, total_amount: int):
        """更新买入持仓"""
        stmt = select(StockHolding).where(
            and_(StockHolding.player_id == player_id, StockHolding.stock_id == stock_id)
        )
        holding = (await session.execute(stmt)).scalars().first()
        
        if holding:
            # 更新现有持仓
            new_total_cost = holding.total_cost + total_amount
            new_shares = holding.shares + shares
            new_avg_cost = new_total_cost // new_shares
            
            holding.shares = new_shares
            holding.avg_cost = new_avg_cost
            holding.total_cost = new_total_cost
            holding.updated_at = datetime.now()
        else:
            # 创建新持仓
            holding = StockHolding(
                player_id=player_id,
                stock_id=stock_id,
                shares=shares,
                avg_cost=unit_price,
                total_cost=total_amount
            )
            session.add(holding)
    
    @classmethod
    async def _update_holding_sell(cls, session: AsyncSession, holding: StockHolding,
                                  shares: int, unit_price: int, total_amount: int):
        """更新卖出持仓"""
        # 计算卖出成本（按比例）
        sold_cost = (holding.total_cost * shares) // holding.shares
        
        # 更新持仓
        holding.shares -= shares
        holding.total_cost -= sold_cost
        holding.updated_at = datetime.now()
        
        # 如果全部卖出，删除持仓记录
        if holding.shares == 0:
            await session.delete(holding)
        else:
            session.add(holding)
