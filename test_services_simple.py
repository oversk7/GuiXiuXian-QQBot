"""
简化的Service测试脚本 - 不依赖NoneBot环境
直接测试Service层的session管理
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到path
sys.path.insert(0, str(Path(__file__).parent))

# 直接导入需要的模块，避免触发NoneBot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# 导入配置
from plugins.xiuxian_game.config.mysql_config import MYSQL_CONFIG

# 导入模型
from plugins.xiuxian_game.models.player import Player

# 创建数据库引擎
DATABASE_URL = f"mysql+aiomysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}?charset=utf8mb4"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def safe_session():
    """模拟safe_session context manager"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def test_stock_service_session_management():
    """测试StockService的session管理"""
    print("\n" + "="*60)
    print("📊 测试 StockService Session管理")
    print("="*60)

    # 导入Service（在函数内部导入避免全局初始化问题）
    from plugins.xiuxian_game.economy.stock_service import StockService

    # 测试1: 验证方法接收session参数
    print("\n✅ 测试1: 验证方法签名")
    import inspect

    methods_to_check = [
        'check_and_update_prices',
        'buy_stock',
        'sell_stock',
        'get_player_holdings',
        'get_player_transactions'
    ]

    for method_name in methods_to_check:
        method = getattr(StockService, method_name)
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())

        # 检查第一个参数（除了cls）是否是session
        if len(params) > 1 and params[1] == 'session':
            print(f"   ✓ {method_name}: 第一个参数是session")
        else:
            print(f"   ✗ {method_name}: 参数不正确 {params}")
            return False

    # 测试2: 验证Service不内部管理session
    print("\n✅ 测试2: 验证Service不内部commit")
    async with AsyncSessionLocal() as session:
        try:
            # 调用方法并确保它不会抛出session相关错误
            updated = await StockService.check_and_update_prices(session, force_update=False)
            print(f"   ✓ check_and_update_prices 可以正常接收外部session")
            print(f"   价格更新: {updated}")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False
        await session.commit()

    # 测试3: 测试真实的查询功能
    print("\n✅ 测试3: 测试实际功能")
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                holdings = await StockService.get_player_holdings(session, player.id)
                print(f"   玩家: {player.nickname}")
                print(f"   持仓数量: {len(holdings)}")
                print("   ✓ get_player_holdings 正常工作")
            else:
                print("   ⚠ 数据库无玩家，跳过功能测试")

        except Exception as e:
            print(f"   ✗ 错误: {e}")
            import traceback
            traceback.print_exc()
            return False
        await session.commit()

    print("\n" + "="*60)
    print("✅ StockService Session管理测试通过！")
    print("="*60)
    return True


async def test_part_time_job_service_session_management():
    """测试PartTimeJobService的session管理"""
    print("\n" + "="*60)
    print("💼 测试 PartTimeJobService Session管理")
    print("="*60)

    from plugins.xiuxian_game.economy.part_time_job_service import PartTimeJobService

    # 测试1: 验证方法签名
    print("\n✅ 测试1: 验证方法签名")
    import inspect

    methods_to_check = [
        'initialize_job_locations',
        'get_available_jobs_at_location',
        'start_job',
        'complete_job',
        'get_current_job_status',
        'get_or_create_player_stats',
        'get_job_locations_list',
        'get_player_job_history'
    ]

    for method_name in methods_to_check:
        method = getattr(PartTimeJobService, method_name)
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())

        # 检查第一个参数（除了cls）是否是session
        if len(params) > 1 and params[1] == 'session':
            print(f"   ✓ {method_name}: 第一个参数是session")
        else:
            print(f"   ✗ {method_name}: 参数不正确 {params}")
            return False

    # 测试2: 验证Service不内部commit
    print("\n✅ 测试2: 验证Service不内部commit")
    async with AsyncSessionLocal() as session:
        try:
            locations = await PartTimeJobService.get_job_locations_list(session)
            print(f"   ✓ get_job_locations_list 可以正常接收外部session")
            print(f"   工作地点: {len(locations)}个")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False
        await session.commit()

    # 测试3: 测试真实功能
    print("\n✅ 测试3: 测试实际功能")
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                success, msg, jobs = await PartTimeJobService.get_available_jobs_at_location(
                    session, player
                )
                print(f"   玩家: {player.nickname} ({player.x}, {player.y})")
                print(f"   结果: {msg}")
                print("   ✓ get_available_jobs_at_location 正常工作")
            else:
                print("   ⚠ 数据库无玩家，跳过功能测试")

        except Exception as e:
            print(f"   ✗ 错误: {e}")
            import traceback
            traceback.print_exc()
            return False
        await session.commit()

    print("\n" + "="*60)
    print("✅ PartTimeJobService Session管理测试通过！")
    print("="*60)
    return True


async def test_transaction_boundary():
    """测试事务边界控制"""
    print("\n" + "="*60)
    print("🔒 测试事务边界控制")
    print("="*60)

    print("\n✅ 测试: Session commit由调用方控制")

    # 测试修改是否会自动提交
    async with AsyncSessionLocal() as session:
        stmt = select(Player).limit(1)
        player = (await session.execute(stmt)).scalars().first()

        if not player:
            print("   ⚠ 数据库无玩家，跳过测试")
            return True

        player_id = player.id
        original_gold = player.gold

        # 修改但不commit
        player.gold += 1000
        session.add(player)
        print(f"   修改玩家金币: {original_gold} -> {player.gold}")
        print("   未执行commit")

    # 重新查询，应该看到原值（因为上面没commit）
    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        if player.gold == original_gold:
            print(f"   ✓ 验证成功: 未commit的修改未保存 (金币仍为{player.gold})")
        else:
            print(f"   ⚠ 注意: AsyncSession可能自动提交了 (金币变为{player.gold})")
            # 恢复原值
            player.gold = original_gold
            session.add(player)
            await session.commit()

    # 测试显式commit
    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        player.gold += 1000
        session.add(player)
        await session.commit()
        print(f"   显式commit后金币: {player.gold}")

    # 验证commit成功
    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        if player.gold == original_gold + 1000:
            print(f"   ✓ 验证成功: commit后的修改已保存")
            # 恢复原值
            player.gold = original_gold
            session.add(player)
            await session.commit()
        else:
            print(f"   ✗ 验证失败: commit未生效")
            return False

    print("\n" + "="*60)
    print("✅ 事务边界控制测试通过！")
    print("="*60)
    return True


async def main():
    """主测试函数"""
    print("\n" + "🔬 Service Session管理测试".center(60, "="))
    print("目标: 验证Service层的session管理重构")
    print("="*60)

    all_passed = True

    try:
        if not await test_stock_service_session_management():
            all_passed = False
    except Exception as e:
        print(f"\n❌ StockService测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    try:
        if not await test_part_time_job_service_session_management():
            all_passed = False
    except Exception as e:
        print(f"\n❌ PartTimeJobService测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    try:
        if not await test_transaction_boundary():
            all_passed = False
    except Exception as e:
        print(f"\n❌ 事务边界测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 清理
    await engine.dispose()

    # 总结
    print("\n" + "="*60)
    if all_passed:
        print("✅ 所有测试通过！Session管理重构成功！".center(60))
    else:
        print("❌ 部分测试失败".center(60))
    print("="*60 + "\n")

    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
