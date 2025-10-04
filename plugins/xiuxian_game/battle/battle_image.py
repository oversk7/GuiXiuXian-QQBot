"""
战斗图片生成模块
当战斗回合数过多时，生成图片版战斗面板
"""

from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
import io
import os


class BattleImageGenerator:
    """战斗图片生成器"""
    
    # 颜色配置
    BG_COLOR = (30, 30, 40)  # 深色背景
    TEXT_COLOR = (220, 220, 220)  # 浅色文字
    HP_FULL_COLOR = (255, 100, 100)  # 红色血条
    HP_EMPTY_COLOR = (60, 60, 70)  # 灰色空血条
    SEPARATOR_COLOR = (100, 100, 120)  # 分割线颜色
    WINNER_COLOR = (100, 255, 100)  # 胜利者颜色
    LOSER_COLOR = (150, 150, 150)  # 失败者颜色
    
    # 尺寸配置
    WIDTH = 800
    LINE_HEIGHT = 30
    PADDING = 20
    HP_BAR_HEIGHT = 20
    HP_BAR_WIDTH = 400
    
    def __init__(self):
        """初始化图片生成器"""
        # 尝试加载字体
        self.font = self._load_font()
        self.small_font = self._load_font(size=16)
        self.title_font = self._load_font(size=24)
    
    def _load_font(self, size: int = 20):
        """加载字体"""
        try:
            # 尝试加载系统字体
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                "/System/Library/Fonts/PingFang.ttc",  # macOS
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            
            # 如果都找不到，使用默认字体
            return ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()
    
    def generate_battle_image(self, battle_log: List[str], 
                             player1_name: str, player2_name: str,
                             player1_hp: int, player1_max_hp: int,
                             player2_hp: int, player2_max_hp: int,
                             winner: str = None) -> bytes:
        """生成战斗图片
        
        Args:
            battle_log: 战斗日志列表
            player1_name: 玩家1名称
            player2_name: 玩家2名称
            player1_hp: 玩家1当前血量
            player1_max_hp: 玩家1最大血量
            player2_hp: 玩家2当前血量
            player2_max_hp: 玩家2最大血量
            winner: 胜利者名称（可选）
            
        Returns:
            图片的字节数据
        """
        # 计算图片高度
        height = self.PADDING * 2 + len(battle_log) * self.LINE_HEIGHT + 200
        
        # 创建图片
        img = Image.new('RGB', (self.WIDTH, height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        y = self.PADDING
        
        # 绘制标题
        title = f"⚔️ {player1_name} VS {player2_name}"
        draw.text((self.PADDING, y), title, fill=self.TEXT_COLOR, font=self.title_font)
        y += 40
        
        # 绘制分割线
        draw.line([(self.PADDING, y), (self.WIDTH - self.PADDING, y)], 
                 fill=self.SEPARATOR_COLOR, width=2)
        y += 20
        
        # 绘制战斗日志
        for log_line in battle_log:
            # 移除emoji（PIL可能不支持）
            clean_line = self._clean_text(log_line)
            draw.text((self.PADDING, y), clean_line, fill=self.TEXT_COLOR, font=self.font)
            y += self.LINE_HEIGHT
        
        # 绘制分割线
        y += 10
        draw.line([(self.PADDING, y), (self.WIDTH - self.PADDING, y)], 
                 fill=self.SEPARATOR_COLOR, width=2)
        y += 20
        
        # 绘制最终血量
        if winner:
            result_text = f"🎉 {winner} 获得胜利！"
            draw.text((self.PADDING, y), result_text, fill=self.WINNER_COLOR, font=self.title_font)
            y += 40
        
        # 绘制玩家1血条
        self._draw_hp_bar(draw, self.PADDING, y, player1_name, 
                         player1_hp, player1_max_hp, 
                         player1_hp > 0)
        y += 60
        
        # 绘制玩家2血条
        self._draw_hp_bar(draw, self.PADDING, y, player2_name, 
                         player2_hp, player2_max_hp, 
                         player2_hp > 0)
        
        # 转换为字节
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes.getvalue()
    
    def _draw_hp_bar(self, draw: ImageDraw, x: int, y: int, 
                    name: str, current_hp: int, max_hp: int, 
                    is_alive: bool = True):
        """绘制血条
        
        Args:
            draw: ImageDraw对象
            x: X坐标
            y: Y坐标
            name: 名称
            current_hp: 当前血量
            max_hp: 最大血量
            is_alive: 是否存活
        """
        # 绘制名称
        name_color = self.TEXT_COLOR if is_alive else self.LOSER_COLOR
        draw.text((x, y), name, fill=name_color, font=self.font)
        y += 25
        
        # 计算血量百分比
        hp_percent = (current_hp / max_hp * 100) if max_hp > 0 else 0
        filled_width = int(self.HP_BAR_WIDTH * current_hp / max_hp) if max_hp > 0 else 0
        
        # 绘制空血条背景
        draw.rectangle(
            [(x, y), (x + self.HP_BAR_WIDTH, y + self.HP_BAR_HEIGHT)],
            fill=self.HP_EMPTY_COLOR,
            outline=self.SEPARATOR_COLOR
        )
        
        # 绘制实际血量
        if filled_width > 0:
            draw.rectangle(
                [(x, y), (x + filled_width, y + self.HP_BAR_HEIGHT)],
                fill=self.HP_FULL_COLOR
            )
        
        # 绘制血量文字
        hp_text = f"{current_hp}/{max_hp} ({hp_percent:.1f}%)"
        draw.text((x + self.HP_BAR_WIDTH + 10, y), hp_text, 
                 fill=name_color, font=self.small_font)
    
    def _clean_text(self, text: str) -> str:
        """清理文本，移除emoji等特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            清理后的文本
        """
        # 简单的emoji替换映射
        emoji_map = {
            "⚔️": "[战]",
            "🎉": "[胜]",
            "💀": "[败]",
            "💥": "[暴击]",
            "🔄": "[连击]",
            "🗡️": "[穿透]",
            "⚡": "[闪避]",
            "🛡️": "[反击]",
            "💚": "[回血]",
            "🧡": "[吸血]",
            "❤️": "♥",
            "🖤": "♡",
            "👹": "[怪]",
            "━": "-",
            "⏰": "[超时]",
        }
        
        result = text
        for emoji, replacement in emoji_map.items():
            result = result.replace(emoji, replacement)
        
        return result


# 全局实例
_battle_image_generator = None


def get_battle_image_generator() -> BattleImageGenerator:
    """获取战斗图片生成器单例"""
    global _battle_image_generator
    if _battle_image_generator is None:
        _battle_image_generator = BattleImageGenerator()
    return _battle_image_generator


def should_use_image(round_count: int, threshold: int = 10) -> bool:
    """判断是否应该使用图片模式
    
    Args:
        round_count: 战斗回合数
        threshold: 阈值（默认10回合）
        
    Returns:
        是否使用图片模式
    """
    return round_count > threshold

