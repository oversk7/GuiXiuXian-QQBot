"""
战斗图片生成模块
将战斗日志渲染为精美图片，支持装备效果色彩分类
"""

from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import io
import os


# 字体加载优先级（Ubuntu首选，Windows兜底）
FONT_PATHS = [
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
    '/usr/share/fonts/noto/NotoSansCJK-Regular.ttc',
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/simsun.ttc',
]

# Emoji替换表（PIL不支持彩色emoji）
EMOJI_MAP = {
    "⚔️": "[战]",
    "💥": "[暴]",
    "🔄": "[连]",
    "🗡️": "[穿]",
    "⚡": "[闪]",
    "🛡️": "[防]",
    "💚": "[回]",
    "🧡": "[吸]",
    "⚰️": "[斩]",
    "🎯": "[龙]",
    "🪞": "[镜]",
    "🔥": "[火]",
    "🆚": "VS",
    "✨": "[光]",
    "🎉": "[胜]",
    "━": "─",
    "⏰": "[时]",
    "💀": "[败]",
    "❤️": "[心]",
    "🌟": "[星]",
}

# 行类型颜色配置
COLOR_ROUND_TITLE = (220, 180, 60)     # 金色：回合标题
COLOR_CRITICAL = (255, 165, 50)        # 橙色：暴击
COLOR_COMBO = (120, 200, 255)          # 青色：连击/穿透
COLOR_LIFESTEAL = (255, 140, 80)       # 橙红：吸血
COLOR_HEAL = (100, 220, 100)           # 绿色：回血
COLOR_MIRROR = (200, 100, 255)         # 紫色：镜怨/反击
COLOR_EXECUTE = (220, 60, 60)          # 红色：处决
COLOR_DODGE = (160, 160, 220)          # 蓝紫：闪避
COLOR_EFFECT_SUB = (180, 150, 255)     # 浅紫：装备效果子行
COLOR_VICTORY = (100, 255, 150)        # 亮绿：胜利结果
COLOR_DEFAULT = (200, 200, 210)        # 浅灰：普通文字
COLOR_SEPARATOR = (80, 90, 110)        # 分割线


def _classify_line_color(line: str) -> Tuple[Tuple[int, int, int], int, int]:
    """
    根据行内容分类颜色和字号
    返回 (颜色, 字号, 行高)
    """
    # 装备效果子行（缩进行）
    if line.startswith("  └"):
        return COLOR_EFFECT_SUB, 15, 22

    # 回合标题
    cleaned = _replace_emoji(line)
    if "─" in cleaned and ("回合" in line or "─" * 3 in cleaned):
        return COLOR_ROUND_TITLE, 18, 32

    # 胜利/结果
    if any(k in line for k in ["获胜", "胜利", "获得胜利", "[胜]", "🎉"]):
        return COLOR_VICTORY, 18, 28

    # 处决
    if any(k in line for k in ["处决", "弑灭", "[斩]", "⚰️"]):
        return COLOR_EXECUTE, 18, 26

    # 吸血
    if any(k in line for k in ["吸血", "[吸]", "🧡"]):
        return COLOR_LIFESTEAL, 18, 26

    # 回血
    if any(k in line for k in ["回血", "回复", "[回]", "💚"]):
        return COLOR_HEAL, 18, 26

    # 镜怨/反击
    if any(k in line for k in ["镜怨", "反弹", "反击", "[镜]", "🪞"]):
        return COLOR_MIRROR, 18, 26

    # 暴击
    if any(k in line for k in ["暴击", "[暴]", "💥"]):
        return COLOR_CRITICAL, 18, 26

    # 连击/穿透
    if any(k in line for k in ["连击", "穿透", "[连]", "[穿]", "🔄", "🗡️"]):
        return COLOR_COMBO, 18, 26

    # 闪避
    if any(k in line for k in ["闪避", "被闪避", "[闪]", "⚡"]):
        return COLOR_DODGE, 18, 26

    return COLOR_DEFAULT, 18, 26


def _replace_emoji(text: str) -> str:
    """替换Emoji为方括号标签"""
    result = text
    for emoji, replacement in EMOJI_MAP.items():
        result = result.replace(emoji, replacement)
    return result


def _clean_for_render(text: str) -> str:
    """
    先替换已知Emoji，再过滤字体无法渲染的Unicode字符。
    保留：ASCII、中文（BMP CJK）、常用标点、盒状绘图、块元素。
    删除：变体选择符、BMP杂项符号/Dingbats、非BMP字符（几乎全是emoji）。
    """
    text = _replace_emoji(text)
    safe = []
    for ch in text:
        cp = ord(ch)
        # 非BMP（U+10000以上）：几乎全是emoji，跳过
        if cp > 0xFFFF:
            continue
        # 变体选择符 U+FE00-U+FE0F
        if 0xFE00 <= cp <= 0xFE0F:
            continue
        # 杂项符号 U+2600-U+26FF（天气、棋子、星座等emoji）
        if 0x2600 <= cp <= 0x26FF:
            continue
        # Dingbats U+2700-U+27BF
        if 0x2700 <= cp <= 0x27BF:
            continue
        # 零宽连接符、零宽不连字等
        if cp in (0x200B, 0x200C, 0x200D, 0xFEFF):
            continue
        safe.append(ch)
    return ''.join(safe)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """加载字体，按优先级尝试"""
    for font_path in FONT_PATHS:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()


class BattleImageGenerator:
    """战斗图片生成器（精美版）"""

    # 尺寸配置
    WIDTH = 720
    PADDING = 16
    BG_COLOR = (18, 20, 30)             # 深海蓝黑背景
    HEADER_BG_COLOR = (28, 32, 50)      # 标题区背景
    HP_BAR_HEIGHT = 16
    HP_FULL_COLOR = (80, 200, 100)      # 绿色血条（存活）
    HP_DEAD_COLOR = (180, 50, 50)       # 红色血条（已死）
    HP_EMPTY_COLOR = (45, 48, 65)       # 空血条背景

    def __init__(self):
        self.font_title = _load_font(22)
        self.font_body = _load_font(18)
        self.font_sub = _load_font(15)
        self.font_small = _load_font(14)

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size >= 20:
            return self.font_title
        elif size >= 17:
            return self.font_body
        elif size >= 14:
            return self.font_sub
        else:
            return self.font_small

    def generate_battle_image(
        self,
        battle_log: List[str],
        player1_name: str,
        player2_name: str,
        player1_level: int,
        player2_level: int,
        player1_hp: int,
        player1_max_hp: int,
        player2_hp: int,
        player2_max_hp: int,
        winner_name: str = None,
    ) -> bytes:
        """
        生成战斗图片

        Args:
            battle_log: 战斗日志列表
            player1_name: 玩家1名称
            player2_name: 玩家2名称
            player1_level: 玩家1等级
            player2_level: 玩家2等级
            player1_hp: 玩家1最终血量
            player1_max_hp: 玩家1最大血量
            player2_hp: 玩家2最终血量
            player2_max_hp: 玩家2最大血量
            winner_name: 胜利者名称（None表示平局）

        Returns:
            PNG图片字节数据
        """
        # 第一步：计算各行高度和颜色
        line_specs = []  # [(cleaned_text, color, font_size, line_height)]
        for raw_line in battle_log:
            color, fsize, lh = _classify_line_color(raw_line)
            cleaned = _clean_for_render(raw_line)
            line_specs.append((cleaned, color, fsize, lh))

        # 第二步：计算总高度
        HEADER_HEIGHT = 70
        SEPARATOR_H = 2
        SEP_MARGIN = 12
        LOG_TOP_MARGIN = 14
        LOG_BOTTOM_MARGIN = 14
        # 每个血条区块 = 名字行(18px) + 间距(4px) + 血条(16px) + 下边距(6px) = 44px
        HP_BLOCK_H = 44
        RESULT_SECTION_H = 32 + HP_BLOCK_H * 2 + 10  # 结果文字 + 两个血条区块 + 底部

        log_height = sum(lh for _, _, _, lh in line_specs)
        total_height = (
            HEADER_HEIGHT
            + SEP_MARGIN + SEPARATOR_H + SEP_MARGIN
            + LOG_TOP_MARGIN + log_height + LOG_BOTTOM_MARGIN
            + SEP_MARGIN + SEPARATOR_H + SEP_MARGIN
            + RESULT_SECTION_H
            + self.PADDING
        )

        # 第三步：绘制
        img = Image.new('RGB', (self.WIDTH, total_height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # ── 标题区 ──
        draw.rectangle([(0, 0), (self.WIDTH, HEADER_HEIGHT)], fill=self.HEADER_BG_COLOR)

        # 玩家名称 VS
        p1_short = self._truncate(player1_name, 14)
        p2_short = self._truncate(player2_name, 14)
        vs_text = f"{p1_short}  VS  {p2_short}"
        draw.text(
            (self.PADDING, 10),
            vs_text,
            fill=(230, 200, 100),
            font=self.font_title,
        )
        # 等级信息
        level_text = f"Lv.{player1_level}  |  Lv.{player2_level}"
        draw.text(
            (self.PADDING, 40),
            level_text,
            fill=(160, 170, 200),
            font=self.font_small,
        )

        y = HEADER_HEIGHT

        # ── 分割线1 ──
        y += SEP_MARGIN
        draw.line([(self.PADDING, y), (self.WIDTH - self.PADDING, y)],
                  fill=COLOR_SEPARATOR, width=SEPARATOR_H)
        y += SEPARATOR_H + SEP_MARGIN

        # ── 战斗日志区 ──
        y += LOG_TOP_MARGIN
        content_width = self.WIDTH - self.PADDING * 2

        for cleaned_text, color, fsize, lh in line_specs:
            font = self._get_font(fsize)
            # 回合标题加底纹
            if color == COLOR_ROUND_TITLE:
                draw.rectangle(
                    [(self.PADDING, y), (self.WIDTH - self.PADDING, y + lh)],
                    fill=(30, 35, 55),
                )
            # 子行缩进
            x_offset = self.PADDING + 12 if cleaned_text.startswith("  ") else self.PADDING
            draw.text((x_offset, y + 2), cleaned_text, fill=color, font=font)
            y += lh

        y += LOG_BOTTOM_MARGIN

        # ── 分割线2 ──
        y += SEP_MARGIN
        draw.line([(self.PADDING, y), (self.WIDTH - self.PADDING, y)],
                  fill=COLOR_SEPARATOR, width=SEPARATOR_H)
        y += SEPARATOR_H + SEP_MARGIN

        # ── 结果区 ──
        if winner_name:
            result_text = f"{_clean_for_render(winner_name)} 获得胜利！"
            draw.text((self.PADDING, y), result_text, fill=COLOR_VICTORY, font=self.font_body)
        else:
            draw.text((self.PADDING, y), "战斗平局！", fill=COLOR_DEFAULT, font=self.font_body)
        y += 32

        # 血条：玩家1（名字 + bar，各占 HP_BLOCK_H）
        self._draw_hp_bar(draw, self.PADDING, y, player1_name, player1_hp, player1_max_hp)
        y += HP_BLOCK_H

        # 血条：玩家2
        self._draw_hp_bar(draw, self.PADDING, y, player2_name, player2_hp, player2_max_hp)

        # ── 输出 ──
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        return buf.getvalue()

    def _draw_hp_bar(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        name: str,
        current_hp: int,
        max_hp: int,
    ):
        """绘制血条：名字在上（y），血条在下（y+20）"""
        # 名字行
        short_name = self._truncate(name, 18)
        draw.text((x, y), short_name, fill=(190, 195, 220), font=self.font_small)

        # 血条行（名字下方 20px）
        bar_y = y + 20
        bar_total_w = self.WIDTH - self.PADDING * 2 - 150
        filled_w = int(bar_total_w * current_hp / max_hp) if max_hp > 0 else 0
        filled_w = max(0, min(filled_w, bar_total_w))

        bar_color = self.HP_FULL_COLOR if current_hp > 0 else self.HP_DEAD_COLOR

        # 空血条底色
        draw.rectangle(
            [(x, bar_y), (x + bar_total_w, bar_y + self.HP_BAR_HEIGHT)],
            fill=self.HP_EMPTY_COLOR,
            outline=(60, 65, 80),
        )
        # 实际血量
        if filled_w > 0:
            draw.rectangle(
                [(x, bar_y), (x + filled_w, bar_y + self.HP_BAR_HEIGHT)],
                fill=bar_color,
            )

        # HP 数值（血条右侧）
        hp_pct = (current_hp / max_hp * 100) if max_hp > 0 else 0
        hp_text = f"{current_hp}/{max_hp}  {hp_pct:.0f}%"
        draw.text(
            (x + bar_total_w + 8, bar_y),
            hp_text,
            fill=(180, 190, 210),
            font=self.font_small,
        )

    def _truncate(self, text: str, max_chars: int) -> str:
        """截断过长文字"""
        cleaned = _clean_for_render(text)
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars - 1] + "…"


# 全局单例
_battle_image_generator: Optional[BattleImageGenerator] = None


def get_battle_image_generator() -> BattleImageGenerator:
    """获取战斗图片生成器单例"""
    global _battle_image_generator
    if _battle_image_generator is None:
        _battle_image_generator = BattleImageGenerator()
    return _battle_image_generator


def should_use_image(round_count: int, threshold: int = 10) -> bool:
    """判断是否应该使用图片模式"""
    return round_count > threshold
