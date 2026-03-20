"""
赞助商店服务

管理诡烛氪金货币和赞助专属服务：
- 购买自定义称号（500诡烛）
- 购买改名卡（10诡烛）
- 公会改名（200诡烛）
- 购买棺材钉（50诡烛）
- 购买哭坟帽（20诡烛）
- 购买重启符（1000诡烛/张）
- 购买初级月卡（88诡烛/月）
- 购买高级月卡（288诡烛/月）
"""
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.player import Player


# ==================== 价格常量 ====================

CUSTOM_TITLE_PRICE = 500    # 自定义称号（诡烛）
RENAME_CARD_PRICE = 10      # 改名卡（诡烛）
GUILD_RENAME_PRICE = 200    # 公会改名（诡烛）
COFFIN_NAIL_PRICE = 50      # 棺材钉（诡烛）
CRYING_TOMB_HAT_PRICE = 20  # 哭坟帽（诡烛）
BASIC_MONTHLY_CARD_PRICE = 88    # 初级月卡（诡烛/月）
PREMIUM_MONTHLY_CARD_PRICE = 288 # 高级月卡（诡烛/月）
INVENTORY_EXPAND_PRICE = 10      # 背包扩容（诡烛/格）
INVENTORY_EXPAND_MAX = 1000      # 背包容量上限
RESET_TALISMAN_PRICE = 1000      # 重启符（诡烛/张）

# ==================== 月卡特权价格 ====================
PREMIUM_SECLUSION_PRICE = 180     # 闭关无上限特权（诡烛/月）
PREMIUM_WAREHOUSE_PRICE = 180     # 远程仓库特权（诡烛/月）
PREMIUM_FISHING_PRICE = 180       # 鱼竿特权（诡烛/月）
PREMIUM_VISION_PRICE = 180        # 全视之眼特权（诡烛/月）

# 称号字符限制
TITLE_MIN_LEN = 1
TITLE_MAX_LEN = 8

# 禁止词（防止滥用）
TITLE_FORBIDDEN_CHARS = set("@#$%^&*<>|\\//\n\r\t")
TITLE_FORBIDDEN_WORDS = ["管理", "Admin", "admin", "系统", "官方", "GM", "gm"]


# ==================== 存储键 ====================

_SPONSOR_KEY = "sponsor"
_CUSTOM_TITLE_KEY = "custom_title"
_OWNED_TITLES_KEY = "owned_titles"


class SponsorShopService:
    """赞助商店核心服务（无状态，操作 player.extra_attrs）"""

    # ==================== 内部辅助 ====================

    @classmethod
    def _get_sponsor_data(cls, player: Player) -> dict:
        """获取赞助数据字典（如不存在则返回空字典）"""
        attrs = player.extra_attrs or {}
        return attrs.get(_SPONSOR_KEY, {})

    @classmethod
    def _set_sponsor_data(cls, player: Player, data: dict) -> None:
        """写回赞助数据（深度更新 extra_attrs）"""
        if player.extra_attrs is None:
            player.extra_attrs = {}
        player.extra_attrs[_SPONSOR_KEY] = data
        # 触发 SQLAlchemy MutableDict 脏标记
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(player, "extra_attrs")

    # ==================== 称号查询 ====================

    @classmethod
    def get_active_custom_title(cls, player: Player) -> Optional[str]:
        """获取当前激活的自定义称号，无则返回 None"""
        sdata = cls._get_sponsor_data(player)
        return sdata.get(_CUSTOM_TITLE_KEY) or None

    @classmethod
    def get_owned_custom_titles(cls, player: Player) -> List[str]:
        """获取玩家拥有的所有自定义称号"""
        sdata = cls._get_sponsor_data(player)
        return sdata.get(_OWNED_TITLES_KEY, [])

    # ==================== 称号购买 ====================

    @classmethod
    def validate_title_text(cls, title: str) -> Tuple[bool, str]:
        """
        校验称号文字合法性

        Returns:
            (合法, 错误原因)
        """
        title = title.strip()
        if not title:
            return False, "称号不能为空"
        if len(title) < TITLE_MIN_LEN:
            return False, f"称号至少需要 {TITLE_MIN_LEN} 个字符"
        if len(title) > TITLE_MAX_LEN:
            return False, f"称号最多 {TITLE_MAX_LEN} 个字符，当前 {len(title)} 个"
        for ch in TITLE_FORBIDDEN_CHARS:
            if ch in title:
                return False, "称号包含非法字符"
        for word in TITLE_FORBIDDEN_WORDS:
            if word.lower() in title.lower():
                return False, f"称号包含禁用词汇「{word}」"
        return True, ""

    @classmethod
    async def buy_custom_title(cls, player: Player, title_text: str, session: AsyncSession) -> Tuple[bool, str]:
        """
        购买自定义称号（500诡烛）

        Returns:
            (成功, 结果消息)
        """
        title_text = title_text.strip()

        ok, err = cls.validate_title_text(title_text)
        if not ok:
            return False, f"⛔ 称号无效：{err}"

        owned = cls.get_owned_custom_titles(player)
        if title_text in owned:
            return False, f"⛔ 你已拥有称号「{title_text}」，无需重复购买\n💡 使用【切换称号 {title_text}】可将其设为当前称号"

        if player.gui_zhu < CUSTOM_TITLE_PRICE:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {CUSTOM_TITLE_PRICE} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        balance_before = player.gui_zhu
        player.gui_zhu -= CUSTOM_TITLE_PRICE
        sdata = cls._get_sponsor_data(player)
        owned_list = sdata.get(_OWNED_TITLES_KEY, [])
        owned_list.append(title_text)
        sdata[_OWNED_TITLES_KEY] = owned_list
        sdata[_CUSTOM_TITLE_KEY] = title_text
        cls._set_sponsor_data(player, sdata)

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "自定义称号", title_text, CUSTOM_TITLE_PRICE, balance_before)

        return True, (
            f"✅ 购买成功！获得自定义称号「{title_text}」\n"
            f"已自动设为当前称号\n"
            f"💡 使用【切换称号】管理所有称号\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 称号切换 ====================

    @classmethod
    def switch_custom_title(cls, player: Player, title_text: str) -> Tuple[bool, str]:
        """
        切换到指定自定义称号（或卸下，传空字符串）

        Returns:
            (成功, 结果消息)
        """
        sdata = cls._get_sponsor_data(player)
        owned = sdata.get(_OWNED_TITLES_KEY, [])

        if not title_text:
            if not sdata.get(_CUSTOM_TITLE_KEY):
                return False, "当前没有激活的自定义称号"
            sdata[_CUSTOM_TITLE_KEY] = ""
            cls._set_sponsor_data(player, sdata)
            return True, "已卸下自定义称号"

        if title_text not in owned:
            return False, f"你没有自定义称号「{title_text}」"

        sdata[_CUSTOM_TITLE_KEY] = title_text
        cls._set_sponsor_data(player, sdata)
        return True, f"已将自定义称号切换为「{title_text}」"

    # ==================== 改名卡购买 ====================

    @classmethod
    async def buy_rename_card(cls, player: Player, session: AsyncSession) -> Tuple[bool, str]:
        """
        购买改名卡（10诡烛，获得1张改名卡进背包）

        Returns:
            (成功, 结果消息)
        """
        if player.gui_zhu < RENAME_CARD_PRICE:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {RENAME_CARD_PRICE} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        from ..models.inventory import ItemInstance
        success = await ItemInstance.add_item(session, player.id, "rename_card", 1)
        if not success:
            return False, "⛔ 背包已满，无法添加改名卡"

        balance_before = player.gui_zhu
        player.gui_zhu -= RENAME_CARD_PRICE

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "改名卡", "×1", RENAME_CARD_PRICE, balance_before)

        return True, (
            f"✅ 购买成功！获得改名卡 ×1\n"
            f"💡 使用【改名 新名字】修改角色昵称\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 公会改名 ====================

    @classmethod
    async def buy_guild_rename(
        cls, player: Player, new_name: str, session: AsyncSession
    ) -> Tuple[bool, str]:
        """
        公会改名（200诡烛，需为公会会长）

        Returns:
            (成功, 结果消息)
        """
        from sqlalchemy import select
        from ..models.guild import Guild

        new_name = new_name.strip()

        # 校验新名称
        if not new_name:
            return False, "⛔ 公会名称不能为空"
        if len(new_name) > 16:
            return False, "⛔ 公会名称不能超过16个字符"

        # 检查玩家是否在公会
        if not player.guild_id:
            return False, "⛔ 你还未加入任何公会"

        # 获取公会
        guild = await session.get(Guild, player.guild_id)
        if not guild:
            return False, "⛔ 公会信息异常"

        # 检查是否为会长
        if guild.president_id != player.id:
            return False, "⛔ 只有会长才能使用公会改名服务"

        # 检查名称相同
        if guild.name == new_name:
            return False, f"⛔ 公会名称已经是「{new_name}」了"

        # 检查名称重复
        existing = await session.execute(
            select(Guild).where(Guild.name == new_name)
        )
        if existing.scalars().first():
            return False, f"⛔ 已存在名为「{new_name}」的公会"

        # 检查诡烛余额
        if player.gui_zhu < GUILD_RENAME_PRICE:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {GUILD_RENAME_PRICE} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        # 执行改名
        old_name = guild.name
        guild.name = new_name
        session.add(guild)
        balance_before = player.gui_zhu
        player.gui_zhu -= GUILD_RENAME_PRICE

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "公会改名", f"{old_name}→{new_name}", GUILD_RENAME_PRICE, balance_before)

        return True, (
            f"✅ 公会改名成功！\n"
            f"📛 {old_name} → {new_name}\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 棺材钉购买 ====================

    @classmethod
    async def buy_coffin_nail(cls, player: Player, session: AsyncSession) -> Tuple[bool, str]:
        """
        购买棺材钉（50诡烛，获得1根棺材钉进背包）

        Returns:
            (成功, 结果消息)
        """
        if player.gui_zhu < COFFIN_NAIL_PRICE:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {COFFIN_NAIL_PRICE} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        from ..models.inventory import ItemInstance
        try:
            await ItemInstance.add_item(session, player.id, "coffin_nail", 1)
        except ValueError:
            return False, "⛔ 背包已满，无法添加棺材钉"

        balance_before = player.gui_zhu
        player.gui_zhu -= COFFIN_NAIL_PRICE

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "棺材钉", "×1", COFFIN_NAIL_PRICE, balance_before)

        return True, (
            f"✅ 购买成功！获得棺材钉 ×1\n"
            f"💡 持有棺材钉可提升闭关效率（最多100根，+50%）\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 哭坟帽购买 ====================

    @classmethod
    async def buy_crying_tomb_hat(cls, player: Player, session: AsyncSession) -> Tuple[bool, str]:
        """
        购买哭坟帽（20诡烛，获得1顶哭坟帽进背包）

        Returns:
            (成功, 结果消息)
        """
        if player.gui_zhu < CRYING_TOMB_HAT_PRICE:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {CRYING_TOMB_HAT_PRICE} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        from ..models.inventory import ItemInstance
        try:
            await ItemInstance.add_item(session, player.id, "resentment_crystal", 1)
        except ValueError:
            return False, "⛔ 背包已满，无法添加哭坟帽"

        balance_before = player.gui_zhu
        player.gui_zhu -= CRYING_TOMB_HAT_PRICE

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "哭坟帽", "×1", CRYING_TOMB_HAT_PRICE, balance_before)

        return True, (
            f"✅ 购买成功！获得哭坟帽 ×1\n"
            f"💡 使用后直接获得1万怨念值\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 背包扩容 ====================

    @classmethod
    async def expand_inventory(cls, player: Player, slots: int, session: AsyncSession) -> Tuple[bool, str]:
        """
        背包永久扩容（10诡烛/格）

        Returns:
            (成功, 结果消息)
        """
        if slots <= 0:
            return False, "⛔ 扩容格数必须大于0"

        old_capacity = player.inventory_capacity
        if old_capacity >= INVENTORY_EXPAND_MAX:
            return False, f"⛔ 背包已达上限 {INVENTORY_EXPAND_MAX} 格，无法继续扩容"

        # 先算实际可扩格数（受上限约束），再按实际格数收费
        actual_slots = min(slots, INVENTORY_EXPAND_MAX - old_capacity)
        total_cost = INVENTORY_EXPAND_PRICE * actual_slots

        if player.gui_zhu < total_cost:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {total_cost} 诡烛（{actual_slots}格 × {INVENTORY_EXPAND_PRICE}诡烛）\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        new_capacity = old_capacity + actual_slots
        balance_before = player.gui_zhu
        player.inventory_capacity = new_capacity
        player.gui_zhu -= total_cost

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "背包扩容", f"+{actual_slots}格({old_capacity}→{new_capacity})", total_cost, balance_before)

        msg = (
            f"✅ 背包扩容成功！永久增加 {actual_slots} 格\n"
            f"📦 背包容量: {old_capacity} → {new_capacity}\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )
        if actual_slots < slots:
            msg += f"\n⚠️ 已接近上限，实际扩容 {actual_slots} 格"
        return True, msg

    # ==================== 重启符购买 ====================

    @classmethod
    async def buy_reset_talisman(cls, player: Player, quantity: int, session: AsyncSession) -> Tuple[bool, str]:
        """
        购买重启符（1000诡烛/张，进背包使用）

        Returns:
            (成功, 结果消息)
        """
        if quantity <= 0:
            return False, "⛔ 购买数量必须大于0"

        total_cost = RESET_TALISMAN_PRICE * quantity

        if player.gui_zhu < total_cost:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {total_cost} 诡烛（{quantity}张 × {RESET_TALISMAN_PRICE}诡烛）\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        from ..models.inventory import ItemInstance
        try:
            await ItemInstance.add_item(session, player.id, "reset_scroll", quantity)
        except ValueError:
            return False, "⛔ 背包已满，无法添加重启符"

        balance_before = player.gui_zhu
        player.gui_zhu -= total_cost

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, "重启符", f"×{quantity}", total_cost, balance_before)

        return True, (
            f"✅ 购买成功！获得重启符 ×{quantity}\n"
            f"💡 使用【使用 重启符】可重置所有已分配属性点\n"
            f"💡 装备加成、丹药加成、VIP加成均会保留\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 月卡购买 ====================

    @classmethod
    async def buy_monthly_card(
        cls, player: Player, card_type: str, session: AsyncSession
    ) -> Tuple[bool, str]:
        """
        购买月卡（初级88诡烛/高级288诡烛，30天有效期，可叠加）

        card_type: "basic" | "premium"

        Returns:
            (成功, 结果消息)
        """
        from ..models.monthly_card import MonthlyCard, CardType, get_card_benefits_config

        if card_type == "basic":
            price = BASIC_MONTHLY_CARD_PRICE
            ct = CardType.BASIC
        else:
            price = PREMIUM_MONTHLY_CARD_PRICE
            ct = CardType.PREMIUM

        if player.gui_zhu < price:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {price} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        card = await MonthlyCard.add_monthly_card(session, player.id, ct, months=1)
        balance_before = player.gui_zhu
        player.gui_zhu -= price

        card_config = get_card_benefits_config()
        card_name = card_config[ct]["name"]

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(session, player, card_name, f"至{card.end_time.strftime('%Y-%m-%d')}", price, balance_before)

        return True, (
            f"✅ 购买成功！获得{card_name} ×1个月\n"
            f"⏰ 到期时间: {card.end_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"💡 使用【月卡】查看当前权益\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    # ==================== 月卡特权购买 ====================

    @classmethod
    async def buy_premium_privilege(
        cls, player: Player, privilege_key: str, privilege_name: str, price: int, session: AsyncSession
    ) -> Tuple[bool, str]:
        """
        购买月卡型特权（30天有效期，可叠加延长）
        """
        if player.gui_zhu < price:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {price} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        from datetime import datetime, timedelta

        extra = player.extra_attrs or {}
        current_until = extra.get(privilege_key)
        now = datetime.now()

        if current_until:
            try:
                existing_end = datetime.fromisoformat(current_until)
                if existing_end > now:
                    new_end = existing_end + timedelta(days=30)
                else:
                    new_end = now + timedelta(days=30)
            except (ValueError, TypeError):
                new_end = now + timedelta(days=30)
        else:
            new_end = now + timedelta(days=30)

        extra[privilege_key] = new_end.isoformat()
        player.extra_attrs = extra

        balance_before = player.gui_zhu
        player.gui_zhu -= price

        from ..models.sponsor_shop_log import SponsorShopLog
        await SponsorShopLog.add_log(
            session, player, privilege_name,
            f"至{new_end.strftime('%Y-%m-%d')}",
            price, balance_before
        )

        return True, (
            f"✅ 购买成功！{privilege_name}\n"
            f"⏰ 有效期至: {new_end.strftime('%Y-%m-%d %H:%M')}\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

    @staticmethod
    def is_privilege_active(player: Player, privilege_key: str) -> bool:
        """检查玩家的某项月卡特权是否在有效期内"""
        from datetime import datetime
        extra = player.extra_attrs or {}
        until_str = extra.get(privilege_key)
        if not until_str:
            return False
        try:
            return datetime.fromisoformat(until_str) > datetime.now()
        except (ValueError, TypeError):
            return False

    # ==================== 商店展示 ====================

    @classmethod
    def get_shop_info(cls, player: Player) -> str:
        """生成商店展示文本"""
        balance = player.gui_zhu
        owned_titles = cls.get_owned_custom_titles(player)
        active_title = cls.get_active_custom_title(player)

        lines = [
            "🕯️ 诡修仙 赞助商店",
            "━━━━━━━━━━━━━",
            f"💰 诡烛余额: {balance} 诡烛",
            "━━━━━━━━━━━━━",
            "",
            "⚔️ 修炼 & 战斗",
            "─────────────",
            f"⚰️ 棺材钉  [{COFFIN_NAIL_PRICE} 诡烛]",
            f"  闭关效率+0.5%（最多100根，+50%）",
            "",
            f"🎩 哭坟帽  [{CRYING_TOMB_HAT_PRICE} 诡烛]",
            f"  使用后获得1万怨念值",
            "",
            f"🔄 重启符  [{RESET_TALISMAN_PRICE} 诡烛/张]",
            f"  重置所有属性点，装备/丹药/VIP加成保留",
            "",
            "━━━━━━━━━━━━━",
            "💳 月卡特权",
            "─────────────",
            f"💳 初级月卡  [{BASIC_MONTHLY_CARD_PRICE} 诡烛/月]",
            f"  修炼+20%，闭关9h，背包+5，突破保护75%",
            f"  🔧一键修复 / ⚙️一键献祭 / ⚔️一键升阶",
            f"  签到咒抗上限+5，签到月卡宝箱×1",
            "",
            f"💎 高级月卡  [{PREMIUM_MONTHLY_CARD_PRICE} 诡烛/月]",
            f"  修炼+50%，闭关12h，背包+20，突破保护80%",
            f"  🔧一键修复 / ⚙️一键献祭 / ⚔️一键升阶",
            f"  🤖自动采集，签到咒抗上限+5，签到月卡宝箱×3",
            "",
            "━━━━━━━━━━━━━",
            "🎒 背包 & 身份",
            "─────────────",
            f"🎒 背包扩容  [{INVENTORY_EXPAND_PRICE} 诡烛/格]",
            f"  永久增加1格背包容量，上限{INVENTORY_EXPAND_MAX}格",
            "",
            f"✍️ 改名卡  [{RENAME_CARD_PRICE} 诡烛]",
            f"  修改一次角色名称",
            "",
            f"🏛️ 公会改名  [{GUILD_RENAME_PRICE} 诡烛]",
            f"  会长专属，修改公会名称",
            "",
            f"📛 自定义称号  [{CUSTOM_TITLE_PRICE} 诡烛]",
            f"  设置专属展示称号 ({TITLE_MIN_LEN}-{TITLE_MAX_LEN}字)",
            "",
        ]

        if owned_titles:
            lines.extend([
                "━━━━━━━━━━━━━",
                "🏷️ 已拥有自定义称号:",
                "─────────────",
            ])
            for t in owned_titles:
                mark = " ◀ 当前" if t == active_title else ""
                lines.append(f"  「{t}」{mark}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━",
            "🐾 宠物饰品（诡烛专属）",
            "─────────────",
            "🟣 虚空锁链  [150 诡烛]  颈饰 攻+20 防+15",
            "🟣 诡纹和服  [150 诡烛]  服饰 攻+15 暴击+1.5%",
            "🟠 星辰发冠  [300 诡烛]  头饰 暴击率+3% 暴击伤害+10%",
            "🟠 银铃璎珞  [300 诡烛]  颈饰 连击率+3% 穿透率+3%",
            "🟠 流光羽衣  [300 诡烛]  服饰 闪避率+3% 反击率+3%",
            "  💡 购买: 【买饰品 名称】",
            "",
            "━━━━━━━━━━━━━",
            f"🕯️ 赞助特权（180 诡烛/月）",
            "─────────────",
            f"⏰ 闭关无上限  [{PREMIUM_SECLUSION_PRICE} 诡烛/月]",
            "  闭关不再有时间上限",
            "",
            f"🏠 远程仓库    [{PREMIUM_WAREHOUSE_PRICE} 诡烛/月]",
            "  随时随地存取阴宅仓库",
            "",
            f"🎣 鱼竿特权    [{PREMIUM_FISHING_PRICE} 诡烛/月]",
            "  每次钓鱼额外多钓2条",
            "",
            f"👁️ 全视之眼    [{PREMIUM_VISION_PRICE} 诡烛/月]",
            "  俯瞰直接显示诡域全部方块",
            "",
        ])

        lines.extend([
            "━━━━━━━━━━━━━",
            "📖 使用方法:",
            "─────────────",
            "【购买棺材钉】       获得1根棺材钉",
            "【购买哭坟帽】       获得1顶哭坟帽",
            "【购买重启符 N】     购买N张重启符（默认1张）",
            "【背包扩容 N】       永久扩容N格（10诡烛/格）",
            "【购买初级月卡】     购买30天初级月卡",
            "【购买高级月卡】     购买30天高级月卡",
            "【购买改名卡】       获得1张改名卡",
            "【购买称号 内容】    购买自定义称号",
            "【公会改名 新名称】  修改公会名称（会长）",
            "【改名 新名字】      使用改名卡改名",
            "【购买闭关特权】     闭关无时间上限（180诡烛/月）",
            "【购买远程仓库】     随地存取阴宅仓库（180诡烛/月）",
            "【购买鱼竿特权】     每次多钓2条鱼（180诡烛/月）",
            "【购买全视之眼】     俯瞰显示全部方块（180诡烛/月）",
        ])

        return "\n".join(lines)
