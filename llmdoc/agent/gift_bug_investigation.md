# 送礼功能Bug调研报告

**调研日期**: 2025-11-30
**Bug描述**: 送礼功能没有实际送出去
**调研范围**: `plugins/xiuxian_game/social/` 目录下的送礼系统

---

## Code Sections (The Evidence)

### 命令处理器
- `plugins/xiuxian_game/social/gift.py` (handle_send_gift): 送礼命令入口，处理用户输入，使用Feature Flag在新旧Service间切换
- `plugins/xiuxian_game/social/gift.py:12` (USE_NEW_GIFT_SERVICE): Feature Flag控制，当前值为`True`，启用新版DI架构GiftService
- `plugins/xiuxian_game/social/gift.py:48-82` (handle_send_gift内的逻辑分支): 根据USE_NEW_GIFT_SERVICE选择调用新版或旧版GiftService
- `plugins/xiuxian_game/social/gift.py:43` (safe_session上下文): 命令处理器使用safe_session管理数据库事务

### GiftService (新版 - 当前使用)
- `plugins/xiuxian_game/social/gift_service_new.py` (GiftService): DI架构版本，依赖注入5个Repository/Service
- `plugins/xiuxian_game/social/gift_service_new.py:97-243` (send_gift方法): 送礼核心逻辑
- `plugins/xiuxian_game/social/gift_service_new.py:154` (consume_item调用): 扣除发送者物品 - 调用ItemRepository.consume_item
- `plugins/xiuxian_game/social/gift_service_new.py:198` (add_item调用): 增加接收者物品 - 调用ItemRepository.add_item
- `plugins/xiuxian_game/social/gift_service_new.py:172` (P0修复注释): **关键证据** - 注释显示已移除Line 128的commit()调用
- `plugins/xiuxian_game/social/gift_service_new.py:229` (P0修复注释): **关键证据** - 注释显示已移除Line 192的commit()调用

### GiftService (旧版 - 备份参考)
- `plugins/xiuxian_game/social/gift_service_legacy.py` (GiftService): 静态方法版本，包含session.commit()调用
- `plugins/xiuxian_game/social/gift_service_legacy.py:128` (session.commit()): **关键证据** - 旧版在夫妻送商品后主动提交事务
- `plugins/xiuxian_game/social/gift_service_legacy.py:192` (session.commit()): **关键证据** - 旧版在送礼完成后主动提交事务

### ItemRepository (关键依赖)
- `plugins/xiuxian_game/infrastructure/repositories/item_repository.py:162-183` (consume_item方法): 封装ItemInstance.consume_item静态方法
- `plugins/xiuxian_game/infrastructure/repositories/item_repository.py:146-160` (add_item方法): 封装ItemInstance.add_item静态方法
- `plugins/xiuxian_game/infrastructure/repositories/item_repository.py:180` (consume_item内调用): 调用ItemInstance.consume_item(self._session, ...)
- `plugins/xiuxian_game/infrastructure/repositories/item_repository.py:160` (add_item内调用): 调用ItemInstance.add_item(self._session, ...)

### ItemInstance模型 (底层实现)
- `plugins/xiuxian_game/models/inventory.py:300-392` (add_item静态方法): 向玩家背包添加物品，包含flush但无commit
- `plugins/xiuxian_game/models/inventory.py:391` (flush调用): **关键证据** - add_item仅调用flush，不调用commit
- `plugins/xiuxian_game/models/inventory.py:395-451` (consume_item静态方法): 从玩家背包扣除物品，包含session操作但无commit
- `plugins/xiuxian_game/models/inventory.py:445` (session.delete): 扣除物品时删除记录，但无commit
- `plugins/xiuxian_game/models/inventory.py:447` (session.add): 修改物品数量，但无commit

### safe_session会话管理器
- `plugins/xiuxian_game/models/db.py` (safe_session): 上下文管理器，自动提交成功事务、异常时回滚

---

## Report (The Answers)

### result

**问题1: 送礼命令的入口在哪里？**
- `plugins/xiuxian_game/social/gift.py:23-86` (handle_send_gift函数)
- 命令注册：`send_gift_cmd = on_command("送礼", block=True, priority=5)`

**问题2: 送礼命令使用的是哪个版本的GiftService？**
- 使用新版DI架构的GiftService (`gift_service_new.py`)
- Feature Flag: `USE_NEW_GIFT_SERVICE = True` (Line 12)
- 调用位置: `gift.py:79` - `service.send_gift(sender.id, receiver_uid, item_name, quantity)`

**问题3: 是否有Feature Flag控制新旧Service切换？当前状态？**
- 是，存在Feature Flag: `USE_NEW_GIFT_SERVICE`
- 当前状态: `True` (启用新版)
- 位置: `gift.py:12`

**问题4: GiftService的send_gift方法完整实现是什么？**
- 新版实现位置: `gift_service_new.py:97-243`
- 关键流程:
  1. 验证发送者和接收者 (Line 117-131)
  2. 检查送礼资格 (Line 129)
  3. 验证物品配置 (Line 134-148)
  4. 夫妻送商品特殊处理 (Line 150-173)
  5. 普通送礼流程 (Line 175-243)

**问题5: send_gift方法是否扣除赠送者物品？**
- **是**，扣除逻辑位于:
  - 夫妻送商品: `gift_service_new.py:154` - `await self._item_repo.consume_item(sender_id, item_config.item_id, quantity)`
  - 普通送礼: `gift_service_new.py:192` - `await self._item_repo.consume_item(sender_id, item_config.item_id, max_addable)`
- 底层调用: `ItemRepository.consume_item()` → `ItemInstance.consume_item()`

**问题6: send_gift方法是否增加接收者物品？**
- **是**，增加逻辑位于:
  - `gift_service_new.py:198` - `await self._item_repo.add_item(receiver.id, item_config.item_id, max_addable)`
- 底层调用: `ItemRepository.add_item()` → `ItemInstance.add_item()`

**问题7: 命令处理器是否正确提交数据库事务？**
- **是**，命令处理器使用safe_session上下文管理器 (`gift.py:43`)
- safe_session会在上下文退出时自动提交事务（成功时）或回滚（异常时）
- 事务提交位置: `db.py` (safe_session实现中的__aexit__方法)

**问题8: 是否有异常处理吞掉了错误？**
- **否**，命令处理器未捕获异常
- GiftService内部有try-catch块，但仅用于资源回退，不会吞没错误
- 异常会向上传播到safe_session，触发事务回滚

### 核心问题根因分析

**Bug根因: 新版GiftService移除了commit()调用，依赖调用方提交事务，但命令处理器的safe_session会在Service方法返回后才提交。**

**证据链条**:

1. **Feature Flag启用新版Service** (gift.py:12)
   ```python
   USE_NEW_GIFT_SERVICE = True
   ```

2. **新版Service移除了commit()** (gift_service_new.py:172, 229)
   ```python
   # P0修复: 移除commit() - 由调用方控制事务
   ```

   对比旧版Service (gift_service_legacy.py:128, 192):
   ```python
   await session.commit()  # 旧版有主动提交
   ```

3. **ItemInstance底层方法仅flush不commit** (inventory.py:391, 445-447)
   ```python
   await session.flush()  # 仅flush，不commit
   await session.delete(inv)  # 仅标记删除，不commit
   session.add(inv)  # 仅标记修改，不commit
   ```

4. **命令处理器的safe_session会提交事务** (gift.py:43, 84-86)
   ```python
   async with safe_session() as session:
       # ... 调用 service.send_gift()
       if success:
           await send_gift_cmd.finish(...)  # 正常退出，safe_session会自动commit
   ```

**问题所在**:
- 新版GiftService的设计理念是"由调用方控制事务"，移除了内部的commit()调用
- 命令处理器使用safe_session包裹整个逻辑，理论上会在退出时自动提交
- **如果safe_session正常工作，不应该出现"送礼没有实际送出去"的问题**

**需要进一步验证的疑点**:
1. safe_session是否真的在执行commit？
2. 是否有其他代码路径提前退出导致事务未提交？
3. 是否存在并发问题导致事务被回滚？

### conclusions

1. 当前送礼功能使用新版DI架构的GiftService (USE_NEW_GIFT_SERVICE=True)
2. 新版GiftService已移除内部commit()调用，遵循"调用方控制事务"的设计原则
3. 旧版GiftService包含2处session.commit()调用 (Line 128, 192)
4. 命令处理器使用safe_session上下文管理器包裹整个逻辑
5. ItemInstance底层方法（add_item, consume_item）仅执行flush，不执行commit
6. GiftService.send_gift方法确实扣除发送者物品和增加接收者物品
7. 如果safe_session正常工作，事务应该会自动提交
8. 问题可能出在safe_session实现或调用时序上

### relations

**调用链路**:
1. 用户输入 → Nonebot2事件 → `gift.py:handle_send_gift`
2. `handle_send_gift` → 打开`safe_session` → 创建GiftServiceNew实例 → 调用`service.send_gift()`
3. `service.send_gift()` → 调用`ItemRepository.consume_item()` → 调用`ItemInstance.consume_item()`
4. `service.send_gift()` → 调用`ItemRepository.add_item()` → 调用`ItemInstance.add_item()`
5. `service.send_gift()` → 返回结果 → `handle_send_gift` → `send_gift_cmd.finish()`
6. `safe_session`上下文退出 → **应该执行commit()**

**依赖关系**:
- `gift.py` 依赖 `gift_service_new.py` (通过Feature Flag)
- `gift_service_new.py` 依赖 `ItemRepository`
- `ItemRepository` 依赖 `ItemInstance` (静态方法)
- `ItemInstance` 依赖 `AsyncSession` (传入的session参数)
- 整个调用链依赖 `safe_session` 的事务管理

**Feature Flag控制点**:
- `gift.py:12` - USE_NEW_GIFT_SERVICE (主控)
- `gift.py:48-82` - 基于Flag选择Service版本
- `gift_service.py:14` - USE_NEW_MENTORSHIP_SERVICE (旧版Service内部依赖)

**事务边界**:
- 旧版: Service内部提交 (gift_service_legacy.py:128, 192)
- 新版: 调用方提交 (依赖safe_session)
- 问题: 如果safe_session未提交，则整个事务回滚

---

## 修复方案 ✅

### ✅ 已采用：在safe_session中排除Nonebot2流程控制异常（根本解决）

**修复位置**: `plugins/xiuxian_game/models/db.py:200-215`

**修复代码**:
```python
@asynccontextmanager
async def safe_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        except Exception as e:
            # 排除 Nonebot2 的流程控制异常
            try:
                from nonebot.exception import FinishedException, PausedException, RejectedException
                if isinstance(e, (FinishedException, PausedException, RejectedException)):
                    await session.commit()  # ✅ 提交事务
                    raise e  # 重新抛出异常继续流程控制
            except ImportError:
                pass

            await session.rollback()
            raise e
```

**优点**:
- ✅ 一处修改，全局生效（自动修复20-30个命令处理器）
- ✅ 符合DI架构"调用方控制事务"的设计原则
- ✅ 代码简洁，无需在每个命令处理器中手动处理
- ✅ 向后兼容，不影响非Nonebot环境

**影响范围**:
- 全局修复所有使用 `finish()` / `pause()` / `reject()` 的命令处理器
- gift.py 恢复到干净状态（无需手动commit）

**提交记录**:
- commit 7c1aded: 根本性修复
- commit af8ef1a: 临时修复（已被7c1aded替代）

---

### 其他备选方案（未采用）

**方案1: 恢复旧版GiftService**
- 将Feature Flag设为False
- 缺点：回退重构进度

**方案2: 在命令处理器中手动commit**
- 在每个finish()前添加commit
- 缺点：需要修改20-30个文件，代码冗余

**方案3: 在Service中恢复commit**
- 在Service内部调用commit
- 缺点：破坏"调用方控制事务"设计原则

---

**最终选择理由**:
- 在safe_session中排除异常是最优雅的根本解决方案
- 符合"Don't Repeat Yourself"原则
- 保持DI架构的完整性和一致性
