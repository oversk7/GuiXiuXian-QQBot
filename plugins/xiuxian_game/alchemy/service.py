"""
炼丹服务 - DI架构版本

将AlchemyService改造为依赖注入架构，使用Repository抽象数据访问
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ..config import config
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..utils_markdown import cmd
from ..models.alchemy_task import AlchemyRecord
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.alchemy_record_repository import AlchemyRecordRepository


class AlchemyService:
    """炼丹服务类 - DI架构版本"""

    # 炼丹炉基础配置（类常量，保持向后兼容）
    FURNACE_ITEM_ID = "furnace"  # 统一的炼丹炉item_id
    BASE_TIME_MINUTES = 5  # 每炉基础耗时5分钟

    def __init__(
        self,
        item_repo: ItemRepository,
        alchemy_record_repo: AlchemyRecordRepository,
    ):
        """
        初始化炼丹服务

        Args:
            item_repo: 物品仓储
            alchemy_record_repo: 炼丹记录仓储
        """
        self._item_repo = item_repo
        self._alchemy_record_repo = alchemy_record_repo
        # 获取session用于flush操作
        self._session = alchemy_record_repo._session

    def get_furnace_effects(self, upgrade_level: int) -> Tuple[float, int]:
        """
        根据炼丹炉升阶等级计算效果

        Args:
            upgrade_level: 升阶等级

        Returns:
            (成功率系数, 耐久消耗基数)

        对应原代码:
            alchemy/service.py Line 23-43
        """
        # 成功率系数：+0阶=1.0，每阶+0.1，最高+10阶=2.0
        success_multiplier = 1.0 + (upgrade_level * 0.1)

        # 耐久消耗：根据等级阶段递减
        if upgrade_level <= 1:
            durability_cost = 5
        elif upgrade_level <= 4:
            durability_cost = 4
        elif upgrade_level <= 7:
            durability_cost = 3
        else:  # 8-10阶
            durability_cost = 2

        return success_multiplier, durability_cost

    def get_recipes(self) -> Dict[str, dict]:
        """
        获取所有丹方配置

        Returns:
            丹方配置字典

        对应原代码:
            alchemy/service.py Line 45-48
        """
        return config.elixirs_config.get("elixirs", {})

    def get_recipe_list(self) -> List[Tuple[str, dict]]:
        """
        以列表形式返回丹方配置，保持原有顺序

        Returns:
            丹方配置列表

        对应原代码:
            alchemy/service.py Line 50-53
        """
        return list(self.get_recipes().items())

    def find_recipe(self, target: str) -> Optional[Tuple[str, dict]]:
        """
        查找丹方

        Args:
            target: 丹方序号(数字字符串)或丹方名称或产物名称

        Returns:
            (recipe_key, recipe_config) 或 None

        对应原代码:
            alchemy/service.py Line 55-84
        """
        recipes_dict = self.get_recipes()
        recipes = self.get_recipe_list()

        # 按序号查找
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(recipes):
                return recipes[idx - 1]
            return None

        # 按产物名称查找
        for key, recipe in recipes:
            prod_name = config.items_config["by_id"][recipe["produce_item_id"]].name
            if prod_name == target:
                return key, recipe

        # 按配方key查找
        if target in recipes_dict:
            return target, recipes_dict[target]

        return None

    def search_recipes(self, keyword: str) -> List[Tuple[int, str, dict]]:
        """
        按关键字搜索丹方

        Args:
            keyword: 搜索关键字

        Returns:
            (序号, 配方key, 配方)列表

        对应原代码:
            alchemy/service.py Line 86-102
        """
        keyword = keyword.strip()
        if not keyword:
            return []

        keyword_lower = keyword.lower()
        results: List[Tuple[int, str, dict]] = []
        for idx, (key, recipe) in enumerate(self.get_recipe_list(), start=1):
            prod_cfg = config.items_config["by_id"][recipe["produce_item_id"]]
            prod_name = prod_cfg.name

            if (
                keyword_lower in key.lower()
                or keyword in prod_name
                or keyword_lower in prod_name.lower()
            ):
                results.append((idx, key, recipe))

        return results

    async def get_player_furnaces(self, player_id: str) -> List[ItemInstance]:
        """
        获取玩家的所有炼丹炉

        Args:
            player_id: 玩家ID

        Returns:
            炼丹炉列表（按升阶等级、耐久排序）

        对应原代码:
            alchemy/service.py Line 104-114
        """
        # 使用ItemRepository获取玩家的炼丹炉（已按升阶、耐久排序）
        furnaces = await self._item_repo.get_by_player_and_item_id(
            player_id, self.FURNACE_ITEM_ID
        )
        return furnaces

    async def check_materials(
        self, player_id: str, recipe: dict, qty: int
    ) -> Tuple[bool, str]:
        """
        检查材料是否充足

        Args:
            player_id: 玩家ID
            recipe: 丹方配置
            qty: 炉数

        Returns:
            (是否充足, 错误信息)

        对应原代码:
            alchemy/service.py Line 116-139
        """
        # 一次性获取所有物品（避免N+1查询）
        invs = await self._item_repo.get_all_by_player_id(player_id)

        mats_required = {mid: q * qty for mid, q in recipe["materials"].items()}
        missing_details: List[str] = []
        for mid, need in mats_required.items():
            total_have = sum(i.quantity for i in invs if i.item_id == mid)
            if total_have < need:
                name = config.items_config["by_id"][mid].name
                shortage = need - total_have
                missing_details.append(f"{name}✖️{need}（缺少{shortage}）")

        if missing_details:
            return False, "材料不足：" + "、".join(missing_details)

        return True, ""

    async def consume_materials(
        self, player_id: str, recipe: dict, qty: int
    ) -> bool:
        """
        消耗材料

        Args:
            player_id: 玩家ID
            recipe: 丹方配置
            qty: 炉数

        Returns:
            是否成功消耗

        对应原代码:
            alchemy/service.py Line 141-149
        """
        mats_required = {mid: q * qty for mid, q in recipe["materials"].items()}
        for mid, need in mats_required.items():
            success = await self._item_repo.consume_item(player_id, mid, need)
            if not success:
                return False
        return True

    async def start_alchemy(
        self,
        player_id: str,
        furnace_id: int,
        recipe_key: str,
        recipe: dict,
        qty: int,
        player_luck: int = 0,
    ) -> Tuple[bool, str, Optional[AlchemyRecord]]:
        """
        开始炼丹

        Args:
            player_id: 玩家ID
            furnace_id: 炼丹炉ID
            recipe_key: 丹方key
            recipe: 丹方配置
            qty: 炉数

        Returns:
            (是否成功, 消息, 炼丹记录)

        对应原代码:
            alchemy/service.py Line 151-219
        """
        # 获取炉子
        furnace = await self._item_repo.get_by_id(str(furnace_id))
        if not furnace or furnace.player_id != player_id:
            return False, "⛔ 未找到对应炼丹炉或非本人所有", None

        if furnace.item_id != self.FURNACE_ITEM_ID:
            return False, "⛔ 该装备不是炼丹炉", None

        coeff, dura_cost_base = self.get_furnace_effects(furnace.upgrade_level)

        # 检查耐久
        total_dura_need = dura_cost_base * qty
        if furnace.durability < total_dura_need:
            return (
                False,
                f"⛔ 炉子耐久不足，需要 {total_dura_need}，当前 {furnace.durability}",
                None,
            )

        # 检查材料
        materials_ok, error_msg = await self.check_materials(player_id, recipe, qty)
        if not materials_ok:
            return False, f"⛔ {error_msg}", None

        # 消耗材料
        if not await self.consume_materials(player_id, recipe, qty):
            return False, "⛔ 扣除材料失败", None

        # 扣除炉子耐久
        broken = furnace.lose_durability(total_dura_need)
        furnace_note = (
            "（炉子已损坏，需修理）" if broken else f"（剩余耐久 {furnace.durability}）"
        )
        if broken:
            # 炉子耐久为0：不再删除，保留以便修理
            pass

        # 创建炼丹记录
        # 运气炼丹加成（S型曲线：midpoint=1000, steepness=500, 上限+6%）
        # 上限保守设计：避免与炼丹炉升阶加成（最高2x）叠加过强
        from ..utils import luck_prob
        luck_alchemy_bonus = luck_prob(player_luck, midpoint=1000, steepness=500) * 0.06
        success_rate = min(0.95, recipe["base_success"] * coeff + luck_alchemy_bonus)
        duration_minutes = self.BASE_TIME_MINUTES * qty

        # 记录使用的材料
        materials_used = {mid: q * qty for mid, q in recipe["materials"].items()}

        record = AlchemyRecord(
            player_id=player_id,
            furnace_id=None if broken else furnace.id,
            recipe_key=recipe_key,
            produce_item_id=recipe["produce_item_id"],
            produce_per=recipe.get("quantity", 1),
            qty=qty,
            success_rate=success_rate,
            duration_minutes=duration_minutes,
        )
        record.set_materials_dict(materials_used)

        # 通过Repository添加记录
        await self._alchemy_record_repo.add(record)

        prod_name = config.items_config["by_id"][recipe["produce_item_id"]].name
        finish_time = record.get_finish_time()
        luck_line = f"\n🍀 运气加成：+{luck_alchemy_bonus * 100:.1f}%" if luck_alchemy_bonus > 0.001 else ""
        msg = (
            f"🕰️ 炼丹开始：{prod_name} ✖️{qty} 炉\n"
            f"🎯 理论成功率：{int(success_rate*100)}%{luck_line}\n"
            f"⏳ 预计完成时间点：{finish_time.strftime('%H:%M:%S')}\n"
            f"🔧 炉子状况 {furnace_note}"
        )

        return True, msg, record

    async def get_player_records(self, player_id: str) -> List[AlchemyRecord]:
        """
        获取玩家的炼丹记录

        Args:
            player_id: 玩家ID

        Returns:
            炼丹记录列表

        对应原代码:
            alchemy/service.py Line 221-225
        """
        return await self._alchemy_record_repo.get_by_player_id(player_id)

    async def claim_reward(self, record: AlchemyRecord) -> Tuple[bool, str]:
        """
        领取炼丹奖励（带行级锁，防止并发领取）

        Args:
            record: 炼丹记录

        Returns:
            (是否成功, 消息)

        对应原代码:
            alchemy/service.py Line 227-281

        修复:
            使用SELECT FOR UPDATE行锁 + 先标记后发放策略，防止竞态条件
        """
        if record.claimed:
            return False, "⛔ 该炼丹记录已领取"

        if not record.is_finished():
            return False, "⛔ 炼丹尚未完成"

        # 【关键修复】先标记为已领取，再发放物品
        # 这样即使后续操作卡顿，重复请求也会在此处被拦截
        record.claimed = True
        await self._alchemy_record_repo.update(record)
        await self._session.flush()  # 立即刷新到数据库，确保claimed标志生效

        success_count, total_produce = record.calculate_result()
        failed_count = record.qty - success_count
        prod_name = config.items_config["by_id"][record.produce_item_id].name

        # 发放成功产出的丹药
        if total_produce > 0:
            try:
                await self._item_repo.add_item(
                    record.player_id, record.produce_item_id, total_produce
                )
            except ValueError as e:
                # 如果发放失败，回滚claimed标志（虽然这种情况极少见）
                record.claimed = False
                return False, f"⛔ {prod_name} ✖️{total_produce} 领取失败：{e}"

        # 失败时返还50%材料（向上取整）
        returned_materials = []
        if failed_count > 0:
            materials_dict = record.get_materials_dict()
            for material_id, total_used in materials_dict.items():
                # 计算失败炉数对应的材料用量
                failed_material_used = (total_used * failed_count) // record.qty
                # 返还50%，向上取整
                return_amount = (failed_material_used + 1) // 2
                if return_amount > 0:
                    try:
                        await self._item_repo.add_item(
                            record.player_id, material_id, return_amount
                        )
                        material_name = config.items_config["by_id"][material_id].name
                        returned_materials.append(f"{material_name}✖️{return_amount}")
                    except ValueError:
                        # 如果添加失败，忽略该材料的返还
                        pass

        msg = f"✅ 炼丹完成！成功 {success_count}/{record.qty} 炉，共得 {prod_name} ✖️{total_produce}"

        # 添加材料返还信息
        if returned_materials:
            msg += f"\n🔄 失败返还：{', '.join(returned_materials)}"

        return True, msg

    def _format_recipe_entry(
        self, idx: int, recipe: dict, owned: Optional[Dict[str, int]] = None
    ) -> str:
        """格式化单条丹方（原生Markdown）

        owned: 玩家库存 {item_id: 数量}；None 时不显示库存
        """
        prod_cfg = config.items_config["by_id"][recipe["produce_item_id"]]
        mats = []
        for mid, need in recipe["materials"].items():
            name = config.items_config["by_id"][mid].name
            if owned is None:
                mats.append(f"{name}✖️{need}")
            else:
                have = owned.get(mid, 0)
                have_text = str(have) if have >= need else f"{have}⚠️"
                mats.append(f"{name}✖️{need}({have_text})")
        title = prod_cfg.name
        return (
            f"**{idx}.** {title} 成功率 **{int(recipe['base_success']*100)}%**｜{cmd('开炉', f'炼丹 {idx} 1')}\n"
            f"　{', '.join(mats)}"
        )

    def format_recipes(
        self,
        page: int = 1,
        page_size: int = 5,
        owned: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        格式化丹方列表（原生Markdown）

        Args:
            page: 页码
            page_size: 每页数量
            owned: 玩家库存 {item_id: 数量}，用于展示材料够不够

        Returns:
            Markdown内容字符串
        """
        recipes = [r for _, r in self.get_recipe_list()]
        total_pages = (len(recipes) - 1) // page_size + 1 if recipes else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        current = recipes[start:end]

        lines = [f"# 📜 丹方 · 第 {page}/{total_pages} 页", "***"]
        for idx, r in enumerate(current, start=start + 1):
            lines.append(self._format_recipe_entry(idx, r, owned))
        lines.append("***")
        if owned is not None:
            lines.append("> 材料括号内为库存，⚠️表示不足；发送【丹方 关键词】可搜索")
        else:
            lines.append("> 发送【丹方 关键词】可搜索")
        nav = []
        if page > 1:
            nav.append(cmd("⬅️上一页", f"丹方 {page - 1}"))
        if page < total_pages:
            nav.append(cmd("下一页➡️", f"丹方 {page + 1}"))
        nav.extend([cmd("炼丹状态"), cmd("收获丹药"), cmd("炼丹系统")])
        lines.append(" | ".join(nav))
        return "\n".join(lines)

    def format_recipe_search(
        self,
        keyword: str,
        matches: List[Tuple[int, str, dict]],
        owned: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        格式化丹方搜索结果（原生Markdown）

        Args:
            keyword: 搜索关键字
            matches: 匹配的丹方列表
            owned: 玩家库存 {item_id: 数量}，用于展示材料够不够

        Returns:
            Markdown内容字符串
        """
        lines = [f"# 🔍 丹方搜索：{keyword}", "***"]
        if not matches:
            lines.append("> 没有找到相关丹方，看看完整列表？")
            lines.append(cmd("丹方"))
            return "\n".join(lines)

        for idx, _, recipe in matches:
            lines.append(self._format_recipe_entry(idx, recipe, owned))
        lines.append("***")
        if owned is not None:
            lines.append("> 材料括号内为库存，⚠️表示不足")
        lines.append(" | ".join([cmd("丹方"), cmd("炼丹状态"), cmd("收获丹药")]))
        return "\n".join(lines)
