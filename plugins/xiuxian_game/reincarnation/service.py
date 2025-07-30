"""
冥返系统服务模块
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.player import Player
from ..models.elixir_usage import ElixirUsageLog
from ..models.inventory import ItemInstance
from ..config import config


class ReincarnationService:
    """冥返系统服务类"""
    
    @staticmethod
    async def can_reincarnate(player: Player) -> bool:
        """检查玩家是否可以冥返"""
        required_level = ReincarnationService.get_required_level_for_reincarnation(player.reincarnation_level)
        return player.level >= required_level
    
    @staticmethod
    async def perform_reincarnation(session: AsyncSession, player: Player) -> str:
        """执行冥返操作"""
        if not await ReincarnationService.can_reincarnate(player):
            required_level = ReincarnationService.get_required_level_for_reincarnation(player.reincarnation_level)
            return f"⛔ 尚未达到冥返要求，需要达到 {required_level} 级才能进行第{player.reincarnation_level + 1}次冥返"
        
        # 获取丹药加成
        elixir_bonus = await ReincarnationService._get_elixir_bonus(session, player.id)
        
        # 初始基础属性
        INIT_ATTRS = {
            "max_hp": 20,
            "max_mp": 20,
            "attack": 1,
            "defense": 5,
            "agility": 5,
            "luck": 1,
        }
        
        # 记录冥返前的信息
        old_level = player.level
        old_reincarnation = player.reincarnation_level
        
        # 重置属性为基础值 + 丹药加成
        for attr_name, base_value in INIT_ATTRS.items():
            setattr(player, attr_name, base_value + elixir_bonus.get(attr_name, 0))
        
        # 重置等级和经验
        player.level = 1
        player.exp = 0
        player.attribute_points = 0
        
        # 增加转数
        player.reincarnation_level += 1
        
        # 恢复满血满蓝
        player.hp = player.max_hp
        player.mp = player.max_mp
        
        # 重新计算装备加成
        await ReincarnationService._recalculate_equipment_bonus(session, player)
        
        session.add(player)
        await session.commit()
        
        # 构建冥返消息
        next_required_level = ReincarnationService.get_required_level_for_reincarnation(player.reincarnation_level)
        next_reincarnation_count = player.reincarnation_level + 1

        msg = (
            f"🌟 冥返成功！踏入第{player.reincarnation_level}转轮回\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 从 Lv.{old_level} 重塑为 Lv.1\n"
            f"✧ 转数：{old_reincarnation} → {player.reincarnation_level}\n"
            f"✧ 每级属性点：{ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)}\n"
            f"✧ 修炼效率加成：+{ReincarnationService.get_cultivation_efficiency_bonus(player.reincarnation_level):.0%}\n"
            f"✧ 闭关效率加成：+{ReincarnationService.get_seclusion_efficiency_bonus(player.reincarnation_level):.0%}\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 下次冥返：需达到 Lv.{next_required_level} (第{next_reincarnation_count}次)\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【修炼】重新踏上修仙之路\n"
            "⬇️ 【面板】查看新的属性"
        )
        
        return msg
    
    @staticmethod
    async def _get_elixir_bonus(session: AsyncSession, player_id: str) -> dict:
        """获取玩家的丹药加成"""
        stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player_id)
        logs = (await session.execute(stmt)).scalars().all()
        
        elixir_bonus = {}
        for log in logs:
            for attr_name, bonus in log.get_attribute_bonus().items():
                elixir_bonus[attr_name] = elixir_bonus.get(attr_name, 0) + bonus
        
        return elixir_bonus
    
    @staticmethod
    async def _recalculate_equipment_bonus(session: AsyncSession, player: Player):
        """重新计算装备加成"""
        # 获取所有已装备的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
        )
        equipped_items = (await session.execute(stmt)).scalars().all()
        
        # 计算装备加成
        equipment_bonus = {}
        for item in equipped_items:
            item_config = item.config
            if item_config and item_config.attr_bonus:
                for attr_name, bonus in item_config.attr_bonus.items():
                    equipment_bonus[attr_name] = equipment_bonus.get(attr_name, 0) + bonus
        
        # 应用装备加成
        for attr_name, bonus in equipment_bonus.items():
            if hasattr(player, attr_name):
                current_value = getattr(player, attr_name)
                setattr(player, attr_name, current_value + bonus)
    
    @staticmethod
    def get_attribute_points_per_level(reincarnation_level: int) -> int:
        """获取每级获得的属性点数：(转数+1)*10"""
        base_points = config.game_config["game"]["points_per_level"]
        return int((reincarnation_level*0.5 + 1) * base_points)
    
    @staticmethod
    def get_cultivation_efficiency_bonus(reincarnation_level: int) -> float:
        """获取修炼效率加成"""
        bonus_per_level = config.game_config["game"]["reincarnation"]["cultivation_efficiency_bonus"]
        return reincarnation_level * bonus_per_level
    
    @staticmethod
    def get_seclusion_efficiency_bonus(reincarnation_level: int) -> float:
        """获取闭关效率加成"""
        bonus_per_level = config.game_config["game"]["reincarnation"]["seclusion_efficiency_bonus"]
        return reincarnation_level * bonus_per_level

    @staticmethod
    def get_required_level_for_reincarnation(current_reincarnation_level: int) -> int:
        """
        计算下次冥返所需的等级
        第一次冥返：300级
        第二次冥返：500级
        第三次冥返：1000级
        之后每次递增500级
        """
        if current_reincarnation_level == 0:
            # 第一次冥返需要300级
            return 300
        elif current_reincarnation_level == 1:
            # 第二次冥返需要500级
            return 500
        elif current_reincarnation_level == 2:
            # 第三次冥返需要1000级
            return 1000
        else:
            # 第四次及以后，每次递增500级
            # 第三次是1000级，第四次是1500级，第五次是2000级...
            return 1000 + (current_reincarnation_level - 2) * 500
