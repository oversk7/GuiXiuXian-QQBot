"""
Cyberpunk Hacking 游戏矩阵图片生成器
赛博朋克风格的视觉呈现
"""
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple
import io
import base64

class CyberpunkHackingImageGenerator:
    """赛博朋克阵法破解图片生成器"""

    # 赛博朋克配色方案
    COLOR_BG = (15, 20, 30)  # 深色背景
    COLOR_GRID = (0, 255, 255, 100)  # 青色网格（半透明）
    COLOR_RUNE = (0, 255, 255)  # 青色符文
    COLOR_RUNE_DIM = (0, 180, 180)  # 暗青色符文（不可选）
    COLOR_RUNE_HIGHLIGHT = (255, 255, 0)  # 黄色高亮（可选）
    COLOR_SELECTED = (255, 100, 255)  # 紫色（已选）
    COLOR_TEXT = (200, 220, 255)  # 浅蓝色文字
    COLOR_TARGET = (0, 255, 100)  # 绿色（目标序列）
    COLOR_COMPLETED = (100, 100, 100)  # 灰色（已完成）

    def __init__(self, size: int = 5):
        self.size = size
        self.cell_size = 80  # 每个格子的大小
        self.padding = 60  # 边距
        self.info_height = 300  # 信息区域高度

        # 计算总尺寸
        self.grid_width = self.size * self.cell_size
        self.grid_height = self.size * self.cell_size
        self.total_width = self.grid_width + self.padding * 2
        self.total_height = self.grid_height + self.padding * 2 + self.info_height

        # 尝试加载字体
        try:
            self.font_large = ImageFont.truetype("msyh.ttc", 32)  # 微软雅黑
            self.font_medium = ImageFont.truetype("msyh.ttc", 24)
            self.font_small = ImageFont.truetype("msyh.ttc", 18)
        except:
            # 如果找不到字体，使用默认字体
            self.font_large = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def generate_image(self, game) -> bytes:
        """生成游戏矩阵图片"""
        # 创建图片
        img = Image.new('RGB', (self.total_width, self.total_height), self.COLOR_BG)
        draw = ImageDraw.Draw(img, 'RGBA')

        # 绘制标题
        self._draw_title(draw)

        # 绘制网格和符文
        self._draw_grid(draw, game)

        # 绘制信息区域
        self._draw_info(draw, game)

        # 转换为bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue()

    def _draw_title(self, draw):
        """绘制标题"""
        title = "仙门奇术 · 阵法破解"
        title_bbox = draw.textbbox((0, 0), title, font=self.font_large)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (self.total_width - title_width) // 2
        title_y = 15

        # 绘制发光效果（多层叠加）
        for offset in range(3, 0, -1):
            alpha = 50 + offset * 20
            glow_color = (*self.COLOR_RUNE, alpha)
            draw.text((title_x, title_y), title, font=self.font_large, fill=glow_color)

        # 绘制主标题
        draw.text((title_x, title_y), title, font=self.font_large, fill=self.COLOR_RUNE)

    def _draw_grid(self, draw, game):
        """绘制网格和符文"""
        start_x = self.padding
        start_y = self.padding + 50

        # 收集已选择的位置
        selected_positions = set(game.current_path)

        # 绘制网格线
        for i in range(self.size + 1):
            # 垂直线
            x = start_x + i * self.cell_size
            draw.line([(x, start_y), (x, start_y + self.grid_height)],
                     fill=self.COLOR_GRID, width=2)
            # 水平线
            y = start_y + i * self.cell_size
            draw.line([(start_x, y), (start_x + self.grid_width, y)],
                     fill=self.COLOR_GRID, width=2)

        # 绘制列标号
        for col in range(self.size):
            x = start_x + col * self.cell_size + self.cell_size // 2
            y = start_y - 30
            text = str(col + 1)
            bbox = draw.textbbox((0, 0), text, font=self.font_medium)
            text_width = bbox[2] - bbox[0]
            draw.text((x - text_width // 2, y), text,
                     font=self.font_medium, fill=self.COLOR_TEXT)

        # 绘制行标号
        for row in range(self.size):
            x = start_x - 35
            y = start_y + row * self.cell_size + self.cell_size // 2
            text = str(row + 1)
            bbox = draw.textbbox((0, 0), text, font=self.font_medium)
            text_height = bbox[3] - bbox[1]
            draw.text((x, y - text_height // 2), text,
                     font=self.font_medium, fill=self.COLOR_TEXT)

        # 绘制符文
        for row in range(self.size):
            for col in range(self.size):
                x = start_x + col * self.cell_size
                y = start_y + row * self.cell_size
                rune = game.matrix[row][col]

                # 判断是否可选
                can_select = game._can_select_position(row, col)
                is_selected = (row, col) in selected_positions

                # 绘制背景高亮
                if is_selected:
                    # 已选择：紫色高亮
                    draw.rectangle([x+2, y+2, x+self.cell_size-2, y+self.cell_size-2],
                                  fill=(*self.COLOR_SELECTED, 50))
                elif can_select:
                    # 可选择：黄色高亮
                    draw.rectangle([x+2, y+2, x+self.cell_size-2, y+self.cell_size-2],
                                  fill=(*self.COLOR_RUNE_HIGHLIGHT, 30))

                # 绘制符文
                rune_color = self.COLOR_RUNE
                if is_selected:
                    rune_color = self.COLOR_SELECTED
                elif can_select:
                    rune_color = self.COLOR_RUNE_HIGHLIGHT
                else:
                    rune_color = self.COLOR_RUNE_DIM

                # 居中绘制符文
                bbox = draw.textbbox((0, 0), rune, font=self.font_large)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                text_x = x + (self.cell_size - text_width) // 2
                text_y = y + (self.cell_size - text_height) // 2

                # 发光效果
                if can_select or is_selected:
                    for offset in range(2, 0, -1):
                        glow_color = (*rune_color[:3], 80)
                        draw.text((text_x, text_y), rune,
                                font=self.font_large, fill=glow_color)

                draw.text((text_x, text_y), rune,
                         font=self.font_large, fill=rune_color)

    def _draw_info(self, draw, game):
        """绘制信息区域"""
        info_y = self.padding + 50 + self.grid_height + 30
        left_x = self.padding

        # 绘制目标序列
        draw.text((left_x, info_y), "🎯 破阵目标:",
                 font=self.font_medium, fill=self.COLOR_TEXT)

        target_y = info_y + 35
        for i, target in enumerate(game.target_sequences):
            status = "✅" if i in game.completed_sequences else "⭕"
            seq_str = " → ".join(target.sequence)
            text = f"{status} {target.name}: {seq_str} (+{target.reward}💰)"

            color = self.COLOR_COMPLETED if i in game.completed_sequences else self.COLOR_TARGET
            draw.text((left_x + 10, target_y), text,
                     font=self.font_small, fill=color)
            target_y += 30

        # 绘制当前状态
        status_y = target_y + 20

        # 当前符文序列
        if game.selected_codes:
            current_seq = " → ".join(game.selected_codes)
            draw.text((left_x, status_y), f"📝 当前符文: {current_seq}",
                     font=self.font_small, fill=self.COLOR_TEXT)
        else:
            draw.text((left_x, status_y), "📝 当前符文: (空)",
                     font=self.font_small, fill=self.COLOR_TEXT)

        # 灵力条
        status_y += 35
        buffer_text = f"⚡ 灵力: {len(game.current_path)}/{game.buffer_size}"
        draw.text((left_x, status_y), buffer_text,
                 font=self.font_small, fill=self.COLOR_TEXT)

        # 绘制灵力条
        bar_x = left_x + 150
        bar_y = status_y + 5
        bar_width = 200
        bar_height = 15

        # 背景条
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
                      outline=self.COLOR_GRID, width=2)

        # 填充条
        fill_width = int(bar_width * len(game.current_path) / game.buffer_size)
        if fill_width > 0:
            color = self.COLOR_TARGET if len(game.current_path) < game.buffer_size else self.COLOR_SELECTED
            draw.rectangle([bar_x + 2, bar_y + 2, bar_x + fill_width, bar_y + bar_height - 2],
                          fill=color)

        # 下一步提示
        status_y += 45
        if game.current_path:
            direction = "横向" if game.is_horizontal else "纵向"
            if game.is_horizontal:
                last_row, _ = game.current_path[-1]
                hint = f"🧭 下一步: {direction}移动（在第{last_row+1}行选择不同列）"
            else:
                _, last_col = game.current_path[-1]
                hint = f"🧭 下一步: {direction}移动（在第{last_col+1}列选择不同行）"
        else:
            hint = "🧭 下一步: 选择第一行任意位置"

        draw.text((left_x, status_y), hint,
                 font=self.font_small, fill=self.COLOR_RUNE_HIGHLIGHT)


def generate_game_image(game) -> bytes:
    """生成游戏图片的便捷函数"""
    generator = CyberpunkHackingImageGenerator(game.size)
    return generator.generate_image(game)
