"""
账号切换服务

核心功能：
1. 账号管理：查看拥有的账号、切换账号、重命名账号
2. 账号转让：生成转让密钥、接收转让、取消转让
3. 历史查询：查看转让历史

设计原则：
- 一个真实玩家（platform_id）可以拥有多个游戏账号（Player）
- 同一时间只能有一个激活的游戏账号
- 账号可以通过6位数字密钥私下交易
- 所有转让操作都会记录审计日志
"""

from typing import Optional, List, Dict, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..infrastructure.repositories.account_ownership_repository import AccountOwnershipRepository
from ..infrastructure.repositories.account_transfer_log_repository import AccountTransferLogRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..models.account_ownership import AccountOwnership
from ..models.player import Player


class AccountSwitchingService:
    """账号切换服务"""

    def __init__(
        self,
        ownership_repo: AccountOwnershipRepository,
        transfer_log_repo: AccountTransferLogRepository,
        player_repo: PlayerRepository
    ):
        """
        初始化账号切换服务

        Args:
            ownership_repo: 账号所有权仓储
            transfer_log_repo: 转让历史仓储
            player_repo: 玩家仓储
        """
        self._ownership_repo = ownership_repo
        self._transfer_log_repo = transfer_log_repo
        self._player_repo = player_repo

    # ==================== 账号管理 ====================

    async def list_owned_accounts(
        self,
        owner_platform_id: str
    ) -> List[Dict[str, any]]:
        """
        查看拥有的所有游戏账号

        Args:
            owner_platform_id: 拥有者的平台ID

        Returns:
            账号列表，每个账号包含:
            - player_id: 游戏账号ID
            - display_name: 账号备注名
            - is_active: 是否激活
            - acquired_type: 获得方式
            - acquired_at: 获得时间
            - player_name: 游戏内角色名
            - level: 等级
            - cultivation_level_name: 境界名称
        """
        # 兜底：如果玩家存在但没有ownership记录（老玩家），自动补建
        ownerships = await self._ownership_repo.find_all_by_owner(
            owner_platform_id,
            include_player=True
        )

        owned_player_ids = {o.player_id for o in ownerships}
        original_player = await self._player_repo.get_by_id(owner_platform_id)
        if original_player and original_player.id not in owned_player_ids:
            new_ownership = AccountOwnership(
                owner_platform_id=owner_platform_id,
                player_id=original_player.id,
                is_active=True if not ownerships else False,
                display_name=original_player.nickname,
                acquired_type="created",
            )
            await self._ownership_repo.create(new_ownership)
            ownerships = await self._ownership_repo.find_all_by_owner(
                owner_platform_id,
                include_player=True
            )

        accounts = []
        for ownership in ownerships:
            player = await self._player_repo.get_by_id(ownership.player_id)
            if player:
                accounts.append({
                    "player_id": ownership.player_id,
                    "display_name": ownership.display_name or "未命名",
                    "is_active": ownership.is_active,
                    "acquired_type": ownership.acquired_type,
                    "acquired_at": ownership.acquired_at,
                    "player_name": player.nickname,
                    "level": player.level,
                    "uid": player.uid
                })

        return accounts

    async def get_active_account(
        self,
        owner_platform_id: str
    ) -> Optional[str]:
        """
        获取当前激活的游戏账号ID

        Args:
            owner_platform_id: 拥有者的平台ID

        Returns:
            激活的游戏账号ID，如果没有激活账号返回None
        """
        ownership = await self._ownership_repo.find_active_by_owner(owner_platform_id)
        return ownership.player_id if ownership else None

    async def switch_account(
        self,
        owner_platform_id: str,
        target_player_id: str
    ) -> Tuple[bool, str]:
        """
        切换到指定的游戏账号

        Args:
            owner_platform_id: 拥有者的平台ID
            target_player_id: 目标游戏账号ID

        Returns:
            (是否成功, 错误信息)
        """
        # 1. 验证所有权
        ownership = await self._ownership_repo.find_by_player_id(target_player_id)
        if not ownership:
            return False, "账号不存在"

        if ownership.owner_platform_id != owner_platform_id:
            return False, "这不是你的账号"

        # 2. 执行切换
        success = await self._ownership_repo.activate_account(
            owner_platform_id,
            target_player_id
        )

        if success:
            return True, "切换成功"
        else:
            return False, "切换失败"

    async def rename_account(
        self,
        owner_platform_id: str,
        player_id: str,
        display_name: str
    ) -> Tuple[bool, str]:
        """
        重命名账号备注

        Args:
            owner_platform_id: 拥有者的平台ID
            player_id: 游戏账号ID
            display_name: 新的备注名（最长32字符）

        Returns:
            (是否成功, 错误信息)
        """
        # 1. 验证所有权
        ownership = await self._ownership_repo.find_by_player_id(player_id)
        if not ownership:
            return False, "账号不存在"

        if ownership.owner_platform_id != owner_platform_id:
            return False, "这不是你的账号"

        # 2. 验证备注名长度
        if len(display_name) > 32:
            return False, "备注名过长（最多32字符）"

        # 3. 更新备注名
        ownership.display_name = display_name
        await self._ownership_repo.update(ownership)

        return True, "重命名成功"

    # ==================== 账号转让 ====================

    async def generate_transfer_key(
        self,
        owner_platform_id: str,
        player_id: str,
        is_admin: bool = False
    ) -> Tuple[bool, str]:
        """
        生成账号转让密钥

        Args:
            owner_platform_id: 拥有者的平台ID
            player_id: 要转让的游戏账号ID
            is_admin: 是否为管理员操作（管理员可以为任何账号生成转让密钥）

        Returns:
            (是否成功, 转让密钥或错误信息)
        """
        # 1. 验证所有权
        ownership = await self._ownership_repo.find_by_player_id(player_id)
        if not ownership:
            return False, "账号不存在"

        # 管理员可以跳过所有权检查
        if not is_admin and ownership.owner_platform_id != owner_platform_id:
            return False, "这不是你的账号"

        # 2. 生成转让密钥（允许转让激活账号，解决单账号转让的死锁问题）
        transfer_key = AccountOwnership.generate_transfer_key()
        ownership.transfer_key = transfer_key
        ownership.transfer_key_created_at = datetime.now()
        await self._ownership_repo.update(ownership)

        return True, transfer_key

    async def accept_transfer(
        self,
        recipient_platform_id: str,
        transfer_key: str
    ) -> Tuple[bool, str]:
        """
        使用转让密钥接收账号

        Args:
            recipient_platform_id: 接收者的平台ID
            transfer_key: 转让密钥

        Returns:
            (是否成功, 错误信息或接收的账号ID)
        """
        # 1. 查找转让密钥对应的账号
        ownership = await self._ownership_repo.find_by_transfer_key(transfer_key)
        if not ownership:
            return False, "无效的转让密钥"

        # 2. 不能转让给自己
        if ownership.owner_platform_id == recipient_platform_id:
            return False, "不能将账号转让给自己"

        # 3. 记录原拥有者
        original_owner = ownership.owner_platform_id
        player_id = ownership.player_id

        # 4. 更改所有权
        ownership.owner_platform_id = recipient_platform_id
        ownership.is_active = False  # 新账号默认不激活
        ownership.acquired_type = "transferred"
        ownership.acquired_at = datetime.now()
        ownership.clear_transfer_key()  # 清除转让密钥
        await self._ownership_repo.update(ownership)

        # 5. 记录转让历史
        await self._transfer_log_repo.create(
            player_id=player_id,
            from_platform_id=original_owner,
            to_platform_id=recipient_platform_id,
            transfer_type="sale",  # 默认为买卖，具体类型可以扩展
            transfer_key_used=transfer_key,
            notes=f"使用转让密钥{transfer_key}完成转让"
        )

        return True, f"成功接收账号 {player_id}"

    async def cancel_transfer_key(
        self,
        owner_platform_id: str,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        取消账号的转让密钥

        Args:
            owner_platform_id: 拥有者的平台ID
            player_id: 游戏账号ID

        Returns:
            (是否成功, 错误信息)
        """
        # 1. 验证所有权
        ownership = await self._ownership_repo.find_by_player_id(player_id)
        if not ownership:
            return False, "账号不存在"

        if ownership.owner_platform_id != owner_platform_id:
            return False, "这不是你的账号"

        # 2. 检查是否有转让密钥
        if not ownership.transfer_key:
            return False, "该账号没有生成转让密钥"

        # 3. 清除转让密钥
        ownership.clear_transfer_key()
        await self._ownership_repo.update(ownership)

        return True, "已取消转让密钥"

    # ==================== 历史查询 ====================

    async def get_transfer_history(
        self,
        platform_id: str,
        limit: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        查看转让历史（买入和卖出）

        Args:
            platform_id: 平台ID
            limit: 每个类别的限制数量

        Returns:
            包含"bought"（买入）和"sold"（卖出）两个列表的字典
        """
        # 1. 查询买入历史
        bought_logs = await self._transfer_log_repo.find_by_to_platform(
            platform_id,
            limit=limit
        )

        # 2. 查询卖出历史
        sold_logs = await self._transfer_log_repo.find_by_from_platform(
            platform_id,
            limit=limit
        )

        # 3. 格式化结果
        bought = [
            {
                "player_id": log.player_id,
                "from_platform_id": log.from_platform_id,
                "transfer_type": log.transfer_type,
                "transfer_time": log.transfer_time,
                "notes": log.notes
            }
            for log in bought_logs
        ]

        sold = [
            {
                "player_id": log.player_id,
                "to_platform_id": log.to_platform_id,
                "transfer_type": log.transfer_type,
                "transfer_time": log.transfer_time,
                "notes": log.notes
            }
            for log in sold_logs
        ]

        return {
            "bought": bought,
            "sold": sold
        }

    async def get_account_transfer_count(
        self,
        player_id: str
    ) -> int:
        """
        查询某个游戏账号的转让次数

        Args:
            player_id: 游戏账号ID

        Returns:
            转让次数
        """
        return await self._transfer_log_repo.count_transfers_by_player(player_id)

    # ==================== 管理员功能 ====================

    async def admin_force_transfer(
        self,
        player_id: str,
        to_platform_id: str,
        notes: str = "管理员强制转让"
    ) -> Tuple[bool, str]:
        """
        管理员强制转让账号（不需要转让密钥）

        Args:
            player_id: 游戏账号ID
            to_platform_id: 新拥有者的平台ID
            notes: 备注

        Returns:
            (是否成功, 错误信息)
        """
        # 1. 查找账号所有权
        ownership = await self._ownership_repo.find_by_player_id(player_id)
        if not ownership:
            return False, "账号不存在"

        # 2. 记录原拥有者
        original_owner = ownership.owner_platform_id

        # 3. 更改所有权
        ownership.owner_platform_id = to_platform_id
        ownership.is_active = False
        ownership.acquired_type = "transferred"
        ownership.acquired_at = datetime.now()
        ownership.clear_transfer_key()
        await self._ownership_repo.update(ownership)

        # 4. 记录转让历史
        await self._transfer_log_repo.create(
            player_id=player_id,
            from_platform_id=original_owner,
            to_platform_id=to_platform_id,
            transfer_type="admin",
            transfer_key_used=None,
            notes=notes
        )

        return True, "管理员强制转让成功"
