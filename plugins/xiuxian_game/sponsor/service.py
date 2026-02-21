"""
赞助商店服务

管理诡烛氪金货币和赞助专属服务：
- 查询诡烛余额
- 购买/管理自定义称号
"""
from typing import Optional, List, Tuple
from ..models.player import Player


# ==================== 常量配置 ====================

# 自定义称号价格（诡烛）
CUSTOM_TITLE_PRICE = 500

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
        购买自定义称号

        流程：
        1. 校验称号文字
        2. 检查不与已有称号重复
        3. 扣除诡烛
        4. 存储称号，设为当前激活
        5. 返回结果

        Returns:
            (成功, 结果消息)
        """
        title_text = title_text.strip()

        # 1. 校验文字
        ok, err = cls.validate_title_text(title_text)
        if not ok:
            return False, f"⛔ 称号无效：{err}"

        # 2. 检查是否已有完全相同的称号
        owned = cls.get_owned_custom_titles(player)
        if title_text in owned:
            return False, f"⛔ 你已拥有称号「{title_text}」，无需重复购买\n💡 使用【切换称号 {title_text}】可将其设为当前称号"

        # 3. 检查诡烛余额
        if player.gui_zhu < CUSTOM_TITLE_PRICE:
            return False, (
                f"⛔ 诡烛不足\n"
                f"需要: {CUSTOM_TITLE_PRICE} 诡烛\n"
                f"当前: {player.gui_zhu} 诡烛"
            )

        # 4. 扣除诡烛，存储称号
        player.gui_zhu -= CUSTOM_TITLE_PRICE
        sdata = cls._get_sponsor_data(player)
        owned_list = sdata.get(_OWNED_TITLES_KEY, [])
        owned_list.append(title_text)
        sdata[_OWNED_TITLES_KEY] = owned_list
        sdata[_CUSTOM_TITLE_KEY] = title_text   # 自动设为激活称号
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
            # 卸下
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
            f"  📛 自定义称号  [{CUSTOM_TITLE_PRICE} 诡烛]",
            f"     设置专属展示称号 ({TITLE_MIN_LEN}-{TITLE_MAX_LEN}字)",
            f"     购买后永久拥有，可随时切换",
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
            "【购买称号 称号内容】 购买自定义称号",
            "【切换称号 称号内容】 切换激活称号",
            "【卸下称号】 取消展示称号",
        ])

        return "\n".join(lines)
