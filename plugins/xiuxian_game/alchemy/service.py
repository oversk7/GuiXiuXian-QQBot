"""
炼丹服务 - 核心业务逻辑
"""
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..config import config
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.alchemy_task import AlchemyRecord


class AlchemyService:
    """炼丹服务类 - 封装所有炼丹相关的业务逻辑"""
    
    # 炼丹炉基础配置
    FURNACE_ITEM_ID = "furnace"  # 统一的炼丹炉item_id
    
    BASE_TIME_MINUTES = 5  # 每炉基础耗时5分钟

    @classmethod
    def get_furnace_effects(cls, upgrade_level: int) -> Tuple[float, int]:
        """
        根据炼丹炉升阶等级计算效果
        Returns:
            (成功率系数, 耐久消耗基数)
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
    
    @classmethod
    def get_recipes(cls) -> Dict[str, dict]:
        """获取所有丹方配置"""
        return config.elixirs_config.get("elixirs", {})

    @classmethod
    def get_recipe_list(cls) -> List[Tuple[str, dict]]:
        """以列表形式返回丹方配置，保持原有顺序"""
        return list(cls.get_recipes().items())

    @classmethod
    def find_recipe(cls, target: str) -> Optional[Tuple[str, dict]]:
        """
        查找丹方
        Args:
            target: 丹方序号(数字字符串)或丹方名称或产物名称
        Returns:
            (recipe_key, recipe_config) 或 None
        """
        recipes_dict = cls.get_recipes()
        recipes = cls.get_recipe_list()
        
        # 按序号查找
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(recipes):
                return recipes[idx-1]
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

    @classmethod
    def search_recipes(cls, keyword: str) -> List[Tuple[int, str, dict]]:
        """按关键字搜索丹方，返回(序号, 配方key, 配方)列表"""
        keyword = keyword.strip()
        if not keyword:
            return []

        keyword_lower = keyword.lower()
        results: List[Tuple[int, str, dict]] = []
        for idx, (key, recipe) in enumerate(cls.get_recipe_list(), start=1):
            prod_cfg = config.items_config["by_id"][recipe["produce_item_id"]]
            prod_name = prod_cfg.name

            if keyword_lower in key.lower() or keyword in prod_name or keyword_lower in prod_name.lower():
                results.append((idx, key, recipe))

        return results

    @classmethod
    async def get_player_furnaces(cls, session: AsyncSession, player_id: str) -> List[ItemInstance]:
        """获取玩家的所有炼丹炉"""
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == cls.FURNACE_ITEM_ID,
        )
        furnaces = (await session.execute(stmt)).scalars().all()
        # 按升阶等级、耐久排序
        furnaces.sort(key=lambda inst: (inst.upgrade_level, inst.durability), reverse=True)
        return furnaces
    
    @classmethod
    async def check_materials(cls, session: AsyncSession, player_id: str, recipe: dict, qty: int) -> Tuple[bool, str]:
        """
        检查材料是否充足
        Returns:
            (是否充足, 错误信息)
        """
        invs = (await session.execute(select(ItemInstance).where(ItemInstance.player_id == player_id))).scalars().all()

        mats_required = {mid: q * qty for mid, q in recipe["materials"].items()}
        missing_details: List[str] = []
        for mid, need in mats_required.items():
            total_have = sum(i.quantity for i in invs if i.item_id == mid)
            if total_have < need:
                name = config.items_config["by_id"][mid].name
                shortage = need - total_have
                missing_details.append(
                    f"{name}✖️{need}（缺少{shortage}）"
                )

        if missing_details:
            return False, "材料不足：" + "、".join(missing_details)

        return True, ""
    
    @classmethod
    async def consume_materials(cls, session: AsyncSession, player_id: str, recipe: dict, qty: int) -> bool:
        """消耗材料"""
        mats_required = {mid: q * qty for mid, q in recipe["materials"].items()}
        for mid, need in mats_required.items():
            success = await ItemInstance.consume_item(session, player_id, mid, need)
            if not success:
                return False
        return True
    
    @classmethod
    async def start_alchemy(cls, session: AsyncSession, player_id: str, furnace_id: int, 
                          recipe_key: str, recipe: dict, qty: int) -> Tuple[bool, str, Optional[AlchemyRecord]]:
        """
        开始炼丹
        Returns:
            (是否成功, 消息, 炼丹记录)
        """
        # 获取炉子
        furnace = await session.get(ItemInstance, furnace_id)
        if not furnace or furnace.player_id != player_id:
            return False, "⛔ 未找到对应炼丹炉或非本人所有", None
        
        if furnace.item_id != cls.FURNACE_ITEM_ID:
            return False, "⛔ 该装备不是炼丹炉", None

        coeff, dura_cost_base = cls.get_furnace_effects(furnace.upgrade_level)
        
        # 检查耐久
        total_dura_need = dura_cost_base * qty
        if furnace.durability < total_dura_need:
            return False, f"⛔ 炉子耐久不足，需要 {total_dura_need}，当前 {furnace.durability}", None
        
        # 检查材料
        materials_ok, error_msg = await cls.check_materials(session, player_id, recipe, qty)
        if not materials_ok:
            return False, f"⛔ {error_msg}", None
        
        # 消耗材料
        if not await cls.consume_materials(session, player_id, recipe, qty):
            return False, "⛔ 扣除材料失败", None
        
        # 扣除炉子耐久
        broken = furnace.lose_durability(total_dura_need)
        furnace_note = "（炉子已损坏）" if broken else f"（剩余耐久 {furnace.durability})"
        if broken:
            await session.delete(furnace)
        
        # 创建炼丹记录
        success_rate = min(0.95, recipe["base_success"] * coeff)
        duration_minutes = cls.BASE_TIME_MINUTES * qty

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
        session.add(record)
        
        prod_name = config.items_config["by_id"][recipe["produce_item_id"]].name
        finish_time = record.get_finish_time()
        msg = (
            f"🕰️ 炼丹开始：{prod_name} ✖️{qty} 炉\n"
            f"🎯 理论成功率：{int(success_rate*100)}%\n"
            f"⏳ 预计完成时间点：{finish_time.strftime('%H:%M:%S')}\n"
            f"🔧 炉子状况 {furnace_note}"
        )
        
        return True, msg, record
    
    @classmethod
    async def get_player_records(cls, session: AsyncSession, player_id: str) -> List[AlchemyRecord]:
        """获取玩家的炼丹记录"""
        stmt = select(AlchemyRecord).where(AlchemyRecord.player_id == player_id)
        return (await session.execute(stmt)).scalars().all()
    
    @classmethod
    async def claim_reward(cls, session: AsyncSession, record: AlchemyRecord) -> Tuple[bool, str]:
        """
        领取炼丹奖励
        Returns:
            (是否成功, 消息)
        """
        if record.claimed:
            return False, "⛔ 该炼丹记录已领取"
        
        if not record.is_finished():
            return False, "⛔ 炼丹尚未完成"
        
        success_count, total_produce = record.calculate_result()
        failed_count = record.qty - success_count

        # 发放成功产出的丹药
        if total_produce > 0:
            try:
                await ItemInstance.add_item(session, record.player_id, record.produce_item_id, total_produce)
            except ValueError as e:
                return False, f"⛔ 领取失败：{e}"

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
                        await ItemInstance.add_item(session, record.player_id, material_id, return_amount)
                        material_name = config.items_config["by_id"][material_id].name
                        returned_materials.append(f"{material_name}✖️{return_amount}")
                    except ValueError:
                        # 如果添加失败，忽略该材料的返还
                        pass

        # 标记为已领取（为了确保消息生成正确）
        record.claimed = True

        prod_name = config.items_config["by_id"][record.produce_item_id].name
        msg = f"✅ 炼丹完成！成功 {success_count}/{record.qty} 炉，共得 {prod_name} ✖️{total_produce}"

        # 添加材料返还信息
        if returned_materials:
            msg += f"\n🔄 失败返还：{', '.join(returned_materials)}"

        # 领取成功后删除记录，避免记录一直保留
        await session.delete(record)

        return True, msg
    
    @classmethod
    def format_recipes(cls, page: int = 1, page_size: int = 5) -> str:
        """格式化丹方列表"""
        recipes = [r for _, r in cls.get_recipe_list()]
        total_pages = (len(recipes)-1)//page_size + 1 if recipes else 1
        page = max(1, min(page, total_pages))
        start = (page-1)*page_size
        end = start+page_size
        current = recipes[start:end]

        lines = ["📜 可用丹方", "━"*10]
        for idx, r in enumerate(current, start=start+1):
            prod_cfg = config.items_config["by_id"][r["produce_item_id"]]
            mats = ", ".join([f"{config.items_config['by_id'][mid].name}✖️{qty}" for mid, qty in r["materials"].items()])
            lines.append(f"{idx}. {prod_cfg.name} (成功率 {int(r['base_success']*100)}%)\n   材料: {mats}")
        lines.append(f"\n页 {page}/{total_pages}")
        return "\n".join(lines)

    @classmethod
    def format_recipe_search(cls, keyword: str, matches: List[Tuple[int, str, dict]]) -> str:
        """格式化丹方搜索结果"""
        if not matches:
            return f"🔍 未找到与“{keyword}”相关的丹方"

        lines = [f"🔍 丹方搜索：{keyword}", "━" * 10]
        for idx, _, recipe in matches:
            prod_cfg = config.items_config["by_id"][recipe["produce_item_id"]]
            mats = ", ".join(
                [
                    f"{config.items_config['by_id'][mid].name}✖️{qty}"
                    for mid, qty in recipe["materials"].items()
                ]
            )
            lines.append(
                f"{idx}. {prod_cfg.name} (成功率 {int(recipe['base_success']*100)}%)\n   材料: {mats}"
            )

        lines.append("\n➡️ 使用【炼丹 配方序号|名称 [数量]】开始炼丹")
        return "\n".join(lines)
