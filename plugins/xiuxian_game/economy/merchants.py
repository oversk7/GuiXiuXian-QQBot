from __future__ import annotations

"""跑商系统 & 缉邪司总部商店

跑商系统规则：
1. 仅限现实世界（region == "大都会"）。
2. 市场坐标固定；列表见 MARKETS。
3. 价格：每天 00:00 刷新，基于日期+市场ID+item_id 生成哈希随机数。
4. 必须玩家坐标与市场坐标一致才可交易。

缉邪司总部规则：
1. 位于风雪镇（坐标由 HEADQUARTERS_COORD 统一定义）
2. 使用公会积分兑换装备升阶相关特殊物品
3. 即使没有所属公会也可以使用（如果有积分）
"""

from datetime import datetime, time, timedelta

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from .market import get_shop_adjusted_price
from ..models.inventory import ItemInstance
from ..models.market_state import MarketState
from ..models.trade_record import TradeRecord, TradeType
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..config import config
from .merchant_service import (
    MARKETS, MARKET_BY_COORD, LIMITED_GOODS,
    CITY_TO_CLUSTER, CLUSTER_NEIGHBORS, _cluster_distance,
    _price_for, _calculate_tiered_multiplier, _calculate_trade_bonuses, _calculate_trade_tax,
    SHOP_ITEMS, SEASONING_SHOP_ITEMS,
    BLACK_MARKET_ID, BLACK_MARKET_OVERPRICE, BLACK_MARKET_DAILY_LIMIT_PER_PLAYER,
    _pick_black_market_today_items, _ensure_black_market_stock, _black_market_daily_purchased_qty,
    HEADQUARTERS_COORD, HEADQUARTERS_ITEMS,
)

def _headquarters_location_hint() -> str:
    """返回缉邪司总部的统一位置提示，避免与坐标校验脱节。"""
    x, y = HEADQUARTERS_COORD
    return f"风雪镇({x},{y})缉邪司总部"


# ------------------- 指令 -------------------
market_cmd = on_command("市集", aliases={"商店", "市场"}, block=True, priority=7)

list_market_cmd = on_command("市集列表", aliases={"市场列表", "全部市集"}, block=True, priority=7)
# 查看指定市集商品
detail_market_cmd = on_command("市集详情", aliases={"市集价格", "市场报价"}, block=True, priority=7)

# 查看某物品在各市集的买/卖价
price_compare_cmd = on_command("市价", block=True, priority=7)

# 跑商记录：查看玩家的交易历史
trade_history_cmd = on_command("跑商记录", block=True, priority=7)

# 市集记录：查看当前市集最近的交易记录（所有玩家）
market_log_cmd = on_command("市集记录", aliases={"交易记录", "市集动态"}, block=True, priority=7)

# 跑商推荐：列出可获利的买卖路线
trade_advise_cmd = on_command("跑商推荐", aliases={"套利", "赚差价"}, block=True, priority=7)

# 交易限制查询：查看玩家当前的交易限制情况
trade_restrictions_cmd = on_command("交易限制", aliases={"限制查询", "交易状态"}, block=True, priority=7)

@market_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await market_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await market_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await market_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        # 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
        if not market:
            # 展示所有市场坐标
            lines = ["# 可交易地点一览", "***"]
            for m in MARKETS:
                lines.append(f"{cmd(m.name, f'导航 {m.name}')} ({m.x},{m.y})")
            lines.append("***")
            lines.append(f"前往对应坐标后输入 {cmd('市集')} 联系当地商人")
            await market_cmd.finish(build_markdown("\n".join(lines)))

        lines = [f"# {market.name} ({market.x},{market.y})", "***"]

        # 显示可购买的商品
        if market.sellable_items:
            lines.append("**可购买商品：**")
            for iid in market.sellable_items:
                item_cfg = config.items_config["by_id"].get(iid)
                sell_p, _ = await _price_for(session, market, iid)

                # 获取库存状态
                market_state = await MarketState.get_or_create(session, market.id, iid)
                stock_status = market_state.get_stock_status()
                stock_info = f"({market_state.current_stock})"

                lines.append(f"{cmd(item_cfg.name, f'购买 {item_cfg.name} ')}│售价 **{sell_p}**│库存{stock_info}{stock_status}")

        # 显示可出售的商品（如果与可购买不同）
        buyable_only = set(market.buyable_items) - set(market.sellable_items)
        if buyable_only:
            lines.append("**额外收购商品：**")
            for iid in buyable_only:
                item_cfg = config.items_config["by_id"].get(iid)
                _, buy_p = await _price_for(session, market, iid)
                lines.append(f"{cmd(item_cfg.name, f'出售 {item_cfg.name} ')}│收价 **{buy_p}**")

        lines.append("***")
        lines.append("价格受供需影响，库存有限先到先得")

        # 新手任务钩子
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(session, player, "command", {"command": "市集"})
        if quest_completed and quest_msg:
            lines.append(f"\n{quest_msg}")

        lines.append(f"{cmd('自动出售')} | {cmd('市集列表')} | {cmd('跑商推荐')}")
        await market_cmd.finish(build_markdown("\n".join(lines)))

buy_cmd = on_command("购买", block=True, priority=7)

@buy_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await buy_cmd.finish("📦 格式：购买 物品名 数量")
    item_name, qty_str = parts
    if not qty_str.isdigit():
        await buy_cmd.finish("❌ 数量需为正整数")
    qty = int(qty_str)
    if qty <= 0:
        await buy_cmd.finish("❌ 数量需大于0")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await buy_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await buy_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await buy_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        # 检查是否为市集购买 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await buy_cmd.finish("⛔ 不存在该物品")

        # 市集购买逻辑 - 检查市场是否出售此商品
        if market and market.can_sell_to_player(item_cfg.item_id):
            # 获取市场状态
            market_state = await MarketState.get_or_create(session, market.id, item_cfg.item_id)
            await market_state.check_daily_refresh(session)
            await market_state.check_restock(session)

            # 检查库存
            if not market_state.can_purchase(qty):
                await buy_cmd.finish(f"❌ 库存不足！当前库存：{market_state.current_stock}，需要：{qty}")

            # 检查背包商品总量限制（防止高等级玩家垄断库存）
            # 注意：血契丹、阴冥草、鱼类和调味料(SEASONING)不占用携带上限
            if item_cfg.item_id in LIMITED_GOODS:
                result_inv = await session.execute(
                    select(ItemInstance).where(
                        ItemInstance.player_id == player.id,
                        ItemInstance.item_id.in_(LIMITED_GOODS)  # 仅统计受限商品
                    )
                )
                current_goods = result_inv.scalars().all()
                current_goods_total = sum(item.quantity for item in current_goods)

                if current_goods_total + qty > 500:
                    await buy_cmd.finish(build_markdown(
                        f"# 商品携带量限制\n"
                        f"***\n"
                        f"当前商品总量：**{current_goods_total}**\n"
                        f"尝试购买：**{qty}**\n"
                        f"携带上限：**500**\n"
                        f"***\n"
                        f"请先出售部分商品再购买\n"
                        f"{cmd('自动出售')} | {cmd('市集')}"))

            # 获取当前价格
            sell_price, _ = await _price_for(session, market, item_cfg.item_id)

            # 阶梯加价：查询今日已购量并计算加价倍率
            already_bought = await TradeRecord.get_daily_purchase_quantity(
                session, player.id, market.id, item_cfg.item_id)
            tiered_multiplier = _calculate_tiered_multiplier(already_bought, qty)
            effective_unit_price = max(1, int(sell_price * tiered_multiplier))
            total_cost = effective_unit_price * qty

            if player.gold < total_cost:
                await buy_cmd.finish(f"❌ 金币不足，需要 {total_cost} (当前 {player.gold})")

            # 先检查背包空间，再扣款
            try:
                await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
            except ValueError as e:
                await buy_cmd.finish(f"❌ {e}")

            # 扣款并更新市场状态
            player.gold -= total_cost
            market_state.apply_purchase(qty)

            # 记录交易
            await TradeRecord.record_trade(
                session=session,
                player_id=player.id,
                trade_type=TradeType.BUY,
                market_id=market.id,
                item_id=item_cfg.item_id,
                quantity=qty,
                unit_price=effective_unit_price,
                total_amount=total_cost
            )

            session.add_all([player, market_state])
            await session.commit()

            # 构建购买成功消息
            tiered_note = ""
            if tiered_multiplier > 1.001:
                tiered_note = f"\n商人加价：x{tiered_multiplier:.2f} (今日已购**{already_bought+qty}**个)"

            buy_msg = (
                f"# 购买成功\n"
                f"***\n"
                f"购买 **{item_cfg.name}**x{qty}\n"
                f"花费 **{total_cost}** 金币{tiered_note}\n"
                f"剩余库存：**{market_state.current_stock}**\n"
            )

            # 新手任务钩子
            from ..quest.novice_quest_service import NoviceQuestService
            quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(session, player, "command", {"command": "购买"})
            if quest_completed and quest_msg:
                buy_msg += f"\n{quest_msg}\n"

            buy_msg += f"***\n{cmd('市集')} | {cmd('自动出售')} | {cmd('跑商推荐')}"
            await buy_cmd.finish(build_markdown(buy_msg))

        # 黑市/基础商店逻辑
        else:
            # 今日黑市上架（非基础物品）
            today_items = await _pick_black_market_today_items(session)
            if item_cfg.item_id in SHOP_ITEMS:
                # 基础物品：基础倍率 × 财富指数
                adjusted_price = await get_shop_adjusted_price(session, item_cfg.price)
                total_cost = adjusted_price * qty
                if player.gold < total_cost:
                    await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")
                try:
                    await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
                except ValueError as e:
                    await buy_cmd.finish(f"❌ {e}")
                player.gold -= total_cost
                await session.commit()
                await buy_cmd.finish(build_markdown(
                    f"# 购买成功\n"
                    f"***\n"
                    f"购买 **{item_cfg.name}**x{qty}\n"
                    f"花费 **{total_cost}** 金币\n"
                    f"***\n"
                    f"{cmd('黑市')} | {cmd('市集')}"))

            elif item_cfg.item_id in SEASONING_SHOP_ITEMS:
                # 食材铺调料：与基础物品定价逻辑相同
                adjusted_price = await get_shop_adjusted_price(session, item_cfg.price)
                total_cost = adjusted_price * qty
                if player.gold < total_cost:
                    await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")
                try:
                    await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
                except ValueError as e:
                    await buy_cmd.finish(f"❌ {e}")
                player.gold -= total_cost
                await session.commit()
                await buy_cmd.finish(build_markdown(
                    f"# 购买成功\n"
                    f"***\n"
                    f"购买 **{item_cfg.name}**x{qty}\n"
                    f"花费 **{total_cost}** 金币\n"
                    f"***\n"
                    f"{cmd('食材铺')} | {cmd('背包 调味品')}"))

            elif item_cfg.item_id in today_items:
                # 黑市高溢价 + 限购
                # 确保今日库存已初始化
                await _ensure_black_market_stock(session, [item_cfg.item_id])
                mstate = await MarketState.get_or_create(session, BLACK_MARKET_ID, item_cfg.item_id)

                if not mstate.can_purchase(qty):
                    await buy_cmd.finish(f"❌ 黑市库存不足！当前库存：{mstate.current_stock}，需要：{qty}")

                # 每人每天总限购（不含基础物品）
                bought = await _black_market_daily_purchased_qty(session, player.id)
                remaining = max(0, BLACK_MARKET_DAILY_LIMIT_PER_PLAYER - bought)
                if qty > remaining:
                    await buy_cmd.finish(
                        f"⛔ 超出今日限购！已购 {bought}/{BLACK_MARKET_DAILY_LIMIT_PER_PLAYER}，还可购买 {remaining} 件")

                base_adjusted = await get_shop_adjusted_price(session, item_cfg.price or 1)
                unit_price = max(1, int(base_adjusted * BLACK_MARKET_OVERPRICE))
                total_cost = unit_price * qty
                if player.gold < total_cost:
                    await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")

                # 先加物，再扣款，避免金额不足卡死库存
                try:
                    await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
                except ValueError as e:
                    await buy_cmd.finish(f"❌ {e}")

                player.gold -= total_cost
                mstate.apply_purchase(qty)

                # 记录交易
                await TradeRecord.record_trade(
                    session=session,
                    player_id=player.id,
                    trade_type=TradeType.BUY,
                    market_id=BLACK_MARKET_ID,
                    item_id=item_cfg.item_id,
                    quantity=qty,
                    unit_price=unit_price,
                    total_amount=total_cost
                )

                session.add_all([player, mstate])
                await session.commit()

                await buy_cmd.finish(build_markdown(
                    f"# 黑市购买成功\n"
                    f"***\n"
                    f"购买 **{item_cfg.name}**x{qty}\n"
                    f"花费 **{total_cost}** 金币\n"
                    f"黑市剩余库存：**{mstate.current_stock}**\n"
                    f"***\n"
                    f"{cmd('黑市')} | {cmd('市集')}"))

            else:
                await buy_cmd.finish("⛔ 此处无法购买该物品")

# -------- 卖出 --------
sell_cmd = on_command("出售", aliases={"卖"}, block=True, priority=7)

# -------- 自动出售 --------
auto_sell_cmd = on_command("自动出售", aliases={"一键出售", "批量出售"}, block=True, priority=7)

@sell_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await sell_cmd.finish("📦 格式：出售 物品名 数量")
    item_name, qty_str = parts
    if not qty_str.isdigit():
        await sell_cmd.finish("❌ 数量需为正整数")
    qty = int(qty_str)
    if qty <= 0:
        await sell_cmd.finish("❌ 数量必须大于0")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await sell_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await sell_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await sell_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n━━━━━━━━━━━━━\n此地没有安全商人。\n━━━━━━━━━━━━━\n⬇️ 【返回】脱离诡域，返回现实", event))

        # 检查是否在市集 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
        if not market:
            await sell_cmd.finish("⛔ 这里只有风～没有商人")

        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await sell_cmd.finish("⛔ 不存在该物品")

        # 检查市场是否收购此商品
        if not market.can_buy_from_player(item_cfg.item_id):
            await sell_cmd.finish("⛔ 商人不收购该物品")

        # 检查库存（聚合数量）
        inv_rows = (await session.execute(
            select(ItemInstance).where(ItemInstance.player_id == player.id, ItemInstance.item_id == item_cfg.item_id)
        )).scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)
        if total_qty < qty:
            await sell_cmd.finish("❌ 背包数量不足")

        # 检查是否违反同地点交易限制（减少到4小时）
        can_sell = await TradeRecord.can_sell_at_market(session, player.id, market.id, item_cfg.item_id, hours=4)
        if not can_sell:
            # 获取最近的购买记录用于提示
            recent_purchases = await TradeRecord.get_recent_purchases_at_market(session, player.id, market.id, item_cfg.item_id, hours=4)
            if recent_purchases:
                latest_purchase = recent_purchases[0]
                from datetime import timedelta
                unlock_time = latest_purchase.trade_time + timedelta(hours=4)
                await sell_cmd.finish(build_markdown(
                    f"# 同地点交易限制\n"
                    f"***\n"
                    f"你在 **{latest_purchase.trade_time.strftime('%H:%M')}** 于此地购买了 **{item_cfg.name}**\n"
                    f"需要等到 **{unlock_time.strftime('%H:%M')}** 才能在此地出售\n"
                    f"***\n"
                    f"建议前往其他市集出售\n"
                    f"{cmd('市集列表')} | {cmd('跑商推荐')} | {cmd('交易限制')}"))

        # 获取市场状态和当前价格
        market_state = await MarketState.get_or_create(session, market.id, item_cfg.item_id)
        await market_state.check_daily_refresh(session)
        await market_state.check_restock(session)

        _, buy_price = await _price_for(session, market, item_cfg.item_id)
        total_gain = buy_price * qty

        # 更新：优先扣未满堆叠
        success_consume = await ItemInstance.consume_item(session, player.id, item_cfg.item_id, qty)
        if not success_consume:
            await session.rollback()
            await sell_cmd.finish("❌ 扣除物品失败")

        # 计算跑商多元奖励 + 跑商税
        bonus_total = 0
        tax_amount = 0
        bonus_lines = []
        is_cross_market = False
        # 检查是否为跨市场交易（在不同市场出售）
        recent_purchases = await TradeRecord.get_recent_purchases_at_market(session, player.id, market.id, item_cfg.item_id, hours=24)
        if not recent_purchases:  # 没有在本地购买记录，说明是从其他地方运来的
            is_cross_market = True
            # 计算各项奖励
            trade_bonuses = await _calculate_trade_bonuses(
                session, player.id, market, item_cfg.item_id, total_gain)
            for name, rate, amount in trade_bonuses:
                if amount > 0:
                    bonus_total += amount
                    bonus_lines.append(f"{name}({rate*100:.0f}%)：+{amount}")

            # 计算跑商税
            tax_rate, tax_amount = await _calculate_trade_tax(session, player.id, total_gain)
            if tax_amount > 0:
                bonus_lines.append(f"💸跑商税({tax_rate*100:.0f}%)：-{tax_amount}")

        net_gain = total_gain + bonus_total - tax_amount

        # FIFO 计算买入成本（在 record_trade 之前，才不会把本次卖出算进已消耗）
        purchase_cost = await TradeRecord.get_fifo_cost(session, player.id, item_cfg.item_id, qty)

        # 更新玩家金币和市场状态
        player.gold += net_gain
        # 更新财富成就统计
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=net_gain, auto_commit=False)
        market_state.apply_sale(qty)

        # 记录交易
        await TradeRecord.record_trade(
            session=session,
            player_id=player.id,
            trade_type=TradeType.SELL,
            market_id=market.id,
            item_id=item_cfg.item_id,
            quantity=qty,
            unit_price=buy_price,
            total_amount=total_gain,
            is_cross_market=is_cross_market
        )

        session.add_all([player, market_state])
        await session.commit()

        # 构建出售结果消息
        sell_lines = [
            f"# 出售成功",
            f"***",
            f"卖出 **{item_cfg.name}**x{qty}",
            f"基础收入：**{total_gain}** 金币",
        ]
        if bonus_lines:
            sell_lines.append("")
            sell_lines.extend(bonus_lines)
            sell_lines.append("")
            sell_lines.append(f"实得 **{net_gain}** 金币")

        # 利润计算
        final_income = net_gain if bonus_lines else total_gain
        if purchase_cost is not None:
            profit = final_income - purchase_cost
            if profit >= 0:
                pct = profit / purchase_cost * 100 if purchase_cost > 0 else 0
                sell_lines.append(f"💰净赚 **{profit}** 金币(+{pct:.1f}%)")
            else:
                pct = abs(profit) / purchase_cost * 100 if purchase_cost > 0 else 0
                sell_lines.append(f"💸亏损 **{abs(profit)}** 金币(-{pct:.1f}%)")

        sell_lines.extend([
            f"市场库存：**{market_state.current_stock}**",
            f"***",
            f"{cmd('市集')} | {cmd('自动出售')} | {cmd('跑商推荐')}",
        ])
        sell_result = "\n".join(sell_lines)
        await sell_cmd.finish(build_markdown(sell_result))

@auto_sell_cmd.handle()
async def _(event: MessageEvent):
    """自动出售背包中所有可出售的商品"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message, require_player
        player = await require_player(session, event, auto_sell_cmd)

        # 获取当前位置的市场
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
        if not market:
            await auto_sell_cmd.finish("⛔ 当前位置没有市集，请先前往市集")

        # 获取背包中的所有商品（排除装备）
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
            .where(ItemInstance.quantity > 0)
        )
        all_items = result.scalars().all()

        # 过滤出可出售的商品，并按物品ID聚合数量
        aggregated_items: dict[str, int] = {}
        blocked_items: set[str] = set()

        for item in all_items:
            if item.is_equipment:
                continue  # 跳过装备
            if item.is_fish:
                continue  # 跳过鱼类，避免误卖鱼栏物品

            if not market.can_buy_from_player(item.item_id):
                continue

            if item.item_id in blocked_items:
                continue

            if item.item_id not in aggregated_items:
                can_sell = await TradeRecord.can_sell_at_market(
                    session, player.id, market.id, item.item_id, hours=4
                )
                if not can_sell:
                    blocked_items.add(item.item_id)
                    continue
                aggregated_items[item.item_id] = 0

            aggregated_items[item.item_id] += item.quantity

        if not aggregated_items:
            await auto_sell_cmd.finish(build_markdown(
                "# 无可出售商品\n"
                "***\n"
                "背包中没有可在当前市集出售的商品\n"
                "可能原因：\n"
                "- 背包中没有商品\n"
                "- 当前市集不收购你的商品\n"
                "- 4小时内在此地购买的商品不能出售\n"
                "***\n"
                f"{cmd('市集')} | {cmd('市集列表')} | {cmd('跑商推荐')}"))

        # 在循环前快照当日已有跨市场收入，避免 flush 后重查导致税率虚高
        daily_revenue_snapshot = await TradeRecord.get_daily_cross_market_revenue(session, player.id)

        # 计算总收益、多元奖励和跑商税
        total_gain = 0
        total_bonus = 0
        sold_items = []

        for item_id, quantity in aggregated_items.items():
            if quantity <= 0:
                continue

            item_cfg = config.items_config["by_id"].get(item_id)
            if not item_cfg:
                continue

            # 获取市场状态和价格
            market_state = await MarketState.get_or_create(session, market.id, item_id)
            await market_state.check_daily_refresh(session)
            await market_state.check_restock(session)

            _, buy_price = await _price_for(session, market, item_id)
            item_gain = buy_price * quantity

            # 计算跑商多元奖励
            item_bonus = 0
            item_bonus_names = []
            is_cross_market = False
            recent_purchases = await TradeRecord.get_recent_purchases_at_market(
                session, player.id, market.id, item_id, hours=24
            )
            if not recent_purchases:
                is_cross_market = True
                trade_bonuses = await _calculate_trade_bonuses(
                    session, player.id, market, item_id, item_gain)
                for name, rate, amount in trade_bonuses:
                    if amount > 0:
                        item_bonus += amount
                        item_bonus_names.append(name)

            # FIFO 计算买入成本（在 record_trade 之前）
            item_cost = await TradeRecord.get_fifo_cost(session, player.id, item_id, quantity)

            # 扣除物品
            try:
                success_consume = await ItemInstance.consume_item(
                    session, player.id, item_id, quantity
                )
            except ValueError:
                continue

            if not success_consume:
                continue

            # 更新市场状态
            market_state.apply_sale(quantity)

            # 记录交易
            await TradeRecord.record_trade(
                session=session,
                player_id=player.id,
                trade_type=TradeType.SELL,
                market_id=market.id,
                item_id=item_id,
                quantity=quantity,
                unit_price=buy_price,
                total_amount=item_gain,
                is_cross_market=is_cross_market
            )
            # flush 确保下一轮循环能查到本次记录
            await session.flush()

            total_gain += item_gain
            total_bonus += item_bonus
            sold_items.append({
                "name": item_cfg.name,
                "quantity": quantity,
                "unit_price": buy_price,
                "total": item_gain,
                "bonus": item_bonus,
                "bonus_names": item_bonus_names,
                "cost": item_cost,
            })

            session.add(market_state)

        if not sold_items:
            await auto_sell_cmd.finish(build_markdown(
                f"# 出售失败\n***\n没有成功出售任何商品\n***\n{cmd('市集')} | {cmd('跑商推荐')}"))

        # 计算跑商税（基于总收入，使用循环前的日收入快照避免多算）
        tax_rate, tax_amount = await _calculate_trade_tax(
            session, player.id, total_gain,
            daily_revenue_override=daily_revenue_snapshot
        )

        # 更新玩家金币
        net_gain = total_gain + total_bonus - tax_amount
        player.gold += net_gain
        # 更新财富成就统计
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=net_gain, auto_commit=False)
        session.add(player)
        await session.commit()

        # 生成结果消息
        lines = [
            f"# 自动出售完成",
            f"共出售 **{len(sold_items)}** 种商品",
            "***"
        ]

        for item in sold_items:
            bonus_text = ""
            if item['bonus'] > 0:
                names = "+".join(n.replace("🌍", "").replace("🚀", "").replace("📦", "").replace("⭐", "").replace("📈", "").replace("🔥", "") for n in item['bonus_names'])
                bonus_text = f" (+{item['bonus']} {names})"
            lines.append(f"- {item['name']} x{item['quantity']} = **{item['total']}**金币{bonus_text}")

        lines.extend(["***"])

        if tax_amount > 0:
            lines.append(f"💸跑商税({tax_rate*100:.0f}%)：-**{tax_amount}** 金币")

        lines.append(f"实得：**{net_gain}** 金币")

        # 利润汇总
        total_cost = sum(item['cost'] for item in sold_items if item['cost'] is not None)
        has_cost = any(item['cost'] is not None for item in sold_items)
        if has_cost and total_cost > 0:
            profit = net_gain - total_cost
            if profit >= 0:
                pct = profit / total_cost * 100
                lines.append(f"💰净赚 **{profit}** 金币(+{pct:.1f}%)")
            else:
                pct = abs(profit) / total_cost * 100
                lines.append(f"💸亏损 **{abs(profit)}** 金币(-{pct:.1f}%)")

        lines.extend([
            f"当前金币：**{player.gold}**",
            f"***\n{cmd('市集')} | {cmd('跑商推荐')} | {cmd('交易限制')}"
        ])
        await auto_sell_cmd.finish(build_markdown("\n".join(lines)))

# -------- 市集列表 --------

@list_market_cmd.handle()
async def _(event: MessageEvent):
    """显示所有市集坐标列表（无论玩家当前位置）。"""
    lines = ["# 全部市集坐标", "***"]
    for m in MARKETS:
        lines.append(f"{cmd(m.name, f'导航 {m.name}')} ({m.x},{m.y})")
    lines.append("***")
    lines.append(f"到达坐标后发送 {cmd('市集')} 进行交易")
    lines.append(f"{cmd('跑商推荐')} | {cmd('交易限制')}")
    await list_market_cmd.finish(build_markdown("\n".join(lines)))

# -------- 市集详情 --------

@detail_market_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    market_name = args.extract_plain_text().strip()
    if not market_name:
        await detail_market_cmd.finish("⛔ 格式：市集详情 市集名称  （示例：市集详情 荔湾镇）")

    market = next((m for m in MARKETS if m.name == market_name), None)
    if not market:
        names = "、".join(m.name for m in MARKETS)
        await detail_market_cmd.finish(f"⛔ 未找到市集：{market_name}。可选：{names}")

    async with safe_session() as session:
        lines = [f"# {market.name} ({market.x},{market.y})", "***"]

        # 显示可购买的商品
        if market.sellable_items:
            lines.append("**可购买商品：**")
            for iid in market.sellable_items:
                item_cfg = config.items_config["by_id"].get(iid)
                sell_p, _ = await _price_for(session, market, iid)

                # 获取库存状态
                market_state = await MarketState.get_or_create(session, market.id, iid)
                stock_status = market_state.get_stock_status()
                stock_info = f"({market_state.current_stock})"

                lines.append(f"{cmd(item_cfg.name, f'购买 {item_cfg.name} ')}│售价 **{sell_p}**│库存{stock_info}{stock_status}")

        # 显示可出售的商品（如果与可购买不同）
        buyable_only = set(market.buyable_items) - set(market.sellable_items)
        if buyable_only:
            lines.append("**额外收购商品：**")
            for iid in buyable_only:
                item_cfg = config.items_config["by_id"].get(iid)
                _, buy_p = await _price_for(session, market, iid)
                lines.append(f"{cmd(item_cfg.name, f'出售 {item_cfg.name} ')}│收价 **{buy_p}**")

        lines.append("***")
        lines.append(f"{cmd(f'导航 {market.name}')} 前往该市集")
        lines.append(f"{cmd('市集列表')} | {cmd('跑商推荐')}")

        await detail_market_cmd.finish(build_markdown("\n".join(lines)))

# -------- 市价 --------

@price_compare_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    item_name = args.extract_plain_text().strip()
    if not item_name:
        await price_compare_cmd.finish("⛔ 格式：市价 物品名称  （示例：市价 回春散）")

    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await price_compare_cmd.finish(f"⛔ 未找到物品：{item_name}")

    async with safe_session() as session:
        lines = [f"# {item_cfg.name} 各市集价格", "***"]
        found = False

        for m in MARKETS:
            can_sell = m.can_sell_to_player(item_cfg.item_id)
            can_buy = m.can_buy_from_player(item_cfg.item_id)

            if not can_sell and not can_buy:
                continue

            found = True
            price_info = []

            if can_sell:
                sell_p, _ = await _price_for(session, m, item_cfg.item_id)
                # 获取库存状态
                market_state = await MarketState.get_or_create(session, m.id, item_cfg.item_id)
                stock_info = f"({market_state.current_stock})"
                price_info.append(f"售 **{sell_p}**│库存{stock_info}")

            if can_buy:
                _, buy_p = await _price_for(session, m, item_cfg.item_id)
                price_info.append(f"收 **{buy_p}**")

            lines.append(f"{cmd(m.name, f'导航 {m.name}')}│{' '.join(price_info)}")

        if not found:
            await price_compare_cmd.finish("⛔ 暂无市集交易该物品")

        lines.append("***")
        lines.append(f"{cmd('跑商推荐')} | {cmd('市集列表')}")
        await price_compare_cmd.finish(build_markdown("\n".join(lines)))

# -------- 交易记录 --------

@trade_history_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """查看玩家的交易记录"""
    args_text = args.extract_plain_text().strip()
    page = 1
    if args_text:
        try:
            page = int(args_text)
            if page < 1:
                page = 1
        except ValueError:
            pass

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await trade_history_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await trade_history_cmd.finish("⛔ 请先创建角色")

        # 查询交易记录
        from sqlalchemy import select, desc
        stmt = select(TradeRecord).where(
            TradeRecord.player_id == player.id
        ).order_by(desc(TradeRecord.trade_time)).limit(10).offset((page - 1) * 10)

        result = await session.execute(stmt)
        records = result.scalars().all()

        if not records:
            await trade_history_cmd.finish(build_markdown(
                f"# 交易记录\n***\n暂无交易记录\n***\n{cmd('市集')} | {cmd('跑商推荐')}"))

        lines = [f"# 交易记录 (第{page}页)", "***"]

        for record in records:
            # 获取商品和市场信息
            item_cfg = config.items_config["by_id"].get(record.item_id)
            market = next((m for m in MARKETS if m.id == record.market_id), None)

            trade_type_text = "购买" if record.trade_type == TradeType.BUY else "出售"

            item_name = item_cfg.name if item_cfg else record.item_id
            market_name = market.name if market else record.market_id

            lines.append(
                f"{trade_type_text} **{item_name}**x{record.quantity} "
                f"| {market_name} | **{record.total_amount}**金币 "
                f"| {record.trade_time.strftime('%m-%d %H:%M')}"
            )

        lines.append("***")
        prev_page = max(1, page - 1)
        next_page = page + 1
        lines.append(f"{cmd(f'上一页', f'跑商记录 {prev_page}')} | {cmd(f'下一页', f'跑商记录 {next_page}')}")
        lines.append(f"{cmd('市集')} | {cmd('跑商推荐')} | {cmd('交易限制')}")

        await trade_history_cmd.finish(build_markdown("\n".join(lines)))

# -------- 市集记录（当前市集所有玩家交易动态） --------

@market_log_cmd.handle()
async def _(event: MessageEvent):
    """查看当前市集最近的购买记录（所有玩家）"""
    async with safe_session() as session:
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await market_log_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await market_log_cmd.finish("⛔ 请先创建角色")

        if player.region != "大都会":
            await market_log_cmd.finish("⛔ 只有在大都会才能查看市集记录")

        if player.is_in_dungeon():
            await market_log_cmd.finish("⛔ 诡域中无法查看市集记录")

        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
        if not market:
            await market_log_cmd.finish(
                build_markdown(
                    f"⛔ 当前位置没有市集\n"
                    f"请前往市集坐标后再查看\n"
                    f"***\n{cmd('市集列表')} | {cmd('导航 城市名', '导航 ')}"
                )
            )

        # 查询该市集最近20条交易记录（购买+出售，所有玩家）
        from sqlalchemy import desc, and_
        stmt = select(TradeRecord).where(
            TradeRecord.market_id == market.id
        ).order_by(desc(TradeRecord.trade_time)).limit(20)

        result = await session.execute(stmt)
        records = result.scalars().all()

        if not records:
            await market_log_cmd.finish(build_markdown(
                f"# {market.name} 市集记录\n***\n暂无交易记录\n***\n{cmd('市集')} | {cmd('跑商推荐')}"))

        # 批量查询涉及的玩家昵称
        player_ids = list({r.player_id for r in records})
        from sqlalchemy import func as sa_func
        stmt_players = select(Player.id, Player.nickname).where(Player.id.in_(player_ids))
        player_rows = (await session.execute(stmt_players)).all()
        nickname_map = {pid: nick for pid, nick in player_rows}

        lines = [f"# {market.name} 市集记录", "***"]

        for record in records:
            item_cfg = config.items_config["by_id"].get(record.item_id)
            item_name = item_cfg.name if item_cfg else record.item_id
            nick = nickname_map.get(record.player_id, "???")

            if record.trade_type == TradeType.BUY:
                action = "购入"
                icon = "🛒"
            else:
                action = "售出"
                icon = "💰"

            time_str = record.trade_time.strftime("%m-%d %H:%M")
            lines.append(
                f"{icon} {nick} {action} **{item_name}**×{record.quantity} "
                f"| 单价{record.unit_price} | {time_str}"
            )

        lines.append("***")
        lines.append(f"{cmd('市集')} | {cmd('市集列表')} | {cmd('跑商推荐')}")

        await market_log_cmd.finish(build_markdown("\n".join(lines)))

# -------- 跑商推荐 --------

@trade_advise_cmd.handle()
async def _(event: MessageEvent):
    """快速跑商推荐：只看玩家附近市集的路线，避免全图遍历。"""
    async with safe_session() as session:
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await trade_advise_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await trade_advise_cmd.finish("⛔ 请先创建角色")

        px, py = player.get_current_coordinates()

        # ---- 第1步：找最近的源市集（当前位置或最近3个）----
        sorted_markets = sorted(MARKETS, key=lambda m: abs(m.x - px) + abs(m.y - py))
        source_markets = sorted_markets[:3]  # 最近3个市集作为进货来源

        # ---- 第2步：确定搜索范围（源市集所在集群 + 邻接集群）----
        search_clusters = set()
        for src in source_markets:
            cl = CITY_TO_CLUSTER.get(src.name)
            if cl:
                search_clusters.add(cl)
                search_clusters.update(CLUSTER_NEIGHBORS.get(cl, []))

        dest_markets = [m for m in MARKETS if CITY_TO_CLUSTER.get(m.name) in search_clusters]

        # ---- 第2.5步：查出玩家当前的交易限制（4小时内买入过的 市集×商品 不能在该市集卖出）----
        restriction_stmt = select(TradeRecord).where(
            TradeRecord.player_id == player.id,
            TradeRecord.trade_type == TradeType.BUY,
            TradeRecord.trade_time > datetime.now() - timedelta(hours=4),
        )
        restricted_pairs = {
            (r.market_id, r.item_id)
            for r in (await session.execute(restriction_stmt)).scalars().all()
        }

        # ---- 第3步：快速计算路线（只查必要的价格）----
        opportunities = []

        for src in source_markets:
            for iid in src.sellable_items:
                # 跳过调料和特殊物品（利润低且玩法不同）
                if iid in ("spice", "wasabi", "lingzhi_powder", "secret_sauce", "immortal_oil"):
                    continue

                sell_p_src, _ = await _price_for(session, src, iid)

                for dst in dest_markets:
                    if dst is src or not dst.can_buy_from_player(iid):
                        continue
                    # 跳过玩家当前被交易限制的目的地（4小时内在该市集买过同商品）
                    if (dst.id, iid) in restricted_pairs:
                        continue
                    _, buy_p_dst = await _price_for(session, dst, iid)
                    profit = buy_p_dst - sell_p_src
                    if profit <= 0:
                        continue

                    margin = profit / sell_p_src if sell_p_src else 0
                    item_cfg = config.items_config["by_id"].get(iid)

                    src_cluster = CITY_TO_CLUSTER.get(src.name, "?")
                    dst_cluster = CITY_TO_CLUSTER.get(dst.name, "?")
                    cdist = _cluster_distance(src_cluster, dst_cluster)
                    tile_dist = int(((src.x - dst.x)**2 + (src.y - dst.y)**2)**0.5)

                    opportunities.append({
                        "item": item_cfg.name if item_cfg else iid,
                        "from": src.name, "to": dst.name,
                        "buy": sell_p_src, "sell": buy_p_dst,
                        "profit": profit, "margin": margin,
                        "src_cluster": src_cluster, "dst_cluster": dst_cluster,
                        "cluster_dist": cdist, "tile_dist": tile_dist,
                    })

        if not opportunities:
            await trade_advise_cmd.finish(build_markdown(
                f"# 跑商推荐\n***\n附近暂无盈利机会，换个地方试试？\n***\n{cmd('市集列表')}"))

        # ---- 第4步：排序展示 ----
        opportunities.sort(key=lambda d: d["profit"], reverse=True)

        # 只推荐中低利润路线：藏掉利润最高的前一半，暴利路线留给玩家自己比价发掘
        if len(opportunities) > 8:
            opportunities = opportunities[len(opportunities) // 2:]

        # 取前8条，去重同商品路线
        seen = set()
        sample = []
        for op in opportunities:
            key = (op["item"], op["to"])
            if key in seen:
                continue
            seen.add(key)
            sample.append(op)
            if len(sample) >= 6:
                break

        DIST_LABELS = {0: "同城", 1: "邻近", 2: "中途", 3: "远途", 4: "远途"}
        DIST_EMOJIS = {0: "🏠", 1: "🚶", 2: "🐎", 3: "🚀", 4: "🚀"}

        lines = ["# 💹 跑商推荐", "***"]

        for op in sample:
            cdist = op['cluster_dist']
            dist_label = DIST_LABELS.get(cdist, "远途")
            dist_emoji = DIST_EMOJIS.get(cdist, "🚀")
            eta_sec = op['tile_dist'] / 0.5
            if eta_sec < 60:
                eta_str = f"{int(eta_sec)}秒"
            elif eta_sec < 3600:
                eta_str = f"{int(eta_sec/60)}分钟"
            else:
                eta_str = f"{eta_sec/3600:.1f}小时"

            op_item = op['item']
            op_from = op['from']
            op_to = op['to']
            lines.append(
                f"{dist_emoji} **{dist_label}** {op['src_cluster']}→{op['dst_cluster']}　"
                f"📈 +**{op['profit']}** ({op['margin']*100:.0f}%)\n"
                f"📦 {cmd(op_item, f'购买 {op_item} ')} \n"
                f"🛒 {cmd(op_from, f'导航 {op_from}')} → "
                f"{cmd(op_to, f'导航 {op_to}')}　"
                f"🗺️{op['tile_dist']}格 ⏱️{eta_str}"
            )
            lines.append("──────────")

        lines.append("***")
        lines.append("💡 这只是入门路线，真正的暴利商机要自己用【市价 物品名】各地比价去发掘")
        lines.append(f"{cmd('市集')} | {cmd('市集列表')} | {cmd('交易限制')}")
        await trade_advise_cmd.finish(build_markdown("\n".join(lines)))

# 黑市指令（替代原“系统商店”）
black_market_cmd = on_command("黑市", aliases={"系统商店", "特殊商店"}, block=True, priority=7)

@black_market_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await black_market_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await black_market_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await black_market_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n━━━━━━━━━━━━━\n此地没有安全商人。\n━━━━━━━━━━━━━\n⬇️ 【返回】脱离诡域，返回现实", event))

        # 今日上架与库存
        today_items = await _pick_black_market_today_items(session)
        await _ensure_black_market_stock(session, today_items)

        lines = ["# 黑市", "***"]
        # 今日黑市·高溢价限量
        if today_items:
            lines.append("黑市商人：这可都是我从诡域坟墓里偷出来的好东西~")
            for iid in today_items:
                cfg = config.items_config["by_id"].get(iid)
                if not cfg:
                    continue
                mstate = await MarketState.get_or_create(session, BLACK_MARKET_ID, iid)
                base_adjusted = await get_shop_adjusted_price(session, cfg.price or 1)
                unit_price = max(1, int(base_adjusted * BLACK_MARKET_OVERPRICE))
                lines.append(f"{cmd(cfg.name, f'购买 {cfg.name} ')}│**{unit_price}** 金币│库存(**{mstate.current_stock}**)")
            lines.append("***")

        # 基础物品（动态定价）
        lines.append("**基础物品：**")
        for item_id in SHOP_ITEMS:
            cfg = config.items_config["by_id"].get(item_id)
            if cfg:
                adj_price = await get_shop_adjusted_price(session, cfg.price)
                lines.append(f"{cmd(cfg.name, f'购买 {cfg.name} ')}│**{adj_price}** 金币")

        # 限购说明
        bought = await _black_market_daily_purchased_qty(session, player.id)
        lines.extend([
            "***",
            f"限购：除基础物品外，每人每日总计 **{BLACK_MARKET_DAILY_LIMIT_PER_PLAYER}** 件",
            f"今日已购（不含基础物品）：**{bought}**/{BLACK_MARKET_DAILY_LIMIT_PER_PLAYER}",
        ])
        lines.append(f"{cmd('市集')} | {cmd('市集列表')} | {cmd('食材铺')}")
        await black_market_cmd.finish(build_markdown("\n".join(lines)))


# 食材铺指令
ingredient_shop_cmd = on_command("食材铺", aliases={"调料铺", "食材商店", "调料商店"}, block=True, priority=7)

@ingredient_shop_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await ingredient_shop_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await ingredient_shop_cmd.finish("⛔ 请先创建角色")

        lines = ["# 🍱 食材铺", "***"]
        lines.append("掌柜：烹饪所需调料，应有尽有，童叟无欺！")
        lines.append("")
        for item_id in SEASONING_SHOP_ITEMS:
            cfg = config.items_config["by_id"].get(item_id)
            if cfg:
                adj_price = await get_shop_adjusted_price(session, cfg.price)
                lines.append(f"{cmd(cfg.name, f'购买 {cfg.name} ')}│**{adj_price}** 金币　{cfg.description.split('。')[0]}")
        lines.extend([
            "***",
            f"{cmd('烹饪帮助')} | {cmd('背包 调味品')} | {cmd('黑市')} | {cmd('帮助')}",
        ])
        await ingredient_shop_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 缉邪司总部商店系统 ====================

# 缉邪司总部商店指令
headquarters_cmd = on_command("缉邪司总部", aliases={"总部商店", "总部"}, block=True, priority=7)

@headquarters_cmd.handle()
async def _(event: MessageEvent):
    """缉邪司总部商店"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await headquarters_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await headquarters_cmd.finish("⛔ 请先创建角色")

        if player.region != "大都会":
            await headquarters_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n━━━━━━━━━━━━━\n此地没有安全商人。\n━━━━━━━━━━━━━\n⬇️ 【返回】脱离诡域，返回现实", event))

        # 检查是否在缉邪司总部坐标 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        if (current_x, current_y) != HEADQUARTERS_COORD:
            await headquarters_cmd.finish(build_markdown(
                f"# 缉邪司总部商店\n"
                f"***\n"
                f"总部位置：{cmd('风雪镇', '导航 风雪镇')} {HEADQUARTERS_COORD}\n"
                f"当前位置：({current_x},{current_y})\n"
                f"***\n"
                f"请前往风雪镇缉邪司总部\n"
                f"{cmd('导航 风雪镇')}"))

        # 显示商店界面
        lines = [
            "# 缉邪司总部商店",
            "***",
            f"当前积分：**{player.gold2}**",
            "***",
            "**装备升阶专用物品：**"
        ]

        # 分类显示商品
        upgrade_items = ["upgrade_stone_low", "upgrade_stone_mid", "upgrade_stone_high", "stabilizer_crystal"]
        tool_items = ["gem_hammer", "gem_chisel"]
        gem_items = ["accuracy_bead_1"]
        anti_combo_items = ["anti_combo_talisman_1", "anti_combo_talisman_2", "anti_combo_talisman_3",
                           "anti_combo_talisman_4", "anti_combo_talisman_5"]
        anti_counter_items = ["anti_counter_pendant_1", "anti_counter_pendant_2", "anti_counter_pendant_3",
                             "anti_counter_pendant_4", "anti_counter_pendant_5"]

        # 升阶材料
        for item_id in upgrade_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"{cmd(item_cfg.name, f'总部兑换 {item_cfg.name} ')} - **{HEADQUARTERS_ITEMS[item_id]}**积分")

        lines.append("")
        lines.append("**镶嵌工具：**")

        # 镶嵌工具
        for item_id in tool_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"{cmd(item_cfg.name, f'总部兑换 {item_cfg.name} ')} - **{HEADQUARTERS_ITEMS[item_id]}**积分")

        lines.append("")
        lines.append("**镶嵌物品：**")

        # 普通镶嵌物
        for item_id in gem_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"{cmd(item_cfg.name, f'总部兑换 {item_cfg.name} ')} - **{HEADQUARTERS_ITEMS[item_id]}**积分")

        # 抗连护符
        for item_id in anti_combo_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"{cmd(item_cfg.name, f'总部兑换 {item_cfg.name} ')} - **{HEADQUARTERS_ITEMS[item_id]}**积分")

        # 抗反玉佩
        for item_id in anti_counter_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"{cmd(item_cfg.name, f'总部兑换 {item_cfg.name} ')} - **{HEADQUARTERS_ITEMS[item_id]}**积分")

        lines.extend([
            "***",
            "即使没有公会也可以使用积分兑换",
            "积分可通过公会捐献、签到等方式获得"
        ])

        await headquarters_cmd.finish(build_markdown("\n".join(lines)))


# 缉邪司总部兑换指令
headquarters_exchange_cmd = on_command("总部兑换", aliases={"缉邪司兑换"}, block=True, priority=7)

@headquarters_exchange_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """缉邪司总部兑换物品"""
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await headquarters_exchange_cmd.finish("⛔ 格式：总部兑换 物品名称 [数量]")

    parts = arg_text.split()
    item_name = parts[0]
    quantity = 1

    if len(parts) > 1:
        try:
            quantity = int(parts[1])
            if quantity <= 0:
                await headquarters_exchange_cmd.finish("⛔ 数量必须大于0")
        except ValueError:
            await headquarters_exchange_cmd.finish("⛔ 数量必须是正整数")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await headquarters_exchange_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await headquarters_exchange_cmd.finish("⛔ 请先创建角色")

        if player.region != "大都会":
            await headquarters_exchange_cmd.finish("⛔ 诡域中无法使用缉邪司服务")

        # 检查是否在缉邪司总部坐标 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        if (current_x, current_y) != HEADQUARTERS_COORD:
            await headquarters_exchange_cmd.finish(f"⛔ 请前往{_headquarters_location_hint()}")

        # 查找物品配置
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await headquarters_exchange_cmd.finish(f"⛔ 未找到物品：{item_name}")

        # 检查是否为总部商品
        if item_cfg.item_id not in HEADQUARTERS_ITEMS:
            available_items = "、".join([
                config.items_config["by_id"][iid].name
                for iid in HEADQUARTERS_ITEMS.keys()
                if iid in config.items_config["by_id"]
            ])
            await headquarters_exchange_cmd.finish(
                f"⛔ 缉邪司总部不出售该物品\n"
                f"📦 可兑换物品：{available_items}")

        # 计算总积分消耗
        unit_cost = HEADQUARTERS_ITEMS[item_cfg.item_id]
        total_cost = unit_cost * quantity

        # 检查积分是否足够
        if player.gold2 < total_cost:
            await headquarters_exchange_cmd.finish(
                f"⛔ 积分不足\n"
                f"💎 需要：{total_cost}积分\n"
                f"💎 拥有：{player.gold2}积分\n"
                f"💎 缺少：{total_cost - player.gold2}积分")

        # 检查背包空间并添加物品
        try:
            await ItemInstance.add_item(session, player.id, item_cfg.item_id, quantity)
        except ValueError as e:
            await headquarters_exchange_cmd.finish(f"⛔ {e}")

        # 扣除积分
        player.gold2 -= total_cost
        await session.commit()

        await headquarters_exchange_cmd.finish(build_markdown(
            f"# 兑换成功\n"
            f"***\n"
            f"获得：**{item_cfg.name}** x{quantity}\n"
            f"消耗：**{total_cost}**积分\n"
            f"剩余：**{player.gold2}**积分\n"
            f"***\n"
            f"{cmd('缉邪司总部')} | {cmd('市集')}"))


# -------- 交易限制查询 --------

@trade_restrictions_cmd.handle()
async def _(event: MessageEvent):
    """查看玩家当前的交易限制情况"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await trade_restrictions_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await trade_restrictions_cmd.finish("⛔ 请先创建角色")

        from datetime import timedelta
        from sqlalchemy import select, and_

        # 查询最近4小时内的购买记录
        time_limit = datetime.now() - timedelta(hours=4)
        stmt = select(TradeRecord).where(
            and_(
                TradeRecord.player_id == player.id,
                TradeRecord.trade_type == TradeType.BUY,
                TradeRecord.trade_time > time_limit
            )
        ).order_by(TradeRecord.trade_time.desc())

        result = await session.execute(stmt)
        recent_purchases = result.scalars().all()

        if not recent_purchases:
            await trade_restrictions_cmd.finish(build_markdown(
                f"# 交易限制\n"
                f"***\n"
                f"当前无交易限制\n"
                f"所有市集均可自由交易\n"
                f"***\n"
                f"{cmd('跑商推荐')} | {cmd('市集列表')}"))

        lines = ["# 当前交易限制情况", "***"]

        # 按市场分组统计限制
        restrictions_by_market = {}
        for purchase in recent_purchases:
            market_id = purchase.market_id
            item_id = purchase.item_id

            if market_id not in restrictions_by_market:
                restrictions_by_market[market_id] = []

            # 计算解锁时间
            unlock_time = purchase.trade_time + timedelta(hours=4)
            time_remaining = unlock_time - datetime.now()

            if time_remaining.total_seconds() > 0:
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

                item_cfg = config.items_config["by_id"].get(item_id)
                item_name = item_cfg.name if item_cfg else item_id

                restrictions_by_market[market_id].append({
                    "item": item_name,
                    "time_remaining": time_str,
                    "unlock_time": unlock_time
                })

        # 显示限制信息
        for market_id, restrictions in restrictions_by_market.items():
            if not restrictions:  # 跳过已过期的限制
                continue

            market = next((m for m in MARKETS if m.id == market_id), None)
            market_name = market.name if market else market_id

            lines.append(f"📍 {market_name}")
            for restriction in restrictions:
                lines.append(f"  🚫 {restriction['item']} - 还需 {restriction['time_remaining']}")
            lines.append("")

        if len(lines) == 2:  # 只有标题，说明所有限制都已过期
            await trade_restrictions_cmd.finish(build_markdown(
                f"# 交易限制\n"
                f"***\n"
                f"当前无交易限制\n"
                f"所有市集均可自由交易\n"
                f"***\n"
                f"{cmd('跑商推荐')} | {cmd('市集列表')}"))

        lines.extend([
            "***",
            "在限制时间内无法在对应市集出售相应商品",
            "可前往其他市集出售或等待限制解除",
            f"{cmd('跑商推荐')} | {cmd('市集列表')}"
        ])

        await trade_restrictions_cmd.finish(build_markdown("\n".join(lines)))
