from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from ..models.db import safe_session
from ..models import Player, EquipmentInstance, TradeEquip
from ..utils import message_add_head

# ---------------- 查看装备市场 ----------------
market_equip = on_command("装备市场", block=True, priority=5)

@market_equip.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        stmt = (
            select(TradeEquip)
            .options(
                selectinload(TradeEquip.equip),
                selectinload(TradeEquip.seller)
            )
            .order_by(TradeEquip.created_at.desc())
            .limit(20)
        )
        rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            await market_equip.finish("🛒 装备市场空无一物～")

        lines = ["⚔️ 𝗘𝗾𝘂𝗶𝗽 𝗠𝗮𝗿𝗸𝗲𝘁", "━━━━━━━━━"]
        for r in rows:
            tpl = r.equip.template  # 在会话内先访问，避免 DetachedInstanceError
            seller_uid = r.seller.uid if r.seller else "?"
            lines.append(
                f"🆔{r.id}│{tpl.name} Dur {r.equip.durability}/{tpl.durability}\n💰{r.price}│卖家UID:{seller_uid}"
            )
        lines.append("━━━━━━━━━\n📥 购装：/购装 交易ID")

        await market_equip.finish(message_add_head("\n".join(lines), event))

# ---------------- 上架装备 ----------------
list_equip_cmd = on_command("装备上架", block=True, priority=5)

@list_equip_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await list_equip_cmd.finish("📦 格式：装备上架 装备ID 价格")
    equip_id_str, price_str = parts
    if not (equip_id_str.isdigit() and price_str.isdigit()):
        await list_equip_cmd.finish("❌ 装备ID 与 价格必须为整数！")
    equip_id = int(equip_id_str)
    price = int(price_str)
    if price <= 0:
        await list_equip_cmd.finish("❌ 价格必须大于0")

    async with safe_session() as session:
        equip = await session.get(EquipmentInstance, equip_id)
        if not equip or equip.player_id != event.get_user_id():
            await list_equip_cmd.finish("❌ 无效装备ID或非本人所有")
        if equip.equipped:
            await list_equip_cmd.finish("❌ 请先卸下装备再上架")
        if equip.on_market:
            await list_equip_cmd.finish("❌ 该装备已在市场上架")

        # 上架
        trade_row = TradeEquip(
            equip_id=equip.id,
            seller_id=event.get_user_id(),
            price=price,
        )
        session.add(trade_row)
        equip.on_market = True
        await session.commit()
        await list_equip_cmd.finish(f"✅ 已上架 {equip.template.name}，单价 {price}金币 (ID:{trade_row.id})")

# ---------------- 购买装备 ----------------
buy_equip_cmd = on_command("购装", block=True, priority=5)

@buy_equip_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text.isdigit():
        await buy_equip_cmd.finish("⚔️ 格式：购装 交易ID")
    trade_id = int(arg_text)

    async with safe_session() as session:
        trade_row = await session.get(TradeEquip, trade_id)
        if not trade_row:
            await buy_equip_cmd.finish("❌ 交易不存在")
        if trade_row.seller_id == event.get_user_id():
            await buy_equip_cmd.finish("❌ 不能购买自己的商品！")
        buyer = await session.get(Player, event.get_user_id())
        if buyer.gold < trade_row.price:
            await buy_equip_cmd.finish(f"❌ 金币不足，需要 {trade_row.price} (当前 {buyer.gold})")

        # 税费
        tax = int(trade_row.price * 0.05) if trade_row.price > 10000 else 0
        seller_gain = trade_row.price - tax

        # 转移金币
        buyer.gold -= trade_row.price
        seller = await session.get(Player, trade_row.seller_id)
        seller.gold += seller_gain

        # 转移装备所有权
        equip = trade_row.equip
        equip.player_id = event.get_user_id()
        equip.on_market = False
        equip.equipped = False

        # 删除交易记录
        await session.delete(trade_row)
        await session.commit()

        tpl = equip.template
        tax_info = f"📝 税费 {tax}金币 (5%)" if tax else ""
        msg = [
            f"✅ 购买 {tpl.name} 成功！",
            f"💸 支付：{trade_row.price}金币",
            f"🏦 卖家到账：{seller_gain}金币",
            tax_info,
        ]
        await buy_equip_cmd.finish("\n".join([m for m in msg if m]))

# ---------------- 下架装备 ----------------
remove_equip_cmd = on_command("装备下架", block=True, priority=5)

@remove_equip_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text.isdigit():
        await remove_equip_cmd.finish("格式：装备下架 交易ID")
    trade_id = int(arg_text)

    async with safe_session() as session:
        trade_row = await session.get(TradeEquip, trade_id)
        if not trade_row or trade_row.seller_id != event.get_user_id():
            await remove_equip_cmd.finish("❌ 交易不存在或没有权限")
        # 避免懒加载 equip 关系
        equip = await session.get(EquipmentInstance, trade_row.equip_id)
        equip.on_market = False
        await session.delete(trade_row)
        await session.commit()
        await remove_equip_cmd.finish(f"🔻 已下架 {equip.template.name}") 