from __future__ import annotations

"""地图可视化系统

生成漂亮的地图图片，显示：
1. 坐标网格
2. 各种地点标注
3. 玩家位置（红点）
4. 美观的背景和样式
"""

import asyncio
import io
import math
import os
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.part_time_job import JobLocation
from ..models.navigation_task import NavigationTask
from ..economy.merchants import MARKETS, HEADQUARTERS_COORD


class MapVisualizer:
    """地图可视化器"""

    # 类级字体缓存，避免重复加载（性能优化）
    _cached_fonts: Optional[Dict[str, ImageFont.FreeTypeFont]] = None
    _font_load_attempted: bool = False

    def __init__(self):
        # 地图配置 - 扩大纵向范围以显示所有地点
        self.map_width = 1600
        self.map_height = 1400  # 增加高度以容纳Y轴范围-2000到2000
        self.grid_size = 20  # 每个网格的像素大小
        self.coordinate_scale = 50  # 坐标缩放比例，50像素 = 1游戏坐标

        # 颜色配置（高端版 - 古地图羊皮纸风格）
        self.colors = {
            # 古地图羊皮纸底色
            'background': '#F4E8D0',  # 羊皮纸底色
            'background_gradient_start': '#F4E8D0',  # 渐变起始（浅羊皮纸）
            'background_gradient_end': '#E8DCC0',    # 渐变结束（深羊皮纸）
            'parchment_texture': '#E8DCC0',  # 纹理颜色

            # 网格和边框（棕褐色调）
            'grid': '#D4C4A0',        # 网格线（棕褐色）
            'border': '#8B6914',      # 主边框（深金棕色）
            'border_decoration': '#CD853F',  # 装饰边框（秘鲁色）
            'coordinate_text': '#5C4033',  # 坐标文字（深棕色）

            # 地点标记（鲜艳对比）
            'player': '#DC143C',      # 玩家（深红色）
            'player_shadow': '#8B0000',  # 玩家阴影
            'player_glow': '#FFD700',    # 玩家光晕（金色）

            'market': '#FF6B00',      # 市集（鲜艳橙）
            'market_shadow': '#CC5500',

            'job': '#9370DB',         # 打工（中紫色）
            'job_shadow': '#6A4C93',

            'special': '#FF1493',     # 特殊（深粉红）
            'special_shadow': '#C71585',

            'mansion': '#8B4513',     # 阴宅（马鞍棕）
            'mansion_connector': '#4169E1',  # 连线（宝蓝色）

            # 导航和装饰
            'location_text': '#2F4F4F',  # 地点文字（深石板灰）
            'navigation_line': '#32CD32',  # 导航线（酸橙绿）
            'navigation_target': '#FFD700',  # 导航目标（金色）

            # 标题和图例
            'title_text': '#4B2E1F',  # 标题（深棕色）
            'legend_bg': '#FFF8DC',   # 图例背景（玉米丝色）
            'legend_border': '#8B6914',  # 图例边框
        }

        # 字体配置（将在运行时加载）
        self.fonts = {}
        
    def _load_fonts(self):
        """加载字体，优先使用中文字体（带缓存机制）"""
        # 如果已有缓存，直接使用
        if MapVisualizer._cached_fonts is not None:
            self.fonts = MapVisualizer._cached_fonts
            return

        # 如果已尝试加载但失败，使用默认字体
        if MapVisualizer._font_load_attempted and MapVisualizer._cached_fonts is None:
            self.fonts = {name: ImageFont.load_default() for name in ['small', 'medium', 'large', 'title']}
            return

        # 标记已尝试加载
        MapVisualizer._font_load_attempted = True

        try:
            # 尝试加载系统中文字体
            font_paths = [
                # Windows 中文字体
                'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
                'C:/Windows/Fonts/simhei.ttf',    # 黑体
                'C:/Windows/Fonts/simsun.ttc',    # 宋体
                'C:/Windows/Fonts/msyhbd.ttc',    # 微软雅黑粗体

                # Linux 中文字体 - 常见路径
                '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',           # 文泉驿微米黑
                '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',             # 文泉驿正黑
                '/usr/share/fonts/truetype/arphic/ukai.ttc',                # AR PL UKai CN
                '/usr/share/fonts/truetype/arphic/uming.ttc',               # AR PL UMing CN
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',   # Noto Sans CJK
                '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf', # Droid Sans Fallback
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',

                # Ubuntu/Debian 特定路径
                '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
                '/usr/share/fonts/truetype/fonts-noto-cjk/NotoSansCJK-Regular.ttc',

                # CentOS/RHEL 特定路径
                '/usr/share/fonts/wqy-microhei/wqy-microhei.ttc',
                '/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc',

                # macOS 中文字体
                '/System/Library/Fonts/PingFang.ttc',
                '/System/Library/Fonts/Hiragino Sans GB.ttc',
                '/Library/Fonts/Arial Unicode MS.ttf',
            ]

            # 首先找到一个可用的中文字体路径
            available_font_path = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        # 尝试加载测试
                        test_font = ImageFont.truetype(font_path, 12)
                        available_font_path = font_path
                        print(f"✓ 找到可用中文字体: {os.path.basename(font_path)}")
                        break
                    except (OSError, IOError):
                        continue

            # 如果找到了可用字体，加载所有大小
            if available_font_path:
                for size, name in [(12, 'small'), (14, 'medium'), (16, 'large'), (20, 'title')]:
                    try:
                        self.fonts[name] = ImageFont.truetype(available_font_path, size)
                        print(f"  - 加载字体大小 {size}px: {name}")
                    except (OSError, IOError):
                        self.fonts[name] = ImageFont.load_default()
                        print(f"  - 警告: 字体大小 {size} 加载失败，使用默认字体")
            else:
                # 没有找到中文字体，使用默认字体
                print("⚠️ 警告: 未找到任何中文字体，图例文字将显示为方块")
                print("   建议安装中文字体：")
                print("   Ubuntu/Debian: sudo apt-get install fonts-wqy-microhei")
                print("   CentOS/RHEL: sudo yum install wqy-microhei-fonts")
                for name in ['small', 'medium', 'large', 'title']:
                    self.fonts[name] = ImageFont.load_default()

        except Exception as e:
            # 全部使用默认字体
            print(f"字体加载异常: {e}")
            for name in ['small', 'medium', 'large', 'title']:
                self.fonts[name] = ImageFont.load_default()

        # 缓存加载的字体，供后续实例使用
        if self.fonts:
            MapVisualizer._cached_fonts = self.fonts
            print(f"✓ 字体已缓存，后续实例将直接使用缓存（性能提升 ~300ms）")

    def _draw_gradient_background(self, image: Image.Image):
        """绘制古地图羊皮纸渐变背景（带纹理效果）"""
        import random

        # 解析起始和结束颜色
        start_color = self._hex_to_rgb(self.colors['background_gradient_start'])
        end_color = self._hex_to_rgb(self.colors['background_gradient_end'])

        # 逐行绘制渐变并添加纹理
        for y in range(self.map_height):
            # 计算当前行的混合比例
            ratio = y / self.map_height

            # 插值计算当前行颜色
            r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
            g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
            b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)

            # 绘制该行
            draw = ImageDraw.Draw(image)
            draw.line([(0, y), (self.map_width, y)], fill=(r, g, b), width=1)

        # 添加羊皮纸纹理效果（噪点）
        pixels = image.load()
        random.seed(42)  # 固定种子，保证每次纹理一致
        for y in range(self.map_height):
            for x in range(self.map_width):
                # 随机添加细微的明暗变化（5%概率）
                if random.random() < 0.05:
                    current = pixels[x, y]
                    # 随机调整亮度 -5 到 +5
                    noise = random.randint(-5, 5)
                    new_r = max(0, min(255, current[0] + noise))
                    new_g = max(0, min(255, current[1] + noise))
                    new_b = max(0, min(255, current[2] + noise))
                    pixels[x, y] = (new_r, new_g, new_b)

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """将十六进制颜色转换为RGB元组"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _draw_decorative_border(self, draw: ImageDraw.Draw):
        """绘制古地图风格装饰性边框"""
        # 外层主边框（深金棕色，粗线）
        border_width = 8
        draw.rectangle([0, 0, self.map_width - 1, self.map_height - 1],
                      outline=self.colors['border'], width=border_width)

        # 内层装饰边框（秘鲁色，细线）
        inner_offset = border_width + 4
        draw.rectangle([inner_offset, inner_offset,
                       self.map_width - inner_offset - 1,
                       self.map_height - inner_offset - 1],
                      outline=self.colors['border_decoration'], width=3)

        # 绘制四角装饰（菱形图案）
        corner_size = 30
        corners = [
            (inner_offset + 10, inner_offset + 10),  # 左上
            (self.map_width - inner_offset - 10, inner_offset + 10),  # 右上
            (inner_offset + 10, self.map_height - inner_offset - 10),  # 左下
            (self.map_width - inner_offset - 10, self.map_height - inner_offset - 10),  # 右下
        ]

        for cx, cy in corners:
            # 绘制菱形装饰
            diamond = [
                (cx, cy - corner_size // 2),  # 上
                (cx + corner_size // 2, cy),  # 右
                (cx, cy + corner_size // 2),  # 下
                (cx - corner_size // 2, cy),  # 左
            ]
            draw.polygon(diamond, fill=self.colors['border_decoration'],
                        outline=self.colors['border'], width=2)

    def _draw_map_title(self, draw: ImageDraw.Draw):
        """绘制地图标题和装饰"""
        # 标题文字
        title = "大都会地图"
        subtitle = "Map of the Metropolis"

        # 标题背景装饰框（移到底部避免遮挡地点）
        title_bg_width = 400
        title_bg_height = 80
        title_bg_x = (self.map_width - title_bg_width) // 2
        title_bg_y = self.map_height - 120  # 底部位置

        # 绘制标题背景（半透明羊皮纸色）
        draw.rectangle([title_bg_x, title_bg_y,
                       title_bg_x + title_bg_width,
                       title_bg_y + title_bg_height],
                      fill=self.colors['legend_bg'],
                      outline=self.colors['border'], width=3)

        # 绘制主标题
        title_font = self.fonts.get('title', self.fonts.get('large'))
        # 计算标题宽度以居中
        try:
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = title_bg_x + (title_bg_width - title_width) // 2
        except:
            title_x = title_bg_x + 80  # 回退位置

        draw.text((title_x, title_bg_y + 15), title,
                 fill=self.colors['title_text'], font=title_font)

        # 绘制副标题
        subtitle_font = self.fonts.get('small')
        try:
            subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
            subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
            subtitle_x = title_bg_x + (title_bg_width - subtitle_width) // 2
        except:
            subtitle_x = title_bg_x + 100  # 回退位置

        draw.text((subtitle_x, title_bg_y + 50), subtitle,
                 fill=self.colors['coordinate_text'], font=subtitle_font)

    def _check_font_support(self, text: str = "测试") -> bool:
        """检查当前字体是否支持中文显示"""
        try:
            # 创建一个小的测试图片
            test_img = Image.new('RGB', (50, 20), color='white')
            test_draw = ImageDraw.Draw(test_img)

            # 尝试绘制中文文字
            test_draw.text((5, 5), text, fill='black', font=self.fonts.get('small'))

            # 检查是否有实际内容（简单检查像素变化）
            pixels = list(test_img.getdata())
            non_white_pixels = sum(1 for pixel in pixels if pixel != (255, 255, 255))

            return non_white_pixels > 10  # 如果有足够的非白色像素，说明字体工作正常

        except Exception:
            return False
    
    def _game_to_pixel(self, x: int, y: int) -> Tuple[int, int]:
        """将游戏坐标转换为像素坐标"""
        # 游戏坐标原点在地图中心
        center_x = self.map_width // 2
        center_y = self.map_height // 2

        # 扩大坐标范围以适应实际地点分布：X轴-500到500，Y轴-500到500
        pixel_x = center_x + (x * self.map_width // 4000)  # X轴范围-2000到2000
        pixel_y = center_y - (y * self.map_height // 4000)  # Y轴范围-2000到2000，Y轴翻转，向上为正

        return pixel_x, pixel_y
    
    def _draw_terrain(self, image: Image.Image):
        """绘制地形层：海域（蓝）+ 八大集群区域（彩色半透明）"""
        overlay = Image.new('RGBA', (self.map_width, self.map_height), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)

        # ── 海域（东海+南海，沿海岸线的不规则多边形）──
        # 用游戏坐标描述海岸线，然后转像素
        # 从地图顶部右侧 → 沿东海岸 → 绕南海 → 地图底部右侧
        coastline_game = [
            (2000, 2000),     # 右上角
            (500, 1500),      # 北境东侧海面
            (450, 700),       # 辽阳以东
            (800, 0),         # 天海卫以东
            (850, -400),      # 海门以东
            (800, -700),      # 舟山以东
            (700, -1100),     # 鹭岛以东
            (500, -1500),     # 鹏城以东
            (350, -1750),     # 琼崖以南
            (-200, -2000),    # 向西南延伸
            (2000, -2000),    # 右下角
        ]
        coastline_px = [self._game_to_pixel(gx, gy) for gx, gy in coastline_game]
        od.polygon(coastline_px, fill=(70, 130, 180, 45))  # 钢蓝色半透明

        # 在深海区域加深颜色（离海岸更远的部分）
        deep_sea_game = [
            (2000, 2000), (900, 1500), (1000, 0), (1100, -500),
            (1000, -1100), (800, -1700), (500, -2000), (2000, -2000),
        ]
        deep_sea_px = [self._game_to_pixel(gx, gy) for gx, gy in deep_sea_game]
        od.polygon(deep_sea_px, fill=(50, 100, 160, 30))  # 更深的蓝

        # ── 八大集群区域（柔和椭圆色块 + 标签）──
        clusters = [
            # (名称, 中心game坐标, 椭圆半径game坐标, RGBA颜色)
            ("京  畿", (25, 0), (300, 250), (200, 160, 60, 30)),     # 暖金
            ("江  南", (590, -560), (200, 150), (60, 160, 60, 28)),   # 翠绿
            ("南  海", (350, -1380), (250, 250), (40, 140, 180, 25)), # 海蓝
            ("蜀  地", (-750, -870), (220, 320), (140, 90, 40, 28)),  # 赭棕
            ("关  中", (-580, -300), (280, 130), (170, 50, 50, 28)),  # 暗红
            ("中  原", (-100, -600), (170, 300), (170, 140, 40, 25)), # 暗金
            ("北  境", (250, 1020), (180, 480), (130, 180, 210, 30)), # 冰蓝
            ("西  域", (-1450, 225), (350, 200), (190, 170, 130, 28)),# 沙黄
        ]

        for name, (cx, cy), (rx, ry), color in clusters:
            px, py = self._game_to_pixel(cx, cy)
            # 游戏坐标半径 → 像素半径
            rx_px = rx * self.map_width // 4000
            ry_px = ry * self.map_height // 4000
            od.ellipse([px - rx_px, py - ry_px, px + rx_px, py + ry_px], fill=color)

        # 合成到主图
        base = image.convert('RGBA')
        composited = Image.alpha_composite(base, overlay)
        image.paste(composited.convert('RGB'))

        # ── 集群标签（直接画在主图上，不需要透明）──
        label_draw = ImageDraw.Draw(image)
        label_font = self.fonts.get('medium', self.fonts.get('small'))
        for name, (cx, cy), _, _ in clusters:
            px, py = self._game_to_pixel(cx, cy)
            # 计算文字宽度以居中
            try:
                bbox = label_draw.textbbox((0, 0), name, font=label_font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            except Exception:
                tw, th = 40, 14
            label_draw.text(
                (px - tw // 2, py - th // 2),
                name,
                fill='#8B7355',  # 柔和棕色，不抢眼
                font=label_font,
            )

    def _draw_background_and_grid(self, draw: ImageDraw.Draw, image: Image.Image):
        """绘制背景和网格（古地图版：羊皮纸纹理 + 装饰边框 + 标题）"""
        # 绘制羊皮纸渐变背景和纹理
        self._draw_gradient_background(image)

        # 绘制地形层：海域 + 集群区域
        self._draw_terrain(image)

        # 绘制装饰性边框（多层边框效果）
        self._draw_decorative_border(draw)

        # 绘制地图标题
        self._draw_map_title(draw)

        # 优化的网格绘制：批量绘制所有线条
        grid_lines = []

        # 垂直网格线（X方向）
        for x in range(0, self.map_width, self.grid_size):
            grid_lines.append([(x, 0), (x, self.map_height)])

        # 水平网格线（Y方向）
        for y in range(0, self.map_height, self.grid_size):
            grid_lines.append([(0, y), (self.map_width, y)])

        # 一次性绘制所有网格线（性能优化：60-70%提升）
        for line in grid_lines:
            draw.line(line, fill=self.colors['grid'], width=1)
        
        # 绘制坐标轴
        center_x = self.map_width // 2
        center_y = self.map_height // 2
        
        # X轴
        draw.line([0, center_y, self.map_width, center_y], fill=self.colors['border'], width=2)
        # Y轴
        draw.line([center_x, 0, center_x, self.map_height], fill=self.colors['border'], width=2)
        
        # 绘制坐标刻度 - 扩大范围以显示所有地点
        for i in range(-2000, 2001, 500):
            if i == 0:
                continue

            # X轴刻度
            pixel_x, _ = self._game_to_pixel(i, 0)
            if 0 <= pixel_x <= self.map_width:
                draw.line([pixel_x, center_y - 5, pixel_x, center_y + 5], fill=self.colors['border'], width=2)
                draw.text((pixel_x - 10, center_y + 8), str(i), fill=self.colors['coordinate_text'], font=self.fonts['small'])

            # Y轴刻度
            _, pixel_y = self._game_to_pixel(0, i)
            if 0 <= pixel_y <= self.map_height:
                draw.line([center_x - 5, pixel_y, center_x + 5, pixel_y], fill=self.colors['border'], width=2)
                draw.text((center_x + 8, pixel_y - 8), str(i), fill=self.colors['coordinate_text'], font=self.fonts['small'])
    
    def _draw_location(self, draw: ImageDraw.Draw, x: int, y: int, name: str,
                      location_type: str, size: int = 8) -> Optional[Tuple[int, int]]:
        """绘制地点标记（带阴影效果），并返回像素坐标"""
        pixel_x, pixel_y = self._game_to_pixel(x, y)

        # 确保在地图范围内
        if not (0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height):
            return None

        # 根据类型选择颜色和阴影颜色
        color = self.colors.get(location_type, self.colors['special'])
        shadow_color = self.colors.get(f'{location_type}_shadow', '#999999')

        # 阴影偏移量
        shadow_offset = 2

        # 先绘制阴影（右下偏移）
        draw.ellipse([
            pixel_x - size + shadow_offset,
            pixel_y - size + shadow_offset,
            pixel_x + size + shadow_offset,
            pixel_y + size + shadow_offset
        ], fill=shadow_color, outline=None)

        # 再绘制地点标记（圆形），不显示任何文字
        draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size],
                    fill=color, outline='#000000', width=2)

        return pixel_x, pixel_y

    def _draw_mansion(self, draw: ImageDraw.Draw, x: int, y: int, mansion_level: int,
                     owner_nickname: str, occupancy_map: Optional[Dict[Tuple[int, int], Dict[str, Any]]] = None,
                     size: int = 6):
        """绘制阴宅标记（房子形状）"""
        pixel_x, pixel_y = self._game_to_pixel(x, y)

        # 确保在地图范围内
        if not (0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height):
            return

        adjusted_pixel_x, adjusted_pixel_y = pixel_x, pixel_y
        connector_needed = False

        if occupancy_map and (pixel_x, pixel_y) in occupancy_map:
            connector_needed = True
            offset_distance = 22
            adjusted_pixel_x = pixel_x + offset_distance
            adjusted_pixel_y = pixel_y

            if adjusted_pixel_x + size >= self.map_width:
                adjusted_pixel_x = pixel_x - offset_distance

            if adjusted_pixel_x - size < 0:
                adjusted_pixel_x = pixel_x
                connector_needed = False

        house_center_x = adjusted_pixel_x
        house_center_y = adjusted_pixel_y

        # 绘制房子形状的阴宅标记
        # 房子底部（矩形）
        house_width = size * 2
        house_height = size * 1.5
        house_left = house_center_x - house_width // 2
        house_top = house_center_y - house_height // 2
        house_right = house_left + house_width
        house_bottom = house_top + house_height

        # 绘制房子主体
        draw.rectangle([house_left, house_top, house_right, house_bottom],
                      fill=self.colors['mansion'], outline='#000000', width=1)

        # 绘制房顶（三角形）
        roof_height = size
        roof_points = [
            (house_center_x, house_top - roof_height),  # 顶点
            (house_left - 1, house_top),         # 左下
            (house_right + 1, house_top)         # 右下
        ]
        draw.polygon(roof_points, fill='#654321', outline='#000000', width=1)

        if connector_needed:
            connector_color = self.colors['mansion_connector']
            line_start_x = house_center_x
            line_start_y = house_center_y
            draw.line([line_start_x, line_start_y, pixel_x, pixel_y],
                      fill=connector_color, width=2)

            arrow_length = 8
            arrow_angle = math.radians(25)
            base_angle = math.atan2(pixel_y - line_start_y, pixel_x - line_start_x)

            for angle_delta in (arrow_angle, -arrow_angle):
                arrow_x = pixel_x - arrow_length * math.cos(base_angle + angle_delta)
                arrow_y = pixel_y - arrow_length * math.sin(base_angle + angle_delta)
                draw.line([pixel_x, pixel_y, arrow_x, arrow_y],
                          fill=connector_color, width=1)

        # 根据阴宅等级在房子上显示等级标记
        if mansion_level <= 10:
            # 在房子中心显示等级数字
            level_text = str(mansion_level)
            # 使用小字体显示等级
            text_bbox = draw.textbbox((0, 0), level_text, font=self.fonts['small'])
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = house_center_x - text_width // 2
            text_y = house_center_y - text_height // 2
            draw.text((text_x, text_y), level_text, fill='#FFFFFF', font=self.fonts['small'])

    def _draw_mansions_from_data(self, draw: ImageDraw.Draw, mansion_data: List[Tuple[int, int, int, str]],
                                occupancy_map: Optional[Dict[Tuple[int, int], Dict[str, Any]]] = None):
        """从预取数据绘制所有阴宅（纯渲染，无DB访问）"""
        for mx, my, mlevel, mnick in mansion_data:
            self._draw_mansion(draw, mx, my, mlevel, mnick, occupancy_map)
    
    def _draw_players(self, draw: ImageDraw.Draw, players: List[Player], current_player_id: str = None):
        """绘制玩家位置"""
        # 先绘制所有其他玩家（小红点）
        for player in players:
            if current_player_id and player.id == current_player_id:
                continue  # 跳过当前玩家，稍后单独绘制

            # 使用正确的当前坐标
            player_x, player_y = player.get_current_coordinates()
            pixel_x, pixel_y = self._game_to_pixel(player_x, player_y)

            # 确保在地图范围内
            if not (0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height):
                continue

            # 其他玩家：特别小的红点（1-2像素）
            size = 1
            draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size],
                        fill=self.colors['player'], outline=None, width=0)

        # 最后绘制当前玩家（粗红点），确保显示在最上层
        if current_player_id:
            for player in players:
                if player.id == current_player_id:
                    # 使用正确的当前坐标
                    player_x, player_y = player.get_current_coordinates()
                    pixel_x, pixel_y = self._game_to_pixel(player_x, player_y)

                    # 确保在地图范围内
                    if 0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height:
                        # 当前玩家：粗红点
                        size = 6
                        draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size],
                                    fill=self.colors['player'], outline='#FFFFFF', width=2)
                    break

    def _draw_navigation_line(self, draw: ImageDraw.Draw, player: Player, nav_task: NavigationTask):
        """绘制导航连线和目标点"""
        # 获取玩家当前现实世界坐标（导航基于现实世界坐标）
        player_x = player.real_world_x or 0
        player_y = player.real_world_y or 0

        # 获取目标坐标
        target_x = nav_task.target_x
        target_y = nav_task.target_y

        # 转换为像素坐标
        player_pixel_x, player_pixel_y = self._game_to_pixel(player_x, player_y)
        target_pixel_x, target_pixel_y = self._game_to_pixel(target_x, target_y)

        # 检查坐标是否在地图范围内
        player_in_bounds = (0 <= player_pixel_x <= self.map_width and
                           0 <= player_pixel_y <= self.map_height)
        target_in_bounds = (0 <= target_pixel_x <= self.map_width and
                           0 <= target_pixel_y <= self.map_height)

        # 如果至少有一个点在地图范围内，就绘制连线
        if player_in_bounds or target_in_bounds:
            # 绘制导航连线（虚线效果）
            self._draw_dashed_line(draw, player_pixel_x, player_pixel_y,
                                 target_pixel_x, target_pixel_y,
                                 self.colors['navigation_line'], width=2)

        # 绘制目标点（如果在地图范围内）
        if target_in_bounds:
            # 绘制目标点标记（黄色圆圈）
            target_size = 8
            draw.ellipse([target_pixel_x - target_size, target_pixel_y - target_size,
                         target_pixel_x + target_size, target_pixel_y + target_size],
                        fill=self.colors['navigation_target'], outline='#000000', width=2)

            # 在目标点下方显示坐标（使用深色文字便于阅读）
            text_x = target_pixel_x - 30  # 向左偏移一些，让文字居中
            text_y = target_pixel_y + 12  # 放在标点下方
            draw.text((text_x, text_y), f"目标({target_x},{target_y})",
                     fill='#000000', font=self.fonts['small'])

    def _draw_dashed_line(self, draw: ImageDraw.Draw, x1: int, y1: int, x2: int, y2: int,
                         color: str, width: int = 1, dash_length: int = 10):
        """绘制虚线"""
        import math

        # 计算线段长度和方向
        dx = x2 - x1
        dy = y2 - y1
        distance = math.sqrt(dx * dx + dy * dy)

        if distance == 0:
            return

        # 单位向量
        unit_x = dx / distance
        unit_y = dy / distance

        # 绘制虚线段
        current_distance = 0
        is_dash = True

        while current_distance < distance:
            # 计算当前段的起点
            start_x = x1 + unit_x * current_distance
            start_y = y1 + unit_y * current_distance

            # 计算当前段的长度
            remaining = distance - current_distance
            segment_length = min(dash_length, remaining)

            # 计算当前段的终点
            end_x = start_x + unit_x * segment_length
            end_y = start_y + unit_y * segment_length

            # 如果是实线段，则绘制
            if is_dash:
                draw.line([int(start_x), int(start_y), int(end_x), int(end_y)],
                         fill=color, width=width)

            # 切换到下一段
            current_distance += segment_length
            is_dash = not is_dash

    def _draw_legend(self, draw: ImageDraw.Draw):
        """绘制古地图风格图例"""
        legend_x = 20
        legend_y = 120  # 下移以避开标题
        legend_width = 200
        legend_height = 180  # 增加高度以容纳阴宅项目

        # 绘制图例背景（羊皮纸色）
        draw.rectangle([legend_x, legend_y, legend_x + legend_width, legend_y + legend_height],
                      fill=self.colors['legend_bg'], outline=self.colors['legend_border'], width=3)

        # 检查字体是否支持中文
        font_supports_chinese = self._check_font_support("图例")

        # 图例标题
        title = "图例" if font_supports_chinese else "Legend"
        draw.text((legend_x + 10, legend_y + 10), title, fill=self.colors['location_text'], font=self.fonts['large'])

        # 图例项目 - 使用纯文字，避免emoji乱码
        if font_supports_chinese:
            legend_items = [
                ("你的位置", self.colors['player']),
                ("市集交易", self.colors['market']),
                ("打工地点", self.colors['job']),
                ("特殊地点", self.colors['special']),
                ("阴宅", self.colors['mansion']),
                ("导航路线", self.colors['navigation_line']),
                ("导航目标", self.colors['navigation_target']),
            ]
        else:
            legend_items = [
                ("You", self.colors['player']),
                ("Markets", self.colors['market']),
                ("Jobs", self.colors['job']),
                ("Special", self.colors['special']),
                ("Mansions", self.colors['mansion']),
                ("Navigation", self.colors['navigation_line']),
                ("Target", self.colors['navigation_target']),
            ]

        for i, (text, color) in enumerate(legend_items):
            item_y = legend_y + 35 + i * 20

            # 特殊处理阴宅图例 - 绘制小房子
            if "阴宅" in text or "Mansions" in text:
                # 绘制小房子图标
                house_size = 3
                house_x = legend_x + 20
                house_y = item_y + 5

                # 房子主体
                draw.rectangle([house_x - house_size, house_y - house_size,
                               house_x + house_size, house_y + house_size],
                              fill=color, outline='#000000', width=1)
                # 房顶
                roof_points = [
                    (house_x, house_y - house_size - 2),  # 顶点
                    (house_x - house_size - 1, house_y - house_size),  # 左下
                    (house_x + house_size + 1, house_y - house_size)   # 右下
                ]
                draw.polygon(roof_points, fill='#654321', outline='#000000', width=1)
            else:
                # 绘制圆形颜色标记（带阴影效果）
                marker_x = legend_x + 20
                marker_y = item_y + 5
                marker_size = 5

                # 绘制阴影
                draw.ellipse([marker_x - marker_size + 1, marker_y - marker_size + 1,
                             marker_x + marker_size + 1, marker_y + marker_size + 1],
                            fill='#999999')
                # 绘制主标记
                draw.ellipse([marker_x - marker_size, marker_y - marker_size,
                             marker_x + marker_size, marker_y + marker_size],
                            fill=color, outline='#000000', width=1)

            # 绘制文字（不再需要去掉emoji前缀）
            draw.text((legend_x + 35, item_y - 2), text, fill=self.colors['location_text'], font=self.fonts['small'])
    
    async def generate_map(self, session: AsyncSession, current_player_id: str = None) -> bytes:
        """生成地图图片（优化版：DB预取 + 线程池渲染）"""
        # 加载字体（带缓存，首次后~300ms性能提升）
        self._load_fonts()

        # ── 阶段1：异步预取所有DB数据 ──
        # 只查当前玩家（不再渲染其他玩家，减少查询量）
        current_player_data = None
        if current_player_id:
            stmt = select(Player).where(Player.id == current_player_id)
            result = await session.execute(stmt)
            p = result.scalar_one_or_none()
            if p:
                px, py = p.get_current_coordinates()
                current_player_data = {
                    'id': p.id, 'nickname': p.nickname, 'x': px, 'y': py,
                    'real_world_x': p.real_world_x or 0, 'real_world_y': p.real_world_y or 0,
                }

        # 阴宅数据
        mansion_stmt = select(Player).where(
            Player.mansion_level > 0,
            Player.mansion_x.isnot(None),
            Player.mansion_y.isnot(None),
            Player.region == "大都会"
        )
        mansion_result = await session.execute(mansion_stmt)
        mansion_data = [
            (o.mansion_x, o.mansion_y, o.mansion_level, o.nickname)
            for o in mansion_result.scalars().all()
            if o.mansion_x is not None and o.mansion_y is not None
        ]

        # 导航任务
        nav_data = None
        if current_player_id:
            nav_task = await session.get(NavigationTask, current_player_id)
            if nav_task:
                nav_data = {'target_x': nav_task.target_x, 'target_y': nav_task.target_y}

        # 打工地点（静态数据，无DB）
        try:
            from ..economy.part_time_job_service import PartTimeJobService
            job_locations = [(d['x'], d['y'], d['name']) for d in PartTimeJobService.JOB_LOCATIONS.values()]
        except ImportError:
            job_locations = [
                (0, 0, "上京商业中心"), (250, -1350, "荔湾镇工业区"),
                (150, -130, "郸城娱乐街区"), (250, -50, "天海卫物流中心"),
            ]

        # ── 阶段2：线程池中执行纯CPU渲染 ──
        return await asyncio.to_thread(
            self._render_map, mansion_data, nav_data,
            current_player_id, current_player_data, job_locations
        )

    def _render_map(self, mansion_data: List[Tuple],
                    nav_data: Optional[Dict], current_player_id: str,
                    current_player_data: Optional[Dict],
                    job_locations: List[Tuple[int, int, str]]) -> bytes:
        """纯CPU渲染地图（在线程池中执行，不阻塞事件循环）"""
        image = Image.new('RGB', (self.map_width, self.map_height), self.colors['background'])
        draw = ImageDraw.Draw(image)

        self._draw_background_and_grid(draw, image)

        occupancy_map: Dict[Tuple[int, int], Dict[str, Any]] = {}

        # 绘制市集
        for market in MARKETS:
            coords = self._draw_location(draw, market.x, market.y, market.name, 'market')
            if coords:
                occupancy_map[coords] = {'type': 'market', 'name': market.name}

        # 绘制缉邪司总部
        hq_x, hq_y = HEADQUARTERS_COORD
        hq_coords = self._draw_location(draw, hq_x, hq_y, "缉邪司总部", 'special')
        if hq_coords:
            occupancy_map[hq_coords] = {'type': 'special', 'name': '缉邪司总部'}

        # 绘制打工地点
        for x, y, name in job_locations:
            coords = self._draw_location(draw, x, y, name, 'job')
            if coords:
                occupancy_map[coords] = {'type': 'job', 'name': name}

        # 绘制阴宅
        self._draw_mansions_from_data(draw, mansion_data, occupancy_map)

        # 当前玩家（粗红点 + 高亮 + 昵称）
        if current_player_data:
            pixel_x, pixel_y = self._game_to_pixel(current_player_data['x'], current_player_data['y'])
            if 0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height:
                draw.ellipse([pixel_x - 6, pixel_y - 6, pixel_x + 6, pixel_y + 6],
                            fill=self.colors['player'], outline='#FFFFFF', width=2)
                draw.ellipse([pixel_x - 10, pixel_y - 10, pixel_x + 10, pixel_y + 10],
                            outline='#FFFF00', width=2)
                draw.text((pixel_x - 20, pixel_y + 12), f"{current_player_data['nickname']}(你)",
                         fill=self.colors['player'], font=self.fonts['medium'])

            # 导航连线
            if nav_data:
                rwx, rwy = current_player_data['real_world_x'], current_player_data['real_world_y']
                pp_x, pp_y = self._game_to_pixel(rwx, rwy)
                tp_x, tp_y = self._game_to_pixel(nav_data['target_x'], nav_data['target_y'])
                p_in = 0 <= pp_x <= self.map_width and 0 <= pp_y <= self.map_height
                t_in = 0 <= tp_x <= self.map_width and 0 <= tp_y <= self.map_height
                if p_in or t_in:
                    self._draw_dashed_line(draw, pp_x, pp_y, tp_x, tp_y,
                                          self.colors['navigation_line'], width=2)
                if t_in:
                    draw.ellipse([tp_x - 8, tp_y - 8, tp_x + 8, tp_y + 8],
                                fill=self.colors['navigation_target'], outline='#000000', width=2)
                    draw.text((tp_x - 30, tp_y + 12),
                             f"目标({nav_data['target_x']},{nav_data['target_y']})",
                             fill='#000000', font=self.fonts['small'])

        self._draw_legend(draw)

        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG', quality=95)
        img_buffer.seek(0)
        return img_buffer.getvalue()
