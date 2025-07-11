from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, delete, func
from ..models.db import safe_session
from ..models import Player, Inventory, TradeItem, PurchaseRequest
from ..config import config
from ..utils import message_add_head

# 辅助函数：获取玩家显示信息
async def _get_user_display(user_id: str) -> tuple:
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        return (player.uid, player.nickname) if player else ("未知", "未知用户")

# 查看交易市场
market = on_command("交易市场", priority=5, block=True)
@market.handle()
async def handle_market(event: MessageEvent):
    async with safe_session() as session:
        result = await session.execute(
            select(TradeItem).where(TradeItem.quantity > 0)
            .order_by(TradeItem.created_at.desc())
            .limit(20)  # 最多显示20条
        )
        trade_items = result.scalars().all()

    if not trade_items:
        await market.finish("🛒 交易市场空空如也～")

    msg = ["🛍️ 𝗧𝗿𝗮𝗱𝗲 𝗠𝗮𝗿𝗸𝗲𝘁", "━━━━━━━━━━"]
    for item in trade_items:
        uid, nickname = await _get_user_display(item.seller_id)
        item_cfg = config.items_config["by_id"].get(item.item_id)
        item_line = [
            f"🆔{item.id}│{item_cfg.name}×{item.quantity}",
            f"💰{item.price}│👤{nickname}[{uid}]"
        ]
        msg.append("\n".join(item_line))

    msg.append("━━━━━━━━━━\n📥 购买：/交易 售卖ID 数量（1w以上交易卖家需缴纳5%税费）")
    await market.finish(message_add_head("\n".join(msg), event))

# 上架物品
list_item = on_command("上架", priority=5, block=True)
@list_item.handle()
async def handle_list_item(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await list_item.finish("📦 格式：/上架 物品名 数量 价格\n例：/上架 传送卷 2 100")

    parts = args_text.split()
    if len(parts) != 3:
        await list_item.finish("❌ 参数错误！格式：/上架 [物品名] [数量] [价格]")

    item_name, quantity_str, price_str = parts
    if not (quantity_str.isdigit() and price_str.isdigit()):
        await list_item.finish("❌ 数量/价格需为正整数！")

    quantity = int(quantity_str)
    price = int(price_str)
    if quantity <= 0 or price <= 0:
        await list_item.finish("❌ 数量和价格必须大于0")

    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await list_item.finish("❌ 物品不存在")
    async with safe_session() as session:
        # 先尝试扣除物品（跨堆叠）
        success = await Inventory.consume_item(session, user_id, item_cfg.item_id, quantity)
        if not success:
            await session.rollback()
            await list_item.finish(f"❌ {item_name} 数量不足")

        # 创建上架记录
        trade_item = TradeItem(
            seller_id=user_id,
            item_id=item_cfg.item_id,
            quantity=quantity,
            price=price
        )
        session.add(trade_item)

        await session.commit()
        await list_item.finish(f"✅ 成功上架 {item_name} ×{quantity}\n💰 单价：{price}金币")

trade_command = on_command("交易", priority=5, block=True)
@trade_command.handle()
async def handle_trade_command(event: MessageEvent, args: Message = CommandArg()):
    buyer_id = event.get_user_id()
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await trade_command.finish("💳 格式：/交易 商品ID 数量\n例：/交易 1 2")

    parts = args_text.split()
    if len(parts) != 2:
        await trade_command.finish("❌ 参数错误！格式：/交易 [商品ID] [数量]")

    trade_item_id_str, quantity_str = parts
    if not (trade_item_id_str.isdigit() and quantity_str.isdigit()):
        await trade_command.finish("❌ ID/数量需为整数！")

    trade_item_id = int(trade_item_id_str)
    quantity = int(quantity_str)

    async with safe_session() as session:
        trade_item = await session.get(TradeItem, trade_item_id)
        if not trade_item:
            await trade_command.finish("❌ 商品不存在")

        # 数量校验（防止购买数量超过库存）
        if quantity > trade_item.quantity:
            await trade_command.finish(f"❌ 购买数量超过库存（当前库存：{trade_item.quantity}）")
        if quantity <= 0:
            await trade_command.finish("❌ 购买数量必须大于0")

        original_total = trade_item.price * quantity
        tax = 0
        
        # 计算税费（当原始交易额>1w时收取5%）
        if original_total > 10000:
            tax = int(original_total * 0.05)
        
        seller_gain = original_total - tax

        buyer = await session.get(Player, buyer_id)
        if buyer.gold < original_total:  # 买家需要支付原始总价
            await trade_command.finish(f"❌ 金币不足，需要：{original_total}（当前：{buyer.gold}）")

        # 更新金币
        buyer.gold -= original_total
        seller = await session.get(Player, trade_item.seller_id)
        seller.gold += seller_gain  # 卖家获得税后金额

        inv = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == buyer_id)
            .where(Inventory.item_id == trade_item.item_id)
        )
        inv = inv.scalars().first()
        if inv:
            inv.quantity += quantity
        else:
            session.add(Inventory(
                player_id=buyer_id,
                item_id=trade_item.item_id,
                quantity=quantity
            ))

        trade_item.quantity -= quantity
        if trade_item.quantity <= 0:
            await session.delete(trade_item)

        # 构建交易结果消息
        item_cfg = config.items_config["by_id"][trade_item.item_id]
        tax_info = f"📝 税费：{tax}金币（5%）" if tax else ""
        seller_uid = (await _get_user_display(trade_item.seller_id))[0]
        
        result_msg = [
            f"✅ 购买 {item_cfg.name} ×{quantity} 成功！",
            f"💸 支付总额：{original_total}金币",
            f"🏦 卖家 [UID:{seller_uid}] 到账：{seller_gain}金币",
            tax_info
        ]
        
        await session.commit()
        await trade_command.finish("\n".join(filter(None, result_msg)))

my_shop = on_command("我的店铺", priority=5, block=True)
@my_shop.handle()
async def handle_my_shop(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        result = await session.execute(
            select(TradeItem)
            .where(TradeItem.seller_id == user_id)
        )
        trade_items = result.scalars().all()

    if not trade_items:
        await my_shop.finish("📭 你还没有上架商品哦～")

    msg = [
        "🏪 𝗠𝘆 𝗦𝗵𝗼𝗽",
        "━━━━━━━━━━"
    ]
    for item in trade_items:
        uid, nickname = await _get_user_display(item.seller_id)
        item_cfg = config.items_config["by_id"].get(item.item_id)
        msg.append(f"🆔{item.id}│{item_cfg.name}×{item.quantity}\n💰 单价：{item.price}金币")
    await my_shop.finish(message_add_head("\n".join(msg), event))

# 新增下架命令
down_item = on_command("下架", priority=5, block=True)

@down_item.handle()
async def handle_remove_trade(event: MessageEvent, args: Message = CommandArg()):
    seller_id = event.get_user_id()
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await down_item.finish("📦 格式：/下架 交易ID 数量\n例：/下架 1 2")
    
    parts = args_text.split()
    if len(parts) != 2:
        await down_item.finish("❌ 参数错误！格式：/下架 [交易ID] [数量]")
    
    trade_item_id_str, quantity_str = parts
    if not (trade_item_id_str.isdigit() and quantity_str.isdigit()):
        await down_item.finish("❌ 交易ID 和 数量必须为整数！")
    
    trade_item_id = int(trade_item_id_str)
    quantity = int(quantity_str)
    
    async with safe_session() as session:
        trade_item = await session.get(TradeItem, trade_item_id)
        if not trade_item:
            await down_item.finish("❌ 交易不存在")
        
        if trade_item.quantity < quantity:
            await down_item.finish(f"❌ {trade_item.item.name} 数量不足")

        # 尝试将物品放回卖家背包，先检测容量
        success = await Inventory.add_item(session, seller_id, trade_item.item_id, quantity)
        if not success:
            await session.rollback()
            await down_item.finish("❌ 背包容量不足，无法下架该物品")

        # 更新交易记录
        trade_item.quantity -= quantity
        if trade_item.quantity <= 0:
            session.delete(trade_item)

        await session.commit()
        item_name = config.items_config["by_id"].get(trade_item.item_id).name
        await down_item.finish(f"✅ 成功下架 {item_name} ×{quantity}")

# ----------------- 悬赏收购系统 -----------------

request_cmd = on_command("悬赏", aliases={"求购"}, priority=5, block=True)

@request_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await request_cmd.finish("📦 格式：悬赏 物品名 数量 价格")
    item_name, qty_str, price_str = parts
    if not (qty_str.isdigit() and price_str.isdigit()):
        await request_cmd.finish("❌ 数量/价格需为正整数！")
    qty = int(qty_str)
    price = int(price_str)
    if qty<=0 or price<=0:
        await request_cmd.finish("❌ 数量和价格必须大于0！")

    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await request_cmd.finish("❌ 物品不存在")

    async with safe_session() as session:
        player = await session.get(Player, user_id)
        total_cost = qty * price
        if player.gold < total_cost:
            await request_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")

        player.gold -= total_cost  # 扣押赏金
        req = PurchaseRequest(requester_id=user_id, item_id=item_cfg.item_id, quantity=qty, price=price)
        session.add(req)
        await session.commit()
        await request_cmd.finish(f"✅ 已发布悬赏 {item_cfg.name} ×{qty}，单价 {price}，总赏金 {total_cost}")

# 悬赏列表
request_list_cmd = on_command("悬赏列表", aliases={"求购列表"}, priority=5, block=True)

@request_list_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        reqs = (await session.execute(select(PurchaseRequest).where(PurchaseRequest.quantity>0).order_by(PurchaseRequest.created_at.desc()).limit(20))).scalars().all()

    if not reqs:
        await request_list_cmd.finish("📭 暂无悬赏信息")

    lines=["📜 𝗕𝗼𝘂𝗻𝘁𝗶𝗲𝘀","━━━━━━━━━━"]
    for r in reqs:
        uid,_ = await _get_user_display(r.requester_id)
        name=config.items_config["by_id"][r.item_id].name
        lines.append(f"🆔{r.id}│{name}×{r.quantity}\n💰{r.price}│🎯UID:{uid}")
    lines.append("━━━━━━━━━━\n🚚 接单：/接单 悬赏ID 数量")
    lines.append("🛑 取消：/取消悬赏 悬赏ID [数量]")
    await request_list_cmd.finish(message_add_head("\n".join(lines), event))

# 接单
supply_cmd = on_command("接单", aliases={"供货"}, priority=5, block=True)

@supply_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    supplier_id = event.get_user_id()
    parts = args.extract_plain_text().strip().split()
    if len(parts)!=2 or not all(p.isdigit() for p in parts):
        await supply_cmd.finish("🚚 格式：接单 悬赏ID 数量")
    req_id=int(parts[0]); qty=int(parts[1])
    if qty<=0:
        await supply_cmd.finish("❌ 数量必须>0")

    async with safe_session() as session:
        req = await session.get(PurchaseRequest, req_id)
        if not req or req.quantity<=0:
            await supply_cmd.finish("❌ 悬赏不存在或已完成")
        if qty>req.quantity:
            await supply_cmd.finish(f"❌ 悬赏剩余 {req.quantity}")

        # 检查库存
        inv_rows = (await session.execute(select(Inventory).where(Inventory.player_id==supplier_id, Inventory.item_id==req.item_id))).scalars().all()
        have=sum(i.quantity for i in inv_rows)
        if have<qty:
            await supply_cmd.finish("❌ 背包数量不足")

        # 扣除物品
        success = await Inventory.consume_item(session, supplier_id, req.item_id, qty)
        if not success:
            await session.rollback()
            await supply_cmd.finish("❌ 扣除失败")
        # 支付赏金
        reward = qty * req.price
        supplier = await session.get(Player, supplier_id)
        supplier.gold += reward

        # 给请求者物品
        success = await Inventory.add_item(session, req.requester_id, req.item_id, qty)
        if not success:
            await session.rollback()
            await supply_cmd.finish("❌ 悬赏者背包容量不足")

        # 更新求购数量
        req.quantity -= qty
        if req.quantity<=0:
            await session.delete(req)

        await session.commit()
        item_name=config.items_config["by_id"][req.item_id].name
        await supply_cmd.finish(f"✅ 已完成悬赏，交付 {item_name}×{qty}，获得 {reward} 金币！")

# 取消悬赏
cancel_request_cmd = on_command("取消悬赏", aliases={"撤销悬赏", "撤销求购"}, priority=5, block=True)

@cancel_request_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    parts = args.extract_plain_text().strip().split()
    if len(parts) not in (1, 2) or not parts[0].isdigit() or (len(parts) == 2 and not parts[1].isdigit()):
        await cancel_request_cmd.finish("🛑 格式：取消悬赏 悬赏ID [数量] （数量留空则全部取消）")

    req_id = int(parts[0])
    cancel_qty = int(parts[1]) if len(parts) == 2 else None

    async with safe_session() as session:
        req = await session.get(PurchaseRequest, req_id)
        if not req or req.quantity <= 0:
            await cancel_request_cmd.finish("❌ 悬赏不存在或已完成")

        if req.requester_id != user_id:
            await cancel_request_cmd.finish("❌ 只能取消自己发布的悬赏")

        if cancel_qty is None:
            cancel_qty = req.quantity
        if cancel_qty <= 0 or cancel_qty > req.quantity:
            await cancel_request_cmd.finish(f"❌ 可取消数量范围 1~{req.quantity}")

        # 返还金币
        refund = cancel_qty * req.price
        player = await session.get(Player, user_id)
        player.gold += refund

        # 更新/删除悬赏
        req.quantity -= cancel_qty
        if req.quantity <= 0:
            await session.delete(req)

        await session.commit()

        item_name = config.items_config["by_id"][req.item_id].name
        await cancel_request_cmd.finish(f"✅ 已取消 {item_name}×{cancel_qty} 悬赏，返还 {refund} 金币")