"""
装备系统命令模块

提供装备相关的用户交互命令：
1. 查看装备栏
2. 装备详情查看
3. 穿戴装备
4. 卸下装备
5. 一键卸下
"""

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select, and_
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown, color_rarity
from ..platform_utils import require_player
# 导入装备服务模块（业务逻辑已移至此处，解决模块耦合）
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .attribute_preview_service import MAIN_ATTRS, project_equipment
from ..battle.attribute_summary import (
    MAIN_ATTRIBUTE_NAMES, BATTLE_ATTRIBUTE_NAMES, format_attribute_value,
    summarize_battle_attributes,
)
from .equipment_service import (
    recalc_equipment_attributes, EQUIP_ITEM_IDS, VIP_EQUIPMENT_IDS,
    ATTR_NAME_MAP, EquipmentService,
)
from .affix_service import get_affixes_from_equipment, format_affixes_display
from .gem_socket_service import GemSocketService
from .inscription_service import get_inscription_display, get_inscription_display_from_item
from .set_bonus_service import get_equipment_set_info, get_active_set_bonuses

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的EquipmentService，False使用旧版本
# =====================================================

BASE_EQUIPMENT_SLOT_LIMIT = 5


def get_equipment_slot_bonus(equipment: ItemInstance | None) -> int:
    """获取装备提供的额外装备槽数量。"""
    cfg = getattr(equipment, "config", None) if equipment else None
    if not cfg:
        return 0
    try:
        return max(0, int(getattr(cfg, "equipment_slot_bonus", 0) or 0))
    except (TypeError, ValueError):
        return 0


def get_equipment_slot_limit(
    equipped_items: list[ItemInstance],
    candidate: ItemInstance | None = None,
) -> int:
    """计算当前装备槽上限；candidate 用于判断本次即将穿戴的装备。"""
    limit = BASE_EQUIPMENT_SLOT_LIMIT
    counted_ids: set[int] = set()

    for eq in equipped_items:
        if not getattr(eq, "equipped", False):
            continue
        limit += get_equipment_slot_bonus(eq)
        if getattr(eq, "id", None) is not None:
            counted_ids.add(eq.id)

    if candidate and getattr(candidate, "id", None) not in counted_ids:
        limit += get_equipment_slot_bonus(candidate)

    return limit


def would_unwear_worsen_slot_overflow(
    equipped_items: list[ItemInstance],
    target: ItemInstance,
) -> tuple[bool, int, int]:
    """判断卸下 target 后是否会让已装备数量超过新槽位上限。"""
    current_count = len([eq for eq in equipped_items if getattr(eq, "equipped", False)])
    current_limit = get_equipment_slot_limit(equipped_items)

    remaining_items = [
        eq for eq in equipped_items
        if getattr(eq, "equipped", False) and getattr(eq, "id", None) != target.id
    ]
    remaining_count = len(remaining_items)
    remaining_limit = get_equipment_slot_limit(remaining_items)

    current_overflow = max(0, current_count - current_limit)
    remaining_overflow = max(0, remaining_count - remaining_limit)
    return remaining_overflow > current_overflow, remaining_count, remaining_limit


async def find_equipment_by_input(session, player_id: str, input_arg: str) -> ItemInstance:
    """
    根据用户输入查找装备，支持：
    1. 简短编号（1-装备总数）
    2. 原始ID（数字）
    3. 装备名称

    返回找到的装备实例，如果未找到则返回None
    """
    all_equips = await ItemRepository(session).get_equipment_for_numbering(
        player_id, EQUIP_ITEM_IDS
    )

    if input_arg.isdigit():
        input_id = int(input_arg)

        # 如果输入的是简短编号（1-装备总数）
        if 1 <= input_id <= len(all_equips):
            return all_equips[input_id - 1]  # 转换为0基索引
        else:
            # 尝试按原始ID查找
            equip = await session.get(ItemInstance, input_id)
            if equip and equip.player_id == player_id and equip.is_equipment:
                return equip
            return None
    else:
        # 按名称查找
        item_config = config.items_config["by_name"].get(input_arg)
        if not item_config or item_config.type.value != "EQUIPMENT":
            return None

        # 在玩家装备中查找该名称的装备
        for equip in all_equips:
            if equip.item_id == item_config.item_id:
                return equip
        return None


def get_equipment_short_id(all_equips: list, target_equip: ItemInstance) -> int:
    """获取装备的简短编号"""
    for i, equip in enumerate(all_equips, 1):
        if equip.id == target_equip.id:
            return i
    return 0

# ---------------- 指令：查看装备栏 ----------------
# 装备栏/装备详情/装备 实测高频，提至 p5 层，不随 item 模块默认 p9
list_equipment = on_command("装备栏", aliases={"我的装备"}, block=True, priority=5, force_whitespace=True)

@list_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数
    arg = args.extract_plain_text().strip()
    page = 1
    if arg:
        try:
            page = int(arg)
            if page < 1:
                page = 1
        except ValueError:
            await list_equipment.finish("⛔ 页码必须是正整数")

    async with safe_session() as session:
        player = await require_player(session, event, list_equipment)

        repository = ItemRepository(session)
        total = await repository.count_equipment_for_numbering(player.id, EQUIP_ITEM_IDS)
        page_size = config.game_config["game"]["inventory_page_size"]
        total_pages = max(1, (total - 1) // page_size + 1)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        current_page_equips = await repository.get_equipment_page_for_numbering(
            player.id, EQUIP_ITEM_IDS, offset=start_idx, limit=page_size,
        )
        equipped_items = await repository.get_equipped_for_slot_display(
            player.id, EQUIP_ITEM_IDS,
        )
        equipped_count = len(equipped_items)
        equipment_slot_limit = get_equipment_slot_limit(equipped_items)

        lines = [
            "# 🎽 装备栏",
            f"已装备 **{equipped_count}**/{equipment_slot_limit}",
            "***",
        ]

        # 为装备分配简短编号（全局编号）
        for i, eq in enumerate(current_page_equips, start=start_idx + 1):
            tpl = eq.config
            equip_state = "🟢已装备" if eq.equipped else "🔘未装备"
            rarity_badge = tpl.get_rarity_display()
            if tpl.rarity in {"purple", "orange", "red"}:
                rarity_badge = color_rarity(
                    {"purple": "史诗", "orange": "传说", "red": "永恒"}[tpl.rarity],
                    tpl.rarity,
                ) + " "

            # 构建装备信息
            info_parts = []

            # 基础信息 - 编号只追加纯数字（配合底部"装备"按钮组合），装备名可点击查看详情
            info_parts.append(f"🆔{cmd(str(i), str(i))}│{rarity_badge}{cmd(tpl.name, f'装备详情 {i}')}")
            requirement = f"Lv.{tpl.required_level}"
            if tpl.required_reincarnation:
                requirement += f"·{tpl.required_reincarnation}转"
            info_parts.append(requirement)

            # 升阶等级
            if eq.upgrade_level > 0:
                info_parts.append(f"⭐+{eq.upgrade_level}")

            # 耐久度
            info_parts.append(f"🛠️{eq.durability}/{tpl.durability}")

            # 宝石镶嵌信息
            if eq.available_gem_slots > 0:
                info_parts.append(f"💎{eq.used_gem_slots}/{eq.available_gem_slots}")

            # 词缀标记
            affix_list = get_affixes_from_equipment(eq.extra_attrs)
            if affix_list:
                info_parts.append(f"🔮{len(affix_list)}词缀")

            # 锁定标记
            if (eq.extra_attrs or {}).get("_player_locked"):
                info_parts.append("🔒")

            # 装备状态
            info_parts.append(equip_state)

            lines.append(" ".join(info_parts))

        lines.append("***")
        lines.append("💡 先点「🗡️装备」再连点编号，拼出「装备 1 2」批量穿戴　点名称查看详情")
        if total_pages > 1:
            lines.append(f"第**{page}**/{total_pages}页")
            nav = []
            if page > 1:
                nav.append(cmd("上一页", f"装备栏 {page - 1}"))
            if page < total_pages:
                nav.append(cmd("下一页", f"装备栏 {page + 1}"))
            if nav:
                lines.append(" | ".join(nav))
        lines.append(cmd("🗡️装备", "装备") + " | " + cmd("装备栏") + " | " + cmd("装备菜单") + " | " + cmd("铭文列表") + " | " + cmd("帮助"))

    if not total:
        await list_equipment.finish("🎒 你的装备栏空空如也")
    await list_equipment.finish(build_markdown("\n".join(lines)))


# ---------------- 指令：装备详情 ----------------
equipment_detail = on_command("装备详情", aliases={"装备信息", "查看装备"}, block=True, priority=5, force_whitespace=True)

@equipment_detail.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    from ..alchemy.service import AlchemyService

    arg = args.extract_plain_text().strip()
    if not arg:
        await equipment_detail.finish("⛔ 格式：装备详情 装备编号/名称")

    async with safe_session() as session:
        player = await require_player(session, event, equipment_detail)

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, arg)
        if not equip:
            await equipment_detail.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 获取装备配置
        tpl = equip.config
        if not tpl:
            await equipment_detail.finish("⛔ 装备配置错误")

        # 稀有度中文映射
        rarity_map = {
            "white": "普通",
            "green": "优秀",
            "blue": "稀有",
            "purple": "史诗",
            "orange": "传说",
            "red": "永恒"
        }
        rarity_display = tpl.get_rarity_display()
        rarity_cn = rarity_map.get(tpl.rarity, tpl.rarity)
        rarity_name = color_rarity(rarity_cn, tpl.rarity)
        # KaTeX 彩色文字无法被 ** 加粗（会原样露出 **），仅纯文本时加粗
        if rarity_name == rarity_cn:
            rarity_name = f"**{rarity_cn}**"
        is_locked = (equip.extra_attrs or {}).get("_player_locked", False)

        # 构建详细信息
        lock_badge = "　🔒已锁定" if is_locked else ""
        lines = [
            f"# ⚔️ {tpl.name}",
            f"ID:{equip.id}　{rarity_display}{rarity_name}　{'🟢已装备' if equip.equipped else '🔘未装备'}{lock_badge}",
            "***",
            f"📊 等级要求：Lv.{tpl.required_level}{f'·{tpl.required_reincarnation}转' if getattr(tpl, 'required_reincarnation', 0) else ''}　⭐ 升阶：+{equip.upgrade_level}",
            f"🛠️ 耐久：{equip.durability}/{tpl.durability}　💰 价值：{tpl.price:,}",
            ""
        ]

        # 获取升阶加成倍率（在所有属性显示前获取）
        upgrade_multiplier = equip.get_upgrade_bonus_multiplier()
        is_furnace = equip.item_id == AlchemyService.FURNACE_ITEM_ID
        furnace_success = furnace_durability = None
        if is_furnace:
            furnace_success, furnace_durability = AlchemyService.get_furnace_effects(equip.upgrade_level)

        # 基础属性
        if tpl.attr_bonus or tpl.attr_ratio:
            lines.append("📈 基础属性：")

            # 固定值属性
            if tpl.attr_bonus:
                for k, v in tpl.attr_bonus.items():
                    base_value = int(v)
                    current_value = int(v * upgrade_multiplier)
                    bonus = current_value - base_value

                    attr_name = ATTR_NAME_MAP.get(k, k)

                    if bonus > 0:
                        lines.append(f"  • {attr_name}：{base_value} → {current_value} (+{bonus})")
                    else:
                        lines.append(f"  • {attr_name}：{base_value}")

            # 百分比属性
            if tpl.attr_ratio:
                for k, r in tpl.attr_ratio.items():
                    base_ratio = float(r) * 100
                    current_ratio = float(r) * upgrade_multiplier * 100
                    bonus_ratio = current_ratio - base_ratio

                    attr_name = ATTR_NAME_MAP.get(k, k)

                    if bonus_ratio > 0:
                        lines.append(f"  • {attr_name}：{base_ratio:.1f}% → 现在{current_ratio:.1f}% (+{bonus_ratio:.1f}%)")
                    else:
                        lines.append(f"  • {attr_name}：{base_ratio:.1f}%")

            lines.append("")

        # 词缀展示
        affixes = get_affixes_from_equipment(equip.extra_attrs)
        if affixes:
            lines.append("🔮 词缀：")
            lines.extend(format_affixes_display(affixes))
            lines.append("")

        # 宝石/铭文镶嵌信息
        if equip.available_gem_slots > 0:
            lines.append("💎 镶嵌孔位：")
            lines.append(f"  • 孔位：{equip.used_gem_slots}/{equip.available_gem_slots}")

            if equip.used_gem_slots > 0:
                gem_info = GemSocketService.get_equipment_gem_info(equip)
                for slot_info in gem_info:
                    if not slot_info["is_empty"]:
                        slot_num = slot_info["slot_number"]
                        if slot_info.get("is_inscription"):
                            display = get_inscription_display(slot_info["inscription_data"])
                            lines.append(f"  • 孔位{slot_num}：📜 {display}")
                        else:
                            gem_name = slot_info["gem_name"]
                            gem_type = slot_info["gem_type"]
                            lines.append(f"  • 孔位{slot_num}：{gem_type} - {gem_name}")

            lines.append("")

        # 装备槽扩展信息
        slot_bonus = get_equipment_slot_bonus(equip)
        if slot_bonus > 0:
            lines.append("🎽 装备槽：")
            lines.append(f"  • 穿戴时装备槽 +{slot_bonus}（实际净增 {slot_bonus - 1} 格）")
            lines.append("")

        # 炼丹炉专属效果展示
        if is_furnace:
            lines.append("🔥 炼丹效果：")
            lines.append(f"  • 当前成功率倍率：×{furnace_success:.1f}")
            lines.append(f"  • 每炉耐久消耗：{furnace_durability}点")

            next_level = equip.upgrade_level + 1
            max_level = equip.config.max_upgrade_level if equip.config else 10
            if next_level <= max_level:
                next_success, next_durability = AlchemyService.get_furnace_effects(next_level)
                lines.append(
                    f"  • 下一阶(+{next_level})预览：成功率×{next_success:.1f}，耐久消耗 {next_durability}点"
                )
            lines.append("")

        # 升阶提升说明
        if equip.upgrade_level > 0:
            lines.append("⭐ 升阶加成：")
            lines.append(f"  • 当前等阶：+{equip.upgrade_level}阶")
            if is_furnace:
                lines.append(f"  • 成功率提升：+{(furnace_success - 1) * 100:.0f}%")
                lines.append(f"  • 当前耐久消耗：{furnace_durability}点/炉")
            else:
                lines.append(f"  • 属性倍率：{upgrade_multiplier:.1f}x")
                lines.append(f"  • 总提升：+{(upgrade_multiplier - 1) * 100:.0f}%")
            lines.append("")

        # 特殊效果（显示解锁状态）
        if hasattr(tpl, 'special_effects') and tpl.special_effects:
            lines.append("✨ 特殊效果：")

            is_vip_equipment = equip.item_id in VIP_EQUIPMENT_IDS

            if is_vip_equipment:
                # VIP装备：全部效果已解锁
                for idx, effect in enumerate(tpl.special_effects, start=1):
                    desc = effect.get('description', '')
                    if not desc:
                        continue
                    lines.append(f"  ✅ {desc}")
            else:
                # 普通装备：计算已解锁的效果数量（每2阶解锁1个效果）
                unlocked_count = equip.upgrade_level // 2

                for idx, effect in enumerate(tpl.special_effects, start=1):
                    desc = effect.get('description', '')
                    if not desc:
                        continue

                    # 计算解锁所需的升阶等级
                    required_level = idx * 2

                    if idx <= unlocked_count:
                        # 已解锁
                        lines.append(f"  ✅ [{idx}] {desc}")
                    else:
                        # 未解锁
                        lines.append(f"  🔒 [{idx}] {desc} (需要+{required_level}阶)")

            lines.append("")

        # 套装信息
        set_info = get_equipment_set_info(equip.item_id)
        if set_info:
            from ..config import config as _cfg
            lines.append("🧩 套装：")
            lines.append(f"  • {set_info['name']}套装")
            piece_names = []
            for pid in set_info["pieces"]:
                pcfg = _cfg.items_config["by_id"].get(pid)
                piece_names.append(pcfg.name if pcfg else pid)
            lines.append(f"  • 部件：{'、'.join(piece_names)}")
            for threshold, desc in set_info["bonuses"].items():
                lines.append(f"  • {threshold}件：{desc}")
            lines.append("")

        # 描述
        lines.append("📝 描述：")
        lines.append(f"  {tpl.description}")

        lines.append("***")
        all_equips = await ItemRepository(session).get_equipment_for_numbering(player.id, EQUIP_ITEM_IDS)
        short_id = get_equipment_short_id(all_equips, equip)
        equipped_for_slots = [item for item in all_equips if item.equipped]
        slot_full = len(equipped_for_slots) >= get_equipment_slot_limit(equipped_for_slots, equip)
        eid = str(equip.id)
        if not equip.equipped:
            preview_arg = f"换装预览 {short_id}" + (" " if slot_full else "")
            lines.append(cmd("预览", preview_arg) + " | " + cmd("穿戴", f"装备 {eid}") + " | " + cmd("装备栏") + " | " + cmd("套装信息") + " | " + cmd("帮助"))
        else:
            lines.append(cmd("卸下 " + tpl.name, f"卸下 {eid}") + " | " + cmd("装备栏") + " | " + cmd("套装信息") + " | " + cmd("帮助"))
        await equipment_detail.finish(build_markdown("\n".join(lines)))


# ---------------- 指令：换装预览 ----------------
preview_equipment = on_command("换装预览", block=True, priority=5, force_whitespace=True)


def validate_equipment_swap(player: Player, equipped: list[ItemInstance],
                            target: ItemInstance, removed: ItemInstance | None) -> str | None:
    """沿用穿戴/卸下约束，按真实命令先卸后穿的顺序检查。"""
    if target.player_id != player.id or (removed and removed.player_id != player.id):
        return "装备不属于你"
    if target.equipped:
        return "目标装备已经穿戴"
    if target.config.required_level > player.level:
        return f"等级不足，需要 Lv.{target.config.required_level}"
    if (target.config.required_reincarnation or 0) > (player.reincarnation_level or 0):
        return f"转数不足，需要 {target.config.required_reincarnation}转"
    if target.durability <= 0:
        return "目标装备已损坏，请先修理"
    if removed:
        if removed.id == target.id or not removed.equipped or removed.id not in {eq.id for eq in equipped}:
            return "卸下编号必须是已穿戴的另一件装备"
        overflow, count, limit = would_unwear_worsen_slot_overflow(equipped, removed)
        if overflow:
            return f"先卸下 {removed.config.name} 会使装备槽不足（剩余 {count}/{limit}），请先卸下其他装备"
    remaining = [eq for eq in equipped if removed is None or eq.id != removed.id]
    if any(eq.item_id == target.item_id for eq in remaining):
        return f"已穿戴同名装备 {target.config.name}"
    limit = get_equipment_slot_limit(remaining, target)
    if len(remaining) >= limit:
        if removed is None:
            return f"装备栏已满（{len(remaining)}/{limit}），请补充卸下编号：换装预览 <穿上编号> <卸下编号>"
        return f"装备栏已满（{len(remaining)}/{limit}）"
    return None


def _format_swap_preview(player, current: dict, projected: dict,
                         before_items: list[ItemInstance], after_items: list[ItemInstance],
                         target: ItemInstance, removed: ItemInstance | None) -> str:
    fmt = format_attribute_value
    lines = [f"# 换装预览：{target.config.name}" + (f" / 卸下 {removed.config.name}" if removed else ""),
             "【六维属性（当前 → 换装后 / 变化）】"]
    for key in MAIN_ATTRS:
        delta = projected[key] - current[key]
        lines.append(f"{MAIN_ATTRIBUTE_NAMES[key]}：{fmt(current[key])} → {fmt(projected[key])} ({delta:+g})")
    before = summarize_battle_attributes(current, before_items, player.level)
    after = summarize_battle_attributes(projected, after_items, player.level)
    changed = []
    for key, name in BATTLE_ATTRIBUTE_NAMES.items():
        a, b = before[key], after[key]
        if a["raw"] == b["raw"] and a["effective"] == b["effective"]:
            continue
        suffix = "点" if key == "critical_power" else "%"
        changed.append(f"{name}：生效 {fmt(a['effective'])} → {fmt(b['effective'])}{suffix}；"
                       f"原始 {fmt(a['raw'])} → {fmt(b['raw'])}{suffix}"
                       + (f"（溢出 {fmt(a['overflow'])} → {fmt(b['overflow'])}{suffix}）"
                          if a['overflow'] or b['overflow'] else ""))
    lines.extend(["【战斗属性（发生变化）】", *(changed or ["无变化"])])
    active_before = get_active_set_bonuses([eq.item_id for eq in before_items])
    active_after = get_active_set_bonuses([eq.item_id for eq in after_items])
    def set_lines(active):
        return {f"{info['name']} {bonus['threshold']}件：{bonus['description']}"
                for info in active.values() for bonus in info['active_bonuses']}
    gained = set_lines(active_after) - set_lines(active_before)
    lost = set_lines(active_before) - set_lines(active_after)
    lines.append("【套装激活变化】")
    lines.extend([*(f"新增：{entry}" for entry in sorted(gained)),
                  *(f"失去：{entry}" for entry in sorted(lost))] or ["无变化"])
    from ..alchemy.service import AlchemyService
    if removed and removed.item_id == AlchemyService.FURNACE_ITEM_ID:
        lines.append("提示：实际卸下炼丹炉会影响进行中的炼丹任务；本次预览不会中断炼丹。")
    lines.append("铭文、体质及战斗内触发效果未折算为战力；结果按当前宠物和临时增益计算。")
    return "\n".join(lines)


@preview_equipment.handle()
async def handle_equipment_preview(event: MessageEvent, args: Message = CommandArg()):
    parts = args.extract_plain_text().strip().split()
    if not 1 <= len(parts) <= 2 or any(not part.isascii() or not part.isdecimal() or int(part) < 1 for part in parts):
        await preview_equipment.finish("格式：换装预览 <穿上编号> [卸下编号]；仅接受装备栏中的短编号")
    async with safe_session() as session:
        player = await require_player(session, event, preview_equipment)
        all_equips = await ItemRepository(session).get_equipment_for_numbering(player.id, EQUIP_ITEM_IDS)
        indices = [int(part) for part in parts]
        if any(index > len(all_equips) for index in indices):
            result = "编号不存在；请查看装备栏中的短编号（不接受装备ID或名称）"
        else:
            target = all_equips[indices[0] - 1]
            removed = all_equips[indices[1] - 1] if len(indices) == 2 else None
            equipped = [eq for eq in all_equips if eq.equipped]
            error = validate_equipment_swap(player, equipped, target, removed)
            if error:
                result = f"⛔ {error}"
            else:
                current = await player.get_effective_attributes(session)
                projected_stored, after_items = project_equipment(player, equipped, target, removed)
                projected = dict(current)
                for key in Player.INIT_ATTRS:
                    projected[key] += projected_stored[key] - getattr(player, key)
                result = _format_swap_preview(player, current, projected, equipped, after_items, target, removed)
    await preview_equipment.finish(build_markdown(result))


# ---------------- 指令：穿戴装备 ----------------
wear_equipment = on_command("装备", aliases={"穿戴", "佩戴"}, block=True, priority=5, force_whitespace=True)

@wear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await wear_equipment.finish("⛔ 格式：装备 装备编号/名称 [编号2 编号3 ...]")

    arg_list = arg.split()

    async with safe_session() as session:
        player = await require_player(session, event, wear_equipment)

        if len(arg_list) == 1:
            # ---- 单件装备：原有逻辑 ----
            equip = await find_equipment_by_input(session, player.id, arg)
            if not equip:
                await wear_equipment.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

            # 如果是按名称查找且有多个同名装备，优先选择耐久度最高的未装备装备
            if not arg.isdigit():
                item_config = config.items_config["by_name"].get(arg)
                if item_config:
                    stmt = select(ItemInstance).where(
                        ItemInstance.player_id == player.id,
                        ItemInstance.item_id == item_config.item_id,
                        ItemInstance.equipped == False
                    ).order_by(ItemInstance.durability.desc())

                    unequipped_items = (await session.execute(stmt)).scalars().all()
                    if unequipped_items:
                        equip = unequipped_items[0]  # 选择耐久度最高的那件

            if equip.equipped:
                await wear_equipment.finish("⛔ 该装备已经穿戴")
            if equip.config.required_level > player.level:
                await wear_equipment.finish(f"⛔ 等级不足，需要 Lv.{equip.config.required_level}")
            if (equip.config.required_reincarnation or 0) > (player.reincarnation_level or 0):
                await wear_equipment.finish(f"⛔ 转数不足，需要 {equip.config.required_reincarnation}转（冥返）后才能穿戴")
            if equip.durability <= 0:
                await wear_equipment.finish("⛔ 该装备已损坏（耐久为0），请先修理后再穿戴")

            same_type_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == equip.item_id,
                ItemInstance.equipped == True
            )
            same_type_equipped = (await session.execute(same_type_stmt)).scalars().all()
            if same_type_equipped:
                await wear_equipment.finish(f"⛔ 已装备同名装备 {equip.config.name}，不能重复穿戴")

            all_equipped_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
            )
            all_equipped = (await session.execute(all_equipped_stmt)).scalars().all()
            slot_limit = get_equipment_slot_limit(list(all_equipped), equip)
            if len(all_equipped) >= slot_limit:
                await wear_equipment.finish(f"⛔ 装备栏已满，当前最多只能穿戴{slot_limit}件装备，请先卸下其他装备")

            equip.equipped = True
            session.add(equip)

            equipment_service = EquipmentService(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )
            await equipment_service.recalc_equipment_attributes(player)
            session.add(player)
            await session.commit()

            durability_info = f" (ID:{equip.id}, 耐久:{equip.durability}/{equip.config.durability})"
            if equip.durability == 0:
                await wear_equipment.finish(f"⛔ {equip.config.name} 耐久为0，已自动卸下，请先修理")

            # 检查新手任务
            from ..quest.novice_quest_service import NoviceQuestService
            quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
                session, player, "command", {"command": "装备"}
            )

            result_msg = f"✅ 成功穿戴 {equip.config.name}{durability_info}"
            if quest_completed and quest_msg:
                result_msg += f"\n\n{quest_msg}"

            await wear_equipment.finish(build_markdown(result_msg))

        else:
            # ---- 批量装备：依次装备，每件完成后立即重算属性并提交 ----
            # 初始化装备服务（整个批次共用）
            equipment_service = EquipmentService(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )

            # 查询当前已装备状态，用于本地维护
            all_equipped_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
            )
            currently_equipped = list((await session.execute(all_equipped_stmt)).scalars().all())
            equipped_count = len(currently_equipped)
            equipped_item_ids = set(e.item_id for e in currently_equipped)
            equipped_instance_ids = set(e.id for e in currently_equipped)

            success_list = []
            fail_list = []

            for single_arg in arg_list:
                equip = await find_equipment_by_input(session, player.id, single_arg)
                if not equip:
                    fail_list.append(f"{single_arg}: 未找到")
                    continue

                # 名称查找时，优先选择耐久最高的未装备装备（排除本次已装备的）
                if not single_arg.isdigit():
                    item_config = config.items_config["by_name"].get(single_arg)
                    if item_config:
                        stmt = select(ItemInstance).where(
                            ItemInstance.player_id == player.id,
                            ItemInstance.item_id == item_config.item_id,
                            ItemInstance.equipped == False
                        ).order_by(ItemInstance.durability.desc())
                        unequipped_items = [
                            i for i in (await session.execute(stmt)).scalars().all()
                            if i.id not in equipped_instance_ids
                        ]
                        if unequipped_items:
                            equip = unequipped_items[0]

                if equip.equipped or equip.id in equipped_instance_ids:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 已穿戴")
                    continue
                if equip.config.required_level > player.level:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 等级不足(需Lv.{equip.config.required_level})")
                    continue
                if (equip.config.required_reincarnation or 0) > (player.reincarnation_level or 0):
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 转数不足(需{equip.config.required_reincarnation}转)")
                    continue
                if equip.durability <= 0:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 已损坏需修理")
                    continue
                if equip.item_id in equipped_item_ids:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 已装备同名装备")
                    continue

                slot_limit = get_equipment_slot_limit(currently_equipped, equip)
                if equipped_count >= slot_limit:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 装备栏已满({equipped_count}/{slot_limit})")
                    continue

                equip.equipped = True
                session.add(equip)

                # 更新本地状态，供后续装备的检查使用
                equipped_count += 1
                currently_equipped.append(equip)
                equipped_item_ids.add(equip.item_id)
                equipped_instance_ids.add(equip.id)
                success_list.append(f"{equip.config.name}(ID:{equip.id})")

            # 批量穿戴完成后统一重算属性并提交
            if success_list:
                await equipment_service.recalc_equipment_attributes(player)
                session.add(player)
                await session.commit()

            lines = []
            if success_list:
                lines.append(f"✅ 成功穿戴：{', '.join(success_list)}")
            if fail_list:
                lines.append("❌ 以下装备失败：")
                lines.extend([f"  • {f}" for f in fail_list])
            if not success_list and not fail_list:
                lines.append("⛔ 未处理任何装备")

            await wear_equipment.finish(message_add_head("\n".join(lines), event))


async def _handle_furnace_unequip(session, player: Player, equip: ItemInstance) -> list[str]:
    """卸下炼丹炉时处理进行中的炼丹任务，返回失败信息列表。"""
    from ..alchemy.service import AlchemyService
    from ..models.alchemy_task import AlchemyRecord

    if equip.item_id != AlchemyService.FURNACE_ITEM_ID:
        return []

    stmt = select(AlchemyRecord).where(
        and_(
            AlchemyRecord.player_id == player.id,
            AlchemyRecord.furnace_id == equip.id,
            AlchemyRecord.claimed == False
        )
    )
    alchemy_records = (await session.execute(stmt)).scalars().all()

    failed_tasks = []
    for record in alchemy_records:
        if not record.is_finished():
            failed_tasks.append(f"{equip.config.name}(ID:{equip.id}) 炼丹任务失败，返还材料")
            for material_id, quantity in record.materials.items():
                try:
                    await ItemInstance.add_item(session, player.id, material_id, quantity)
                except ValueError:
                    material_config = config.items_config["by_id"].get(material_id)
                    if material_config:
                        gold_value = material_config.price * quantity
                        player.gold += gold_value
                        failed_tasks.append(f"背包已满，{material_config.name}×{quantity} 转为 {gold_value} 金币")
        await session.delete(record)

    return failed_tasks


# ---------------- 指令：卸下装备 ----------------
unwear_equipment = on_command("卸下", block=True, priority=9)

@unwear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await unwear_equipment.finish("⛔ 格式：卸下 装备编号/名称")

    async with safe_session() as session:
        player = await require_player(session, event, unwear_equipment)

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, arg)
        if not equip:
            await unwear_equipment.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 如果是按名称查找且有多个同名装备，优先选择已装备且升阶等级最高的
        if not arg.isdigit():
            item_config = config.items_config["by_name"].get(arg)
            if item_config:
                stmt = select(ItemInstance).where(
                    ItemInstance.player_id == player.id,
                    ItemInstance.item_id == item_config.item_id,
                    ItemInstance.equipped == True
                ).order_by(ItemInstance.upgrade_level.desc())

                equipped_items = (await session.execute(stmt)).scalars().all()
                if equipped_items:
                    equip = equipped_items[0]  # 选择升阶等级最高的那件

        # 检查是否已装备
        if not equip.equipped:
            await unwear_equipment.finish("⛔ 该装备未穿戴")

        all_equipped_stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        all_equipped = list((await session.execute(all_equipped_stmt)).scalars().all())
        would_overflow, remaining_count, remaining_limit = would_unwear_worsen_slot_overflow(
            all_equipped,
            equip,
        )
        if would_overflow:
            await unwear_equipment.finish(
                f"⛔ 卸下 {equip.config.name} 后装备槽会不足"
                f"（剩余 {remaining_count}/{remaining_limit}）\n"
                "💡 请先卸下其他不提供装备槽的装备，再卸下它"
            )

        failed_tasks = await _handle_furnace_unequip(session, player, equip)

        # 卸下装备
        equip.equipped = False

        # 移除装备的属性加成
        delta = (equip.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            current_value = getattr(player, k, 0)
            setattr(player, k, max(0, current_value - v))

        # 清除装备的持久化加成记录
        if "_persist_bonus" in (equip.extra_attrs or {}):
            extra_new = {k: v for k, v in equip.extra_attrs.items() if k != "_persist_bonus"}
            equip.extra_attrs = extra_new

        session.add(equip)

        # 重新计算剩余装备的属性加成，确保 mp_from_hp 等全局被动同步
        # 新版本: 使用DI架构的EquipmentService
        equipment_service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        await equipment_service.recalc_equipment_attributes(player)
        await session.commit()

        # 构建结果消息
        result_msg = f"✅ 成功卸下 {equip.config.name} (ID:{equip.id})"
        if failed_tasks:
            result_msg += "\n" + "\n".join([f"🔄 {task}" for task in failed_tasks])

        await unwear_equipment.finish(message_add_head(result_msg, event))


# ---------------- 指令：一键卸下 ----------------
unwear_all_equipment = on_command("一键卸下", aliases={"卸下全部", "全部卸下"}, block=True, priority=9)

@unwear_all_equipment.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, unwear_all_equipment)

        # 查找所有已装备的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

        if not equipped_items:
            await unwear_all_equipment.finish("⛔ 你没有穿戴任何装备")

        all_failed_tasks = []
        unworn_equipment = []

        for equip in equipped_items:
            all_failed_tasks.extend(await _handle_furnace_unequip(session, player, equip))

            # 卸下装备
            equip.equipped = False

            # 移除装备的属性加成
            delta = (equip.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - v))

            # 清除装备的持久化加成记录
            if "_persist_bonus" in (equip.extra_attrs or {}):
                extra_new = {k: v for k, v in equip.extra_attrs.items() if k != "_persist_bonus"}
                equip.extra_attrs = extra_new

            session.add(equip)
            unworn_equipment.append(f"{equip.config.name}(ID:{equip.id})")

        # 重新计算剩余装备的属性加成，确保属性正确恢复
        # 新版本: 使用DI架构的EquipmentService
        equipment_service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        await equipment_service.recalc_equipment_attributes(player)
        # 确保当前HP/MP不超过新的上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        session.add(player)
        await session.commit()

        # 构建结果消息
        result_msg = f"✅ 成功卸下 {len(unworn_equipment)} 件装备：\n" + "、".join(unworn_equipment)

        if all_failed_tasks:
            for task_info in all_failed_tasks:
                result_msg += f"\n🔄 {task_info}"

        await unwear_all_equipment.finish(result_msg)


# ==================== 套装信息 ====================
set_info_cmd = on_command("套装信息", aliases={"套装", "套装列表"}, block=True, priority=9)


@set_info_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, set_info_cmd)

        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        equipped = (await session.execute(stmt)).scalars().all()
        equipped_ids = [eq.item_id for eq in equipped]

        from .set_bonus_service import get_active_set_bonuses, _load_config
        all_sets = _load_config().get("sets", {})
        active = get_active_set_bonuses(equipped_ids)

        from ..config import config as _cfg
        lines = ["# 🧩 套装系统", "***"]

        for set_id, set_def in all_sets.items():
            name = set_def["name"]
            pieces = set_def["pieces"]
            count = sum(1 for p in pieces if p in set(equipped_ids))
            is_active = set_id in active

            lines.append(f"**{name}套装** （{count}/{len(pieces)}件已装备）")

            piece_names = []
            for pid in pieces:
                pcfg = _cfg.items_config["by_id"].get(pid)
                pname = pcfg.name if pcfg else pid
                marker = "✅" if pid in set(equipped_ids) else "⬜"
                piece_names.append(f"{marker}{pname}")
            lines.append(f"  部件：{'、'.join(piece_names)}")

            for threshold, bonus in sorted(set_def.get("bonuses", {}).items()):
                desc = bonus.get("description", "")
                activated = count >= int(threshold)
                status = "🟢" if activated else "🔘"
                lines.append(f"  {status} {threshold}件：{desc}")

            lines.append("")

        if not all_sets:
            lines.append("暂无套装数据")

        lines.append("***")
        lines.append(cmd("装备栏") + " | " + cmd("帮助"))
        await set_info_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 装备菜单（VIP定制装备专属技能） ====================

# VIP装备技能帮助信息注册表
# 格式: item_id -> { "name": 装备名, "icon": 图标, "skills": 技能说明文本 }
_VIP_EQUIPMENT_SKILL_MENUS: dict[str, dict] = {
    "vip_blade_zhanlongshan": {
        "name": "斩龙闪",
        "icon": "⚔️",
        "skills": (
            "⚔️ 斩龙闪 · 灭法之影\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "6项被动效果战斗中自动生效"
        ),
    },
    "vip_robe_jingyuanzhiyi": {
        "name": "镜怨披风",
        "icon": "🪞",
        "skills": (
            "🪞 镜怨披风 · 镜中怨灵\n"
            "━━━━━━━━━━━━━\n"
            "👻 主动技能 — 怨灵拾荒（每日1次）：\n"
            "【怨灵拾荒】 派出怨灵拾荒/领取战利品\n"
            "【镜怨披风】 查看镜怨披风状态面板\n"
            "━━━━━━━━━━━━━\n"
            "3项被动效果战斗中自动生效"
        ),
    },
    "vip_gui_yu": {
        "name": "归雨",
        "icon": "☂️",
        "skills": (
            "☂️ 归雨 · 鬼域雨钉\n"
            "━━━━━━━━━━━━━\n"
            "🌧️ 主动技能 — 鬼域雨钉（锚点传送）：\n"
            "【锚点】 查看已设置的雨钉锚点\n"
            "【锚点 设置 <名称>】 钉下雨钉（最多3个）\n"
            "【锚点 传送 <编号>】 传送（CD5分钟，耗5%理智）\n"
            "【锚点 携带 <UID> <编号>】 携带他人传送（耗10%理智）\n"
            "【锚点 删除 <编号>】 拔除雨钉\n"
            "【同意传送】/【拒绝传送】 回应携带邀请\n"
            "【归雨】查看归雨状态面板"
        ),
    },
    "heaven_retreat_star_blade": {
        "name": "天退星刀",
        "icon": "🔫",
        "skills": (
            "🔫 天退星刀 · 插翅虎\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "3项被动效果战斗中自动生效"
        ),
    },
    "vip_chrono_watch": {
        "name": "折光年",
        "icon": "⏱️",
        "skills": (
            "⏱️ 折光年 · 拨针系统\n"
            "━━━━━━━━━━━━━\n"
            "⏳ 主动技能 — 拨针系统（日常效率）：\n"
            "【拨针 签到】重置签到（每日1次，耐久-3）\n"
            "【拨针 闭关】立即按满时长出关（每日1次，耐久-5）\n"
            "【拨针 讨伐】BOSS攻击次数+1（每日1次，耐久-5）\n"
            "【拨针 委托】额外刷新委托（每日1次，耐久-3）\n"
            "【折光年】查看怀表状态面板"
        ),
    },
    "vip_longying_flash": {
        "name": "龙影闪",
        "icon": "🌀",
        "skills": (
            "🌀 龙影闪 · 灭法之影\n"
            "━━━━━━━━━━━━━\n"
            "🌀 主动技能 — 虚界锚钉（锚点传送）：\n"
            "【锚钉】 查看已设置的锚钉列表\n"
            "【锚钉 设置 <名称>】 撕开虚界裂隙设锚钉（最多3个）\n"
            "【锚钉 传送 <编号>】 穿越虚界传送（CD5分钟，耗5%理智）\n"
            "【锚钉 携带 <UID> <编号>】 拉对方一同穿越\n"
            "【锚钉 删除 <编号>】 缝合裂隙拔除锚钉\n"
            "【同意穿越】/【拒绝穿越】 回应携带邀请\n"
            "【龙影闪】查看装备状态面板"
        ),
    },
    "vip_ghost_dice": {
        "name": "诡面骰",
        "icon": "🎲",
        "skills": (
            "🎲 诡面骰 · 八面诡纹\n"
            "━━━━━━━━━━━━━\n"
            "🎰 主动技能 — 骰相·乱（八面骰）：\n"
            "【掷骰】摇动命运，随机+100%一项特殊属性（每日1次，耐久-5）\n"
            "【诡面骰】查看诡面骰状态面板\n"
            "━━━━━━━━━━━━━\n"
            "5项被动效果战斗中自动生效"
        ),
    },
    "vip_shoes_longren": {
        "name": "龙刃鞋",
        "icon": "👟",
        "skills": (
            "👟 龙刃鞋 · 踏风流\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "3项被动效果战斗中自动生效"
        ),
    },
    "vip_pendant_fuze": {
        "name": "福泽守心佩",
        "icon": "🪬",
        "skills": (
            "🪬 福泽守心佩 · 守心流\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "3项被动效果战斗中自动生效"
        ),
    },
    "vip_jade_xuanxu_shuangyan": {
        "name": "玄墟双衍玉",
        "icon": "💠",
        "skills": (
            "💠 玄墟双衍玉\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "穿戴时装备槽 +2，实际净增1个可用装备槽"
        ),
    },
}


equip_menu_cmd = on_command("装备菜单", aliases={"装备技能", "VIP技能"}, block=True, priority=9)


@equip_menu_cmd.handle()
async def handle_equip_menu(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, equip_menu_cmd)

        # 查询玩家已装备的所有装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(list(_VIP_EQUIPMENT_SKILL_MENUS.keys()))
        )
        equipped_vip = (await session.execute(stmt)).scalars().all()

        if not equipped_vip:
            await equip_menu_cmd.finish(
                "⛔ 你当前没有装备任何VIP定制装备\n"
                "💡 VIP定制装备需穿戴后才能查看专属技能菜单"
            )

        # 按装备构建帮助信息
        lines = ["# ✨ VIP装备技能菜单", "***"]

        for eq in equipped_vip:
            menu = _VIP_EQUIPMENT_SKILL_MENUS.get(eq.item_id)
            if menu:
                lines.append("")
                lines.append(menu["skills"])

        lines.append("***")
        lines.append(f"当前装备了 **{len(equipped_vip)}** 件VIP定制装备")
        lines.append(cmd("装备栏") + " | " + cmd("装备菜单") + " | " + cmd("帮助"))
        await equip_menu_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 铭文列表命令 ====================

inscription_list_cmd = on_command("铭文列表", aliases={"铭文栏", "我的铭文"}, priority=9, block=True)

_INSCRIPTION_PAGE_SIZE = 30

@inscription_list_cmd.handle()
async def handle_inscription_list(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    page = 1
    if arg_text.isdigit() and int(arg_text) >= 1:
        page = int(arg_text)

    msg = ""
    async with safe_session() as session:
        player = await require_player(session, event, inscription_list_cmd)

        from sqlalchemy import or_
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            or_(
                ItemInstance.item_id.like("inscription_%"),
                ItemInstance.item_id.like("adv_inscription_%"),
            )
        )
        inscriptions = (await session.execute(stmt)).scalars().all()

        synth_cmd = cmd("合成铭文")
        equip_bar_cmd = cmd("装备栏")
        help_cmd = cmd("帮助")
        if not inscriptions:
            msg = f"# 📜 铭文列表\n***\n你还没有铭文物品\n击杀精英怪可掉落铭文，或用铭文碎片合成\n***\n{synth_cmd} | {equip_bar_cmd} | {help_cmd}"
        else:
            rarity_map = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}
            rarity_order = {"orange": 0, "purple": 1, "blue": 2, "green": 3, "white": 4}

            fragment_count = 0
            normal_inscriptions = []
            for insc in inscriptions:
                if insc.item_id == "inscription_fragment":
                    fragment_count += insc.quantity
                else:
                    normal_inscriptions.append(insc)

            normal_inscriptions.sort(
                key=lambda x: rarity_order.get(
                    x.config.rarity if x.config else "white", 99
                )
            )

            total = len(normal_inscriptions)
            total_pages = max(1, (total + _INSCRIPTION_PAGE_SIZE - 1) // _INSCRIPTION_PAGE_SIZE)
            if page > total_pages:
                page = total_pages

            start = (page - 1) * _INSCRIPTION_PAGE_SIZE
            end = start + _INSCRIPTION_PAGE_SIZE
            page_items = normal_inscriptions[start:end]

            lines = [f"# 📜 铭文列表（{page}/{total_pages}页 共{total}个）", "***", "```bash"]

            for i, insc in enumerate(page_items, start=start + 1):
                display = get_inscription_display_from_item(insc)
                rarity = insc.config.rarity if insc.config else "unknown"
                icon = rarity_map.get(rarity, "⚪")
                lines.append(f"[{i}] {icon} {display}")

            if fragment_count > 0 and page == total_pages:
                lines.append(f"    🔵 铭文碎片 ×{fragment_count}（收集5个可【合成铭文】）")

            lines.append("```")
            lines.append("***")

            nav_parts = []
            if page > 1:
                nav_parts.append(cmd(f"上一页", f"铭文列表 {page - 1}"))
            if page < total_pages:
                nav_parts.append(cmd(f"下一页", f"铭文列表 {page + 1}"))
            nav_parts.extend([synth_cmd, equip_bar_cmd, help_cmd])
            lines.append(" | ".join(nav_parts))
            msg = "\n".join(lines)

    await inscription_list_cmd.finish(build_markdown(msg))
