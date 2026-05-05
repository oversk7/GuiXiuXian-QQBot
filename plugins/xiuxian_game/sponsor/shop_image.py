"""赞助商店图片渲染。"""

import base64
import io
from typing import Iterable


def _load_font(size: int):
    from PIL import ImageFont

    for path in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _text_width(draw, text: str, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except AttributeError:
        return len(text) * getattr(font, "size", 16)


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _draw_card(draw, box: tuple[int, int, int, int], title: str, items: Iterable[tuple[str, str, str]], color: tuple[int, int, int], fonts: dict) -> None:
    x1, y1, x2, y2 = box
    try:
        draw.rounded_rectangle(box, radius=10, fill=(24, 27, 35), outline=color, width=2)
        draw.rounded_rectangle((x1, y1, x2, y1 + 42), radius=10, fill=(34, 36, 46))
        draw.rectangle((x1, y1 + 32, x2, y1 + 42), fill=(34, 36, 46))
    except AttributeError:
        draw.rectangle(box, fill=(24, 27, 35), outline=color)
        draw.rectangle((x1, y1, x2, y1 + 42), fill=(34, 36, 46))

    draw.text((x1 + 18, y1 + 9), title, fill=color, font=fonts["section"])
    y = y1 + 58
    for name, price, desc in items:
        draw.text((x1 + 18, y), name, fill=(244, 246, 250), font=fonts["item"])
        price_w = _text_width(draw, price, fonts["price"])
        draw.text((x2 - price_w - 18, y + 1), price, fill=(255, 205, 96), font=fonts["price"])
        y += 28
        for line in _wrap_text(draw, desc, fonts["desc"], x2 - x1 - 36):
            draw.text((x1 + 18, y), line, fill=(166, 174, 190), font=fonts["desc"])
            y += 22
        y += 8


def generate_sponsor_shop_image(balance: int, owned_titles: list[str], active_title: str | None) -> str | None:
    """生成赞助商店图片，返回 base64；PIL 不可用时返回 None。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    fonts = {
        "title": _load_font(42),
        "subtitle": _load_font(19),
        "section": _load_font(23),
        "item": _load_font(20),
        "price": _load_font(18),
        "desc": _load_font(16),
        "footer": _load_font(17),
    }

    width = 1180
    height = 1420
    img = Image.new("RGB", (width, height), (12, 15, 23))
    draw = ImageDraw.Draw(img)

    for y in range(170):
        t = y / 170
        color = (
            int(41 + 33 * t),
            int(21 + 13 * t),
            int(58 + 38 * t),
        )
        draw.line((0, y, width, y), fill=color)

    title = "诡修仙 赞助商店"
    draw.text((42, 34), title, fill=(255, 255, 255), font=fonts["title"])
    draw.text((46, 96), f"当前诡烛余额：{balance}", fill=(255, 218, 116), font=fonts["subtitle"])
    draw.text((46, 126), "确认类服务不会先扣费，目标账号确认后才完成兑换。", fill=(190, 196, 210), font=fonts["subtitle"])

    sections = [
        ("修炼与战斗", (239, 104, 104), [
            ("棺材钉", "50/根", "闭关效率+0.5%，最多100根，最高+50%"),
            ("哭坟帽", "20/顶", "使用后直接获得1万怨念值"),
            ("重启符", "1000/张", "重置所有属性点，保留装备、丹药、VIP加成"),
            ("圣诞裂隙", "30/个", "瞬移到任意坐标或诡域层级"),
        ]),
        ("月卡", (96, 165, 250), [
            ("初级月卡", "88/月", "修炼+20%，闭关9小时，背包+5，突破保护75%"),
            ("高级月卡", "288/月", "修炼+50%，闭关12小时，背包+20，自动采集"),
        ]),
        ("身份与账号", (167, 139, 250), [
            ("背包扩容", "10/格", "永久增加背包容量，上限1000格"),
            ("改名卡", "10/张", "修改一次角色名称"),
            ("公会改名", "200/次", "会长专属，修改公会名称"),
            ("自定义称号", "500/个", "购买1-8字专属展示称号"),
            ("绑定小号", "200/个", "主号发起申请，目标小号拥有者确认后转入账号列表"),
        ]),
        ("宠物饰品", (52, 211, 153), [
            ("虚空锁链", "150", "紫色颈饰，攻击+20 防御+15"),
            ("诡纹和服", "150", "紫色服饰，攻击+15 暴击+1.5%"),
            ("星辰发冠", "300", "橙色头饰，暴击率+3% 暴击伤害+10%"),
            ("银铃璎珞", "300", "橙色颈饰，连击率+3% 穿透率+3%"),
            ("流光羽衣", "300", "橙色服饰，闪避率+3% 反击率+3%"),
        ]),
        ("赞助特权", (251, 191, 36), [
            ("闭关无上限", "180/月", "闭关不再有时间上限"),
            ("远程仓库", "180/月", "随时随地存取阴宅仓库"),
            ("鱼竿特权", "180/月", "每次钓鱼额外多钓2条，50次保底传说鱼"),
            ("全视之眼", "180/月", "俯瞰直接显示诡域全部方块"),
        ]),
    ]

    card_w = 540
    card_h = [300, 200, 340, 340, 300]
    positions = [(42, 200), (598, 200), (42, 520), (598, 420), (42, 880)]
    for idx, (name, color, items) in enumerate(sections):
        x, y = positions[idx]
        _draw_card(draw, (x, y, x + card_w, y + card_h[idx]), name, items, color, fonts)

    owned_y = 880
    owned_x = 598
    owned_box_h = 300
    title_text = "已拥有称号"
    owned_lines = []
    if owned_titles:
        for title in owned_titles[:8]:
            suffix = " 当前" if title == active_title else ""
            owned_lines.append((f"「{title}」{suffix}", "", ""))
    else:
        owned_lines.append(("暂无自定义称号", "", "购买称号后会显示在这里"))
    _draw_card(draw, (owned_x, owned_y, owned_x + card_w, owned_y + owned_box_h), title_text, owned_lines, (148, 163, 184), fonts)

    footer_y = 1230
    footer = [
        "常用命令：购买重启符 N / 背包扩容 N / 购买称号 内容 / 购买绑定小号 UID",
        "确认命令：确认绑定小号 验证码",
        "记录查询：赞助记录",
    ]
    for line in footer:
        draw.text((48, footer_y), line, fill=(201, 209, 217), font=fonts["footer"])
        footer_y += 34

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
