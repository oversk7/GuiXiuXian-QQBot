"""
战斗图片生成模块
将战斗日志渲染为精美图片，支持装备效果色彩分类
支持双字体渲染：CJK字体负责中文，Emoji字体负责emoji图标
"""

from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import io
import os


# ── 主字体（CJK中文）优先级 ──────────────────────────────────
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

# ── Emoji字体优先级（单色TrueType，PIL可直接渲染）─────────────
EMOJI_FONT_PATHS = [
    '/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoEmoji-Bold.ttf',
    '/usr/share/fonts/noto-emoji/NotoEmoji-Regular.ttf',
    '/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf',
    'C:/Windows/Fonts/seguisym.ttf',   # Segoe UI Symbol（单色，PIL可用）
]

# ── Emoji字符 → 简化替换（仅在无emoji字体时使用）────────────
EMOJI_FALLBACK_MAP = {
    "⚔️": "[战]", "💥": "[暴]", "🔄": "[连]", "🗡️": "[穿]",
    "⚡": "[闪]", "🛡️": "[防]", "💚": "[回]", "🧡": "[吸]",
    "⚰️": "[斩]", "🎯": "[龙]", "🪞": "[镜]", "🔥": "[火]",
    "🆚": "VS",   "✨": "[光]", "🎉": "[胜]", "⏰": "[时]",
    "💀": "[败]", "❤️": "[心]", "🌟": "[星]",
    # ━ 换为普通横线（任何字体均支持）
    "━": "─",
}

# ── 行类型颜色配置 ────────────────────────────────────────────
COLOR_ROUND_TITLE = (220, 180, 60)
COLOR_CRITICAL    = (255, 165, 50)
COLOR_COMBO       = (120, 200, 255)
COLOR_LIFESTEAL   = (255, 140, 80)
COLOR_HEAL        = (100, 220, 100)
COLOR_MIRROR      = (200, 100, 255)
COLOR_EXECUTE     = (220, 60,  60)
COLOR_DODGE       = (160, 160, 220)
COLOR_EFFECT_SUB  = (180, 150, 255)
COLOR_VICTORY     = (100, 255, 150)
COLOR_DEFAULT     = (200, 200, 210)
COLOR_SEPARATOR   = (80,  90,  110)


# ── 工具函数 ──────────────────────────────────────────────────

def _is_emoji_cp(cp: int) -> bool:
    """判断码点是否为需要emoji字体渲染的字符"""
    return (
        0x1F300 <= cp <= 0x1FFFF or  # Misc Symbols & Pictographs, Emoticons, etc.
        0x2600  <= cp <= 0x26FF  or  # Misc Symbols（⚡⚔ etc.）
        0x2700  <= cp <= 0x27BF  or  # Dingbats
        0x2300  <= cp <= 0x23FF  or  # Misc Technical（⏰ etc.）
    )


def _strip_variation_selectors(text: str) -> str:
    """移除变体选择符（U+FE00-U+FE0F），保留实际字符"""
    return ''.join(ch for ch in text if not (0xFE00 <= ord(ch) <= 0xFE0F))


def _replace_emoji_fallback(text: str) -> str:
    """无emoji字体时：替换为方括号标签，再移除剩余不可渲染字符"""
    for emoji, repl in EMOJI_FALLBACK_MAP.items():
        text = text.replace(emoji, repl)
    # 过滤残余的non-BMP / BMP杂项emoji / 变体选择符
    safe = []
    for ch in text:
        cp = ord(ch)
        if cp > 0xFFFF:          continue  # 非BMP
        if 0xFE00 <= cp <= 0xFE0F: continue  # 变体选择符
        if 0x2600 <= cp <= 0x26FF: continue  # Misc Symbols（已被fallback map处理）
        if 0x2700 <= cp <= 0x27BF: continue  # Dingbats
        if cp in (0x200B, 0x200C, 0x200D, 0xFEFF): continue
        safe.append(ch)
    return ''.join(safe)


def _normalize_line(text: str) -> str:
    """统一处理：仅替换 ━→─，保留其余字符（有emoji字体时使用）"""
    return text.replace("━", "─")


def _classify_line_color(line: str) -> Tuple[Tuple[int, int, int], int, int]:
    """返回 (颜色, 字号, 行高)"""
    if line.startswith("  └"):
        return COLOR_EFFECT_SUB, 15, 22

    # 回合标题：含"第N回合"且含横线
    if "回合" in line and ("━" in line or "─" in line):
        return COLOR_ROUND_TITLE, 18, 32

    if any(k in line for k in ["获胜", "胜利", "🎉"]):
        return COLOR_VICTORY, 18, 28
    if any(k in line for k in ["处决", "弑灭", "⚰️"]):
        return COLOR_EXECUTE, 18, 26
    if any(k in line for k in ["吸血", "🧡"]):
        return COLOR_LIFESTEAL, 18, 26
    if any(k in line for k in ["回血", "回复", "💚"]):
        return COLOR_HEAL, 18, 26
    if any(k in line for k in ["镜怨", "反弹", "反击", "🪞"]):
        return COLOR_MIRROR, 18, 26
    if any(k in line for k in ["暴击", "💥"]):
        return COLOR_CRITICAL, 18, 26
    if any(k in line for k in ["连击", "穿透", "🔄", "🗡️"]):
        return COLOR_COMBO, 18, 26
    if any(k in line for k in ["闪避", "被闪避", "⚡"]):
        return COLOR_DODGE, 18, 26

    return COLOR_DEFAULT, 18, 26


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _load_emoji_font(size: int) -> Optional[ImageFont.FreeTypeFont]:
    for path in EMOJI_FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


def _draw_mixed_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    main_font: ImageFont.FreeTypeFont,
    emoji_font: Optional[ImageFont.FreeTypeFont],
    fill: Tuple[int, int, int],
):
    """
    逐字符渲染：emoji字符用emoji_font，其余用main_font。
    emoji_font为None时直接用main_font（此时text已被fallback处理过）。
    """
    for ch in text:
        cp = ord(ch)
        if 0xFE00 <= cp <= 0xFE0F:   # 变体选择符：跳过但不占宽
            continue

        use_font = (emoji_font if (emoji_font and _is_emoji_cp(cp)) else main_font)
        draw.text((x, y), ch, font=use_font, fill=fill)

        try:
            advance = int(use_font.getlength(ch))
        except Exception:
            try:
                bbox = use_font.getbbox(ch)
                advance = bbox[2] - bbox[0] if bbox else use_font.size
            except Exception:
                advance = use_font.size
        x += advance


# ── 主类 ─────────────────────────────────────────────────────

class BattleImageGenerator:
    """战斗图片生成器"""

    WIDTH       = 720
    PADDING     = 16
    BG_COLOR    = (18, 20, 30)
    HEADER_BG   = (28, 32, 50)
    HP_H        = 16
    HP_FULL     = (80,  200, 100)
    HP_DEAD     = (180, 50,  50)
    HP_EMPTY    = (45,  48,  65)

    def __init__(self):
        self.font_title = _load_font(22)
        self.font_body  = _load_font(18)
        self.font_sub   = _load_font(15)
        self.font_small = _load_font(14)

        # 尝试加载emoji字体（与主字体同尺寸）
        self.emoji_body  = _load_emoji_font(18)
        self.emoji_sub   = _load_emoji_font(15)
        self.emoji_small = _load_emoji_font(14)
        self.has_emoji   = self.emoji_body is not None

    def _main_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size >= 20: return self.font_title
        if size >= 17: return self.font_body
        if size >= 14: return self.font_sub
        return self.font_small

    def _emoji_font(self, size: int) -> Optional[ImageFont.FreeTypeFont]:
        if not self.has_emoji:
            return None
        if size >= 17: return self.emoji_body
        if size >= 14: return self.emoji_sub
        return self.emoji_small

    def _render(
        self,
        draw: ImageDraw.ImageDraw,
        pos: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: Tuple[int, int, int],
        fsize: int = 18,
    ):
        """统一渲染入口：有emoji字体则混排，否则用fallback文字"""
        x, y = pos
        if self.has_emoji:
            _draw_mixed_text(draw, x, y, text, font, self._emoji_font(fsize), fill)
        else:
            draw.text((x, y), text, font=font, fill=fill)

    def _prepare_line(self, raw: str) -> str:
        """根据是否有emoji字体决定文字处理方式"""
        if self.has_emoji:
            return _strip_variation_selectors(_normalize_line(raw))
        else:
            return _replace_emoji_fallback(raw)

    def _truncate(self, text: str, max_chars: int) -> str:
        cleaned = self._prepare_line(text)
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars - 1] + "…"

    # ── 主入口 ───────────────────────────────────────────────

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
        """生成战斗图片，返回 PNG 字节数据"""

        # 第一步：预处理每一行
        line_specs = []
        for raw in battle_log:
            color, fsize, lh = _classify_line_color(raw)
            text = self._prepare_line(raw)
            line_specs.append((text, color, fsize, lh))

        # 第二步：计算图片总高度
        HEADER_H     = 70
        SEP_H        = 2
        SEP_M        = 12
        LOG_TOP      = 14
        LOG_BOT      = 14
        HP_BLOCK_H   = 44   # 名字(16) + 间距(4) + 血条(16) + 下边距(8) = 44
        RESULT_H     = 32 + HP_BLOCK_H * 2 + 10

        log_h = sum(lh for _, _, _, lh in line_specs)
        total_h = (
            HEADER_H
            + SEP_M + SEP_H + SEP_M
            + LOG_TOP + log_h + LOG_BOT
            + SEP_M + SEP_H + SEP_M
            + RESULT_H
            + self.PADDING
        )

        # 第三步：创建画布
        img  = Image.new('RGB', (self.WIDTH, total_h), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # ── 标题区 ──
        draw.rectangle([(0, 0), (self.WIDTH, HEADER_H)], fill=self.HEADER_BG)
        p1_short = self._truncate(player1_name, 14)
        p2_short = self._truncate(player2_name, 14)
        vs_text  = f"{p1_short}  VS  {p2_short}"
        self._render(draw, (self.PADDING, 10), vs_text, self.font_title, (230, 200, 100), 22)
        draw.text(
            (self.PADDING, 42),
            f"Lv.{player1_level}  |  Lv.{player2_level}",
            fill=(160, 170, 200), font=self.font_small,
        )

        y = HEADER_H

        # ── 分割线1 ──
        y += SEP_M
        draw.line([(self.PADDING, y), (self.WIDTH - self.PADDING, y)], fill=COLOR_SEPARATOR, width=SEP_H)
        y += SEP_H + SEP_M

        # ── 战斗日志区 ──
        y += LOG_TOP
        for text, color, fsize, lh in line_specs:
            font = self._main_font(fsize)
            if color == COLOR_ROUND_TITLE:
                draw.rectangle(
                    [(self.PADDING, y), (self.WIDTH - self.PADDING, y + lh)],
                    fill=(30, 35, 55),
                )
            x_off = self.PADDING + 12 if text.startswith("  ") else self.PADDING
            self._render(draw, (x_off, y + 2), text, font, color, fsize)
            y += lh

        y += LOG_BOT

        # ── 分割线2 ──
        y += SEP_M
        draw.line([(self.PADDING, y), (self.WIDTH - self.PADDING, y)], fill=COLOR_SEPARATOR, width=SEP_H)
        y += SEP_H + SEP_M

        # ── 结果区 ──
        if winner_name:
            wn = self._prepare_line(winner_name)
            result_text = f"{wn} 获得胜利！"
            self._render(draw, (self.PADDING, y), result_text, self.font_body, COLOR_VICTORY, 18)
        else:
            draw.text((self.PADDING, y), "战斗平局！", fill=COLOR_DEFAULT, font=self.font_body)
        y += 32

        # ── 血条区 ──
        self._draw_hp_bar(draw, self.PADDING, y, player1_name, player1_hp, player1_max_hp)
        y += HP_BLOCK_H
        self._draw_hp_bar(draw, self.PADDING, y, player2_name, player2_hp, player2_max_hp)

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
        """名字在上（y），血条在下（y+20），无重叠"""
        # 名字
        short = self._truncate(name, 18)
        draw.text((x, y), short, fill=(190, 195, 220), font=self.font_small)

        # 血条
        bar_y = y + 20
        bar_w = self.WIDTH - self.PADDING * 2 - 150
        filled = int(bar_w * current_hp / max_hp) if max_hp > 0 else 0
        filled = max(0, min(filled, bar_w))
        bar_color = self.HP_FULL if current_hp > 0 else self.HP_DEAD

        draw.rectangle([(x, bar_y), (x + bar_w, bar_y + self.HP_H)],
                       fill=self.HP_EMPTY, outline=(60, 65, 80))
        if filled > 0:
            draw.rectangle([(x, bar_y), (x + filled, bar_y + self.HP_H)],
                           fill=bar_color)

        hp_pct  = (current_hp / max_hp * 100) if max_hp > 0 else 0
        hp_text = f"{current_hp}/{max_hp}  {hp_pct:.0f}%"
        draw.text((x + bar_w + 8, bar_y), hp_text,
                  fill=(180, 190, 210), font=self.font_small)


# ── 单例接口（保持不变）─────────────────────────────────────

_generator: Optional[BattleImageGenerator] = None


def get_battle_image_generator() -> BattleImageGenerator:
    global _generator
    if _generator is None:
        _generator = BattleImageGenerator()
    return _generator


def should_use_image(round_count: int, threshold: int = 10) -> bool:
    return round_count > threshold
