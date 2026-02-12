"""
除夕叩门活动 — 配置文件

定义诡事类型、叙事文本池、奖励参数、活动商店等
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ==================== 诡事类型配置 ====================

@dataclass
class GhostEventType:
    """诡事类型定义"""
    type_id: str           # 类型ID
    name: str              # 类型名称
    npc_prefix: str        # NPC名前缀
    description: str       # 简短说明
    tier: str              # 强度: basic / medium / elite / boss
    weight: int            # 刷新权重
    hp_mult: float         # HP倍率
    atk_mult: float        # 攻击倍率
    def_mult: float        # 防御倍率
    agi_mult: float        # 敏捷倍率
    reward_mult: float     # 奖励倍率
    shard_reward: int      # 碎片奖励
    material_drop_rate: float  # 材料掉落概率
    narratives: List[str] = field(default_factory=list)  # 叙事池
    special_mechanic: str = ""  # 特殊机制描述


# NPC名字池
GHOST_NAMES = [
    "王二", "李三", "张氏", "赵四", "陈五", "孙六",
    "周七", "吴八", "郑九", "冯十", "褚十一", "卫十二",
    "无名者", "丁某", "曹某", "严某", "魏某", "蒋某",
]

# 城市/地名池
CITY_NAMES = [
    "旧城区", "月光巷", "雾影街", "鬼门胡同", "幽冥路",
    "黄泉渡口", "枯井坊", "断桥弄", "灯笼街", "纸人铺",
    "陈家老宅", "废弃学堂", "旧停尸房", "烂尾楼",
    "地下通道", "临江码头", "城隍庙", "义庄旧址",
]


# ==================== 五类诡事定义 ====================

GHOST_EVENT_TYPES: Dict[str, GhostEventType] = {
    "knock_curse": GhostEventType(
        type_id="knock_curse",
        name="叩门诅咒",
        npc_prefix="鬼仆",
        description="被敲门鬼诅咒死后沦为仆从的亡者残骸",
        tier="basic",
        weight=35,
        hp_mult=1.0, atk_mult=1.0, def_mult=1.0, agi_mult=1.0,
        reward_mult=1.0, shard_reward=1, material_drop_rate=0.05,
        narratives=[
            "{地名}老宅区，住户连续三夜听到沉闷敲门声。第一夜后指甲发黑，第二夜后左臂皮肤大面积溃烂。敲门声仍在继续。",
            "{地名}出租屋内发现一具尸体，面部完全腐烂，但死者手机通话记录显示，死前最后一句话是：'有人在敲门，我去开——'",
            "{地名}街道监控拍到异常画面：凌晨三点，一个没有面孔的人形站在某户门前，缓缓抬手，叩了三下。门内随即传出惨叫。",
        ],
    ),
    "domain_seep": GhostEventType(
        type_id="domain_seep",
        name="鬼域渗透",
        npc_prefix="渗界仆从",
        description="从敲门鬼鬼域裂隙中爬出的亡者",
        tier="medium",
        weight=20,
        hp_mult=1.3, atk_mult=1.2, def_mult=1.2, agi_mult=1.1,
        reward_mult=1.3, shard_reward=2, material_drop_rate=0.10,
        narratives=[
            "{地名}地面出现一道细长裂缝，透过裂缝能看到灰色的另一个世界——和这里一模一样的街道，但所有窗户都是黑的，街上游荡着面目模糊的人影。有东西正在往外爬。",
            "{地名}居民报告：家中镜子映出的不再是自己的房间，而是一条灰暗的走廊，走廊尽头有无数人影在排队——排队走向一扇门。镜面开始往外渗水。",
        ],
    ),
    "audio_spread": GhostEventType(
        type_id="audio_spread",
        name="录音扩散",
        npc_prefix="咒音残响",
        description="录音中凝聚成形的敲门声实体",
        tier="medium",
        weight=20,
        hp_mult=1.3, atk_mult=1.2, def_mult=1.2, agi_mult=1.1,
        reward_mult=1.3, shard_reward=2, material_drop_rate=0.10,
        narratives=[
            "紧急！修士通讯频道被投放了一段音频，内容为三声沉闷的敲门声。已有数十人收听。所有听过的人反馈：耳鸣不止，且每到深夜就能听到自家门外有东西在敲。",
            "{地名}发现一台循环播放敲门声的老式收音机，无法关闭，无法断电，砸碎后碎片仍在发出声响。周围三条街的住户均已出现腐化症状。",
        ],
    ),
    "wish_sticker": GhostEventType(
        type_id="wish_sticker",
        name="愿望贴纸",
        npc_prefix="灯下黑影",
        description="路灯鬼留下的分身/投影",
        tier="elite",
        weight=18,
        hp_mult=2.0, atk_mult=1.5, def_mult=1.5, agi_mult=1.3,
        reward_mult=2.0, shard_reward=3, material_drop_rate=0.20,
        narratives=[
            "{地名}路灯下发现散落的愿望贴纸。一张写着'希望父亲的手术顺利'，背面用血写着'已达成——代价：母亲'。路灯下那个低头的黑影仍然站在那里。",
            "{地名}路口，路灯以不规律频率闪烁。有修士报告：灯灭的瞬间，能看到一个背对自己的黑色人影；灯亮时人影消失，但地上多了一张空白贴纸和一支笔。",
        ],
        special_mechanic="restart",  # 被攻击后有概率恢复30%HP
    ),
    "silent_curse": GhostEventType(
        type_id="silent_curse",
        name="禁字之祸",
        npc_prefix="禁字之祸",
        description='"静悄悄"的物质化分身',
        tier="boss",
        weight=7,
        hp_mult=3.0, atk_mult=2.0, def_mult=1.8, agi_mult=1.5,
        reward_mult=3.5, shard_reward=5, material_drop_rate=0.40,
        narratives=[
            "{地名}出现甲级诡象。一名修士在通讯中说了那个字，话音未落，身边凭空出现一个脏兮兮的小女孩——没有鼻子和嘴巴，只有两个漆黑的眼洞和一双耳朵。修士当场重伤。它在听。",
            "{地名}学堂内，一名教书先生在课上讲到某个字时，教室角落里多了一个人。所有孩子都看到了她——穿着脏污连衣裙，浑身淤青，空洞的眼眶对着先生的方向。现在整间学堂被封锁。",
        ],
        special_mechanic="silence",  # 禁声debuff: 暴击率和连击率各降低10%
    ),
}


# ==================== 刷新参数 ====================

REFRESH_INTERVAL_MINUTES = 30  # 刷新间隔(分钟)
SPAWN_COUNT_RANGE = (3, 5)     # 每波生成数量范围
MAX_ACTIVE_EVENTS = 15         # 同时存在上限
COORD_RANGE = 300              # 坐标范围(-300~300)
EVENT_LIFETIME_MINUTES = 60    # 鬼怪存活时间(分钟)


# ==================== 瞬移参数 ====================

TELEPORT_MAX_DISTANCE = 100    # 瞬移最大曼哈顿距离
TELEPORT_COOLDOWN = 180        # 瞬移冷却时间(秒)
TELEPORT_COORD_RANGE = 500     # 瞬移坐标范围


# ==================== 奖励公式参数 ====================

BASE_EXP = 500           # 基础经验
EXP_PER_LEVEL = 10       # 每等级经验加成
BASE_GOLD = 300          # 基础金币
GOLD_PER_LEVEL = 5       # 每等级金币加成


# ==================== 活动商店配置 ====================

@dataclass
class ShopItem:
    """商店物品定义"""
    item_id: str           # 物品模板ID (items.yaml中的id)
    name: str              # 显示名称
    shard_cost: int        # 碎片价格
    daily_limit: int       # 每日限购(0=无每日限购)
    event_limit: int       # 活动限购(0=无活动限购)
    category: str          # 分区名称
    description: str = ""  # 商店描述(可选,默认用items.yaml)


# 商店物品列表
SHOP_ITEMS: List[ShopItem] = [
    # 【日用补给区】
    ShopItem("knocker_zhenhunxiang", "镇魂香", 3, daily_limit=10, event_limit=0, category="日用补给"),
    ShopItem("knocker_bixiongfu", "避凶符", 5, daily_limit=5, event_limit=0, category="日用补给"),
    ShopItem("knocker_zhoupodan", "咒破丹", 5, daily_limit=5, event_limit=0, category="日用补给"),

    # 【成长加速区】
    ShopItem("spirit_elixir", "升灵丹", 5, daily_limit=8, event_limit=0, category="成长加速"),
    ShopItem("blood_heart_elixir", "血心丹", 12, daily_limit=3, event_limit=0, category="成长加速"),
    ShopItem("upgrade_stone_low", "初级升阶石", 8, daily_limit=3, event_limit=0, category="成长加速"),
    ShopItem("upgrade_stone_mid", "中级升阶石", 25, daily_limit=1, event_limit=0, category="成长加速"),
    ShopItem("life_recovery_elixir", "回生丹", 6, daily_limit=5, event_limit=0, category="成长加速"),

    # 【稀有宝物区】
    ShopItem("knocker_bone_elixir", "敲门鬼的指骨", 30, daily_limit=0, event_limit=3, category="稀有宝物"),
    ShopItem("knocker_wish_elixir", "路灯鬼的愿望", 30, daily_limit=0, event_limit=3, category="稀有宝物"),
    ShopItem("knocker_silence_elixir", '"静悄悄"的沉默', 30, daily_limit=0, event_limit=3, category="稀有宝物"),
    ShopItem("critical_bead_3", "三级暴击佛珠", 35, daily_limit=0, event_limit=2, category="稀有宝物"),
    ShopItem("penetration_crystal_3", "三级穿透水晶", 35, daily_limit=0, event_limit=2, category="稀有宝物"),
    ShopItem("stabilizer_crystal", "稳定水晶", 50, daily_limit=0, event_limit=1, category="稀有宝物"),

    # 【食谱解锁区】
    ShopItem("recipe_sweet_sour_bass", "食谱·糖醋鲈鱼", 8, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_braised_mandarin", "食谱·酱焖桂鱼", 8, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_yellow_croaker_soup", "食谱·黄花鱼羹", 8, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_steamed_pomfret", "食谱·清蒸鲳鱼", 8, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_grilled_sea_bream", "食谱·炭烤鲷鱼", 8, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_salmon_sashimi", "食谱·三文鱼刺身", 18, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_grilled_eel", "食谱·蒲烧鳗鱼", 18, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_steamed_turbot", "食谱·清蒸多宝鱼", 20, daily_limit=0, event_limit=1, category="食谱解锁"),
    ShopItem("recipe_sturgeon_feast", "食谱·鲟鱼全席", 40, daily_limit=0, event_limit=1, category="食谱解锁"),

    # 【限定收藏区】
    ShopItem("knocker_relic", "叩门者残骸", 80, daily_limit=0, event_limit=1, category="限定收藏"),
    ShopItem("knocker_title", '"封门人"称号', 150, daily_limit=0, event_limit=1, category="限定收藏"),
]


# ==================== 全服播报模板 ====================

BROADCAST_SPAWN = (
    "咚...咚...咚...\n"
    "缉邪司甲级通报：大都会{count}处出现异常诡象！\n"
    "{event_list}"
    "所有修士即刻响应，使用【除夕活动】查看详情。"
)

BROADCAST_BOSS_KILL = (
    "{player_name}封印了{location}的{npc_name}。\n"
    "据悉该实体消散前，空洞的眼眶最后\"看\"了一眼四周——然后无声地碎裂了。"
)

# 重启战斗文案(愿望贴纸特殊机制)
RESTART_BATTLE_TEXT = "黑影的轮廓模糊了一瞬——仿佛时间倒退，它的伤口正在愈合。路灯闪了一下。"

# 瞬移文案
TELEPORT_TEXT = "空间扭曲——你踏入一道短暂的裂隙，眨眼间已身处({x},{y})。裂隙在身后无声合拢。"


# ==================== 活动持续时间 ====================

DEFAULT_DURATION_HOURS = 48  # 默认活动持续时间(小时)
