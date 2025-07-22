"""数据库备份服务"""
import os
import shutil
import glob
from datetime import datetime
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


class DatabaseBackupService:
    """数据库备份服务类"""
    
    def __init__(self):
        # 数据库文件路径
        self.db_path = Path(__file__).parent.parent / "data" / "game.db"
        # 备份目录（项目根目录）
        self.backup_dir = Path(__file__).parent.parent.parent.parent
        # 备份文件名前缀
        self.backup_prefix = "game_backup_"
        # 最大保留备份数量
        self.max_backups = 3
    
    def create_backup(self) -> bool:
        """
        创建数据库备份
        返回: 是否成功
        """
        try:
            # 检查数据库文件是否存在
            if not self.db_path.exists():
                logger.warning(f"数据库文件不存在: {self.db_path}")
                return False
            
            # 生成备份文件名（包含时间戳）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{self.backup_prefix}{timestamp}.db"
            backup_path = self.backup_dir / backup_filename
            
            # 复制数据库文件到备份目录
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"数据库备份成功: {backup_path}")
            
            # 清理旧备份
            self._cleanup_old_backups()
            
            return True
            
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return False
    
    def _cleanup_old_backups(self) -> None:
        """清理旧的备份文件，只保留最近的几个"""
        try:
            # 获取所有备份文件
            backup_pattern = str(self.backup_dir / f"{self.backup_prefix}*.db")
            backup_files = glob.glob(backup_pattern)
            
            # 按修改时间排序（最新的在前）
            backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            # 删除超出保留数量的备份文件
            files_to_delete = backup_files[self.max_backups:]
            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                    logger.info(f"删除旧备份文件: {file_path}")
                except OSError as e:
                    logger.error(f"删除备份文件失败 {file_path}: {e}")
                    
        except Exception as e:
            logger.error(f"清理旧备份失败: {e}")
    
    def get_backup_list(self) -> List[dict]:
        """
        获取备份文件列表
        返回: 备份文件信息列表 [{"filename": str, "size": int, "created_time": datetime}, ...]
        """
        try:
            backup_pattern = str(self.backup_dir / f"{self.backup_prefix}*.db")
            backup_files = glob.glob(backup_pattern)
            
            backup_info = []
            for file_path in backup_files:
                try:
                    stat = os.stat(file_path)
                    backup_info.append({
                        "filename": os.path.basename(file_path),
                        "full_path": file_path,
                        "size": stat.st_size,
                        "created_time": datetime.fromtimestamp(stat.st_mtime)
                    })
                except OSError:
                    continue
            
            # 按创建时间排序（最新的在前）
            backup_info.sort(key=lambda x: x["created_time"], reverse=True)
            return backup_info
            
        except Exception as e:
            logger.error(f"获取备份列表失败: {e}")
            return []
    
    def restore_backup(self, backup_filename: str) -> bool:
        """
        从备份恢复数据库
        参数: backup_filename - 备份文件名
        返回: 是否成功
        """
        try:
            backup_path = self.backup_dir / backup_filename
            
            if not backup_path.exists():
                logger.error(f"备份文件不存在: {backup_path}")
                return False
            
            # 创建当前数据库的临时备份
            temp_backup = self.db_path.with_suffix(".db.temp")
            if self.db_path.exists():
                shutil.copy2(self.db_path, temp_backup)
            
            try:
                # 恢复备份
                shutil.copy2(backup_path, self.db_path)
                logger.info(f"数据库恢复成功: {backup_filename}")
                
                # 删除临时备份
                if temp_backup.exists():
                    temp_backup.unlink()
                
                return True
                
            except Exception as e:
                # 恢复失败，回滚到临时备份
                if temp_backup.exists():
                    shutil.copy2(temp_backup, self.db_path)
                    temp_backup.unlink()
                raise e
                
        except Exception as e:
            logger.error(f"数据库恢复失败: {e}")
            return False


# 全局备份服务实例
backup_service = DatabaseBackupService()
