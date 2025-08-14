from __future__ import annotations

"""地图可视化系统

生成漂亮的地图图片，显示：
1. 坐标网格
2. 各种地点标注
3. 玩家位置（红点）
4. 美观的背景和样式
"""

import io
import math
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.part_time_job import JobLocation
from ..economy.merchants import MARKETS, HEADQUARTERS_COORD


class MapVisualizer:
    """地图可视化器"""
    
    def __init__(self):
        # 地图配置
        self.map_width = 1200
        self.map_height = 800
        self.grid_size = 20  # 每个网格的像素大小
        self.coordinate_scale = 50  # 坐标缩放比例，50像素 = 1游戏坐标
        
        # 颜色配置
        self.colors = {
            'background': '#E6F3FF',  # 浅蓝色背景
            'grid': '#D0E8FF',        # 网格线颜色
            'coordinate_text': '#666666',  # 坐标文字颜色
            'player': '#FF4444',      # 玩家红点
            'market': '#FF8800',      # 市集橙色
            'job': '#8844FF',         # 打工地点紫色
            'special': '#FF44FF',     # 特殊地点粉色
            'border': '#4488CC',      # 边框颜色
            'location_text': '#333333',  # 地点文字颜色
        }
        
        # 字体配置（将在运行时加载）
        self.fonts = {}
        
    def _load_fonts(self):
        """加载字体，优先使用中文字体"""
        try:
            # 尝试加载系统中文字体
            font_paths = [
                # Windows 中文字体
                'C:/Windows/Fonts/msyh.ttc',      # 微软雅黑
                'C:/Windows/Fonts/simhei.ttf',    # 黑体
                'C:/Windows/Fonts/simsun.ttc',    # 宋体
                # Linux 中文字体
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                '/System/Library/Fonts/PingFang.ttc',  # macOS
            ]
            
            # 加载不同大小的字体
            for size, name in [(12, 'small'), (14, 'medium'), (16, 'large'), (20, 'title')]:
                font_loaded = False
                for font_path in font_paths:
                    try:
                        self.fonts[name] = ImageFont.truetype(font_path, size)
                        font_loaded = True
                        break
                    except (OSError, IOError):
                        continue
                
                if not font_loaded:
                    # 使用默认字体
                    self.fonts[name] = ImageFont.load_default()
                    
        except Exception:
            # 全部使用默认字体
            for name in ['small', 'medium', 'large', 'title']:
                self.fonts[name] = ImageFont.load_default()
    
    def _game_to_pixel(self, x: int, y: int) -> Tuple[int, int]:
        """将游戏坐标转换为像素坐标"""
        # 游戏坐标原点在地图中心
        center_x = self.map_width // 2
        center_y = self.map_height // 2
        
        pixel_x = center_x + (x * self.map_width // 1000)  # 假设游戏世界范围是-500到500
        pixel_y = center_y - (y * self.map_height // 800)  # Y轴翻转，向上为正
        
        return pixel_x, pixel_y
    
    def _draw_background_and_grid(self, draw: ImageDraw.Draw):
        """绘制背景和网格"""
        # 填充背景色
        draw.rectangle([0, 0, self.map_width, self.map_height], fill=self.colors['background'])
        
        # 绘制网格线
        for x in range(0, self.map_width, self.grid_size):
            draw.line([x, 0, x, self.map_height], fill=self.colors['grid'], width=1)
        for y in range(0, self.map_height, self.grid_size):
            draw.line([0, y, self.map_width, y], fill=self.colors['grid'], width=1)
        
        # 绘制坐标轴
        center_x = self.map_width // 2
        center_y = self.map_height // 2
        
        # X轴
        draw.line([0, center_y, self.map_width, center_y], fill=self.colors['border'], width=2)
        # Y轴
        draw.line([center_x, 0, center_x, self.map_height], fill=self.colors['border'], width=2)
        
        # 绘制坐标刻度
        for i in range(-500, 501, 100):
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
                      location_type: str, size: int = 8):
        """绘制地点标记"""
        pixel_x, pixel_y = self._game_to_pixel(x, y)

        # 确保在地图范围内
        if not (0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height):
            return

        # 根据类型选择颜色
        color = self.colors.get(location_type, self.colors['special'])

        # 只绘制地点标记（圆形），不显示任何文字
        draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size],
                    fill=color, outline='#000000', width=2)
    
    def _draw_players(self, draw: ImageDraw.Draw, players: List[Player]):
        """绘制玩家位置"""
        for player in players:
            pixel_x, pixel_y = self._game_to_pixel(player.x, player.y)

            # 确保在地图范围内
            if not (0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height):
                continue

            # 只绘制玩家红点，不显示任何文字
            size = 6
            draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size],
                        fill=self.colors['player'], outline='#FFFFFF', width=2)
    
    def _draw_legend(self, draw: ImageDraw.Draw):
        """绘制图例"""
        legend_x = 20
        legend_y = 20
        legend_width = 200
        legend_height = 120
        
        # 绘制图例背景
        draw.rectangle([legend_x, legend_y, legend_x + legend_width, legend_y + legend_height], 
                      fill='#FFFFFF', outline=self.colors['border'], width=2)
        
        # 图例标题
        draw.text((legend_x + 10, legend_y + 10), "图例", fill=self.colors['location_text'], font=self.fonts['large'])
        
        # 图例项目
        legend_items = [
            ("🔴 玩家位置", self.colors['player']),
            ("🟠 市集交易", self.colors['market']),
            ("🟣 打工地点", self.colors['job']),
            ("🟡 特殊地点", self.colors['special']),
        ]
        
        for i, (text, color) in enumerate(legend_items):
            item_y = legend_y + 35 + i * 20
            # 绘制颜色标记
            draw.ellipse([legend_x + 15, item_y, legend_x + 25, item_y + 10], fill=color)
            # 绘制文字
            draw.text((legend_x + 35, item_y - 2), text[2:], fill=self.colors['location_text'], font=self.fonts['small'])
    
    async def generate_map(self, session: AsyncSession, current_player_id: str = None) -> bytes:
        """生成地图图片"""
        # 加载字体
        self._load_fonts()
        
        # 创建图片
        image = Image.new('RGB', (self.map_width, self.map_height), self.colors['background'])
        draw = ImageDraw.Draw(image)
        
        # 绘制背景和网格
        self._draw_background_and_grid(draw)
        
        # 绘制市集
        for market in MARKETS:
            self._draw_location(draw, market.x, market.y, market.name, 'market')
        
        # 绘制缉邪司总部
        hq_x, hq_y = HEADQUARTERS_COORD
        self._draw_location(draw, hq_x, hq_y, "缉邪司总部", 'special')
        
        # 绘制打工地点
        try:
            from ..economy.part_time_job_service import PartTimeJobService
            for location_data in PartTimeJobService.JOB_LOCATIONS.values():
                self._draw_location(draw, location_data['x'], location_data['y'], 
                                  location_data['name'], 'job')
        except ImportError:
            # 如果导入失败，使用默认配置
            default_jobs = [
                (0, 0, "上京商业中心"),
                (100, 200, "制造工业区"),
                (-50, 150, "休闲娱乐街区"),
                (200, -100, "物流配送中心"),
            ]
            for x, y, name in default_jobs:
                self._draw_location(draw, x, y, name, 'job')
        
        # 查询并绘制玩家位置
        stmt = select(Player).where(Player.region == "大都会")
        result = await session.execute(stmt)
        players = result.scalars().all()
        
        # 如果指定了当前玩家，将其放在最后绘制（显示在最上层）
        if current_player_id:
            current_player = None
            other_players = []
            for player in players:
                if player.id == current_player_id:
                    current_player = player
                else:
                    other_players.append(player)
            
            # 先绘制其他玩家
            self._draw_players(draw, other_players)
            # 再绘制当前玩家（高亮显示）
            if current_player:
                pixel_x, pixel_y = self._game_to_pixel(current_player.x, current_player.y)
                if 0 <= pixel_x <= self.map_width and 0 <= pixel_y <= self.map_height:
                    # 绘制高亮圆圈
                    size = 12
                    draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size], 
                                fill=None, outline='#FFFF00', width=3)
                    # 绘制玩家点
                    size = 8
                    draw.ellipse([pixel_x - size, pixel_y - size, pixel_x + size, pixel_y + size], 
                                fill=self.colors['player'], outline='#FFFFFF', width=2)
                    # 绘制玩家昵称
                    text_x = pixel_x + size + 3
                    text_y = pixel_y - 8
                    draw.text((text_x, text_y), f"{current_player.nickname}(你)", 
                             fill=self.colors['player'], font=self.fonts['medium'])
        else:
            self._draw_players(draw, players)
        
        # 绘制图例
        self._draw_legend(draw)
        
        # 将图片转换为字节流
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG', quality=95)
        img_buffer.seek(0)
        
        return img_buffer.getvalue()
