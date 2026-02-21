"""
赞助商店服务

管理诡烛氪金货币和赞助专属服务：
- 购买自定义称号（500诡烛）
- 购买改名卡（10诡烛）
- 公会改名（200诡烛）
"""
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.player import Player


# ==================== 价格常量 ====================

CUSTOM_TITLE_PRICE = 500    # 自定义称号（诡烛）
RENAME_CARD_PRICE = 10      # 改名卡（诡烛）
GUILD_RENAME_PRICE = 200    # 公会改名（诡烛）

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
    def buy_custom_title(cls, player: Player, title_text: str) -> Tuple[bool, str]:
        """
        购买自定义称号（纯内存操作，由调用方提交事务）

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

        player.gui_zhu -= CUSTOM_TITLE_PRICE
        sdata = cls._get_sponsor_data(player)
        owned_list = sdata.get(_OWNED_TITLES_KEY, [])
        owned_list.append(title_text)
        sdata[_OWNED_TITLES_KEY] = owned_list
        sdata[_CUSTOM_TITLE_KEY] = title_text
        cls._set_sponsor_data(player, sdata)

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

        player.gui_zhu -= RENAME_CARD_PRICE
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
        player.gui_zhu -= GUILD_RENAME_PRICE

        return True, (
            f"✅ 公会改名成功！\n"
            f"📛 {old_name} → {new_name}\n"
            f"🔮 剩余诡烛: {player.gui_zhu}"
        )

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
            "",
            "🛒 商品列表:",
            f"  ✍️  改名卡          [{RENAME_CARD_PRICE} 诡烛]",
            f"     修改一次角色名称",
            f"  🏛️  公会改名        [{GUILD_RENAME_PRICE} 诡烛]",
            f"     会长专属，修改公会名称",
            f"  📛  自定义称号      [{CUSTOM_TITLE_PRICE} 诡烛]",
            f"     设置专属展示称号 ({TITLE_MIN_LEN}-{TITLE_MAX_LEN}字)",
            "",
        ]

        if owned_titles:
            lines.append("🏷️ 已拥有自定义称号:")
            for t in owned_titles:
                mark = " ◀ 当前" if t == active_title else ""
                lines.append(f"  「{t}」{mark}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━",
            "📖 使用方法:",
            "【购买改名卡】       获得1张改名卡",
            "【购买称号 内容】    购买自定义称号",
            "【公会改名 新名称】  修改公会名称（会长）",
            "【改名 新名字】      使用改名卡改名",
        ])

        return "\n".join(lines)
