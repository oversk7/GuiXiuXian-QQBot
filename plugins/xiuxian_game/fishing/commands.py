"""钓鱼系统指令处理器

实现钓鱼相关的用户交互界面
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta

from ..models.db import safe_session
from ..models.fishing_record import FishingRecord, FishingStats
from ..models.inventory import ItemInstance
from ..utils_markdown import cmd, build_markdown, color_rarity
from ..config import config
from .service import FishingService

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的FishingService，False使用旧版本
# =====================================================


# 钓鱼指令
fishing_cmd = on_command("钓鱼", block=True, priority=5)

@fishing_cmd.handle()
async def _(event: MessageEvent):
    """钓鱼指令处理"""
    async with safe_session() as session:
        try:
            # 使用跨平台工具获取玩家数据
            from ..platform_utils import require_player
            player = await require_player(session, event, fishing_cmd)

            # 执行钓鱼
            from ..infrastructure.repositories.fishing_record_repository import FishingRecordRepository
            from ..infrastructure.repositories.fishing_stats_repository import FishingStatsRepository
            from ..infrastructure.repositories.item_repository import ItemRepository
            from .service import FishingService

            service = FishingService(
                fishing_record_repo=FishingRecordRepository(session),
                fishing_stats_repo=FishingStatsRepository(session),
                item_repo=ItemRepository(session),
            )
            result = await service.do_fishing(player)
            if not result["success"]:
                await fishing_cmd.finish(build_markdown(result["message"]))

            # 鱼竿特权：额外多钓2条（独立计算品质）
            from ..sponsor.service import SponsorShopService
            extra_catches = []
            if SponsorShopService.is_privilege_active(player, "premium_fishing_until"):
                current_x, current_y = player.get_current_coordinates()
                for _ in range(2):
                    extra_rarity = FishingService.calculate_fish_rarity(player)
                    extra_fish_id = FishingService.get_random_fish(extra_rarity)
                    extra_fish_cfg = config.items_config["by_id"].get(extra_fish_id)
                    if extra_fish_cfg:
                        try:
                            await service._item_repo.add_item(player.id, extra_fish_id, 1)
                            # 特权额外鱼不记录record_fishing，避免占用每日钓鱼次数
                            fishing_stats_obj = await service._fishing_stats_repo.get_or_create(player.id)
                            await service._fishing_stats_repo.update_stats(
                                fishing_stats_obj, extra_fish_cfg.price, extra_rarity, 1
                            )
                            rarity_emoji_map = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}
                            extra_catches.append(
                                f"{rarity_emoji_map.get(extra_rarity, '⚪')}{extra_fish_cfg.name}×1"
                            )
                        except ValueError:
                            pass

                # 保底机制：今日钓满50次后额外赠送1条传说鱼
                stats_check = await service._fishing_record_repo.get_player_fishing_stats(player.id)
                if stats_check["today_fishing_count"] >= FishingService.DAILY_FISHING_LIMIT:
                    legend_fish_id = FishingService.get_random_fish("orange")
                    legend_fish_cfg = config.items_config["by_id"].get(legend_fish_id)
                    if legend_fish_cfg:
                        try:
                            await service._item_repo.add_item(player.id, legend_fish_id, 1)
                            # 保底鱼不记录record_fishing，避免占用每日钓鱼次数
                            fishing_stats_obj = await service._fishing_stats_repo.get_or_create(player.id)
                            await service._fishing_stats_repo.update_stats(
                                fishing_stats_obj, legend_fish_cfg.price, "orange", 1
                            )
                            extra_catches.append(
                                f"🟠{legend_fish_cfg.name}×1（每日保底）"
                            )
                        except ValueError:
                            pass
        except TypeError as e:
            if "unsupported operand type(s) for +=: 'NoneType' and 'int'" in str(e):
                await fishing_cmd.finish(build_markdown("⛔ 钓鱼数据异常，请联系管理员处理"))
            else:
                # 其他TypeError也正常finish，不要raise
                await fishing_cmd.finish(build_markdown(f"⛔ 钓鱼发生错误：{str(e)}"))

        # ⚠️ 关键修复：必须在finish()之前commit，否则finish()抛出的异常会导致rollback
        await session.commit()

        # 新手任务钩子
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(session, player, "command", {"command": "钓鱼"})

        # 构建成功消息 - 使用图鉴MD模版
        rarity_emoji = {
            "white": "⚪",
            "green": "🟢",
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠"
        }

        emoji = rarity_emoji.get(result["rarity"], "⚪")

        # 根据稀有度显示不同的祝贺信息
        if result["rarity"] == "orange":
            celebration = "🎉✨ 传说级收获！！！ ✨🎉"
        elif result["rarity"] == "purple":
            celebration = "🎊 稀有鱼类！！ 🎊"
        elif result["rarity"] == "blue":
            celebration = "🌟 优质鱼类！ 🌟"
        else:
            celebration = "🎣 钓鱼成功！"

        quantity_text = f"×{result['quantity']}" if result['quantity'] > 1 else ""

        # 使用图鉴MD模版 (102499345_1769178984)
        # 获取鱼类配置
        fish_config = config.items_config["by_id"].get(result["fish_id"])
        if not fish_config:
            # 如果没有配置，使用文字版本
            content = (
                f"# {celebration}\n"
                f"***\n"
                f"🐟 {emoji}{result['fish_name']}{quantity_text}\n"
                f"💰 价值：**{result['value']}** 金币\n"
                f"***\n"
                f"🎣 继续钓鱼需等待 {FishingService.FISHING_COOLDOWN} 分钟"
            )
            if quest_completed and quest_msg:
                content += "\n\n" + quest_msg
            if extra_catches:
                content += "\n🎣 鱼竿特权额外收获：" + "、".join(extra_catches)
            buttons = f"\n{cmd('钓鱼')} | {cmd('鱼栏')} | {cmd('钓鱼记录')} | {cmd('钓鱼图鉴')}"
            await fishing_cmd.finish(build_markdown(content + buttons))

        # 原生 Markdown 卡片
        lines = [
            f"# {celebration}",
            "***",
            f"🐟 {emoji}{color_rarity(result['fish_name'], result['rarity'])}{quantity_text}",
            f"💰 价值：**{result['value']}** 金币",
        ]

        # 鱼类图片（使用catalog.py中的函数）
        from ..item.catalog import _get_item_image_url
        fish_image_url = _get_item_image_url(result["fish_id"])
        if fish_image_url:
            # 鱼类图片统一尺寸：宽300x高163
            lines.append(f"![{result['fish_name']} #300px #163px]({fish_image_url})")

        # 鱼类描述
        if fish_config.description:
            lines.append("***")
            lines.append(f"📖 *{fish_config.description}*")

        # 新手任务消息
        if quest_completed and quest_msg:
            lines.append(quest_msg.strip())

        # 鱼竿特权额外收获
        if extra_catches:
            lines.append(f"🎣 鱼竿特权额外收获：{'、'.join(extra_catches)}")

        lines.append("***")
        lines.append(f"> 🎣 继续钓鱼需等待 {FishingService.FISHING_COOLDOWN} 分钟")
        lines.append(f"{cmd('鱼栏')} | {cmd('钓鱼记录')} | {cmd('钓鱼排行')} | {cmd('钓鱼图鉴')}")

        await fishing_cmd.finish(build_markdown("\n".join(lines)))


# 钓鱼记录指令
fishing_record_cmd = on_command("钓鱼记录", aliases={"我的钓鱼"}, block=True, priority=5)

@fishing_record_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """查看钓鱼记录"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        player = await require_player(session, event, fishing_record_cmd)

        # 获取钓鱼统计
        stats = await FishingRecord.get_player_fishing_stats(session, player.id)
        
        # 获取最近钓鱼记录
        recent_records = await FishingRecord.get_recent_fishing_records(session, player.id, 5)
        
        lines = [
            "# 🎣 钓鱼记录",
            "***",
            f"📊 总钓鱼次数：**{stats['total_fishing_count']}**",
            f"🐟 总钓鱼数量：**{stats['total_fish_caught']}**",
            f"📅 今日钓鱼：**{stats['today_fishing_count']}**/{FishingService.DAILY_FISHING_LIMIT}",
            "***"
        ]

        if recent_records:
            lines.append("🕐 最近记录：")
            for record in recent_records:
                fish_config = config.items_config["by_id"].get(record.fish_id)
                if fish_config:
                    rarity_display = fish_config.get_rarity_display()
                    quantity_text = f"×{record.quantity}" if record.quantity > 1 else ""
                    time_str = record.fishing_time.strftime("%m-%d %H:%M")
                    lines.append(f"  {rarity_display}{fish_config.name}{quantity_text} ({time_str})")
        else:
            lines.append("📝 暂无钓鱼记录")

        buttons = f"\n{cmd('钓鱼')} | {cmd('钓鱼状态')} | {cmd('钓鱼排行')} | {cmd('钓鱼图鉴')}"

        await fishing_record_cmd.finish(build_markdown("\n".join(lines) + buttons))


# 钓鱼排行榜指令
fishing_leaderboard_cmd = on_command("钓鱼排行", aliases={"钓鱼榜"}, block=True, priority=5)

@fishing_leaderboard_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼排行榜（按区服隔离）"""
    async with safe_session() as session:
        from ..platform_utils import require_player
        from ..infrastructure.repositories.fishing_record_repository import FishingRecordRepository
        from ..infrastructure.repositories.fishing_stats_repository import FishingStatsRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from .service import FishingService

        player = await require_player(session, event, fishing_leaderboard_cmd)

        service = FishingService(
            fishing_record_repo=FishingRecordRepository(session),
            fishing_stats_repo=FishingStatsRepository(session),
            item_repo=ItemRepository(session),
        )
        leaderboard = await service.get_fishing_leaderboard(10, player.server_id)
        if not leaderboard:
            await fishing_leaderboard_cmd.finish(build_markdown("📊 暂无钓鱼排行数据"))

        lines = [
            f"# 🏆 钓鱼排行榜（{player.server_id}区 · 按总价值）",
            "***"
        ]

        for i, player_data in enumerate(leaderboard, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

            nick_cmd = cmd(player_data['nickname'], f"面板 {player_data['uid']}")
            lines.append(
                f"{medal} {nick_cmd}\n"
                f"   💰 总价值：**{player_data['total_fish_value']}**\n"
                f"   🎣 钓鱼次数：**{player_data['total_fishing_count']}**\n"
                f"   🐟 鱼类数量：**{player_data['total_fish_caught']}**"
            )

            if player_data['legendary_fish_caught'] > 0:
                lines.append(f"   🟠 传说鱼类：**{player_data['legendary_fish_caught']}**")
            if player_data['rare_fish_caught'] > 0:
                lines.append(f"   🟣 稀有鱼类：**{player_data['rare_fish_caught']}**")

            lines.append("***")

        buttons = f"\n{cmd('钓鱼')} | {cmd('钓鱼记录')} | {cmd('钓鱼图鉴')}"

        await fishing_leaderboard_cmd.finish(build_markdown("\n".join(lines) + buttons))


# 钓鱼状态指令
fishing_status_cmd = on_command("钓鱼状态", block=True, priority=5)

@fishing_status_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼状态"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        player = await require_player(session, event, fishing_status_cmd)

        # 检查钓鱼状态
        from ..infrastructure.repositories.fishing_record_repository import FishingRecordRepository
        from ..infrastructure.repositories.fishing_stats_repository import FishingStatsRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from .service import FishingService

        service = FishingService(
            fishing_record_repo=FishingRecordRepository(session),
            fishing_stats_repo=FishingStatsRepository(session),
            item_repo=ItemRepository(session),
        )
        can_fish, reason = await service.can_fishing(player)
        # 获取统计信息
        stats = await FishingRecord.get_player_fishing_stats(session, player.id)
        
        # 获取钓鱼统计记录
        fishing_stats = await FishingStats.get_or_create(session, player.id)
        
        lines = [
            "# 🎣 钓鱼状态",
            "***"
        ]

        if can_fish:
            lines.append("✅ 可以钓鱼")
        else:
            lines.append(f"⏰ {reason}")

        lines.extend([
            f"📅 今日钓鱼：**{stats['today_fishing_count']}**/{FishingService.DAILY_FISHING_LIMIT}",
            f"🎣 总钓鱼次数：**{stats['total_fishing_count']}**",
            f"🐟 总鱼类数量：**{stats['total_fish_caught']}**",
            f"💰 总鱼类价值：**{fishing_stats.total_fish_value}**",
            "***"
        ])

        if fishing_stats.rare_fish_caught > 0:
            lines.append(f"🟣 稀有鱼类：**{fishing_stats.rare_fish_caught}**")
        if fishing_stats.legendary_fish_caught > 0:
            lines.append(f"🟠 传说鱼类：**{fishing_stats.legendary_fish_caught}**")
        if fishing_stats.best_fish_value > 0:
            lines.append(f"🏆 最贵单鱼：**{fishing_stats.best_fish_value}** 金币")

        lines.extend([
            "***",
            f"🍀 运气值：**{player.luck}**（影响稀有鱼概率）",
            "💡 运气值越高，钓到稀有鱼的概率越大"
        ])

        buttons = f"\n{cmd('钓鱼')} | {cmd('钓鱼记录')} | {cmd('钓鱼排行')}"

        await fishing_status_cmd.finish(build_markdown("\n".join(lines) + buttons))


# 钓鱼图鉴指令
fishing_guide_cmd = on_command("钓鱼图鉴", aliases={"鱼类图鉴"}, block=True, priority=5)

@fishing_guide_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼图鉴"""
    lines = [
        "# 📖 钓鱼图鉴",
        "***",
        "🎣 **钓鱼系统说明：**",
        f"• 随时随地可以{cmd('钓鱼')}，方便新手",
        f"• 每次钓鱼冷却时间：**{FishingService.FISHING_COOLDOWN}**分钟",
        f"• 每日钓鱼次数限制：**{FishingService.DAILY_FISHING_LIMIT}**次",
        "• 运气值大幅影响稀有鱼概率和数量",
        "• 高运气玩家将获得显著的钓鱼加成",
        "***",
        "🐟 **鱼类稀有度（基础概率）：**",
        "⚪ 普通（55%）- 鲤鱼、鲫鱼、草鱼等",
        "🟢 优良（28%）- 鲈鱼、桂鱼、黄花鱼等",
        "🔵 精品（14%）- 三文鱼、金枪鱼、石斑鱼等",
        "🟣 稀有（2.5%）- 中华鲟、龙鱼等",
        "🟠 传说（0.5%）- 金龙鱼、凤凰鱼等",
        "",
        "🍀 **运气加成效果：**",
        "• 🟠传说鱼：运气加成最高（最多+300%）",
        "• 🟣稀有鱼：运气加成很高（最多+200%）",
        "• 🔵精品鱼：运气加成中等（最多+100%）",
        "• 🟢优良鱼：运气加成较小（最多+50%）",
        "• ⚪普通鱼：不受运气影响，但数量有加成",
        "***",
        "🎒 **鱼栏系统：**",
        "• 鱼类存入专属鱼栏，不占背包空间",
        f"• 使用{cmd('鱼栏')}查看所有鱼类存量和总估值",
        "• 鱼栏容量无限制，可以尽情钓鱼",
        "***",
        "💰 **鱼类用途：**",
        "• 可在沿海城市出售给商人（舟山/海门/鹭岛/荔湾镇/鹏城/琼崖）",
        "• 稀有鱼类价值更高",
        f"• 参与{cmd('钓鱼排行')}榜竞争",
        f"• 使用{cmd('丢弃')}指令放生鱼类，获得功德",
        "***",
        "📋 **相关指令：**",
        f"{cmd('钓鱼')} - 开始钓鱼",
        f"{cmd('钓鱼记录')} - 查看钓鱼记录",
        f"{cmd('钓鱼状态')} - 查看当前状态",
        f"{cmd('钓鱼排行')} - 查看排行榜",
        f"{cmd('鱼栏')} - 查看鱼类存量",
        f"{cmd('吃鱼 鱼名 数量', '吃鱼 ')} - 品尝鱼类美味",
        f"{cmd('丢弃')} - 放生鱼类，获得功德"
    ]

    buttons = f"\n{cmd('钓鱼')} | {cmd('钓鱼状态')} | {cmd('钓鱼概率')}"

    await fishing_guide_cmd.finish(build_markdown("\n".join(lines) + buttons))


# 钓鱼概率查询指令
fishing_prob_cmd = on_command("钓鱼概率", aliases={"鱼类概率", "我的鱼率"}, block=True, priority=5)

@fishing_prob_cmd.handle()
async def _(event: MessageEvent):
    """查看钓鱼概率"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        from ..infrastructure.repositories.fishing_record_repository import FishingRecordRepository
        from ..infrastructure.repositories.fishing_stats_repository import FishingStatsRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from .service import FishingService

        player = await require_player(session, event, fishing_prob_cmd)

        # 计算概率
        probabilities = FishingService.calculate_fishing_probabilities(player)

        # 稀有度显示映射
        rarity_display = {
            "white": ("⚪ 普通鱼", "white"),
            "green": ("🟢 优良鱼", "green"),
            "blue": ("🔵 精品鱼", "blue"),
            "purple": ("🟣 稀有鱼", "purple"),
            "orange": ("🟠 传说鱼", "orange")
        }

        lines = [
            "# 📊 我的钓鱼概率",
            "***",
            f"🍀 当前幸运值：**{player.luck}**",
            "***",
            "🐟 各品阶鱼类概率：",
            ""
        ]

        # 按稀有度从低到高显示
        for rarity in ["white", "green", "blue", "purple", "orange"]:
            rarity_name, rarity_key = rarity_display[rarity]
            prob_data = probabilities[rarity]
            base_rate = prob_data["base_rate"]
            actual_rate = prob_data["actual_rate"]
            multiplier = prob_data["multiplier"]

            # 计算提升百分比
            improvement = ((actual_rate - base_rate) / base_rate) * 100 if base_rate > 0 else 0

            # 显示格式
            if rarity == "white":
                lines.append(f"{rarity_name} **{actual_rate:.2f}%**")
            else:
                if improvement > 0:
                    lines.append(f"{rarity_name} **{actual_rate:.2f}%** (基础{base_rate}% x {multiplier:.2f}倍, +{improvement:.1f}%)")
                else:
                    lines.append(f"{rarity_name} **{actual_rate:.2f}%** (基础{base_rate}%)")

        lines.extend([
            "",
            "***",
            "💡 说明：",
            "• 幸运值影响稀有鱼概率和数量",
            "• 幸运值越高，钓到稀有鱼概率越大",
            "• 概率已自动归一化处理",
        ])

        buttons = f"\n{cmd('钓鱼')} | {cmd('钓鱼状态')} | {cmd('钓鱼图鉴')}"

        await fishing_prob_cmd.finish(build_markdown("\n".join(lines) + buttons))


# 吃鱼指令（娱乐功能，实际为丢弃）
eat_fish_cmd = on_command("吃鱼", aliases={"吃掉鱼", "品尝鱼"}, block=True, priority=5)

@eat_fish_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """吃鱼指令（实际为丢弃鱼类物品）

    用法：吃鱼 [鱼类名称] [数量]
    示例：吃鱼 鲤鱼 2
    """
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await eat_fish_cmd.finish("⛔ 格式错误，正确格式：吃鱼 [鱼类名称] [数量]")

    fish_name, qty_str = params

    # 参数校验
    try:
        quantity = int(qty_str)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await eat_fish_cmd.finish("⛔ 数量必须为正整数")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        player = await require_player(session, event, eat_fish_cmd)

        # 通过名称查找鱼类物品
        fish_config = config.items_config["by_name"].get(fish_name)
        if not fish_config:
            await eat_fish_cmd.finish(f"⛔ 不存在鱼类：{fish_name}")

        # 检查是否为鱼类物品（通过item_id判断）
        # 所有鱼类物品都在钓鱼系统的鱼类列表中
        from .service import FishingService
        all_fish_ids = []
        for rarity_config in FishingService.FISH_RARITY_CONFIG.values():
            all_fish_ids.extend(rarity_config["fish_list"])

        if fish_config.item_id not in all_fish_ids:
            await eat_fish_cmd.finish(f"⛔ {fish_name} 不是鱼类，无法食用")

        # 检查背包中是否有该鱼类
        from sqlalchemy import select
        inv_rows = (await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
            .where(ItemInstance.item_id == fish_config.item_id)
        )).scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)

        if total_qty < quantity:
            await eat_fish_cmd.finish(f"⛔ {fish_name} 数量不足，你只有 {total_qty} 条")

        try:
            # 消耗鱼类物品（实际为丢弃）
            await ItemInstance.consume_item(session, player.id, fish_config.item_id, quantity)
            await session.commit()
        except ValueError as e:
            await eat_fish_cmd.finish(f"⛔ 食用失败：{e}")

        # 根据鱼类稀有度显示不同的食用效果
        rarity_emoji = {
            "white": "⚪",
            "green": "🟢",
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠"
        }

        emoji = rarity_emoji.get(fish_config.rarity, "⚪")
        quantity_text = f"{quantity}条" if quantity > 1 else "1条"

        # 根据稀有度显示不同的食用体验
        if fish_config.rarity == "orange":
            taste_desc = "🌟 传说级的美味！仿佛整个人都被神圣的光芒包围，这味道简直是天界的馈赠！"
            effect_desc = "✨ 你感到体内涌起一股神秘的力量，仿佛连灵魂都得到了升华！"
        elif fish_config.rarity == "purple":
            taste_desc = "🎊 稀有的珍馐！肉质鲜美至极，每一口都是极致的享受！"
            effect_desc = "💫 你感到精神焕发，仿佛获得了某种特殊的力量！"
        elif fish_config.rarity == "blue":
            taste_desc = "🌟 优质的美味！肉质紧实鲜甜，让人回味无穷！"
            effect_desc = "😋 你感到心情愉悦，身体也变得轻盈了一些！"
        elif fish_config.rarity == "green":
            taste_desc = "😋 不错的味道！肉质鲜美，营养丰富！"
            effect_desc = "🍽️ 你感到饱腹感十足，精神也好了不少！"
        else:  # white
            taste_desc = "🐟 普通的鱼肉，但也算是不错的一餐！"
            effect_desc = "😊 你填饱了肚子，感觉还不错！"

        content = (
            f"# 🍽️ 美食品尝\n"
            f"***\n"
            f"🐟 品尝了 {emoji}{fish_name} x**{quantity_text}**\n"
            f"***\n"
            f"{taste_desc}\n"
            f"{effect_desc}\n"
            f"***\n"
            f"💡 虽然只是品尝，但这份美味永远留在了记忆中！"
        )

        buttons = f"\n{cmd('钓鱼')} | {cmd('鱼栏')} | {cmd('钓鱼记录')}"

        await eat_fish_cmd.finish(build_markdown(content + buttons))
