"""
周主题氛围系统

每周轮换一个都市怪谈主题，影响游戏氛围、材料掉落、NPC状态等
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum


class WeeklyTheme(str, Enum):
    """周主题枚举"""
    MIRROR_REFLECTION = "镜中人"        # 镜子/倒影相关
    FOURTH_PERSON = "第四人"            # 多出来的人
    STAIRWELL_ECHO = "楼梯间回声"       # 楼梯/声音相关
    MIDNIGHT_KNOCK = "午夜敲门"         # 敲门/访客相关
    SHADOW_FOLLOWER = "影子尾随"        # 影子/跟踪相关
    ELEVATOR_DESCENT = "电梯坠落"       # 电梯相关
    PHONE_CALL = "来电显示"             # 电话/通讯相关


# 主题配置
THEME_CONFIG: Dict[WeeklyTheme, Dict] = {
    WeeklyTheme.MIRROR_REFLECTION: {
        "name": "镜中人",
        "description": "镜子里的你，比你晚了0.3秒才动...",
        "emoji": "🪞",
        "related_locations": ["卫生间", "试衣间", "理发店", "舞蹈室"],
        "material_boost": {
            "cursed_mirror_shard": 1.5,     # 诅咒镜片掉率+50%
            "phantom_thread": 1.3,          # 幻影丝线掉率+30%
        },
        "atmosphere_texts": [
            "镜子里的你眨了眨眼，但你确定自己没有眨。",
            "倒影中多了一个人，站在你身后，但转身后什么都没有。",
            "镜面起雾了，有人从里面写下了你的名字。",
            "你看到镜中的自己在微笑，但你的脸上没有表情。"
        ]
    },
    WeeklyTheme.FOURTH_PERSON: {
        "name": "第四人",
        "description": "三个人的合影里，总是会多出一张脸...",
        "emoji": "👤",
        "related_locations": ["电影院", "KTV", "聚会厅", "包厢"],
        "material_boost": {
            "soul_crystal": 1.5,            # 灵魂结晶掉率+50%
            "nightmare_silk": 1.3,          # 梦魇丝绸掉率+30%
        },
        "atmosphere_texts": [
            "你数了数房间里的人，明明只有三个，为什么有四个影子？",
            "照片洗出来后，角落里多了一张模糊的脸。",
            "电梯显示载重四人，但里面明明只有你们三个。",
            "有人在叫你的名字，但你的朋友都说他们没开口。"
        ]
    },
    WeeklyTheme.STAIRWELL_ECHO: {
        "name": "楼梯间回声",
        "description": "你在13楼，却听到14楼传来自己的脚步声...",
        "emoji": "🪜",
        "related_locations": ["楼梯间", "天台", "消防通道", "地下室"],
        "material_boost": {
            "ghost_bone": 1.5,              # 鬼骨掉率+50%
            "yin_iron": 1.3,                # 阴铁掉率+30%
        },
        "atmosphere_texts": [
            "楼梯间的脚步声在你停下后，又多响了三声。",
            "你往上走了十分钟，楼层指示牌还是显示3楼。",
            "有人在楼上唱歌，声音越来越近，但始终看不到人。",
            "消防通道的门自己关上了，门把手是温热的。"
        ]
    },
    WeeklyTheme.MIDNIGHT_KNOCK: {
        "name": "午夜敲门",
        "description": "凌晨三点的敲门声，门外没有人，猫眼里一片漆黑...",
        "emoji": "🚪",
        "related_locations": ["住宅", "旅馆", "公寓", "宿舍"],
        "material_boost": {
            "flesh_crystal": 1.5,           # 血肉结晶掉率+50%
            "cursed_talisman": 1.3,         # 诅咒符纸掉率+30%
        },
        "atmosphere_texts": [
            "敲门声很有节奏：三长两短，三长两短，一直重复。",
            "你透过猫眼看出去，走廊里站着一个背对你的人。",
            "门缝下塞进来一张纸条，上面写着'我知道你在里面'。",
            "敲门声停了，但你听到有人在门外数数：一、二、三..."
        ]
    },
    WeeklyTheme.SHADOW_FOLLOWER: {
        "name": "影子尾随",
        "description": "路灯下，你的影子比你先一步转过街角...",
        "emoji": "🌑",
        "related_locations": ["街道", "小巷", "地下通道", "停车场"],
        "material_boost": {
            "void_essence": 1.5,            # 虚空精华掉率+50%
            "demon_heart": 1.3,             # 恶魔之心掉率+30%
        },
        "atmosphere_texts": [
            "你的影子在墙上扭曲成奇怪的形状，像是在挣扎。",
            "路灯熄灭的瞬间，你看到影子朝相反的方向跑了。",
            "地上多了一个影子，它跟着你走，但头是扭曲的。",
            "你停下脚步，影子却又往前走了两步才停下。"
        ]
    },
    WeeklyTheme.ELEVATOR_DESCENT: {
        "name": "电梯坠落",
        "description": "电梯按钮上的-4层，你从未注意过...",
        "emoji": "🛗",
        "related_locations": ["电梯", "高楼", "商场", "医院"],
        "material_boost": {
            "medical_record": 1.5,          # 病历本掉率+50%
            "rusty_chain": 1.3,             # 锈蚀铁链掉率+30%
        },
        "atmosphere_texts": [
            "电梯突然停在两层之间，显示屏上闪烁着'13.5'。",
            "你按了1楼，电梯却一直往下，-1、-2、-3...",
            "电梯里只有你一个人，但镜子里映出了满满一电梯的人。",
            "电梯门打开，外面是一条漆黑的走廊，墙上写着'欢迎回家'。"
        ]
    },
    WeeklyTheme.PHONE_CALL: {
        "name": "来电显示",
        "description": "手机响了，来电显示是你自己的号码...",
        "emoji": "📞",
        "related_locations": ["电话亭", "办公室", "家中", "地铁站"],
        "material_boost": {
            "spirit_stone": 1.5,            # 灵石掉率+50%
            "god_tear": 1.3,                # 神之泪掉率+30%
        },
        "atmosphere_texts": [
            "电话那头传来你自己的声音：'不要回头，它就在你身后。'",
            "未接来电99+，全部来自同一个号码：000-0000-0000。",
            "你接起电话，听到的是自己昨晚的梦话录音。",
            "手机自动拨出了一个号码，通话记录里显示'已接通-72小时'。"
        ]
    }
}


class WeeklyThemeManager:
    """周主题管理器"""
    
    @staticmethod
    def get_current_theme() -> WeeklyTheme:
        """获取当前周主题（基于周数循环）"""
        # 使用ISO周数，确保每周一切换
        current_week = datetime.now().isocalendar()[1]
        themes = list(WeeklyTheme)
        theme_index = current_week % len(themes)
        return themes[theme_index]
    
    @staticmethod
    def get_theme_config(theme: WeeklyTheme = None) -> Dict:
        """获取主题配置"""
        if theme is None:
            theme = WeeklyThemeManager.get_current_theme()
        return THEME_CONFIG.get(theme, {})
    
    @staticmethod
    def get_theme_info() -> str:
        """获取当前主题信息（格式化文本）"""
        from ..config import config as game_config

        theme = WeeklyThemeManager.get_current_theme()
        theme_config = THEME_CONFIG[theme]

        # 计算本周剩余天数
        now = datetime.now()
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7

        lines = [
            f"🌙 本周主题：{theme_config['emoji']} {theme_config['name']}",
            "━━━━━━━━━━━━━",
            f"📖 {theme_config['description']}",
            "",
            "✨ 主题效果：",
        ]

        # 材料加成（显示中文名称）
        if theme_config.get("material_boost"):
            lines.append("📦 材料掉落加成：")
            for material_id, boost in theme_config["material_boost"].items():
                boost_pct = int((boost - 1) * 100)
                # 尝试从配置中获取材料中文名
                try:
                    material_name = game_config.items_config["by_id"].get(material_id, {}).name or material_id
                except (AttributeError, KeyError):
                    material_name = material_id
                lines.append(f"  • {material_name} +{boost_pct}%")

        lines.extend([
            "",
            f"⏰ 距离主题切换还有 {days_until_monday} 天",
            "━━━━━━━━━━━━━",
            "💡 主题每周一自动切换"
        ])

        return "\n".join(lines)
    
    @staticmethod
    def get_random_atmosphere_text(theme: WeeklyTheme = None) -> Optional[str]:
        """获取随机氛围文本"""
        import random
        if theme is None:
            theme = WeeklyThemeManager.get_current_theme()
        config = THEME_CONFIG.get(theme, {})
        texts = config.get("atmosphere_texts", [])
        return random.choice(texts) if texts else None
    
    @staticmethod
    def apply_material_boost(material_id: str, base_quantity: int, theme: WeeklyTheme = None) -> int:
        """应用主题材料加成"""
        if theme is None:
            theme = WeeklyThemeManager.get_current_theme()
        config = THEME_CONFIG.get(theme, {})
        boost_map = config.get("material_boost", {})
        
        if material_id in boost_map:
            boost = boost_map[material_id]
            return int(base_quantity * boost)
        
        return base_quantity
    
    @staticmethod
    def is_location_boosted(location_name: str, theme: WeeklyTheme = None) -> bool:
        """检查地点是否受主题加成"""
        if theme is None:
            theme = WeeklyThemeManager.get_current_theme()
        config = THEME_CONFIG.get(theme, {})
        related_locations = config.get("related_locations", [])
        
        # 模糊匹配
        return any(loc in location_name for loc in related_locations)

