#!/usr/bin/env python3
"""测试 UnitOfWork 是否正确处理异常（包括 finish() 抛出的异常）"""

import asyncio


class CustomException(Exception):
    """模拟 FinishedException"""
    pass


class MockSession:
    """模拟数据库会话"""
    def __init__(self, session_id):
        self.session_id = session_id
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self):
        print(f"  Session {self.session_id}: commit()")
        self.committed = True

    async def rollback(self):
        print(f"  Session {self.session_id}: rollback()")
        self.rolled_back = True

    async def close(self):
        print(f"  Session {self.session_id}: close()")
        self.closed = True


class SimpleUnitOfWork:
    """简化的 UnitOfWork 实现"""
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._session = None

    async def __aenter__(self):
        self._session = self._session_factory()
        print(f"[UnitOfWork] 创建会话: {self._session.session_id}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """当前的实现"""
        try:
            if exc_type is not None:
                print(f"[UnitOfWork] 检测到异常: {exc_type.__name__}")
                await self._session.rollback()
            else:
                print(f"[UnitOfWork] 没有异常，提交")
                await self._session.commit()
        finally:
            print(f"[UnitOfWork] 关闭会话")
            await self._session.close()

        # 不抑制异常
        return False


async def test_normal_flow():
    """测试正常流程"""
    print("\n" + "="*60)
    print("测试 1: 正常流程（无异常）")
    print("="*60)

    session_id = 1

    def session_factory():
        return MockSession(session_id)

    async with SimpleUnitOfWork(session_factory) as uow:
        print("执行业务逻辑...")

    session = MockSession(session_id)  # 检查状态
    print(f"\n结果:")
    print(f"  已提交: {session.committed}")
    print(f"  已回滚: {session.rolled_back}")
    print(f"  已关闭: {session.closed}")


async def test_exception_in_block():
    """测试在 UnitOfWork 内部抛出异常"""
    print("\n" + "="*60)
    print("测试 2: 在 UnitOfWork 内部抛出异常")
    print("="*60)

    session_id = 2
    session_obj = None

    def session_factory():
        nonlocal session_obj
        session_obj = MockSession(session_id)
        return session_obj

    try:
        async with SimpleUnitOfWork(session_factory) as uow:
            print("执行业务逻辑...")
            print("抛出 CustomException...")
            raise CustomException("模拟 finish() 异常")
    except CustomException:
        print("✅ CustomException 被捕获")

    print(f"\n结果:")
    print(f"  已提交: {session_obj.committed}")
    print(f"  已回滚: {session_obj.rolled_back}")
    print(f"  已关闭: {session_obj.closed}")

    if session_obj.closed and session_obj.rolled_back:
        print("✅ 会话正确关闭和回滚")
    else:
        print("❌ 会话未正确清理")


async def test_nested_context():
    """测试嵌套上下文"""
    print("\n" + "="*60)
    print("测试 3: 嵌套上下文中抛出异常")
    print("="*60)

    session_id = 3
    session_obj = None

    def session_factory():
        nonlocal session_obj
        session_obj = MockSession(session_id)
        return session_obj

    try:
        async with SimpleUnitOfWork(session_factory) as uow:
            print("外层: 执行业务逻辑...")

            # 模拟在内部某处调用 finish()
            async def some_function():
                print("内层: 检查条件...")
                print("内层: 条件不满足，抛出异常...")
                raise CustomException("模拟 finish() 异常")

            await some_function()

            print("外层: 这行不会被执行")

    except CustomException:
        print("✅ CustomException 被捕获")

    print(f"\n结果:")
    print(f"  已提交: {session_obj.committed}")
    print(f"  已回滚: {session_obj.rolled_back}")
    print(f"  已关闭: {session_obj.closed}")

    if session_obj.closed and session_obj.rolled_back:
        print("✅ 即使在嵌套调用中抛出异常，会话也被正确清理")
    else:
        print("❌ 会话未正确清理")


async def main():
    await test_normal_flow()
    await test_exception_in_block()
    await test_nested_context()

    print("\n" + "="*60)
    print("测试结论")
    print("="*60)
    print("""
当前的 UnitOfWork.__aexit__ 实现使用了 try...finally，
这意味着即使在 async with 块内抛出异常（如 finish()），
finally 块中的 session.close() 也会被执行。

因此，理论上不应该出现连接泄漏问题。

但实际运行中仍出现连接泄漏警告，可能的原因：
1. finally 块没有被执行（极其罕见，除非进程崩溃）
2. session.close() 执行了但连接未归还（SQLAlchemy bug？）
3. 存在其他未使用 UnitOfWork 的直接会话使用

建议：
1. 检查是否有未使用 UnitOfWork 的地方
2. 检查 session.close() 的实现是否正确
3. 添加详细日志来追踪会话生命周期
    """)


if __name__ == "__main__":
    asyncio.run(main())
