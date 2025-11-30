"""
Service重构测试脚本

用于测试StockService和PartTimeJobService的session管理重构
模拟玩家操作，验证功能是否正常
"""

import asyncio
from sqlalchemy import select
from plugins.xiuxian_game.models.db import safe_session
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.economy.stock_service import StockService
from plugins.xiuxian_game.economy.part_time_job_service import PartTimeJobService


async def test_stock_service():
    """测试股票服务"""
    print("\n" + "="*60)
    print("📊 开始测试 StockService")
    print("="*60)

    # 测试1: 获取股票列表和价格检查
    async with safe_session() as session:
        print("\n✅ 测试1: 检查并更新股票价格")
        try:
            updated = await StockService.check_and_update_prices(session, force_update=False)
            print(f"   价格更新状态: {updated}")
            print("   ✓ check_and_update_prices 正常工作")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    # 测试2: 获取玩家持仓（使用测试玩家）
    async with safe_session() as session:
        print("\n✅ 测试2: 获取玩家持仓")
        try:
            # 获取第一个玩家作为测试对象
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                holdings = await StockService.get_player_holdings(session, player.id)
                print(f"   测试玩家: {player.nickname} (ID: {player.id})")
                print(f"   持仓数量: {len(holdings)}")
                if holdings:
                    for h in holdings[:3]:  # 只显示前3个
                        print(f"   - {h['name']}: {h['shares']}份")
                print("   ✓ get_player_holdings 正常工作")
            else:
                print("   ⚠ 数据库中没有玩家，跳过此测试")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    # 测试3: 获取交易记录
    async with safe_session() as session:
        print("\n✅ 测试3: 获取交易记录")
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                transactions = await StockService.get_player_transactions(session, player.id, limit=5)
                print(f"   交易记录数量: {len(transactions)}")
                if transactions:
                    for t in transactions[:3]:
                        print(f"   - {t['name']}: {t['type'].value} {t['shares']}份")
                print("   ✓ get_player_transactions 正常工作")
            else:
                print("   ⚠ 数据库中没有玩家，跳过此测试")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    print("\n" + "="*60)
    print("✅ StockService 所有测试通过！")
    print("="*60)
    return True


async def test_part_time_job_service():
    """测试打工服务"""
    print("\n" + "="*60)
    print("💼 开始测试 PartTimeJobService")
    print("="*60)

    # 测试1: 获取工作地点列表
    async with safe_session() as session:
        print("\n✅ 测试1: 获取工作地点列表")
        try:
            locations = await PartTimeJobService.get_job_locations_list(session)
            print(f"   工作地点数量: {len(locations)}")
            for loc in locations:
                print(f"   - {loc['name']}: {loc['job_count']}个工作")
            print("   ✓ get_job_locations_list 正常工作")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    # 测试2: 获取玩家位置的可用工作
    async with safe_session() as session:
        print("\n✅ 测试2: 获取玩家可用工作")
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                success, msg, jobs = await PartTimeJobService.get_available_jobs_at_location(session, player)
                print(f"   测试玩家: {player.nickname}")
                print(f"   位置: ({player.x}, {player.y}) - {player.region}")
                print(f"   结果: {msg}")
                if success:
                    print(f"   可用工作: {len(jobs)}个")
                    for job in jobs[:3]:
                        print(f"   - {job['name']}: {job['base_reward']}金币")
                print("   ✓ get_available_jobs_at_location 正常工作")
            else:
                print("   ⚠ 数据库中没有玩家，跳过此测试")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    # 测试3: 获取玩家工作状态
    async with safe_session() as session:
        print("\n✅ 测试3: 获取玩家工作状态")
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                success, msg, status = await PartTimeJobService.get_current_job_status(session, player)
                print(f"   工作状态: {msg}")
                if success and status:
                    print(f"   工作名称: {status['job_name']}")
                    print(f"   是否完成: {status['is_completed']}")
                print("   ✓ get_current_job_status 正常工作")
            else:
                print("   ⚠ 数据库中没有玩家，跳过此测试")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    # 测试4: 获取玩家打工统计
    async with safe_session() as session:
        print("\n✅ 测试4: 获取玩家打工统计")
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                stats = await PartTimeJobService.get_or_create_player_stats(session, player.id)
                print(f"   完成工作: {stats.total_jobs_completed}次")
                print(f"   总收入: {stats.total_earnings}金币")
                print(f"   总工时: {stats.total_work_hours}小时")
                print("   ✓ get_or_create_player_stats 正常工作")
            else:
                print("   ⚠ 数据库中没有玩家，跳过此测试")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    # 测试5: 获取打工历史
    async with safe_session() as session:
        print("\n✅ 测试5: 获取打工历史")
        try:
            stmt = select(Player).limit(1)
            player = (await session.execute(stmt)).scalars().first()

            if player:
                history = await PartTimeJobService.get_player_job_history(session, player.id, limit=5)
                print(f"   历史记录: {len(history)}条")
                for job in history[:3]:
                    print(f"   - {job['job_name']}: {job['total_reward']}金币")
                print("   ✓ get_player_job_history 正常工作")
            else:
                print("   ⚠ 数据库中没有玩家，跳过此测试")
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            return False

    print("\n" + "="*60)
    print("✅ PartTimeJobService 所有测试通过！")
    print("="*60)
    return True


async def test_transaction_atomicity():
    """测试事务原子性"""
    print("\n" + "="*60)
    print("🔒 测试事务原子性")
    print("="*60)

    print("\n✅ 测试: 验证safe_session的自动提交")
    async with safe_session() as session:
        stmt = select(Player).limit(1)
        player = (await session.execute(stmt)).scalars().first()

        if player:
            original_gold = player.gold
            print(f"   玩家: {player.nickname}")
            print(f"   初始金币: {original_gold}")

            # 修改金币但不手动commit
            player.gold += 1000
            session.add(player)
            print(f"   修改后金币: {player.gold}")
            print("   未手动commit，依赖safe_session的自动提交")

    # 重新查询验证是否提交成功
    async with safe_session() as session:
        player = await session.get(Player, player.id)
        if player.gold == original_gold + 1000:
            print(f"   ✓ 验证成功: 金币正确保存为 {player.gold}")
            # 恢复原值
            player.gold = original_gold
            session.add(player)
        else:
            print(f"   ✗ 验证失败: 金币未正确保存")
            return False

    print("\n" + "="*60)
    print("✅ 事务原子性测试通过！")
    print("="*60)
    return True


async def main():
    """主测试函数"""
    print("\n" + "🔬 Service重构测试工具".center(60, "="))
    print("测试目标: 验证StockService和PartTimeJobService的session管理重构")
    print("="*60)

    all_passed = True

    # 测试股票服务
    try:
        if not await test_stock_service():
            all_passed = False
    except Exception as e:
        print(f"\n❌ StockService测试异常: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试打工服务
    try:
        if not await test_part_time_job_service():
            all_passed = False
    except Exception as e:
        print(f"\n❌ PartTimeJobService测试异常: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试事务原子性
    try:
        if not await test_transaction_atomicity():
            all_passed = False
    except Exception as e:
        print(f"\n❌ 事务原子性测试异常: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 总结
    print("\n" + "="*60)
    if all_passed:
        print("✅ 所有测试通过！Service重构成功！".center(60))
    else:
        print("❌ 部分测试失败，请检查错误信息".center(60))
    print("="*60 + "\n")

    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
