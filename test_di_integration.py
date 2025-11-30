"""
DI容器和UoW集成测试

验证:
1. DIContainer正确注册和解析服务
2. UnitOfWork正确管理事务边界
3. Repository通过UoW共享会话
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import yaml

# 加载数据库配置(直接读取YAML,避免触发NoneBot)
config_path = Path(__file__).parent / "plugins" / "xiuxian_game" / "config" / "database.yaml"
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

db_config = config["database"]["mysql"]
DATABASE_URL = f"mysql+aiomysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}?charset=utf8mb4"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

#导入模型和基础设施(绕过__init__.py)
import importlib.util

def import_module_from_path(module_name, file_path):
    """动态导入模块,避免触发__init__.py"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# 导入Player模型
Player = import_module_from_path(
    "player_model",
    Path(__file__).parent / "plugins" / "xiuxian_game" / "models" / "player.py"
).Player

# 导入DI容器
DIContainer = import_module_from_path(
    "di_container",
    Path(__file__).parent / "plugins" / "xiuxian_game" / "infrastructure" / "di" / "container.py"
).DIContainer

# 导入UoW
UnitOfWork = import_module_from_path(
    "uow",
    Path(__file__).parent / "plugins" / "xiuxian_game" / "infrastructure" / "uow" / "unit_of_work.py"
).UnitOfWork


async def test_di_container():
    """测试1: DIContainer基础功能"""
    print("\n" + "="*60)
    print("🧪 测试1: DIContainer基础功能")
    print("="*60)

    container = DIContainer()

    # 测试注册和解析
    container.register_singleton(str, lambda c: "singleton_value")
    container.register_transient(int, lambda c: 42)

    # 解析singleton
    value1 = container.resolve(str)
    value2 = container.resolve(str)
    assert value1 is value2, "❌ Singleton应该返回同一个实例"
    print(f"   ✓ Singleton工作正常: {value1}")

    # 解析transient
    num1 = container.resolve(int)
    num2 = container.resolve(int)
    print(f"   ✓ Transient工作正常: {num1}")

    # 测试未注册服务
    try:
        container.resolve(float)
        print("   ❌ 应该抛出ValueError")
        return False
    except ValueError as e:
        print(f"   ✓ 正确抛出异常: {e}")

    print("\n✅ DIContainer基础功能测试通过!")
    return True


async def test_uow_basic():
    """测试2: UoW基础功能"""
    print("\n" + "="*60)
    print("🧪 测试2: UnitOfWork基础功能")
    print("="*60)

    # 创建会话工厂
    def session_factory():
        return AsyncSessionLocal()

    # 测试会话创建和关闭
    async with UnitOfWork(session_factory) as uow:
        print(f"   ✓ 会话已创建: {id(uow.session)}")

        # 测试仓储访问
        player_repo = uow.players
        print(f"   ✓ PlayerRepository已创建: {type(player_repo).__name__}")

        # 验证会话共享
        assert uow.players._session is uow.session
        print(f"   ✓ Repository共享同一会话")

    print("\n✅ UnitOfWork基础功能测试通过!")
    return True


async def test_uow_transaction():
    """测试3: UoW事务管理"""
    print("\n" + "="*60)
    print("🧪 测试3: UnitOfWork事务管理")
    print("="*60)

    def session_factory():
        return AsyncSessionLocal()

    # 查询第一个玩家
    async with UnitOfWork(session_factory) as uow:
        stmt = select(Player).limit(1)
        result = await uow.session.execute(stmt)
        player = result.scalars().first()

        if not player:
            print("   ⚠ 数据库无玩家,跳过事务测试")
            return True

        player_id = player.id
        original_gold = player.gold
        print(f"   玩家: {player.nickname}, 初始金币: {original_gold}")

    # 测试: 修改但不提交(异常回滚)
    try:
        async with UnitOfWork(session_factory) as uow:
            player = await uow.players.get_by_id(player_id)
            player.gold += 1000
            print(f"   修改金币为: {player.gold}")
            raise ValueError("模拟异常,触发回滚")
    except ValueError:
        pass

    # 验证: 金币未改变
    async with UnitOfWork(session_factory) as uow:
        player = await uow.players.get_by_id(player_id)
        if player.gold == original_gold:
            print(f"   ✓ 回滚成功,金币仍为: {player.gold}")
        else:
            print(f"   ❌ 回滚失败,金币变为: {player.gold}")
            return False

    # 测试: 正常提交
    async with UnitOfWork(session_factory) as uow:
        player = await uow.players.get_by_id(player_id)
        player.gold += 1000
        print(f"   修改金币为: {player.gold}")
        # 正常退出,自动提交

    # 验证: 金币已改变
    async with UnitOfWork(session_factory) as uow:
        player = await uow.players.get_by_id(player_id)
        if player.gold == original_gold + 1000:
            print(f"   ✓ 提交成功,金币变为: {player.gold}")
            # 恢复原值
            player.gold = original_gold
        else:
            print(f"   ❌ 提交失败,金币为: {player.gold}")
            return False

    print("\n✅ UnitOfWork事务管理测试通过!")
    return True


async def test_repository_queries():
    """测试4: Repository查询功能"""
    print("\n" + "="*60)
    print("🧪 测试4: Repository查询功能")
    print("="*60)

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 测试get_by_id
        stmt = select(Player).limit(1)
        result = await uow.session.execute(stmt)
        player = result.scalars().first()

        if not player:
            print("   ⚠ 数据库无玩家,跳过查询测试")
            return True

        # 通过Repository查询
        player_from_repo = await uow.players.get_by_id(player.id)
        assert player_from_repo.id == player.id
        print(f"   ✓ get_by_id工作正常: {player_from_repo.nickname}")

        # 测试exists
        exists = await uow.players.exists(player.id)
        assert exists is True
        print(f"   ✓ exists工作正常: {exists}")

        # 测试count
        count = await uow.players.count()
        print(f"   ✓ count工作正常: {count}个玩家")

        # 测试get_by_nickname
        player_by_name = await uow.players.get_by_nickname(player.nickname)
        if player_by_name:
            assert player_by_name.id == player.id
            print(f"   ✓ get_by_nickname工作正常")

    print("\n✅ Repository查询功能测试通过!")
    return True


async def main():
    """主测试函数"""
    print("\n" + "🧪 DI容器和UoW集成测试".center(60, "="))
    print("目标: 验证DI容器、UoW和Repository的集成")
    print("="*60)

    all_passed = True

    # 测试1: DIContainer基础功能
    try:
        if not await test_di_container():
            all_passed = False
    except Exception as e:
        print(f"\n❌ DIContainer测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试2: UoW基础功能
    try:
        if not await test_uow_basic():
            all_passed = False
    except Exception as e:
        print(f"\n❌ UoW基础测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试3: UoW事务管理
    try:
        if not await test_uow_transaction():
            all_passed = False
    except Exception as e:
        print(f"\n❌ UoW事务测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试4: Repository查询功能
    try:
        if not await test_repository_queries():
            all_passed = False
    except Exception as e:
        print(f"\n❌ Repository查询测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 总结
    print("\n" + "="*60)
    if all_passed:
        print("✅ 所有测试通过!DI容器和UoW集成成功!".center(60))
    else:
        print("❌ 部分测试失败".center(60))
    print("="*60 + "\n")

    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
